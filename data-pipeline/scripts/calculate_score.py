"""26개 지표의 현재값을 기준선과 비교해 과열도 스코어를 계산하고 daily_score/indicator_values에 저장.

기준선(threshold)은 이제 전부 리서치/논리 기반의 고정값이다
(config/indicator_thresholds.py의 INDICATOR_THRESHOLDS). 원래는 과거 데이터의
상위/하위 N% 지점(percentile)을 기준선으로 썼는데, 그러려면 지표별로 최소
표본 수가 쌓일 때까지 기준선 자체가 계속 흔들리는 문제가 있었다. 기준값을
조정하고 싶으면 이 파일이 아니라 indicator_thresholds.py만 고치면 된다.

kospi_high_gap만 예외로, 기준선(threshold=0)은 고정이지만 progress 계산에
쓰는 "0% 진행" 기준점(floor)은 지금도 동적으로 계산한다. kospi_high_gap은
0 이하 값만 가지는 지표라 (현재값/기준선)*100 공식을 그대로 쓸 수 없어서,
floor를 두고 0%(기준선)를 "100% 진행"으로 선형 보간한다. 이 floor는
kospi_close_raw(1년치 종가 히스토리)의 연중 최저/최고가로 "지난 1년간
실제로 관측된 최대 낙폭"을 계산한다(compute_kospi_high_gap_floor) — 히스토리가
부족하면 고정 대체값(-20%)을 쓴다.

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

daily_score.score("햇쩨 지수")는 지표별 capped_progress의 가중 평균이다
(Σ(weight_i × capped_progress_i) / Σ(weight_i), weight는 indicators.weight).
단, "데이터가 아예 없는" 지표는 가중 평균에서 완전히 제외한다(분모의 weight
합계에도 포함하지 않음) — get_latest_value가 InsufficientHistoryError를
던지는 no_value 케이스가 이 경우다.

stage(저온/상온/고온/초고온)는 이 가중 평균 점수 자체를 4구간으로 나눠 정한다
(stage_for_score) — hit_count 비율로 정하지 않는다. hit_count는 화면의 Hit
배지 표시용으로 계속 계산하지만, stage 산정에는 관여하지 않는다.
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

KOSPI_HIGH_GAP_FALLBACK_FLOOR = -20.0  # kospi_close_raw 히스토리가 부족할 때의 대체값
KOSPI_CLOSE_RAW_SLUG = "kospi_close_raw"
MIN_FLOOR_HISTORY_SAMPLES = 5  # kospi_high_gap floor 계산에 필요한 최소 과거 데이터 개수
NEUTRAL_PROGRESS = 50.0  # 값이 아예 없는 지표(no_value)를 표에 표시할 때 쓰는 자리표시자

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
    if len(values) < MIN_FLOOR_HISTORY_SAMPLES:
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

    # cumulative_average (youtube_finance_search_views 전용): 오늘 값을 포함해
    # 지금까지 쌓인 전체 값의 평균을 매일 다시 계산해 그날의 기준선으로 삼는다.
    # 데이터가 1건(오늘)뿐이면 평균=오늘 값이라 progress가 항상 100%로 나오는데,
    # 이건 "판단을 보류"하는 게 아니라 의도된 결과다 — 데이터가 쌓일수록 평균이
    # 더 많은 날짜를 반영하며 자연스럽게 비교 기준이 안정된다. get_latest_value가
    # 이미 성공했다는 건 최소 1건은 있다는 뜻이라 표본이 몇 개든 그냥 계산한다.
    values = get_all_values(client, indicator_id)
    return statistics.mean(values)


def compute_hit(current: float, threshold: float, config: dict) -> bool:
    if config.get("direction") == "low":
        return current <= threshold
    return current >= threshold


def compute_progress(slug: str, current: float, threshold: float, config: dict) -> float:
    if slug == "kospi_high_gap":
        floor = config["floor"]
        return (current - floor) / (threshold - floor) * 100
    if slug in NEGATIVE_CURRENT_CLAMP_SLUGS and current < 0:
        return 0.0
    if config.get("direction") == "low":
        if current == 0:
            return 0.0
        return threshold / current * 100
    return current / threshold * 100


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
            no_value = True
        else:
            no_value = False
            threshold = compute_threshold(client, indicator_id, config)
            hit = compute_hit(current, threshold, config)
            progress = compute_progress(slug, current, threshold, config)
            capped_progress = cap_progress(progress)

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
        note = "  (값 없음 - 가중 평균에서 제외)" if r["no_value"] else ""
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
            {
                "normalized_score": round(r["progress"], 2),
                "threshold": round(r["threshold"], 2) if r["threshold"] is not None else None,
            }
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
