"""yfinance의 VIX(^VIX) 종가와 이미 저장된 vkospi 값을 날짜로 매칭해
"VIX 대비 VKOSPI 스프레드"를 계산해 Supabase에 upsert.

⚠️ **2026-07-23 현재 이 스크립트는 일일 워크플로에서 빠져 있다(수동 실행 전용).**
2026-07-20 에 지표를 화면·점수에서 내렸는데(is_public=false, 임계값·가중치 표에도 없음)
수집만 계속 돌고 있었다 — 매일 yfinance 를 호출하고 실패 집계까지 차지하면서 산출물은
어디에도 안 쓰였다. 되살릴 때 워크플로에 다시 넣으면 된다(그때 VKOSPI 카드와 겹치지
않게 무엇을 보여줄지부터 정할 것).

VKOSPI는 fetch_vkospi.py가 이미 매일 수집해 indicator_values에 쌓고 있으므로
여기서 다시 받지 않고 Supabase에서 읽기만 한다 — VIX만 새로 yfinance에서 받는다.

VIX와 VKOSPI(우리가 저장한 KRX "코스피 200 변동성지수")는 산출식·스케일이 서로
달라(전자는 ~15, 후자는 ~78 수준) 절대값을 그냥 빼면 의미가 없다. 그래서 각
지수를 자기 최근 1년 분포 내 백분위(0~100)로 바꾼 뒤, raw = VIX 백분위 - VKOSPI
백분위로 계산한다. 양수로 클수록 "미국은 불안한데(높은 백분위) 한국만 유독
잠잠(낮은 백분위)" = 방심 신호이므로 direction="high"다. 음수(한국이 오히려 더
출렁)일 땐 calculate_score에서 progress를 0으로 바닥 처리한다
(NEGATIVE_CURRENT_CLAMP_SLUGS).

VIX와 VKOSPI는 각각 미국/한국 거래일 기준이라 하루 정도 어긋날 수 있는데,
kospi_gold_ratio와 동일하게 지금 단계에서는 이 오차를 감수하고 단순 날짜
문자열 매칭으로 시작한다.

VIX·VKOSPI 공통 날짜 전체를 매 실행마다 다시 upsert한다 — raw_value(스프레드)는
동일하지만 카드용 세부값(VIX·VKOSPI 개별값)을 details(JSONB)에 채워 넣기 위해서다.
normalized_score는 payload에 없어 보존되고, VIX 조회는 어차피 매 실행마다 한다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

VIX_TICKER = "^VIX"
BACKFILL_DAYS = 365
PERCENTILE_WINDOW = 252  # 백분위 계산에 쓰는 최대 트레일링 거래일(약 1년)

VKOSPI_SLUG = "vkospi"

INDICATOR_SLUG = "vix_vkospi_spread"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "VIX 대비 VKOSPI 스프레드",
    "category": "시장",
    "headline": "미국과 한국의 변동성 지수 격차",
    "description_beginner": "미국은 불안한데 한국 증시만 잠잠할수록, 방심 신호로 봅니다",
    "unit": "pt",
    # 2026-07-20 대시보드에서 내림: 1년의 76%가 과열도 0이라 종합점수에 기여하지
    #   못했고(같은 이유로 market_actions 공식을 갈아엎었다), VKOSPI 에서 파생된
    #   지표라 VKOSPI 카드와 겹쳤다. 데이터는 계속 쌓아 두되 화면·점수에서는 뺀다.
    "is_public": False,
    # raw = VIX 백분위 - VKOSPI 백분위. 양수로 클수록 "한국만 유독 방심" = 과열이므로
    # direction은 high(기본). VIX·VKOSPI는 산출식/스케일이 달라 절대값 뺄셈이 무의미했는데,
    # 각자 자기 1년 분포 내 백분위로 바꾸면 스케일과 무관하게 비교할 수 있다.
    "direction": "high",
}


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


def trailing_percentiles(series: dict[str, float]) -> dict[str, float]:
    """각 날짜의 값이 '자기 직전 PERCENTILE_WINDOW 거래일 분포'에서 몇 백분위인지
    (0~100)를 계산한다. VIX와 VKOSPI는 산출식·스케일이 달라 절대값을 그대로 빼면
    안 되므로, 각자 자기 과거 분포 내 위치(백분위)로 바꿔 비교 가능하게 만든다."""
    dates = sorted(series)
    vals = [series[d] for d in dates]
    result: dict[str, float] = {}
    for i, d in enumerate(dates):
        lo = max(0, i - PERCENTILE_WINDOW + 1)
        window = vals[lo : i + 1]
        cur = vals[i]
        result[d] = sum(1 for x in window if x <= cur) / len(window) * 100
    return result


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    vkospi_id = get_indicator_id(client, VKOSPI_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    vix_prices = fetch_vix_prices(start, today)
    print(f"[yfinance] {VIX_TICKER} 종가 {len(vix_prices)}건 조회")

    vkospi_values = get_indicator_values(client, vkospi_id, start)
    print(f"[Supabase] {VKOSPI_SLUG} {len(vkospi_values)}건 조회")

    common_dates = sorted(set(vix_prices) & set(vkospi_values))
    if not common_dates:
        print("[vix_vkospi_spread] VIX/VKOSPI 시계열의 공통 날짜가 없습니다")
        return

    # 각 지수를 자기 1년 분포 내 백분위로 바꾼 뒤, raw = VIX 백분위 - VKOSPI 백분위.
    # 양수로 클수록 "미국은 불안한데 한국만 유독 잠잠" = 방심(과열). 매 실행 전체를
    # 다시 upsert한다 — normalized_score는 payload에 없어 보존된다.
    vix_pct = trailing_percentiles(vix_prices)
    vkospi_pct = trailing_percentiles(vkospi_values)

    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(vix_pct[d] - vkospi_pct[d], 2),
            "details": {
                "vix": round(vix_prices[d], 2),
                "vkospi": round(vkospi_values[d], 2),
                "vix_pct": round(vix_pct[d], 1),
                "vkospi_pct": round(vkospi_pct[d], 1),
            },
        }
        for d in common_dates
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (백분위 스프레드)")

    latest_date = common_dates[-1]
    print(
        f"[vix_vkospi_spread] 최신값 ({latest_date} 기준): "
        f"VIX {vix_prices[latest_date]:.2f}(백분위 {vix_pct[latest_date]:.0f}) - "
        f"VKOSPI {vkospi_values[latest_date]:.2f}(백분위 {vkospi_pct[latest_date]:.0f}) "
        f"-> 방심도 {vix_pct[latest_date] - vkospi_pct[latest_date]:.1f}pt"
    )


if __name__ == "__main__":
    main()
