"""FRED DGS2(미국 2년물 국채금리)를 가져와 이미 저장된 us10y(10년물) 값과
날짜 매칭해 장단기 금리차(10년물-2년물)를 계산, Supabase에 upsert.

10년물은 fetch_us10y.py가 이미 매일 수집해 indicator_values에 쌓고 있으므로
여기서 다시 받지 않고 Supabase에서 읽기만 한다 — DGS2만 새로 FRED에서 받아
같은 날짜끼리 뺄셈한다. 최초 실행 시(해당 indicator에 저장된 값이 하나도
없을 때) 최근 1년치를 한 번에 백필하고, 이후 실행부터는 최신 관측치 하나만
오늘 날짜로 추가한다(fetch_us10y.py와 동일한 diff 패턴).

스프레드가 역전(음수)되면 경기침체 신호로 유명하지만, 이 지표는 "과열도"
관점이라 반대 방향을 본다 — 역전에서 벗어나 스프레드가 뚜렷하게 벌어지는
국면은 시장이 경기 확장/위험선호를 기대하고 있다는 뜻이라 direction="high"
(스프레드가 넓을수록 과열)로 잡았다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import FRED_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_ID = "DGS2"
BACKFILL_DAYS = 365

US10Y_SLUG = "us10y"

INDICATOR_SLUG = "yield_curve_spread"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "미국 장단기 금리차 (10년물-2년물)",
    "category": "시장",
    "headline": "채권시장이 보내는 경고",
    "description_beginner": "미국 장기 금리가 단기 금리보다 낮아지는 '역전'은 경기 침체의 대표 신호로 유명해요. 반대로 스프레드가 넓게 벌어지면 경기 확장 기대가 살아나고 있다는 뜻일 수 있어요",
    "unit": "%p",
    "weight": 3,
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def get_indicator_id(client, slug: str) -> str:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    if not result.data:
        raise RuntimeError(f"indicator '{slug}'가 아직 없습니다 — 먼저 실행되어야 합니다")
    return result.data[0]["id"]


def get_values(client, indicator_id: str, start: date) -> dict[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"]: float(row["raw_value"]) for row in result.data}


def has_existing_history(client, indicator_id: str) -> bool:
    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .limit(1)
        .execute()
    )
    return bool(existing.data)


def fetch_dgs2_range(start: date, end: date) -> dict[str, float]:
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
    return {
        obs["date"]: float(obs["value"])
        for obs in resp.json()["observations"]
        if obs["value"] != "."
    }


def upsert_spreads(client, indicator_id: str, dgs2_values: dict[str, float], us10y_values: dict[str, float]) -> list[tuple[str, float]]:
    common_dates = sorted(set(dgs2_values) & set(us10y_values))
    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(us10y_values[d] - dgs2_values[d], 2),
        }
        for d in common_dates
    ]
    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    return [(r["date"], r["raw_value"]) for r in rows]


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    us10y_id = get_indicator_id(client, US10Y_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    backfilling = not has_existing_history(client, indicator_id)
    start = today - timedelta(days=BACKFILL_DAYS if backfilling else 10)

    dgs2_values = fetch_dgs2_range(start, today)
    us10y_values = get_values(client, us10y_id, start)
    print(f"[FRED] DGS2 {len(dgs2_values)}건, [Supabase] us10y {len(us10y_values)}건 (날짜 매칭 대상)")

    rows = upsert_spreads(client, indicator_id, dgs2_values, us10y_values)
    if not rows:
        print("[WARNING] DGS2·us10y 공통 날짜가 없어 저장할 스프레드가 없습니다")
        return

    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")
    latest_date, latest_spread = rows[-1]
    print(
        f"[yield_curve_spread] 최신값 ({latest_date} 기준): "
        f"10년물 {us10y_values[latest_date]}% - 2년물 {dgs2_values[latest_date]}% "
        f"= {latest_spread}%p"
    )


if __name__ == "__main__":
    main()
