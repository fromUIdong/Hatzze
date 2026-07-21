"""네이버 데이터랩 검색어트렌드 API로 '주식 초보' 검색량 지수를 가져와 Supabase indicator_values에 upsert.

조회 기간(1년) 내 모든 날짜별 값을 매 실행마다 upsert한다. 같은 날짜를 다시
upsert해도 값을 덮어쓸 뿐이라 멱등적이며, 별도의 최초/이후 실행 분기가 필요 없다.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.naver_client import datalab_search  # noqa: E402
from common.details import store_vs_average_details  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

KEYWORD_GROUP_NAME = "주식초보"
# 주식을 '처음 시작하는 사람'의 검색 의도만 모은다 — 종목명·시황 검색어를 섞으면
# 기존 투자자의 관심까지 잡혀 '초보 유입'이라는 지표의 뜻이 흐려진다.
# 데이터랩은 그룹의 검색량을 합산해 0~100으로 정규화하므로, 키워드를 늘리면 저변이
# 넓어져 신호가 안정된다. 매 실행 365일치를 다시 받아 upsert 하니 과거 시계열도
# 같은 구성으로 재계산돼 단절이 생기지 않는다(그룹당 20개까지 허용).
KEYWORDS = [
    "주식 시작하는 법",
    "증권계좌 개설",
    "주식 초보",
    "주린이",  # 초보 투자자를 가리키는 관용어 — 입문 검색의 대표어
    "주식 공부",
    "주식 입문",
    "주식 하는법",
    "주식 계좌 개설",
    "증권사 추천",
    "미국주식 시작",
]
LOOKBACK_DAYS = 365

INDICATOR_SLUG = "naver_search_trend"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "주식 초보 검색량 지수",
    "headline": "주식 입문 검색어의 검색량",
    "category": "감성",
    "description_beginner": "주식 입문자를 위한 검색량이 늘어나면 뒤늦은 국면일 수 있어요",
    "unit": "pt",
}


def fetch_search_trend() -> list[dict]:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    resp = datalab_search(
        {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "timeUnit": "date",
            "keywordGroups": [{"groupName": KEYWORD_GROUP_NAME, "keywords": KEYWORDS}],
        }
    )
    resp.raise_for_status()
    data_points = resp.json()["results"][0]["data"]
    if not data_points:
        raise RuntimeError("네이버 데이터랩 응답에 데이터가 없습니다")
    return data_points


def upsert_all(client, indicator_id: str, data_points: list[dict]) -> None:
    rows = [
        {
            "indicator_id": indicator_id,
            "date": point["period"],
            "raw_value": float(point["ratio"]),
        }
        for point in data_points
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()


def main() -> None:
    data_points = fetch_search_trend()
    latest = data_points[-1]
    print(
        f"[Naver DataLab] '{KEYWORD_GROUP_NAME}' {len(data_points)}일치 조회 완료 "
        f"(최신 {latest['period']} 기준: {latest['ratio']})"
    )

    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    upsert_all(client, indicator_id, data_points)
    print(f"[Supabase] indicator_values upsert 완료: {len(data_points)}건")

    # 카드가 'pt' 대신 '평소 대비 N배'를 보여줄 수 있게 30일 평균 대비 배수를
    # details에 채운다.
    updated = store_vs_average_details(client, indicator_id)
    print(f"[Supabase] 평소 대비 배수 details 저장 완료: {updated}건")


if __name__ == "__main__":
    main()
