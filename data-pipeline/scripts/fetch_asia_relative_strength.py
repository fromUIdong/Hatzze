"""yfinance의 니케이225(^N225)·항셍(^HSI)·대만가권(^TWII) 종가와 저장된
kospi_close_raw로 "아시아 3국 대비 코스피 상대강도"를 계산해 Supabase에 upsert.

각 지수(코스피 포함)마다 자기 자신의 거래일 기준으로 "최근 20거래일 수익률"을
따로 계산한다 — 시장마다 휴장일이 달라서 "20일 전"을 달력일이 아니라 그 지수
자체의 20번째 이전 거래일로 잡아야 정확하다(compute_20d_return). 그 다음
날짜 문자열이 코스피·일본·홍콩·대만 4개 시계열 모두에 공통으로 존재하는
날짜만 골라 아시아 3국 평균 수익률과 코스피 초과 수익률(코스피 - 아시아 평균)을
계산한다. 이 교집합 방식 때문에 각국 휴장일이 겹치지 않는 날은 자연히
제외된다(예: 한국은 개장, 일본은 공휴일인 날은 그날 값이 안 나옴) — 데이터
품질을 위한 의도된 트레이드오프다.

kospi_close_raw가 가진 1년치 범위 안에서 계산 가능한 구간(각 시계열의 최초
20거래일 이후부터)을 매 실행마다 전부 다시 upsert한다 — raw_value는 동일하지만
카드용 세부값(각국 20일 수익률)을 details(JSONB)에 채워 넣기 위해서다.
normalized_score는 payload에 없어 보존되고, yfinance 조회는 어차피 매 실행마다
하므로 추가 비용은 없다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

TICKERS = {
    "일본(니케이225)": "^N225",
    "홍콩(항셍)": "^HSI",
    "대만(가권)": "^TWII",
}
RETURN_WINDOW = 20  # 최근 20거래일 수익률
BACKFILL_DAYS = 365

KOSPI_RAW_SLUG = "kospi_close_raw"

INDICATOR_SLUG = "kospi_asia_relative_strength"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "아시아 3국(일본·홍콩·대만) 대비 코스피 상대강도",
    "category": "시장",
    "description_beginner": "최근 한 달간 코스피가 일본·홍콩·대만 증시보다 얼마나 더 올랐는지 비교해요. 이웃 증시와 달리 한국만 유독 앞서가고 있다면 그만큼 쏠림이 심하다는 뜻일 수 있어요",
    "unit": "%p",
    # kospi_volume_surge/vkospi와 비슷한 급의 보조-시장 지표라 기본값(1)보다
    # 높게 잡는다. 지정하지 않으면 다른 새 지표들처럼 안전하게 1로 들어간다.
    "weight": 3,
}


def get_indicator_id(client, slug: str) -> str:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    if not result.data:
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    return result.data[0]["id"]


def get_indicator_values(client, indicator_id: str, start: date) -> dict[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"]: float(row["raw_value"]) for row in result.data}


def fetch_prices(ticker: str, start: date, end: date) -> dict[str, float]:
    history = yf.Ticker(ticker).history(
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


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    kospi_raw_id = get_indicator_id(client, KOSPI_RAW_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    kospi_prices = get_indicator_values(client, kospi_raw_id, start)
    print(f"[Supabase] {KOSPI_RAW_SLUG} {len(kospi_prices)}건 조회")
    kospi_returns = compute_20d_return(kospi_prices)

    asia_returns: dict[str, dict[str, float]] = {}
    for name, ticker in TICKERS.items():
        prices = fetch_prices(ticker, start, today)
        returns = compute_20d_return(prices)
        print(f"[yfinance] {name}({ticker}) 종가 {len(prices)}건 → 20일 수익률 {len(returns)}건")
        asia_returns[ticker] = returns

    common_dates = (
        set(kospi_returns)
        & set(asia_returns["^N225"])
        & set(asia_returns["^HSI"])
        & set(asia_returns["^TWII"])
    )
    if not common_dates:
        print(f"[{INDICATOR_SLUG}] 4개 시계열의 공통 날짜가 없습니다")
        return

    def relative_strength(d: str) -> float:
        asia_avg = (
            asia_returns["^N225"][d] + asia_returns["^HSI"][d] + asia_returns["^TWII"][d]
        ) / 3
        return kospi_returns[d] - asia_avg

    def details_for(d: str) -> dict:
        # 카드가 목업 원본대로 4개국 상대 막대를 그릴 수 있도록 각국 20일 수익률을
        # details(JSONB)에 함께 저장한다(코스피=100 기준 상대지수는 프론트에서 계산).
        return {
            "kospi": round(kospi_returns[d], 2),
            "nikkei": round(asia_returns["^N225"][d], 2),
            "hangseng": round(asia_returns["^HSI"][d], 2),
            "taiex": round(asia_returns["^TWII"][d], 2),
        }

    # 공통 날짜 전체를 매 실행마다 다시 upsert한다 — raw_value는 동일하지만 카드용
    # 세부값(각국 수익률)을 details에 채워 넣기 위해서다. normalized_score는 payload에
    # 없어 보존되고, yfinance 조회는 어차피 매 실행마다 하므로 추가 비용은 없다.
    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(relative_strength(d), 2),
            "details": details_for(d),
        }
        for d in sorted(common_dates)
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (details 포함)")

    latest_date = max(common_dates)
    latest_asia_avg = (
        asia_returns["^N225"][latest_date]
        + asia_returns["^HSI"][latest_date]
        + asia_returns["^TWII"][latest_date]
    ) / 3
    print(
        f"[{INDICATOR_SLUG}] 최신값 ({latest_date} 기준): "
        f"코스피 20일 수익률 {kospi_returns[latest_date]:.2f}%, "
        f"아시아 3국 평균 {latest_asia_avg:.2f}% "
        f"(일본 {asia_returns['^N225'][latest_date]:.2f}%, "
        f"홍콩 {asia_returns['^HSI'][latest_date]:.2f}%, "
        f"대만 {asia_returns['^TWII'][latest_date]:.2f}%), "
        f"초과 수익률 {relative_strength(latest_date):.2f}%p"
    )


if __name__ == "__main__":
    main()
