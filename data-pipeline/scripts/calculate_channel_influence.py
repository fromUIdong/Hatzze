"""채널 영향력 점수(Influence Score)를 노션 계산법대로 매일 계산해 저장한다.

각 활성 채널마다 4개 지표를 구간 점수로 환산한 뒤 합산·보정한다:
  - 뷰레이트(%)  = 최근 ~30개 게시물 평균 조회수 / 구독자수 × 100  (최대 35)
  - 포워드율(%) = 최근 ~30개 게시물 포워드 합 / 조회수 합 × 100     (최대 30)
  - 구독자 규모 티어                                              (최대 20)
  - 활동성       = 최근 7일 게시물 수                              (최대 15)
  Raw = 네 점수 합(최대 100)
  Influence Score = 48 + (Raw/100)×52                     (일반, 뷰레이트 ≥ 3%)
                  = min((48 + (Raw/100)×52)×0.85, 70)     (성장중, 뷰레이트 < 3%)

결과를 telegram_channel_stats 의 오늘(KST) 행에 upsert한다(7D 변동 비교용 일별 저장).
데이터는 Telethon 수집분(telegram_messages) + telegram_channels.subscriber_count 를
쓰므로, fetch_telegram.py 다음에 실행한다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/calculate_channel_influence.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.timeutil import today_kst  # noqa: E402

RECENT_POSTS = 30  # 평균 조회수/포워드율 계산에 쓰는 최근 게시물 수
GROWING_VIEW_RATE = 3.0  # 이 뷰레이트(%) 미만이면 "성장 중" 등급
GROWING_PENALTY = 0.85
GROWING_CAP = 70.0

# (하한 임계값, 점수) 내림차순 — 값이 임계값 이상인 첫 구간의 점수를 쓴다.
VIEW_RATE_TIERS = [(30, 35), (20, 30), (15, 25), (10, 20), (5, 14), (3, 8), (0, 3)]
FWD_RATE_TIERS = [(10, 30), (5, 25), (2, 20), (1, 14), (0.5, 8), (0, 3)]
SUB_TIERS = [(50000, 20), (20000, 16), (10000, 12), (5000, 8), (1000, 5), (200, 2), (0, 0)]
ACTIVITY_TIERS = [(20, 15), (10, 12), (5, 8), (2, 4), (0, 1)]


def tier_score(value: float, tiers: list[tuple[float, int]]) -> int:
    for threshold, score in tiers:
        if value >= threshold:
            return score
    return tiers[-1][1]


def main() -> None:
    db = get_client()
    channels = (
        db.table("telegram_channels")
        .select("handle,subscriber_count")
        .eq("is_active", True)
        .execute()
        .data
    )
    if not channels:
        print("[경고] 활성 채널이 없습니다.")
        return

    today = today_kst().isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = []

    for ch in channels:
        handle = ch["handle"]
        sub = ch["subscriber_count"] or 0

        recent = (
            db.table("telegram_messages")
            .select("views,forwards")
            .eq("channel_handle", handle)
            .order("posted_at", desc=True)
            .limit(RECENT_POSTS)
            .execute()
            .data
        )
        weekly_posts = (
            db.table("telegram_messages")
            .select("id", count="exact")
            .eq("channel_handle", handle)
            .gte("posted_at", week_ago)
            .limit(1)
            .execute()
            .count
        ) or 0

        views = [m["views"] for m in recent if m["views"] is not None]
        avg_views = sum(views) / len(views) if views else 0.0
        view_rate = (avg_views / sub * 100) if sub else 0.0
        sum_views = sum(m["views"] or 0 for m in recent)
        sum_fwd = sum(m["forwards"] or 0 for m in recent)
        fwd_rate = (sum_fwd / sum_views * 100) if sum_views else 0.0

        raw = (
            tier_score(view_rate, VIEW_RATE_TIERS)
            + tier_score(fwd_rate, FWD_RATE_TIERS)
            + tier_score(sub, SUB_TIERS)
            + tier_score(weekly_posts, ACTIVITY_TIERS)
        )
        base = 48 + (raw / 100) * 52
        is_growing = view_rate < GROWING_VIEW_RATE
        influence = min(base * GROWING_PENALTY, GROWING_CAP) if is_growing else base

        rows.append(
            {
                "channel_handle": handle,
                "date": today,
                "subscriber_count": sub,
                "avg_views": round(avg_views, 1),
                "view_rate": round(view_rate, 2),
                "fwd_rate": round(fwd_rate, 3),
                "weekly_posts": weekly_posts,
                "influence_score": round(influence, 1),
                "is_growing": is_growing,
            }
        )

    db.table("telegram_channel_stats").upsert(
        rows, on_conflict="channel_handle,date"
    ).execute()

    rows.sort(key=lambda r: r["influence_score"], reverse=True)
    print(f"=== Influence Score {today} (저장 완료, {len(rows)}건) ===")
    print(f"{'#':>2} {'채널':<16}{'구독':>9}{'뷰레이트':>8}{'Score':>7}  등급")
    for i, r in enumerate(rows, 1):
        grade = "성장중" if r["is_growing"] else "일반"
        print(
            f"{i:>2} {r['channel_handle']:<16}{r['subscriber_count']:>9,}"
            f"{r['view_rate']:>7.1f}%{r['influence_score']:>7.1f}  {grade}"
        )


if __name__ == "__main__":
    main()
