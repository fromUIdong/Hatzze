"""업비트 공개 API(인증 불필요)의 BTC/KRW 일별 캔들과 yfinance의 BTC-USD·
USD/KRW로 김치프리미엄을, 업비트 자체 거래대금으로 거래대금 급증도를 계산해
"업비트 투기 과열 지수"(두 서브지표의 기하평균)를 Supabase에 upsert.

- 김치프리미엄(%) = (업비트 BTC/KRW 종가 / (BTC-USD 종가 × USD/KRW 종가) - 1) × 100
  세 시계열(업비트/BTC-USD/USD-KRW)을 날짜 문자열로 그대로 매칭한다 —
  fetch_gold_ratio.py와 같은 트레이드오프로, 거래소별 시간대 차이로 인한
  하루 정도의 오차는 감수한다.
- 거래대금 급증도(%) = 오늘 24시간 거래대금 / 최근 VOLUME_WINDOW(30)일
  평균 거래대금 × 100. 업비트 자체 데이터만 쓰므로 날짜 매칭 문제가 없다.
- 종합 raw_value = sqrt(김프_progress × 거래대금_progress), 여기서
  김프_progress = 김프/10*100, 거래대금_progress = 거래대금급증도/150*100
  (10, 150은 각 서브지표의 기준값). 기하평균이라 한쪽만 극단적으로 튀어도
  전체가 과대평가되지 않고, 둘 다 높아야 종합 지수도 높게 나온다.
  김치프리미엄이 음수(역프)면 "투기 과열"과 반대 신호라 김프_progress를
  0으로 바닥 처리한다 — 그러면 기하평균 전체가 0이 되어, 역프 상태에서는
  거래대금이 아무리 뛰어도 종합 지수가 뜨지 않는다(의도된 동작).
  이 raw_value는 이미 0~100대의 "진행률"에 가까운 값이라, calculate_score.py
  에서 threshold=100로 나누는 건 사실상 그대로 통과시키는 것에 가깝다.

캔들 조회는 업비트 API가 한 번에 최대 200개까지만 주기 때문에 `to`
파라미터로 과거로 페이지를 넘겨가며 모은다. 거래대금 30일 평균을 구하려면
조회 시작일보다 더 이전 데이터가 필요해서, 목표 기간(BACKFILL_DAYS)보다
VOLUME_WINDOW만큼 더 넉넉히 가져온다.

최초 실행 시 계산 가능한 만큼 1년치를 백필하고, 이후 실행부터는 아직
없는 날짜만 채운다.
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402

UPBIT_CANDLES_URL = "https://api.upbit.com/v1/candles/days"
UPBIT_MARKET = "KRW-BTC"
UPBIT_PAGE_SIZE = 200
REQUEST_TIMEOUT_SEC = 15

BTC_USD_TICKER = "BTC-USD"
USD_KRW_TICKER = "KRW=X"

BACKFILL_DAYS = 365
VOLUME_WINDOW = 30  # 거래대금 급증도 계산에 쓰는 이동평균 기간

KIMCHI_PREMIUM_THRESHOLD = 10.0
VOLUME_SURGE_THRESHOLD = 150.0

INDICATOR_SLUG = "upbit_speculation_index"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "업비트 투기 과열 지수",
    "category": "밈",
    "description_beginner": "개미들이 코스피만 하는 게 아니에요 — 여유자금이 있을 때 코인 시장으로도 같이 흘러가요. 김치프리미엄과 거래대금이 동시에 뛴다면, 그 뜨거운 돈이 코스피에도 이미 들어와 있을 가능성이 높아요",
    "unit": "pt",
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


def fetch_upbit_candles(min_days: int) -> dict[str, dict]:
    """날짜(YYYY-MM-DD) -> {"close": KRW 종가, "trade_value": 24h 거래대금(KRW)}."""
    candles: dict[str, dict] = {}
    to_param: str | None = None

    while len(candles) < min_days:
        params = {"market": UPBIT_MARKET, "count": UPBIT_PAGE_SIZE}
        if to_param:
            params["to"] = to_param

        resp = requests.get(UPBIT_CANDLES_URL, params=params, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break

        for candle in page:
            d = candle["candle_date_time_kst"][:10]
            candles[d] = {
                "close": float(candle["trade_price"]),
                "trade_value": float(candle["candle_acc_trade_price"]),
            }

        oldest_kst = page[-1]["candle_date_time_kst"].replace("T", " ")
        to_param = oldest_kst

        if len(page) < UPBIT_PAGE_SIZE:
            break

    return candles


def fetch_yf_close(ticker: str, start: date, end: date) -> dict[str, float]:
    history = yf.Ticker(ticker).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat()
    )
    return {ts.date().isoformat(): float(close) for ts, close in history["Close"].items()}


def compute_volume_surge(upbit_candles: dict[str, dict]) -> dict[str, float]:
    """날짜별 (당일 거래대금 / 최근 VOLUME_WINDOW일 평균 거래대금) × 100."""
    dates = sorted(upbit_candles.keys())
    result = {}
    for i in range(VOLUME_WINDOW, len(dates)):
        window_dates = dates[i - VOLUME_WINDOW : i]
        avg = sum(upbit_candles[d]["trade_value"] for d in window_dates) / VOLUME_WINDOW
        if avg == 0:
            continue
        today_value = upbit_candles[dates[i]]["trade_value"]
        result[dates[i]] = today_value / avg * 100
    return result


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    upbit_candles = fetch_upbit_candles(BACKFILL_DAYS + VOLUME_WINDOW + 5)
    print(f"[Upbit] {UPBIT_MARKET} 일별 캔들 {len(upbit_candles)}건 조회")

    btc_usd = fetch_yf_close(BTC_USD_TICKER, start, today)
    usd_krw = fetch_yf_close(USD_KRW_TICKER, start, today)
    print(f"[yfinance] {BTC_USD_TICKER} {len(btc_usd)}건, {USD_KRW_TICKER} {len(usd_krw)}건 조회")

    volume_surge = compute_volume_surge(upbit_candles)
    print(f"[upbit_speculation_index] 거래대금 급증도 {len(volume_surge)}건 계산")

    common_dates = set(upbit_candles) & set(btc_usd) & set(usd_krw) & set(volume_surge)
    if not common_dates:
        print(f"[{INDICATOR_SLUG}] 공통 날짜가 없어 계산할 수 없습니다")
        return

    def composite_for(d: str) -> tuple[float, float, float]:
        krw_price = upbit_candles[d]["close"]
        global_price_krw = btc_usd[d] * usd_krw[d]
        premium = (krw_price / global_price_krw - 1) * 100
        kimchi_progress = max(premium / KIMCHI_PREMIUM_THRESHOLD * 100, 0.0)
        volume_progress = volume_surge[d] / VOLUME_SURGE_THRESHOLD * 100
        composite = math.sqrt(kimchi_progress * volume_progress)
        return premium, volume_surge[d], composite

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    existing_dates = {row["date"] for row in existing.data}
    missing_dates = sorted(common_dates - existing_dates)

    if not missing_dates:
        print(f"[{INDICATOR_SLUG}] 백필할 신규 날짜 없음 (이미 최신 상태)")
    else:
        rows = []
        for d in missing_dates:
            _, _, composite = composite_for(d)
            rows.append(
                {"indicator_id": indicator_id, "date": d, "raw_value": round(composite, 2)}
            )
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
        print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_date = max(common_dates)
    premium, surge, composite = composite_for(latest_date)
    print(
        f"[{INDICATOR_SLUG}] 최신값 ({latest_date} 기준): "
        f"김치프리미엄 {premium:.2f}%, 거래대금 급증도 {surge:.1f}%, "
        f"종합 지수 {composite:.2f}pt"
    )


if __name__ == "__main__":
    main()
