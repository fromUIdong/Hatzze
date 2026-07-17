"""오늘의 과열도 지수와 지표들을 LLM(Claude Haiku)으로 2~3문장 요약해
daily_score.ai_summary에 저장한다. 프론트 히어로 카드가 이 문장을 읽어 렌더한다.

calculate_score.py가 daily_score/indicator_values를 채운 뒤 실행하는 후속 단계다.
LLM 호출이 실패하거나 키가 없어도 파이프라인 본체(점수 계산)엔 영향이 없도록,
워크플로에선 continue-on-error로 돌리고 실패 알림 집계에서도 제외한다.

⚠️ 공개 저장소 + 법적 이유로, 이 요약은 시장의 "과열도"만 서술한다. 매수·매도·투자
권유, 목표가, 상승/하락 전망은 시스템 프롬프트에서 강하게 금지한다(아래 SYSTEM).
숫자는 지표가 준 값만 쓰고 지어내지 않는다. 면책 문구는 프론트가 따로 보여주므로
요약엔 넣지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from common.config import ANTHROPIC_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

# Haiku 4.5 — 2~3문장 짧은 요약엔 충분히 빠르고 저렴하다. 하루 2회 실행이라 비용은
# 사실상 무시 가능. (thinking/effort 파라미터는 Haiku 4.5에서 불필요/미지원이라 안 쓴다.)
MODEL = "claude-haiku-4-5"

# Hit(초고온 진입) 판정선 = 진행률 ≥ 75. calculate_score.py의 HIT_ZONE과 동일하게 맞춘다.
HIT_ZONE = 75.0


def cap_progress(progress: float) -> float:
    """진행률을 0~100으로 클램핑. calculate_score.cap_progress와 동일."""
    return min(max(progress, 0.0), 100.0)


def stage_for_score(score: float) -> str:
    """종합 점수 → 구간. calculate_score.stage_for_score와 동일(밴드 25/50/75)."""
    if score < 25:
        return "저온"
    if score < 50:
        return "상온"
    if score < 75:
        return "고온"
    return "초고온"


SYSTEM = """\
당신은 한국 주식시장의 "과열도(온도)"를 보여주는 대시보드 '햇쩨(hatzze)'의 오늘의 요약을 쓰는 작성자입니다.

당신이 쓰는 문장은 아래 '오프너' 문장 바로 뒤에 이어 붙습니다:
  "오늘은 시장 지표 N개, 감성 지표 M개가 기준선을 넘었어요. 지표들이 가리키는 현재 시장 온도는 XX 구간이에요."
따라서 전체 과열도 지수·구간을 다시 말하지 말고, 곧바로 오늘 눈여겨볼 지표 이야기로
자연스럽게 이어가세요. "특히", "눈에 띄는 건" 같은 말로 시작하면 좋습니다.
예를 들어 "오늘 코스피는 전체 과열도 25%로 상온 구간을 유지하고 있어요"처럼 지수나
구간(저온/상온/고온/초고온)을 되풀이하는 문장으로 시작하지 마세요 — 오프너에 이미
있습니다.

[분량·말투 — 반드시 2문장]
- 정확히 2문장만 씁니다. 마침표는 문장 끝 딱 2번. (1문장·3문장·4문장 모두 금지)
- 첫 문장 = 주인공 지표 뜻풀이, 둘째 문장 = 최근 추세. 각 개념을 '한 문장'에 담으세요.
  지표를 2개 언급하더라도 쉼표로 이어 한 문장으로 쓰고, 문장을 더 쪼개지 마세요.
- 화면에서 오프너 문단 뒤에 이 두 문장이 각각 한 문단씩 붙어 전체가 3문단이 됩니다.
- 친근한 존댓말로 끝맺습니다(예: "~이에요", "~네요", "~어 보여요").
- 과장 없이, 데이터가 말해주는 만큼만 씁니다.

[데이터 읽는 법 — 중요]
- 각 지표의 '과열도'(0=저온 ~ 100=초고온)가 그 지표가 얼마나 과열됐는지를 나타내는
  유일한 값입니다. 과열도가 높을수록 뜨겁고, 낮을수록 식은 것입니다.
- 'Hit'이 붙은 지표는 기준선을 넘어 초고온 구간에 든 것입니다.
- 과열도가 높은데 "식었다/하회한다"고 쓰거나, 낮은데 "뜨겁다"고 쓰지 마세요(방향을
  절대 뒤집지 말 것).

[반드시 담을 것 — 나열이 아니라 해석]
- 봇이 아니라 LLM이 쓰는 요약입니다. 지표를 단순 나열하는 데 그치지 말고, 오늘 데이터가
  무엇을 시사하는지 '한 겹의 해석'을 더하세요. 단, 모든 해석은 주어진 데이터로
  뒷받침돼야 합니다(아래 [절대 하지 말 것]).
- 첫 문장(주인공 지표 + 뜻풀이): 오늘 가장 뜨거운(또는 가장 눈에 띄는) 지표 1~2개를
  골라, 이름과 함께 **그 지표가 무엇을 재는지 / 왜 뜨거운(또는 식은) 게 의미 있는지**를
  쉬운 말로 풀어줍니다. 각 지표 밑의 '뜻:' 설명을 근거로 삼되, 그대로 베끼지 말고 한
  문장에 자연스럽게 녹여내세요. 뜻 설명에 없는 내용은 지어내지 마세요.
- 둘째 문장(최근 추세): 최근 며칠간 햇쩨 지수가 어떻게 움직였는지 흐름을 [최근 추세]
  수치에 근거해 짚어줍니다. (예: "지난주 50℃대에서 며칠째 내려와 오늘 25℃까지 식은
  흐름이에요.") 과거 궤적만 서술하고, 앞으로 오를지/내릴지 같은 예측은 하지 마세요.

[강조 형식 — 중요]
- 특히 중요한 부분(지표 이름, 핵심 과열도 %, 두드러진 사실)은 **별표 두 개로 감싸서**
  굵게 표시하세요. 예: **깃헙 트레이딩봇 저장소 생성 수**가 **과열도 100%**를 찍었어요.
- 단, 온도 단어(저온/상온/고온/초고온)는 별표로 감싸지 마세요 — 색은 화면에서 자동으로
  입혀집니다.
- 그 외 마크다운(# 제목, - 목록)이나 별표는 쓰지 말고, 굵게(**...**)만 씁니다. 한 문단.

[절대 하지 말 것]
- 매수/매도/매매/"사라"/"팔아라" 등 투자 권유나 신호로 읽힐 표현.
- 목표가, 상승/하락 예측이나 전망, "오를 것/내릴 것" 같은 방향 단정.
- 특정 종목 추천, 정치적 발언, 특정 인물 비방.
- 데이터에 없는 숫자를 지어내는 것(주어진 값만 사용).
- 데이터로 뒷받침되지 않는 일반화·단정. 특히 카테고리(시장 지표/감성 지표) 전체를
  뭉뚱그려 "감성 지표가 전반적으로 뜨겁다/식었다", "시장 지표와 감성 지표의 온도 차이가
  벌어졌다"처럼 비교하지 마세요. 같은 카테고리 안에서도 지표마다 과열도가 크게
  다릅니다(예: 감성 지표인 깃헙봇 100%, 뉴스 감성 0%). 카테고리 평균을 지어내 비교하지
  마세요.
- "저온/상온/고온/초고온은 참고용" 같은 면책 문구(화면에 따로 표시되므로 넣지 않음).

지표는 시장의 과열 정도를 나타낸 '재미·참고용' 온도계일 뿐입니다. 그 톤을 유지하세요.
설명 없이 이어지는 요약 문장만 출력하세요."""


# 첫 문장(주인공 뜻풀이)에 근거를 주기 위해, 상위 몇 개 지표엔 설명문(뜻)을 함께 붙인다.
DESC_TOP_N = 5


def build_digest(
    score: float,
    stage: str,
    hit_count: int,
    rows: list[dict],
    recent_scores: list[float],
) -> str:
    """LLM에 넘길 지표 요약(사람이 읽는 한글 텍스트). 과열도 높은 순으로 정렬해
    모델이 '눈여겨볼 지표'를 고르기 쉽게 한다.

    과열도(capped progress)에는 이미 지표별 방향(high/low)이 반영돼 있어, 이 값 하나가
    '얼마나 뜨거운지'의 단일 척도다. raw 현재값/기준값을 같이 주면 모델이 '현재<기준=식음'
    처럼 방향을 거꾸로 읽는 일이 생겨(예: 상대강도 지표) 일부러 뺀다.

    헤드라인 '햇쩨 지수'는 온도(℃)로, 개별 지표는 기준선까지의 진행률(과열도 %)로
    표기해 화면 표기와 맞춘다.

    - [최근 추세]: 3번째 문단(추세)용. 최근 며칠 햇쩨 지수를 오래된→오늘 순으로 준다.
    - [지표별]의 '뜻:' : 1번째 문단(주인공 뜻풀이)용. 상위 DESC_TOP_N개에만 설명문을 붙여,
      모델이 지표 의미를 지어내지 않고 근거 있게 풀도록 한다."""
    lines = [
        f"[전체] 햇쩨 지수 {score:.0f}℃ · {stage} 구간 · 기준선 초과(Hit) 지표 {hit_count}개",
    ]
    if recent_scores:
        trend = " → ".join(f"{s:.0f}" for s in recent_scores)
        lines.append(f"[최근 추세] 최근 {len(recent_scores)}일 햇쩨 지수(℃, 오래된→오늘): {trend}")
    lines += [
        "",
        "[지표별] 과열도 높은 순 (0=저온 ~ 100=초고온, 'Hit'=기준선 초과)",
    ]
    for i, r in enumerate(rows):
        hit_mark = " · Hit" if r["hit"] else ""
        lines.append(f"- {r['name']} ({r['category']}): 과열도 {r['capped']:.0f}%{hit_mark}")
        if i < DESC_TOP_N and r.get("desc"):
            lines.append(f"    뜻: {r['desc']}")
    return "\n".join(lines)


def main() -> None:
    if not ANTHROPIC_API_KEY:
        # 키가 없으면 조용히 건너뛴다(설정 전 로컬/CI에서도 파이프라인이 안 깨지게).
        print("[skip] ANTHROPIC_API_KEY가 없어 요약 생성을 건너뜁니다.")
        return

    client = get_client()

    # 프론트가 보여주는 '최신' daily_score 행에 요약을 붙인다(오늘 계산이 안 돌았어도
    # 최신 날짜 기준으로 맞춘다). 최근 8일을 받아 3번째 문단(추세)용 궤적을 만든다.
    ds = (
        client.table("daily_score")
        .select("date, score, stage")
        .order("date", desc=True)
        .limit(8)
        .execute()
    )
    if not ds.data:
        print("[skip] daily_score 행이 없어 요약할 대상이 없습니다.")
        return
    target_date = ds.data[0]["date"]
    score = float(ds.data[0]["score"])
    # 최신순으로 받았으니 뒤집어 오래된→오늘 순으로. 추세 서술용.
    recent_scores = [float(r["score"]) for r in reversed(ds.data)]
    stage = stage_for_score(score)  # 저장된 라벨 대신 점수에서 재계산(프론트와 동일 규칙)

    # 공개 지표 + 각 지표의 최신 값. normalized_score는 calculate_score가 저장한 원본
    # 진행률(캡핑 전)이라, 여기서 캡핑/Hit을 다시 계산한다. description_beginner는
    # 1번째 문단(주인공 뜻풀이)의 근거로 상위 지표에 붙인다.
    indicators = (
        client.table("indicators")
        .select("id, name, category, description_beginner")
        .eq("is_public", True)
        .order("created_at", desc=False)
        .execute()
    )

    rows: list[dict] = []
    for ind in indicators.data:
        iv = (
            client.table("indicator_values")
            .select("normalized_score")
            .eq("indicator_id", ind["id"])
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if not iv.data:
            continue
        progress = iv.data[0].get("normalized_score")
        if progress is None:
            continue  # 아직 진행률이 안 채워진 지표는 제외
        capped = cap_progress(float(progress))
        rows.append(
            {
                "name": ind["name"],
                "category": ind["category"],
                "desc": ind.get("description_beginner"),
                "capped": capped,
                "hit": capped >= HIT_ZONE,
            }
        )

    if not rows:
        print("[skip] 요약할 지표 값이 없습니다.")
        return

    rows.sort(key=lambda r: r["capped"], reverse=True)
    hit_count = sum(1 for r in rows if r["hit"])
    digest = build_digest(score, stage, hit_count, rows, recent_scores)

    print("─" * 60)
    print(digest)
    print("─" * 60)

    anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = anthropic.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM,
        messages=[{"role": "user", "content": digest}],
    )
    # 별표(**...**)는 굵게 표시용이라 유지한다 — 프론트가 파싱해 <b>로 렌더하고,
    # 짝이 안 맞는 별표는 그냥 글자로 보여준다(드묾).
    summary = "".join(b.text for b in resp.content if b.type == "text").strip()

    if not summary:
        print("[WARNING] LLM이 빈 응답을 반환해 요약을 저장하지 않습니다.")
        return

    print(f"[요약] {summary}")

    client.table("daily_score").update({"ai_summary": summary}).eq(
        "date", target_date
    ).execute()
    print(f"[Supabase] daily_score.ai_summary 저장 완료: date={target_date}")


if __name__ == "__main__":
    main()
