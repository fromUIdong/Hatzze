"""종합점수(햇쩨 지수) 재구성 + 구조적 하한 분석 + VKOSPI 스케일 점검."""
import numpy as np
import pandas as pd

from engine import CAPPED, INDICATOR_WEIGHTS, kdf, kospi, series, spearman

pd.set_option("display.width", 260)

LONG = {k: v for k, v in CAPPED.items() if len(v) >= 150}
print(f"장기 히스토리 지표 {len(LONG)}개, 가중치 합 {sum(INDICATOR_WEIGHTS[k] for k in LONG):.1f}/50.0")

# ---------------------------------------------------------- 구조적 하한
print()
print("=" * 130)
print("A. 구조적 하한 — 이 지표가 '1년 내내 한 번도 그 아래로 내려가지 않은' 과열도")
rows = []
for slug, s in CAPPED.items():
    w = INDICATOR_WEIGHTS[slug]
    rows.append(dict(slug=slug, w=w, n=len(s), min=float(s.min()), p5=float(s.quantile(0.05)), contrib=w * float(s.min())))
fl = pd.DataFrame(rows).set_index("slug").sort_values("contrib", ascending=False)
print(fl.round(1).to_string())
tot_w = sum(INDICATOR_WEIGHTS[k] for k in CAPPED)
print(f"\n합계 하한 기여 {fl['contrib'].sum():.1f} / 가중치합 {tot_w:.1f} → 종합점수 구조적 하한 ≈ {fl['contrib'].sum()/tot_w:.1f}점")
lw = {k: INDICATOR_WEIGHTS[k] for k in LONG}
flL = fl.loc[list(LONG)]
print(f"(장기 지표만) 하한 {flL['contrib'].sum()/sum(lw.values()):.1f}점")

# ---------------------------------------------------------- 종합점수 재구성
print()
print("=" * 130)
print("B. 종합점수 재구성 (장기 지표 16개, 가중치 재정규화)")
mat = pd.DataFrame(LONG).reindex(kospi.index)
w = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
avail = mat.notna()
num = (mat.fillna(0) * w).sum(axis=1)
den = (avail * w).sum(axis=1)
score = (num / den).where(den > 0)
score.name = "score"

comp = pd.DataFrame({"kospi": kospi, "score": score, "gap": kdf["gap"]}).dropna()
print(comp["score"].describe().round(1).to_string())
print()
print("월별 종합점수 vs 코스피")
mo = comp.resample("ME").agg({"kospi": "last", "score": "mean", "gap": "mean"})
mo["stage"] = pd.cut(mo["score"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(mo.round(1).to_string())

print()
print("C. 이벤트별 종합점수")
for lbl, d in [("고점 2026-02-26", "2026-02-26"), ("저점 2026-03-31", "2026-03-31"),
               ("고점 2026-06-22", "2026-06-22"), ("저점 2026-07-20", "2026-07-20"),
               ("고점 2025-11-03", "2025-11-03"), ("저점 2025-11-24", "2025-11-24")]:
    d = pd.Timestamp(d)
    if d in comp.index:
        print(f"  {lbl}: 코스피 {comp.loc[d,'kospi']:.0f}  종합점수 {comp.loc[d,'score']:.1f}")

print()
print("D. 종합점수의 코스피 대비 상관")
for tgt in ["gap", "bwd20", "fwd5", "fwd20", "fwd60", "fwd_dd"]:
    r, n = spearman(score, kdf[tgt])
    print(f"  score vs {tgt:7}: r={r:+.3f} (n={n})")

# 분위별 향후 수익률
print()
print("E. 종합점수 5분위별 향후 코스피 수익률")
j = pd.concat([score, kdf[["fwd5", "fwd20", "fwd60", "fwd_dd"]]], axis=1).dropna()
j["q"] = pd.qcut(j["score"], 5, labels=["Q1(저)", "Q2", "Q3", "Q4", "Q5(고)"])
agg = j.groupby("q", observed=True)[["fwd5", "fwd20", "fwd60", "fwd_dd"]].mean() * 100
agg["n"] = j.groupby("q", observed=True).size()
print(agg.round(1).to_string())

score.to_pickle("score.pkl")

# ---------------------------------------------------------- VKOSPI 스케일
print()
print("=" * 130)
print("F. VKOSPI raw 시계열 — 스케일이 도중에 바뀌었는지 점검")
vk = series["vkospi"]["raw"]
print(vk.resample("ME").agg(["min", "median", "max", "count"]).round(1).to_string())

print()
print("G. leverage_etf_volume 이상치")
lev = series["leverage_etf_volume"]["raw"]
print(lev[lev > 100].to_string())
