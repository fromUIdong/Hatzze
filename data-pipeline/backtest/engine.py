"""과열도 지표 전수 백테스트 엔진.

- calculate_score.compute_progress 를 그대로 재현해 지표별 progress 시계열을 만든다
- 히스토리가 없는 kospi_high_gap / buffett_index / small_business(괴리) 는 원본
  시계열(kospi_close_raw, CCSI)에서 재구성한다
- KOSPI 종가 시계열과 붙여 동행성/선행성/눈금 진단을 낸다
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.indicator_thresholds import (  # noqa: E402
    INDICATOR_THRESHOLDS,
    NEGATIVE_CURRENT_CLAMP_SLUGS,
)
from config.indicator_weights import INDICATOR_WEIGHTS  # noqa: E402
from scripts.calculate_score import (  # noqa: E402
    CCSI_PCTILE_ANCHORS,
    KOSPI_DD_PCTILE_ANCHORS,
    compute_progress,
    percentile_from_anchors,
)

SCRATCH = Path(__file__).parent  # 덤프 JSON이 놓이는 곳
HOT_ZONE = 75.0

# ---------------------------------------------------------------- 데이터 로드
raw = json.load(open(SCRATCH / "values.json"))
series: dict[str, pd.DataFrame] = {}
_by = defaultdict(list)
for r in raw:
    _by[r["slug"]].append(r)

for slug, rows in _by.items():
    rows.sort(key=lambda r: r["date"])
    df = pd.DataFrame(
        {
            "date": [r["date"] for r in rows],
            "raw": [float(r["raw_value"]) for r in rows],
            "details": [r.get("details") or {} for r in rows],
        }
    ).drop_duplicates("date", keep="last")
    df["date"] = pd.to_datetime(df["date"])
    series[slug] = df.set_index("date")

kospi = series["kospi_close_raw"]["raw"].rename("kospi")
IDX = kospi.index  # 거래일 축


# ------------------------------------------------- 재구성: kospi_high_gap
def rebuild_high_gap() -> pd.Series:
    """fetch_kospi_high_gap.compute_gap 재현: 오늘 제외 직전 365일 최고가 대비 %."""
    out = {}
    for d in IDX:
        w = kospi[(kospi.index >= d - timedelta(days=365)) & (kospi.index < d)]
        if len(w) < 20:  # 창이 너무 짧으면 신뢰 불가
            continue
        prior_high = w.max()
        out[d] = (kospi[d] - prior_high) / prior_high * 100
    return pd.Series(out).rename("kospi_high_gap")


HIGH_GAP = rebuild_high_gap()


# ------------------------------------------------- 재구성: buffett_index
def rebuild_buffett() -> pd.Series:
    """시총/GDP. 시총 히스토리가 15일뿐이라 코스피 지수에 비례한다고 보고 역산한다.

    겹치는 15일에서 buffett/kospi 비율의 중앙값을 상수로 잡는다(GDP는 분기라 느림).
    """
    b = series["buffett_index"]["raw"]
    common = b.index.intersection(kospi.index)
    ratio = float((b[common] / kospi[common]).median())
    return (kospi * ratio).rename("buffett_index")


BUFFETT = rebuild_buffett()


# ------------------------------------------------- 재구성: 실물–증시 괴리(lead)
def rebuild_divergence() -> pd.Series:
    ccsi = series["consumer_sentiment_index"]["raw"]
    ccsi = ccsi.reindex(ccsi.index.union(IDX)).ffill().reindex(IDX)
    out = {}
    for d in IDX:
        if d not in HIGH_GAP.index or pd.isna(ccsi[d]):
            continue
        real = percentile_from_anchors(float(ccsi[d]), CCSI_PCTILE_ANCHORS)
        mkt = percentile_from_anchors(float(HIGH_GAP[d]), KOSPI_DD_PCTILE_ANCHORS)
        out[d] = max(0.0, mkt - real)
    return pd.Series(out).rename("small_business_crisis_index")


DIVERGENCE = rebuild_divergence()


# ------------------------------------------------- progress 시계열 계산
def progress_series(slug: str) -> pd.Series | None:
    cfg = INDICATOR_THRESHOLDS[slug]

    if slug == "kospi_high_gap":
        vals = HIGH_GAP
    elif slug == "buffett_index":
        vals = BUFFETT
    elif slug == "small_business_crisis_index":
        return DIVERGENCE.clip(0, 100)
    else:
        if slug not in series:
            return None
        vals = series[slug]["raw"]

    det = series.get(slug)
    out = {}

    # relative_surge(거래대금): details.surge_pct 사용
    rs = cfg.get("relative_surge")
    if rs is not None and det is not None:
        for d, row in det.iterrows():
            s = (row["details"] or {}).get("surge_pct")
            if s is None:
                continue
            out[d] = (float(s) - rs["floor"]) / (rs["ceil"] - rs["floor"]) * 100
        return pd.Series(out)

    if cfg["kind"] == "cumulative_average":
        # PIT: 오늘 포함 지금까지의 평균이 그날의 기준선
        run = vals.expanding().mean()
        for d in vals.index:
            out[d] = compute_progress(slug, float(vals[d]), float(run[d]), cfg)
        return pd.Series(out)

    thr = cfg["threshold"]
    for d in vals.index:
        out[d] = compute_progress(slug, float(vals[d]), thr, cfg)
    return pd.Series(out)


PROG = {}
for slug in INDICATOR_THRESHOLDS:
    s = progress_series(slug)
    if s is not None and len(s):
        PROG[slug] = s.sort_index()

CAPPED = {k: v.clip(0, 100) for k, v in PROG.items()}


# ------------------------------------------------- 시장 기준선(정답지)
kdf = pd.DataFrame({"kospi": kospi})
for h in (5, 20, 60):
    kdf[f"fwd{h}"] = kospi.shift(-h) / kospi - 1
    kdf[f"bwd{h}"] = kospi / kospi.shift(h) - 1
kdf["gap"] = HIGH_GAP  # 전고점 대비 %(동행 열기 프록시)
# 향후 60일 최대 낙폭(고점 판별용)
fwd_min = pd.Series(
    {d: kospi[(kospi.index > d) & (kospi.index <= d + timedelta(days=90))].min() for d in IDX}
)
kdf["fwd_dd"] = fwd_min / kospi - 1


def pearson(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    j = pd.concat([a, b], axis=1).dropna()
    if len(j) < 20:
        return float("nan"), len(j)
    x, y = j.iloc[:, 0].to_numpy(), j.iloc[:, 1].to_numpy()
    if x.std() == 0 or y.std() == 0:
        return float("nan"), len(j)
    return float(np.corrcoef(x, y)[0, 1]), len(j)


def spearman(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    j = pd.concat([a, b], axis=1).dropna()
    if len(j) < 20:
        return float("nan"), len(j)
    x = j.iloc[:, 0].rank().to_numpy()
    y = j.iloc[:, 1].rank().to_numpy()
    if x.std() == 0 or y.std() == 0:
        return float("nan"), len(j)
    return float(np.corrcoef(x, y)[0, 1]), len(j)


if __name__ == "__main__":
    print(f"KOSPI {kospi.index.min().date()} ~ {kospi.index.max().date()} n={len(kospi)}")
    print(f"지표 progress 시계열 생성: {len(PROG)}개")
    for slug in INDICATOR_THRESHOLDS:
        s = CAPPED.get(slug)
        n = 0 if s is None else len(s)
        print(f"  {slug:34} n={n:4} w={INDICATOR_WEIGHTS.get(slug)}")
