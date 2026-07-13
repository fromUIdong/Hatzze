"""KRX Open API 두 엔드포인트로 "레버리지 ETF·선물 미결제약정 종합 지수"
(레버리지 ETF 거래대금 + 코스피200 선물 미결제약정 복합 지표)를 계산해
Supabase에 upsert.

원래 leverage_etf_volume은 KODEX 레버리지 ETF 거래대금(억원) 하나만 저장했는데,
여기에 코스피200 선물 미결제약정(open interest) 급증도를 더해 "레버리지·선물
양쪽에서 베팅이 얼마나 뜨겁고 오래가는지"를 종합하는 지표로 확장했다. slug와
weight는 그대로 유지한다 — 이 프로젝트는 percentile→고정 기준값 전환, 업비트
지수의 기하평균→가중산술평균 전환처럼 지표의 계산 방식이 바뀔 때마다 slug를
유지해온 전례를 따른 것이다. 새 slug를 만들면 기존 daily_score 이력과의 연결이
끊기고, weight도 처음부터 다시 정해야 한다.

- ETF 거래대금(억원)과 선물 미결제약정(계약수)은 각각 내부용 원본 캐시
  indicator(leverage_etf_trade_value_raw, kospi200_futures_oi_raw,
  is_public=false)에 그대로 쌓는다 — kospi_close_raw와 동일한 패턴. 둘 다 KRX
  API가 날짜 범위 조회를 지원하지 않고 하루 단위로만 조회 가능해서, 매일 새로
  전체를 훑지 않도록 각각 독립적으로 diff 기반 백필을 유지한다. (기존
  leverage_etf_volume에 이미 쌓여 있던 ETF 거래대금 244일치는 재수집하지 않고
  leverage_etf_trade_value_raw로 그대로 옮겨 재사용했다.)
- ETF거래대금_progress = ETF 거래대금 / 40000(억원, 4조원) × 100 (기존 leverage_etf_volume
  기준값 그대로)
- 미결제약정_progress = (오늘 미결제약정 / 최근 1년 평균 미결제약정 × 100) / 150 × 100
  — "최근 1년 평균 대비 150%"를 완전히 달아오른 수준으로 본다. 미결제약정은
  만기 롤오버 등으로 원래도 변동이 크고, 개별 계약월이 아니라 코스피200 선물
  전체 계약월 합계를 쓰기 때문에 절대 수치보다 평균 대비 상대적 급증 여부로
  보는 게 더 안정적이다.
- 종합 raw_value = ETF거래대금_progress × 0.5 + 미결제약정_progress × 0.5
  (업비트 지수와 동일한 가중 산술평균 — 한쪽이 0이어도 나머지 절반은 반영됨)
  이 raw_value는 이미 0~100대 진행률에 가까운 값이라 calculate_score.py에서
  threshold=100로 나누는 건 사실상 그대로 통과시키는 것에 가깝다. unit도
  "억원"에서 다른 복합 지수들과 동일한 "pt"로 바뀐다.
- 매 실행마다 두 원본 캐시에 공통으로 존재하는 날짜 전체를 다시 계산해
  upsert한다(diff 아님) — 공식이 바뀔 수 있는 파생값이라 fetch_upbit_speculation.py와
  같은 이유다. 다만 이 재계산은 이미 Supabase에 쌓인 원본 캐시를 읽기만 하므로
  KRX API를 다시 호출하지 않아 비용이 들지 않는다.

선물 미결제약정 엔드포인트(drv/fut_bydd_trd, "선물 일별매매정보(주식선물外)")는
처음 작성할 때(승인 대기 중이던 시점) ISU_NM 매칭 키워드를 "코스피 200 선물",
미결제약정 필드명을 OPNINT_QTY로 추정해뒀었는데, 승인 후 실제 응답을 확인해보니
(2026-07-13) 둘 다 틀렸다 — 실제로는 종목명이 "코스피200 F 202609 (주간)"처럼
공백 없이 "코스피200 F"로 시작하고(계약월별로 여러 건, 주/야간 구분도 있음),
필드명은 ACC_OPNINT_QTY다. 이 불일치 때문에 API가 승인된 뒤에도 매 실행마다
"코스피200 선물" 레코드를 하나도 못 찾아 kospi200_futures_oi_raw가 계속
비어있었다(재시도 실패가 아니라 이름 불일치로 인한 매칭 실패였음 — 로그에는
에러 없이 그냥 "0건 저장"으로만 나와서 발견이 늦었다). 지금은 고쳤으니 정상
동작해야 하지만, 401이 다시 나면(승인이 풀리는 등) 여전히 그 사실을 로그로
남기고 원본 캐시 백필만 건너뛴 채 나머지는 계속 진행한다(ETF 쪽은 별개로
정상 동작).
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

ETF_URL = "http://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
FUTURES_URL = "http://data-dbg.krx.co.kr/svc/apis/drv/fut_bydd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
WON_PER_EOK = 100_000_000  # 1억원 = 1e8원

TRADING_VALUE_KEY = "ACC_TRDVAL"
ISU_CODE_KEY = "ISU_CD"
TARGET_ISU_CODE = "122630"  # KODEX 레버리지

# 실제 응답으로 검증 완료(2026-07-13). "코스피200 F "(공백 없음, "F"=선물)로
# 시작하는 종목만 매칭 — 뒤에 계약월/주야간 구분이 붙는다(예: "코스피200 F
# 202609 (주간)"). 접두 공백 없이 매칭하면 "코스피200 SP ..."(캘린더 스프레드)나
# "미니코스피 F ..."(미니선물, 별개 상품)까지 잘못 포함되므로 주의.
KOSPI200_FUTURES_NAME_KEYWORD = "코스피200 F "
OPEN_INTEREST_KEY = "ACC_OPNINT_QTY"

ETF_THRESHOLD = 40_000.0  # 억원 (4조원) — 기존 leverage_etf_volume 기준값
OI_SURGE_THRESHOLD = 150.0  # 최근 1년 평균 대비 %, "완전히 달아오름" 기준

ETF_RAW_SLUG = "leverage_etf_trade_value_raw"
ETF_RAW_META = {
    "slug": ETF_RAW_SLUG,
    "name": "레버리지 ETF 거래대금 (내부용 원본)",
    "category": "정통",
    "description_beginner": "레버리지 ETF·선물 미결제약정 종합 지수 계산을 위해 내부적으로 저장하는 KODEX 레버리지 ETF 거래대금 데이터예요.",
    "unit": "억원",
    "is_public": False,
}

OI_RAW_SLUG = "kospi200_futures_oi_raw"
OI_RAW_META = {
    "slug": OI_RAW_SLUG,
    "name": "코스피200 선물 미결제약정 (내부용 원본)",
    "category": "정통",
    "description_beginner": "레버리지 ETF·선물 미결제약정 종합 지수 계산을 위해 내부적으로 저장하는 코스피200 선물 미결제약정 데이터예요.",
    "unit": "계약",
    "is_public": False,
}

COMPOSITE_SLUG = "leverage_etf_volume"
COMPOSITE_META = {
    "slug": COMPOSITE_SLUG,
    "name": "레버리지 ETF·선물 미결제약정 종합 지수",
    "category": "정통",
    "description_beginner": "레버리지 상품 거래와 선물 미결제약정을 같이 보면, 개인들이 얼마나 공격적으로, 그리고 얼마나 오래 베팅을 이어가고 있는지 알 수 있어요",
    "unit": "pt",
}


def ensure_indicator(client, meta: dict) -> str:
    slug = meta["slug"]
    existing = client.table("indicators").select("id").eq("slug", slug).execute()
    if existing.data:
        indicator_id = existing.data[0]["id"]
        client.table("indicators").update(
            {k: v for k, v in meta.items() if k != "slug"}
        ).eq("id", indicator_id).execute()
        return indicator_id

    inserted = client.table("indicators").insert(meta).execute()
    return inserted.data[0]["id"]


def business_days(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon ... 4=Fri
            yield current
        current += timedelta(days=1)


def get_existing_dates(client, indicator_id: str, start: date) -> set[str]:
    result = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"] for row in result.data}


def get_values(client, indicator_id: str, start: date) -> dict[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start.isoformat())
        .execute()
    )
    return {row["date"]: float(row["raw_value"]) for row in result.data}


def fetch_leverage_etf_trading_value(bas_dd: str) -> float | None:
    resp = krx_get(ETF_URL, bas_dd)
    if resp is None:
        return None

    if resp.status_code == 401:
        raise PermissionError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'ETF 시세정보'(etp/etf_bydd_trd) 개별 서비스 API 이용신청 및 승인이 "
            "됐는지 확인하세요."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    record = next(
        (r for r in records if TARGET_ISU_CODE in (r.get(ISU_CODE_KEY) or "")),
        None,
    )
    if record is None:
        return None

    value = record.get(TRADING_VALUE_KEY)
    if value in (None, ""):
        return None  # 휴장일 등으로 값이 비어있는 경우
    won = float(str(value).replace(",", ""))
    return won / WON_PER_EOK


class FuturesApprovalPendingError(Exception):
    """선물 일별매매정보 API가 아직 승인되지 않았을 때 발생."""


def fetch_kospi200_futures_oi(bas_dd: str) -> float | None:
    resp = krx_get(FUTURES_URL, bas_dd)
    if resp is None:
        return None

    if resp.status_code == 401:
        raise FuturesApprovalPendingError(
            "KRX API가 401을 반환했습니다. data.krx.co.kr(정보데이터시스템)에서 "
            "'선물 일별매매정보(주식선물外)'(drv/fut_bydd_trd) 개별 서비스 API "
            "이용신청 및 승인이 됐는지 확인하세요."
        )
    resp.raise_for_status()

    records = resp.json().get("OutBlock_1", [])
    kospi200_records = [
        r for r in records if KOSPI200_FUTURES_NAME_KEYWORD in (r.get("ISU_NM") or "")
    ]
    if not kospi200_records:
        return None

    total_oi = 0.0
    for r in kospi200_records:
        value = r.get(OPEN_INTEREST_KEY)
        if value in (None, ""):
            continue
        total_oi += float(str(value).replace(",", ""))
    return total_oi if total_oi > 0 else None


def backfill_daily(client, indicator_id: str, fetch_fn, label: str) -> None:
    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    existing_dates = get_existing_dates(client, indicator_id, start)
    missing_days = [
        d for d in business_days(start, today) if d.isoformat() not in existing_dates
    ]
    if not missing_days:
        print(f"[{label}] 백필할 신규 날짜 없음 (이미 최신 상태)")
        return

    print(f"[{label}] 백필 대상 {len(missing_days)}일 조회 시작")
    rows = []
    for d in missing_days:
        value = fetch_fn(d.strftime("%Y%m%d"))
        if value is not None:
            rows.append(
                {"indicator_id": indicator_id, "date": d.isoformat(), "raw_value": value}
            )
        time.sleep(REQUEST_DELAY_SEC)

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    skipped = len(missing_days) - len(rows)
    print(f"[{label}] 백필 완료: {len(rows)}건 저장 ({skipped}건 제외)")


def main() -> None:
    client = get_client()

    etf_raw_id = ensure_indicator(client, ETF_RAW_META)
    oi_raw_id = ensure_indicator(client, OI_RAW_META)
    composite_id = ensure_indicator(client, COMPOSITE_META)
    print(f"[Supabase] indicator '{ETF_RAW_SLUG}' id: {etf_raw_id}")
    print(f"[Supabase] indicator '{OI_RAW_SLUG}' id: {oi_raw_id}")
    print(f"[Supabase] indicator '{COMPOSITE_SLUG}' id: {composite_id}")

    backfill_daily(client, etf_raw_id, fetch_leverage_etf_trading_value, "ETF거래대금")

    try:
        backfill_daily(client, oi_raw_id, fetch_kospi200_futures_oi, "선물미결제약정")
    except FuturesApprovalPendingError as e:
        print(f"[WARNING] 선물 미결제약정 백필을 건너뜁니다: {e}")

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    etf_values = get_values(client, etf_raw_id, start)
    oi_values = get_values(client, oi_raw_id, start)
    print(
        f"[종합 지수] ETF 거래대금 {len(etf_values)}건, 선물 미결제약정 {len(oi_values)}건 보유"
    )

    if not oi_values:
        print(
            "[종합 지수] 선물 미결제약정 데이터가 아직 없어 종합 지수를 계산할 수 "
            "없습니다 (승인 대기 중이면 승인 후 재실행하세요). 기존 값을 그대로 둡니다."
        )
        return

    oi_avg = sum(oi_values.values()) / len(oi_values)

    common_dates = sorted(set(etf_values) & set(oi_values))
    if not common_dates:
        print("[종합 지수] ETF·선물 공통 날짜가 없어 종합 지수를 계산할 수 없습니다")
        return

    def composite_for(d: str) -> tuple[float, float, float]:
        etf_progress = etf_values[d] / ETF_THRESHOLD * 100
        oi_surge_pct = oi_values[d] / oi_avg * 100
        oi_progress = oi_surge_pct / OI_SURGE_THRESHOLD * 100
        composite = etf_progress * 0.5 + oi_progress * 0.5
        return etf_progress, oi_progress, composite

    # 카드의 범위 바가 "역대 최저 ↔ 역대 최고" 사이에서 '지금' 위치를 정확히
    # 찍을 수 있도록, 보유 구간의 종합 지수 최소/최대를 미리 구해 details에 함께 넣는다.
    comp_by_date = {d: composite_for(d) for d in common_dates}
    all_composites = [v[2] for v in comp_by_date.values()]
    hist_min = round(min(all_composites), 2)
    hist_max = round(max(all_composites), 2)

    def row_for(d: str) -> dict:
        etf_progress, oi_progress, composite = comp_by_date[d]
        return {
            "indicator_id": composite_id,
            "date": d,
            "raw_value": round(composite, 2),
            # 카드가 목업 원본대로 ETF 거래대금 / 선물 미결제약정 두 서브바를 그리고,
            # 범위 바에 역대 최저/최고 대비 현재 위치를 찍을 수 있도록 details에 저장.
            "details": {
                "etf_progress": round(etf_progress, 1),
                "futures_progress": round(oi_progress, 1),
                "hist_min": hist_min,
                "hist_max": hist_max,
            },
        }

    rows = [row_for(d) for d in common_dates]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_date = common_dates[-1]
    etf_progress, oi_progress, composite = composite_for(latest_date)
    print(
        f"[종합 지수] 최신값 ({latest_date} 기준): "
        f"ETF 거래대금 {etf_values[latest_date]:.1f}억원(진행률 {etf_progress:.1f}%), "
        f"선물 미결제약정 {oi_values[latest_date]:,.0f}계약"
        f"(1년 평균 대비 {oi_values[latest_date] / oi_avg * 100:.1f}%, 진행률 {oi_progress:.1f}%), "
        f"종합 지수 {composite:.2f}pt"
    )


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
