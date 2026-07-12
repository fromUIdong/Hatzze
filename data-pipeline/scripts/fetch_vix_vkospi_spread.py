"""yfinance의 VIX(^VIX) 종가와 이미 저장된 vkospi 값을 날짜로 매칭해
"VIX 대비 VKOSPI 스프레드"(VKOSPI - VIX)를 계산해 Supabase에 upsert.

VKOSPI는 fetch_vkospi.py가 이미 매일 수집해 indicator_values에 쌓고 있으므로
여기서 다시 받지 않고 Supabase에서 읽기만 한다 — VIX만 새로 yfinance에서 받아
같은 날짜끼리 뺄셈한다(fetch_yield_spread.py와 동일한 패턴).

스프레드가 음수로 크면 "미국보다 한국 변동성이 낮다"는 뜻인데, 이게 꼭 안전하다는
뜻은 아니다 — 오히려 한국 시장이 미국 대비 유독 방심하고 있다는 신호로 본다.
그래서 이 지표는 direction="low"(스프레드가 낮을수록/더 마이너스일수록 과열)로
잡는다.

VIX와 VKOSPI는 각각 미국/한국 거래일 기준이라 하루 정도 어긋날 수 있는데,
kospi_gold_ratio와 동일하게 지금 단계에서는 이 오차를 감수하고 단순 날짜
문자열 매칭으로 시작한다.

최초 실행 시(해당 indicator에 저장된 값이 하나도 없을 때) VIX·VKOSPI 공통 날짜
전체를 백필하고, 이후 실행부터는 아직 없는 날짜만 채운다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402

VIX_TICKER = "^VIX"
BACKFILL_DAYS = 365

VKOSPI_SLUG = "vkospi"

INDICATOR_SLUG = "vix_vkospi_spread"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "VIX 대비 VKOSPI 스프레드",
    "category": "정통",
    "headline": "태평양 건너 공포와 비교하면",
    "description_beginner": "미국 시장(VIX)보다 한국 시장(VKOSPI)이 유독 방심하고 있는지 비교해요. 스프레드가 마이너스로 클수록 한국만 유독 안일한 상태일 수 있어요",
    "unit": "pt",
    "direction": "low",
    "weight": 2,
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
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    return result.data[0]["id"]


def fetch_vix_prices(start: date, end: date) -> dict[str, float]:
    history = yf.Ticker(VIX_TICKER).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat()
    )
    return {ts.date().isoformat(): float(close) for ts, close in history["Close"].items()}


def get_indicator_values(client, indicator_id: str, start: date) -> dict[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"]: float(row["raw_value"]) for row in result.data}


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    vkospi_id = get_indicator_id(client, VKOSPI_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    vix_prices = fetch_vix_prices(start, today)
    print(f"[yfinance] {VIX_TICKER} 종가 {len(vix_prices)}건 조회")

    vkospi_values = get_indicator_values(client, vkospi_id, start)
    print(f"[Supabase] {VKOSPI_SLUG} {len(vkospi_values)}건 조회")

    existing_spread_dates = set(get_indicator_values(client, indicator_id, start).keys())

    common_dates = sorted(set(vix_prices) & set(vkospi_values))
    missing_dates = [d for d in common_dates if d not in existing_spread_dates]

    if not common_dates:
        print("[vix_vkospi_spread] VIX/VKOSPI 시계열의 공통 날짜가 없습니다")
        return

    if not missing_dates:
        print("[vix_vkospi_spread] 백필할 신규 날짜 없음 (이미 최신 상태)")
    else:
        rows = [
            {
                "indicator_id": indicator_id,
                "date": d,
                "raw_value": round(vkospi_values[d] - vix_prices[d], 2),
            }
            for d in missing_dates
        ]
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
        print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_date = common_dates[-1]
    latest_spread = vkospi_values[latest_date] - vix_prices[latest_date]
    print(
        f"[vix_vkospi_spread] 최신값 ({latest_date} 기준): "
        f"VKOSPI {vkospi_values[latest_date]:.2f} - VIX {vix_prices[latest_date]:.2f} "
        f"= {latest_spread:.2f}pt"
    )


if __name__ == "__main__":
    main()
