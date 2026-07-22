"""업비트 공개 API(인증 불필요)의 BTC/KRW 일별 캔들과 yfinance의 BTC-USD·
USD/KRW로 김치프리미엄을, 업비트 자체 거래대금으로 거래대금 급증도를 계산해
"업비트 투기 과열 지수"(두 서브지표의 가중 산술평균)를 Supabase에 upsert.

- 김치프리미엄(%) = (업비트 BTC/KRW 종가 / (BTC-USD 종가 × USD/KRW 종가) - 1) × 100
  세 시계열(업비트/BTC-USD/USD-KRW)을 날짜 문자열로 그대로 매칭한다 —
  fetch_gold_ratio.py와 같은 트레이드오프로, 거래소별 시간대 차이로 인한
  하루 정도의 오차는 감수한다.
- 거래대금 급증도(%) = 오늘 24시간 거래대금 / 최근 VOLUME_WINDOW(30)일
  평균 거래대금 × 100. 업비트 자체 데이터만 쓰므로 날짜 매칭 문제가 없다.
- 종합 raw_value = 김프_progress × 0.5 + 거래대금_progress × 0.5, 여기서
  김프_progress = 김프/10*100, 거래대금_progress = 거래대금급증도/150*100
  (10, 150은 각 서브지표의 기준값). 원래는 기하평균(sqrt(a×b))을 썼는데,
  두 서브지표 중 하나라도 0에 가까우면(예: 역프로 김프_progress=0) 전체가
  통째로 0이 되어버려 다른 쪽 신호가 아무리 커도 묻히는 문제가 있었다 —
  가중 산술평균으로 바꿔 한쪽이 0이어도 나머지 절반은 반영되게 했다.
  김치프리미엄이 음수(역프)면 "투기 과열"과 반대 신호라 김프_progress는
  여전히 0으로 바닥 처리한다(NEGATIVE_CURRENT_CLAMP_SLUGS와 같은 원칙).
  이 raw_value는 이미 0~100대의 "진행률"에 가까운 값이라, calculate_score.py
  에서 threshold=100로 나누는 건 사실상 그대로 통과시키는 것에 가깝다.

캔들 조회는 업비트 API가 한 번에 최대 200개까지만 주기 때문에 `to`
파라미터로 과거로 페이지를 넘겨가며 모은다. 거래대금 30일 평균을 구하려면
조회 시작일보다 더 이전 데이터가 필요해서, 목표 기간(BACKFILL_DAYS)보다
VOLUME_WINDOW만큼 더 넉넉히 가져온다.

raw_value는 원본 시세가 아니라 계산식으로 파생된 값이라, fetch_naver_trend.py
처럼 매 실행마다 계산 가능한 날짜 전체를 다시 계산해 upsert한다 — 공식
자체가 나중에 또 바뀔 수 있는데, "이미 있는 날짜는 건너뛰기" 방식이면
공식을 바꿔도 과거 값이 낡은 채로 남는다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

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
    "headline": "김치 프리미엄과 코인 거래량",
    "category": "감성",
    # 코인 자금이 코스피로 옮겨왔다는 '자금 이동'으로 읽지 않는다 — 이 지표는 그걸
    # 관측하지 못한다. 김프·거래대금이 재는 건 위험자산을 감수하려는 심리의 온도이고,
    # 코스피 과열과는 같은 심리를 공유할 뿐이다.
    "description_beginner": "김프·거래대금이 같이 뛰면, 위험한 자산까지 돈이 몰릴 만큼 투자 심리가 달아올랐다는 신호입니다",
    "unit": "pt",
    "weight": 2,
}


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
    indicator_id = ensure_indicator(client, INDICATOR_META)
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
        composite = kimchi_progress * 0.5 + volume_progress * 0.5
        return premium, volume_surge[d], composite

    def row_for(d: str) -> dict:
        premium, surge, composite = composite_for(d)
        kimchi_progress = max(premium / KIMCHI_PREMIUM_THRESHOLD * 100, 0.0)
        volume_progress = surge / VOLUME_SURGE_THRESHOLD * 100
        return {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(composite, 2),
            # 카드가 목업 원본대로 김치프리미엄 / 거래량 강도 두 서브바를 그릴 수
            # 있도록 세부값을 details(JSONB)에 함께 저장한다.
            "details": {
                "kimchi_premium": round(premium, 2),
                "kimchi_progress": round(kimchi_progress, 1),
                "volume_surge": round(surge, 1),
                "volume_progress": round(volume_progress, 1),
            },
        }

    rows = [row_for(d) for d in sorted(common_dates)]
    client.table("indicator_values").upsert(rows, on_conflict="indicator_id,date").execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (details 포함)")

    latest_date = max(common_dates)
    premium, surge, composite = composite_for(latest_date)
    print(
        f"[{INDICATOR_SLUG}] 최신값 ({latest_date} 기준): "
        f"김치프리미엄 {premium:.2f}%, 거래대금 급증도 {surge:.1f}%, "
        f"종합 지수 {composite:.2f}pt"
    )


if __name__ == "__main__":
    main()
