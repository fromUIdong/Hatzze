"""네이버 데이터랩 검색어트렌드 API로 '주식 초보' 검색량 지수를 가져와 Supabase indicator_values에 upsert.

조회 기간(1년) 내 모든 날짜별 값을 매 실행마다 upsert한다. 같은 날짜를 다시
upsert해도 값을 덮어쓸 뿐이라 멱등적이며, 별도의 최초/이후 실행 분기가 필요 없다.
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
KEYWORD_GROUP_NAME = "주식초보"
KEYWORDS = ["주식 시작하는 법", "증권계좌 개설", "주식 초보"]
LOOKBACK_DAYS = 365

INDICATOR_SLUG = "naver_search_trend"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "주식 초보 검색량 지수",
    "category": "감성",
    "description_beginner": "'주식 초보' 같은 검색이 늘어 다들 이제서야 뛰어든다면, 이미 많이 오른 뒤늦은 국면일 수 있어요",
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
        # unit 등 메타데이터가 바뀔 수 있으므로 최신 내용으로 갱신한다.
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
        f"[Naver DataLab] '{KEYWORD_GROUP_NAME}' {len(data_points)}일치 조회 완료 "
        f"(최신 {latest['period']} 기준: {latest['ratio']})"
    )

    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    upsert_all(client, indicator_id, data_points)
    print(f"[Supabase] indicator_values upsert 완료: {len(data_points)}건")


if __name__ == "__main__":
    main()
