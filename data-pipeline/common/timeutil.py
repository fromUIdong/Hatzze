"""시간대 유틸.

GitHub Actions 러너는 UTC로 동작해서 date.today()가 UTC 날짜를 준다. 그런데
KRX·네이버 뉴스·디시인사이드 같은 국내 소스의 날짜(게시 시각)는 KST 기준이라,
UTC 날짜와 하루 어긋날 수 있다 — 특히 KST 이른 아침(=UTC로는 전날 밤)에 실행되면
"오늘"(UTC)이 국내 소스의 "오늘"(KST)보다 하루 뒤처진다. 이 경우 오늘자 콘텐츠가
하나도 매칭되지 않아 감성 지수가 0으로 잘못 계산되는 버그가 있었다.

국내 소스 기준 '오늘'이 필요한 곳에서는 date.today() 대신 today_kst()를 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    """UTC 러너에서도 한국 기준 오늘 날짜를 반환한다."""
    return datetime.now(KST).date()


def business_days(start: date, end: date):
    """start~end(양끝 포함) 사이의 평일을 순서대로 내놓는다.

    KRX는 주말에 데이터가 없어 조회해봐야 빈 응답이라, 백필하는 fetch 스크립트들이
    주말을 건너뛸 때 쓴다. 공휴일까지는 거르지 않는다 — 휴장일은 응답이 비어 있어
    호출부가 자연히 건너뛰므로, 휴장일 달력을 따로 들고 있을 필요가 없다.
    """
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon ... 4=Fri
            yield current
        current += timedelta(days=1)
