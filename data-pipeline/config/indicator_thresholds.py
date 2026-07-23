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
    # floor −35%~−3% = 0~75%. floor=−35%는 코스피 10년 낙폭 실측 근거: 최대 낙폭 −43.9%지만
    # 그건 극단이고 1%ile −33%·5%ile −28% 수준이라, −30%는 10년 중 2.4%만 닿아 흔한 낙폭
    # (−20~−25%)의 강세값을 지나치게 눌렀다(−25%가 progress 11). −35%로 낮추면 −25%가 21로
    # 올라 "전고점에서 크게 빠졌지만 아직 바닥은 아님"이 더 합리적으로 반영된다.
    "kospi_high_gap": {"kind": "fixed", "threshold": 0.0, "floor": -35.0, "kink": -3.0},
    "naver_search_trend": {"kind": "fixed", "threshold": 70.0},
    # dcinside_post_count / news_sentiment: (긍정−부정)/전체×100 (−100~100).
    # 2026-07-20 분류를 키워드 매칭 → LLM 으로 바꾸면서 **값의 스케일이 커졌다.**
    # 키워드 시절 디시는 제목의 95%가 어느 단어에도 안 걸려 중립으로 빠졌고, 그 결과
    # 관측 범위가 −4.6~0.1 에 그쳐 threshold 25 에 **한 번도 닿을 수 없었다**(진행률 ≤18%).
    # LLM 전환 후 분류율이 6%→72% 로 올라 같은 날 −24.4 가 나온다 — 임계값을 바꾸지
    # 않아도 이제야 의미 있게 켜질 수 있는 범위가 됐으므로 25/35 를 유지한다.
    # (히스토리에는 두 방식이 섞이지만 게이지가 '최근 |최대|' 기준이라 계산은 안 깨지고,
    #  30일 창이 굴러가며 자연히 LLM 값만 남는다.)
    "dcinside_post_count": {"kind": "fixed", "threshold": 25.0},
    # kospi_volume_surge: 절대 거래대금이 아니라 "30일 평균 대비 %"(details.surge_pct)로 판단.
    # 2026-07-23 재보정: 옛 눈금(−20~+33.3)은 실측 분포(−43.6% ~ +107.4%)보다 훨씬 좁아
    # **219일 중 45%가 양끝에 포화**됐다(바닥 19% · 천장 26%). 가중치 2위(4.0) 지표가
    # 그 절반의 날에 해상도를 잃은 셈이고, 실제로 오늘도 −43.6%로 floor 밖이라 거래대금이
    # 더 줄어도 점수가 안 움직였다. 분포가 오른쪽으로 길어(p75 +34%, p95 +72%) 눈금도
    # 비대칭으로 잡는다 → 바닥 0% · 천장 3% · 초고온 16%.
    # 초고온 진입은 급증 +47.5%(= floor + 0.75×(ceil−floor)).
    "kospi_volume_surge": {"kind": "fixed", "threshold": 500_000.0, "relative_surge": {"floor": -50.0, "ceil": 80.0}},
    "vkospi": {"kind": "fixed", "threshold": 20.0, "direction": "low"},
    "news_sentiment": {"kind": "fixed", "threshold": 35.0},
    "kospi_gold_ratio": {"kind": "fixed", "threshold": 2.2},
    # kosdaq_kospi_ratio: 2026-07-23 측정 방식 자체를 바꿨다(fetch_kosdaq_ratio.py 참고).
    # 옛 raw_value는 코스닥/코스피 '레벨 비율'이라, 코스피가 오르면 코스닥이 그대로여도
    # 값이 떨어졌다 — 1년간 시간과의 상관이 -0.928인 순수 추세라 고정 눈금을 어디 둬도
    # 1년의 85%가 천장에 붙었다. 이제 raw는 **코스닥 20거래일 초과수익률(%p)**이다.
    # floor -20 ~ ceiling +10: 코스닥이 코스피와 같으면(0%p) 과열도 51로 상온 한가운데,
    # 초고온 진입은 +2.5%p. 실측 232일에서 바닥 14% · 천장 0% · 초고온 12%.
    "kosdaq_kospi_ratio": {"kind": "fixed", "threshold": 10.0, "floor": -20.0},
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
    # bestseller_finance_ratio: 베스트셀러 100위 중 경제·재테크 도서 비중(%).
    # 16%는 실측상 거의 닿지 않는 값이라(최근 30일 관측값이 2%·4% 두 종류뿐) 지표가
    # 늘 바닥에 붙어 있었다. 10%로 낮춰 "서점가 열풍"이 실제로 켜질 수 있게 한다.
    "bestseller_finance_ratio": {"kind": "fixed", "threshold": 10.0},
    # youtube: 기준선=누적 평균(compute_threshold). 예전엔 progress=현재/평균×100이라 "평균=100%
    # =정상"인데도 과열 100%로 잡혀(평균 이하도 hit) 점수를 부풀렸다. surge_map으로 "평균 대비
    # 급증(%)"을 과열도로 매핑한다 — 평균(급증 0%)=진행률 50(상온), +25%=75(초고온 진입/Hit),
    # +50%=100. 카드의 "평소 대비 X배"는 threshold(=평균) 그대로라 안 깨진다.
    "youtube_finance_search_views": {"kind": "cumulative_average", "surge_map": {"floor": -50.0, "ceil": 50.0}},
    # kospi_asia_relative_strength: 코스피 20거래일 수익률이 일본·홍콩·대만 평균보다
    # 몇 %p 앞섰나. 2026-07-23 재보정: 옛 설정은 threshold 10 하나뿐이고 floor가 없어
    # 0 아래가 전부 뭉개졌다 — "5%p 뒤처진 날"과 "23%p 뒤처진 날"이 똑같이 0.
    # 그 결과 198일 중 25%가 바닥, 25%가 천장인 **사실상 이진 신호**였다(중간이 없음).
    # floor를 줘서 뒤처지는 정도도 눈금 안에 들어오게 한다 → 바닥 2% · 천장 2% · 초고온 17%.
    # 초고온 진입은 +13.75%p(= -20 + 0.75×45).
    "kospi_asia_relative_strength": {"kind": "fixed", "threshold": 25.0, "floor": -20.0},
    # luxury_consumption_index: 2026-07-23 재보정. "최고치의 70% = 과열"이라는 규칙을
    # 네이버 검색 지표 3개에 똑같이 적용했는데, 이 지표만 값이 늘 44~76 대역에 머물러
    # **377일 중 93%가 초고온**이었다(카드가 늘 '과열'로 읽혔다). 게다가 카드는
    # '평소 대비 0.9배↓'라고 말하는데 점수는 67% 과열로 들어가 방향이 어긋났다.
    # floor 40 ~ ceiling 78: 중앙값이 54로 상온 한가운데 오고 초고온은 17%.
    # 초고온 진입은 68.5pt.
    "luxury_consumption_index": {"kind": "fixed", "threshold": 78.0, "floor": 40.0},
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
    # ※ 2026-07-23 주석 정정: 예전엔 "0.50은 370일 중 16일(4.3%)만 도달해 옛 임계값의
    #    엄격도를 재현한다"고 적혀 있었는데, 그 4.3%는 **진행률 100(완전 도달)** 기준이었다.
    #    실제 배지는 진행률 75(= raw 0.375)에서 켜지고, 그 기준의 실측 도달률은 **15%**다
    #    — 같은 파일의 put_call(5%)보다 3배 헐겁다. 공식을 바꾼 지 얼마 안 됐으니 눈금은
    #    데이터가 더 쌓인 뒤 판단하고, 지금은 사실만 바로잡는다.
    # 참고 분위수: p75=0.31, p90=0.43, p95=0.46, 최대=0.56.
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
