"""과거 날짜의 과열도(normalized_score)와 종합점수(daily_score)를 소급 계산한다.

**왜 필요한가.** calculate_score.py 는 매 실행 '그날의 최신 행' 하나만 갱신한다. 그래서
raw_value 는 1년치가 쌓여 있어도 과열도는 최근 며칠분만 채워져 있다(2026-07-23 기준
raw 4,293행 중 263행). daily_score 도 15행뿐이라 과열도 추이 차트를 그릴 수가 없다.
이 스크립트가 raw 히스토리 전체에 지금의 공식·임계값을 적용해 그 빈칸을 메운다.

**날짜마다 기준선이 다른 지표를 어떻게 다루나.**
- cumulative_average(유튜브·예탁금): 그날까지 쌓인 값만으로 평균을 낸다. 오늘 기준
  평균을 과거에 소급하면 그때는 알 수 없던 정보를 쓰는 셈이라(lookahead) 추이가 왜곡된다.
- relative_surge(거래대금): fetch 가 날짜별로 details.surge_pct 를 남겨 둬 그대로 쓴다.
- 실물–증시 괴리: CCSI(월 1회)와 코스피 신고가 괴리율이 둘 다 있는 날만 계산한다.
  둘 중 하나라도 없는 과거 날짜는 **그 지표를 그날 가중 평균에서 빼고**, 옛 의미
  (자영업 검색지수 ÷ 70)로 억지로 채우지 않는다.

**종합점수의 한계 — 차트에 쓸 때 반드시 알아야 한다.** 지표마다 수집 시작일이 달라
과거로 갈수록 계산에 들어가는 지표가 적어진다. calculate_score 와 동일하게 '그날 값이
있는 지표'만으로 가중 평균을 내므로(분모도 그만큼 작아진다) 값 자체는 일관되지만,
2026-07-09 이전은 가중치 50 중 28.5(57%)만으로 계산된 값이다. 차트에 그릴 때는 그
경계를 표시하거나, 전 지표가 갖춰진 구간만 쓰는 게 정직하다.

실행:
    python scripts/backfill_scores.py                  # 미리보기만 (기본)
    python scripts/backfill_scores.py --apply          # 과열도 저장
    python scripts/backfill_scores.py --apply --daily-score   # 종합점수까지 재계산
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from config.indicator_thresholds import INDICATOR_THRESHOLDS  # noqa: E402
from config.indicator_weights import INDICATOR_WEIGHTS  # noqa: E402

# calculate_score 의 공식을 그대로 쓴다 — 두 벌로 두면 반드시 어긋난다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calculate_score import (  # noqa: E402
    CCSI_PCTILE_ANCHORS,
    CCSI_SLUG,
    HOT_ZONE,
    KOSPI_DD_PCTILE_ANCHORS,
    cap_progress,
    compute_progress,
    percentile_from_anchors,
    stage_for_score,
)

BATCH = 500


def load_series(client, indicator_id: str) -> list[dict]:
    """(date, raw_value, details) 전체. 1,000행 상한을 넘길 수 있어 페이지를 이어 받는다."""
    out, start = [], 0
    while True:
        page = (
            client.table("indicator_values")
            .select("date,raw_value,details")
            .eq("indicator_id", indicator_id)
            .order("date")
            .range(start, start + 999)
            .execute()
            .data
        )
        if not page:
            break
        out += page
        if len(page) < 1000:
            break
        start += 1000
    return out


def progress_by_date(slug: str, rows: list[dict]) -> dict[str, float]:
    """날짜 → 원본 progress(캡핑 전). 계산 불가한 날짜는 뺀다."""
    cfg = INDICATOR_THRESHOLDS[slug]
    out: dict[str, float] = {}
    running: list[float] = []

    for r in rows:
        cur = float(r["raw_value"])
        details = r.get("details") or {}

        if cfg["kind"] == "cumulative_average":
            running.append(cur)
            threshold = sum(running) / len(running)  # 그날까지만 — lookahead 방지
        else:
            threshold = cfg["threshold"]

        rs = cfg.get("relative_surge")
        if rs is not None:
            surge = details.get("surge_pct")
            if surge is None:
                continue  # fetch 가 아직 세부값을 안 남긴 날짜
            out[r["date"]] = (float(surge) - rs["floor"]) / (rs["ceil"] - rs["floor"]) * 100
            continue

        out[r["date"]] = compute_progress(slug, cur, threshold, cfg)
    return out


def divergence_by_date(client, ids: dict[str, str]) -> dict[str, float]:
    """실물–증시 괴리: 날짜 → progress(= max(0, 증시%ile − 실물%ile)).

    CCSI 는 월 1회라 그 달 이후의 모든 날짜에 '가장 최근 공표값'을 적용한다.
    코스피 신고가 괴리율이 없는 날짜는 계산하지 않는다(그 지표를 그날 제외).
    """
    if CCSI_SLUG not in ids or "kospi_high_gap" not in ids:
        return {}
    ccsi_rows = load_series(client, ids[CCSI_SLUG])
    gap_rows = load_series(client, ids["kospi_high_gap"])
    if not ccsi_rows or not gap_rows:
        return {}

    ccsi_sorted = sorted((r["date"], float(r["raw_value"])) for r in ccsi_rows)
    out: dict[str, float] = {}
    for g in gap_rows:
        d = g["date"]
        prior = [v for cd, v in ccsi_sorted if cd <= d]
        if not prior:
            continue
        real = percentile_from_anchors(prior[-1], CCSI_PCTILE_ANCHORS)
        market = percentile_from_anchors(float(g["raw_value"]), KOSPI_DD_PCTILE_ANCHORS)
        out[d] = max(0.0, market - real)
    return out


def main() -> None:
    apply = "--apply" in sys.argv
    do_daily = "--daily-score" in sys.argv
    client = get_client()

    ids = {
        r["slug"]: r["id"]
        for r in client.table("indicators").select("id,slug").execute().data
    }

    per_indicator: dict[str, dict[str, float]] = {}
    raw_lookup: dict[str, dict[str, float]] = {}
    for slug in INDICATOR_WEIGHTS:
        if slug not in ids:
            print(f"[WARNING] '{slug}' 지표 행이 없어 건너뜁니다")
            continue
        rows = load_series(client, ids[slug])
        raw_lookup[slug] = {r["date"]: float(r["raw_value"]) for r in rows}
        per_indicator[slug] = progress_by_date(slug, rows)
        print(f"  {slug:32} raw {len(rows):>4}행 → 과열도 {len(per_indicator[slug]):>4}일치")

    # 괴리 지수는 calculate_score 와 동일하게 override 한다.
    div = divergence_by_date(client, ids)
    if div:
        per_indicator["small_business_crisis_index"] = div
        print(f"  {'small_business_crisis_index(괴리 override)':32} → {len(div)}일치")

    total = sum(len(v) for v in per_indicator.values())
    print(f"\n[과열도] 계산 완료: {total}일치 (지표 {len(per_indicator)}개)")

    if apply:
        n = 0
        for slug, by_date in per_indicator.items():
            payload = [
                {
                    "indicator_id": ids[slug],
                    "date": d,
                    "raw_value": raw_lookup[slug][d],
                    "normalized_score": round(p, 2),
                }
                for d, p in sorted(by_date.items())
                if d in raw_lookup.get(slug, {})
            ]
            for i in range(0, len(payload), BATCH):
                client.table("indicator_values").upsert(
                    payload[i : i + BATCH], on_conflict="indicator_id,date"
                ).execute()
            n += len(payload)
        print(f"[Supabase] normalized_score {n}건 저장")
    else:
        print("[미리보기] --apply 를 붙이면 저장합니다.")

    # ── 종합점수 ────────────────────────────────────────────────────────────
    # 날짜를 정확히 맞춰 합치면 안 된다. 지표마다 갱신 주기가 달라서(KRX는 영업일만,
    # 검색지수는 주말도, 예탁금은 D+1) 어떤 날은 25개가 모이고 어떤 날은 13개뿐이라
    # 점수가 시장이 아니라 '그날 몇 개가 모였나'에 따라 출렁인다.
    #
    # calculate_score 는 지표별 **최신값**을 쓴다 — 사실상 앞으로 채우기(forward-fill)다.
    # 같은 규칙을 소급 적용해야 라이브 값과 이어지는 시리즈가 나온다. 단, 영영 멈춘
    # 지표를 무한히 끌고 가지 않도록 CARRY_LIMIT_DAYS 를 넘으면 그날부터 뺀다.
    CARRY_LIMIT_DAYS = 10

    all_days = sorted({d for m in per_indicator.values() for d in m})
    first, last = date.fromisoformat(all_days[0]), date.fromisoformat(all_days[-1])

    scores = {}
    cursor = first
    while cursor <= last:
        d = cursor.isoformat()
        items: list[tuple[str, float]] = []
        for slug, m in per_indicator.items():
            prior = [x for x in m if x <= d]
            if not prior:
                continue
            src = max(prior)
            if (cursor - date.fromisoformat(src)).days > CARRY_LIMIT_DAYS:
                continue  # 너무 오래 멈춘 지표는 그날 계산에서 뺀다
            items.append((slug, cap_progress(m[src])))
        wsum = sum(INDICATOR_WEIGHTS[s] for s, _ in items)
        if wsum > 0:
            scores[d] = (
                sum(INDICATOR_WEIGHTS[s] * p for s, p in items) / wsum,
                wsum,
                len(items),
            )
        cursor += timedelta(days=1)

    days = sorted(scores)
    print(f"\n[종합점수] {len(days)}일치 계산 ({days[0]} ~ {days[-1]})")
    print(f"  {'날짜':12}{'점수':>7}{'구간':>6}{'지표':>5}{'가중치합':>8}")
    for d in days[:3] + ["…"] + days[-5:]:
        if d == "…":
            print("  …")
            continue
        s, w, n = scores[d]
        print(f"  {d:12}{s:>7.2f}{stage_for_score(s):>6}{n:>5}{w:>8.1f}")

    full = sum(INDICATOR_WEIGHTS.values())
    partial = [d for d in days if scores[d][1] < full * 0.95]
    if partial:
        print(
            f"\n  ⚠ 지표가 다 갖춰지지 않은 날짜 {len(partial)}일 "
            f"({partial[0]} ~ {partial[-1]}) — 가중치 합이 {full:.1f} 미만이라 "
            f"이후 구간과 같은 잣대가 아닙니다."
        )

    if do_daily and apply:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "date": d,
                "score": round(scores[d][0], 2),
                "stage": stage_for_score(scores[d][0]),
                "updated_at": now,
            }
            for d in days
        ]
        for i in range(0, len(rows), BATCH):
            client.table("daily_score").upsert(rows[i : i + BATCH], on_conflict="date").execute()
        print(f"[Supabase] daily_score {len(rows)}건 저장 (기존 행도 지금 공식으로 재계산)")
    elif do_daily:
        print("\n[미리보기] --apply 를 함께 붙여야 daily_score 를 저장합니다.")
    else:
        print("\n[안내] daily_score 까지 다시 쓰려면 --daily-score 를 붙이세요.")

    _ = HOT_ZONE  # calculate_score 와 같은 상수를 쓰고 있음을 표시


if __name__ == "__main__":
    main()
