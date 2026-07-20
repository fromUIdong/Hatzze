"""집계 결과를 LLM(Claude Haiku)으로 문장화해 카더라 리포트 카드에 넣는다.

  telegram_daily_brief.sentiment_summary : 생태계 센티먼트 카드 상단 총평(2문장)
  telegram_stock_narrative.narrative     : 주요 종목 리포트의 흐름 요약(종목당 75~80자)

앞 단계(calculate_telegram_sentiment.py)가 이미 수치를 다 세어 놨다. 여기서 하는 일은
**그 수치를 읽어 문장으로 옮기는 것뿐**이고, 모델이 새 숫자를 만들어내면 안 된다.

⚠️ 공개 저장소 + 법적 이유로 매수·매도·투자권유·목표가·상승/하락 전망은 시스템
프롬프트에서 강하게 금지한다(히어로 요약 generate_daily_summary.py 와 같은 방침).
면책 문구는 프론트가 따로 렌더하므로 문장에 넣지 않는다.

키가 없거나 호출이 실패해도 파이프라인 본체엔 영향이 없도록 조용히 건너뛴다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/generate_telegram_narratives.py --dry-run  # digest만 출력(호출 없음)
    python scripts/generate_telegram_narratives.py            # 생성 + 저장
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from common.config import ANTHROPIC_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.timeutil import KST  # noqa: E402
from common.supabase_client import load_all  # noqa: E402

MODEL = "claude-haiku-4-5"

# 요약을 만들 종목 수. 카드는 상위 3종목만 보여주지만, 프론트는 페이지 요청 시점에
# 상위 종목을 다시 뽑는다 — 파이프라인 실행 이후 순위가 바뀌어도 문장이 비지 않도록
# 여유를 둔다(추가 3건은 하루 3회 호출이라 비용상 무의미한 수준).
NARRATIVE_TOP_N = 6

# 종목 요약 길이. **목표**는 75~80자 — 반칸 카드에서 3줄이 꽉 차는 구간이라 종목별
# 카드 높이가 가지런해진다. **허용**은 70~83자로 조금 넓다:
#   - 83자 초과 = 4줄이 되어 레이아웃이 깨진다(진짜 하한선. app/telegram/page.tsx 주석 참고)
#   - 70자 미만 = 3줄을 못 채워 눈에 띄게 짧다
# 6자짜리 좁은 창을 매번 맞추긴 어려워서, 목표를 벗어나면 다시 쓰게 하되 끝내 못 맞추면
# 허용 범위 안에서는 그냥 저장한다 — 가장 많이 언급된 종목의 문단이 통째로 비는 게
# 몇 자 짧은 것보다 나쁘기 때문(실제로 SK하이닉스가 66자로 탈락한 적이 있다).
LEN_MIN, LEN_MAX = 75, 80
LEN_HARD_MIN, LEN_HARD_MAX = 70, 83
MAX_RETRIES = 3

# 집계 창. 프론트 카드가 "최근 7일"이라 **오늘 포함 7일**이어야 화면 수치와 맞는다
# (days=7로 빼면 8일치가 잡혀 화제어 횟수가 화면보다 커진다).
WINDOW_DAYS = 7
WINDOW_OFFSET = WINDOW_DAYS - 1

COMMON = """\
당신은 한국 주식 텔레그램 채널들을 분석하는 대시보드 '카더라 리포트'의 문장을 쓰는 작성자입니다.
아래 데이터를 보고, 지시된 문장만 씁니다.

[말투]
- 친근한 존댓말로 끝맺습니다(예: "~이에요", "~네요", "~어 보여요"). 과장 없이 데이터만큼만.

[데이터 읽는 법]
- 이 데이터는 '텔레그램에서 무엇이 얼마나·어떤 톤으로 회자됐는가'이지, 주가나 기업 실적이
  아닙니다. 반드시 "언급", "화제", "관심" 같은 말로 서술하세요.
- 주어진 숫자만 씁니다. 데이터에 없는 수치·사건·이유를 지어내지 마세요.

[절대 하지 말 것]
- 매수/매도/투자 권유·신호, 목표가, 주가 상승/하락 예측('오를 것/내릴 것/앞으로').
- **투자자의 행동이나 속내를 추정하는 말**('수익 실현 타이밍', '저가 매수 기회',
  '차익 실현 물량' 등). 데이터는 메시지의 톤과 화제일 뿐, 누가 무엇을 하려는지가 아닙니다.
- 데이터에 없는 인과 추론(예: 어떤 화제어가 많다고 해서 그 이유를 지어내기).
- 특정 인물·정치 언급, 확인되지 않은 루머의 사실 단정.
- 면책 문구(화면에 따로 있음).

[출력] 설명·머리말 없이, 지시된 문장만 출력하세요. 마크다운·목록·제목 금지."""

BRIEF_TONE_SYSTEM = COMMON + """

[이번 문장 — 전체 분위기]
오늘 텔레그램 메시지의 톤 구성(낙관/중립/비관 비율)과 가장 많이 오르내린 화제어를 엮어,
지금 이 생태계의 분위기를 한 문장으로 요약하세요. 비율 수치를 그대로 읽어주기보다,
무엇이 대화를 주도하고 있는지가 드러나게 쓰세요."""

BRIEF_CONTRAST_SYSTEM = COMMON + """

[이번 문장 — 테마별 온도차]
테마별 낙관 비중을 비교해, 관심이나 분위기가 어느 테마로 쏠리고 어느 쪽이 식었는지를
한 문장으로 쓰세요. 테마 이름을 최소 2개 언급해 대비가 드러나게 하세요.
표본(메시지 수)이 너무 적은 테마는 언급하지 마세요."""

STOCK_SYSTEM = COMMON + f"""

[이번 문장 — 종목별 흐름 요약]
한 종목에 대해, 최근 {WINDOW_DAYS}일 텔레그램에서 그 종목이 어떻게 회자됐는지를 씁니다.
- 일별 언급 추이(늘었는지 줄었는지)와 어떤 맥락에서 언급됐는지를 함께 담으세요.
- 대표 메시지 발췌는 '무엇이 화제였는지'의 근거로만 쓰고, 그대로 베끼지 마세요.
- **반드시 {LEN_MIN}자 이상 {LEN_MAX}자 이하**로 쓰세요(공백 포함). 카드 높이가 이 길이에
  맞춰져 있어 넘치면 레이아웃이 깨집니다. 한 문장 또는 두 문장으로 자연스럽게 맞추세요."""


def build_brief_digest(db, latest: str) -> str | None:
    """센티먼트 총평용 digest.

    창은 최근 7일 — 카드 헤더가 '최근 7일'이라 화면의 막대 비율과 총평이 같은 기간을
    말해야 한다. 하루치만 쓰면 주말처럼 표본이 얇은 날에 총평이 튄다.
    """
    since = (datetime.fromisoformat(latest).date() - timedelta(days=WINDOW_OFFSET)).isoformat()
    sent = [
        r
        for r in load_all(
            db,
            "telegram_sentiment_daily",
            "date,scope,positive_count,neutral_count,negative_count,message_count",
        )
        if r["date"] >= since
    ]

    window: dict[str, Counter] = defaultdict(Counter)
    for r in sent:
        c = window[r["scope"]]
        c["positive"] += r["positive_count"]
        c["neutral"] += r["neutral_count"]
        c["negative"] += r["negative_count"]
        c["total"] += r["message_count"]

    overall = window.get("overall")
    if not overall or not overall["total"]:
        return None

    n = overall["total"]
    lines = [
        f"[전체] 최근 {WINDOW_DAYS}일 분석 메시지 {n}건 · "
        f"낙관 {overall['positive'] * 100 // n}% · "
        f"중립 {overall['neutral'] * 100 // n}% · "
        f"비관 {overall['negative'] * 100 // n}%",
    ]

    # 최근 며칠 낙관 비율 궤적(오래된→오늘) — 분위기가 어느 쪽으로 움직였는지의 근거.
    trail = []
    for r in sorted((x for x in sent if x["scope"] == "overall"), key=lambda x: x["date"])[-5:]:
        if r["message_count"]:
            trail.append(f"{r['date'][5:]} {r['positive_count'] * 100 // r['message_count']}%")
    if len(trail) > 1:
        lines.append(f"[낙관 비율 추이] {' → '.join(trail)}")

    lines.append("")
    lines.append("[테마별] 낙관 비중 (메시지 수가 적은 테마는 참고만)")
    themes = sorted(
        ((s, c) for s, c in window.items() if s != "overall" and c["total"]),
        key=lambda kv: kv[1]["total"],
        reverse=True,
    )[:6]
    for scope, c in themes:
        m = c["total"]
        lines.append(
            f"- {scope}: {m}건 · 낙관 {c['positive'] * 100 // m}% · "
            f"비관 {c['negative'] * 100 // m}%"
        )

    kws = load_all(db, "telegram_keyword_daily", "date,keyword,mention_count")
    recent = Counter()
    for r in kws:
        if r["date"] >= since:
            recent[r["keyword"]] += r["mention_count"]
    if recent:
        lines.append("")
        lines.append(
            f"[최근 {WINDOW_DAYS}일 화제어] "
            + ", ".join(f"{w} {n}회" for w, n in recent.most_common(10))
        )
    return "\n".join(lines)


def build_stock_digests(db, latest: str) -> list[tuple[str, str, str]]:
    """(종목코드, 종목명, digest) 목록. 최근 창의 주목도 상위 종목만."""
    since = (datetime.fromisoformat(latest).date() - timedelta(days=WINDOW_OFFSET)).isoformat()

    daily = [
        r
        for r in load_all(
            db, "telegram_stock_daily", "date,stock_code,mention_count,weighted_score"
        )
        if r["date"] >= since
    ]
    if not daily:
        return []

    agg: dict[str, dict] = defaultdict(lambda: {"w": 0.0, "m": 0, "by_date": {}})
    for r in daily:
        a = agg[r["stock_code"]]
        a["w"] += float(r["weighted_score"] or 0)
        a["m"] += r["mention_count"] or 0
        a["by_date"][r["date"]] = r["mention_count"] or 0
    top = sorted(agg.items(), key=lambda kv: kv[1]["w"], reverse=True)[:NARRATIVE_TOP_N]

    stocks = load_all(db, "stocks", "code,name")
    name_of = {s["code"]: s["name"] for s in stocks}

    mentions = load_all(db, "telegram_message_stocks", "channel_handle,message_id,stock_code")
    msgs = {
        (m["channel_handle"], m["message_id"]): m
        for m in load_all(
            db, "telegram_messages", "channel_handle,message_id,posted_at,text,views,forwards"
        )
    }
    analysis = {
        (a["channel_handle"], a["message_id"]): a["sentiment"]
        for a in load_all(db, "telegram_message_analysis", "channel_handle,message_id,sentiment")
    }

    by_code: dict[str, list[tuple]] = defaultdict(list)
    for m in mentions:
        by_code[m["stock_code"]].append((m["channel_handle"], m["message_id"]))

    out = []
    for code, a in top:
        name = name_of.get(code, code)
        series = " → ".join(
            f"{d[5:]} {a['by_date'].get(d, 0)}회" for d in sorted(a["by_date"])
        )
        lines = [
            f"[종목] {name} ({code})",
            f"[최근 {WINDOW_DAYS}일 언급] 총 {a['m']}회",
            f"[일별 추이] {series}",
        ]

        keys = [k for k in by_code.get(code, []) if k in msgs and (msgs[k].get("text") or "").strip()]
        keys = [k for k in keys if msgs[k]["posted_at"][:10] >= since]

        tone = Counter(analysis[k] for k in keys if k in analysis)
        if tone:
            t = sum(tone.values())
            lines.append(
                f"[언급 톤] 낙관 {tone['positive'] * 100 // t}% · "
                f"중립 {tone['neutral'] * 100 // t}% · 비관 {tone['negative'] * 100 // t}%"
            )

        # 가장 널리 퍼진 메시지 3건을 근거로 준다 — '왜 화제였는지'를 지어내지 않도록.
        keys.sort(
            key=lambda k: (msgs[k].get("views") or 0) + (msgs[k].get("forwards") or 0) * 3,
            reverse=True,
        )
        if keys:
            lines.append("")
            lines.append("[대표 메시지 발췌]")
            for k in keys[:3]:
                text = " ".join((msgs[k].get("text") or "").split())[:180]
                lines.append(f"- {text}")
        out.append((code, name, "\n".join(lines)))
    return out


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]

    if not ANTHROPIC_API_KEY and not dry_run:
        print("[skip] ANTHROPIC_API_KEY가 없어 문장 생성을 건너뜁니다.")
        return

    db = get_client()

    # 기준일 = 집계가 존재하는 가장 최근 날짜(오늘 파이프라인이 아직 안 돌았어도 맞춘다).
    rows = (
        db.table("telegram_sentiment_daily")
        .select("date")
        .order("date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        print("[skip] telegram_sentiment_daily 가 비어 있습니다. "
              "먼저 calculate_telegram_sentiment.py 를 실행하세요.")
        return
    latest = rows[0]["date"]
    print(f"[기준일] {latest}")

    brief_digest = build_brief_digest(db, latest)
    stock_digests = build_stock_digests(db, latest)

    if dry_run:
        print("─" * 60)
        print(brief_digest or "(총평 digest 없음)")
        for code, name, d in stock_digests:
            print("─" * 60)
            print(d)
        print("─" * 60)
        print("[dry-run] LLM 호출·저장 없이 종료합니다.")
        return

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def ask(system: str, digest: str, max_tokens: int = 400) -> str:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": digest}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    # ── 총평 2문장 ──────────────────────────────────────────────────────────
    # 한 번의 호출로 "정확히 2문장"을 강제하면 문장 수가 흔들린다(히어로 요약에서 겪음).
    # 문장별로 따로 생성해 개수를 결정적으로 고정하고, 카드가 한 문단으로 렌더하므로
    # 공백으로 이어 붙인다.
    if brief_digest:
        try:
            tone_sentence = ask(BRIEF_TONE_SYSTEM, brief_digest)
            contrast_sentence = ask(BRIEF_CONTRAST_SYSTEM, brief_digest)
            summary = f"{tone_sentence} {contrast_sentence}".strip()
            if summary:
                db.table("telegram_daily_brief").upsert(
                    {
                        "date": latest,
                        "sentiment_summary": summary,
                        "model": MODEL,
                        # upsert의 UPDATE 경로에서는 컬럼 기본값(now())이 다시 안 걸리므로
                        # 갱신 시각을 명시해 준다.
                        "updated_at": datetime.now(KST).isoformat(),
                    },
                    on_conflict="date",
                ).execute()
                print(f"[총평] {summary}")
        except Exception as exc:
            print(f"[WARNING] 총평 생성 실패: {type(exc).__name__}: {exc}")
    else:
        print("[안내] 총평을 만들 집계가 없어 건너뜁니다.")

    # ── 종목 흐름 요약 ──────────────────────────────────────────────────────
    saved = 0
    for code, name, digest in stock_digests:
        try:
            # 목표 범위에 들 때까지 다시 쓰게 하되, 시도한 문장을 전부 후보로 모아 둔다.
            candidates = [ask(STOCK_SYSTEM, digest)]
            for attempt in range(MAX_RETRIES):
                if LEN_MIN <= len(candidates[-1]) <= LEN_MAX:
                    break
                cur = candidates[-1]
                need = "늘려" if len(cur) < LEN_MIN else "줄여"
                fix = (
                    f"방금 쓴 문장은 {len(cur)}자예요. 뜻은 유지하면서 {need} "
                    f"{LEN_MIN}~{LEN_MAX}자로 다시 써 주세요.\n\n"
                    f"{digest}\n\n[방금 쓴 문장]\n{cur}"
                )
                candidates.append(ask(STOCK_SYSTEM, fix))

            # 목표 범위가 있으면 그중 첫 번째, 없으면 허용 범위 중 목표 한가운데에 가장 가까운 것.
            mid = (LEN_MIN + LEN_MAX) / 2
            in_goal = [t for t in candidates if LEN_MIN <= len(t) <= LEN_MAX]
            in_ok = [t for t in candidates if LEN_HARD_MIN <= len(t) <= LEN_HARD_MAX]
            if in_goal:
                text = in_goal[0]
            elif in_ok:
                text = min(in_ok, key=lambda t: abs(len(t) - mid))
            else:
                lens = ", ".join(str(len(t)) for t in candidates)
                print(f"  [{name}] 길이({lens}자)가 허용 범위를 벗어나 저장하지 않습니다.")
                continue
            db.table("telegram_stock_narrative").upsert(
                {"date": latest, "stock_code": code, "narrative": text, "model": MODEL},
                on_conflict="date,stock_code",
            ).execute()
            saved += 1
            print(f"  [{name}] ({len(text)}자) {text}")
        except Exception as exc:
            print(f"  [{name}] 실패: {type(exc).__name__}: {exc}")

    print(f"[Supabase] telegram_stock_narrative {saved}/{len(stock_digests)}종목 저장")


if __name__ == "__main__":
    main()
