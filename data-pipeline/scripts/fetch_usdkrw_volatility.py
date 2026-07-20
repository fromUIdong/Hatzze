"""yfinance의 USD/KRW(KRW=X) 종가로 원/달러 환율 변동성을 계산해 Supabase에 upsert.

변동성 = 최근 VOLATILITY_WINDOW(20)일 일별 변동률(%)의 표준편차. VKOSPI와
마찬가지로 "낮을수록 과열(방심)" 방향이다 — calculate_score.py에서
direction: "low"로 다뤄야 한다.

최초 실행 시 1년치를 백필하고, 이후 실행부터는 아직 없는 날짜만 채운다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

FX_TICKER = "KRW=X"
BACKFILL_DAYS = 365
VOLATILITY_WINDOW = 20  # 최근 20일 일별 변동률의 표준편차

INDICATOR_SLUG = "usdkrw_volatility"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "원/달러 환율 변동성",
    "category": "시장",
    "description_beginner": "환율 출렁임이 너무 잔잔하면, 위험을 잊고 방심했다는 신호예요",
    "unit": "%",
}


def fetch_volatility_series(start: date, end: date) -> dict[str, float]:
    # 20일 이동 표준편차를 구하려면 start보다 더 이전 데이터가 필요하다.
    fetch_start = start - timedelta(days=VOLATILITY_WINDOW * 3)  # 주말/휴일 감안 여유치
    history = yf.Ticker(FX_TICKER).history(
        start=fetch_start.isoformat(), end=(end + timedelta(days=1)).isoformat()
    )
    pct_change = history["Close"].pct_change() * 100
    rolling_std = pct_change.rolling(window=VOLATILITY_WINDOW).std()

    result = {}
    for ts, value in rolling_std.items():
        if pd.isna(value):
            continue
        d = ts.date()
        if start <= d <= end:
            result[d.isoformat()] = float(value)
    return result


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    volatility_series = fetch_volatility_series(start, today)
    print(f"[yfinance] {FX_TICKER} 변동성 {len(volatility_series)}건 계산")

    if not volatility_series:
        print("[usdkrw_volatility] 계산된 값이 없습니다")
        return

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    existing_dates = {row["date"] for row in existing.data}

    missing = {d: v for d, v in volatility_series.items() if d not in existing_dates}
    if not missing:
        print("[usdkrw_volatility] 백필할 신규 날짜 없음 (이미 최신 상태)")
    else:
        rows = [
            {"indicator_id": indicator_id, "date": d, "raw_value": v}
            for d, v in missing.items()
        ]
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
        print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_date = max(volatility_series)
    print(
        f"[usdkrw_volatility] 최신값 ({latest_date} 기준): "
        f"{volatility_series[latest_date]:.4f}%"
    )


if __name__ == "__main__":
    main()
