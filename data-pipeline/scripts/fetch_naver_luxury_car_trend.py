"""네이버 데이터랩 검색어트렌드 API로 명품·수입차 브랜드 20개를 한 그룹으로
묶어 '명품·수입차 소비 검색 지수'를 가져와 Supabase indicator_values에 upsert.

데이터랩은 한 keywordGroup 안의 여러 키워드 검색량을 합산해 0~100 상대지수
하나로 반환한다(그룹당 최대 20개) — 그래서 명품 브랜드 9개 + 수입차 브랜드
9개 + 실물 소비 키워드 2개, 정확히 20개를 한 그룹으로 묶으면 "명품·수입차
소비 관심도"를 종합한 단일 지수가 나온다. 브랜드명 검색은 순수 소비 목적 외에
관련 주식 종목에 대한 관심으로도 잡힐 수 있지만, "이 브랜드에 대한 대중적
관심도 전반"을 재는 지표로 넓게 해석해 별도 필터링은 하지 않는다.

fetch_naver_trend.py와 동일하게 조회 기간(1년) 내 모든 날짜별 값을 매 실행마다
upsert한다. 같은 날짜를 다시 upsert해도 값을 덮어쓸 뿐이라 멱등적이며, 별도의
최초/이후 실행 분기가 필요 없다.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
KEYWORD_GROUP_NAME = "명품수입차소비"
KEYWORDS = [
    # 명품 브랜드 (9개)
    "샤넬", "루이비통", "롤렉스", "에르메스", "구찌", "프라다", "디올", "카르티에", "발렌시아가",
    # 수입차 브랜드 (9개)
    "벤츠", "BMW", "아우디", "포르쉐", "테슬라", "렉서스", "람보르기니", "페라리", "벤틀리",
    # 실물 소비 키워드 (2개)
    "중고차 시세", "수입차 구매",
]
assert len(KEYWORDS) == 20, f"데이터랩 keywordGroup 한도는 20개인데 {len(KEYWORDS)}개입니다"
LOOKBACK_DAYS = 365

INDICATOR_SLUG = "luxury_consumption_index"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "명품·수입차 소비 검색 지수",
    "category": "감성",
    "description_beginner": "샤넬·벤츠 같은 명품·수입차 브랜드 검색이 늘어나면, 사람들이 여윳돈으로 과시성 소비에 지갑을 열고 있다는 신호예요. 씀씀이가 커질수록 시장도 들떠 있을 수 있어요",
    "unit": "pt",
}


def fetch_search_trend() -> list[dict]:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    resp = requests.post(
        NAVER_DATALAB_URL,
        headers={
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            "Content-Type": "application/json",
        },
        data=json.dumps(
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "timeUnit": "date",
                "keywordGroups": [
                    {"groupName": KEYWORD_GROUP_NAME, "keywords": KEYWORDS}
                ],
            }
        ),
        timeout=15,
    )
    resp.raise_for_status()
    data_points = resp.json()["results"][0]["data"]
    if not data_points:
        raise RuntimeError("네이버 데이터랩 응답에 데이터가 없습니다")
    return data_points


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        indicator_id = existing.data[0]["id"]
        client.table("indicators").update(
            {k: v for k, v in INDICATOR_META.items() if k != "slug"}
        ).eq("id", indicator_id).execute()
        return indicator_id

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


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
        f"[Naver DataLab] '{KEYWORD_GROUP_NAME}'({len(KEYWORDS)}개 키워드) {len(data_points)}일치 조회 완료 "
        f"(최신 {latest['period']} 기준: {latest['ratio']})"
    )

    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    upsert_all(client, indicator_id, data_points)
    print(f"[Supabase] indicator_values upsert 완료: {len(data_points)}건")


if __name__ == "__main__":
    main()
