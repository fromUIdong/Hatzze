"""YouTube Data API로 재테크 키워드 관련 영상을 검색해, 최근 화제성(조회수)을
계산해 Supabase에 upsert.

처음엔 "인기 급상승"(mostPopular) 차트에서 재테크 콘텐츠 비중을 보려 했지만,
인급동은 카테고리가 워낙 다양해 재테크 콘텐츠가 뚫고 올라가는 일이 거의 없어
(실제로 상위 50개 중 하나도 안 걸림) 항상 0%에 가까운 죽은 지표가 될 가능성이
높았다. 그래서 search.list로 재테크 키워드를 직접 검색해 "최근 이 주제로 뜨는
영상이 실제로 얼마나 화제인지"를 조회수로 직접 측정하는 방식으로 바꿨다.

FINANCE_KEYWORDS(config/finance_content_keywords.py)를 "|"(OR)로 묶어
search.list(order=viewCount, publishedAfter=최근 SEARCH_WINDOW_DAYS일)로
최근 업로드된 영상 중 조회수 상위 SEARCH_MAX_RESULTS개를 찾고, videos.list로
실제 조회수를 조회해 평균을 raw_value로 쓴다. search.list는 유닛 비용이 커서
(100유닛/회, videos.list는 1유닛/회) 하루 1회 실행 기준으로는 문제없지만
호출 횟수를 늘릴 땐 쿼터(기본 10,000유닛/일)를 주의해야 한다.

"최근 N일 내 상위 조회수"는 매번 현재 시점 기준으로만 조회 가능해 과거 날짜를
그대로 재현할 수 없다. 따라서 백필은 불가능하고 오늘부터 매일 누적한다.
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import YOUTUBE_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from config.finance_content_keywords import FINANCE_KEYWORDS  # noqa: E402

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
SEARCH_WINDOW_DAYS = 7
SEARCH_MAX_RESULTS = 20
REQUEST_TIMEOUT_SEC = 15
MAX_RETRIES = 3
RETRY_DELAY_SEC = 3

INDICATOR_SLUG = "youtube_finance_search_views"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "재테크 유튜브 검색 콘텐츠 조회수",
    "category": "감성",
    "description_beginner": "재테크 유튜브 조회수가 확 뛰면, 콘텐츠가 평소보다 빠르게 퍼진다는 신호예요",
    "unit": "회",
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def _get_with_retry(url: str, params: dict) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
            if resp.status_code == 403:
                raise RuntimeError(
                    "YouTube API가 403을 반환했습니다. YOUTUBE_API_KEY가 유효한지, "
                    "YouTube Data API v3가 활성화됐는지, 일일 쿼터가 남아있는지 확인하세요."
                )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, RuntimeError) as e:
            last_error = e
            print(f"[YouTube] 요청 실패 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)

    raise RuntimeError(f"YouTube API 요청이 {MAX_RETRIES}번 모두 실패했습니다") from last_error


def search_finance_video_ids() -> list[str]:
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=SEARCH_WINDOW_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    data = _get_with_retry(
        YOUTUBE_SEARCH_URL,
        {
            "part": "snippet",
            "q": "|".join(FINANCE_KEYWORDS),
            "type": "video",
            "order": "viewCount",
            "publishedAfter": published_after,
            "regionCode": "KR",
            "relevanceLanguage": "ko",
            "maxResults": SEARCH_MAX_RESULTS,
            "key": YOUTUBE_API_KEY,
        },
    )
    return [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def fetch_view_counts(video_ids: list[str]) -> list[int]:
    if not video_ids:
        return []
    data = _get_with_retry(
        YOUTUBE_VIDEOS_URL,
        {
            "part": "statistics",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        },
    )
    return [int(item["statistics"].get("viewCount", 0)) for item in data.get("items", [])]


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    video_ids = search_finance_video_ids()
    if not video_ids:
        raise RuntimeError(
            f"최근 {SEARCH_WINDOW_DAYS}일 내 재테크 키워드 관련 영상을 찾지 못했습니다"
        )

    view_counts = fetch_view_counts(video_ids)
    if not view_counts:
        raise RuntimeError("검색된 영상들의 조회수를 조회하지 못했습니다")

    avg_views = sum(view_counts) / len(view_counts)

    print(f"[YouTube] 최근 {SEARCH_WINDOW_DAYS}일 내 재테크 영상 {len(view_counts)}개 조회")
    for count in sorted(view_counts, reverse=True):
        print(f"  - {count:,}회")

    score = round(avg_views, 2)
    print(f"[YouTube] 평균 조회수: {score:,.2f}회")

    today = date.today().isoformat()
    client.table("indicator_values").upsert(
        {"indicator_id": indicator_id, "date": today, "raw_value": score},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score}")


if __name__ == "__main__":
    main()
