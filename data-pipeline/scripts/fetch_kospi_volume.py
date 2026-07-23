"""KRX Open API로 코스피 일별 거래대금을 받아와 Supabase에 upsert.

코스피 지수 시세 엔드포인트(kospi_dd_trd, fetch_kospi_high_gap.py/fetch_buffett_index.py에서
이미 승인받아 쓰고 있음)의 ACC_TRDVAL(거래대금, 원) 필드를 그대로 사용한다 — 별도
엔드포인트 승인이 필요 없다. 억원 단위로 환산해 저장하고, "급증도" 판단(과거 대비
상위 5% 등)은 calculate_score.py의 percentile 로직에서 처리한다.

최초 실행 시 최근 1년치를 백필해서 저장하고, 이후 실행부터는 아직 없는 날짜만 채운다.
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402
from common.timeutil import days_to_backfill  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
VOLUME_AVG_WINDOW = 30  # 급증도 비교 기준: 직전 30영업일 평균 거래대금
LEVEL_WINDOW = 250      # 절대 수준 비교 기준: 직전 1년(250영업일) 분포에서의 백분위
LEVEL_MIN_SAMPLE = 60   # 백분위가 널뛰지 않을 최소 표본
TARGET_INDEX_NAME = "코스피"
TRADING_VALUE_KEY = "ACC_TRDVAL"
WON_PER_EOK = 100_000_000  # 1억원 = 1e8원

INDICATOR_SLUG = "kospi_volume_surge"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "거래대금 급증도",
    "headline": "평소 대비 오늘 오간 거래대금",
    "category": "시장",
    "description_beginner": "코스피 거래가 평소보다 훨씬 몰리면, 다들 흥분해 달려든다는 신호입니다",
    "unit": "억원",
}


def fetch_trading_value(bas_dd: str) -> float | None:
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return None  # 네트워크 재시도 소진 — 이 날짜만 건너뜀
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'코스피 시리즈 일별시세정보' 개별 서비스 API 이용신청 및 승인이 됐는지 확인하세요."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    record = next((r for r in records if r.get("IDX_NM") == TARGET_INDEX_NAME), None)
    if record is None:
        return None

    value = record.get(TRADING_VALUE_KEY)
    if value in (None, ""):
        return None  # 휴장일 등으로 값이 비어있는 경우
    won = float(str(value).replace(",", ""))
    return won / WON_PER_EOK


def backfill(client, indicator_id: str) -> None:
    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    existing_dates = {row["date"] for row in existing.data}

    # 옛 공휴일을 매 실행 다시 물어보지 않도록 최근 창만 훑는다(common/timeutil 참고).
    missing_days = days_to_backfill(existing_dates, today, bootstrap_days=BACKFILL_DAYS)
    if not missing_days:
        print("[KRX] 백필할 신규 날짜 없음 (이미 최신 상태)")
        return

    print(f"[KRX] 백필 대상 {len(missing_days)}일 조회 시작")
    new_rows = []
    for d in missing_days:
        value = fetch_trading_value(d.strftime("%Y%m%d"))
        if value is not None:
            new_rows.append(
                {"indicator_id": indicator_id, "date": d.isoformat(), "raw_value": value}
            )
        time.sleep(REQUEST_DELAY_SEC)

    if new_rows:
        client.table("indicator_values").upsert(
            new_rows, on_conflict="indicator_id,date"
        ).execute()
    skipped = len(missing_days) - len(new_rows)
    print(f"[KRX] 백필 완료: {len(new_rows)}건 저장 (휴장일 등 {skipped}건 제외)")


def get_values(client, indicator_id: str, start: date) -> dict[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"]: float(row["raw_value"]) for row in result.data}


def store_rolling_average_details(client, indicator_id: str) -> None:
    """각 날짜의 직전 30영업일 평균 대비 급증율(%)과 직전 250영업일 대비 절대 수준
    백분위를 계산해 details에 채운다. raw_value는 그대로 두고(같은 값 재설정) details만
    갱신하며, normalized_score는 payload에 없어 보존된다.

    **level_pct 를 넣는 이유**(2026-07-23, docs/indicator-audit-2026-07-23.md §3-1·§4-2):
    30일 상대만 보면 서서히 몇 배가 되는 흐름이 원리상 안 보인다. 1년간 절대 거래대금은
    9.4조 → 50.8조(5.4배)로 코스피와 상관 +0.922 였는데, 같은 기간 surge_pct 와 코스피의
    상관은 **-0.019** 였다. 2026-06-22 사상 최고점 당일 거래대금이 41.9조인데 급증율이
    +2.3%라 과열도가 25.6(저온 근처)으로 찍혔다. 급증율은 '단기 발작'을, 절대 백분위는
    '국면'을 잡으므로 calculate_score 가 7:3으로 섞는다.
    """
    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    values = get_values(client, indicator_id, start)
    dates_sorted = sorted(values)

    rows = []
    for i in range(VOLUME_AVG_WINDOW, len(dates_sorted)):
        window = [values[dates_sorted[j]] for j in range(i - VOLUME_AVG_WINDOW, i)]
        avg = sum(window) / VOLUME_AVG_WINDOW
        if avg <= 0:
            continue
        d = dates_sorted[i]
        detail = {
            "avg_30d": round(avg, 0),
            "surge_pct": round(values[d] / avg * 100 - 100, 1),
        }
        # 절대 수준: 직전 LEVEL_WINDOW 영업일 중 오늘보다 낮았던 날의 비율(0~100).
        # 오늘을 뺀 과거만 보므로 미래 정보가 섞이지 않는다. 표본이 얇으면 백분위가
        # 널뛰므로 최소 LEVEL_MIN_SAMPLE 일이 쌓인 뒤부터 넣는다.
        hist = [values[dates_sorted[j]] for j in range(max(0, i - LEVEL_WINDOW), i)]
        if len(hist) >= LEVEL_MIN_SAMPLE:
            detail["level_pct"] = round(
                sum(1 for v in hist if v < values[d]) / len(hist) * 100, 1
            )
        rows.append(
            {
                "indicator_id": indicator_id,
                "date": d,
                "raw_value": values[d],
                "details": detail,
            }
        )

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    print(f"[Supabase] 30일 평균 details 저장 완료: {len(rows)}건")


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    backfill(client, indicator_id)
    store_rolling_average_details(client, indicator_id)


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
