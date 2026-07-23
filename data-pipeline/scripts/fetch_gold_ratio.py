"""yfinance의 국제 금 선물(GC=F) 종가와 저장된 kospi_close_raw를 날짜로 매칭해
"금 대비 코스피 상대강도" 비율(코스피 종가 / 금 종가)을 계산해 Supabase에 upsert.

금은 GC=F(COMEX 금 선물)를 사용한다 — XAU=X(현물 표기)는 이 환경에서 404로
데이터가 전혀 나오지 않아 제외했다. 코스피는 원화, 금은 달러 기준이라 엄밀히는
환율 보정이 필요하지만, 지금 단계에서는 단순 비율로 시작한다(정밀한 환헤지
계산은 추후 과제).

날짜 매칭은 두 시계열의 날짜 문자열을 그대로 비교한다. GC=F는 미국 시장 기준
거래일(전날 저녁~당일 새벽, 한국시간 기준)이라 코스피 거래일과 하루 정도
어긋날 수 있지만, 지금 단계에서는 이 오차를 감수하고 단순 비교로 시작한다.

최초 실행 시 두 시계열의 공통 날짜에 대해 1년치를 백필하고, 이후 실행부터는
아직 없는 날짜만 채운다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

GOLD_TICKER = "GC=F"
BACKFILL_DAYS = 365

KOSPI_RAW_SLUG = "kospi_close_raw"

INDICATOR_SLUG = "kospi_gold_ratio"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "금 대비 코스피 상대강도",
    "headline": "안전자산 금과 견준 코스피 강도",
    "category": "시장",
    # 1칸 카드로 줄면서(2026-07-23 코스닥 칸 제거) 설명이 혼자 한 줄 더 길어졌다 —
    # 같은 행 카드들이 35~51자인데 이것만 54자였다. 뜻은 그대로 두고 길이만 맞춘다.
    "description_beginner": "이 비율이 높아질수록 안전자산보다 주식에 돈이 몰렸다는 신호입니다",
    "unit": "배",
}


def get_indicator_id(client, slug: str) -> str:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    if not result.data:
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    return result.data[0]["id"]


def fetch_gold_prices(start: date, end: date) -> dict[str, float]:
    history = yf.Ticker(GOLD_TICKER).history(
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
    indicator_id = ensure_indicator(client, INDICATOR_META)
    kospi_indicator_id = get_indicator_id(client, KOSPI_RAW_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    gold_prices = fetch_gold_prices(start, today)
    print(f"[yfinance] {GOLD_TICKER} 종가 {len(gold_prices)}건 조회")

    kospi_prices = get_indicator_values(client, kospi_indicator_id, start)
    print(f"[Supabase] {KOSPI_RAW_SLUG} {len(kospi_prices)}건 조회")

    common_dates = sorted(set(gold_prices) & set(kospi_prices))

    if not common_dates:
        print("[kospi_gold_ratio] 금/코스피 시계열의 공통 날짜가 없습니다")
        return

    # 계산 가능한 날짜 전체를 매번 다시 쓴다(fetch_kosdaq_ratio·fetch_upbit_speculation과
    # 같은 이유) — 파생값이라 공식이나 details 스키마가 바뀌면 옛 행이 낡은 채로 남는다.
    # 실제로 2026-07-23 카드에 "코스피 6,798 ÷ 금 4,147"을 띄우려고 details를 새로 넣을 때,
    # '없는 날짜만 채우기' 방식이라 과거 행에 details가 안 들어가는 문제가 있었다.
    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": kospi_prices[d] / gold_prices[d],
            # 카드가 "1.65배"의 근거를 그대로 보여줄 수 있게 두 원값을 남긴다.
            "details": {
                "kospi_close": round(kospi_prices[d], 2),
                "gold_close": round(gold_prices[d], 2),
            },
        }
        for d in common_dates
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (전량 재계산)")

    latest_date = common_dates[-1]
    latest_ratio = kospi_prices[latest_date] / gold_prices[latest_date]
    print(
        f"[kospi_gold_ratio] 최신값 ({latest_date} 기준): "
        f"코스피 {kospi_prices[latest_date]:.2f} / 금 {gold_prices[latest_date]:.2f} "
        f"= {latest_ratio:.4f}"
    )


if __name__ == "__main__":
    main()
