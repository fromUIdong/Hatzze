"""telegram_message_stocks × telegram_messages 를 종목·날짜(KST)로 집계해
telegram_stock_daily 에 저장한다. 급부상 종목·종목 리포트·테마의 토대.

각 (날짜, 종목)마다: 언급 메시지 수, 서로 다른 채널 수, 조회/포워드 합,
그리고 weighted_score = 언급 메시지들의 트렌딩 점수 합
(views×0.5 + forwards×3.0 + replies×1.5)을 계산한다.

extract 가 message_stocks 를 전량 재생성하므로 여기도 매 실행 전량 재계산해 맞춘다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/calculate_stock_daily.py --dry-run   # 계산·미리보기만
    python scripts/calculate_stock_daily.py             # 저장
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.timeutil import KST  # noqa: E402
from common.supabase_client import load_all  # noqa: E402

# 트렌딩 점수 가중치(트렌딩 메시지 공식과 동일).
W_VIEWS, W_FWD, W_REPLIES = 0.5, 3.0, 1.5


def trending_score(m: dict) -> float:
    return (
        (m["views"] or 0) * W_VIEWS
        + (m["forwards"] or 0) * W_FWD
        + (m["replies"] or 0) * W_REPLIES
    )


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    db = get_client()

    messages = {
        (m["channel_handle"], m["message_id"]): m
        for m in load_all(
            db, "telegram_messages", "channel_handle,message_id,posted_at,views,forwards,replies"
        )
    }
    mentions = load_all(
        db, "telegram_message_stocks", "channel_handle,message_id,stock_code"
    )

    # (date, code) -> 집계 누적
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"mentions": 0, "channels": set(), "views": 0, "fwd": 0, "weighted": 0.0}
    )
    for men in mentions:
        msg = messages.get((men["channel_handle"], men["message_id"]))
        if not msg or not msg["posted_at"]:
            continue
        date = datetime.fromisoformat(msg["posted_at"]).astimezone(KST).date().isoformat()
        a = agg[(date, men["stock_code"])]
        a["mentions"] += 1
        a["channels"].add(men["channel_handle"])
        a["views"] += msg["views"] or 0
        a["fwd"] += msg["forwards"] or 0
        a["weighted"] += trending_score(msg)

    rows = [
        {
            "date": date,
            "stock_code": code,
            "mention_count": a["mentions"],
            "channel_count": len(a["channels"]),
            "sum_views": a["views"],
            "sum_forwards": a["fwd"],
            "weighted_score": round(a["weighted"], 1),
        }
        for (date, code), a in agg.items()
    ]
    print(f"집계 {len(rows)}행 ((날짜×종목), 메시지 {len(messages)}·언급 {len(mentions)})")

    # 급부상 미리보기: 최신일 vs 그 이전 일평균(baseline) 대비 weighted_score 급증
    code_to_name = {
        s["code"]: s["name"] for s in load_all(db, "stocks", "code,name")
    }
    dates = sorted({r["date"] for r in rows})
    if len(dates) >= 2:
        latest = dates[-1]
        prior = dates[:-1]
        latest_w = {r["stock_code"]: r["weighted_score"] for r in rows if r["date"] == latest}
        base_w: dict[str, float] = defaultdict(float)
        for r in rows:
            if r["date"] in prior:
                base_w[r["stock_code"]] += r["weighted_score"]
        surge = []
        for code, w in latest_w.items():
            base = base_w.get(code, 0.0) / len(prior)
            ratio = (w / base) if base > 0 else float("inf")
            surge.append((ratio, w, base, code))
        surge.sort(key=lambda x: (x[1]), reverse=True)  # 최신 주목도 큰 순
        print(f"\n=== 최신일({latest}) 주목 종목 TOP 10 (weighted / 이전 {len(prior)}일 평균) ===")
        for ratio, w, base, code in surge[:10]:
            tag = "🆕신규" if base == 0 else (f"×{ratio:.1f}" if ratio >= 1.5 else "")
            print(f"  {code_to_name.get(code, code):<16} 오늘 {w:>9,.0f} · 평소 {base:>8,.0f} {tag}")

    if dry_run:
        print("\n--dry-run: DB에 저장하지 않았습니다.")
        return

    db.table("telegram_stock_daily").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    for i in range(0, len(rows), 500):
        db.table("telegram_stock_daily").insert(rows[i : i + 500]).execute()
    print(f"\n[Supabase] telegram_stock_daily {len(rows)}행 저장 완료")


if __name__ == "__main__":
    main()
