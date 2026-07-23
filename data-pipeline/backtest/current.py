"""**지금 배포될 설정 그대로** 돌리는 최종 백테스트.

앞선 스크립트들(plan4/improve4/absolute…)은 후보를 비교하려고 눈금을 코드 안에 박아 뒀다.
이 스크립트는 그러지 않는다 — config/indicator_thresholds.py·indicator_weights.py 와
scripts/calculate_score.py 의 상수(SCORE_DISPLAY_ANCHORS, LEAD_FLOOR/CEIL, level_weight)를
**그대로 import** 해서, 설정을 고치고 다시 돌리면 그 설정의 성적이 나온다.

한계 하나: 단기 9개(가중치 15.0/46.5 = 32%)는 히스토리가 7~24일뿐이라 과거 시계열을 만들 수
없다. 각 지표의 관측 평균을 상수로 놓아 위치만 반영한다(분산 기여 0 = 보수적).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/hun/hatzze/data-pipeline")
from config.indicator_thresholds import INDICATOR_THRESHOLDS as T  # noqa: E402
from config.indicator_weights import INDICATOR_WEIGHTS as W  # noqa: E402
from scripts.calculate_score import (  # noqa: E402
    CCSI_PCTILE_ANCHORS,
    HOT_ZONE,
    KOSPI_DD_PCTILE_ANCHORS,
    SCORE_DISPLAY_ANCHORS,
    cap_progress,
    compute_progress,
    percentile_from_anchors,
    stage_for_score,
)

pd.set_option("display.width", 330)
PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]
# calculate_score.main 안의 지역 상수와 같은 값(괴리 지수 lead 매핑)
LEAD_FLOOR, LEAD_CEIL = -75.0, 45.0

rows = json.load(open("values.json"))
by = defaultdict(dict)
for r in rows:
    by[r["slug"]][r["date"]] = r


def ser(slug: str) -> pd.Series:
    d = by[slug]
    return pd.Series({pd.Timestamp(k): float(v["raw_value"]) for k, v in d.items()}).sort_index()


def det(slug: str, key: str) -> pd.Series:
    d = by[slug]
    out = {pd.Timestamp(k): (v.get("details") or {}).get(key) for k, v in d.items()}
    return pd.Series({k: float(v) for k, v in out.items() if v is not None}).sort_index()


kospi = ser("kospi_close_raw")
IDX = kospi.index

# ── 히스토리가 없는 3개는 원본에서 재구성 ─────────────────────────────────
high_gap = pd.Series({
    d: (kospi[d] - kospi[(kospi.index >= d - timedelta(days=365)) & (kospi.index < d)].max())
       / kospi[(kospi.index >= d - timedelta(days=365)) & (kospi.index < d)].max() * 100
    for d in IDX if len(kospi[(kospi.index >= d - timedelta(days=365)) & (kospi.index < d)]) >= 20
})
_b = ser("buffett_index")
buffett = kospi * float((_b[_b.index.intersection(kospi.index)] / kospi[_b.index.intersection(kospi.index)]).median())
_ccsi = ser("consumer_sentiment_index").reindex(
    ser("consumer_sentiment_index").index.union(IDX)).ffill().reindex(IDX)
lead = pd.Series({
    d: percentile_from_anchors(float(high_gap[d]), KOSPI_DD_PCTILE_ANCHORS)
       - percentile_from_anchors(float(_ccsi[d]), CCSI_PCTILE_ANCHORS)
    for d in IDX if d in high_gap.index and not pd.isna(_ccsi[d])
})

RAW = {"kospi_high_gap": high_gap, "buffett_index": buffett}
SHORT = ["investor_deposit", "individual_net_buy", "dcinside_post_count", "turnover_concentration",
         "news_sentiment", "brokerage_app_rank", "youtube_finance_search_views",
         "bestseller_finance_ratio", "github_trading_bot_repos"]

# ── 설정 그대로 progress 계산 ─────────────────────────────────────────────
prog, means = {}, {}
for slug, cfg in T.items():
    if slug not in W:
        continue  # 점수에서 빠진 지표(코스닥)
    if slug == "small_business_crisis_index":
        prog[slug] = ((lead - LEAD_FLOOR) / (LEAD_CEIL - LEAD_FLOOR) * 100).clip(0, 100)
        continue
    vals = RAW.get(slug, ser(slug) if slug in by else None)
    if vals is None or vals.empty:
        continue
    rs = cfg.get("relative_surge")
    if rs is not None:
        surge, level = det(slug, "surge_pct"), det(slug, "level_pct")
        p = ((surge - rs["floor"]) / (rs["ceil"] - rs["floor"]) * 100)
        lw = cfg.get("level_weight")
        if lw:
            p = (p.clip(0, 100) * (1 - lw)).add(level * lw, fill_value=np.nan).dropna()
        prog[slug] = p.clip(0, 100)
    elif cfg["kind"] == "cumulative_average":
        run = vals.expanding().mean()
        prog[slug] = pd.Series(
            {d: cap_progress(compute_progress(slug, float(vals[d]), float(run[d]), cfg)) for d in vals.index})
    else:
        prog[slug] = pd.Series(
            {d: cap_progress(compute_progress(slug, float(vals[d]), cfg["threshold"], cfg)) for d in vals.index})
    if slug in SHORT:
        means[slug] = float(prog[slug].mean())

LONG = [s for s in prog if s not in SHORT]
wl = pd.Series({s: W[s] for s in LONG})
short_contrib = sum(W[s] * means[s] for s in SHORT if s in means)
short_w = sum(W[s] for s in SHORT if s in means)

M = pd.DataFrame({s: prog[s] for s in LONG}).reindex(IDX)
long_raw = ((M.fillna(0) * wl).sum(axis=1) / (M.notna() * wl).sum(axis=1)).where((M.notna() * wl).sum(axis=1) > 0)
raw = (long_raw * wl.sum() + short_contrib) / (wl.sum() + short_w)
score = raw.map(lambda x: percentile_from_anchors(x, SCORE_DISPLAY_ANCHORS) if not pd.isna(x) else np.nan)

print("=" * 200)
print(f"점수 산정 지표 {len(W)}개 · weight_sum {sum(W.values()):.1f} "
      f"(장기 {wl.sum():.1f} {len(LONG)}개 + 단기 {short_w:.1f} {len(means)}개)")
print(f"기간 {IDX.min().date()} ~ {IDX.max().date()} ({len(IDX)}영업일)")
print(f"앵커 {SCORE_DISPLAY_ANCHORS}")

# ── 지표별 진단 ─────────────────────────────────────────────────────────
def sp(a, b):
    j = pd.concat([a, b], axis=1).dropna()
    if len(j) < 20:
        return np.nan
    x, y = j.iloc[:, 0].rank(), j.iloc[:, 1].rank()
    return np.nan if x.std() == 0 or y.std() == 0 else float(np.corrcoef(x, y)[0, 1])


fwd_dd = pd.Series({d: kospi[(kospi.index > d) & (kospi.index <= d + timedelta(days=90))].min() / kospi[d] - 1 for d in IDX})
pm = pd.Series(False, index=IDX)
tm = pd.Series(False, index=IDX)
for d in PEAKS:
    i = IDX.get_loc(pd.Timestamp(d)); pm.iloc[max(0, i - 7):i + 1] = True
for d in TROUGHS:
    i = IDX.get_loc(pd.Timestamp(d)); tm.iloc[max(0, i - 7):i + 1] = True

diag = []
for s in prog:
    x = prog[s].reindex(IDX)
    diag.append(dict(slug=s, w=W[s], n=int(prog[s].notna().sum()), 중앙=x.median(),
                     바닥=(x <= 0).mean() * 100, 천장=(x >= 100).mean() * 100,
                     초고온=(x >= HOT_ZONE).mean() * 100, 최소=x.min(),
                     스프=x[pm].mean() - x[tm].mean(), r_gap=sp(x, high_gap), r_dd=sp(x, fwd_dd)))
D = pd.DataFrame(diag).set_index("slug").sort_values("w", ascending=False)
print()
print("A. 지표별 (단기 9개는 n이 작아 스프레드·상관 무의미)")
print(D.round(2).to_string())
print(f"\n  구조적 하한 합계 → 종합 원점수 {(D['w'] * D['최소']).sum() / sum(W.values()):.1f}점")

# ── 종합 ────────────────────────────────────────────────────────────────
def pmax(x, d, b=5, f=5):
    i = IDX.get_loc(pd.Timestamp(d))
    return x.reindex(IDX[max(0, i - b):i + f + 1]).max()


stg = pd.cut(score.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
j = pd.concat([score.rename("s"), fwd_dd.rename("dd")], axis=1).dropna()
j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
dd = (j.groupby("q", observed=True)["dd"].mean() * 100).round(1).tolist()
print()
print("=" * 200)
print("B. 종합점수")
print(f"  범위 {score.min():.0f}~{score.max():.0f} · 중앙 {score.median():.0f} · 최근({IDX.max().date()}) {score.dropna().iloc[-1]:.0f}")
print(f"  고점 기간 최고(±5영업일) {'/'.join(f'{pmax(score, d):.0f}' for d in PEAKS)}")
print(f"  고점 당일 {'/'.join(f'{score.get(pd.Timestamp(d), np.nan):.0f}' for d in PEAKS)}")
print(f"  저점 당일 {'/'.join(f'{score.get(pd.Timestamp(d), np.nan):.0f}' for d in TROUGHS)}")
print(f"  스프레드(고점창−저점창) {score[pm].mean() - score[tm].mean():.1f}")
print("  국면 " + " ".join(f"{k} {v / len(stg) * 100:.0f}%" for k, v in stg.value_counts().sort_index().items()))
print(f"  vs 전고점괴리 r={sp(score, high_gap):+.3f} · vs 향후90일 최대낙폭 r={sp(score, fwd_dd):+.3f}")
print(f"  향후 최대낙폭 4분위 {dd}  {'단조 O' if all(dd[i] >= dd[i+1] for i in range(3)) else '단조 X'}")

print()
print("C. 월별")
m = pd.DataFrame({"코스피": kospi, "점수": score}).resample("ME").agg({"코스피": "last", "점수": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["점수"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(0).to_string())
