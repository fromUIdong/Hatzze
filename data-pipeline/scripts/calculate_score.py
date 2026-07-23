"""25개 지표의 현재값을 기준선과 비교해 과열도 스코어를 계산하고 daily_score/indicator_values에 저장.

기준선(threshold)은 이제 전부 리서치/논리 기반의 고정값이다
(config/indicator_thresholds.py의 INDICATOR_THRESHOLDS). 원래는 과거 데이터의
상위/하위 N% 지점(percentile)을 기준선으로 썼는데, 그러려면 지표별로 최소
표본 수가 쌓일 때까지 기준선 자체가 계속 흔들리는 문제가 있었다. 기준값을
조정하고 싶으면 이 파일이 아니라 indicator_thresholds.py만 고치면 된다.

kospi_high_gap은 0 이하 값만 가지는 지표라 (현재값/기준선)*100 공식을 그대로
쓸 수 없어서, floor(-35%)와 kink(-3%)를 둔 피스와이즈로 매핑한다. floor·kink는
둘 다 indicator_thresholds.py의 고정값이다 — 예전엔 floor를 kospi_close_raw
히스토리에서 매일 다시 계산했지만, 지금은 다른 지표들과 같은 고정 임계값 철학을
따른다.

vkospi/usdkrw_volatility는 다른 지표와 반대 방향이다 — 값이 낮을수록(시장이
방심할수록) 과열 신호다. INDICATOR_THRESHOLDS에 "direction": "low"가 있으면
현재값이 기준선 이하일 때 Hit, progress = threshold/current*100 (낮을수록
progress가 커짐)으로 계산한다. 나머지 지표는 기본값인 "high" 방향(현재값이
기준선 이상일 때 Hit)을 쓴다.

dcinside_post_count/news_sentiment는 현재값이 음수로 나올 수 있는 감성 점수류
지표다. current/threshold*100 공식을 그대로 쓰면 음수 현재값이 음수 progress를
만들어 화면에 "-12%"처럼 어색하게 표시되므로, 이 두 지표는 현재값이 음수면
그냥 progress=0으로 바닥 처리한다(NEGATIVE_CURRENT_CLAMP_SLUGS).

Progress는 두 가지 버전을 함께 다룬다:
- 원본(raw) Progress: 100%를 넘거나 음수여도 그대로 둔 값. "기준선을 몇 % 초과했는지"
  같은 상세 정보를 보여줘야 하는 indicator_values.normalized_score에 저장한다.
- 캡핑(capped) Progress: 0~100% 범위로 자른 값(min(max(x, 0), 100)). 지표 하나가
  100%를 크게 초과해 종합 스코어를 왜곡하지 않도록, daily_score.score(아래
  설명하는 가중 평균)는 이 캡핑된 값들로 계산한다.

기준선이 전부 고정값이 되면서 "히스토리가 부족해 기준선을 못 정하는" 경우는
youtube_finance_search_views를 빼면 더 이상 없다. 유일하게 남는 예외 상황은
"이 지표에 값이 아예 한 건도 없는" 경우(예: 새 지표를 막 추가했는데 fetch
스크립트가 아직 한 번도 안 돈 경우)뿐이고, 이때는 그 지표만 daily_score
가중 평균에서 완전히 제외한다(no_value, 아래 설명).

youtube_finance_search_views는 유일하게 고정 기준선을 쓰지 않는 지표다.
나머지 지표들은 INDICATOR_THRESHOLDS의 고정값을 기준선으로 삼지만, 이 지표는
"오늘 값을 포함한 지금까지의 전체 평균"을 매일 다시 계산해 그날의 기준선으로
쓴다(compute_threshold의 "cumulative_average" 분기). 표본이 1개(오늘 하루)뿐이면
평균=오늘 값이 되어 progress가 100%로 나오는데, 이는 데이터 부족으로 판단을
보류하는 게 아니라 의도된 동작이다 — 데이터가 쌓일수록 평균이 더 많은 날짜를
반영하며 비교 기준이 자연스럽게 안정되기 때문이다.

daily_score.score("햇쩨 지수")는 지표별 capped_progress의 가중 평균을 낸 뒤
(Σ(weight_i × capped_progress_i) / Σ(weight_i)), 그 원점수를 SCORE_DISPLAY_ANCHORS로
한 번 더 매핑한 값이다. 매핑을 두는 이유는 그 상수 주석에 적어 뒀다 — 요약하면 서로
무상관인 26개 지표의 평균은 산술적으로 가운데로 모여서, 코스피가 세 배가 되는 동안에도
초고온이 하루도 안 나왔기 때문이다. 순위를 보존하는 단조 변환이라 지표 간 상대 판단은
그대로다.
단, "데이터가 아예 없는" 지표는 가중 평균에서 완전히 제외한다(분모의 weight
합계에도 포함하지 않음) — get_latest_value가 InsufficientHistoryError를
던지는 no_value 케이스가 이 경우다.

stage(저온/상온/고온/초고온)는 이 가중 평균 점수 자체를 4구간으로 나눠 정한다
(stage_for_score) — 초고온 지표 개수로 정하지 않는다. 개수는 화면의 배지·히어로
문장용으로 계속 세지만, stage 산정에는 관여하지 않는다.

**화면에 적는 "기준선"은 진행률 100이 아니라 초고온 진입선(진행률 75)이다.**
INDICATOR_THRESHOLDS의 threshold는 진행률 100을 맞추는 매핑 상한이고, 카드가
보여줄 기준선은 raw_at_progress(slug, HOT_ZONE, ...)로 되돌려 details.hot_threshold에
저장한다. 이렇게 해야 "기준선을 넘었다"와 "초고온 배지가 켜졌다"가 같은 뜻이 된다 —
예전엔 배지가 75에서 켜지는데 카드엔 100 지점을 기준선으로 적어서, 기준선에 못 미친
지표에 배지가 붙었다(2026-07-22 기준 3개).
"""

from __future__ import annotations

import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from config.indicator_thresholds import (  # noqa: E402
    INDICATOR_THRESHOLDS,
    NEGATIVE_CURRENT_CLAMP_SLUGS,
)
from config.indicator_weights import INDICATOR_WEIGHTS  # noqa: E402

# 실물–증시 괴리 = "실물 경제와 증시 중 누가 더 강한가"(양방향 게이지). 두 축을 각자
# '역대 백분위'(0~100, 자기 역사에서 어느 지점만큼 강한가)로 만들어 공정하게 비교한다.
# 서로 다른 척도(심리지수 vs 낙폭%)를 그냥 빼면 불공정해서, 백분위로 통일했다.
#
# 백분위 매핑은 DB 히스토리가 짧아(코스피 종가 1년) 실시간 계산이 불가능하므로, 장기
# 실측 분위수를 앵커 상수로 박아 구간 선형보간한다(다른 지표들의 fixed-threshold 철학과 동일).
CCSI_SLUG = "consumer_sentiment_index"
# CCSI 역대 분위수(2008~2026 216개월 실측): p10~p90. 값→백분위 보간용.
CCSI_PCTILE_ANCHORS = [(90.0, 10), (98.0, 25), (102.0, 50), (107.0, 75), (112.0, 90)]
# 코스피 전고점 대비 낙폭(%) 역대 분위수(10년 실측). 낙폭이 얕을수록(0에 가까울수록) 증시 강함.
KOSPI_DD_PCTILE_ANCHORS = [(-25.9, 10), (-21.6, 25), (-15.1, 50), (-3.4, 75), (-0.4, 90)]
NEUTRAL_PROGRESS = 50.0  # 값이 아예 없는 지표(no_value)를 표에 표시할 때 쓰는 자리표시자

# 종합점수 표시 눈금 — 가중평균 원점수를 '역대 백분위' 앵커로 펴서 보여준다.
#
# 왜 필요한가: 26개 지표는 서로 거의 무상관이다(지표 쌍 평균 Spearman +0.038). 각자 자기
# 최고치를 전부 다른 날 찍기 때문에, 가중평균은 산술적으로 가운데로 모인다 — 모두가 동시에
# 최고치라면 97.8이 나오지만 1년 실측 최고는 68.6이었고 **초고온(75+)이 단 하루도 없었다**
# (코스피가 세 배가 되는 동안). 개별 눈금을 아무리 손봐도 이 압축은 안 풀린다.
#
# 그래서 원점수를 자기 분포의 백분위로 매핑한다. **순위를 100% 보존**하는 단조 변환이라
# 지표 간 상대 판단을 바꾸지 않고 눈금만 편다. 코드에 이미 있는 percentile_from_anchors 를
# 그대로 쓴다(CCSI·낙폭 축과 같은 패턴).
#
# **앵커는 '이 해의 백분위'가 아니라 '원점수의 절대 수준'에 건다.** 처음엔 실측 분위수로
# 잡았는데(p5→12, p25→33 …), 표본이 코스피가 세 배가 된 해라 그 해의 하위 5%가 곧 표시
# 12점이 됐다. 그런데 그 시점의 시장은 전년 대비 +117%, 버핏지수 199%로 절대 기준으론
# 전혀 차갑지 않다 — 폭락 직후인 2026-07-23이 6.16점으로 찍혔고, 그건 눈금이 표본에
# 갇혔다는 뜻이다. 개별 지표의 floor 를 아무리 고쳐도 과거 구간이 같이 올라가 백분위
# 위치가 그대로라 안 풀린다(31.6 → 34.2로 2.6점 움직였을 뿐이다).
#
# 원점수 자체는 이미 절대 척도다(모든 지표가 0이면 0, 다 최대면 100). 거기에 직접 앵커를
# 걸면 "이 해가 유난했다"가 점수에 그대로 남는다 — 실제로 이 표본에서 저온은 거의 안 나오고
# 중앙값이 53이다.
#
# 이 눈금에서 2025-07~2026-07 구간은: 고점 기간 최고치 79/88/86(세 고점 모두 75 이상),
# 저점 47/45/35, 폭락 직후 오늘 31, 국면 비중 상온 37% · 고온 44% · 초고온 19%.
# 향후 90일 최대낙폭은 4분위에서 −1.1 / −2.3 / −2.9 / −4.3%로 단조롭게 나빠진다.
# 이 표본에서 저온(25 미만)은 사실상 안 나온다 — 코스피가 1년 새 세 배가 된 해라 그게 맞다.
#
# ※ 앵커 x값은 backtest/absolute.py 가 낸 값에서 **일괄 −2** 한 것이다. 백테스트의 원점수는
#   단기 9개를 관측 평균 상수로 놓아 추정한 값이라 편의가 있는데, 첫 실제 실행에서 그 편의가
#   −2.23(추정 34.15 vs 실측 31.92)으로 측정돼 그만큼 보정했다.
#
# 백분위 방식이 아니므로 **표본이 바뀌어도 앵커를 다시 뽑을 필요가 없다** — 원점수 분포가
# 옮겨가면 점수가 그만큼 움직이는 게 맞다. 다만 지표 구성·가중치를 크게 바꾸면 원점수의
# 뜻이 달라지므로 그때는 backtest/absolute.py 로 다시 확인할 것.
SCORE_DISPLAY_ANCHORS = [
    (14.0, 0), (32.0, 31), (44.0, 50), (54.0, 72), (61.0, 86), (68.0, 96), (78.0, 100),
]
# 초고온 진입선(진행률 75) = 화면이 "기준선"으로 부르는 지점.
#
# 예전엔 진행률 100 지점을 기준선으로 표시하면서 배지는 75에서 켰다. 그래서 "기준선
# 0.14배 이상"이라고 적힌 카드가 0.11배에서 HIT 배지를 달았다 — 세 지표가 동시에
# 그랬다. 이제 카드에 적는 기준선 자체를 초고온 진입선으로 바꿔(raw_at_progress),
# "기준선을 넘었다 = 초고온 배지가 켜졌다"가 항상 같은 뜻이 되게 한다.
HOT_ZONE = 75.0

INDICATOR_ORDER = list(INDICATOR_THRESHOLDS.keys())


class InsufficientHistoryError(Exception):
    """지표에 값이 아예 한 건도 없을 때(no_value) 발생."""


def get_indicator(client, slug: str) -> tuple[str, str, float]:
    result = (
        client.table("indicators").select("id,name,weight").eq("slug", slug).execute()
    )
    if not result.data:
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    row = result.data[0]
    # 가중치는 코드(config/indicator_weights.py)가 소스 오브 트루스 — DB weight는 폴백.
    db_weight = float(row["weight"]) if row.get("weight") is not None else 1.0
    weight = INDICATOR_WEIGHTS.get(slug, db_weight)

    # DB 값이 코드와 다르면 코드값으로 맞춰 둔다. 점수 계산에는 이미 코드값을 쓰므로
    # 결과가 달라지진 않지만, SQL로 직접 들여다볼 때 낡은 숫자를 보고 판단하는 걸 막는다
    # (2026-07-23 기준 25개 중 13개가 어긋나 있었다 — 예탁금 DB 1.0 vs 코드 3.0 등).
    if slug in INDICATOR_WEIGHTS and abs(db_weight - weight) > 1e-9:
        client.table("indicators").update({"weight": weight}).eq("id", row["id"]).execute()
        print(f"[동기화] '{slug}' weight {db_weight:g} → {weight:g} (코드 기준)")

    return row["id"], row["name"], weight


def get_latest_value(client, indicator_id: str) -> tuple[str, float, dict]:
    """최신 행의 (날짜, 원값, details)를 돌려준다.

    details 를 같이 받아오는 이유: 뒤에서 relative_surge(거래대금)와 hot_threshold 병합에
    모두 필요한데, 따로 조회하면 지표마다 쿼리가 두 번씩 나간다.
    """
    result = (
        client.table("indicator_values")
        .select("date,raw_value,details")
        .eq("indicator_id", indicator_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise InsufficientHistoryError(f"indicator_id={indicator_id}에 값이 아직 없습니다")
    row = result.data[0]
    return row["date"], float(row["raw_value"]), (row.get("details") or {})


def get_indicator_id_or_none(client, slug: str) -> str | None:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    if not result.data:
        return None
    return result.data[0]["id"]


def percentile_from_anchors(value: float, anchors: list[tuple[float, int]]) -> float:
    """값을 (값, 백분위) 앵커들로 구간 선형보간해 0~100 백분위로 만든다.

    앵커는 값 오름차순이어야 한다. 앵커 밖은 양끝 백분위로 클램프한다. 예: CCSI 앵커에서
    102(p50)와 107(p75) 사이의 105는 p50~p75를 선형보간해 ≈65가 된다.
    """
    if value <= anchors[0][0]:
        return float(anchors[0][1])
    if value >= anchors[-1][0]:
        return float(anchors[-1][1])
    for (v0, p0), (v1, p1) in zip(anchors, anchors[1:]):
        if v0 <= value <= v1:
            return p0 + (value - v0) / (v1 - v0) * (p1 - p0)
    return float(anchors[-1][1])  # 도달 불가(방어)


def ccsi_real_strength(client) -> tuple[float, float] | None:
    """CCSI 최신값을 (실물강도 백분위 0~100, CCSI 원값)으로 돌려준다.

    강도 = CCSI가 역대에서 몇 %ile인가(높을수록 실물 심리 강함). 원값도 함께 주는 이유:
    카드 툴팁이 "CCSI 106.6 → 역대 68%ile" 처럼 실제 지수와 변환 근거를 같이 보여준다.
    CCSI 지표가 아직 없으면 None.
    """
    ccsi_id = get_indicator_id_or_none(client, CCSI_SLUG)
    if ccsi_id is None:
        return None
    try:
        _, current, _ = get_latest_value(client, ccsi_id)
    except InsufficientHistoryError:
        return None
    return percentile_from_anchors(current, CCSI_PCTILE_ANCHORS), current


def kospi_market_strength(client) -> tuple[float, float] | None:
    """코스피 전고점 대비 낙폭을 (증시강세 백분위 0~100, 낙폭 %)로 돌려준다.

    강세 = 낙폭이 역대에서 몇 %ile로 얕은가(전고점에 가까울수록 강함). kospi_high_gap의
    raw_value(전고점 대비 %)를 그대로 재사용한다 — 그 카드의 progress(피스와이즈)와는
    목적이 달라(여긴 역대 백분위) 별도 계산이다. 값이 없으면 None.
    """
    hg_id = get_indicator_id_or_none(client, "kospi_high_gap")
    if hg_id is None:
        return None
    try:
        _, gap, _ = get_latest_value(client, hg_id)  # 전고점 대비 % (음수)
    except InsufficientHistoryError:
        return None
    return percentile_from_anchors(gap, KOSPI_DD_PCTILE_ANCHORS), gap


def get_all_values(client, indicator_id: str) -> list[float]:
    result = (
        client.table("indicator_values")
        .select("raw_value")
        .eq("indicator_id", indicator_id)
        .execute()
    )
    return [float(r["raw_value"]) for r in result.data]


def compute_threshold(client, indicator_id: str, config: dict) -> float:
    if config["kind"] == "fixed":
        return config["threshold"]

    # cumulative_average (youtube_finance_search_views 전용): 오늘 값을 포함해
    # 지금까지 쌓인 전체 값의 평균을 매일 다시 계산해 그날의 기준선으로 삼는다.
    # 데이터가 1건(오늘)뿐이면 평균=오늘 값이라 progress가 항상 100%로 나오는데,
    # 이건 "판단을 보류"하는 게 아니라 의도된 결과다 — 데이터가 쌓일수록 평균이
    # 더 많은 날짜를 반영하며 자연스럽게 비교 기준이 안정된다. get_latest_value가
    # 이미 성공했다는 건 최소 1건은 있다는 뜻이라 표본이 몇 개든 그냥 계산한다.
    values = get_all_values(client, indicator_id)
    return statistics.mean(values)


def compute_progress(slug: str, current: float, threshold: float, config: dict) -> float:
    if slug == "kospi_high_gap":
        # 피스와이즈: kink(−3%)~threshold(0%=ATH)를 75~100%(초고온을 근처로 좁게),
        # floor(−30%)~kink를 0~75%로 균등 배분.
        floor = config["floor"]
        kink = config["kink"]
        if current >= kink:
            return 75.0 + (current - kink) / (threshold - kink) * 25.0
        return (current - floor) / (kink - floor) * 75.0
    if "floor" in config:
        # 일반 floor-ceiling(버핏 등): floor=0%, threshold(ceiling)=100% 선형.
        floor = config["floor"]
        return (current - floor) / (threshold - floor) * 100
    if "surge_map" in config:
        # cumulative_average(youtube): threshold=평균이라 current/threshold*100은 평균=100(정상)이
        # 돼 과열 척도로 안 맞는다. 평균 대비 급증(%)을 0~100 과열도로 매핑한다 — 평균(급증 0%)이
        # floor~ceil의 중앙(=상온), ceil에서 초고온. surge_map = {floor, ceil}(급증 % 단위).
        sm = config["surge_map"]
        surge = (current / threshold - 1) * 100 if threshold else 0.0
        return (surge - sm["floor"]) / (sm["ceil"] - sm["floor"]) * 100
    if slug in NEGATIVE_CURRENT_CLAMP_SLUGS and current < 0:
        return 0.0
    if config.get("direction") == "low":
        if current == 0:
            return 0.0
        return threshold / current * 100
    return current / threshold * 100


def raw_at_progress(
    slug: str, target: float, threshold: float, config: dict, avg_30d: float | None = None
) -> float | None:
    """progress가 target이 되는 원값(raw_value)을 거꾸로 구한다 — compute_progress의 역함수.

    카드에 적는 "기준선"을 초고온 진입선(target=HOT_ZONE)으로 바꾸기 위해 쓴다. 각 분기는
    compute_progress와 **같은 순서**여야 한다(특히 relative_surge는 main에서 나중에
    덮어쓰므로 여기서도 가장 먼저 본다).

    threshold가 매일 바뀌는 지표(youtube·예탁금의 누적평균, 거래대금의 30일 평균)도
    그날의 값으로 계산되므로 기준선이 자연히 같이 움직인다.
    """
    rs = config.get("relative_surge")
    if rs is not None:
        if not avg_30d:
            return None
        surge = rs["floor"] + target / 100.0 * (rs["ceil"] - rs["floor"])
        return avg_30d * (1 + surge / 100.0)
    if slug == "kospi_high_gap":
        floor, kink = config["floor"], config["kink"]
        if target >= 75.0:
            return kink + (target - 75.0) / 25.0 * (threshold - kink)
        return floor + target / 75.0 * (kink - floor)
    if "floor" in config:
        return config["floor"] + target / 100.0 * (threshold - config["floor"])
    if "surge_map" in config:
        sm = config["surge_map"]
        surge = sm["floor"] + target / 100.0 * (sm["ceil"] - sm["floor"])
        return threshold * (1 + surge / 100.0)
    if config.get("direction") == "low":
        return threshold / (target / 100.0) if target else None
    return threshold * (target / 100.0)


def cap_progress(progress: float) -> float:
    return min(max(progress, 0.0), 100.0)


def stage_for_score(score: float) -> str:
    if score < 25:
        return "저온"
    if score < 50:
        return "상온"
    if score < 75:
        return "고온"
    return "초고온"


def main() -> None:
    client = get_client()

    results = []
    for slug in INDICATOR_ORDER:
        config = INDICATOR_THRESHOLDS[slug]
        indicator_id, name, weight = get_indicator(client, slug)

        try:
            latest_date, current, latest_details = get_latest_value(client, indicator_id)
        except InsufficientHistoryError as e:
            print(f"[WARNING] '{slug}' 값이 아직 없어 가중 평균에서 제외됨: {e}")
            latest_date = date.today().isoformat()
            latest_details = {}
            current = None
            threshold = None
            hot_threshold = None
            hit = False
            progress = NEUTRAL_PROGRESS
            capped_progress = NEUTRAL_PROGRESS
            no_value = True
        else:
            no_value = False
            threshold = compute_threshold(client, indicator_id, config)
            progress = compute_progress(slug, current, threshold, config)
            capped_progress = cap_progress(progress)

            avg_30d = None
            rs = config.get("relative_surge")
            if rs is not None:
                # 절대 거래대금 대신 "30일 평균 대비 %"(fetch가 details.surge_pct에 저장)로.
                surge = latest_details.get("surge_pct")
                if surge is not None:
                    progress = (surge - rs["floor"]) / (rs["ceil"] - rs["floor"]) * 100
                    # 30일 상대만으로는 1년에 걸쳐 5배가 되는 흐름이 안 보인다(사상 최고점
                    # 당일 41.9조인데 급증율 +2.3%라 과열도 25.6). details.level_pct(직전
                    # 250영업일 백분위)를 level_weight 만큼 섞어 '국면'을 되살린다.
                    lw = config.get("level_weight")
                    level = latest_details.get("level_pct")
                    if lw and level is not None:
                        progress = cap_progress(progress) * (1 - lw) + float(level) * lw
                    capped_progress = cap_progress(progress)
                    avg_30d = latest_details.get("avg_30d")

            # 카드에 적을 기준선 = 초고온 진입선. 이 값을 넘으면(direction=low면 밑돌면)
            # 정확히 그때 초고온 배지가 켜진다 — 표시와 판정이 같은 지점을 가리킨다.
            hot_threshold = raw_at_progress(slug, HOT_ZONE, threshold, config, avg_30d)
            if avg_30d and hot_threshold is not None:
                threshold = round(hot_threshold, 2)  # 거래대금은 표시용 절대값도 이 선으로

            hit = capped_progress >= HOT_ZONE

        results.append(
            {
                "slug": slug,
                "name": name,
                "weight": weight,
                "indicator_id": indicator_id,
                "date": latest_date,
                "current": current,
                "threshold": threshold,
                "hot_threshold": hot_threshold,
                "base_details": latest_details,
                "hit": hit,
                "progress": progress,
                "capped_progress": capped_progress,
                "no_value": no_value,
            }
        )

    # 실물–증시 괴리: "실물 경제와 증시 중 누가 더 강한가"(양방향 게이지). 두 축을 각자
    # 역대 백분위(0~100)로 만들어 lead = 증시%ile − 실물%ile 을 낸다. lead>0 이면 증시가
    # 실물을 앞지른 것(거품 신호), lead<0 이면 실물이 앞선 것(건강).
    #
    # 2026-07-23 이전에는 기여를 max(0, lead)로 잘랐다 — "실물이 앞서는 건 과열이 아니다"는
    # 논리였는데, 그 결과 **1년의 54%가 과열도 0**이고 초고온이 단 하루도 없었다(최대 57.5).
    # 동행성은 +0.533으로 멀쩡한 지표인데 절반이 뭉개져 점수에 기여를 못 한 것이다. 이제
    # lead(-75~+45)를 그대로 0~100에 펴서, 실물이 크게 앞서면 '차갑다'로 읽히게 한다.
    # 카드는 여전히 lead의 부호로 "실물 X% 강세"↔"증시 X% 강세"를 양방향으로 보여준다.
    LEAD_FLOOR, LEAD_CEIL = -75.0, 45.0
    by_slug = {r["slug"]: r for r in results}
    sb = by_slug.get("small_business_crisis_index")
    hg = by_slug.get("kospi_high_gap")
    ccsi = ccsi_real_strength(client)
    mkt = kospi_market_strength(client)
    if sb and hg and not sb["no_value"] and ccsi is not None and mkt is not None:
        real_strength, ccsi_value = ccsi
        market_strength, gap_pct = mkt
        lead = market_strength - real_strength  # +면 증시 앞섬, −면 실물 앞섬
        sb["progress"] = (lead - LEAD_FLOOR) / (LEAD_CEIL - LEAD_FLOOR) * 100
        sb["capped_progress"] = cap_progress(sb["progress"])
        sb["hit"] = sb["capped_progress"] >= HOT_ZONE
        # 카드에 적을 기준선도 같은 척도로 되돌린다(진행률 75가 되는 lead 값).
        sb["hot_threshold"] = LEAD_FLOOR + HOT_ZONE / 100.0 * (LEAD_CEIL - LEAD_FLOOR)
        # 카드용: 두 축 백분위 + 방향(lead) + 원값(툴팁). 병합해 남의 키 보존.
        sb["extra_details"] = {
            "real_strength": round(real_strength, 1),
            "market_strength": round(market_strength, 1),
            "lead": round(lead, 1),  # 양수=증시 강세, 음수=실물 강세
            "ccsi_value": round(ccsi_value, 1),
            "kospi_gap": round(gap_pct, 1),
        }

    hit_count = sum(1 for r in results if r["hit"])
    weighted_results = [r for r in results if not r["no_value"]]
    weight_sum = sum(r["weight"] for r in weighted_results)
    raw_score = (
        sum(r["weight"] * r["capped_progress"] for r in weighted_results) / weight_sum
        if weight_sum > 0
        else 0.0
    )
    # 무상관 평균의 압축을 푼다 — SCORE_DISPLAY_ANCHORS 주석 참고. 순위 보존 단조 변환이라
    # 지표 간 순서는 그대로고 눈금만 펴진다.
    weighted_score = percentile_from_anchors(raw_score, SCORE_DISPLAY_ANCHORS)
    stage = stage_for_score(weighted_score)

    # 화면과 같은 말을 쓴다: '기준선'은 초고온 진입선(카드에 뜨는 값)이고, 진행률 100을
    # 맞추는 매핑 상한은 '상한(100)'으로 따로 적는다. 로그만 옛 이름을 쓰면 나중에 이
    # 표를 보고 임계값을 조정할 때 다시 같은 혼동이 생긴다.
    print(
        f"{'slug':22} {'weight':>7} {'현재값':>14} {'기준선(초고온)':>15} {'상한(100)':>14} "
        f"{'초고온':>6} {'Progress(원본)':>14} {'Progress(캡핑)':>14}"
    )
    for r in results:
        hot_mark = "O" if r["hit"] else "X"
        current_str = (
            f"{r['current']:>14.2f}" if r["current"] is not None else f"{'N/A':>14}"
        )
        hot_str = (
            f"{r['hot_threshold']:>15.2f}"
            if r.get("hot_threshold") is not None
            else f"{'N/A':>15}"
        )
        cap_str = (
            f"{r['threshold']:>14.2f}" if r["threshold"] is not None else f"{'N/A':>14}"
        )
        note = "  (값 없음 - 가중 평균에서 제외)" if r["no_value"] else ""
        print(
            f"{r['slug']:22} {r['weight']:>7.1f} {current_str} {hot_str} {cap_str} "
            f"{hot_mark:>6} {r['progress']:>13.1f}% {r['capped_progress']:>13.1f}%{note}"
        )
    print()
    excluded = [r["slug"] for r in results if r["no_value"]]
    print(
        f"[종합] 초고온: {hit_count}/{len(results)}, 원점수(가중평균): {raw_score:.2f} "
        f"→ 표시 점수: {weighted_score:.2f} (weight_sum: {weight_sum:.1f}), stage: {stage}"
        + (f", 제외됨: {', '.join(excluded)}" if excluded else "")
    )

    # 0에 눌린 지표는 "더 식어도 점수를 못 내리는" 상태다. 한둘이면 정상(순매도·비관처럼
    # 과열의 반대는 0이 맞다)이지만, 가중치 합이 커지면 종합점수가 구조적으로 위로만
    # 움직이게 된다. 눈금이 실제 분포와 어긋났다는 신호이기도 해서 매 실행 찍어 둔다.
    clamped = [r for r in weighted_results if r["capped_progress"] <= 0.0]
    if clamped:
        cw = sum(r["weight"] for r in clamped)
        print(
            f"[감시] 과열도 0으로 눌린 지표 {len(clamped)}개 · 가중치 {cw:.1f}/{weight_sum:.1f} "
            f"({cw / weight_sum * 100:.0f}%): " + ", ".join(r["slug"] for r in clamped)
        )

    for r in results:
        payload = {
            "normalized_score": round(r["progress"], 2),
            "threshold": round(r["threshold"], 2) if r["threshold"] is not None else None,
        }
        # details는 fetch 스크립트와 나눠 쓰는 칸이라 통째로 대입하면 남의 키가 날아간다
        # (2026-07-20 괴리 카드가 그렇게 비었다). 읽어온 기존 값 위에 내 키만 얹는다.
        merged = dict(r.get("base_details") or {})
        merged.update(r.get("extra_details") or {})
        if r.get("hot_threshold") is not None:
            merged["hot_threshold"] = round(r["hot_threshold"], 4)
        if merged:
            payload["details"] = merged
        client.table("indicator_values").update(payload).eq(
            "indicator_id", r["indicator_id"]
        ).eq("date", r["date"]).execute()
    print(f"[Supabase] indicator_values.normalized_score upsert 완료 ({len(results)}건, 원본 Progress 저장)")

    today = date.today().isoformat()
    now_utc = datetime.now(timezone.utc).isoformat()
    client.table("daily_score").upsert(
        {
            "date": today,
            "score": round(weighted_score, 2),
            "stage": stage,
            "updated_at": now_utc,
        },
        on_conflict="date",
    ).execute()
    print(
        f"[Supabase] daily_score upsert 완료: date={today}, score={round(weighted_score, 2)}, "
        f"stage={stage}, updated_at={now_utc}"
    )


if __name__ == "__main__":
    main()
