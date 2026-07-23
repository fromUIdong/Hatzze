"""'평소 대비 몇 배'를 카드에 보여주기 위한 공통 details 헬퍼.

네이버 데이터랩 검색지수처럼 절대 검색 건수가 없는 0~100 상대지수는 'N pt'로
보여줘봐야 와닿지 않는다. 대신 각 날짜의 값을 '최근 한 달(직전 WINDOW 거래일)
평균' 대비 배수로 바꿔 details에 채워두면, 카드가 '평소 대비 1.3배'처럼
직관적으로 보여줄 수 있다. fetch_kospi_volume.py의 30일 평균 details와 같은
패턴이다.

raw_value는 그대로 둔 채 details만 갱신 upsert한다. normalized_score는 payload에
넣지 않아 그대로 보존된다.

**details는 반드시 병합해서 쓴다(덮어쓰지 않는다).** 이 컬럼은 fetch 스크립트만
쓰는 게 아니다 — calculate_score.py도 같은 행의 details에 자기 키를 남긴다(실물–증시
괴리의 real_stress/market_strength/divergence). 예전엔 여기서 dict를 통째로 새로
만들어 넣어서, fetch가 돌 때마다 calculate_score가 쓴 키가 날아갔다. 평소엔
워크플로우 순서(fetch… → calculate_score)가 마지막에 복원해줘서 안 보였지만,
그 사이에서 실행이 끊기면(2026-07-20 17:09 취소된 실행) 복원이 안 돼 카드의 두 축이
0으로 표시됐다. 순서에 기대지 않도록 기존 키를 보존하고 자기 키만 갱신한다.
"""

from __future__ import annotations

from datetime import date, timedelta

DEFAULT_WINDOW = 30  # '평소'로 삼는 직전 거래일 수(약 한 달)
DEFAULT_BACKFILL_DAYS = 365


def store_vs_average_details(
    client,
    indicator_id: str,
    window: int = DEFAULT_WINDOW,
    backfill_days: int = DEFAULT_BACKFILL_DAYS,
) -> int:
    """각 날짜의 직전 window 거래일 평균과 그 대비 배수(vs_avg)를 details에 저장한다.

    저장 형태: details = {"avg_index": <평균>, "vs_avg": <현재/평균>}.
    반환값은 갱신한 행 수.
    """
    start = (date.today() - timedelta(days=backfill_days)).isoformat()
    result = (
        client.table("indicator_values")
        .select("date,raw_value,details")
        .eq("indicator_id", indicator_id)
        .gte("date", start)
        .execute()
    )
    values = {row["date"]: float(row["raw_value"]) for row in result.data}
    existing = {row["date"]: (row.get("details") or {}) for row in result.data}
    dates_sorted = sorted(values)

    rows = []
    for i in range(window, len(dates_sorted)):
        window_values = [values[dates_sorted[j]] for j in range(i - window, i)]
        avg = sum(window_values) / window
        if avg <= 0:
            continue  # 평균이 0이면 배수를 낼 수 없어 건너뜀
        d = dates_sorted[i]
        rows.append(
            {
                "indicator_id": indicator_id,
                "date": d,
                "raw_value": values[d],
                # 남이 쓴 키(calculate_score의 괴리 3종 등)를 보존하고 내 키만 갱신한다.
                "details": {
                    **existing.get(d, {}),
                    "avg_index": round(avg, 1),
                    "vs_avg": round(values[d] / avg, 2),
                },
            }
        )

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    return len(rows)


def sentiment_details(result: dict) -> dict:
    """감성 분류 결과에서 카드가 '낙관:비관'을 그릴 수 있는 키만 뽑는다.

    raw_value(순감성 = (긍정-부정)/전체×100)만으로는 낙관:비관 비율을 되돌릴 수
    없다 — 중립이 몇 건이었는지가 사라지기 때문이다. 그래서 건수를 그대로 남긴다.
    디시·뉴스 두 스크립트가 같은 키 이름을 써야 카드가 하나의 코드로 둘 다 그린다.
    """
    return {
        "pos_count": result["positive"],
        "neg_count": result["negative"],
        "neu_count": result["neutral"],
        "total_count": result["total"],
    }


def merge_details(client, indicator_id: str, day: str, new_keys: dict) -> dict:
    """그 날짜의 기존 details에 new_keys만 얹은 dict를 돌려준다(저장은 호출자가).

    details는 여러 writer가 공유하는 칸이라 통째로 대입하면 남의 키가 날아간다
    (모듈 docstring 참고). 여기서 기존 값을 먼저 읽어 병합해 준다.

    **새 details 키를 쓸 땐 이 함수(또는 upsert_details)를 거칠 것.** 지금은 통째로
    대입해도 충돌이 안 나는 지표가 대부분이지만, 그건 우연히 writer가 하나뿐이기
    때문이지 안전해서가 아니다.
    """
    existing = (
        client.table("indicator_values")
        .select("details")
        .eq("indicator_id", indicator_id)
        .eq("date", day)
        .execute()
    )
    current = (existing.data[0].get("details") or {}) if existing.data else {}
    return {**current, **new_keys}


def upsert_details(client, indicator_id: str, rows: list[dict]) -> int:
    """날짜별 details를 **기존 키를 보존하며** 한 번에 upsert한다.

    rows 형태: [{"date": "YYYY-MM-DD", "raw_value": <필수>, "details": {...내 키만...}}]

    통째 대입을 막는 기본 경로다. fetch 스크립트들이 각자 dict를 새로 만들어 넣는 바람에
    2026-07-20 실물–증시 괴리 카드의 두 축이 0으로 표시된 적이 있다(calculate_score가
    같은 행에 쓴 키가 날아갔다). 그때는 3개 함수만 병합형으로 고쳤는데, 남은 스크립트도
    새 키를 추가할 땐 이걸 쓰면 같은 실수를 반복하지 않는다.

    반환: 저장한 행 수.
    """
    if not rows:
        return 0

    dates = [r["date"] for r in rows]
    existing = (
        client.table("indicator_values")
        .select("date,details")
        .eq("indicator_id", indicator_id)
        .in_("date", dates)
        .execute()
    )
    prior = {r["date"]: (r.get("details") or {}) for r in existing.data}

    payload = [
        {
            "indicator_id": indicator_id,
            "date": r["date"],
            "raw_value": r["raw_value"],
            "details": {**prior.get(r["date"], {}), **(r.get("details") or {})},
        }
        for r in rows
    ]
    client.table("indicator_values").upsert(
        payload, on_conflict="indicator_id,date"
    ).execute()
    return len(payload)


DEFAULT_SCALE_WINDOW = 60
DEFAULT_SCALE_FLOOR = 1.0
DEFAULT_SCALE_MIN_POINTS = 3


def store_abs_scale_details(
    client,
    indicator_id: str,
    window: int = DEFAULT_SCALE_WINDOW,
    backfill_days: int = DEFAULT_BACKFILL_DAYS,
    floor: float = DEFAULT_SCALE_FLOOR,
    min_points: int = DEFAULT_SCALE_MIN_POINTS,
) -> int:
    """각 날짜 기준 최근 window일 내 |값|의 최댓값(scale)을 details에 저장한다.

    감성 게이지(비관↔낙관)를 '절대 ±100'이 아니라 '자기 최근 범위 대비'로 배치할
    때 쓰는 기준값이다. 지표마다 값의 크기가 크게 달라(예: 디시 ±1, 뉴스 ±30)
    같은 축으로는 한쪽이 늘 정중앙처럼 보이는데, 각자 최근 |최대|로 나누면 둘 다
    적당히 움직인다. 데이터가 적으면 있는 만큼으로 계산하고, floor 미만으로는 안
    내려가게 해 0 근처 잡음이 과증폭되는 걸 막는다.
    """
    start = (date.today() - timedelta(days=backfill_days)).isoformat()
    result = (
        client.table("indicator_values")
        .select("date,raw_value,details")
        .eq("indicator_id", indicator_id)
        .gte("date", start)
        .execute()
    )
    values = {row["date"]: float(row["raw_value"]) for row in result.data}
    existing = {row["date"]: (row.get("details") or {}) for row in result.data}
    dates_sorted = sorted(values)

    rows = []
    for i in range(len(dates_sorted)):
        lo = max(0, i - window + 1)
        window_abs = [abs(values[dates_sorted[j]]) for j in range(lo, i + 1)]
        if len(window_abs) < min_points:
            continue
        scale = max(max(window_abs), floor)
        d = dates_sorted[i]
        rows.append(
            {
                "indicator_id": indicator_id,
                "date": d,
                "raw_value": values[d],
                # store_vs_average_details 와 같은 이유로 병합한다(모듈 docstring 참고).
                "details": {**existing.get(d, {}), "scale": round(scale, 2)},
            }
        )

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    return len(rows)
