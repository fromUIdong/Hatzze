"""시간대 유틸.

GitHub Actions 러너는 UTC로 동작해서 date.today()가 UTC 날짜를 준다. 그런데
KRX·네이버 뉴스·디시인사이드 같은 국내 소스의 날짜(게시 시각)는 KST 기준이라,
UTC 날짜와 하루 어긋날 수 있다 — 특히 KST 이른 아침(=UTC로는 전날 밤)에 실행되면
"오늘"(UTC)이 국내 소스의 "오늘"(KST)보다 하루 뒤처진다. 이 경우 오늘자 콘텐츠가
하나도 매칭되지 않아 감성 지수가 0으로 잘못 계산되는 버그가 있었다.

국내 소스 기준 '오늘'이 필요한 곳에서는 date.today() 대신 today_kst()를 쓴다.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    """UTC 러너에서도 한국 기준 오늘 날짜를 반환한다."""
    return datetime.now(KST).date()


def business_days(start: date, end: date):
    """start~end(양끝 포함) 사이의 평일을 순서대로 내놓는다.

    KRX는 주말에 데이터가 없어 조회해봐야 빈 응답이라, 백필하는 fetch 스크립트들이
    주말을 건너뛸 때 쓴다. 공휴일까지는 거르지 않는다 — 휴장일 달력을 따로 들고
    있지 않아도 응답이 비어 있어 호출부가 자연히 건너뛴다. 다만 그 '빈 응답'을
    매번 다시 받아오지는 않도록 days_to_backfill 을 쓸 것(아래).
    """
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon ... 4=Fri
            yield current
        current += timedelta(days=1)


DEFAULT_RECENT_BUSINESS_DAYS = 15  # 약 3주 — 웬만한 연휴·장애 공백을 덮는다


def days_to_backfill(
    existing_dates: set[str],
    today: date,
    *,
    bootstrap_days: int,
    recent_days: int = DEFAULT_RECENT_BUSINESS_DAYS,
) -> list[date]:
    """아직 채우지 않은 영업일 목록 — 매 실행 조회할 날짜를 정한다.

    행이 하나도 없으면(최초 실행) bootstrap_days 만큼 전부 훑고, 이미 쌓여 있으면
    **최근 recent_days 영업일만** 본다.

    창을 좁히는 이유: business_days 는 공휴일을 못 걸러서, 광복절·추석·설처럼
    영영 데이터가 없을 날짜가 '아직 안 채운 영업일'로 계속 잡힌다. 1년 창을 그대로
    쓰면 그 18일을 **매 실행마다 KRX에 다시 물어보게 된다**(6개 스크립트 × 하루 2회
    = 200회 넘는 헛호출). 최근 창만 보면 옛 공휴일은 자연히 빠지고, 그 안에서
    생긴 진짜 공백은 그대로 메워진다.

    3주보다 오래 밀린 공백은 이 경로로 안 메워진다 — 그 정도로 오래 멈추면
    check_freshness.py 가 먼저 알리고, BACKFILL_FULL=1 로 전체 창을 다시 훑으면 된다.
    """
    if not existing_dates or os.getenv("BACKFILL_FULL") == "1":
        start = today - timedelta(days=bootstrap_days)
        return [d for d in business_days(start, today) if d.isoformat() not in existing_dates]

    # 최근 recent_days 영업일 — 주말·연휴를 감안해 넉넉한 달력 구간에서 뒤에서 자른다.
    window = list(business_days(today - timedelta(days=recent_days * 3), today))[-recent_days:]
    return [d for d in window if d.isoformat() not in existing_dates]
