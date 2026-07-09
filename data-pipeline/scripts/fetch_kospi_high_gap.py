"""KRX Open API로 코스피 지수 종가를 받아와 52주 신고가 대비 괴리율을 계산해 Supabase에 upsert.

최초 실행 시 최근 1년치 일별 종가를 백필해서 raw price 캐시(kospi_close_raw indicator)에
저장하고, 이후 실행부터는 아직 없는 날짜만 추가로 채운다. 매 실행마다 최신 종가 기준
52주 신고가 대비 괴리율을 계산해 kospi_high_gap indicator의 오늘 값으로 upsert한다.
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import KRX_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
CLOSE_PRICE_KEY = "CLSPRC_IDX"
# OutBlock_1에는 코스피 외에도 코스피200/100/50 등 여러 계열 지수가 함께 내려온다.
TARGET_INDEX_NAME = "코스피"

RAW_SLUG = "kospi_close_raw"
RAW_META = {
    "slug": RAW_SLUG,
    "name": "코스피 지수 종가 (내부용 원본)",
    "category": "정통",
    "description_beginner": "52주 신고가 대비 괴리율 계산을 위해 내부적으로 저장하는 코스피 지수 종가 데이터예요.",
    "unit": "pt",
    "is_public": False,
}

GAP_SLUG = "kospi_high_gap"
GAP_META = {
    "slug": GAP_SLUG,
    "name": "코스피 신고가 대비 괴리율",
    "category": "정통",
    "description_beginner": (
        '코스피가 역대 최고 기록에 얼마나 가까운지 보여줘요. '
        '가까울수록 "더 오를 데가 있나" 싶은 부담스러운 구간'
    ),
    "unit": "%",
}


def ensure_indicator(client, meta: dict) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", meta["slug"]).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(meta).execute()
    return inserted.data[0]["id"]


def fetch_close_price(bas_dd: str) -> float | None:
    resp = requests.get(
        KRX_URL,
        params={"basDd": bas_dd},
        headers={"AUTH_KEY": KRX_API_KEY},
        timeout=10,
    )
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'코스피 시리즈 일별시세정보' 개별 서비스 API 이용신청 및 승인이 됐는지 확인하세요."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    if not records:
        return None

    record = next((r for r in records if r.get("IDX_NM") == TARGET_INDEX_NAME), None)
    if record is None:
        found_names = [r.get("IDX_NM") for r in records]
        raise KeyError(f"'{TARGET_INDEX_NAME}' 지수를 응답에서 찾지 못했습니다. 포함된 지수명: {found_names}")

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


def backfill_raw_prices(client, raw_indicator_id: str) -> None:
    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", raw_indicator_id)
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
        close = fetch_close_price(d.strftime("%Y%m%d"))
        if close is not None:
            new_rows.append(
                {"indicator_id": raw_indicator_id, "date": d.isoformat(), "raw_value": close}
            )
        time.sleep(REQUEST_DELAY_SEC)

    if new_rows:
        client.table("indicator_values").upsert(
            new_rows, on_conflict="indicator_id,date"
        ).execute()
    skipped = len(missing_days) - len(new_rows)
    print(f"[KRX] 백필 완료: {len(new_rows)}건 저장 (휴장일 등 {skipped}건 제외)")


def compute_gap(client, raw_indicator_id: str) -> tuple[str, float, float, float]:
    rows = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", raw_indicator_id)
        .order("date", desc=True)
        .execute()
    ).data
    if not rows:
        raise RuntimeError("52주 신고가를 계산할 종가 데이터가 없습니다")

    latest_date = rows[0]["date"]
    latest_close = float(rows[0]["raw_value"])
    fifty_two_week_high = max(float(r["raw_value"]) for r in rows)
    gap_pct = (latest_close - fifty_two_week_high) / fifty_two_week_high * 100
    return latest_date, latest_close, fifty_two_week_high, gap_pct


def main() -> None:
    client = get_client()

    raw_id = ensure_indicator(client, RAW_META)
    gap_id = ensure_indicator(client, GAP_META)
    print(f"[Supabase] indicator '{RAW_SLUG}' id: {raw_id}")
    print(f"[Supabase] indicator '{GAP_SLUG}' id: {gap_id}")

    backfill_raw_prices(client, raw_id)

    latest_date, latest_close, high, gap_pct = compute_gap(client, raw_id)
    print(
        f"[계산] 최근 종가 {latest_close} ({latest_date} 기준) / 52주 신고가 {high} "
        f"-> 괴리율 {gap_pct:.2f}%"
    )

    today = date.today().isoformat()
    rounded_gap = round(gap_pct, 2)
    client.table("indicator_values").upsert(
        {"indicator_id": gap_id, "date": today, "raw_value": rounded_gap},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={rounded_gap}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
