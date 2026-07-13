"""KRX Open API(data-dbg.krx.co.kr) 요청 공통 재시도 헬퍼.

GitHub Actions 실행 환경(해외 클라우드)에서 한국 서버로 요청을 보낼 때 가끔
연결 자체가 타임아웃/실패하는 경우가 있다 — ECOS에서 먼저 발견해
fetch_buffett_index.py에 재시도 로직을 넣었고, fetch_leverage_etf_volume.py도
KRX 요청에 자체 재시도 로직(_get_with_retry)을 갖고 있었다. 이 두 재시도
로직이 스크립트마다 따로 구현돼 있었는데, 매일 워크플로우 실행 중 서로 다른
스크립트가 번갈아 이런 네트워크 타임아웃으로 실패하는 걸 확인하고(2026-07-13
확인, 매일 다른 스텝이 실패) 재시도 로직이 없던 나머지 KRX 호출 스크립트들
(fetch_kospi_high_gap.py, fetch_kospi_volume.py, fetch_kosdaq_ratio.py,
fetch_vkospi.py, fetch_market_cap_concentration.py, fetch_buffett_index.py의
시가총액 조회)에도 동일하게 적용하기 위해 공통 헬퍼로 뽑아냈다.

재시도 대상은 두 가지다: (1) 연결 자체가 실패하는 경우(타임아웃, 연결 거부 등,
requests.exceptions.RequestException), (2) 서버가 5xx(500/503 등 일시적 서버
오류)를 반환하는 경우. 둘 다 KRX 쪽의 일시적 문제일 가능성이 높아 몇 초 간격으로
재시도하고, 끝까지 안 되면 None을 반환해 호출자가 그 날짜만 건너뛰게 한다.

반면 401 같은 4xx는 재시도하지 않고 그대로 반환한다 — 인증/권한 문제처럼
재시도해도 결과가 안 바뀌는 상황이라, 호출자가 상태 코드를 보고 명확한 안내
메시지를 내도록 넘긴다.
"""

from __future__ import annotations

import time

import requests

from common.config import KRX_API_KEY

KRX_REQUEST_TIMEOUT_SEC = 15
KRX_MAX_RETRIES = 3
KRX_RETRY_DELAY_SEC = 3


def krx_get(url: str, bas_dd: str) -> requests.Response | None:
    """basDd 파라미터로 KRX API에 GET 요청을 보낸다.

    연결 실패(타임아웃 등)나 5xx 서버 오류는 최대 KRX_MAX_RETRIES번 재시도하고,
    그래도 안 되면 None을 반환한다 — 호출자는 이 날짜만 건너뛰면 되고, 스크립트
    전체를 실패시키지 않아도 된다. 4xx(401 등)는 재시도 없이 그대로 반환한다.
    """
    last_error: str | None = None
    for attempt in range(1, KRX_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params={"basDd": bas_dd},
                headers={"AUTH_KEY": KRX_API_KEY},
                timeout=KRX_REQUEST_TIMEOUT_SEC,
            )
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(f"[KRX] {bas_dd} 요청 실패 ({attempt}/{KRX_MAX_RETRIES}): {e}")
            if attempt < KRX_MAX_RETRIES:
                time.sleep(KRX_RETRY_DELAY_SEC)
            continue

        if resp.status_code >= 500:
            last_error = f"서버 오류 {resp.status_code}"
            print(f"[KRX] {bas_dd} {last_error} ({attempt}/{KRX_MAX_RETRIES})")
            if attempt < KRX_MAX_RETRIES:
                time.sleep(KRX_RETRY_DELAY_SEC)
            continue

        return resp

    print(
        f"[WARNING] {bas_dd} 요청이 {KRX_MAX_RETRIES}번 모두 실패해 이 날짜는 "
        f"건너뜁니다: {last_error}"
    )
    return None
