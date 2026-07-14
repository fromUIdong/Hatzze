"""GitHub 검색 API로 최근 24시간 내 생성된 트레이딩 봇 저장소 개수를 가져와
Supabase indicator_values에 upsert.

"trading-bot", "quant-trading", "stock-bot", "algo-trading" 키워드가 이름 또는
설명에 포함된 저장소 중 생성 시각이 최근 LOOKBACK_HOURS(24)시간 이내인 것의
total_count를 그대로 raw_value로 쓴다. 인증 없이도 호출 가능하지만 검색 API는
rate limit이 낮아(비인증 10회/분 vs 인증 30회/분), .env.local에 GITHUB_TOKEN이
있으면 사용하고 없으면 비인증으로 진행한다.

GitHub 검색 API는 생성일 범위(created:YYYY-MM-DD..YYYY-MM-DD)로 과거 특정
기간을 조회하는 것 자체는 가능하지만, 결과는 "그 기간에 생성됐고 지금까지
삭제되지 않고 살아남은" 저장소만 잡히는 현재 시점 기준 재구성이라 당시의 진짜
값과 다르다. 게다가 검색 API 자체의 낮은 rate limit 때문에 365일치를 백필하려면
수백 번을 호출해야 한다. 그래서 백필은 하지 않고 fetch_bestseller_ratio.py와
동일하게 오늘 값만 조회해 그때부터 매일 누적한다.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import GITHUB_TOKEN  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
KEYWORDS = ["trading-bot", "quant-trading", "stock-bot", "algo-trading"]
LOOKBACK_HOURS = 24
REQUEST_TIMEOUT_SEC = 15

INDICATOR_SLUG = "github_trading_bot_repos"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "GitHub 트레이딩봇 저장소 생성 수",
    "category": "감성",
    "headline": "개발자들도 뛰어드는 순간",
    "description_beginner": "개발자까지 트레이딩 봇을 만들 만큼 관심이 높아졌어요",
    "unit": "건",
    # weight 미지정 -> 기본값 1(검증 전 새 지표 안전장치)
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def fetch_trading_bot_repo_count() -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # GitHub 검색 API는 괄호로 묶은 OR절 전체에 in: 한정자를 적용하지 않는다
    # (실제 호출로 확인 — `("a" OR "b") in:name,description`은 0건을 반환).
    # 항목마다 in: 한정자를 반복해서 붙여야 각 키워드가 이름/설명에서 매칭된다.
    # created: 같은 bare 한정자는 OR로 묶인 전체 절에 공통으로 적용된다.
    keyword_clause = " OR ".join(f'"{kw}" in:name,description' for kw in KEYWORDS)
    query = f"{keyword_clause} created:>={cutoff}"

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    resp = requests.get(
        GITHUB_SEARCH_URL,
        params={"q": query},
        headers=headers,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    data = resp.json()
    return int(data.get("total_count", 0))


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    count = fetch_trading_bot_repo_count()
    print(f"[GitHub] 최근 {LOOKBACK_HOURS}시간 내 생성된 트레이딩봇 저장소: {count}건")

    today = date.today().isoformat()
    client.table("indicator_values").upsert(
        {"indicator_id": indicator_id, "date": today, "raw_value": float(count)},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={count}")


if __name__ == "__main__":
    main()
