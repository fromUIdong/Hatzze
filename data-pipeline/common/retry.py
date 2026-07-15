"""네트워크 재시도용 지수 백오프 지연 계산 — KRX/ECOS 공통.

해외(GitHub Actions) 러너에서 한국 정부 API(KRX/ECOS)로의 연결이 간헐적으로
타임아웃되므로, 고정 간격 재시도보다 지수 백오프로 한 실행 안에서 회복 확률을
높인다. base_sec에서 시작해 매 재시도마다 2배씩 늘리고 max_sec에서 상한을 둔다
(예: base=2, max=20 → 2, 4, 8, 16, 20, 20 …).
"""

from __future__ import annotations


def backoff_delay(attempt: int, base_sec: float = 2.0, max_sec: float = 20.0) -> float:
    """1-based attempt(방금 실패한 시도 번호)에 대한 다음 재시도까지의 지연(초).

    attempt=1 → base_sec, 2 → 2*base_sec, … max_sec에서 상한.
    """
    return min(base_sec * (2 ** (attempt - 1)), max_sec)
