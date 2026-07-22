"""KOSPI 전체 시가총액과 명목GDP로 버핏지수를 계산해 Supabase에 upsert.

- 코스피 시가총액: KRX Open API의 지수 시세 엔드포인트(fetch_kospi_high_gap.py와 동일)
  응답 중 IDX_NM="코스피" 레코드의 MKTCAP 필드를 그대로 사용한다. 시가총액 전용 엔드포인트를
  새로 찾지 않은 이유는, 이미 승인된 지수 시세 API 응답에 코스피 전체 시가총액이 그대로
  포함되어 있어 별도 서비스 승인 없이 바로 쓸 수 있기 때문이다.
- 명목GDP: ECOS StatisticSearch(통계표코드 200Y109, 항목코드 10601 = "국내총생산에 대한
  지출", 원계열/명목/분기)에서 최근 4개 분기 값을 합산해 연환산한다. 분기 GDP를 그대로
  쓰면 버핏지수가 약 4배로 부풀려지기 때문에 반드시 연환산이 필요하다.

ECOS(ecos.bok.or.kr)는 GitHub Actions 실행 환경에서 가끔 연결 자체가 타임아웃되는
경우가 있었다(코드 문제가 아니라 해외 클라우드 IP 접속이 느리거나 막히는 것으로
추정). 타임아웃/연결 실패에 한해 몇 초 간격으로 재시도하고, 그래도 안 되면
EcosUnavailableError로 명확히 구분해 오늘 하루 버핏지수 계산만 건너뛴다 — 다른
지표들의 파이프라인 실행을 막지 않는다. KRX 쪽도 같은 부류의 문제를 겪을 수 있다고
보고(2026-07-13, 매일 다른 스크립트가 번갈아 타임아웃으로 실패하는 걸 확인함)
common/krx_client.py의 공통 재시도 헬퍼(krx_get)로 동일하게 대응한다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.ecos_client import EcosUnavailableError, statistic_search  # noqa: E402
from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd"
TARGET_INDEX_NAME = "코스피"
MARKET_CAP_LOOKBACK_DAYS = 10  # 최근 거래일을 못 찾을 경우를 대비한 안전 범위

ECOS_STAT_CODE = "200Y109"  # 국내총생산에 대한 지출(원계열, 명목, 분기 및 연간)
ECOS_ITEM_CODE = "10601"  # 국내총생산에 대한 지출 (= GDP)
ECOS_CYCLE = "Q"
ECOS_TRAILING_QUARTERS = 4

# ECOS 호출·재시도·EcosUnavailableError 는 common/ecos_client.py 로 옮겼다
# (CCSI fetch 와 공유). 여기선 그걸 가져다 쓴다.

RAW_MKTCAP_SLUG = "kospi_market_cap_raw"
RAW_MKTCAP_META = {
    "slug": RAW_MKTCAP_SLUG,
    "name": "코스피 전체 시가총액 (내부용 원본)",
    "category": "시장",
    "description_beginner": "버핏지수 계산을 위해 내부적으로 저장하는 코스피 전체 시가총액 데이터입니다.",
    "unit": "원",
    "is_public": False,
}

BUFFETT_SLUG = "buffett_index"
BUFFETT_META = {
    "slug": BUFFETT_SLUG,
    "name": "버핏지수",
    "headline": "나라 경제 규모와 견준 증시 몸집",
    "category": "시장",
    # "100%가 정상"은 미국 옛 기준이라 코스피엔 안 맞는다 — 임계값 백테스트에서 나온
    # 실제 구간(floor 105% / ceiling 235%, config/indicator_thresholds.py)을 쓴다.
    "description_beginner": (
        "나라 경제 규모(GDP)에 비해 주식시장 몸집이 얼마나 커졌는지 봅니다. "
        "코스피는 100%대 초반이 평범하고, 230%를 넘으면 실물이 감당 못 할 거품을 의심하는 과열 구간입니다"
    ),
    "unit": "%",
}


def fetch_kospi_market_cap(bas_dd: str) -> float | None:
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

    value = record.get("MKTCAP")
    if value in (None, ""):
        return None  # 휴장일 등으로 값이 비어있는 경우
    return float(str(value).replace(",", ""))


def fetch_latest_market_cap() -> tuple[str, float]:
    day = date.today()
    for _ in range(MARKET_CAP_LOOKBACK_DAYS):
        market_cap = fetch_kospi_market_cap(day.strftime("%Y%m%d"))
        if market_cap is not None:
            return day.isoformat(), market_cap
        day -= timedelta(days=1)

    raise RuntimeError(
        f"최근 {MARKET_CAP_LOOKBACK_DAYS}일 내 코스피 시가총액 데이터를 찾지 못했습니다"
    )


def fetch_annualized_gdp() -> tuple[str, float]:
    end_year = date.today().year
    start_year = end_year - 3
    valid_rows = statistic_search(
        ECOS_STAT_CODE, ECOS_CYCLE, f"{start_year}Q1", f"{end_year}Q4", ECOS_ITEM_CODE
    )

    if len(valid_rows) < ECOS_TRAILING_QUARTERS:
        raise RuntimeError(
            f"연환산에 필요한 분기 데이터가 부족합니다 ({len(valid_rows)}개 확보)"
        )

    trailing = valid_rows[-ECOS_TRAILING_QUARTERS:]
    # UNIT_NAME은 "십억원" 기준이므로 1e9를 곱해 원 단위로 환산한다.
    annualized_gdp_krw = sum(float(r["DATA_VALUE"]) for r in trailing) * 1e9
    latest_quarter = trailing[-1]["TIME"]
    return latest_quarter, annualized_gdp_krw


def main() -> None:
    client = get_client()

    raw_id = ensure_indicator(client, RAW_MKTCAP_META)
    buffett_id = ensure_indicator(client, BUFFETT_META)
    print(f"[Supabase] indicator '{RAW_MKTCAP_SLUG}' id: {raw_id}")
    print(f"[Supabase] indicator '{BUFFETT_SLUG}' id: {buffett_id}")

    mktcap_date, market_cap_krw = fetch_latest_market_cap()
    print(f"[KRX] 코스피 전체 시가총액 ({mktcap_date} 기준): {market_cap_krw:,.0f}원")

    try:
        latest_quarter, annualized_gdp_krw = fetch_annualized_gdp()
    except EcosUnavailableError as e:
        print(f"[WARNING] {e}")
        print(
            "[WARNING] 코드 에러가 아니라 ECOS 서버 접속 문제로 판단해, 오늘 버핏지수 "
            "계산을 건너뜁니다. 다른 지표들은 영향받지 않고 계속 진행됩니다."
        )
        return

    print(
        f"[ECOS] 명목GDP 연환산 (최근 4개 분기, {latest_quarter} 기준 최신): "
        f"{annualized_gdp_krw:,.0f}원"
    )

    buffett_index = market_cap_krw / annualized_gdp_krw * 100
    print(f"[계산] 버핏지수 = 시가총액 / 연환산GDP x 100 = {buffett_index:.2f}%")

    today = date.today().isoformat()

    client.table("indicator_values").upsert(
        {"indicator_id": raw_id, "date": today, "raw_value": market_cap_krw},
        on_conflict="indicator_id,date",
    ).execute()

    # 카드가 GDP 실제 규모를 보여줄 수 있도록 세부값을 details(JSONB)에 저장한다.
    # 분기 문자열("2026Q1")은 연/분기 숫자로 쪼개 저장한다(details는 숫자 맵).
    try:
        gdp_year = int(latest_quarter[:4])
        gdp_q = int(latest_quarter.split("Q")[-1])
    except (ValueError, IndexError):
        gdp_year, gdp_q = 0, 0

    rounded_index = round(buffett_index, 2)
    client.table("indicator_values").upsert(
        {
            "indicator_id": buffett_id,
            "date": today,
            "raw_value": rounded_index,
            "details": {
                "gdp": round(annualized_gdp_krw, 0),
                "market_cap": round(market_cap_krw, 0),
                "gdp_year": gdp_year,
                "gdp_q": gdp_q,
                # 행의 date 는 '계산한 날'이지 '자료의 날'이 아니다. KRX가 최근
                # 영업일치를 아직 안 냈으면 며칠 전 시가총액으로 오늘 행을 쓰게 되고,
                # 그러면 화면상 최신값처럼 보인다. 실제 기준일을 함께 남겨 카드가
                # "기준 07-16"을 표시할 수 있게 한다(숫자 맵이라 YYYYMMDD 정수).
                "source_date": int(mktcap_date.replace("-", "")),
            },
        },
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={rounded_index}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
