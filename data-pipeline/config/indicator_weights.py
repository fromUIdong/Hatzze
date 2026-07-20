"""26개 지표의 종합점수(햇쩨 지수) 가중치 — 코드가 소스 오브 트루스.

daily_score.score = Σ(weight_i × capped_progress_i) / Σ(weight_i). 예전엔 이 weight를
Supabase indicators.weight에서만 읽어 버전 관리가 안 됐는데, 재현성·이력을 위해 여기로
옮겼다. calculate_score.get_indicator가 DB weight 대신 이 값을 쓴다(여기 없는 slug은
DB weight로 폴백). 값을 바꾸면 이 파일만 고치고 파이프라인을 재실행하면 된다.

배정 원리(2026-07-17 재편성): 시장이 얼마나 과열/침체됐는지를 가장 직접 반영하는 3축 —
가격(전고점 대비 위치)·거래량·예탁금 — 에 큰 무게를 싣는다. 밸류(버핏)는 느리고 현재
국면 반영이 약해 낮춘다. 매매 안전장치(매수 사이드카 빈발)는 실제 과열의 하드 데이터라
올린다. 표본 1일 노이즈(github)·후행 소비(명품·오마카세)는 낮춘다. 부트스트랩 지표는 데이터
쌓이면 재조정. ※ put_call_ratio는 옵션 API 승인(2026-07-20)으로 실데이터 수집을 시작했고
카드에도 실값이 나오지만, **점수 편입은 아직 보류**다 — 여기에 넣으면 종합점수 분모가
바뀌어 백테스트로 맞춘 기존 가중치 균형이 흔들린다. 편입하려면 임계값(indicator_thresholds)
설계와 재검증을 함께 해야 한다.
"""

INDICATOR_WEIGHTS = {
    # 핵심 3축 (가격·거래량·예탁금) — 과열/침체 국면을 가장 직접 반영
    "kospi_high_gap": 4.5,          # 가격: 전고점 대비 위치(과열 위치 최강 신호)
    "kospi_volume_surge": 4.0,      # 거래량: 폭증=흥분 / 침체=이탈
    "investor_deposit": 3.0,        # 예탁금: 대기 매수 실탄(단 방향 다소 애매 → 3축 중 하위)
    # froth 심리·투기
    "vkospi": 3.0,                  # 공포/방심
    "naver_search_trend": 3.0,      # 초보 유입
    "individual_net_buy": 2.5,      # 개미 매매(고점 물림)
    "upbit_speculation_index": 2.5, # 코인 투기
    "leverage_etf_volume": 2.5,     # 레버리지·선물 미결제약정 투기
    "turnover_concentration": 2.0,  # 거래대금 쏠림
    "kosdaq_kospi_ratio": 2.0,      # 잡주 투기
    "kospi_gold_ratio": 2.0,        # 위험선호
    "buffett_index": 2.0,           # 밸류(느림·비타이밍) → 축소
    "dcinside_post_count": 2.0,     # 커뮤니티 여론
    "market_actions_30d": 2.0,      # 매수 사이드카=과열 하드데이터 → 상향
    "news_sentiment": 1.5,          # 언론 낙관
    "usdkrw_volatility": 1.5,       # FX 방심
    "brokerage_app_rank": 1.5,      # 증권 앱 유입
    "small_business_crisis_index": 1.5,  # 실물–증시 괴리
    "vix_vkospi_spread": 1.0,       # 한국만 방심
    "kospi_asia_relative_strength": 1.0, # 상대 모멘텀
    "youtube_finance_search_views": 1.0, # 콘텐츠 열기
    "bestseller_finance_ratio": 1.0,     # 책 열풍(느림)
    "github_trading_bot_repos": 0.5,     # 표본 1일 노이즈
    "luxury_consumption_index": 0.5,     # 후행 소비
    "fine_dining_search_index": 0.5,     # 후행 소비
}
