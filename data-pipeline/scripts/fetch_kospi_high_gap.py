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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402
from common.timeutil import days_to_backfill  # noqa: E402

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
    "category": "시장",
    "description_beginner": "52주 신고가 대비 괴리율 계산을 위해 내부적으로 저장하는 코스피 지수 종가 데이터입니다.",
    "unit": "pt",
    "is_public": False,
}

GAP_SLUG = "kospi_high_gap"
GAP_META = {
    "slug": GAP_SLUG,
    "name": "코스피 신고가 대비 괴리율",
    "headline": "현재 지수와 52주 신고가 사이의 거리",
    "category": "시장",
    # 카드가 2칸으로 넓어져 설명 자리가 늘었다 — 기존 39자를 70자 안팎으로 늘려
    # "왜 이 숫자가 과열 신호인지"까지 한 문장 더 담는다.
    "description_beginner": (
        "코스피가 최근 1년 최고점에서 얼마나 떨어져 있는지를 보여줍니다. "
        "0%에 가까울수록 신고가를 새로 쓰는 중이라 기대가 몰리기 쉽고, "
        "그만큼 더 오를 자리가 남았나 싶은 부담도 커지는 구간입니다"
    ),
    "unit": "%",
}


def fetch_close_price(bas_dd: str) -> float | None:
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

    # 옛 공휴일을 매 실행 다시 물어보지 않도록 최근 창만 훑는다(common/timeutil 참고).
    missing_days = days_to_backfill(existing_dates, today, bootstrap_days=BACKFILL_DAYS)
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
    # 지표 이름 그대로 '52주' 창으로 자른다. 예전엔 날짜 필터가 없어 저장된 종가 전부에서
    # 전고점을 잡았는데, 백필이 옛 행을 지우지 않아 표가 계속 자라므로 실제로는 '전체 기간
    # 최고가'였다(이미 365일 밖 행이 9개 있었다). 지금은 최고점이 1년 안이라 값이 우연히
    # 같지만, 고점이 1년보다 오래되는 순간 "52주 괴리율"이 조용히 틀려진다.
    window_start = (date.today() - timedelta(days=BACKFILL_DAYS)).isoformat()
    rows = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", raw_indicator_id)
        .gte("date", window_start)
        .order("date", desc=True)
        .execute()
    ).data
    if not rows:
        raise RuntimeError("52주 신고가를 계산할 종가 데이터가 없습니다")

    latest_date = rows[0]["date"]
    latest_close = float(rows[0]["raw_value"])
    # 오늘(rows[0])을 제외한 전고점. 오늘 종가가 이걸 넘으면 '신고가'라 gap이 양수(+X%)로
    # 나와 화면에 "이전 전고점 대비 +X%"를 표시할 수 있다. 넘지 못하면 음수(-X%, 전고점
    # 아래). 오늘을 포함해 max를 잡으면 신고가 날에도 gap이 0에 캡돼 초과분이 안 보인다.
    prior_high = max((float(r["raw_value"]) for r in rows[1:]), default=latest_close)
    gap_pct = (latest_close - prior_high) / prior_high * 100
    return latest_date, latest_close, prior_high, gap_pct


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
        {
            "indicator_id": gap_id,
            "date": today,
            "raw_value": rounded_gap,
            # 행의 date 는 '계산한 날'이지 '자료의 날'이 아니다. KRX가 최근 영업일치를
            # 아직 안 냈으면 며칠 전 종가로 오늘 행을 써서 화면상 최신값처럼 보인다.
            # 실제 종가 기준일을 남겨 카드가 "기준 07-16"을 표시할 수 있게 한다
            # (details 는 숫자 맵이라 YYYYMMDD 정수로 넣는다).
            "details": {"source_date": int(latest_date.replace("-", ""))},
        },
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={rounded_gap}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
