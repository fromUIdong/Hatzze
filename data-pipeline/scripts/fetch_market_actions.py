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

raw_value("순수치") = (매수 사이드카 건수 - 매도 사이드카 건수) × 1
                      + CB 발동 건수 × (-4)
CB는 사이드카 개별 건보다 훨씬 무겁게(-4) 반영해 발동 시 지수를 크게 끌어내리되,
지수 전체를 극단적으로 좌우하지 않는 수준으로 잡았다. 음수면 progress=0으로
바닥 처리한다(다른 지표들의 NEGATIVE_CURRENT_CLAMP_SLUGS와 동일한 원칙 — 매도
쏠림/패닉 신호는 "매수 쏠림 과열"과 반대 방향이라 0 밑으로는 의미가 없다).

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

KIND_SEARCH_URL = "https://kind.krx.co.kr/disclosure/searchtotalinfo.do"
REQUEST_TIMEOUT_SEC = 20
PAGE_SIZE = 500  # 연간 발동 건수(수십 건 수준)를 한 페이지에 다 담기에 충분

SIDECAR_KEYWORD = "사이드카"
CIRCUIT_BREAKER_SEARCH_KEYWORD = "매매거래중단"  # KIND는 "서킷브레이커"라는 단어를 안 씀
CB_TITLE_MARKER = "CB 발동"  # 개별종목 매매정지 등 무관한 검색 결과를 걸러내는 후처리 필터

WINDOW_DAYS = 30  # 롤링 집계 기간
BACKFILL_DAYS = 365
CB_WEIGHT = -4.0
SIDECAR_WEIGHT = 1.0

# 자리마다 검색 시 이 시장명들만 "시장 전체" 이벤트로 인정한다(개별 종목명이
# market으로 잡히는 경우는 사이드카/CB 발동 공시가 아니므로 애초에
# CB_TITLE_MARKER/사이드카 패턴에 안 걸려 자연히 제외되지만, 이중 안전장치로 남겨둔다).
MARKET_NAMES = {"유가증권시장", "코스닥시장"}

INDICATOR_SLUG = "market_actions_30d"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "최근 한 달 매매 안전장치 동향",
    "category": "정통",
    "headline": "한 달간 어느 쪽이 우세했나",
    "description_beginner": "주가가 급등하면 매수 사이드카, 급락하면 매도 사이드카·서킷브레이커(CB)가 발동돼요. 최근 한 달 어느 쪽 안전장치가 더 자주 걸렸는지로 시장이 달아올랐는지 식었는지를 읽어요",
    "unit": "건",
    "weight": 2,
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        indicator_id = existing.data[0]["id"]
        # 이름/헤드라인/설명을 바꿨을 때 기존 레코드에도 반영되도록 매 실행 갱신한다.
        client.table("indicators").update(
            {k: v for k, v in INDICATOR_META.items() if k != "slug"}
        ).eq("id", indicator_id).execute()
        return indicator_id

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


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
    indicator_id = ensure_indicator(client)
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
        raw = (buy_count - sell_count) * SIDECAR_WEIGHT + cb_count * CB_WEIGHT
        raw = max(raw, 0.0)
        rows.append(
            {
                "indicator_id": indicator_id,
                "date": d.isoformat(),
                "raw_value": round(raw, 2),
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
    latest_raw = max((latest_buy - latest_sell) * SIDECAR_WEIGHT + latest_cb * CB_WEIGHT, 0.0)
    print(
        f"[{INDICATOR_SLUG}] 오늘({today}) 기준 최근 {WINDOW_DAYS}일: "
        f"매수 사이드카 {latest_buy}건, 매도 사이드카 {latest_sell}건, CB 발동 {latest_cb}건 "
        f"-> 순수치 {round(latest_raw, 2)}"
    )


if __name__ == "__main__":
    main()
