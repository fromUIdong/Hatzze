"""KIND(한국거래소 공시시스템) 통합검색의 "시장조치" 카테고리에서 사이드카·CB
(서킷브레이커) 발동 공시를 검색해 "최근 30일 매수 쏠림 안전장치 지수"를
계산해 Supabase에 upsert.

KRX 공식 API/정보데이터시스템 어디에도 사이드카·CB 발동 이력을 주는 엔드포인트가
없어서(조사 완료), 대신 KIND의 시장조치 공시를 쓴다 — 발동 1건당 정확히 공시
1건이 나오고(뉴스 집계처럼 언론사별 중복 보도 문제가 없음), 매수/매도 사이드카가
제목에 명확히 구분되며, 시/분/초 단위 발동 시각까지 포함된 공식 소스다.
robots.txt는 kind.krx.co.kr에 아예 없어(404) 명시적 크롤링 차단이 없다.

KIND는 "서킷브레이커"라는 단어를 쓰지 않는다 — 공식 명칭은 "매매거래 일시중단
(N단계 CB 발동)"이다. "매매거래중단" 키워드로 검색하면 개별종목 매매정지(SPAC
합병 등)까지 섞여 나오므로, 제목에 "CB 발동" 문구가 있는 것만 후처리로
골라낸다.

- 매수 사이드카 = 프로그램 매수호가 일시 효력정지(선물 가격이 5% 이상 급등)
- 매도 사이드카 = 프로그램 매도호가 일시 효력정지(선물 가격이 5% 이상 급락)
- CB 발동 = 코스피/코스닥 지수가 8% 이상 급락해 전체 시장 매매거래가 중단됨
  (항상 급락/패닉 신호)

raw_value("매수 사이드카 비중") = 매수 / (매수 + 매도 + CB + 2)

즉 "안전장치가 걸렸을 때 그중 상승 쪽(매수 사이드카)이 차지한 비중". 0에 가까울수록
패닉(매도·CB 우세), 1에 가까울수록 멜트업(매수 우세)이다.

**2026-07-20 공식 교체 이력.** 이전 공식은 (매수-매도)×1 + CB×(-4)를 0으로 클램프한
차이값이었는데, 1년 370일 중 **318일(86%)이 0**으로 뭉개져 사실상 정보를 못 냈다.
안전장치가 아예 안 걸린 날은 46%뿐이니 나머지 40%p는 실제 이벤트가 있었는데도 버려진
것이다(예: 매수4·매도7·CB4인 국면과 아무 일 없던 국면이 똑같이 0). 차이값은 매수와
매도가 연간 거의 균형이라(17건 vs 18건) 잘 안 벌어지고, CB가 -4로 강하게 끌어내리면
곧장 바닥에 붙는 구조였다.

비중으로 바꾸면 0~1로 유계라 포화되지 않고, 같은 자료로 값 종류가 4가지 → 25가지가
된다. 분모의 +2(SMOOTHING_K)는 얇은 표본 방어다 — 없으면 "한 달에 매수 사이드카
1건, 나머지 0건"이 비중 1.0(최대 과열)이 돼버린다. +2를 넣으면 매수 1건만=0.33,
3건만=0.60, 6건만=0.75로 건수에 따라 자연히 눌린다.

방향은 그대로 high=과열이고, 셋 다 0인 조용한 달은 0.0이 된다(과열 신호 없음 —
의미상 맞다). 임계값은 config/indicator_thresholds.py에서 0.50으로, 옛 임계값 2.0과
같은 엄격도(1년 중 16일 도달)에 맞췄다.

KIND 검색은 날짜 범위 쿼리라 페이지 하나로 1년치를 통째로 받아올 수 있다(연간
사이드카 20~30건, CB 5~10건 수준이라 페이지네이션 없이 한 번에 충분).
그래서 매일 새 날짜 범위로 재검색하는 대신, 1년치 이벤트를 한 번만 받아와
메모리 안에서 날짜별로 30일 슬라이딩 윈도우를 계산한다 —
fetch_asia_relative_strength.py의 20일 수익률 계산과 같은 접근이다. 최초
실행 시 계산 가능한 만큼(최근 365일) 백필하고, 이후 실행부터도 매번 전체를
다시 계산해 upsert한다(공식이 바뀔 수 있는 파생값이라 fetch_upbit_speculation.py
와 동일한 이유).
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

KIND_SEARCH_URL = "https://kind.krx.co.kr/disclosure/searchtotalinfo.do"
REQUEST_TIMEOUT_SEC = 20
PAGE_SIZE = 500  # 연간 발동 건수(수십 건 수준)를 한 페이지에 다 담기에 충분

SIDECAR_KEYWORD = "사이드카"
CIRCUIT_BREAKER_SEARCH_KEYWORD = "매매거래중단"  # KIND는 "서킷브레이커"라는 단어를 안 씀
CB_TITLE_MARKER = "CB 발동"  # 개별종목 매매정지 등 무관한 검색 결과를 걸러내는 후처리 필터

WINDOW_DAYS = 30  # 롤링 집계 기간
BACKFILL_DAYS = 365
# 얇은 표본 평활 상수 — raw_value 주석 참조.
SMOOTHING_K = 2.0

# 자리마다 검색 시 이 시장명들만 "시장 전체" 이벤트로 인정한다(개별 종목명이
# market으로 잡히는 경우는 사이드카/CB 발동 공시가 아니므로 애초에
# CB_TITLE_MARKER/사이드카 패턴에 안 걸려 자연히 제외되지만, 이중 안전장치로 남겨둔다).
MARKET_NAMES = {"유가증권시장", "코스닥시장"}

INDICATOR_SLUG = "market_actions_30d"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "최근 한 달 매매 안전장치 동향",
    "category": "시장",
    "headline": "사이드카·서킷브레이커 발동 내역",
    "description_beginner": "주가가 급등하면 매수 사이드카, 급락하면 매도 사이드카·서킷브레이커(CB)가 발동돼요. 최근 한 달 어느 쪽 안전장치가 더 자주 걸렸는지로 시장이 달아올랐는지 식었는지를 읽어요",
    "unit": "건",
    "weight": 2,
}


def search_market_actions(kwd: str, from_date: date, to_date: date) -> list[tuple[str, str, date]]:
    """(시장명, 제목, 날짜) 리스트를 반환. 시/분/초는 버리고 날짜만 쓴다."""
    resp = requests.post(
        KIND_SEARCH_URL,
        data={
            "method": "searchTotalInfoSub",
            "forward": "searchtotalinfo_detail",
            "fdName": "all_mktact_idx",
            "scn": "mktact",
            "srchFd": "2",  # 시장조치 카테고리
            "kwd": kwd,
            "fromData": from_date.isoformat(),
            "toData": to_date.isoformat(),
            "pageIndex": "1",
            "currentPageSize": str(PAGE_SIZE),
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    resp.raise_for_status()

    entries = []
    pattern = re.compile(
        r'<strong class="name"><a[^>]*>([^<]+)</a></strong>\s*'
        r'<span class="subject"><a href="#" title="([^"]+)"[^>]*>.*?</a></span>\s*'
        r'<em class="date">\s*([\d-]{10})',
        re.DOTALL,
    )
    for market, raw_title, date_str in pattern.findall(resp.text):
        title = re.sub(r"</?b>", "", raw_title)  # <b>강조</b> 태그 제거
        entries.append((market.strip(), title.strip(), date.fromisoformat(date_str.strip())))
    return entries


def classify_sidecar(entries: list[tuple[str, str, date]]) -> list[tuple[str, date]]:
    """[(방향, 날짜), ...] — 방향은 'buy' 또는 'sell'."""
    result = []
    for market, title, event_date in entries:
        if market not in MARKET_NAMES or SIDECAR_KEYWORD not in title:
            continue
        if "매수" in title:
            result.append(("buy", event_date))
        elif "매도" in title:
            result.append(("sell", event_date))
    return result


def classify_circuit_breaker(entries: list[tuple[str, str, date]]) -> list[date]:
    return [
        event_date
        for market, title, event_date in entries
        if market in MARKET_NAMES and CB_TITLE_MARKER in title
    ]


def rolling_counts(dates: list[date], window_end: date) -> int:
    window_start = window_end - timedelta(days=WINDOW_DAYS - 1)
    return sum(1 for d in dates if window_start <= d <= window_end)


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    fetch_start = today - timedelta(days=BACKFILL_DAYS + WINDOW_DAYS)

    sidecar_entries = search_market_actions(SIDECAR_KEYWORD, fetch_start, today)
    cb_entries = search_market_actions(CIRCUIT_BREAKER_SEARCH_KEYWORD, fetch_start, today)

    sidecars = classify_sidecar(sidecar_entries)
    buy_dates = [d for direction, d in sidecars if direction == "buy"]
    sell_dates = [d for direction, d in sidecars if direction == "sell"]
    cb_dates = classify_circuit_breaker(cb_entries)

    print(
        f"[KIND] 조회 기간 {fetch_start} ~ {today}: "
        f"매수 사이드카 {len(buy_dates)}건, 매도 사이드카 {len(sell_dates)}건, "
        f"CB 발동 {len(cb_dates)}건"
    )

    rows = []
    for offset in range(BACKFILL_DAYS + 1):
        d = today - timedelta(days=offset)
        buy_count = rolling_counts(buy_dates, d)
        sell_count = rolling_counts(sell_dates, d)
        cb_count = rolling_counts(cb_dates, d)
        raw = buy_count / (buy_count + sell_count + cb_count + SMOOTHING_K)
        rows.append(
            {
                "indicator_id": indicator_id,
                "date": d.isoformat(),
                "raw_value": round(raw, 4),
                # 카드가 목업 원본대로 매수/매도/CB 다이버징 바를 그릴 수 있도록
                # 최근 30일 세 건수를 details(JSONB)에 함께 저장한다.
                "details": {"buy": buy_count, "sell": sell_count, "cb": cb_count},
            }
        )

    client.table("indicator_values").upsert(rows, on_conflict="indicator_id,date").execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(rows)}건")

    latest_buy = rolling_counts(buy_dates, today)
    latest_sell = rolling_counts(sell_dates, today)
    latest_cb = rolling_counts(cb_dates, today)
    latest_raw = latest_buy / (latest_buy + latest_sell + latest_cb + SMOOTHING_K)
    print(
        f"[{INDICATOR_SLUG}] 오늘({today}) 기준 최근 {WINDOW_DAYS}일: "
        f"매수 사이드카 {latest_buy}건, 매도 사이드카 {latest_sell}건, CB 발동 {latest_cb}건 "
        f"-> 매수 비중 {round(latest_raw, 3)}"
    )


if __name__ == "__main__":
    main()
