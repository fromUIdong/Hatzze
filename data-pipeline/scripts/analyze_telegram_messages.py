"""텔레그램 메시지를 LLM(Claude Haiku)으로 분류해 telegram_message_analysis 에 저장한다.

메시지 1건당 (1) 톤 = positive/neutral/negative, (2) 종목명이 아닌 화제어 0~3개를 뽑는다.
이 표를 집계해 생태계 센티먼트·이슈 키워드 카드가 만들어진다(calculate_telegram_sentiment.py).

설계 판단:
- **메시지 단위로 저장한다.** 하루치 요약만 만들면 다음 날 비교 대상이 없다. 한 번 분류해
  두면 날짜·테마·종목 어느 축으로든 재집계되고, 화면에 뜨는 수치("긍정 62%")는 LLM이 아니라
  SQL이 센다. 종목추출·테마 로테이션과 같은 철학이다.
- **증분 처리.** fetch_telegram.py 는 7일 창을 매 실행 재수집하지만(조회수 갱신용),
  분석은 파이프라인에서 유일하게 돈이 드는 단계라 한 번 한 건은 절대 다시 호출하지 않는다.
- **화제어는 자유 추출.** 새로 뜨는 이슈를 놓치지 않는 게 '이슈 키워드' 카드의 존재
  이유라 사전에서 고르게 하지 않는다. 표기 흔들림(HBM/에이치비엠)은 집계 단계의
  별칭 사전(config/issue_keywords.py)이 흡수한다.
- **본문 앞 600자만.** 실측 p90이 989자, 최대 6,503자인데 뒤쪽은 대부분 면책·홍보 문구다.
  앞부분에 핵심이 있어 600자로 자른다(비용도 같이 줄어든다).

실패해도 파이프라인 본체엔 영향이 없어야 하므로, 키가 없으면 조용히 건너뛰고 배치 하나가
깨져도 나머지는 계속 처리한다(generate_daily_summary.py 와 같은 방침).

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/analyze_telegram_messages.py --dry-run    # 대상 건수·프롬프트만 확인
    python scripts/analyze_telegram_messages.py --limit 30   # 소량 실호출(검증용)
    python scripts/analyze_telegram_messages.py              # 미분석분 전량
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from common.config import ANTHROPIC_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.supabase_client import load_all  # noqa: E402

# Haiku 4.5 — 분류는 대량 호출이라 속도/비용이 중요하고, 3지선다 + 명사 추출 난이도엔
# 충분하다. 하루 ~300건이면 월 2~3달러 수준. (히어로 요약도 같은 모델을 쓴다.)
MODEL = "claude-haiku-4-5"

# 한 호출에 넣을 메시지 수. 크게 잡을수록 호출당 오버헤드(시스템 프롬프트)가 분산되지만,
# 너무 크면 모델이 뒤쪽 항목을 성의 없이 처리하고 한 배치 실패의 손실도 커진다.
BATCH_SIZE = 15

# 본문에서 모델에 넘길 최대 글자수.
TEXT_CAP = 600

SYSTEM = """\
당신은 한국 주식 텔레그램 채널·채팅방의 메시지를 분류하는 분석기입니다.
각 메시지에 대해 (1) 톤, (2) 화제어를 뽑아 JSON으로만 답합니다.

[톤 분류 — 글쓴이가 시장/종목을 어떤 분위기로 말하는가]
- positive: 기대·호재·강세를 말하는 톤. 실적 개선, 수주, 목표가 상향, 낙관적 전망.
- negative: 우려·악재·약세를 말하는 톤. 실적 부진, 규제, 손실, 비관적 전망.
- neutral: 사실 전달 위주. 시황 브리핑, 공시 요약, 일정 안내, 숫자 나열, 광고·공지.
판단이 애매하면 neutral 입니다. 글쓴이의 태도를 보세요 — 주가가 내렸다는 사실을
담담히 전하면 neutral 이고, 그걸 두고 걱정하거나 위험을 경고하면 negative 입니다.

[화제어 0~3개]
- 지금 무엇이 화제인지 보여주는 말을 뽑습니다. 예: HBM, 관세, 금리인하, 수주, 공매도.
- **종목명·기업명·인명·채널명은 절대 넣지 마세요.** (종목은 따로 집계합니다.)
- "주가", "시장", "오늘", "상승"처럼 아무 정보가 없는 일반어도 넣지 마세요.
- 메시지에 실제로 등장한 표현을 씁니다. 없으면 빈 배열로 두세요 — 억지로 채우지 마세요.
- **짧은 명사로 쓰세요 — 되도록 2~6글자, 최대 10글자.** 조사·서술어를 떼고 압축합니다.
  (예: "금리를 인하" → "금리인하", "영업이익 컨센서스 상회" → "실적호조")
  문장이나 긴 구절을 넣으면 안 됩니다 — 같은 이슈가 제각각 표현돼 집계가 깨집니다.

[입력 형식] 각 메시지는 "### <번호>" 줄로 시작합니다.
[출력] 모든 번호에 대해 정확히 하나씩, 입력 순서대로 결과를 만드세요."""

# Structured outputs — 스키마로 형식을 강제해 파싱 실패를 없앤다(Haiku 4.5 지원).
# ※ 배열 길이 제약(maxItems)은 스키마에서 지원되지 않으므로 개수 제한은 프롬프트로 건다.
SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "neutral", "negative"],
                    },
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["n", "sentiment", "keywords"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def pending_messages(db) -> list[dict]:
    """아직 분류하지 않은 메시지(본문 있는 것만)를 오래된 순으로 돌려준다.

    분류 완료 목록을 통째로 받아 파이썬에서 빼는 방식이다. PostgREST 로는 복합키
    'not in' 을 깔끔히 표현하기 어렵고, 규모가 수천 건이라 메모리에서 처리해도 충분하다.
    """
    messages = load_all(db, "telegram_messages", "channel_handle,message_id,posted_at,text")
    done = load_all(db, "telegram_message_analysis", "channel_handle,message_id")
    done_keys = {(r["channel_handle"], r["message_id"]) for r in done}

    pending = [
        m
        for m in messages
        if (m["channel_handle"], m["message_id"]) not in done_keys
        and (m.get("text") or "").strip()
    ]
    pending.sort(key=lambda m: m["posted_at"])
    return pending


def build_prompt(batch: list[dict]) -> str:
    """배치를 '### 번호' 로 구분한 하나의 사용자 메시지로 만든다."""
    parts = []
    for i, m in enumerate(batch, start=1):
        text = (m.get("text") or "").strip()
        if len(text) > TEXT_CAP:
            text = text[:TEXT_CAP] + " …(생략)"
        parts.append(f"### {i}\n{text}")
    return "\n\n".join(parts)


def classify(client: Anthropic, batch: list[dict]) -> dict[int, dict]:
    """배치 1개를 분류해 {번호: {sentiment, keywords}} 로 돌려준다."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(batch)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    parsed = json.loads(raw)
    return {int(r["n"]): r for r in parsed.get("results", [])}


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    if not ANTHROPIC_API_KEY and not dry_run:
        # 키가 없으면 조용히 건너뛴다(설정 전 로컬/CI에서도 파이프라인이 안 깨지게).
        print("[skip] ANTHROPIC_API_KEY가 없어 메시지 분류를 건너뜁니다.")
        return

    db = get_client()
    pending = pending_messages(db)
    if not pending:
        print("[안내] 새로 분류할 메시지가 없습니다.")
        return

    if limit is not None:
        pending = pending[:limit]

    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    chars = sum(min(len((m.get("text") or "")), TEXT_CAP) for m in pending)
    print(f"[대상] 미분류 메시지 {len(pending)}건 · {len(batches)}회 호출 · 본문 {chars:,}자")

    if dry_run:
        print("\n[프롬프트 미리보기 — 첫 배치]")
        print("─" * 60)
        print(build_prompt(batches[0])[:1500])
        print("─" * 60)
        print("[dry-run] LLM 호출·저장 없이 종료합니다.")
        return

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    rows: list[dict] = []
    failed_batches = 0
    for bi, batch in enumerate(batches, start=1):
        try:
            result = classify(client, batch)
        except Exception as exc:  # 배치 하나가 깨져도 나머지는 계속 처리한다
            failed_batches += 1
            print(f"  [{bi}/{len(batches)}] 실패: {type(exc).__name__}: {exc}")
            continue

        got = 0
        for i, m in enumerate(batch, start=1):
            r = result.get(i)
            if not r:
                continue  # 모델이 빠뜨린 번호 — 다음 실행에서 미분류로 다시 잡힌다
            keywords = [k.strip() for k in r.get("keywords", []) if k and k.strip()]
            rows.append(
                {
                    "channel_handle": m["channel_handle"],
                    "message_id": m["message_id"],
                    "sentiment": r["sentiment"],
                    "keywords": keywords[:3],  # 개수 제한은 프롬프트 + 여기서 이중으로
                    "model": MODEL,
                }
            )
            got += 1
        print(f"  [{bi}/{len(batches)}] {got}/{len(batch)}건 분류")

    if not rows:
        print("[경고] 저장할 분류 결과가 없습니다.")
        return

    for i in range(0, len(rows), 500):
        db.table("telegram_message_analysis").upsert(
            rows[i : i + 500], on_conflict="channel_handle,message_id"
        ).execute()

    tone = {"positive": 0, "neutral": 0, "negative": 0}
    for r in rows:
        tone[r["sentiment"]] += 1
    total = len(rows)
    print(
        f"[Supabase] telegram_message_analysis {total}건 저장 · "
        f"긍정 {tone['positive']}({tone['positive'] * 100 // total}%) · "
        f"중립 {tone['neutral']}({tone['neutral'] * 100 // total}%) · "
        f"비관 {tone['negative']}({tone['negative'] * 100 // total}%)"
    )
    if failed_batches:
        print(f"[안내] 실패한 배치 {failed_batches}개는 다음 실행에서 다시 시도됩니다.")

    # 남은 잔량을 찍는다. 이 단계는 비용 때문에 증분 처리라, 유입이 처리 속도보다 빠르면
    # 잔량이 조용히 쌓인다 — 그러면 센티먼트 집계가 최근 메시지를 빼놓고 계산하게 되는데
    # 지금은 그걸 알 방법이 없다(실측 2026-07-23: 수집 3,396건 중 3,147건만 분류됨).
    # 화면에 띄울 일은 아니고, 실행 로그에서 추세만 보이면 된다.
    left = len(pending_messages(db))
    if left:
        print(f"[잔량] 아직 분류되지 않은 메시지 {left}건 — 다음 실행에서 이어서 처리합니다.")
    else:
        print("[잔량] 미분류 메시지 없음 — 수집분을 모두 따라잡았습니다.")


if __name__ == "__main__":
    main()
