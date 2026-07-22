"""한국은행 ECOS 소비자심리지수(CCSI)를 가져와 indicator_values 에 저장.

CCSI 는 한국은행이 매달 약 2,500가구를 조사해 내는 '소비자심리지수'로, 100 이 장기
평균이다(2003~2023 평균=100). 100 위면 소비심리가 평균보다 낙관, 아래면 위축이다.

**쓰임 — 실물–증시 괴리 지수의 '실물 stress' 축.** 기존엔 '자영업 폐업 검색량'으로
실물 스트레스를 쟀는데, 검색은 노이즈가 크다. CCSI 는 정제된 심리 조사라 실물 축으로
더 낫다. calculate_score.py 가 이 raw_value 를 threshold(floor=100·ceiling=70)로 선형
매핑해 'stress progress'(심리가 나쁠수록 높음)로 뒤집어 괴리 계산에 쓴다. 즉 이 지표
자체의 방향(낮을수록 stress↑)은 config 의 floor/threshold 로 표현하고, 여기선 CCSI
원값을 그대로 저장만 한다.

**주기.** CCSI 는 월간이다(매월 말 발표, ECOS 반영은 그 직후). 그래서 값은 한 달에 한
번만 바뀐다 — 파이프라인은 매일 돌지만 같은 달엔 같은 값을 덮어쓸 뿐이라 멱등이다.
실물 경제 자체가 천천히 변하니 '느린 실물 축'으로는 오히려 맞다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/fetch_consumer_sentiment.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.ecos_client import statistic_search  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

# 소비자동향조사, 월간. 항목 FME = '소비자심리지수'(종합 CCSI). 2026-07 실측 확인.
ECOS_STAT_CODE = "511Y002"
ECOS_ITEM_CODE = "FME"
ECOS_CYCLE = "M"
LOOKBACK_MONTHS = 18  # details(추이·게이지)용으로 넉넉히 받는다

INDICATOR_SLUG = "consumer_sentiment_index"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "소비자심리지수 (CCSI)",
    "category": "시장",
    "headline": "실물 소비심리 (100=평균)",
    "description_beginner": "한국은행이 매달 재는 소비심리예요. 100 아래로 내려갈수록 사람들이 지갑을 닫는다는 실물경제 위축 신호예요.",
    "unit": "",
}


def month_str(d: date) -> str:
    return f"{d.year}{d.month:02d}"


def fetch_ccsi() -> list[tuple[str, float]]:
    """(YYYY-MM-01, CCSI) 리스트. TIME(YYYYMM)을 그 달 1일 날짜로 저장한다."""
    today = date.today()
    start_year = today.year - (2 if today.month <= LOOKBACK_MONTHS % 12 else 1) - 1
    rows = statistic_search(
        ECOS_STAT_CODE,
        ECOS_CYCLE,
        f"{start_year}01",
        month_str(today),
        ECOS_ITEM_CODE,
        count=500,
    )
    out: list[tuple[str, float]] = []
    for r in rows:
        t = r["TIME"]  # "YYYYMM"
        out.append((f"{t[:4]}-{t[4:6]}-01", float(r["DATA_VALUE"])))
    return out


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    series = fetch_ccsi()
    if not series:
        print("[ECOS] CCSI 데이터를 받지 못했습니다.")
        sys.exit(1)

    rows = [{"indicator_id": indicator_id, "date": d, "raw_value": v} for d, v in series]
    client.table("indicator_values").upsert(rows, on_conflict="indicator_id,date").execute()

    latest_date, latest_val = series[-1]
    tone = "평균 이상(낙관)" if latest_val >= 100 else "평균 이하(위축)"
    print(f"[ECOS] CCSI {len(rows)}개월치 저장. 최신: {latest_date[:7]} = {latest_val} ({tone})")


if __name__ == "__main__":
    main()
