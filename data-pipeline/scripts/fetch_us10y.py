"""FRED DGS10(미국 10년물 국채금리) 최신값을 가져와 Supabase indicator_values에 upsert."""

import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import FRED_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

FRED_SERIES_ID = "DGS10"
INDICATOR_SLUG = "us10y"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "미국 10년물 국채금리",
    "category": "정통",
    "description_beginner": "금리가 오르면 안전한 예금·채권이 매력적이라 주식에서 돈이 빠져나갈 수 있어요",
    "unit": "%",
}


def fetch_latest_dgs10() -> tuple[str, float]:
    resp = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": FRED_SERIES_ID,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,
        },
        timeout=10,
    )
    resp.raise_for_status()
    observations = resp.json()["observations"]
    for obs in observations:
        if obs["value"] != ".":
            return obs["date"], float(obs["value"])
    raise RuntimeError(f"최근 {FRED_SERIES_ID} 관측치 중 유효한 값이 없습니다")


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
    fred_date, yield_value = fetch_latest_dgs10()
    print(f"[FRED] {FRED_SERIES_ID} 최신 관측치 ({fred_date} 기준): {yield_value}%")

    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today().isoformat()
    upsert_value(client, indicator_id, today, yield_value)
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={yield_value}")


if __name__ == "__main__":
    main()
