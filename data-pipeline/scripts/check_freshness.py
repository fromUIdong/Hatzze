"""지표별 자료 신선도를 검사하고, 허용치를 넘긴 게 있으면 실패로 끝낸다.

**왜 필요한가.** 파이프라인의 실패는 워크플로가 잡아주지만, 잡지 못하는 게 하나
있다 — "성공했는데 새 데이터가 없는" 경우다. KRX가 최근 영업일치를 아직 안 냈거나
접속이 막히면 fetch 스크립트는 "휴장일 등 N건 제외"만 찍고 **정상 종료**한다. 그러면
워크플로는 초록불인데 화면은 며칠 전 값을 오늘 값처럼 보여준다. 실제로 2026-07-22
오후 실행에서 KRX가 403을 내 8개 지표가 통째로 안 들어왔는데 아무 표시가 없었다.

**무엇을 재는가.** 행이 꽂힌 날짜가 아니라 **자료의 날짜**를 본다. 둘은 다르다 —
예를 들어 코스피 신고가는 KRX가 멈춰도 매일 '오늘' 행을 쓴다(며칠 전 종가로 계산해서).
그래서 행 날짜만 보면 영원히 최신이다. 그런 지표는 details.source_date 에 실제 자료
기준일을 남기므로 그걸 우선한다.

내부용 원본(kospi_close_raw 등)도 같이 본다. 파생 지표는 매일 행을 쓰기 때문에,
KRX가 멈춘 걸 가장 먼저 드러내는 건 원본 쪽이다.

**허용치.** 영업일 기준이다. 대부분의 국내 지표는 전일 종가를 받으므로 1영업일
지연이 정상이고, 여기에 하루 여유를 둬 기본 2로 잡는다. 공표 주기가 다른 것만
따로 적어 둔다(아래 ALLOWANCE). 오탐을 허용치로 흡수하고 진짜 멈춤만 잡는 게 목적이라,
애매하면 넉넉한 쪽으로 둔다.

실행:
    cd data-pipeline && python scripts/check_freshness.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.timeutil import business_days, today_kst  # noqa: E402
from config.indicator_weights import INDICATOR_WEIGHTS  # noqa: E402

DEFAULT_ALLOWANCE = 2  # 영업일. 국내 지표는 전일치가 정상이라 1 + 여유 1.

# 공표 주기가 달라 기본값으로는 오탐이 나는 것만 적는다.
ALLOWANCE = {
    # 고객예탁금은 금투협이 D+1에 공표하는데 아침 실행(10~11시 KST)이 그보다 이르다.
    # 저녁 실행이 받아 가므로 하루 더 준다.
    "investor_deposit": 3,
    # 버핏지수는 KRX 시총 + ECOS GDP 조합이라, ECOS가 막히면 그날을 통째로 건너뛴다.
    "buffett_index": 3,
    # CCSI는 한국은행이 월 1회 공표한다. 두 달 넘게 안 들어오면 그때 알린다.
    "consumer_sentiment_index": 45,
    # 알라딘 베스트셀러는 주 단위로 갱신돼 같은 값이 며칠 이어진다.
    "bestseller_finance_ratio": 5,
}

# 점수에 안 들어가지만 상태를 봐야 하는 내부용 원본. 파생 지표가 매일 행을 쓰는 탓에
# KRX 정체가 여기서 가장 먼저 보인다.
INTERNAL_SLUGS = [
    "kospi_close_raw",
    "kosdaq_close_raw",
    "kospi_market_cap_raw",
    "leverage_etf_trade_value_raw",
    "kospi200_futures_oi_raw",
    "consumer_sentiment_index",
]


def business_day_lag(data_date: str, today: date) -> int:
    """자료 기준일부터 오늘까지 지난 영업일 수. 오늘치면 0, 어제(평일)치면 1."""
    d = date.fromisoformat(data_date)
    if d >= today:
        return 0
    return sum(1 for x in business_days(d, today) if x > d)


def latest_data_date(client, indicator_id: str) -> str | None:
    """가장 최근 행의 '자료 날짜'.

    details.source_date 가 있으면 그걸 쓴다 — 행 날짜는 '계산한 날'이라 원본이 멈춰도
    매일 갱신되기 때문이다(코스피 신고가·버핏지수가 그렇다).
    """
    res = (
        client.table("indicator_values")
        .select("date,details")
        .eq("indicator_id", indicator_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    src = (row.get("details") or {}).get("source_date")
    if src:
        s = str(int(src))
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return row["date"]


def main() -> None:
    client = get_client()
    today = today_kst()

    meta = {
        r["slug"]: (r["id"], r["name"])
        for r in client.table("indicators").select("id,slug,name").execute().data
    }

    checks: list[tuple[str, float | None]] = [(s, w) for s, w in INDICATOR_WEIGHTS.items()]
    checks += [(s, None) for s in INTERNAL_SLUGS if s not in INDICATOR_WEIGHTS]

    rows = []
    for slug, weight in checks:
        if slug not in meta:
            print(f"[WARNING] '{slug}' 지표 행이 없습니다 — 건너뜁니다")
            continue
        indicator_id, name = meta[slug]
        data_date = latest_data_date(client, indicator_id)
        allowance = ALLOWANCE.get(slug, DEFAULT_ALLOWANCE)
        lag = business_day_lag(data_date, today) if data_date else 9999
        rows.append(
            {
                "slug": slug,
                "name": name,
                "weight": weight,
                "date": data_date or "없음",
                "lag": lag,
                "allowance": allowance,
                "stale": lag > allowance,
            }
        )

    rows.sort(key=lambda r: (-(r["lag"] - r["allowance"]), -(r["weight"] or 0)))

    print(f"[신선도] 기준 오늘(KST) = {today}")
    print(f"{'지연':>4} {'허용':>4}  {'자료일':11} {'가중':>5}  지표")
    print("-" * 72)
    for r in rows:
        mark = "  ← 초과" if r["stale"] else ""
        w = f"{r['weight']:.1f}" if r["weight"] is not None else "내부"
        print(f"{r['lag']:>4} {r['allowance']:>4}  {r['date']:11} {w:>5}  {r['name'][:28]}{mark}")

    stale = [r for r in rows if r["stale"]]
    if not stale:
        print(f"\n[신선도] 이상 없음 — {len(rows)}개 지표 모두 허용 범위 안입니다.")
        return

    weighted = sum(r["weight"] for r in stale if r["weight"])
    print(
        f"\n[신선도] 허용치를 넘긴 지표 {len(stale)}개"
        + (f" · 점수 가중치 {weighted:.1f}/{sum(INDICATOR_WEIGHTS.values()):.1f}" if weighted else "")
    )
    for r in stale:
        print(f"  - {r['name']}: 자료 {r['date']} ({r['lag']}영업일 전, 허용 {r['allowance']})")
    print(
        "\n해당 지표의 fetch 스텝 로그를 확인하세요. 스텝이 'success'인데 여기서 걸렸다면 "
        "소스가 데이터를 안 준 것이지 코드가 죽은 게 아닙니다."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
