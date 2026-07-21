"""네이버 오픈 API 호출 공통 — NAVER API HUB(네이버 클라우드) 단일 경로.

**배경.** 개발자센터의 Search / Search Trend / Shopping Insight 는 2026-07-30 부로
신규 접수가 끊기고 기존 이용자도 2027-06-30 까지만 쓸 수 있다. 그 뒤로는 NAVER
API HUB 로 옮겨야 한다. (2026-07-31 에 유예 없이 즉시 끊기는 '쇼핑'·'책'·'학술정보'
는 우리가 안 쓴다. finance.naver.com 스크래핑 두 곳은 API 가 아니라 무관하다.)

**우리가 쓰는 두 API.** 콘솔에서 Application 하나에 둘 다 등록하면 키 하나로 호출된다.

    NAVER 검색 > 뉴스        → /search/v1/news        (GET)
    Data Lab  > 검색어트렌드 → /search-trend/v1/search (POST)

경로를 찾을 때 헤맸던 부분이라 적어 둔다: 검색어트렌드의 경로 카테고리는 콘솔 표기
('Data Lab')를 따르지 않고 **search-trend** 다. datalab/dataLab/data-lab 조합은 전부
404 였다. 게이트웨이는 **미구독이면 401, 없는 경로면 404** 를 주므로 둘을 구분해
진단하면 된다.

**응답 형식.** 구 개발자센터 API 와 동일하다 — 같은 요청으로 대조해 JSON 이 완전히
같음을 확인했다(2026-07-22). 그래서 호출부의 파싱 코드는 그대로 두고 호출 지점만
이 모듈로 모았다.
"""

from __future__ import annotations

import requests

from common.config import NAVER_HUB_KEY, NAVER_HUB_KEY_ID

BASE = "https://naverapihub.apigw.ntruss.com"
NEWS_URL = f"{BASE}/search/v1/news"
SEARCH_TREND_URL = f"{BASE}/search-trend/v1/search"


def _headers(json_body: bool = False) -> dict:
    if not (NAVER_HUB_KEY_ID and NAVER_HUB_KEY):
        raise RuntimeError(
            "NAVER_HUB_KEY_ID / NAVER_HUB_KEY 가 없습니다. 네이버 클라우드 콘솔의 "
            "NAVER API HUB > Application > 인증 정보에서 발급한 값을 넣어 주세요."
        )
    h = {"X-NCP-APIGW-API-KEY-ID": NAVER_HUB_KEY_ID, "X-NCP-APIGW-API-KEY": NAVER_HUB_KEY}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _explain(resp: requests.Response, what: str) -> None:
    """진단이 필요한 상태코드에 무엇을 확인해야 하는지 붙여 준다."""
    if resp.status_code == 401:
        print(
            f"[Naver] {what} 401 — Application 에 해당 API 가 등록돼 있는지 "
            "(NAVER API HUB > Application > API 관리) 확인하세요."
        )
    elif resp.status_code == 404:
        print(f"[Naver] {what} 404 — 호출 경로가 바뀌었을 수 있습니다. NCP API 문서를 확인하세요.")


def search_news(params: dict, timeout: int = 10) -> requests.Response:
    """뉴스 검색. params: query / display / start / sort."""
    resp = requests.get(NEWS_URL, headers=_headers(), params=params, timeout=timeout)
    _explain(resp, "뉴스 검색")
    return resp


def search_trend(body: dict, timeout: int = 15) -> requests.Response:
    """검색어 트렌드. body: startDate / endDate / timeUnit / keywordGroups."""
    resp = requests.post(SEARCH_TREND_URL, headers=_headers(True), json=body, timeout=timeout)
    _explain(resp, "검색어 트렌드")
    return resp
