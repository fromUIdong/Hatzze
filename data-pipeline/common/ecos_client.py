"""한국은행 ECOS(ecos.bok.or.kr) 통계 조회 공통 헬퍼.

ECOS 는 GitHub Actions(해외 클라우드) 실행 환경에서 가끔 연결 자체가 타임아웃/실패
한다 — fetch_buffett_index.py 가 자체 재시도로 대응하고 있었는데, CCSI(소비자심리지수)
도 ECOS 를 쓰게 되면서 같은 로직을 공유하려고 뽑아냈다. KRX 의 common/krx_client.py 와
같은 이유·같은 구조다.
"""

from __future__ import annotations

import time

import requests

from common.config import ECOS_API_KEY
from common.retry import backoff_delay

ECOS_BASE_URL = "https://ecos.bok.or.kr/api"
ECOS_REQUEST_TIMEOUT_SEC = 30
ECOS_MAX_RETRIES = 6
ECOS_RETRY_BASE_DELAY_SEC = 2
ECOS_RETRY_MAX_DELAY_SEC = 20


class EcosUnavailableError(RuntimeError):
    """재시도를 다 쓰고도 ECOS 에 닿지 못했을 때(네트워크 문제)."""


def fetch_ecos_payload(url: str) -> dict:
    """URL 을 그대로 GET 해 JSON 을 돌려준다. 연결 실패는 재시도, 끝내 실패하면 예외."""
    last_error: Exception | None = None
    for attempt in range(1, ECOS_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=ECOS_REQUEST_TIMEOUT_SEC)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"[ECOS] 요청 실패 ({attempt}/{ECOS_MAX_RETRIES}): {e}")
            if attempt < ECOS_MAX_RETRIES:
                time.sleep(backoff_delay(attempt, ECOS_RETRY_BASE_DELAY_SEC, ECOS_RETRY_MAX_DELAY_SEC))

    raise EcosUnavailableError(
        f"ECOS API 요청이 {ECOS_MAX_RETRIES}번 모두 실패했습니다 (타임아웃/연결 실패 — "
        "코드 문제가 아니라 네트워크 문제로 추정됩니다)"
    ) from last_error


def statistic_search(
    stat_code: str, cycle: str, start: str, end: str, item_code: str = "", count: int = 100
) -> list[dict]:
    """StatisticSearch 를 호출해 row 리스트를 돌려준다(TIME 오름차순, 값 있는 것만).

    item_code 를 주면 그 항목만, 안 주면 통계표의 모든 항목을 받는다.
    """
    path = f"{ECOS_BASE_URL}/StatisticSearch/{ECOS_API_KEY}/json/kr/1/{count}/{stat_code}/{cycle}/{start}/{end}"
    if item_code:
        path += f"/{item_code}"
    payload = fetch_ecos_payload(path)

    block = payload.get("StatisticSearch")
    if not block:
        # ECOS 는 조회 결과가 없을 때 {"RESULT": {"CODE": "INFO-200", ...}} 를 준다.
        raise RuntimeError(f"ECOS 응답에 StatisticSearch 가 없습니다: {payload}")

    rows = [r for r in block.get("row", []) if r.get("DATA_VALUE") not in (None, "")]
    rows.sort(key=lambda r: r["TIME"])
    return rows
