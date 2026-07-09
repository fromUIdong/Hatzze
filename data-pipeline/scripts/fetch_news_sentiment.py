"""네이버 뉴스 검색 API로 경제뉴스 헤드라인 감성 지수를 계산해 Supabase에 upsert.

"코스피", "증시" 키워드로 최신순(sort=date) 뉴스를 모아 오늘자 헤드라인만 골라
감성 분류한다. 감성 스코어 = (긍정 - 부정) / 전체 * 100 (-100~100).

네이버 뉴스 검색 API는 날짜 범위 필터를 지원하지 않고 최신순 페이지네이션만
가능하며, 쿼리당 start+display 합이 1000을 넘을 수 없다(즉 쿼리당 최대 1000건까지만
조회 가능). --backfill은 이 한도 안에서 도달 가능한 과거 날짜만큼만 채우고, 그
이상 과거는 채우지 못한 채로 남아 이후 매일 실행하면서 자연스럽게 누적된다.
"""

from __future__ import annotations

import html
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from config.news_sentiment_keywords import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS  # noqa: E402

NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
QUERIES = ["코스피", "증시"]
DISPLAY_PER_PAGE = 100
MAX_START = 1000  # 네이버 뉴스 검색 API 한도: start + display - 1 <= 1000
REQUEST_DELAY_SEC = 0.2
# 정렬이 흐트러진 예외적인 기사 한두 건 때문에 조기 종료되지 않도록, 목표 범위보다
# 오래된 기사가 연속으로 여러 건 나올 때만 완전히 지난 것으로 판단한다.
OLD_ITEM_STREAK_THRESHOLD = 5

BACKFILL_DAYS = 30  # 실제로는 API의 1000건 한도 안에서 도달 가능한 만큼만 채워짐

INDICATOR_SLUG = "news_sentiment"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "경제뉴스 헤드라인 감성 지수",
    "category": "밈",
    "description_beginner": "경제 뉴스 제목에 낙관적인 말이 많은지 비관적인 말이 많은지 보여주는 지수예요. 다들 장밋빛 전망만 하고 있다면 과열 신호일 수 있어요",
    "unit": "pt",
}

TAG_RE = re.compile(r"<[^>]+>")


def clean_title(raw_title: str) -> str:
    return html.unescape(TAG_RE.sub("", raw_title)).strip()


def parse_pub_date(pub_date: str) -> date:
    # 예: "Wed, 08 Jul 2026 14:32:00 +0900"
    return datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z").date()


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def classify_sentiment(title: str) -> str:
    positive_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in title)
    negative_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in title)

    if positive_hits == 0 and negative_hits == 0:
        return "neutral"
    if positive_hits > negative_hits:
        return "positive"
    if negative_hits > positive_hits:
        return "negative"
    return "neutral"  # 동률


def fetch_page(query: str, start: int) -> list[dict]:
    resp = requests.get(
        NAVER_NEWS_SEARCH_URL,
        headers={
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        },
        params={
            "query": query,
            "display": DISPLAY_PER_PAGE,
            "start": start,
            "sort": "date",
        },
        timeout=10,
    )
    if resp.status_code == 401:
        raise PermissionError(
            "네이버 API가 401을 반환했습니다. developers.naver.com에서 해당 "
            "애플리케이션에 '검색' API가 활성화되어 있는지 확인하세요."
        )
    resp.raise_for_status()
    return resp.json().get("items", [])


def compute_sentiment(titles: list[str]) -> dict:
    positive = negative = neutral = 0
    for title in titles:
        label = classify_sentiment(title)
        if label == "positive":
            positive += 1
        elif label == "negative":
            negative += 1
        else:
            neutral += 1

    total = len(titles)
    score = (positive - negative) / total * 100 if total else 0.0
    return {
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "total": total,
        "score": score,
    }


def collect_today_titles_for_query(query: str) -> dict[str, str]:
    today = date.today()
    headlines: dict[str, str] = {}
    start = 1
    consecutive_old = 0
    done = False

    while start <= MAX_START and not done:
        items = fetch_page(query, start)
        if not items:
            break

        for item in items:
            try:
                pub_date = parse_pub_date(item["pubDate"])
            except (KeyError, ValueError):
                continue

            if pub_date != today:
                consecutive_old += 1
                if consecutive_old >= OLD_ITEM_STREAK_THRESHOLD:
                    done = True
                    break
                continue
            consecutive_old = 0

            link = item.get("link") or item.get("originallink") or item["title"]
            headlines[link] = clean_title(item["title"])

        if len(items) < DISPLAY_PER_PAGE:
            break

        start += DISPLAY_PER_PAGE
        if not done:
            time.sleep(REQUEST_DELAY_SEC)

    print(f"[Naver News] '{query}' 조회 완료 ({len(headlines)}건)")
    return headlines


def collect_today_titles() -> list[str]:
    combined: dict[str, str] = {}
    for query in QUERIES:
        combined.update(collect_today_titles_for_query(query))
        time.sleep(REQUEST_DELAY_SEC)
    return list(combined.values())


def collect_daily_titles_for_query(
    query: str, oldest_missing: str
) -> dict[str, dict[str, str]]:
    """날짜별 {link: 제목} 딕셔너리를 모은다."""
    day_headlines: dict[str, dict[str, str]] = {}
    start = 1
    consecutive_old = 0
    done = False

    while start <= MAX_START and not done:
        items = fetch_page(query, start)
        if not items:
            break

        for item in items:
            try:
                pub_date = parse_pub_date(item["pubDate"]).isoformat()
            except (KeyError, ValueError):
                continue

            if pub_date < oldest_missing:
                consecutive_old += 1
                if consecutive_old >= OLD_ITEM_STREAK_THRESHOLD:
                    done = True
                    break
                continue
            consecutive_old = 0

            link = item.get("link") or item.get("originallink") or item["title"]
            day_headlines.setdefault(pub_date, {})[link] = clean_title(item["title"])

        if len(items) < DISPLAY_PER_PAGE:
            break

        start += DISPLAY_PER_PAGE
        if not done:
            time.sleep(REQUEST_DELAY_SEC)

    return day_headlines


def backfill_daily_sentiment(client, indicator_id: str) -> None:
    today = date.today()
    target_dates = {
        (today - timedelta(days=offset)).isoformat() for offset in range(BACKFILL_DAYS)
    }

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .in_("date", list(target_dates))
        .execute()
    )
    existing_dates = {row["date"] for row in existing.data}
    missing_dates = target_dates - existing_dates

    if not missing_dates:
        print(f"[Naver News] 백필할 신규 날짜 없음 (최근 {BACKFILL_DAYS}일 모두 저장됨)")
        return

    oldest_missing = min(missing_dates)
    print(f"[Naver News] 백필 대상 {len(missing_dates)}일 (가장 오래된 날짜: {oldest_missing})")

    combined: dict[str, dict[str, str]] = {}
    for query in QUERIES:
        query_days = collect_daily_titles_for_query(query, oldest_missing)
        for d, links in query_days.items():
            combined.setdefault(d, {}).update(links)
        time.sleep(REQUEST_DELAY_SEC)

    if combined:
        reachable = sorted(combined.keys())
        print(
            f"[Naver News] API 한도(쿼리당 최대 {MAX_START}건) 안에서 도달한 날짜 범위: "
            f"{reachable[0]} ~ {reachable[-1]}"
        )

    rows_to_save = []
    for d, links in combined.items():
        if d not in missing_dates:
            continue
        result = compute_sentiment(list(links.values()))
        score = round(result["score"], 2)
        rows_to_save.append({"indicator_id": indicator_id, "date": d, "raw_value": score})
        print(
            f"[Naver News] {d}: 긍정 {result['positive']} / 부정 {result['negative']} / "
            f"중립 {result['neutral']} (전체 {result['total']}) -> {score}pt"
        )

    if rows_to_save:
        client.table("indicator_values").upsert(
            rows_to_save, on_conflict="indicator_id,date"
        ).execute()

    not_reached = missing_dates - set(combined.keys())
    if not_reached:
        print(
            f"[Naver News] API 한도 안에서 도달하지 못한 날짜 {len(not_reached)}일은 "
            "이번엔 백필하지 못했습니다. 매일 실행하면서 자연스럽게 채워집니다."
        )
    print(f"[Naver News] 백필 완료: {len(rows_to_save)}일치 저장")


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    if "--backfill" in sys.argv:
        backfill_daily_sentiment(client, indicator_id)
        return

    titles = collect_today_titles()
    result = compute_sentiment(titles)
    today = date.today().isoformat()

    print(
        f"[Naver News] 오늘({today}) 감성 분류 — 긍정 {result['positive']}건 / "
        f"부정 {result['negative']}건 / 중립 {result['neutral']}건 (전체 {result['total']}건)"
    )

    if result["total"]:
        neutral_ratio = result["neutral"] / result["total"] * 100
        if neutral_ratio >= 80:
            print(
                f"[WARNING] 중립 비율이 {neutral_ratio:.1f}%로 매우 높습니다. "
                "config/news_sentiment_keywords.py의 키워드를 보강하는 걸 권장합니다."
            )

    score = round(result["score"], 2)
    print(f"[Naver News] 감성 스코어: {score}pt")

    client.table("indicator_values").upsert(
        {"indicator_id": indicator_id, "date": today, "raw_value": score},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score}")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
