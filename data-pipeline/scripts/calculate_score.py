"""5개 지표의 현재값을 기준선과 비교해 과열도 스코어를 계산하고 daily_score/indicator_values에 저장.

기준선(threshold) 종류:
- 고정 기준선: buffett_index(100), kospi_high_gap(0)
- 데이터 기반 기준선: us10y/naver_search_trend(과거 1년치의 상위 5% 지점),
  dcinside_post_count(과거 30일치의 상위 5% 지점)

kospi_high_gap은 0 이하 값만 가지는 지표라 (현재값/기준선)*100 공식을 그대로 쓸 수
없다. KOSPI_HIGH_GAP_FLOOR(기준선까지의 거리를 재는 "0% 진행" 기준점, 지금까지
관측된 실제 값과 비슷한 -20%로 설정한 가정값)을 두고 0%(기준선)를 "100% 진행"으로
선형 보간한다.

Progress는 두 가지 버전을 함께 다룬다:
- 원본(raw) Progress: 100%를 넘거나 음수여도 그대로 둔 값. "기준선을 몇 % 초과했는지"
  같은 상세 정보를 보여줘야 하는 indicator_values.normalized_score에 저장한다.
- 캡핑(capped) Progress: 0~100% 범위로 자른 값(min(max(x, 0), 100)). 지표 하나가
  100%를 크게 초과해 종합 스코어를 왜곡하지 않도록, daily_score.score(평균)는
  이 캡핑된 값들의 평균으로 계산한다.

percentile 기준선을 계산하려면 지표별로 최소 MIN_PERCENTILE_SAMPLES개의 과거
데이터가 필요하다. 갤러리 교체 등으로 특정 지표의 히스토리가 막 리셋된 경우처럼
데이터가 부족하면, 그 지표 하나 때문에 스크립트 전체가 죽어서 나머지 4개 지표까지
daily_score 갱신이 막히는 걸 막기 위해 해당 지표만 hit=False/progress=50(중립)으로
대체하고 경고를 남긴 뒤 계속 진행한다.
"""

from __future__ import annotations

import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402

KOSPI_HIGH_GAP_FLOOR = -20.0  # "0% 진행"으로 볼 기준점 (조정 가능한 가정값)
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
]

INDICATOR_CONFIGS = {
    "buffett_index": {"kind": "fixed", "threshold": 100.0},
    "kospi_high_gap": {"kind": "fixed", "threshold": 0.0, "floor": KOSPI_HIGH_GAP_FLOOR},
    "us10y": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "naver_search_trend": {"kind": "percentile", "window_days": 365, "percentile": 95},
    "dcinside_post_count": {"kind": "percentile", "window_days": 30, "percentile": 95},
}


def percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    quantiles = statistics.quantiles(sorted(values), n=100, method="inclusive")
    index = min(max(round(pct), 1), 99) - 1
    return quantiles[index]


def get_indicator(client, slug: str) -> tuple[str, str]:
    result = client.table("indicators").select("id,name").eq("slug", slug).execute()
    if not result.data:
        raise RuntimeError(
            f"indicator '{slug}'가 존재하지 않습니다. 해당 fetch 스크립트를 먼저 실행하세요."
        )
    return result.data[0]["id"], result.data[0]["name"]


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
        raise RuntimeError(f"indicator_id={indicator_id}에 값이 없습니다")
    row = result.data[0]
    return row["date"], float(row["raw_value"])


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


def compute_threshold(client, indicator_id: str, config: dict) -> float:
    if config["kind"] == "fixed":
        return config["threshold"]

    values = get_window_values(client, indicator_id, config["window_days"])
    if len(values) < MIN_PERCENTILE_SAMPLES:
        raise InsufficientHistoryError(
            f"percentile 계산에 최소 {MIN_PERCENTILE_SAMPLES}개 데이터가 필요한데 "
            f"{len(values)}개뿐입니다"
        )
    return percentile(values, config["percentile"])


def compute_progress(slug: str, current: float, threshold: float, config: dict) -> float:
    if slug == "kospi_high_gap":
        floor = config["floor"]
        return (current - floor) / (threshold - floor) * 100
    return current / threshold * 100


def cap_progress(progress: float) -> float:
    return min(max(progress, 0.0), 100.0)


def stage_for_hit_count(hit_count: int) -> str:
    if hit_count <= 1:
        return "냉정"
    if hit_count == 2:
        return "보통"
    if hit_count == 3:
        return "과열"
    return "광기"  # 4 or 5


def main() -> None:
    client = get_client()

    results = []
    for slug in INDICATOR_ORDER:
        config = INDICATOR_CONFIGS[slug]
        indicator_id, name = get_indicator(client, slug)
        latest_date, current = get_latest_value(client, indicator_id)

        try:
            threshold = compute_threshold(client, indicator_id, config)
            hit = current >= threshold
            progress = compute_progress(slug, current, threshold, config)
            capped_progress = cap_progress(progress)
            insufficient = False
        except InsufficientHistoryError as e:
            print(f"[WARNING] '{slug}' 히스토리 부족으로 중립 처리됨: {e}")
            threshold = None
            hit = False
            progress = NEUTRAL_PROGRESS
            capped_progress = NEUTRAL_PROGRESS
            insufficient = True

        results.append(
            {
                "slug": slug,
                "name": name,
                "indicator_id": indicator_id,
                "date": latest_date,
                "current": current,
                "threshold": threshold,
                "hit": hit,
                "progress": progress,
                "capped_progress": capped_progress,
                "insufficient": insufficient,
            }
        )

    hit_count = sum(1 for r in results if r["hit"])
    average_progress = sum(r["capped_progress"] for r in results) / len(results)
    stage = stage_for_hit_count(hit_count)

    print(
        f"{'slug':22} {'현재값':>14} {'기준선':>14} {'Hit':>5} "
        f"{'Progress(원본)':>14} {'Progress(캡핑)':>14}"
    )
    for r in results:
        hit_mark = "O" if r["hit"] else "X"
        threshold_str = (
            f"{r['threshold']:>14.2f}" if r["threshold"] is not None else f"{'N/A':>14}"
        )
        note = "  (히스토리 부족 - 중립 처리)" if r["insufficient"] else ""
        print(
            f"{r['slug']:22} {r['current']:>14.2f} {threshold_str} "
            f"{hit_mark:>5} {r['progress']:>13.1f}% {r['capped_progress']:>13.1f}%{note}"
        )
    print()
    print(f"[종합] Hit: {hit_count}/5, average_progress(캡핑 기준): {average_progress:.2f}%, stage: {stage}")

    for r in results:
        client.table("indicator_values").update(
            {"normalized_score": round(r["progress"], 2)}
        ).eq("indicator_id", r["indicator_id"]).eq("date", r["date"]).execute()
    print("[Supabase] indicator_values.normalized_score upsert 완료 (5건, 원본 Progress 저장)")

    today = date.today().isoformat()
    client.table("daily_score").upsert(
        {"date": today, "score": round(average_progress, 2), "stage": stage},
        on_conflict="date",
    ).execute()
    print(f"[Supabase] daily_score upsert 완료: date={today}, score={round(average_progress, 2)}, stage={stage}")


if __name__ == "__main__":
    main()
