"""26개 지표의 종합점수(햇쩨 지수) 가중치 — 코드가 소스 오브 트루스.

daily_score.score = Σ(weight_i × capped_progress_i) / Σ(weight_i). 예전엔 이 weight를
Supabase indicators.weight에서만 읽어 버전 관리가 안 됐는데, 재현성·이력을 위해 여기로
옮겼다. calculate_score.get_indicator가 DB weight 대신 이 값을 쓴다(여기 없는 slug은
DB weight로 폴백). 값을 바꾸면 이 파일만 고치고 파이프라인을 재실행하면 된다.

배정 원리: 하락을 앞서는 '소매-과열(선행)' 지표(거래대금·업비트·초보검색·디씨·레버리지)는
높게, 느리거나 후행인 매크로·소비(버핏·us10y·금리차·명품·오마카세·날씨)는 낮게 둔다.
현재 값은 원리 기반 시작점이며 백테스트로 계속 다듬는다(2026-07-17 1차 적용).
"""

INDICATOR_WEIGHTS = {
    # 선행·핵심 (소매 과열 / 가격 모멘텀)
    "kospi_high_gap": 4.0,          # 가격 기반 선행·동행
    "kospi_volume_surge": 4.0,      # 소매 과열(선행)
    "buffett_index": 3.0,           # 밸류 앵커지만 느림·후행
    "vkospi": 3.0,                  # 방심(동행)
    "top10_market_cap_concentration": 3.0,  # 구조·동행
    "upbit_speculation_index": 3.0, # 소매 과열(선행)
    "naver_search_trend": 3.0,      # 소매 과열(선행)
    "leverage_etf_volume": 3.0,     # 레버리지 투기(선행)
    # 동행 / 보조
    "us10y": 2.0,                   # 후행 매크로(+ 방향 재검토 대상)
    "kospi_asia_relative_strength": 2.0,  # 동행 모멘텀
    "kospi_gold_ratio": 2.0,        # 동행
    "kosdaq_kospi_ratio": 2.0,      # 투기 선행·동행
    "usdkrw_volatility": 2.0,       # 방심(동행)
    "vix_vkospi_spread": 2.0,       # 방심(동행)
    "dcinside_post_count": 2.0,     # 감성(선행)
    "news_sentiment": 2.0,          # 감성(선행·동행)
    "market_actions_30d": 1.5,      # 동행(CB=스트레스 시점)
    "copper_price_momentum": 1.5,   # 매크로 동행
    "small_business_crisis_index": 1.5,  # 파생(선행+가격)
    "yield_curve_spread": 1.5,      # 후행 매크로
    "bestseller_finance_ratio": 1.0,     # 선행이나 갱신 느림
    "youtube_finance_search_views": 1.0, # 소매(선행)
    "github_trading_bot_repos": 1.0,     # 표본 부족, 관찰
    # 참고용 (후행 소비 / 노이즈)
    "luxury_consumption_index": 0.5,     # 후행 소비
    "fine_dining_search_index": 0.5,     # 후행 소비
    "weather_sunshine_index": 0.5,       # 노이즈
}
