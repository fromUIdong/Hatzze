"""알라딘 오픈API로 종합 베스트셀러 상위 100권을 조회해 경제 도서 비중을
계산해 Supabase에 upsert.

표본이 100권인 이유: 예전엔 50권만 봤는데, 그러면 비중이 2%p 단위로만 움직인다
(1권=2%). 실제로 60일간 나온 값이 2.0과 4.0 두 종류뿐이라 "1권이냐 2권이냐"를
재는 꼴이었고, 과열 신호로서 정보가 거의 없었다. threshold 주석은 처음부터
'베스트셀러 100위 중'을 전제하고 있었으니 코드가 의도를 못 따라간 쪽이다.

각 도서의 categoryName(예: "국내도서>경제경영>재테크/투자")에 "경제경영"이
포함되는지로 판단한다. 경제경영 카테고리(CID=170)를 별도로 조회해 교차 대조하는
대신, 종합 베스트셀러 조회 한 번으로 끝내는 쪽이 더 안정적이고 API 호출도 적다
— 종합 순위와 카테고리별 순위는 서로 다른 랭킹이라 두 목록을 교차 매칭하는 것보다
한 목록 안에서 categoryName을 직접 읽는 편이 정확하다.

알라딘 API는 "오늘" 시점 베스트셀러만 조회 가능해 과거 날짜를 조회할 수 없다.
따라서 백필은 불가능하고 오늘부터 매일 누적한다. 표본을 50 → 100권으로 넓힌 날
이전 값은 50권 기준이라 시계열에 한 번 단차가 생긴다(51~100위에 경제경영 책이
더 많아 새 값이 대체로 높게 나온다).
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import ALADIN_TTB_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

ALADIN_URL = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
# 알라딘은 한 번에 최대 50권만 준다 — MaxResults=100 을 넣어도 조용히 50 으로 잘린다.
# start 는 아이템 오프셋이 아니라 **페이지 번호**라, 100권을 받으려면 1·2페이지를 받는다.
MAX_RESULTS = 50
PAGES = 2  # 1페이지=1~50위, 2페이지=51~100위
ECONOMY_CATEGORY_KEYWORD = "경제경영"
REQUEST_TIMEOUT_SEC = 30  # 알라딘 API가 가끔 응답이 느려서 여유 있게 설정
MAX_RETRIES = 3
RETRY_DELAY_SEC = 3

INDICATOR_SLUG = "bestseller_finance_ratio"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "경제 베스트셀러 비중",
    "headline": "베스트셀러 100권 중 경제 책 비중",
    "category": "감성",
    "description_beginner": "베스트셀러에 재테크 책이 많으면, 관심이 쏠렸다는 신호",
    "unit": "%",
}


def fetch_page(page: int) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                ALADIN_URL,
                params={
                    "ttbkey": ALADIN_TTB_KEY,
                    "QueryType": "Bestseller",
                    "MaxResults": MAX_RESULTS,
                    "start": page,
                    "SearchTarget": "Book",
                    "output": "js",
                    "Version": "20131101",
                },
                timeout=REQUEST_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data = resp.json()

            if "errorCode" in data:
                raise RuntimeError(
                    f"알라딘 API 오류: {data.get('errorMessage')} (code={data.get('errorCode')})"
                )

            return data.get("item", [])
        except (requests.exceptions.RequestException, RuntimeError) as e:
            last_error = e
            print(f"[Aladin] {page}페이지 요청 실패 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)

    raise RuntimeError(f"알라딘 API {page}페이지 요청이 {MAX_RETRIES}번 모두 실패했습니다") from last_error


def fetch_bestseller_list() -> list[dict]:
    """1·2페이지를 합쳐 상위 100권. itemId 로 중복을 거른다(페이지 경계가 겹칠 때 대비)."""
    books: list[dict] = []
    seen: set = set()
    for page in range(1, PAGES + 1):
        for b in fetch_page(page):
            key = b.get("itemId")
            if key in seen:
                continue
            seen.add(key)
            books.append(b)
    return books


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    items = fetch_bestseller_list()
    total = len(items)
    if total == 0:
        raise RuntimeError("알라딘 베스트셀러 목록을 받아오지 못했습니다")

    economy_books = [
        item
        for item in items
        if ECONOMY_CATEGORY_KEYWORD in (item.get("categoryName") or "")
    ]
    ratio = len(economy_books) / total * 100

    print(f"[Aladin] 종합 베스트셀러 {total}권 중 경제경영 {len(economy_books)}권")
    for book in economy_books:
        print(f"  #{book.get('bestRank')} {book.get('title')} ({book.get('categoryName')})")

    score = round(ratio, 2)
    print(f"[Aladin] 경제·재테크 도서 비중: {score}%")

    today = date.today().isoformat()
    client.table("indicator_values").upsert(
        {"indicator_id": indicator_id, "date": today, "raw_value": score},
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score}")


if __name__ == "__main__":
    main()
