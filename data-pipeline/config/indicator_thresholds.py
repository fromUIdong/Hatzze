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
    # kospi_high_gap: ATH 근접도. 피스와이즈 — kink(−1.5%)~ceiling(+5%) = 75~100%,
    # floor(−35%)~kink = 0~75%.
    # 2026-07-23 재보정: 옛 ceiling 0%(=전고점)는 상승장에서 너무 자주 닿아 **1년의 31%가
    # 천장 포화**였다. 2026-02 고점과 06 고점이 둘 다 100으로 같게 찍혀, 가중치 1위 지표가
    # 정작 고점끼리를 구분하지 못했다. 천장을 +5%(전고점 초과분까지 눈금 안)로 열면 포화가
    # 0.4%로 떨어진다. kink 도 −3 → −1.5 로 올려 초고온 비율을 60% → 46%로 낮춘다.
    # floor=−35%는 유지 — 코스피 10년 낙폭 실측(1%ile −33%·5%ile −28%) 근거이고, 이번
    # 표본(최대 −28.5%)만 보고 좁히면 진짜 약세장에서 바로 포화된다.
    "kospi_high_gap": {"kind": "fixed", "threshold": 5.0, "floor": -35.0, "kink": -1.5},
    # kospi_speed_60d: 코스피 60거래일 수익률(%). '얼마나 높이 왔나'(kospi_high_gap)와
    # 짝을 이루는 '얼마나 빨리 왔나' 축 — 둘의 상관은 +0.130으로 거의 직교한다.
    # **floor 는 실측 분위수가 아니라 절대 의미로 잡는다.** 처음엔 다른 지표들처럼 p15
    # (=20.6%)로 잡았는데, 이 표본은 60일 수익률이 **한 번도 마이너스가 아니었던 해**라
    # (최소 +4.8%, 중앙 +28.3%) "60일에 20% 올라도 과열도 0"이 돼 버렸다. 평범한 장이라면
    # 이 지표가 영원히 0에 붙는다. 0%(제자리)를 0, +50%(두 달 반 만에 1.5배)를 100으로 둔다.
    "kospi_speed_60d": {"kind": "fixed", "threshold": 50.0, "floor": 0.0},
    # naver_search_trend: 데이터랩이 조회 시점 직전 365일 최대치를 100으로 정규화해 주므로
    # raw 는 "지난 1년 최고점의 몇 %"라는 상대값이다. 옛 임계값 70은 실측 p95가 46.4라
    # **1년 중 4.0%만 초고온**이었다 — 코스피가 세 배가 되는 동안에도 거의 안 켜졌다.
    # ceiling 48(≈p95)로 낮추면 초고온이 11.9%로 다른 지표들과 같은 엄격도가 된다.
    "naver_search_trend": {"kind": "fixed", "threshold": 48.0, "floor": 0.0},
    # dcinside_post_count / news_sentiment: (긍정−부정)/전체×100 (−100~100).
    # 2026-07-20 분류를 키워드 매칭 → LLM 으로 바꾸면서 **값의 스케일이 커졌다.**
    # 키워드 시절 디시는 제목의 95%가 어느 단어에도 안 걸려 중립으로 빠졌고, 그 결과
    # 관측 범위가 −4.6~0.1 에 그쳐 threshold 25 에 **한 번도 닿을 수 없었다**(진행률 ≤18%).
    # LLM 전환 후 분류율이 6%→72% 로 올라 같은 날 −24.4 가 나온다 — 임계값을 바꾸지
    # 않아도 이제야 의미 있게 켜질 수 있는 범위가 됐으므로 25/35 를 유지한다.
    # (히스토리에는 두 방식이 섞이지만 게이지가 '최근 |최대|' 기준이라 계산은 안 깨지고,
    #  30일 창이 굴러가며 자연히 LLM 값만 남는다.)
    # 2026-07-23: 둘 다 floor-ceiling 으로 바꿨다. 임계값 25/35 는 LLM 전환 뒤에도
    # **한 번도 닿지 않았다** — 디시는 1년 관측 범위가 −24.4~0.15 로 내내 음수라 93%가
    # 과열도 0이었고(주갤 정서가 구조적으로 부정적이다), 뉴스는 53%가 0·13%가 100인
    # 켜짐-꺼짐 스위치였다. 실측 분포 위에 눈금을 다시 얹어 중간 구간이 생기게 한다.
    # ※ 디시가 음수 구간에 걸쳐 있다는 건 "덜 부정적 = 상대적 과열"로 읽는다는 뜻이다.
    #    절대적 낙관이 아니라 **평소 대비** 온도를 재는 것으로 의미가 바뀌었다.
    "dcinside_post_count": {"kind": "fixed", "threshold": 2.5, "floor": -7.5},
    # kospi_volume_surge: 절대 거래대금이 아니라 "30일 평균 대비 %"(details.surge_pct)로 판단.
    # 2026-07-23 재보정: 옛 눈금(−20~+33.3)은 실측 분포(−43.6% ~ +107.4%)보다 훨씬 좁아
    # **219일 중 45%가 양끝에 포화**됐다(바닥 19% · 천장 26%). 가중치 2위(4.0) 지표가
    # 그 절반의 날에 해상도를 잃은 셈이고, 실제로 오늘도 −43.6%로 floor 밖이라 거래대금이
    # 더 줄어도 점수가 안 움직였다. 분포가 오른쪽으로 길어(p75 +34%, p95 +72%) 눈금도
    # 비대칭으로 잡는다 → 바닥 0% · 천장 3% · 초고온 16%.
    # 초고온 진입은 급증 +47.5%(= floor + 0.75×(ceil−floor)).
    # ※ 2026-07-23 절대 수준 축 추가. 30일 상대만 보면 서서히 몇 배가 되는 흐름이 원리상
    #    안 보인다 — 1년간 절대 거래대금은 코스피와 상관 +0.922 인데 surge_pct 는 −0.019 였고,
    #    사상 최고점 당일(41.9조) 과열도가 25.6이었다. level_weight 만큼 details.level_pct
    #    (직전 250영업일 백분위)를 섞는다: progress = 0.7×급증률눈금 + 0.3×절대백분위.
    "kospi_volume_surge": {
        "kind": "fixed",
        "threshold": 500_000.0,
        "relative_surge": {"floor": -55.0, "ceil": 85.0},
        "level_weight": 0.3,
    },
    "vkospi": {"kind": "fixed", "threshold": 20.0, "direction": "low"},
    "news_sentiment": {"kind": "fixed", "threshold": 65.0, "floor": -50.0},
    # kospi_gold_ratio: 2026-07-23 floor 추가. floor 가 없으면 progress = raw/2.2×100 이라
    # 관측 최저(0.86)에서도 과열도가 39 밑으로 못 내려갔다 — 폭락 바닥에서 73.4를 찍은
    # 이유가 이것이다. floor 0.70 이면 하한이 10.7로 내려간다(0.85면 0이 되지만 중앙값이
    # 12.7로 지나치게 차가워져 0.70을 택했다).
    "kospi_gold_ratio": {"kind": "fixed", "threshold": 2.2, "floor": 0.70},
    # ※ kosdaq_kospi_ratio 는 2026-07-23 점수에서 **제거**했다. 한 해에 측정 방식을 세 번
    #   갈아엎은 지표다(레벨 비율 → 코스피 대비 초과수익 → 코스닥 자체 전고점 괴리).
    #   마지막 형태는 froth 타당성이 멀쩡했지만(동행성 +0.678), 결국 kospi_high_gap 과 같은
    #   것을 시장만 바꿔 재는 지표라 카드 한 칸을 쓸 값어치가 없다고 판단했다. 그 자리에
    #   kospi_speed_60d 카드를 넣었다. 스크립트(fetch_kosdaq_ratio.py)는 kosdaq_close_raw
    #   수집만 남기고, 지표 행은 is_public=False 로 내려 프론트 자동 노출을 막았다.
    # usdkrw_volatility: 낮을수록 과열(방심)이라 **floor에 큰 값, ceiling에 작은 값**을 넣어
    # 방향을 뒤집는다. compute_progress는 "floor" in config를 direction보다 먼저 보므로
    # direction 키 없이 이 순서만으로 계산이 맞는다(카드의 '이하' 표기는 DB direction 컬럼이
    # 따로 갖고 있으니 fetch 스크립트의 INDICATOR_META는 direction="low"를 유지할 것).
    # 옛 임계값 0.25는 **관측 최저(0.2704)보다도 낮아** 진행률 100에 영원히 못 닿았고
    # 초고온이 1.9%뿐이었다. floor 0.85(≈p90) / ceiling 0.20으로 잡으면 초고온 8.9%가 되고
    # 구조적 하한 22.6도 사라진다.
    "usdkrw_volatility": {"kind": "fixed", "threshold": 0.20, "floor": 0.85},
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
    # ※ 2026-07-23: threshold 100 은 관측 범위(p5 42.3 ~ p95 71.3)와 동떨어져 1년 내내
    #    과열도가 37.7~71에 갇혔다 — 초고온 3.6%, 구조적 하한 37.7(가중치 2.0×37.7이
    #    종합점수에 상시 얹혔다). floor 38 / ceiling 74로 실측 위에 다시 얹는다.
    "leverage_etf_volume": {"kind": "fixed", "threshold": 74.0, "floor": 38.0},
    # bestseller_finance_ratio: 베스트셀러 100위 중 경제·재테크 도서 비중(%).
    # 10%도 여전히 못 닿았다 — 관측값이 2·4·5% 세 종류뿐(최대 5%)이라 과열도가 20~50에
    # 갇혔다. 5%로 낮춘다. 값 자체가 세 종류뿐이라 눈금을 더 정밀하게 잡는 건 의미가 없다.
    "bestseller_finance_ratio": {"kind": "fixed", "threshold": 5.0},
    # youtube: 기준선=누적 평균(compute_threshold). 예전엔 progress=현재/평균×100이라 "평균=100%
    # =정상"인데도 과열 100%로 잡혀(평균 이하도 hit) 점수를 부풀렸다. surge_map으로 "평균 대비
    # 급증(%)"을 과열도로 매핑한다 — 평균(급증 0%)=진행률 50(상온), +25%=75(초고온 진입/Hit),
    # +50%=100. 카드의 "평소 대비 X배"는 threshold(=평균) 그대로라 안 깨진다.
    "youtube_finance_search_views": {"kind": "cumulative_average", "surge_map": {"floor": -50.0, "ceil": 50.0}},
    # kospi_asia_relative_strength: 코스피 20거래일 수익률이 일본·홍콩·대만 평균보다
    # 몇 %p 앞섰나. 실측 p20으로 잡았던 floor −10 은 속도 지표와 같은 과적합이었다 —
    # 이웃보다 16%p 뒤처진 날도 0으로 뭉개진다. ±20%p 라는 대칭 절대 기준으로 되돌린다
    # (0%p = 이웃과 같은 속도 = 눈금 한가운데).
    "kospi_asia_relative_strength": {"kind": "fixed", "threshold": 20.0, "floor": -20.0},
    # luxury_consumption_index: 2026-07-23 재보정. "최고치의 70% = 과열"이라는 규칙을
    # 네이버 검색 지표 3개에 똑같이 적용했는데, 이 지표만 값이 늘 44~76 대역에 머물러
    # **377일 중 93%가 초고온**이었다(카드가 늘 '과열'로 읽혔다). 게다가 카드는
    # '평소 대비 0.9배↓'라고 말하는데 점수는 67% 과열로 들어가 방향이 어긋났다.
    # floor 40 ~ ceiling 78: 중앙값이 54로 상온 한가운데 오고 초고온은 17%.
    # 초고온 진입은 68.5pt.
    # floor 는 42 — 실측 p20(48)로 잡으면 관측 최저(44.3)가 0에 붙어 하방이 뭉개진다.
    "luxury_consumption_index": {"kind": "fixed", "threshold": 78.0, "floor": 42.0},
    # fine_dining: floor 가 없어 관측 최저(20.0)에서도 과열도가 28.6 밑으로 못 갔다.
    # floor 18 / ceiling 48(실측 p20/p88)로 바꿔 하한을 6.6까지 내린다.
    "fine_dining_search_index": {"kind": "fixed", "threshold": 48.0, "floor": 18.0},
    # small_business_crisis_index는 검색량이 높을수록 "실물경제 위기 신호가 뚜렷하다"는
    # 뜻이지만, 점수 기여는 아래 calculate_score 가 '실물–증시 괴리(lead)'로 완전히
    # 덮어쓴다. 여기 값은 lead 계산이 불가능할 때의 폴백으로만 쓰인다.
    "small_business_crisis_index": {"kind": "fixed", "threshold": 70.0},
    # upbit_speculation_index: raw_value 자체가 이미 fetch 스크립트 안에서
    # 두 서브지표(김치프리미엄, 거래대금 급증도)의 가중 산술평균으로 계산된
    # "진행률에 가까운" 값이라, threshold=100은 "두 신호 모두 자기 기준선에
    # 도달한 수준"을 의미한다. 여기서 다시 나누는 건 사실상 그대로 통과시키는
    # 것에 가깝다.
    # ※ 2026-07-23: threshold 100 은 실측 p95(62.7)보다 훨씬 위라 초고온이 2.2%뿐이었다.
    #    ceiling 75 로 낮춰 11.2%가 되게 한다. raw 가 이미 두 서브지표의 가중평균(진행률에
    #    가까운 값)이라 floor 는 0 그대로다.
    "upbit_speculation_index": {"kind": "fixed", "threshold": 75.0, "floor": 0.0},
    # github_trading_bot_repos: 첫 관측값 하나로 잡았던 150은 **너무 낮았다** — 실측
    # 중앙값이 117이라 13일 중 31%가 천장 포화, 54%가 초고온이었다(다른 지표와 반대 방향의
    # 사고다). floor 40 / ceiling 225(실측 p20/p88)로 다시 얹는다. 표본이 13일뿐이라 잠정.
    "github_trading_bot_repos": {"kind": "fixed", "threshold": 225.0, "floor": 40.0},
    # brokerage_app_rank: 애플 금융 무료앱 차트 내 증권 앱들의 froth 점수(Σ(101-순위)).
    # threshold 800은 관측 최대(448)의 1.8배라 **닿을 수 없었다** — 7일 내내 과열도가
    # 47~56에 고정됐다(구조적 하한 47.0). floor 355 / ceiling 450 으로 실측 위에 얹는다.
    # 표본이 7일뿐이라 잠정 — 몇 주 쌓이면 재조정할 것.
    "brokerage_app_rank": {"kind": "fixed", "threshold": 450.0, "floor": 355.0},
    # individual_net_buy: 코스피 개인 순매수의 최근 5거래일 누적(억원).
    # threshold 100,000억은 관측 최대(48,790억)의 2배라 **닿을 수 없었다** — 절반이 바닥.
    # floor −60,000 / ceiling +67,000 으로 순매도 구간까지 눈금에 넣는다(순매도의 정도도
    # 정보다 — 옛 설정은 −4.8조와 −0.5조를 똑같이 0으로 뭉갰다). 표본 10일이라 잠정.
    "individual_net_buy": {"kind": "fixed", "threshold": 67_000.0, "floor": -60_000.0},
    # investor_deposit: 고객예탁금(대기 매수 자금, 억원). 수준이 구조적으로 크고 우상향하므로
    # youtube처럼 '최근 평균(cumulative_average) 대비 급증(surge_map)'으로 froth를 본다 —
    # 평균이면 상온(50), 평균 대비 +15%면 초고온(100). 예탁금 변동폭이 작아 ±15%로 잡았다.
    "investor_deposit": {"kind": "cumulative_average", "surge_map": {"floor": -15.0, "ceil": 15.0}},
    # turnover_concentration: 상위10 종목 거래대금 비중(%). 절대값 floor-ceiling.
    # 2026-07-23 floor 를 60 → 68.5 로 올렸다 — KOSPI는 구조적으로 70%대라 floor 60이면
    # 관측 최저(68.4)에서도 과열도가 42 밑으로 안 내려갔다(구조적 하한 42.0). 실측 p20인
    # 68.5로 올리면 하한이 0이 된다. 표본 24일이라 잠정.
    "turnover_concentration": {"kind": "fixed", "threshold": 80.0, "floor": 68.5},
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

# 현재값이 음수로 나올 수 있는 지표(감성 점수류)를 progress=0으로 바닥 처리하는 장치.
#
# **2026-07-23 현재 비어 있다.** 여기 있던 셋(dcinside·news_sentiment·individual_net_buy)이
# 전부 floor-ceiling 으로 바뀌면서 음수 구간이 눈금 안으로 들어왔기 때문이다. 셋 다 음수를
# 0으로 뭉개는 바람에 정보를 잃고 있었다 — 디시는 1년 내내 음수라 93%가 0이었고, 개인
# 순매수는 −4.8조와 −0.5조가 똑같이 0이었다. compute_progress 는 "floor" in config 를
# 이 집합보다 **먼저** 보므로, floor 를 준 지표를 여기 남겨 둬도 동작하지 않는다.
#
# 장치 자체는 남겨 둔다 — floor 를 주기 애매한 음수 지표가 새로 생기면 다시 쓸 수 있다.
NEGATIVE_CURRENT_CLAMP_SLUGS: set[str] = set()
