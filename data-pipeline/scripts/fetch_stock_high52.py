"""KRX 일별매매정보를 52주치 훑어 종목별 '최고 종가'를 구해 stocks 에 저장.

**왜 필요한가.** 코스피 신고가 카드는 지수 괴리율(왼쪽)과 거래대금 상위 종목의 52주
고점 대비(오른쪽)를 나란히 놓는다. 그런데 왼쪽은 KRX 종가 기준인데 오른쪽만 야후
실시간이라 한 카드 안에서 잣대가 갈렸다 — 배지에 "7/22 기준"이라 적어도 오른쪽 숫자는
그 날짜의 값이 아니었고, 야후의 52주 고점은 **장중 고가** 기준이라 종가 기준인 지수 쪽보다
구조적으로 높게 나온다(실측 코스피 9,385 vs 9,114).

KRX 응답에는 52주 고점 필드가 없고 그날 OHLC 만 있다. 대신 한 번의 호출이 **그날 전
종목**을 주므로, 52주치 날짜를 훑으면 종목별 최고 종가를 직접 구할 수 있다. 종가 기준으로
잡아 지수 쪽(kospi_high_gap 이 kospi_close_raw 의 최고 종가를 쓰는 것)과 잣대를 맞춘다.

**호출량이 커서 매일 돌리지 않는다.** 52주 × 2개 시장 = 500회 안팎이라, stocks 의
high_52w_date 가 REFRESH_AFTER_DAYS 안에 갱신돼 있으면 그냥 넘어간다. 그 사이의 신고가는
'오늘 종가가 저장된 고점보다 높으면 갱신'으로 따라잡는다(고점은 위로만 움직이므로
이 증분 갱신은 항상 옳다). 반대로 옛 고점이 52주 창을 벗어나 **내려가야 하는** 경우는
증분으로 알 수 없어서, 주기적 전체 재계산이 그걸 바로잡는다.

실행:
    python scripts/fetch_stock_high52.py            # 필요할 때만 전체 재계산
    python scripts/fetch_stock_high52.py --force    # 무조건 전체 재계산
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.krx_client import krx_get  # noqa: E402
from common.supabase_client import get_client, load_all  # noqa: E402
from common.timeutil import business_days, today_kst  # noqa: E402

KOSPI_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
KOSDAQ_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd"
WINDOW_DAYS = 365
REQUEST_DELAY_SEC = 0.05
REFRESH_AFTER_DAYS = 30  # 이만큼 지나야 전체를 다시 훑는다(전체 훑기는 80분 걸린다)
BATCH = 500


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def fetch_day(url: str, bas_dd: str) -> list[dict]:
    resp = krx_get(url, bas_dd)
    if resp is None or resp.status_code != 200:
        return []
    return resp.json().get("OutBlock_1", [])


def sweep_high52(start: date, end: date) -> dict[str, tuple[int, str]]:
    """종목코드 → (최고 종가, 그 날짜). 52주치를 훑는다."""
    best: dict[str, tuple[int, str]] = {}
    days = list(business_days(start, end))
    print(f"[KRX] 52주 최고 종가 계산 — {len(days)}영업일 × 2개 시장 조회")

    for i, d in enumerate(days, 1):
        bas_dd = d.strftime("%Y%m%d")
        iso = d.isoformat()
        for url in (KOSPI_URL, KOSDAQ_URL):
            for row in fetch_day(url, bas_dd):
                code = (row.get("ISU_CD") or "").strip()
                close = _to_int(row.get("TDD_CLSPRC"))
                if not code or not close:
                    continue
                if code not in best or close > best[code][0]:
                    best[code] = (close, iso)
            time.sleep(REQUEST_DELAY_SEC)
        if i % 50 == 0:
            print(f"  ... {i}/{len(days)}일 · 종목 {len(best)}개")
    return best


def needs_refresh(client, today: date) -> bool:
    rows = (
        client.table("stocks")
        .select("high_52w_date")
        .not_.is_("high_52w_date", "null")
        .order("high_52w_date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return True
    last = date.fromisoformat(rows[0]["high_52w_date"])
    age = (today - last).days
    print(f"[stocks] 마지막 전체 재계산 {last} ({age}일 전)")
    return age >= REFRESH_AFTER_DAYS


def main() -> None:
    client = get_client()
    today = today_kst()
    force = "--force" in sys.argv

    try:
        stale = needs_refresh(client, today)
    except Exception as e:
        # high_52w_date 컬럼이 아직 없는 환경(마이그레이션 019 전)
        print(f"[SKIP] stocks.high_52w 컬럼을 읽지 못했습니다 — 마이그레이션 019를 먼저 실행하세요: {e}")
        return

    if not (force or stale):
        print("[stocks] 최근에 재계산돼 있어 건너뜁니다 (--force 로 강제 실행)")
        return

    best = sweep_high52(today - timedelta(days=WINDOW_DAYS), today)
    if not best:
        print("[오류] KRX에서 종가를 하나도 받지 못했습니다.")
        sys.exit(1)

    known = {s["code"] for s in load_all(client, "stocks", "code")}
    rows = [
        {"code": code, "high_52w": high, "high_52w_date": on}
        for code, (high, on) in best.items()
        if code in known  # stocks 에 없는 코드는 건너뜀(신규 상장은 fetch_krx_stocks 가 먼저 넣는다)
    ]
    for i in range(0, len(rows), BATCH):
        client.table("stocks").upsert(rows[i : i + BATCH], on_conflict="code").execute()

    top = sorted(best.items(), key=lambda kv: -kv[1][0])[:3]
    print(f"[Supabase] stocks.high_52w {len(rows)}종목 저장 (기준 {today})")
    for code, (high, on) in top:
        print(f"  {code}  최고 종가 {high:,}원 ({on})")
    print(f"[안내] 다음 전체 재계산은 {REFRESH_AFTER_DAYS}일 뒤입니다. "
          "그 사이 신고가는 fetch_krx_stocks.py 가 매일 갱신합니다.")


if __name__ == "__main__":
    main()
