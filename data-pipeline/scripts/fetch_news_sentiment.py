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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.naver_client import search_news  # noqa: E402
from common.details import merge_details, sentiment_details, store_abs_scale_details  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.timeutil import today_kst  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402
from common.llm_sentiment import LlmUnavailableError, classify_titles  # noqa: E402

QUERIES = ["코스피", "증시"]
DISPLAY_PER_PAGE = 100
# API HUB 한도는 start <= 1000 이다(초과 시 400 "Invalid start value"). 구 개발자센터의
# 'start + display - 1 <= 1000' 보다 느슨하지만, start 를 100씩 늘리므로 실질 상한은
# 그대로 1,000건이다 — 값을 바꿀 이유는 없고 규칙만 바로잡아 둔다.
MAX_START = 1000
REQUEST_DELAY_SEC = 0.2
# 정렬이 흐트러진 예외적인 기사 한두 건 때문에 조기 종료되지 않도록, 목표 범위보다
# 오래된 기사가 연속으로 여러 건 나올 때만 완전히 지난 것으로 판단한다.
OLD_ITEM_STREAK_THRESHOLD = 5

BACKFILL_DAYS = 30  # 실제로는 API의 1000건 한도 안에서 도달 가능한 만큼만 채워짐

INDICATOR_SLUG = "news_sentiment"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "경제뉴스 감성 지수",
    "headline": "경제뉴스 제목에 드러난 낙관·비관",
    "category": "감성",
    "description_beginner": "뉴스 제목마다 장밋빛 전망만 넘치면, 여론이 한쪽으로 쏠린 신호입니다",
    "unit": "pt",
}

TAG_RE = re.compile(r"<[^>]+>")


def clean_title(raw_title: str) -> str:
    return html.unescape(TAG_RE.sub("", raw_title)).strip()


def parse_pub_date(pub_date: str) -> date:
    # 예: "Wed, 08 Jul 2026 14:32:00 +0900"
    return datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z").date()


def fetch_page(query: str, start: int) -> list[dict]:
    resp = search_news(
        {
            "query": query,
            "display": DISPLAY_PER_PAGE,
            "start": start,
            "sort": "date",
        }
    )
    if resp.status_code == 401:
        # NAVER API HUB 는 '해당 API 가 Application 에 등록 안 됨'을 401 로 준다
        # (없는 경로는 404). 그래서 401 이면 키가 아니라 등록 여부를 먼저 본다.
        raise PermissionError(
            "네이버 뉴스 검색이 401을 반환했습니다. 네이버 클라우드 콘솔의 "
            "NAVER API HUB > Application > API 관리에서 'NAVER 검색 > 뉴스'가 "
            "등록돼 있는지, 그리고 NAVER_HUB_KEY_ID/KEY 가 그 Application 의 키인지 확인하세요."
        )
    resp.raise_for_status()
    return resp.json().get("items", [])


def compute_sentiment(titles: list[str]) -> dict:
    labels = classify_titles(titles, source="경제 뉴스 헤드라인", slang=False)
    positive = labels.count("positive")
    negative = labels.count("negative")
    neutral = labels.count("neutral")

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
    today = today_kst()
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
    today = today_kst()
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
        rows_to_save.append(
            {"indicator_id": indicator_id, "date": d, "raw_value": score, "details": sentiment_details(result)}
        )
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
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    if "--backfill" in sys.argv:
        backfill_daily_sentiment(client, indicator_id)
        # 감성 게이지가 '자기 최근 범위 대비'로 마커를 배치할 수 있게 스케일 저장.
        store_abs_scale_details(client, indicator_id)
        return

    titles = collect_today_titles()
    result = compute_sentiment(titles)
    today = today_kst().isoformat()

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

    # 같은 날 재실행이면 이미 details가 있을 수 있어 병합해서 쓴다(공유 칸).
    client.table("indicator_values").upsert(
        {
            "indicator_id": indicator_id,
            "date": today,
            "raw_value": score,
            "details": merge_details(client, indicator_id, today, sentiment_details(result)),
        },
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score}")

    # 감성 게이지가 '자기 최근 범위 대비'로 마커를 배치할 수 있게 스케일 저장.
    updated = store_abs_scale_details(client, indicator_id)
    print(f"[Supabase] 감성 스케일 details 저장 완료: {updated}건")


if __name__ == "__main__":
    try:
        main()
    except LlmUnavailableError as e:
        # 분류가 안 되면 그날 값을 쓰지 않는다 — 옛 키워드 방식으로 몰래 되돌아가면
        # 스케일이 다른 값이 시계열에 섞여 더 나쁘다. 워크플로우는 continue-on-error 다.
        print(f"[WARNING] [Naver News] LLM 분류 불가로 오늘 계산을 건너뜁니다: {e}")
