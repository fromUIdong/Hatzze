"""최종 권고안 튜닝 및 검증."""
import numpy as np
import pandas as pd

from engine import CAPPED, HIGH_GAP, INDICATOR_WEIGHTS, kdf, kospi, series, spearman
from recal import BIG_PEAKS, BIG_TROUGHS, PM, TM, build, newprog, W_NEW, W_CUR, LONG

pd.set_option("display.width", 300)
vk = series["vkospi"]["raw"]
absv = series["kospi_volume_surge"]["raw"]
det = series["kospi_volume_surge"]["details"]
surge = pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)


def st(s, name):
    s = s.reindex(kospi.index)
    print(f"  {name:38} 중앙 {s.median():5.1f} 바닥 {(s<=0).mean()*100:4.1f}% 천장 {(s>=100).mean()*100:4.1f}% 초고온 {(s>=75).mean()*100:5.1f}% | 고점 {s[PM].mean():5.1f} 저점 {s[TM].mean():5.1f} 스프 {s[PM].mean()-s[TM].mean():+6.1f} | r_gap {spearman(s, kdf['gap'])[0]:+.3f} r_dd {spearman(s, kdf['fwd_dd'])[0]:+.3f}")


print("=" * 190)
print("VKOSPI — floor-ceiling 방식 (기존 코드의 floor 분기 그대로 사용: floor=고VKOSPI, threshold=저VKOSPI)")
st((20.0 / vk * 100).clip(0, 100), "현행 thr=20 dir=low")
for f, c in [(70, 25), (80, 25), (90, 30), (95, 20)]:
    st(((vk - f) / (c - f) * 100).clip(0, 100), f"floor={f} ceiling={c}")

print()
print("=" * 190)
print("kospi_high_gap — kink 위치별")
def hg(f, k, c):
    return pd.Series({d: (75 + (v - k) / (c - k) * 25) if v >= k else (v - f) / (k - f) * 75 for d, v in HIGH_GAP.items()}).clip(0, 100)
for f, k, c in [(-35, -3, 0), (-35, -3, 5), (-35, -1.5, 5), (-35, 0, 5), (-30, -1.5, 5)]:
    st(hg(f, k, c), f"floor={f} kink={k} ceil={c}")

print()
print("=" * 190)
print("거래대금 — 혼합 비율별 (30일급증 : 250일 절대백분위)")
cur = ((surge - (-50)) / (80 - (-50)) * 100).clip(0, 100)
lvl = {}
for i, d in enumerate(absv.index):
    h = absv.iloc[max(0, i - 250): i]
    if len(h) >= 60:
        lvl[d] = float((h < absv.iloc[i]).mean() * 100)
lvl = pd.Series(lvl)
for a in [1.0, 0.7, 0.5, 0.3, 0.0]:
    st((cur.reindex(lvl.index) * a + lvl * (1 - a)).dropna(), f"급증 {a:.0%} : 절대 {1-a:.0%}")

print()
print("=" * 190)
print("최종 권고 조합")
FIN = {k: CAPPED[k] for k in LONG}
FIN.update(newprog)
FIN["kospi_high_gap"] = hg(-35, -1.5, 5)
FIN["vkospi"] = ((vk - 80) / (25 - 80) * 100).clip(0, 100)
FIN["kospi_volume_surge"] = (cur.reindex(lvl.index) * 0.7 + lvl * 0.3).dropna()

for nm, (pm_, wv) in {
    "① 현행 눈금 + 현행 가중치": ({k: CAPPED[k] for k in LONG}, W_CUR),
    "② 현행 눈금 + 권장 가중치": ({k: CAPPED[k] for k in LONG}, W_NEW),
    "③ 권장 눈금 + 현행 가중치": ({**{k: CAPPED[k] for k in LONG}, **newprog}, W_CUR),
    "④ 최종 권고(눈금+가중치)": (FIN, W_NEW),
}.items():
    s = build({k: pm_[k] for k in LONG if k in pm_}, wv).reindex(kospi.index)
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    vc = stg.value_counts()
    print(f"\n{nm}")
    print(f"  범위 {s.min():.1f}~{s.max():.1f} 중앙 {s.median():.1f} | 고점창 {s[PM].mean():.1f} 저점창 {s[TM].mean():.1f} 스프레드 {s[PM].mean()-s[TM].mean():.1f}")
    print(f"  r_gap {spearman(s, kdf['gap'])[0]:+.3f}  r_fwd60 {spearman(s, kdf['fwd60'])[0]:+.3f}  r_fwd_dd {spearman(s, kdf['fwd_dd'])[0]:+.3f}")
    print("  국면비중 " + " ".join(f"{k} {vc.get(k,0)/len(stg)*100:.0f}%" for k in ["저온", "상온", "고온", "초고온"]))
    ev = " | ".join(f"{pd.Timestamp(d).date()} {s.get(pd.Timestamp(d), np.nan):.0f}" for d in BIG_PEAKS)
    ev2 = " | ".join(f"{pd.Timestamp(d).date()} {s.get(pd.Timestamp(d), np.nan):.0f}" for d in BIG_TROUGHS)
    print(f"  고점: {ev}")
    print(f"  저점: {ev2}")
    print(f"  최근값(2026-07-22): {s.dropna().iloc[-1]:.1f}")
    j = pd.concat([s.rename("s"), kdf[["fwd20", "fwd60", "fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    g = (j.groupby("q", observed=True)[["fwd20", "fwd60", "fwd_dd"]].mean() * 100).round(1)
    print("  4분위 향후: " + " / ".join(f"{i} fwd60 {r.fwd60:+.0f}% dd {r.fwd_dd:+.1f}%" for i, r in g.iterrows()))
