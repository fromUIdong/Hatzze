"""KRX 유가증권 종목별 일별매매(sto/stk_bydd_trd)로 '거래대금 쏠림도'를 계산해 저장.

froth 논리: 거래대금이 소수 종목에 쏠릴수록 = 다들 같은 핫한 종목/테마만 쫓는다 = 과열.
raw_value = 상위 10종목 거래대금 / 전체 KOSPI 거래대금 × 100 (%).

기존 '시총 쏠림도'(top10_market_cap_concentration)는 급락장의 대형주 도피에도 켜져 방향이
모호했다. '거래대금 쏠림'은 '다들 같은 종목을 사고판다'는 행동을 직접 재서 froth에 더 맞다.
다만 KOSPI 거래대금은 구조적으로 삼성전자·SK하이닉스에 크게 쏠려 있어(상시 70%+), 절대
수준 threshold는 낡는다. 그래서 youtube·예탁금처럼 '최근 평균 대비 급증(surge_map)'으로
쏠림 '심화'를 과열로 본다 — 평균이면 상온, 평균보다 쏠림이 커지면 초고온.

범위: KOSPI만 본다. KOSDAQ 엔드포인트(ksq_bydd_trd)는 2026-07-20 승인돼 호출은 가능해졌지만,
과거값이 전부 KOSPI 기준이라 지표 시계열의 연속성을 깨지 않으려고 확장은 보류했다. 테마·잡주
쏠림은 KOSDAQ에서 더 잘 드러나므로, 확장한다면 기존 slug를 덮지 말고 별도 지표로 두거나
과거분을 재계산해야 한다.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
TOP_N = 10
BACKFILL_DAYS = 30  # 최근 30일(달력) 조회 — 휴장일은 빈 응답이라 건너뛴다
REQUEST_DELAY_SEC = 0.05
WON_PER_JO = 1_000_000_000_000

INDICATOR_SLUG = "turnover_concentration"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "거래대금 쏠림도",
    "category": "시장",
    "headline": "소수 종목에 다 몰릴 때",
    "description_beginner": "거래가 소수 인기 종목에 쏠릴수록, 다들 같은 핫한 종목만 쫓는다는 과열 신호일 수 있어요",
    "unit": "%",
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    return client.table("indicators").insert(INDICATOR_META).execute().data[0]["id"]


def _to_float(s: str) -> float:
    try:
        return float((s or "0").replace(",", ""))
    except ValueError:
        return 0.0


def fetch_concentration(bas_dd: str):
    """(top10_share%, details) 반환. 휴장/실패면 None."""
    resp = krx_get(KRX_URL, bas_dd)
    if resp is None:
        return None
    if resp.status_code == 401:
        raise PermissionError(
            "KRX sto/stk_bydd_trd가 401. data.krx.co.kr에서 '유가증권 일별매매정보' "
            "Open API 이용신청·승인을 확인하세요."
        )
    rows = resp.json().get("OutBlock_1", [])
    vals = sorted((_to_float(d.get("ACC_TRDVAL")) for d in rows), reverse=True)
    total = sum(vals)
    if total <= 0 or len(vals) < TOP_N:
        return None
    top_n_sum = sum(vals[:TOP_N])
    share = round(top_n_sum / total * 100, 2)
    # 카드용: 상위 5종목 이름·비중
    named = sorted(rows, key=lambda d: _to_float(d.get("ACC_TRDVAL")), reverse=True)
    top5 = [
        {"name": d["ISU_NM"], "share": round(_to_float(d.get("ACC_TRDVAL")) / total * 100, 1)}
        for d in named[:5]
    ]
    details = {"top10_share": share, "total_jo": round(total / WON_PER_JO, 1), "top5": top5}
    return share, details


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    saved = 0
    latest_line = None
    for offset in range(BACKFILL_DAYS):
        d = date.today() - timedelta(days=offset)
        if d.weekday() >= 5:  # 주말 skip
            continue
        bas_dd = d.strftime("%Y%m%d")
        result = fetch_concentration(bas_dd)
        if result is None:
            continue  # 휴장/데이터 없음
        share, details = result
        client.table("indicator_values").upsert(
            {"indicator_id": indicator_id, "date": d.isoformat(), "raw_value": share, "details": details},
            on_conflict="indicator_id,date",
        ).execute()
        saved += 1
        if latest_line is None:
            latest_line = f"{d.isoformat()} 상위10 거래대금 비중 {share}% (총 {details['total_jo']}조, 1위 {details['top5'][0]['name']} {details['top5'][0]['share']}%)"
    print(f"[KRX] 거래대금 쏠림 {saved}일치 저장. 최신: {latest_line}")


if __name__ == "__main__":
    main()
