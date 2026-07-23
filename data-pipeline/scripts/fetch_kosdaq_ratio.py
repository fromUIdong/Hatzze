"""KRX Open API(코스닥 지수 시세, idx/kosdaq_dd_trd)로 코스닥 종가를 받아
"코스닥 신고가 대비 괴리율"(코스닥 종가 vs 자기 52주 전고점)을 계산해 Supabase에 upsert.

**2026-07-23 측정 방식 두 번째 교체.** 이 지표는 한 해에 두 번 갈아엎었다.
1) 원래는 코스닥 종가 ÷ 코스피 종가, 즉 두 지수의 '레벨 비율'이었다. 코스피(1980=100)와
   코스닥(1996=1000)은 기준일이 달라 비율의 절대 크기에 의미가 없고, 한쪽이 오르면 다른
   쪽이 그대로여도 값이 움직였다. 시간과의 상관이 -0.928인 순수 추세라 1년의 85%가 과열도
   100에 붙었다.
2) 그래서 '코스피 대비 20거래일 초과수익률'로 바꿨는데, 1년 백테스트에서 **froth와 정확히
   반대로 도는 것**이 드러났다(docs/indicator-audit-2026-07-23.md §3-3). 이번 상승장이
   대형주 주도였던 탓에 코스닥 초과수익 중앙값이 2026-05 -24.9%p, 06 -27.7%p로 **최고점
   근처에서 최악**이었고 폭락기에 -3.8%p로 회복했다. 전고점 괴리와의 순위상관 -0.224,
   고점창-저점창 스프레드 -35.0 으로 25개 지표 중 최악이었다 — 폭락 바닥에서 이 지표
   혼자 과열도 85.2를 찍었다.

**원인은 눈금이 아니라 측정 대상이었다.** "코스닥이 코스피보다 잘 갔나"는 대형주 장세에서
froth와 무관하다. 지표 설명이 원래 묻고 싶은 건 "잡주에 투기적 자금이 몰렸나"이므로,
코스피와 견주는 대신 **코스닥 자체가 신고가를 쓰고 있나**를 본다(kospi_high_gap과 같은 방식).
교체 후 전고점 괴리와의 상관이 -0.224 → **+0.678** 로 부호가 뒤집혔고, 가중치를 깎지 않고
2.0을 그대로 쓸 수 있게 됐다.

※ slug 는 `kosdaq_kospi_ratio` 그대로 둔다. 측정이 두 번 바뀌는 동안 이름이 실제 계산과
   어긋나 있지만, slug 를 바꾸면 지표 행이 새로 생기면서 1년치 히스토리·가중치 설정·
   프론트 참조가 전부 끊긴다. 화면에 보이는 name/description 만 실제 계산에 맞춘다.

코스닥 종가는 kospi_close_raw 와 같은 층의 내부용 지표(kosdaq_close_raw, is_public=false)에
쌓아 두고, 괴리율은 매 실행마다 계산 가능한 날짜 전체를 다시 계산해 upsert한다 — 공식이
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
from common.timeutil import days_to_backfill  # noqa: E402

KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kosdaq_dd_trd"
BACKFILL_DAYS = 365
REQUEST_DELAY_SEC = 0.05
CLOSE_PRICE_KEY = "CLSPRC_IDX"
# kospi_dd_trd처럼 여러 계열 지수(코스닥, 코스닥 150 등)가 함께 내려온다.
TARGET_INDEX_NAME = "코스닥"
HIGH_WINDOW_DAYS = 365  # 전고점을 잡는 창(52주) — kospi_high_gap 과 동일

RAW_SLUG = "kosdaq_close_raw"
RAW_META = {
    "slug": RAW_SLUG,
    "name": "코스닥 지수 종가 (내부용 원본)",
    "category": "시장",
    "description_beginner": "신고가 대비 괴리율 계산에 쓰는 원본 데이터입니다",
    "unit": "pt",
    "is_public": False,
}

INDICATOR_SLUG = "kosdaq_kospi_ratio"  # 이름은 옛 측정 방식의 잔재 — 위 docstring 참고
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "코스닥 신고가 대비 괴리율",
    "headline": "코스닥이 자기 최고점에서 떨어진 거리",
    "category": "시장",
    "description_beginner": "코스닥이 신고가에 가까울수록 작은 종목에도 투기적인 돈이 몰렸다는 신호일 수 있습니다",
    "unit": "%",
    # 2026-07-23 점수·화면에서 내렸다. 타당성이 문제가 아니라(동행성 +0.678) 결국
    # kospi_high_gap 과 같은 것을 시장만 바꿔 재는 지표여서, 카드 한 칸을 kospi_speed_60d
    # 에 내줬다. 값 계산은 그대로 남겨 둔다 — 되돌리려면 is_public 과 두 config 만 되살리면
    # 된다. **is_public 을 안 내리면 프론트가 '미배치 공개 지표'로 자동 노출한다.**
    "is_public": False,
}


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

    # 옛 공휴일을 매 실행 다시 물어보지 않도록 최근 창만 훑는다(common/timeutil 참고).
    missing_days = days_to_backfill(existing, today, bootstrap_days=BACKFILL_DAYS)
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


def compute_high_gaps(prices: dict[str, float]) -> dict[str, tuple[float, float]]:
    """날짜별 (전고점 대비 괴리율 %, 그날 기준 전고점)을 돌려준다.

    fetch_kospi_high_gap.compute_gap 과 같은 규칙 — **그날을 제외한** 직전 365일 최고가를
    쓴다. 오늘을 포함해 max 를 잡으면 신고가를 쓴 날에도 괴리가 0에 캡돼 초과분이 안 보인다.
    """
    dates = sorted(prices)
    out: dict[str, tuple[float, float]] = {}
    for i, d in enumerate(dates):
        cutoff = (date.fromisoformat(d) - timedelta(days=HIGH_WINDOW_DAYS)).isoformat()
        window = [prices[x] for x in dates[:i] if x >= cutoff]
        if len(window) < 20:  # 창이 너무 짧으면 '전고점'이라 부를 수 없다
            continue
        prior_high = max(window)
        out[d] = ((prices[d] - prior_high) / prior_high * 100, prior_high)
    return out


def main() -> None:
    client = get_client()
    raw_id = ensure_indicator(client, RAW_META)
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{RAW_SLUG}' id: {raw_id}")
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    backfill_kosdaq_closes(client, raw_id)

    today = date.today()
    start = today - timedelta(days=BACKFILL_DAYS)
    kosdaq_prices = get_indicator_values(client, raw_id, start)
    print(f"[Supabase] 코스닥 종가 {len(kosdaq_prices)}건 조회")

    gaps = compute_high_gaps(kosdaq_prices)
    if not gaps:
        print(f"[{INDICATOR_SLUG}] 전고점을 잡을 만큼 종가가 쌓이지 않았습니다")
        return

    rows = [
        {
            "indicator_id": indicator_id,
            "date": d,
            "raw_value": round(gap, 2),
            # 카드가 "코스닥 751 · 전고점 1,229" 처럼 근거를 같이 보여줄 수 있게 남긴다.
            "details": {"close": kosdaq_prices[d], "prior_high": round(high, 2)},
        }
        for d, (gap, high) in sorted(gaps.items())
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건 (전량 재계산)")

    last = max(gaps)
    gap, high = gaps[last]
    print(
        f"[{INDICATOR_SLUG}] 최신값 ({last} 기준): "
        f"코스닥 {kosdaq_prices[last]:.2f} / 52주 전고점 {high:.2f} -> 괴리율 {gap:.2f}%"
    )


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
