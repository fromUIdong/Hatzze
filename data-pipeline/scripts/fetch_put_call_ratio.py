"""KRX Open API(옵션 일별매매정보, drv/opt_bydd_trd)로 코스피200 옵션의
풋/콜 거래량 비율을 계산해 Supabase에 upsert.

풋/콜 비율 = 풋 거래량 / 콜 거래량. 1보다 작으면 콜(상승 베팅)이 우세해
시장이 낙관·탐욕 쪽으로 기울었다는 뜻이고, 1보다 크면 풋(하락 대비)이 우세하다.

**대상 상품:** 코스피200 계열만 본다(코스피200 옵션 + 위클리(목/월) + 미니).
코스닥150 옵션은 기초지수가 달라 제외한다 — 이 지표는 코스피 과열도를 읽는
용도이고, 실측상 코스닥150은 하루 거래량이 코스피200 계열의 0.2% 수준이라
포함해도 신호는 못 주면서 기초지수만 섞인다.

**야간 세션 포함:** ISU_NM에 "(야간)"이 붙은 종목은 별도 행으로 오는데 함께
더한다. 같은 상품의 실제 체결이고, 낮/밤을 나누면 그날 포지셔닝을 절반만
보게 된다.

응답의 ACC_TRDVOL(누적거래량)을 쓴다. 미체결약정(ACC_OPNINT_QTY)은 잔고라
'그날의 심리'를 보는 이 지표와 성격이 다르다.

카드(app/page.tsx CardPutCall)가 콜/풋 비중 막대를 그릴 수 있도록 details에
put_vol·call_vol 원본 거래량을 함께 저장한다.

최초 실행 시 최근 1년치를 백필하고, 이후 실행부터는 아직 없는 날짜만 채운다
(fetch_vkospi.py 와 동일한 방식).
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/drv/opt_bydd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05

# PROD_NM이 이 접두사로 시작하는 상품만 집계한다(코스피200 계열).
# 실응답 확인: "코스피200 옵션", "코스피200 위클리(목) 옵션",
#              "코스피200 위클리(월) 옵션", "미니코스피200 옵션".
KOSPI200_PROD_PREFIXES = ("코스피200", "미니코스피200")

INDICATOR_SLUG = "put_call_ratio"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "옵션 풋/콜 비율",
    "category": "시장",
    "description_beginner": (
        "콜(상승 베팅)이 풋(하락 대비)보다 많을수록, 다들 오를 거라 탐욕에 차 있다는 신호예요"
    ),
    "unit": "배",
}


def ensure_indicator(client) -> str:
    existing = client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    if existing.data:
        return existing.data[0]["id"]
    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def to_int(value) -> int:
    """KRX 수치 필드는 콤마가 섞인 문자열이고, 휴장·미체결이면 빈 문자열이다."""
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def fetch_volumes(bas_dd: str) -> tuple[int, int] | None:
    """(put_vol, call_vol). 휴장일 등 데이터가 없으면 None."""
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return None  # 네트워크 재시도 소진 — 이 날짜만 건너뜀
    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'옵션 일별매매정보/주식옵션外'(drv/opt_bydd_trd) 개별 서비스 API "
            "이용신청 및 승인 상태를 확인하세요."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    put_vol = call_vol = 0
    for r in records:
        if not str(r.get("PROD_NM", "")).startswith(KOSPI200_PROD_PREFIXES):
            continue
        vol = to_int(r.get("ACC_TRDVOL"))
        kind = r.get("RGHT_TP_NM")
        if kind == "PUT":
            put_vol += vol
        elif kind == "CALL":
            call_vol += vol

    # 콜 거래량이 0이면 비율이 무한대라 저장하지 않는다(휴장일·데이터 결손).
    if call_vol == 0:
        return None
    return put_vol, call_vol


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
        result = fetch_volumes(d.strftime("%Y%m%d"))
        if result is not None:
            put_vol, call_vol = result
            new_rows.append(
                {
                    "indicator_id": indicator_id,
                    "date": d.isoformat(),
                    "raw_value": round(put_vol / call_vol, 4),
                    "details": {"put_vol": put_vol, "call_vol": call_vol},
                }
            )
        time.sleep(REQUEST_DELAY_SEC)

    if new_rows:
        client.table("indicator_values").upsert(
            new_rows, on_conflict="indicator_id,date"
        ).execute()
        latest = new_rows[-1]
        print(
            f"[{INDICATOR_SLUG}] 최신 {latest['date']}: 풋 {latest['details']['put_vol']:,} / "
            f"콜 {latest['details']['call_vol']:,} -> {latest['raw_value']}"
        )
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
