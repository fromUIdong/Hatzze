"""26개 지표의 Hit/progress 기준값(threshold) 설정.

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
    "us10y": {"kind": "fixed", "threshold": 5.0},
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
    # copper_price_momentum: 20거래일 만에 15% 이상 오르면 뚜렷한 상승 모멘텀으로
    # 보는 논리적 추정치다 — kospi_asia_relative_strength와 마찬가지로 실측 분포를
    # 아직 확인 못 했으니 데이터가 쌓이면 재조정이 필요할 수 있다.
    "copper_price_momentum": {"kind": "fixed", "threshold": 15.0},
    # github_trading_bot_repos: 사전 추정 근거가 전혀 없는 완전히 새로운 지표라
    # 실행해서 나온 첫 관측값(81건, 2026-07-11)을 기준점으로 삼았다. threshold=150은
    # 그 값의 약 1.85배 — "하루 평균보다 확연히 많이 튀는" 수준을 잠정적으로 잡은
    # 것이라, 표본이 하루뿐이라는 한계가 크다. 며칠~몇 주치 데이터가 쌓이면 실제
    # 분포(평균, 표준편차)를 보고 반드시 재조정해야 한다.
    "github_trading_bot_repos": {"kind": "fixed", "threshold": 150.0},
    # market_actions_30d: raw_value = (매수 사이드카 - 매도 사이드카) - CB발동×4를
    # 실제 KIND 공시로 1년치(2025-07~2026-07) 백필해 매일의 롤링 30일 값을 계산해보니
    # 최댓값이 3.0에 그쳤다 — 사이드카는 연간 매수17건/매도18건으로 거의 균형이라
    # (매수-매도) 차이가 잘 안 벌어지고, CB는 발동되면 -4로 강하게 끌어내리기 때문.
    # 사용자가 제안한 15~20은 이 지표 구조상 사실상 도달 불가능한 값이라 채택하지
    # 않았다. 대신 threshold=2.0은 1년 366일 중 상위 4.4%(16일)만 도달한 수준으로,
    # "매수 쪽이 뚜렷하게 우세"에 해당하는 현실적인 기준값이다.
    "market_actions_30d": {"kind": "fixed", "threshold": 2.0},
    # yield_curve_spread: FRED DGS10-DGS2 실측 2년치(2024-07~2026-07, 498거래일)로
    # 분포를 확인해보니 -0.30%p(역전)~0.74%p(정상화 정점) 범위였고, 중앙값은
    # 0.49%p, 최근값(2026-07-09)은 0.39%p였다. threshold=0.6%p는 상위 12.2%(61일)
    # 수준으로, 관측 범위 상단부에 해당하는 "뚜렷하게 정상화·확대된" 스프레드다.
    "yield_curve_spread": {"kind": "fixed", "threshold": 0.6},
    # top10_market_cap_concentration: sto/stk_bydd_trd API가 아직 미승인이라 직접
    # 계산은 못 했지만(2026-07-11 기준 401), 공개된 자료 기준 코스피 상위 10종목
    # 시가총액 비중은 통상 40~45% 수준이고(삼성전자 단독 약 22%), 2026년 들어
    # 반도체 쏠림이 심해지며 상위 4종목 비중만도 1월 38.83%에서 5월 49.49%로
    # 급등했다. threshold=50.0은 "상위 몇 종목이 지수를 사실상 떠받치는" 수준의
    # 임계선으로 잡은 논리적 추정치다 — API 승인 후 실측 분포를 보고 반드시
    # 재조정해야 한다.
    "top10_market_cap_concentration": {"kind": "fixed", "threshold": 50.0},
    # vix_vkospi_spread: raw = VIX 백분위 - VKOSPI 백분위(각자 최근 1년 분포 기준).
    # VIX와 VKOSPI는 산출식·스케일이 달라(VIX~15, KRX "코스피200 변동성지수"~78) 절대값
    # 뺄셈이 무의미해서, 각자 자기 분포 내 백분위로 바꿔 비교한다. 양수로 클수록
    # "미국은 불안한데 한국만 유독 잠잠" = 방심(과열)이라 direction=high(기본).
    # 실측 분포(2025-07~2026-07, 237거래일, 저장된 VKOSPI와 기존 스프레드로 VIX를 역산해
    # 계산)로 보니 min -82.9, 중앙값 -13.4, p90 14.3, p95 31.6, max 77.1 — 양수(한국이 더
    # 잠잠)인 날이 22%뿐이라 과열은 원래 드문 신호다. threshold=30은 상위 5.5%(13/237일)로,
    # 기존 지표가 잡던 상위 3.8% 및 다른 지표들의 상위 5~12% 관례와 비슷한 "뚜렷한 방심"
    # 구간이다. 음수(한국이 오히려 더 출렁)면 progress=0으로 바닥 처리한다
    # (NEGATIVE_CURRENT_CLAMP_SLUGS).
    "vix_vkospi_spread": {"kind": "fixed", "threshold": 30.0},
}

# 현재값이 음수로 나올 수 있는 지표(감성 점수류)는 음수를 "역방향 과열"로 해석하지
# 않고 그냥 progress=0으로 바닥 처리한다. current/threshold*100 공식을 그대로 쓰면
# 음수 현재값이 음수 progress를 만들어 화면에 "-12%"처럼 어색하게 표시되기 때문.
NEGATIVE_CURRENT_CLAMP_SLUGS = {
    "dcinside_post_count",
    "news_sentiment",
    # 한국이 미국보다 오히려 더 출렁이면(백분위 스프레드 음수) 방심과 반대라 progress=0.
    "vix_vkospi_spread",
}
