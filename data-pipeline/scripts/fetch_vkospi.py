"""KRX Open API(파생상품지수 시세, idx/drvprod_dd_trd)로 VKOSPI를 받아와 Supabase에 upsert.

VKOSPI는 코스피200 옵션 가격 기반 변동성지수라 "파생상품지수" 엔드포인트에 포함되어
있을 것으로 보고 이 엔드포인트를 사용한다. kospi_dd_trd(지수 시세)와는 별개로 개별
서비스 이용신청이 필요할 수 있다 — 401이 나면 그 사실을 알려주고 종료한다.

실제 응답의 IDX_NM에는 "VKOSPI"가 아니라 KRX 공식 명칭인 "코스피 200 변동성지수"로
들어온다(승인 후 실응답으로 확인함). "변동성지수"만으로 substring 매칭하면 "변동성매칭
양매도지수" 등 다른 파생상품지수와 헷갈릴 수 있어 정확한 이름으로 매칭한다.

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

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
CLOSE_PRICE_KEY = "CLSPRC_IDX"
TARGET_INDEX_NAME = "코스피 200 변동성지수"  # KRX 공식 명칭 (실응답 확인 완료, "VKOSPI"라는 이름은 안 씀)

INDICATOR_SLUG = "vkospi"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "VKOSPI (변동성지수)",
    "category": "시장",
    "description_beginner": "코스피의 '공포지수'예요. 너무 낮으면 다들 위험을 잊고 방심하고 있다는 신호일 수 있어요",
    "unit": "pt",
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def fetch_vkospi_value(bas_dd: str) -> float | None:
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return None  # 네트워크 재시도 소진 — 이 날짜만 건너뜀
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'파생상품지수 시세정보'(idx/drvprod_dd_trd) 개별 서비스 API 이용신청 및 "
            "승인이 됐는지 확인하세요 (코스피 지수 시세와는 별도 승인이 필요합니다)."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    if not records:
        return None

    record = next(
        (r for r in records if r.get("IDX_NM") == TARGET_INDEX_NAME), None
    )
    if record is None:
        found_names = [r.get("IDX_NM") for r in records]
        raise KeyError(
            f"'{TARGET_INDEX_NAME}' 지수를 응답에서 찾지 못했습니다. "
            f"포함된 지수명: {found_names}"
        )

    value = record.get(CLOSE_PRICE_KEY)
    if value in (None, ""):
        return None  # 휴장일 등으로 값이 비어있는 경우
    return float(str(value).replace(",", ""))


def business_days(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon ... 4=Fri
            yield current
        current += timedelta(days=1)


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

    missing_days = [
        d for d in business_days(start, today) if d.isoformat() not in existing_dates
    ]
    if not missing_days:
        print("[KRX] 백필할 신규 날짜 없음 (이미 최신 상태)")
        return

    print(f"[KRX] 백필 대상 {len(missing_days)}일 조회 시작")
    new_rows = []
    for d in missing_days:
        value = fetch_vkospi_value(d.strftime("%Y%m%d"))
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


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    backfill(client, indicator_id)


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
