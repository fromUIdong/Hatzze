"""최종 후보의 재척도 앵커를 상수로 확정 — 운영에 박아 넣을 숫자."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, spearman
from lift import PEAKS, TROUGHS, W_REC, scaled, wavg

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]

base = wavg(scaled(85), W_REC).reindex(kospi.index)
print("=" * 150)
print("A. 재척도 전 원점수(ceiling p85 + 권고 가중치)의 실측 분위수 — 앵커 후보")
qs = np.percentile(base.dropna(), [1, 3, 5, 10, 25, 50, 75, 90, 95, 97, 99])
for q, v in zip([1, 3, 5, 10, 25, 50, 75, 90, 95, 97, 99], qs):
    print(f"  p{q:<3} = {v:.1f}")

print()
print("=" * 150)
print("B. 앵커별 결과 — (원점수 lo, hi) → (표시 lo, hi) 선형")


def rep(name, s):
    s = s.reindex(kospi.index)
    pk = np.array([s.get(pd.Timestamp(d), np.nan) for d in PEAKS])
    tr = np.array([s.get(pd.Timestamp(d), np.nan) for d in TROUGHS])
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    j = pd.concat([s.rename("s"), kdf[["fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    dd = (j.groupby("q", observed=True)["fwd_dd"].mean() * 100).round(1).tolist()
    print(f"  {name:34} 고점 {pk[0]:4.0f}/{pk[1]:4.0f}/{pk[2]:4.0f} 저점 {tr[0]:4.0f}/{tr[1]:4.0f}/{tr[2]:4.0f} | "
          f"중앙 {s.median():5.1f} 최근 {s.dropna().iloc[-1]:5.1f} | 저온 {(stg=='저온').mean()*100:4.1f}% 상온 {(stg=='상온').mean()*100:4.1f}% "
          f"고온 {(stg=='고온').mean()*100:4.1f}% 초고온 {(stg=='초고온').mean()*100:4.1f}% | 낙폭Q {dd}")


def aff(s, lo, hi, lo_t, hi_t):
    return (lo_t + (s - lo) / (hi - lo) * (hi_t - lo_t)).clip(0, 100)


rep("재척도 없음", base)
for lo, hi, lo_t, hi_t in [
    (30, 78, 15, 90),
    (30, 78, 20, 88),
    (32, 76, 20, 85),
    (28, 80, 15, 92),
    (35, 75, 25, 85),
]:
    rep(f"원 {lo}~{hi} → 표시 {lo_t}~{hi_t}", aff(base, lo, hi, lo_t, hi_t))

print()
print("=" * 150)
print("C. 확정안: 원 30~78 → 표시 20~88 의 월별 서사")
s = aff(base, 30, 78, 20, 88).reindex(kospi.index)
m = pd.DataFrame({"코스피": kospi, "점수": s}).resample("ME").agg({"코스피": "last", "점수": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["점수"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print()
print("  주요 이벤트 판독:")
for lbl, d in [("고점 2025-11-03", "2025-11-03"), ("저점 2025-11-24", "2025-11-24"),
               ("고점 2026-02-26", "2026-02-26"), ("저점 2026-03-31", "2026-03-31"),
               ("고점 2026-06-22", "2026-06-22"), ("저점 2026-07-20", "2026-07-20")]:
    d = pd.Timestamp(d)
    if d in s.index and not pd.isna(s[d]):
        print(f"    {lbl}  코스피 {kospi[d]:>6.0f} → {s[d]:5.1f}")
print(f"\n  r_gap {spearman(s, kdf['gap'])[0]:+.3f}   r_fwd_dd {spearman(s, kdf['fwd_dd'])[0]:+.3f}")
print(f"  코스피 8,000 이상이던 날의 점수: 중앙 {s[kospi >= 8000].median():.1f} (n={(kospi>=8000).sum()})")
print(f"  코스피 7,000 이상이던 날의 점수: 중앙 {s[kospi >= 7000].median():.1f} (n={(kospi>=7000).sum()})")
