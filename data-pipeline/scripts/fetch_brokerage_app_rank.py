"""애플 앱스토어 '금융' 무료앱 인기차트(한국)에서 증권 앱들의 순위를 긁어
froth 점수로 환산해 Supabase indicator_values에 upsert.

froth 논리: 증권(주식거래) 앱이 인기차트 상위로 치솟으면 = 개미가 대거 유입 =
과열. 2020~21 강세장에서 토스증권·미국 로빈후드가 앱 순위 1위를 찍던 그림이다.

점수 = 차트에 든 증권 앱마다 (LIMIT + 1 - 순위)를 합산. 상위(순위 낮음)일수록,
많이 들수록 점수가 커진다. (예: 10위=91점, 50위=51점, 차트 밖=0점)

한계:
- iOS 전용. 구글플레이는 무료 순위 공개 API가 없어(유료/스크래핑) 빠진다 —
  안드로이드 비중 큰 한국에선 iOS 차트를 대표 프록시로 쓴다.
- 애플 RSS는 '현재 스냅샷'만 줘서 과거 백필이 안 된다. fetch_github_trading_repos와
  동일하게 오늘 값만 조회해 그때부터 매일 누적한다.
- '금융' 카테고리는 은행·페이·보험이 대부분이라 증권 앱만 키워드로 골라낸다.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

# genre=6015 = 금융(Finance). limit=100 상위 100개 무료앱.
RSS_URL = "https://itunes.apple.com/kr/rss/topfreeapplications/genre=6015/limit=100/json"
LIMIT = 100
REQUEST_TIMEOUT_SEC = 15

# 증권(주식거래) 앱 식별 키워드 — 앱 이름 또는 판매사(artist)에 포함되면 증권 앱으로 본다.
# 일반 키워드(증권/securities)가 대부분을 잡고, 영문 앱명(M-STOCK/mPOP/영웅문 등)을 보강한다.
# 주의: 순수 "토스"(송금앱)는 제외하고 "토스증권/Toss Securities"만 매칭한다.
BROKERAGE_KEYWORDS = [
    "증권", "securities",
    "m-stock", "mpop", "영웅문", "namuh", "나무증권", "m-able", "mable", "크레온",
    "토스증권", "toss securities",
]

# 이름에 '증권'이 들어가지만 주식거래 전용이 아닌 금융 통합 슈퍼앱은 제외한다
# (예: 모니모 = 삼성 생명·화재·카드·증권 통합앱). froth는 '주식거래 앱' 순위여야 한다.
EXCLUDE_KEYWORDS = ["통합앱", "모니모", "monimo"]

INDICATOR_SLUG = "brokerage_app_rank"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "증권 앱 인기차트 순위",
    "category": "감성",
    "headline": "너도나도 계좌 트는 순간",
    "description_beginner": "증권 앱이 앱스토어 인기차트 상위로 치솟으면, 개미가 대거 몰려든다는 신호예요",
    "unit": "점",
    # weight 미지정 -> 기본값 1(검증 전 새 지표 안전장치)
}


def _is_brokerage(name: str, artist: str) -> bool:
    hay = f"{name} {artist}".lower()
    if any(kw.lower() in hay for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw.lower() in hay for kw in BROKERAGE_KEYWORDS)


def fetch_brokerage_froth() -> tuple[float, list[dict]]:
    resp = requests.get(RSS_URL, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    entries = resp.json().get("feed", {}).get("entry", [])
    if isinstance(entries, dict):  # 결과가 1개면 dict로 올 수 있어 리스트로 정규화
        entries = [entries]

    charted: list[dict] = []
    score = 0.0
    for rank, entry in enumerate(entries, start=1):
        name = (entry.get("im:name") or {}).get("label", "")
        artist = (entry.get("im:artist") or {}).get("label", "")
        if _is_brokerage(name, artist):
            contribution = LIMIT + 1 - rank
            score += contribution
            charted.append({"name": name, "rank": rank})
    return score, charted


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    score, charted = fetch_brokerage_froth()
    if charted:
        listing = ", ".join(f"{c['name']}({c['rank']}위)" for c in charted)
    else:
        listing = "차트인 증권 앱 없음"
    print(f"[AppStore] 증권 앱 froth 점수: {score:.0f}  |  {listing}")

    top_rank = min((c["rank"] for c in charted), default=None)
    details = {"count": len(charted), "top_rank": top_rank, "charted": charted}

    today = date.today().isoformat()
    client.table("indicator_values").upsert(
        {
            "indicator_id": indicator_id,
            "date": today,
            "raw_value": float(score),
            "details": details,
        },
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score:.0f}")


if __name__ == "__main__":
    main()
