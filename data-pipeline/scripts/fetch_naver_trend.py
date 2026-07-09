"""네이버 데이터랩 검색어트렌드 API로 '주식 초보' 검색량 지수를 가져와 Supabase indicator_values에 upsert."""

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
LOOKBACK_DAYS = 90

INDICATOR_SLUG = "naver_search_trend"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "주식 초보 검색량 지수",
    "category": "밈",
    "description_beginner": "다들 이제서야 주식을 시작하려고 검색하고 있다면, 이미 많이 오른 뒤일 수 있어요",
    "unit": "지수",
}


def fetch_latest_search_trend() -> tuple[str, float]:
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
        timeout=10,
    )
    resp.raise_for_status()
    data_points = resp.json()["results"][0]["data"]
    if not data_points:
        raise RuntimeError("네이버 데이터랩 응답에 데이터가 없습니다")

    latest = data_points[-1]
    return latest["period"], float(latest["ratio"])


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def upsert_value(client, indicator_id: str, value_date: str, raw_value: float) -> None:
    client.table("indicator_values").upsert(
        {
            "indicator_id": indicator_id,
            "date": value_date,
            "raw_value": raw_value,
        },
        on_conflict="indicator_id,date",
    ).execute()


def main() -> None:
    trend_date, ratio = fetch_latest_search_trend()
    print(f"[Naver DataLab] '{KEYWORD_GROUP_NAME}' 최신 검색량 지수 ({trend_date} 기준): {ratio}")

    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today().isoformat()
    upsert_value(client, indicator_id, today, ratio)
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={ratio}")


if __name__ == "__main__":
    main()
