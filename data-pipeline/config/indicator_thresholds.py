"""지표별 Hit/progress 기준값(threshold) 설정.

percentile 기반(과거 데이터의 상위/하위 N% 지점)은 데이터가 1년 가까이 쌓일
때까지 기준선이 계속 흔들려서, 리서치·논리 기반으로 정한 고정 기준값으로
전환했다. 기준값을 조정하고 싶을 땐 이 파일만 고치면 되고
calculate_score.py의 계산 로직(compute_progress 등)은 건드릴
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

unit 참고(threshold와 raw_value가 같은 단위인지 확인용): kospi_volume_surge는
"억원" 단위라 500000 = 50조원이다.
"""

INDICATOR_THRESHOLDS = {
    # 버핏지수: floor-ceiling — 시총/GDP 105%=0%(정상), 235%=100%(초고온). 재보정 배경:
    # 1년 분포상 100%는 사실상 바닥(p10)이라 늘 최대치로 고정됐고, 235%(p90, 상위10%)
    # 이상에서만 "과열→하락" 신호가 나왔다. ceiling은 기여 상한이지 표시값 상한이 아니다.
    "buffett_index": {"kind": "fixed", "threshold": 235.0, "floor": 105.0},
    # kospi_high_gap: ATH 근접도. 피스와이즈 — ATH −3%~0% = 75~100%(초고온을 근처로 좁게),
    # floor −30%~−3% = 0~75%. floor=−30%는 "약세장(−20%)도 아직 과열 끼가 남는" 시장 맥락
    # (−20%인데 약세장 느낌 안 남)을 반영해 크래시급에서만 저온으로 본다.
    "kospi_high_gap": {"kind": "fixed", "threshold": 0.0, "floor": -30.0, "kink": -3.0},
    "naver_search_trend": {"kind": "fixed", "threshold": 70.0},
    "dcinside_post_count": {"kind": "fixed", "threshold": 25.0},
    # kospi_volume_surge: 절대 거래대금이 아니라 "30일 평균 대비 %"(details.surge_pct)로 판단.
    # 평소(0%)=상온, +20%↑=초고온. floor surge −20%=0%, ceiling surge +33.3%=100%
    # (→ 0%→37.5%, +20%→75%). 절대값은 baseline drift로 낡아서 상대로 전환.
    "kospi_volume_surge": {"kind": "fixed", "threshold": 500_000.0, "relative_surge": {"floor": -20.0, "ceil": 33.33, "hit": 20.0}},
    "vkospi": {"kind": "fixed", "threshold": 20.0, "direction": "low"},
    "news_sentiment": {"kind": "fixed", "threshold": 35.0},
    "kospi_gold_ratio": {"kind": "fixed", "threshold": 2.2},
    "kosdaq_kospi_ratio": {"kind": "fixed", "threshold": 0.14},
    "usdkrw_volatility": {"kind": "fixed", "threshold": 0.25, "direction": "low"},
    # put_call_ratio: 풋 거래량 / 콜 거래량. 콜(상승 베팅)이 많을수록 값이 작아지므로
    # direction="low" — 낮을수록 탐욕(과열)이다. ※ direction 은 여기와 fetch 스크립트의
    # INDICATOR_META 양쪽에 있어야 한다(점수 계산은 여기를, 카드의 "이하/이상" 표기는
    # DB 컬럼을 본다).
    # 실측 242영업일: 최소 0.459 / p25 0.861 / 중앙 0.947 / p75 1.062 / 최대 3.226.
    # threshold=0.50 이면 중앙값이 progress 53%(상온)에 놓이고, Hit(≥75 → 0.667 이하)
    # 도달이 10일(4.1%)로 market_actions_30d(4.3%)와 같은 엄격도가 된다.
    # 0.55 로 올리면 Hit 이 6.6%로 헐거워지고, 0.45 면 2.1%로 사실상 안 켜진다.
    "put_call_ratio": {"kind": "fixed", "threshold": 0.50, "direction": "low"},
    # leverage_etf_volume: raw_value가 fetch_leverage_etf_volume.py 안에서 이미
    # ETF거래대금_progress와 선물 미결제약정_progress의 가중 산술평균으로 계산된
    # 진행률 값이라(upbit_speculation_index와 동일한 설계), threshold=100은
    # "두 서브 신호 모두 자기 기준선에 도달한 수준"을 의미한다.
    "leverage_etf_volume": {"kind": "fixed", "threshold": 100.0},
    "bestseller_finance_ratio": {"kind": "fixed", "threshold": 16.0},
    # youtube: 기준선=누적 평균(compute_threshold). 예전엔 progress=현재/평균×100이라 "평균=100%
    # =정상"인데도 과열 100%로 잡혀(평균 이하도 hit) 점수를 부풀렸다. surge_map으로 "평균 대비
    # 급증(%)"을 과열도로 매핑한다 — 평균(급증 0%)=진행률 50(상온), +25%=75(초고온 진입/Hit),
    # +50%=100. 카드의 "평소 대비 X배"는 threshold(=평균) 그대로라 안 깨진다.
    "youtube_finance_search_views": {"kind": "cumulative_average", "surge_map": {"floor": -50.0, "ceil": 50.0}},
    # kospi_asia_relative_strength: threshold=10(%p)은 "코스피 20거래일
    # 수익률이 일본·홍콩·대만 평균보다 10%p 이상 앞선다"를 뚜렷한 쏠림으로
    # 보는 논리적 추정치다 — 실측 분포(예: 최근 1~2년 이 지표의 실제
    # 최댓값·분산)를 아직 확인 못 했으니, 데이터가 쌓이면 재조정이 필요할
    # 수 있다.
    "kospi_asia_relative_strength": {"kind": "fixed", "threshold": 10.0},
    # naver_search_trend와 동일한 논리: 조회 기간 내 최고치의 70% 수준을
    # "이례적으로 관심이 쏠린" 구간으로 본다.
    "luxury_consumption_index": {"kind": "fixed", "threshold": 70.0},
    # 아래 둘도 naver_search_trend와 동일한 논리(조회 기간 내 최고치의 70%
    # 수준을 과열로 봄). small_business_crisis_index는 검색량이 높을수록
    # "실물경제 위기 신호가 뚜렷하다"는 뜻이라 direction은 그대로 high다 —
    # 다른 지표들의 "높을수록 시장 과열"과는 의미가 다르지만, 계산 방식(현재값이
    # 기준값 이상이면 Hit)은 동일하다.
    "fine_dining_search_index": {"kind": "fixed", "threshold": 70.0},
    "small_business_crisis_index": {"kind": "fixed", "threshold": 70.0},
    # upbit_speculation_index: raw_value 자체가 이미 fetch 스크립트 안에서
    # 두 서브지표(김치프리미엄, 거래대금 급증도)의 가중 산술평균으로 계산된
    # "진행률에 가까운" 값이라, threshold=100은 "두 신호 모두 자기 기준선에
    # 도달한 수준"을 의미한다. 여기서 다시 나누는 건 사실상 그대로 통과시키는
    # 것에 가깝다.
    "upbit_speculation_index": {"kind": "fixed", "threshold": 100.0},
    # github_trading_bot_repos: 사전 추정 근거가 전혀 없는 완전히 새로운 지표라
    # 실행해서 나온 첫 관측값(81건, 2026-07-11)을 기준점으로 삼았다. threshold=150은
    # 그 값의 약 1.85배 — "하루 평균보다 확연히 많이 튀는" 수준을 잠정적으로 잡은
    # 것이라, 표본이 하루뿐이라는 한계가 크다. 며칠~몇 주치 데이터가 쌓이면 실제
    # 분포(평균, 표준편차)를 보고 반드시 재조정해야 한다.
    "github_trading_bot_repos": {"kind": "fixed", "threshold": 150.0},
    # brokerage_app_rank: 애플 금융 무료앱 차트 내 증권 앱들의 froth 점수(Σ(101-순위)).
    # github처럼 사전 분포가 없어 첫 관측값(462점, 2026-07-17 — 증권 앱 7개 차트인, 최고 10위)을
    # 기준점으로 삼았다. threshold=800은 "증권 앱들이 최상위로 도배(대부분 top20~1위)"되는
    # 과열 수준의 잠정 추정치라, 며칠~몇 주 쌓이면 실제 분포로 반드시 재조정해야 한다.
    "brokerage_app_rank": {"kind": "fixed", "threshold": 800.0},
    # individual_net_buy: 코스피 개인 순매수의 최근 5거래일 누적(억원). 개미가 순매수로
    # 몰릴수록 froth. threshold=100,000억(+10조)은 "개미가 5일간 대량 순매수"하는 과열의
    # 잠정 추정치 — 실측 분포가 쌓이면 재조정 필요. 순매도(음수)는 progress 0으로 바닥.
    "individual_net_buy": {"kind": "fixed", "threshold": 100_000.0},
    # investor_deposit: 고객예탁금(대기 매수 자금, 억원). 수준이 구조적으로 크고 우상향하므로
    # youtube처럼 '최근 평균(cumulative_average) 대비 급증(surge_map)'으로 froth를 본다 —
    # 평균이면 상온(50), 평균 대비 +15%면 초고온(100). 예탁금 변동폭이 작아 ±15%로 잡았다.
    "investor_deposit": {"kind": "cumulative_average", "surge_map": {"floor": -15.0, "ceil": 15.0}},
    # turnover_concentration: 상위10 종목 거래대금 비중(%). '평균 대비 상대'로 보면 70%+라도
    # 평균 근처면 시원하게 나와 직관과 어긋나(Hun 피드백), 절대값 floor-ceiling으로 전환한다.
    # 60%(=폭넓은 참여, 저온) ~ 80%(=극단 쏠림, 초고온). 이러면 70%가 과열도 50%(고온 주황)
    # 근처로, "70% 이상이면 충분히 높다"는 감각과 맞는다. 단 KOSPI는 구조적으로 70%대라
    # 이 지표가 평소에도 고온으로 자주 뜬다(의도된 트레이드오프).
    "turnover_concentration": {"kind": "fixed", "threshold": 80.0, "floor": 60.0},
    # market_actions_30d: raw_value = 매수 / (매수 + 매도 + CB + 2) — 안전장치가 걸렸을 때
    # 매수 사이드카가 차지한 비중(0~1). 2026-07-20에 차이값(매수-매도-CB×4, 0클램프)에서
    # 교체했다 — 옛 공식은 1년 370일 중 318일(86%)이 0으로 뭉개져 정보를 못 냈다(안전장치가
    # 아예 없던 날은 46%뿐이라 40%p는 실제 이벤트가 있었는데도 버려졌다).
    # threshold=0.50은 1년 370일 중 16일(4.3%)만 도달해 **옛 임계값 2.0의 엄격도(16일,
    # 4.4%)를 그대로 재현**한다 — 공식을 바꾸되 지표가 종합점수에 기여하는 강도는
    # 유지하려는 의도다. 참고 분위수: p75=0.31, p90=0.43, p95=0.46, 최대=0.56.
    "market_actions_30d": {"kind": "fixed", "threshold": 0.50},
}

# 현재값이 음수로 나올 수 있는 지표(감성 점수류)는 음수를 "역방향 과열"로 해석하지
# 않고 그냥 progress=0으로 바닥 처리한다. current/threshold*100 공식을 그대로 쓰면
# 음수 현재값이 음수 progress를 만들어 화면에 "-12%"처럼 어색하게 표시되기 때문.
NEGATIVE_CURRENT_CLAMP_SLUGS = {
    "dcinside_post_count",
    "news_sentiment",
    # 개인 순매도(음수 누적)는 froth의 반대(개미 이탈)라 progress=0으로 바닥 처리.
    "individual_net_buy",
}
