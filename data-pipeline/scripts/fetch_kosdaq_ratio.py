"""KRX Open API(코스닥 지수 시세, idx/kosdaq_dd_trd)로 코스닥 종가를 받아와
저장된 kospi_close_raw와 날짜 매칭해 "코스피 대비 코스닥 상대강도"(코스닥/코스피)
비율을 계산해 Supabase에 upsert.

kospi_dd_trd(지수 시세)와는 별개로 개별 서비스 이용신청이 필요할 수 있다. 401이
나면 KRX 정보데이터시스템에서 '코스닥 시리즈 일별시세정보' 서비스를 신청/승인받아야
한다.

최초 실행 시 1년치를 백필하고, 이후 실행부터는 아직 없는 날짜만 채운다.
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
from common.timeutil import business_days  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kosdaq_dd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
CLOSE_PRICE_KEY = "CLSPRC_IDX"
# kospi_dd_trd처럼 여러 계열 지수(코스닥, 코스닥 150 등)가 함께 내려올 것으로 예상.
TARGET_INDEX_NAME = "코스닥"

KOSPI_RAW_SLUG = "kospi_close_raw"

INDICATOR_SLUG = "kosdaq_kospi_ratio"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "코스피 대비 코스닥 상대강도",
    "category": "시장",
    "description_beginner": "코스닥이 유독 앞서가면 투기성 자금이 위험을 무릅쓰고 몰리고 있다는 신호일 수 있어요",
    "unit": "배",
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


def fetch_kosdaq_close(bas_dd: str) -> float | None:
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return None  # 네트워크 재시도 소진 — 이 날짜만 건너뜀
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'코스닥 시리즈 일별시세정보'(idx/kosdaq_dd_trd) 개별 서비스 API 이용신청 "
            "및 승인이 됐는지 확인하세요 (코스피 지수 시세와는 별도 승인이 필요합니다)."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    record = next((r for r in records if r.get("IDX_NM") == TARGET_INDEX_NAME), None)
    if record is None:
        return None

    value = record.get(CLOSE_PRICE_KEY)
    if value in (None, ""):
        return None  # 휴장일 등으로 값이 비어있는 경우
    return float(str(value).replace(",", ""))


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    kospi_indicator_id = get_indicator_id(client, KOSPI_RAW_SLUG)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    kospi_prices = get_indicator_values(client, kospi_indicator_id, start)
    print(f"[Supabase] {KOSPI_RAW_SLUG} {len(kospi_prices)}건 조회")
    existing_dates = set(get_indicator_values(client, indicator_id, start).keys())

    missing_days = [
        d
        for d in business_days(start, today)
        if d.isoformat() not in existing_dates and d.isoformat() in kospi_prices
    ]
    if not missing_days:
        print("[kosdaq_kospi_ratio] 백필할 신규 날짜 없음 (이미 최신 상태)")
        return

    print(f"[KRX] 백필 대상 {len(missing_days)}일 조회 시작")
    rows = []
    for d in missing_days:
        kosdaq_close = fetch_kosdaq_close(d.strftime("%Y%m%d"))
        if kosdaq_close is not None:
            ratio = kosdaq_close / kospi_prices[d.isoformat()]
            rows.append(
                {"indicator_id": indicator_id, "date": d.isoformat(), "raw_value": ratio}
            )
        time.sleep(REQUEST_DELAY_SEC)

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    skipped = len(missing_days) - len(rows)
    print(f"[KRX] 백필 완료: {len(rows)}건 저장 (휴장일 등 {skipped}건 제외)")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
