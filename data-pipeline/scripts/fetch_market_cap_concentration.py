"""KRX Open API의 유가증권 일별매매정보(sto/stk_bydd_trd)로 코스피 전종목
시가총액을 받아 상위 10종목 쏠림도를 계산해 Supabase에 upsert.

percentile이 아니라 고정 기준값 체계라 히스토리 백필이 필요 없다 — 오늘자
스냅샷 하나만 저장한다(fetch_buffett_index.py의 kospi_market_cap_raw와 동일한
"오늘 값만 매일 갱신" 방식).

sto/stk_bydd_trd(유가증권 일별매매정보) 서비스는 처음 작성 시점(2026-07-11)엔
401(승인 대기)이었으나 이후 승인되어 정상 동작한다. 혹시 다시 401이 나면
leverage_etf_volume의 선물 미결제약정 API와 동일한 패턴으로, 그 사실을 로그로
남기고 데이터 수집만 건너뛴다(indicators 메타데이터는 이미 등록되어 있음).

전체 시가총액은 이미 fetch_buffett_index.py가 매일 kospi_market_cap_raw로
저장하고 있으므로 여기서 다시 계산하지 않고 그 값을 그대로 나눠 쓴다(같은
거래일 기준으로 날짜 매칭, 당일 값이 없으면 최근 값으로 대체).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
MARKET_CAP_KEY = "MKTCAP"
LOOKBACK_DAYS = 10  # 최근 거래일/kospi_market_cap_raw 값을 못 찾을 경우를 대비한 안전 범위
TOP_N = 10

RAW_MKTCAP_SLUG = "kospi_market_cap_raw"

INDICATOR_SLUG = "top10_market_cap_concentration"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "코스피 시가총액 상위 10종목 쏠림도",
    "category": "시장",
    "headline": "몇몇 대장주가 이끄는 지수",
    "description_beginner": "코스피 상승이 몇몇 대형주에만 기대고 있는지 보여줘요. 쏠림이 심할수록 겉보기 지수는 좋아 보여도 시장이 실제로는 얇고 취약해서, 대장주가 흔들리면 함께 무너질 수 있어요",
    "unit": "%",
    "weight": 3,
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def get_indicator_id(client, slug: str) -> str | None:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    return result.data[0]["id"] if result.data else None


def fetch_all_stocks(bas_dd: str) -> list[dict]:
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return []  # 네트워크 재시도 소진 — 이 날짜만 건너뜀(호출자가 이전 날짜로 재시도)
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'유가증권 일별매매정보'(sto/stk_bydd_trd) 개별 서비스 API 이용신청 및 "
            "승인이 됐는지 확인하세요."
        )
    resp.raise_for_status()
    return resp.json().get("OutBlock_1", [])


def fetch_latest_top10_sum() -> tuple[str, float]:
    day = date.today()
    for _ in range(LOOKBACK_DAYS):
        records = fetch_all_stocks(day.strftime("%Y%m%d"))
        caps = sorted(
            (
                float(str(r[MARKET_CAP_KEY]).replace(",", ""))
                for r in records
                if r.get(MARKET_CAP_KEY) not in (None, "")
            ),
            reverse=True,
        )
        if caps:
            return day.isoformat(), sum(caps[:TOP_N])
        day -= timedelta(days=1)

    raise RuntimeError(f"최근 {LOOKBACK_DAYS}일 내 코스피 전종목 시세 데이터를 찾지 못했습니다")


def fetch_total_market_cap(client, target_date: str) -> tuple[str, float]:
    raw_id = get_indicator_id(client, RAW_MKTCAP_SLUG)
    if raw_id is None:
        raise RuntimeError(
            f"'{RAW_MKTCAP_SLUG}' indicator가 아직 없습니다 — fetch_buffett_index.py가 "
            "먼저 실행되어야 합니다"
        )

    exact = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", raw_id)
        .eq("date", target_date)
        .execute()
    )
    if exact.data:
        return exact.data[0]["date"], float(exact.data[0]["raw_value"])

    nearest = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", raw_id)
        .lte("date", target_date)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not nearest.data:
        raise RuntimeError(f"'{RAW_MKTCAP_SLUG}'에 저장된 값이 없습니다")
    return nearest.data[0]["date"], float(nearest.data[0]["raw_value"])


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    top10_date, top10_sum = fetch_latest_top10_sum()
    print(f"[KRX] 코스피 시가총액 상위 {TOP_N}종목 합계 ({top10_date} 기준): {top10_sum:,.0f}원")

    total_date, total_cap = fetch_total_market_cap(client, top10_date)
    print(f"[Supabase] 코스피 전체 시가총액 ({total_date} 기준): {total_cap:,.0f}원")

    concentration = top10_sum / total_cap * 100
    print(f"[계산] 상위 10종목 쏠림도 = {top10_sum:,.0f} / {total_cap:,.0f} x 100 = {concentration:.2f}%")

    rounded = round(concentration, 2)
    client.table("indicator_values").upsert(
        {"indicator_id": indicator_id, "date": top10_date, "raw_value": rounded},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={top10_date}, raw_value={rounded}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
