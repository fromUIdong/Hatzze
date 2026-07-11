"""yfinance의 구리 선물(HG=F) 종가로 "닥터 코퍼"(구리 가격 모멘텀)를 계산해
Supabase에 upsert.

구리는 건설·제조업 전반에 쓰여 경기를 선행 반영하는 원자재로 유명하다
("Dr. Copper" 별명 — 경기를 의사처럼 미리 진단한다는 뜻). 최근 20거래일
수익률(%) = (오늘 종가 / 20거래일 전 종가 - 1) × 100 —
fetch_asia_relative_strength.py의 compute_20d_return과 동일한 계산 방식이다.

최초 실행 시 1년치 중 20거래일 이후부터 계산 가능한 구간을 전부 백필하고,
이후 실행부터는 아직 없는 날짜만 채운다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402

COPPER_TICKER = "HG=F"
RETURN_WINDOW = 20  # 최근 20거래일 수익률
BACKFILL_DAYS = 365

INDICATOR_SLUG = "copper_price_momentum"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": '구리 가격 모멘텀 ("닥터 코퍼")',
    "category": "정통",
    "headline": "구리가 먼저 알아채는 경기",
    "description_beginner": "구리는 건설, 제조업 전반에 쓰여서 경기를 먼저 반영하는 원자재로 유명해요. 가격이 빠르게 오르고 있다면 경기 확장 기대가 커지고 있다는 신호일 수 있어요",
    "unit": "%",
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


def fetch_prices(start: date, end: date) -> dict[str, float]:
    history = yf.Ticker(COPPER_TICKER).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat()
    )
    return {ts.date().isoformat(): float(close) for ts, close in history["Close"].items()}


def compute_20d_return(prices: dict[str, float]) -> dict[str, float]:
    """날짜순 정렬 기준 자기 자신의 20번째 이전 거래일 대비 수익률(%)을 계산한다."""
    dates = sorted(prices.keys())
    result = {}
    for i in range(RETURN_WINDOW, len(dates)):
        d, d_prev = dates[i], dates[i - RETURN_WINDOW]
        result[d] = (prices[d] / prices[d_prev] - 1) * 100
    return result


def get_existing_dates(client, indicator_id: str, start: date) -> set[str]:
    result = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"] for row in result.data}


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    prices = fetch_prices(start, today)
    print(f"[yfinance] {COPPER_TICKER} 종가 {len(prices)}건 조회")

    returns = compute_20d_return(prices)
    print(f"[{INDICATOR_SLUG}] 20일 수익률 {len(returns)}건 계산")

    if not returns:
        print(f"[{INDICATOR_SLUG}] 계산된 값이 없습니다")
        return

    existing_dates = get_existing_dates(client, indicator_id, start)
    missing_dates = sorted(set(returns) - existing_dates)

    if not missing_dates:
        print(f"[{INDICATOR_SLUG}] 백필할 신규 날짜 없음 (이미 최신 상태)")
    else:
        rows = [
            {"indicator_id": indicator_id, "date": d, "raw_value": round(returns[d], 2)}
            for d in missing_dates
        ]
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
        print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_date = max(returns)
    print(f"[{INDICATOR_SLUG}] 최신값 ({latest_date} 기준): {returns[latest_date]:.2f}%")


if __name__ == "__main__":
    main()
