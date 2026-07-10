"""7개 지표의 현재값을 기준선과 비교해 과열도 스코어를 계산하고 daily_score/indicator_values에 저장.

기준선(threshold) 종류:
- 고정 기준선: buffett_index(100), kospi_high_gap(0)
- 데이터 기반 기준선: us10y/naver_search_trend(과거 1년치의 상위 5% 지점),
  dcinside_post_count(과거 30일치의 상위 5% 지점), kospi_volume_surge(과거 1년치의
  상위 5% 지점), vkospi(과거 1년치의 하위 5% 지점 — 아래 direction 설명 참고)

kospi_high_gap은 0 이하 값만 가지는 지표라 (현재값/기준선)*100 공식을 그대로 쓸 수
없다. "0% 진행" 기준점(floor)을 두고 0%(기준선)를 "100% 진행"으로 선형 보간한다.
이 floor는 원래 -20%로 고정된 가정값이었는데, 실제 관측치(-20.49%)가 이미 그보다
더 내려가 있어서 progress가 항상 음수 → 0%로 캡핑되며 progress bar가 늘 비어
보이는 문제가 있었다. 이제는 kospi_close_raw(1년치 종가 히스토리)의 연중
최저/최고가로 "지난 1년간 실제로 관측된 최대 낙폭"을 계산해 floor로 쓴다
(compute_kospi_high_gap_floor) — 히스토리가 부족하면 예전 고정값(-20%)으로
대체한다.

vkospi는 다른 지표와 반대 방향이다 — 값이 낮을수록(시장이 방심할수록) 과열 신호다.
config에 "direction": "low"를 주면 기준선을 하위 5% 지점으로 잡고, 현재값이 그
이하일 때 Hit, progress = threshold/current*100 (낮을수록 progress가 커짐)으로
계산한다. 나머지 지표는 기본값인 "high" 방향(현재값이 기준선 이상일 때 Hit)을 쓴다.

Progress는 두 가지 버전을 함께 다룬다:
- 원본(raw) Progress: 100%를 넘거나 음수여도 그대로 둔 값. "기준선을 몇 % 초과했는지"
  같은 상세 정보를 보여줘야 하는 indicator_values.normalized_score에 저장한다.
- 캡핑(capped) Progress: 0~100% 범위로 자른 값(min(max(x, 0), 100)). 지표 하나가
  100%를 크게 초과해 종합 스코어를 왜곡하지 않도록, daily_score.score(아래
  설명하는 가중 평균)는 이 캡핑된 값들로 계산한다.

percentile 기준선을 계산하려면 지표별로 최소 MIN_PERCENTILE_SAMPLES개의 과거
데이터가 필요하다. 갤러리 교체 등으로 특정 지표의 히스토리가 막 리셋된 경우처럼
데이터가 부족하면, 그 지표 하나 때문에 스크립트 전체가 죽어서 나머지 지표까지
daily_score 갱신이 막히는 걸 막기 위해 해당 지표만 hit=False/progress=50(중립)으로
대체하고 경고를 남긴 뒤 계속 진행한다.

예외: youtube_finance_search_views는 이 percentile/중립-폴백 방식을 쓰지 않는
유일한 지표다. 나머지 12개 percentile 지표는 "과거 N일치의 상위 P% 지점"을
고정 기준선으로 삼지만, 이 지표는 window_days/percentile/MIN_PERCENTILE_SAMPLES
개념 자체가 없고 대신 "오늘 값을 포함한 지금까지의 전체 평균"을 매일 다시 계산해
그날의 기준선으로 쓴다(compute_threshold의 "cumulative_average" 분기). 표본이
1개(오늘 하루)뿐이어도 평균=오늘 값이 되어 progress가 100%로 나오는데, 이는
데이터 부족으로 판단을 보류하는 게 아니라 의도된 동작이다 — 데이터가 쌓일수록
평균이 더 많은 날짜를 반영하며 비교 기준이 자연스럽게 안정되기 때문이다.

daily_score.score("햇쩨 지수")는 지표별 capped_progress의 가중 평균이다
(Σ(weight_i × capped_progress_i) / Σ(weight_i), weight는 indicators.weight).
단, "데이터가 아예 없는" 지표(KRX 승인 대기 중인 vkospi/kosdaq_kospi_ratio/
leverage_etf_volume처럼 indicator_values에 값 자체가 한 건도 없는 경우)는
승인 전까지 지수를 왜곡하지 않도록 가중 평균에서 완전히 제외한다(분모의
weight 합계에도 포함하지 않음). 반면 "값은 있지만 percentile 계산에 필요한
히스토리가 부족한" 지표(초기의 dcinside_post_count, news_sentiment 등)는
중립값(50%)으로 채워서 가중 평균에 계속 참여시킨다 — 이 둘을 구분하는 게
get_latest_value(값 자체가 없음, no_value=True)와 compute_threshold(값은
있지만 percentile 계산 불가, insufficient=True)의 실패 지점 차이다.

stage(냉정/보통/과열/광기)는 이 가중 평균 점수 자체를 4구간으로 나눠 정한다
(stage_for_score) — 예전처럼 hit_count 비율로 정하지 않는다. hit_count는
화면의 Hit 배지 표시용으로 계속 계산하지만, stage 산정에는 더 이상 관여하지
않는다.
"""

from __future__ import annotations

import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402

KOSPI_HIGH_GAP_FALLBACK_FLOOR = -20.0  # kospi_close_raw 히스토리가 부족할 때의 대체값
KOSPI_CLOSE_RAW_SLUG = "kospi_close_raw"
MIN_PERCENTILE_SAMPLES = 5  # percentile 기준선 계산에 필요한 최소 과거 데이터 개수
NEUTRAL_PROGRESS = 50.0  # 히스토리 부족으로 판단을 보류할 때 대체하는 "중립" 값


class InsufficientHistoryError(Exception):
    """percentile 기준선을 계산하기에 과거 데이터가 부족할 때 발생."""


INDICATOR_ORDER = [
    "buffett_index",
    "kospi_high_gap",
    "us10y",
    "naver_search_trend",
    "dcinside_post_count",
    "kospi_volume_surge",
    "vkospi",
    "news_sentiment",
    "kospi_gold_ratio",
    "kosdaq_kospi_ratio",
    "usdkrw_volatility",
    "leverage_etf_volume",
    "bestseller_finance_ratio",
    "youtube_finance_search_views",
]

INDICATOR_CONFIGS = {
    "buffett_index": {"kind": "fixed", "threshold": 100.0},
    "kospi_high_gap": {"kind": "fixed", "threshold": 0.0},
    "us10y": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "naver_search_trend": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "dcinside_post_count": {"kind": "percentile", "window_days": 30, "percentile": 95},
    "kospi_volume_surge": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "vkospi": {"kind": "percentile", "window_days": 365, "percentile": 5, "direction": "low"},
    "news_sentiment": {"kind": "percentile", "window_days": 30, "percentile": 95},
    "kospi_gold_ratio": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "kosdaq_kospi_ratio": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "usdkrw_volatility": {"kind": "percentile", "window_days": 365, "percentile": 5, "direction": "low"},
    "leverage_etf_volume": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "bestseller_finance_ratio": {"kind": "percentile", "window_days": 30, "percentile": 95},
    # youtube_finance_search_views만 percentile이 아니라 "누적 평균 대비 비율"
    # 방식을 쓴다 — 아래 compute_threshold의 "cumulative_average" 분기와
    # 모듈 docstring 설명 참고.
    "youtube_finance_search_views": {"kind": "cumulative_average"},
}


def percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    quantiles = statistics.quantiles(sorted(values), n=100, method="inclusive")
    index = min(max(round(pct), 1), 99) - 1
    return quantiles[index]


def get_indicator(client, slug: str) -> tuple[str, str, float]:
    result = (
        client.table("indicators").select("id,name,weight").eq("slug", slug).execute()
    )
    if not result.data:
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    row = result.data[0]
    weight = float(row["weight"]) if row.get("weight") is not None else 1.0
    return row["id"], row["name"], weight


def get_latest_value(client, indicator_id: str) -> tuple[str, float]:
    result = (
        client.table("indicator_values")
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise InsufficientHistoryError(f"indicator_id={indicator_id}에 값이 아직 없습니다")
    row = result.data[0]
    return row["date"], float(row["raw_value"])


def get_indicator_id_or_none(client, slug: str) -> str | None:
    result = client.table("indicators").select("id").eq("slug", slug).execute()
    if not result.data:
        return None
    return result.data[0]["id"]


def compute_kospi_high_gap_floor(client) -> float:
    """kospi_close_raw의 지난 1년 최고/최저 종가로 "실제 관측된 최대 낙폭"을
    구해 kospi_high_gap의 floor로 쓴다. 히스토리가 부족하면 대체값을 쓴다.
    """
    raw_id = get_indicator_id_or_none(client, KOSPI_CLOSE_RAW_SLUG)
    if raw_id is None:
        return KOSPI_HIGH_GAP_FALLBACK_FLOOR

    values = get_window_values(client, raw_id, 365)
    if len(values) < MIN_PERCENTILE_SAMPLES:
        return KOSPI_HIGH_GAP_FALLBACK_FLOOR

    year_high = max(values)
    year_low = min(values)
    return round((year_low - year_high) / year_high * 100, 2)


def get_window_values(client, indicator_id: str, window_days: int) -> list[float]:
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    result = (
        client.table("indicator_values")
        .select("raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", cutoff)
        .execute()
    )
    return [float(r["raw_value"]) for r in result.data]


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

    if config["kind"] == "cumulative_average":
        # youtube_finance_search_views 전용: percentile/MIN_PERCENTILE_SAMPLES를
        # 쓰지 않고, 오늘 값을 포함해 지금까지 쌓인 전체 값의 평균을 매일 다시
        # 계산해 그날의 기준선으로 삼는다. 데이터가 1건(오늘)뿐이면 평균=오늘 값이라
        # progress가 항상 100%로 나오는데, 이건 "판단을 보류"하는 게 아니라 의도된
        # 결과다 — 데이터가 쌓일수록 평균이 더 많은 날짜를 반영하며 자연스럽게
        # 비교 기준이 안정된다. 따라서 다른 percentile 지표와 달리
        # InsufficientHistoryError를 던지지 않고, 표본이 몇 개든 그냥 계산한다.
        values = get_all_values(client, indicator_id)
        return statistics.mean(values)

    values = get_window_values(client, indicator_id, config["window_days"])
    if len(values) < MIN_PERCENTILE_SAMPLES:
        raise InsufficientHistoryError(
            f"percentile 계산에 최소 {MIN_PERCENTILE_SAMPLES}개 데이터가 필요한데 "
            f"{len(values)}개뿐입니다"
        )
    return percentile(values, config["percentile"])


def compute_hit(current: float, threshold: float, config: dict) -> bool:
    if config.get("direction") == "low":
        return current <= threshold
    return current >= threshold


def compute_progress(slug: str, current: float, threshold: float, config: dict) -> float:
    if slug == "kospi_high_gap":
        floor = config["floor"]
        return (current - floor) / (threshold - floor) * 100
    if config.get("direction") == "low":
        if current == 0:
            return 0.0
        return threshold / current * 100
    return current / threshold * 100


def cap_progress(progress: float) -> float:
    return min(max(progress, 0.0), 100.0)


def stage_for_score(score: float) -> str:
    if score < 25:
        return "냉정"
    if score < 50:
        return "보통"
    if score < 75:
        return "과열"
    return "광기"


def main() -> None:
    client = get_client()

    results = []
    for slug in INDICATOR_ORDER:
        config = INDICATOR_CONFIGS[slug]
        if slug == "kospi_high_gap":
            floor = compute_kospi_high_gap_floor(client)
            config = {**config, "floor": floor}
            print(f"[kospi_high_gap] floor(지난 1년 최대 낙폭) = {floor}%")

        indicator_id, name, weight = get_indicator(client, slug)

        try:
            latest_date, current = get_latest_value(client, indicator_id)
        except InsufficientHistoryError as e:
            print(f"[WARNING] '{slug}' 값이 아직 없어 가중 평균에서 제외됨: {e}")
            latest_date = date.today().isoformat()
            current = None
            threshold = None
            hit = False
            progress = NEUTRAL_PROGRESS
            capped_progress = NEUTRAL_PROGRESS
            insufficient = True
            no_value = True
        else:
            no_value = False
            try:
                threshold = compute_threshold(client, indicator_id, config)
                hit = compute_hit(current, threshold, config)
                progress = compute_progress(slug, current, threshold, config)
                capped_progress = cap_progress(progress)
                insufficient = False
            except InsufficientHistoryError as e:
                print(f"[WARNING] '{slug}' 데이터 부족으로 중립(50%) 처리, 가중 평균엔 포함: {e}")
                threshold = None
                hit = False
                progress = NEUTRAL_PROGRESS
                capped_progress = NEUTRAL_PROGRESS
                insufficient = True

        results.append(
            {
                "slug": slug,
                "name": name,
                "weight": weight,
                "indicator_id": indicator_id,
                "date": latest_date,
                "current": current,
                "threshold": threshold,
                "hit": hit,
                "progress": progress,
                "capped_progress": capped_progress,
                "insufficient": insufficient,
                "no_value": no_value,
            }
        )

    hit_count = sum(1 for r in results if r["hit"])
    weighted_results = [r for r in results if not r["no_value"]]
    weight_sum = sum(r["weight"] for r in weighted_results)
    weighted_score = (
        sum(r["weight"] * r["capped_progress"] for r in weighted_results) / weight_sum
        if weight_sum > 0
        else 0.0
    )
    stage = stage_for_score(weighted_score)

    print(
        f"{'slug':22} {'weight':>7} {'현재값':>14} {'기준선':>14} {'Hit':>5} "
        f"{'Progress(원본)':>14} {'Progress(캡핑)':>14}"
    )
    for r in results:
        hit_mark = "O" if r["hit"] else "X"
        current_str = (
            f"{r['current']:>14.2f}" if r["current"] is not None else f"{'N/A':>14}"
        )
        threshold_str = (
            f"{r['threshold']:>14.2f}" if r["threshold"] is not None else f"{'N/A':>14}"
        )
        if r["no_value"]:
            note = "  (값 없음 - 가중 평균에서 제외)"
        elif r["insufficient"]:
            note = "  (데이터 부족 - 중립 처리, 가중 평균엔 포함)"
        else:
            note = ""
        print(
            f"{r['slug']:22} {r['weight']:>7.1f} {current_str} {threshold_str} "
            f"{hit_mark:>5} {r['progress']:>13.1f}% {r['capped_progress']:>13.1f}%{note}"
        )
    print()
    excluded = [r["slug"] for r in results if r["no_value"]]
    print(
        f"[종합] Hit: {hit_count}/{len(results)}, weighted_score: {weighted_score:.2f}% "
        f"(weight_sum: {weight_sum:.1f}), stage: {stage}"
        + (f", 제외됨: {', '.join(excluded)}" if excluded else "")
    )

    for r in results:
        client.table("indicator_values").update(
            {"normalized_score": round(r["progress"], 2)}
        ).eq("indicator_id", r["indicator_id"]).eq("date", r["date"]).execute()
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
