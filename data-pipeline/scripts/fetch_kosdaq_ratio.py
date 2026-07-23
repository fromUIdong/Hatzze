"""KRX Open API(코스닥 지수 시세, idx/kosdaq_dd_trd)로 코스닥 종가를 받아
"코스피 대비 코스닥 상대강도"(코스닥 20거래일 수익률 − 코스피 20거래일 수익률)를
계산해 Supabase에 upsert.

**2026-07-23 측정 방식 교체.** 예전엔 raw_value가 코스닥 종가 ÷ 코스피 종가, 즉 두 지수의
'레벨 비율'이었다. 그런데 코스피(1980=100)와 코스닥(1996=1000)은 기준일이 달라 이 비율의
절대 크기 자체엔 의미가 없고, 더 큰 문제는 **한쪽 지수가 오르면 다른 쪽이 그대로여도 비율이
움직인다**는 점이다. 실제로 1년간 코스피가 +113.5%, 코스닥이 -5.8%였고 비율은
0.2506 → 0.1105 로 반토막 났다 — 코스닥이 투기적으로 식어서가 아니라 코스피가 두 배가 된
결과다. 시간과의 상관계수가 -0.928(평균회귀 없는 순수 추세)이라 고정 눈금을 어디에 두든
"코스닥이 유독 앞서가나"가 아니라 "두 지수가 기준일 이후 얼마나 벌어졌나"를 재게 된다.
그 결과 1년의 85%가 과열도 100 에 붙어 정보를 못 냈다.

지표 설명("코스닥이 유독 앞서가면 투기성 자금이…")이 원래 묻고 싶은 건 **상대 모멘텀**이라,
fetch_asia_relative_strength.py와 똑같은 방식(20거래일 초과수익률)으로 바꾼다. 레벨이 아니라
수익률 차이라 기준일 문제도, 장기 드리프트도 사라진다.

코스닥 종가는 kospi_close_raw 와 같은 층의 내부용 지표(kosdaq_close_raw, is_public=false)에
쌓아 두고, 상대강도는 매 실행마다 계산 가능한 날짜 전체를 다시 계산해 upsert한다 — 공식이
바뀔 수 있는 파생값이라 "이미 있는 날짜는 건너뛰기" 방식이면 과거 값이 낡은 채로 남는다
(fetch_upbit_speculation.py와 같은 이유).

kospi_dd_trd(지수 시세)와는 별개로 개별 서비스 이용신청이 필요할 수 있다. 401이
나면 KRX 정보데이터시스템에서 '코스닥 시리즈 일별시세정보' 서비스를 신청/승인받아야 한다.
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
# kospi_dd_trd처럼 여러 계열 지수(코스닥, 코스닥 150 등)가 함께 내려온다.
TARGET_INDEX_NAME = "코스닥"
RETURN_WINDOW = 20  # 상대강도를 재는 거래일 수 — 아시아 상대강도와 동일하게 맞춘다

KOSPI_RAW_SLUG = "kospi_close_raw"

RAW_SLUG = "kosdaq_close_raw"
RAW_META = {
    "slug": RAW_SLUG,
    "name": "코스닥 지수 종가 (내부용 원본)",
    "category": "시장",
    "description_beginner": "상대강도 계산에 쓰는 원본 데이터입니다",
    "unit": "pt",
    "is_public": False,
}

INDICATOR_SLUG = "kosdaq_kospi_ratio"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "코스피 대비 코스닥 상대강도",
    "headline": "코스피와 견준 코스닥 강도",
    "category": "시장",
    "description_beginner": "최근 한 달 코스닥이 코스피보다 얼마나 더 올랐는지 봅니다. 코스닥이 유독 앞서가면 투기성 자금이 위험을 무릅쓰고 몰리고 있다는 신호일 수 있습니다",
    "unit": "%p",
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


def backfill_kosdaq_closes(client, raw_indicator_id: str) -> None:
    """아직 없는 영업일의 코스닥 종가만 받아 채운다(kospi_close_raw와 같은 패턴)."""
    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    existing = set(get_indicator_values(client, raw_indicator_id, start))

    missing_days = [
        d for d in business_days(start, today) if d.isoformat() not in existing
    ]
    if not missing_days:
        print("[KRX] 코스닥 종가 백필할 신규 날짜 없음 (이미 최신 상태)")
        return

    print(f"[KRX] 코스닥 종가 백필 대상 {len(missing_days)}일 조회 시작")
    rows = []
    for d in missing_days:
        close = fetch_kosdaq_close(d.strftime("%Y%m%d"))
        if close is not None:
            rows.append(
                {"indicator_id": raw_indicator_id, "date": d.isoformat(), "raw_value": close}
            )
        time.sleep(REQUEST_DELAY_SEC)

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    print(f"[KRX] 백필 완료: {len(rows)}건 저장 (휴장일 등 {len(missing_days) - len(rows)}건 제외)")


def compute_20d_return(prices: dict[str, float]) -> dict[str, float]:
    """날짜순 정렬 기준 자기 자신의 20번째 이전 거래일 대비 수익률(%)."""
    dates = sorted(prices)
    return {
        dates[i]: (prices[dates[i]] / prices[dates[i - RETURN_WINDOW]] - 1) * 100
        for i in range(RETURN_WINDOW, len(dates))
    }


def main() -> None:
    client = get_client()
    raw_id = ensure_indicator(client, RAW_META)
    indicator_id = ensure_indicator(client, INDICATOR_META)
    kospi_raw_id = get_indicator_id(client, KOSPI_RAW_SLUG)
    print(f"[Supabase] indicator '{RAW_SLUG}' id: {raw_id}")
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    backfill_kosdaq_closes(client, raw_id)

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    kospi_prices = get_indicator_values(client, kospi_raw_id, start)
    kosdaq_prices = get_indicator_values(client, raw_id, start)
    print(f"[Supabase] 코스피 종가 {len(kospi_prices)}건 · 코스닥 종가 {len(kosdaq_prices)}건 조회")

    kospi_returns = compute_20d_return(kospi_prices)
    kosdaq_returns = compute_20d_return(kosdaq_prices)
    common_dates = sorted(set(kospi_returns) & set(kosdaq_returns))
    if not common_dates:
        print(f"[{INDICATOR_SLUG}] 두 시계열의 공통 날짜가 없어 계산할 수 없습니다")
        return

    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(kosdaq_returns[d] - kospi_returns[d], 2),
            # 카드가 두 수익률을 나란히 보여줄 수 있게 세부값도 남긴다.
            "details": {
                "kosdaq_return": round(kosdaq_returns[d], 2),
                "kospi_return": round(kospi_returns[d], 2),
            },
        }
        for d in common_dates
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (전량 재계산)")

    last = common_dates[-1]
    print(
        f"[{INDICATOR_SLUG}] 최신값 ({last} 기준): "
        f"코스닥 {RETURN_WINDOW}일 수익률 {kosdaq_returns[last]:.2f}%, "
        f"코스피 {kospi_returns[last]:.2f}% "
        f"-> 초과 수익률 {kosdaq_returns[last] - kospi_returns[last]:.2f}%p"
    )


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
