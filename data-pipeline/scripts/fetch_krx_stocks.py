"""KOSPI/KOSDAQ 상장종목 마스터(코드↔종목명)를 KRX에서 받아 stocks 테이블에 upsert.

카더라 리포트의 종목추출 사전 base다. KRX 일별 시세 엔드포인트
(stk_bydd_trd/ksq_bydd_trd)는 그날 전 종목의 ISU_CD·ISU_NM·MKT_NM 을 주므로,
최신 가용 거래일 하나를 받으면 그게 곧 상장종목 목록이 된다. KRX 데이터는 며칠
지연될 수 있어(오늘·어제는 빌 수 있음) 최신 가용일을 과거로 훑어 찾는다.

신규 상장을 반영하도록 주기적으로(예: 매일 배치) 돌려도 되고, 델리스팅된 종목은
굳이 지우지 않는다(과거 언급과의 연결 보존).

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/fetch_krx_stocks.py
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.timeutil import today_kst  # noqa: E402

KOSPI_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
KOSDAQ_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd"
MAX_LOOKBACK_DAYS = 10  # 최신 가용 거래일을 찾기 위해 과거로 훑는 최대 일수


def _to_int(value) -> int | None:
    """KRX 숫자 문자열('12,345')을 int로. 빈 값/파싱 실패는 None."""
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_rows(url: str, bas_dd: str) -> list[dict]:
    resp = krx_get(url, bas_dd)
    if resp is None:
        return []
    if resp.status_code != 200:
        # 401(미승인 시리즈) 등은 조용히 빈 목록으로 넘기지 말고 드러낸다.
        print(f"[경고] {url.rsplit('/', 1)[-1]} {bas_dd}: HTTP {resp.status_code} {resp.text[:120]}")
        return []
    return resp.json().get("OutBlock_1", [])


def latest_available_date() -> str | None:
    """오늘(KST)부터 과거로 훑어 KOSPI 데이터가 있는 첫 basDd(YYYYMMDD)를 찾는다."""
    day = today_kst()
    for _ in range(MAX_LOOKBACK_DAYS):
        bas_dd = day.strftime("%Y%m%d")
        if fetch_rows(KOSPI_URL, bas_dd):
            return bas_dd
        day -= timedelta(days=1)
    return None


def main() -> None:
    bas_dd = latest_available_date()
    if not bas_dd:
        print(f"[오류] 최근 {MAX_LOOKBACK_DAYS}일 내 KRX 데이터를 찾지 못했습니다.")
        sys.exit(1)

    stocks: dict[str, dict] = {}
    for url in (KOSPI_URL, KOSDAQ_URL):
        for d in fetch_rows(url, bas_dd):
            code = (d.get("ISU_CD") or "").strip()
            name = (d.get("ISU_NM") or "").strip()
            if not code or not name:
                continue
            stocks[code] = {
                "code": code,
                "name": name,
                "market": (d.get("MKT_NM") or "").strip() or None,
                "sect_type": (d.get("SECT_TP_NM") or "").strip() or None,
                # 종가·등락률도 같은 응답에 있어 추가 호출 없이 저장한다(급부상 카드 표시용).
                "close_price": _to_int(d.get("TDD_CLSPRC")),
                "change_rate": _to_float(d.get("FLUC_RT")),
                "price_date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}",
            }

    if not stocks:
        print(f"[오류] {bas_dd} 종목이 0개입니다. 중단합니다.")
        sys.exit(1)

    rows = list(stocks.values())
    db = get_client()
    db.table("stocks").upsert(rows, on_conflict="code").execute()

    by_mkt: dict[str, int] = {}
    for r in rows:
        by_mkt[r["market"] or "기타"] = by_mkt.get(r["market"] or "기타", 0) + 1
    print(f"[Supabase] stocks upsert 완료: {len(rows)}개 (기준일 {bas_dd})")
    for mkt, n in sorted(by_mkt.items()):
        print(f"  {mkt}: {n}개")


if __name__ == "__main__":
    main()
