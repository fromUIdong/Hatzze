"""'평소 대비 몇 배'를 카드에 보여주기 위한 공통 details 헬퍼.

네이버 데이터랩 검색지수처럼 절대 검색 건수가 없는 0~100 상대지수는 'N pt'로
보여줘봐야 와닿지 않는다. 대신 각 날짜의 값을 '최근 한 달(직전 WINDOW 거래일)
평균' 대비 배수로 바꿔 details에 채워두면, 카드가 '평소 대비 1.3배'처럼
직관적으로 보여줄 수 있다. fetch_kospi_volume.py의 30일 평균 details와 같은
패턴이다.

raw_value는 그대로 둔 채 details만 갱신 upsert한다. normalized_score는 payload에
넣지 않아 그대로 보존된다.
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
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start)
        .execute()
    )
    values = {row["date"]: float(row["raw_value"]) for row in result.data}
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
                "details": {
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
        .select("date,raw_value")
        .eq("indicator_id", indicator_id)
        .gte("date", start)
        .execute()
    )
    values = {row["date"]: float(row["raw_value"]) for row in result.data}
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
                "details": {"scale": round(scale, 2)},
            }
        )

    if rows:
        client.table("indicator_values").upsert(
            rows, on_conflict="indicator_id,date"
        ).execute()
    return len(rows)
