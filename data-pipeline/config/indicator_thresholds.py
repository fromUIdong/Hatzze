"""17개 지표의 Hit/progress 기준값(threshold) 설정.

percentile 기반(과거 데이터의 상위/하위 N% 지점)은 데이터가 1년 가까이 쌓일
때까지 기준선이 계속 흔들려서, 리서치·논리 기반으로 정한 고정 기준값으로
전환했다. 기준값을 조정하고 싶을 땐 이 파일만 고치면 되고
calculate_score.py의 계산 로직(compute_hit/compute_progress 등)은 건드릴
필요가 없다.

각 항목의 필드:
- kind: "fixed"(고정 기준값) 또는 "cumulative_average"(youtube_finance_search_views
  전용 — 과거 percentile 대신 "오늘 포함 지금까지 쌓인 값의 평균"을 매일
  다시 계산해 기준선으로 쓴다. calculate_score.py의 compute_threshold 참고)
- threshold: kind="fixed"일 때의 기준값. current(현재값)가 이 값 이상(또는
  direction="low"면 이하)이면 Hit.
- direction: "high"(기본값, 생략 가능 — 현재값이 기준값 이상이면 Hit) 또는
  "low"(현재값이 기준값 이하면 Hit — vkospi/usdkrw_volatility처럼 낮을수록
  시장이 방심하고 있다는 과열 신호인 지표)

unit 참고(threshold와 raw_value가 같은 단위인지 확인용): kospi_volume_surge와
leverage_etf_volume은 "억원" 단위라 500000 = 50조원, 40000 = 4조원이다.
"""

INDICATOR_THRESHOLDS = {
    "buffett_index": {"kind": "fixed", "threshold": 100.0},
    "kospi_high_gap": {"kind": "fixed", "threshold": 0.0},
    "us10y": {"kind": "fixed", "threshold": 5.0},
    "naver_search_trend": {"kind": "fixed", "threshold": 70.0},
    "dcinside_post_count": {"kind": "fixed", "threshold": 25.0},
    "kospi_volume_surge": {"kind": "fixed", "threshold": 500_000.0},  # 억원 (50조원)
    "vkospi": {"kind": "fixed", "threshold": 20.0, "direction": "low"},
    "news_sentiment": {"kind": "fixed", "threshold": 35.0},
    "kospi_gold_ratio": {"kind": "fixed", "threshold": 2.2},
    "kosdaq_kospi_ratio": {"kind": "fixed", "threshold": 0.14},
    "usdkrw_volatility": {"kind": "fixed", "threshold": 0.25, "direction": "low"},
    "leverage_etf_volume": {"kind": "fixed", "threshold": 40_000.0},  # 억원 (4조원)
    "bestseller_finance_ratio": {"kind": "fixed", "threshold": 16.0},
    "youtube_finance_search_views": {"kind": "cumulative_average"},
    # weather_sunshine_index: threshold=8은 "전운량 2 이하(구름 거의 없음)"에
    # 해당하는 맑음지수다. 다만 이건 계절과 무관하게 고정된 값이라는 한계가
    # 있다 — 예를 들어 장마철(6~7월)엔 맑은 날 자체가 드물어 이 기준을 거의
    # 못 넘기고, 반대로 건조한 가을/겨울엔 자주 넘길 수 있다. 계절별 기준선을
    # 따로 두려면 이 단일 threshold로는 안 되고 월별/계절별 분기가 필요하다.
    "weather_sunshine_index": {"kind": "fixed", "threshold": 8.0},
    # kospi_asia_relative_strength: threshold=10(%p)은 "코스피 20거래일
    # 수익률이 일본·홍콩·대만 평균보다 10%p 이상 앞선다"를 뚜렷한 쏠림으로
    # 보는 논리적 추정치다 — 실측 분포(예: 최근 1~2년 이 지표의 실제
    # 최댓값·분산)를 아직 확인 못 했으니, 데이터가 쌓이면 재조정이 필요할
    # 수 있다.
    "kospi_asia_relative_strength": {"kind": "fixed", "threshold": 10.0},
    # naver_search_trend와 동일한 논리: 조회 기간 내 최고치의 70% 수준을
    # "이례적으로 관심이 쏠린" 구간으로 본다.
    "luxury_consumption_index": {"kind": "fixed", "threshold": 70.0},
}

# 현재값이 음수로 나올 수 있는 지표(감성 점수류)는 음수를 "역방향 과열"로 해석하지
# 않고 그냥 progress=0으로 바닥 처리한다. current/threshold*100 공식을 그대로 쓰면
# 음수 현재값이 음수 progress를 만들어 화면에 "-12%"처럼 어색하게 표시되기 때문.
NEGATIVE_CURRENT_CLAMP_SLUGS = {"dcinside_post_count", "news_sentiment"}
