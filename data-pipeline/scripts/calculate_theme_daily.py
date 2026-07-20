"""종목 일별 집계를 테마로 묶어 telegram_theme_daily 에 저장한다 (테마 로테이션).

config/stock_themes.py 의 테마 사전으로 telegram_stock_daily 를 그룹핑한다.
한 종목이 여러 테마에 속하면 각 테마에 모두 반영된다(예: POSCO홀딩스는 2차전지).

share_pct 는 그날 '전체 종목' 주목도 합 대비 비중이다 — 주말엔 절대 언급량이
평일의 1/10로 떨어져 절대량으로는 테마 간 비교도, 날짜 간 비교도 안 되기 때문
(급부상 종목 계산과 같은 이유). rank 는 그날 share_pct 순위로, 주간 순위 변동은
프론트에서 날짜 간 rank 를 비교해 구한다.

extract/stock_daily 가 전량 재계산하므로 여기도 매 실행 전량 재계산해 맞춘다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/calculate_theme_daily.py --dry-run   # 계산·미리보기만
    python scripts/calculate_theme_daily.py             # 저장
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from config.stock_themes import THEMES  # noqa: E402


def load_all(db, table: str, columns: str) -> list[dict]:
    rows, start = [], 0
    while True:
        page = db.table(table).select(columns).range(start, start + 999).execute().data
        if not page:
            break
        rows += page
        start += 1000
    return rows


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    db = get_client()

    # 테마 사전의 종목명을 코드로 해석한다. stocks 에 없는 이름은 건너뛰되 무엇이
    # 빠졌는지 알린다. 코스닥 적재(2026-07-20) 이후 남는 미해결은 사전 오타이거나
    # KRX 정식명 불일치(예: 엔씨소프트 → "NC")이니 사전을 고쳐야 한다.
    stocks = load_all(db, "stocks", "code,name")
    code_of = {s["name"]: s["code"] for s in stocks}
    theme_of: dict[str, list[str]] = defaultdict(list)  # code -> [theme]
    missing: dict[str, list[str]] = {}
    for theme, names in THEMES.items():
        unresolved = []
        for name in names:
            code = code_of.get(name)
            if code:
                theme_of[code].append(theme)
            else:
                unresolved.append(name)
        if unresolved:
            missing[theme] = unresolved
    if missing:
        total = sum(len(v) for v in missing.values())
        print(f"[경고] stocks 에 없어 건너뛴 종목 {total}개 — 사전의 이름을 KRX 정식명과 맞추세요:")
        for t, v in missing.items():
            print(f"  {t}: {', '.join(v)}")

    daily = load_all(db, "telegram_stock_daily", "date,stock_code,weighted_score,mention_count")
    if not daily:
        print("[경고] telegram_stock_daily 가 비어 있습니다. 먼저 calculate_stock_daily.py 를 실행하세요.")
        return

    # 그날 전체 주목도(테마 무관) — share_pct 의 분모.
    day_total: dict[str, float] = defaultdict(float)
    for r in daily:
        day_total[r["date"]] += float(r["weighted_score"] or 0)

    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"w": 0.0, "m": 0, "codes": set()}
    )
    for r in daily:
        for theme in theme_of.get(r["stock_code"], ()):
            a = agg[(r["date"], theme)]
            a["w"] += float(r["weighted_score"] or 0)
            a["m"] += r["mention_count"] or 0
            a["codes"].add(r["stock_code"])

    rows = []
    for (date, theme), a in agg.items():
        total = day_total.get(date, 0.0)
        rows.append(
            {
                "date": date,
                "theme": theme,
                "mention_count": a["m"],
                "weighted_score": round(a["w"], 1),
                "share_pct": round(a["w"] / total * 100, 2) if total else 0,
                "stock_count": len(a["codes"]),
            }
        )

    # 날짜별 share_pct 순위 부여.
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    for date_rows in by_date.values():
        date_rows.sort(key=lambda r: r["share_pct"], reverse=True)
        for i, r in enumerate(date_rows, 1):
            r["rank"] = i

    print(f"\n집계 {len(rows)}행 ((날짜×테마), 테마 {len(THEMES)}개 · 날짜 {len(by_date)}일)")
    latest = max(by_date)
    print(f"\n=== 최신일({latest}) 테마 순위 ===")
    print(f"{'#':>2} {'테마':<14}{'점유율':>8}{'언급':>7}{'종목':>6}")
    for r in sorted(by_date[latest], key=lambda r: r["rank"])[:10]:
        print(f"{r['rank']:>2} {r['theme']:<14}{r['share_pct']:>7.1f}%{r['mention_count']:>7}{r['stock_count']:>6}")

    if dry_run:
        print("\n--dry-run: DB에 저장하지 않았습니다.")
        return

    db.table("telegram_theme_daily").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    for i in range(0, len(rows), 500):
        db.table("telegram_theme_daily").insert(rows[i : i + 500]).execute()
    print(f"\n[Supabase] telegram_theme_daily {len(rows)}행 저장 완료")


if __name__ == "__main__":
    main()
