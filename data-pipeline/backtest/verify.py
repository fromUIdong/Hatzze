"""문서 §4-1/§4-2/§4-3 권고를 문서에 적은 숫자 그대로 조합해 재검증."""
import numpy as np
import pandas as pd

from engine import BUFFETT, CAPPED, DIVERGENCE, HIGH_GAP, INDICATOR_WEIGHTS, kdf, kospi, series, spearman
from recal import PM, TM, build

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
W_CUR = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
W_REC = W_CUR.copy()
for k, v in {"kospi_volume_surge": 4.5, "kospi_high_gap": 4.0, "naver_search_trend": 3.5,
             "kospi_asia_relative_strength": 2.0, "leverage_etf_volume": 2.0,
             "upbit_speculation_index": 2.0, "usdkrw_volatility": 1.0, "vkospi": 1.5,
             "kospi_gold_ratio": 1.0, "put_call_ratio": 1.0, "kosdaq_kospi_ratio": 0.5}.items():
    W_REC[k] = v

r_gold = series["kospi_gold_ratio"]["raw"]
print("금비율 floor 후보별 중앙 과열도 / 구조적 하한")
for f in [0.5, 0.7, 0.85]:
    p = ((r_gold - f) / (2.2 - f) * 100).clip(0, 100)
    print(f"  floor={f}: 중앙 {p.median():.1f}  최소 {p.min():.1f}  초고온 {(p>=75).mean()*100:.1f}%")

det = series["kospi_volume_surge"]["details"]
surge = pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)
absv = series["kospi_volume_surge"]["raw"]
lvl = {}
for i, d in enumerate(absv.index):
    h = absv.iloc[max(0, i - 250): i]
    if len(h) >= 60:
        lvl[d] = float((h < absv.iloc[i]).mean() * 100)
lvl = pd.Series(lvl)

def lin(s, f, c):
    return ((s - f) / (c - f) * 100).clip(0, 100)

REC = {k: CAPPED[k] for k in LONG}
REC["kospi_high_gap"] = pd.Series(
    {d: (75 + (v + 1.5) / 6.5 * 25) if v >= -1.5 else (v + 35) / 33.5 * 75 for d, v in HIGH_GAP.items()}
).clip(0, 100)
REC["naver_search_trend"] = lin(series["naver_search_trend"]["raw"], 0, 48)
REC["upbit_speculation_index"] = lin(series["upbit_speculation_index"]["raw"], 0, 75)
REC["usdkrw_volatility"] = lin(series["usdkrw_volatility"]["raw"], 0.85, 0.20)
REC["leverage_etf_volume"] = lin(series["leverage_etf_volume"]["raw"], 38, 74)
REC["kospi_asia_relative_strength"] = lin(series["kospi_asia_relative_strength"]["raw"], -10, 23)
REC["fine_dining_search_index"] = lin(series["fine_dining_search_index"]["raw"], 18, 48)
REC["luxury_consumption_index"] = lin(series["luxury_consumption_index"]["raw"], 48, 78)
REC["kospi_gold_ratio"] = lin(r_gold, 0.7, 2.2)
REC["kospi_volume_surge"] = (lin(surge, -55, 85).reindex(lvl.index) * 0.7 + lvl * 0.3).dropna()

print()
print("=" * 150)
BIG_PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
BIG_TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]
for nm, (pmap, wv) in {
    "① 현행 눈금 + 현행 가중치": ({k: CAPPED[k] for k in LONG}, W_CUR),
    "② 현행 눈금 + 권고 가중치": ({k: CAPPED[k] for k in LONG}, W_REC),
    "③ 권고 눈금 + 현행 가중치": (REC, W_CUR),
    "④ 권고 눈금 + 권고 가중치": (REC, W_REC),
}.items():
    s = build({k: pmap[k] for k in LONG if k in pmap}, wv).reindex(kospi.index)
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    vc = stg.value_counts()
    print(f"\n{nm}")
    print(f"  범위 {s.min():.1f}~{s.max():.1f} 중앙 {s.median():.1f} | 스프레드 {s[PM].mean()-s[TM].mean():.1f} "
          f"(고점 {s[PM].mean():.1f} 저점 {s[TM].mean():.1f})")
    print(f"  r_gap {spearman(s, kdf['gap'])[0]:+.3f}  r_fwd60 {spearman(s, kdf['fwd60'])[0]:+.3f}  r_fwd_dd {spearman(s, kdf['fwd_dd'])[0]:+.3f}")
    print("  국면 " + " ".join(f"{k} {vc.get(k,0)/len(stg)*100:.1f}%" for k in ["저온", "상온", "고온", "초고온"]))
    print("  고점 " + " / ".join(f"{s.get(pd.Timestamp(d), np.nan):.0f}" for d in BIG_PEAKS)
          + "   저점 " + " / ".join(f"{s.get(pd.Timestamp(d), np.nan):.0f}" for d in BIG_TROUGHS))
    j = pd.concat([s.rename("s"), kdf[["fwd60", "fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    g = (j.groupby("q", observed=True)[["fwd60", "fwd_dd"]].mean() * 100).round(1)
    print("  " + " / ".join(f"{i} fwd60 {r.fwd60:+.0f}% dd {r.fwd_dd:+.1f}%" for i, r in g.iterrows()))

print()
print("=" * 150)
print("floor 추가로 사라지는 구조적 하한")
tot = sum(INDICATOR_WEIGHTS[k] * CAPPED[k].min() for k in CAPPED)
print(f"  현행 전체 구조적 하한: {tot/50:.1f}점")
four = ["usdkrw_volatility", "leverage_etf_volume", "fine_dining_search_index", "kospi_gold_ratio"]
six = four + ["turnover_concentration", "brokerage_app_rank"]
print(f"  4개(환율·레버리지·오마카세·금) 기여: {sum(INDICATOR_WEIGHTS[k]*CAPPED[k].min() for k in four)/50:.1f}점")
print(f"  6개(+쏠림·앱순위) 기여: {sum(INDICATOR_WEIGHTS[k]*CAPPED[k].min() for k in six)/50:.1f}점")
