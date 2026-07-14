"""FRED DGS10(미국 10년물 국채금리)을 가져와 Supabase indicator_values에 upsert.

최초 실행 시(해당 indicator에 저장된 값이 하나도 없을 때) 최근 1년치를 한 번에
백필하고, 이후 실행부터는 최신 관측치 하나만 오늘 날짜로 추가한다.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import FRED_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_ID = "DGS10"
BACKFILL_DAYS = 365

INDICATOR_SLUG = "us10y"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "미국 10년물 국채금리",
    "category": "시장",
    "description_beginner": "금리가 오르면 안전한 채권으로 돈이 옮겨가, 주식에서 빠질 수 있어요",
    "unit": "%",
}


def fetch_latest_dgs10() -> tuple[str, float]:
    resp = requests.get(
        FRED_OBSERVATIONS_URL,
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


def fetch_observation_range(start: date, end: date) -> list[dict]:
    resp = requests.get(
        FRED_OBSERVATIONS_URL,
        params={
            "series_id": FRED_SERIES_ID,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "sort_order": "asc",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["observations"]


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def has_existing_history(client, indicator_id: str) -> bool:
    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .limit(1)
        .execute()
    )
    return bool(existing.data)


def upsert_value(client, indicator_id: str, value_date: str, raw_value: float) -> None:
    client.table("indicator_values").upsert(
        {
            "indicator_id": indicator_id,
            "date": value_date,
            "raw_value": raw_value,
        },
        on_conflict="indicator_id,date",
    ).execute()


def backfill(client, indicator_id: str) -> None:
    end = date.today()
    start = end - timedelta(days=BACKFILL_DAYS)
    observations = fetch_observation_range(start, end)

    rows = [
        {"indicator_id": indicator_id, "date": obs["date"], "raw_value": float(obs["value"])}
        for obs in observations
        if obs["value"] != "."
    ]
    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    skipped = len(observations) - len(rows)
    print(f"[FRED] 백필 완료: {len(rows)}건 저장 (휴장일 등 {skipped}건 제외)")


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    if not has_existing_history(client, indicator_id):
        print("[FRED] 기존 데이터 없음 -> 최근 1년치 백필 시작")
        backfill(client, indicator_id)
        return

    fred_date, yield_value = fetch_latest_dgs10()
    print(f"[FRED] {FRED_SERIES_ID} 최신 관측치 ({fred_date} 기준): {yield_value}%")

    today = date.today().isoformat()
    upsert_value(client, indicator_id, today, yield_value)
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={yield_value}")


if __name__ == "__main__":
    main()
