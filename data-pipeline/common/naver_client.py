"""네이버 오픈 API 호출 공통 — 개발자센터(구) ↔ 네이버 클라우드(신) 양쪽을 다룬다.

**배경.** 2026-07-30 24:00 부로 개발자센터의 Search / Search Trend / Shopping Insight
신규 접수가 끊기고, 기존 이용자도 2027-06-30 까지만 쓸 수 있다. 그 뒤로는 NAVER
API HUB(네이버 클라우드) 로 옮겨야 한다. 2026-07-31 에 유예 없이 즉시 끊기는 건
Search API 중 '쇼핑'·'책'·'학술정보' 인데, 우리는 셋 다 안 쓴다(뉴스만 쓴다).

**전환 상태 (2026-07-22 실측).**
- 데이터랩: 새 키로 HUB_DATALAB_URL 이 200 OK. 응답 JSON 이 구 API 와 **완전히 동일**
  해서(같은 요청으로 대조 확인) 호출부의 파싱 코드는 그대로 둔다.
- 뉴스: HUB_NEWS_URL 이 401 "A subscription to the API is required" — 경로는 맞고
  콘솔에서 해당 API 구독 신청이 안 된 상태다. 그래서 구독 전까지는 구 API 로
  폴백하고 경고를 남긴다. 구독이 끝나면 코드 변경 없이 저절로 새 API 를 탄다.

폴백은 '구독 안 됨(401)' 한 가지에만 적용한다. 그 외 오류는 그대로 올려 호출부의
재시도·에러 처리가 원래대로 동작하게 둔다 — 조용히 삼키면 문제를 못 본다.
"""

from __future__ import annotations

import requests

from common.config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_HUB_KEY,
    NAVER_HUB_KEY_ID,
)

LEGACY_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
LEGACY_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
# 뉴스는 API HUB, 데이터랩은 아직 AI·NAVER API 호스트에만 있다(HUB 호스트의 datalab
# 경로 후보 6종 모두 404 확인). 호스트가 갈리는 게 오타처럼 보이지만 실측 결과다.
HUB_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
HUB_DATALAB_URL = "https://naveropenapi.apigw.ntruss.com/datalab/v1/search"


def has_hub_keys() -> bool:
    return bool(NAVER_HUB_KEY_ID and NAVER_HUB_KEY)


def _hub_headers(json_body: bool = False) -> dict:
    h = {"X-NCP-APIGW-API-KEY-ID": NAVER_HUB_KEY_ID, "X-NCP-APIGW-API-KEY": NAVER_HUB_KEY}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _legacy_headers(json_body: bool = False) -> dict:
    h = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _needs_subscription(resp: requests.Response) -> bool:
    """새 플랫폼에서 '아직 구독 안 된 API' 를 부를 때의 응답인지."""
    return resp.status_code == 401 and "subscription" in resp.text.lower()


def datalab_search(body: dict, timeout: int = 15) -> requests.Response:
    """데이터랩 검색어 트렌드. 새 키가 있으면 새 플랫폼으로 보낸다."""
    if has_hub_keys():
        resp = requests.post(HUB_DATALAB_URL, headers=_hub_headers(True), json=body, timeout=timeout)
        if not _needs_subscription(resp):
            return resp
        print("[Naver] 데이터랩이 새 플랫폼에서 미구독 상태 — 구 API 로 폴백합니다.")
    return requests.post(LEGACY_DATALAB_URL, headers=_legacy_headers(True), json=body, timeout=timeout)


def search_news(params: dict, timeout: int = 10) -> requests.Response:
    """뉴스 검색. 새 키가 있고 구독까지 됐으면 새 플랫폼으로 보낸다."""
    if has_hub_keys():
        resp = requests.get(HUB_NEWS_URL, headers=_hub_headers(), params=params, timeout=timeout)
        if not _needs_subscription(resp):
            return resp
        print(
            "[Naver] 뉴스 검색 API 가 새 플랫폼에서 미구독 상태 — 구 API 로 폴백합니다. "
            "네이버 클라우드 콘솔에서 구독하면 자동으로 새 API 를 씁니다."
        )
    return requests.get(LEGACY_NEWS_URL, headers=_legacy_headers(), params=params, timeout=timeout)
