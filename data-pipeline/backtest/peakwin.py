"""고점 '기간' 정의 + ④＋가 각 기간에서 몇까지 올라가나 + 무엇이 발목을 잡나."""
import numpy as np
import pandas as pd

from engine import kdf, kospi, series, spearman
from plan4 import P4, TARGET, W4, apply_anchors, full, lin, raw, wavg
from improve4 import P_kq, W_kq, T_HI
from improve4b import P_g

pd.set_option("display.width", 320)

PEAK_DAYS = ["2025-11-03", "2026-02-26", "2026-06-22"]
# 고점 '기간' = 고점일 기준 앞뒤 15영업일 (직전 상승 구간 + 직후 며칠)
WIN = 15


def windows(days=PEAK_DAYS, back=WIN, fwd=5):
    out = []
    for d in days:
        i = kospi.index.get_loc(pd.Timestamp(d))
        out.append(kospi.index[max(0, i - back): i + fwd + 1])
    return out


WINS = windows()


def build(pmap, w, target=T_HI, smooth=3):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    a = [(float(np.percentile(b.dropna(), p)), t) for p, t in target]
    return apply_anchors(b, a), b


S, BASE = build(P_g, W_kq)

print("=" * 150)
print(f"고점 기간(고점일 −{WIN} ~ +5영업일) 안에서 ④＋의 최고치")
for d, wdw in zip(PEAK_DAYS, WINS):
    seg = S.reindex(wdw).dropna()
    print(f"  {d} (코스피 {kospi[pd.Timestamp(d)]:.0f})  기간 최고 {seg.max():5.1f} @ {seg.idxmax().date()}  |  고점일 {S[pd.Timestamp(d)]:5.1f}  |  기간 평균 {seg.mean():5.1f}")

print()
print("=" * 150)
print("각 고점 기간 최고치 날짜에서 지표별 과열도 — 무엇이 발목을 잡나")
M = pd.DataFrame({k: P_g[k] for k in W_kq.index if k in P_g}).reindex(kospi.index)
for d, wdw in zip(PEAK_DAYS, WINS):
    seg = S.reindex(wdw).dropna()
    best_d = seg.idxmax()
    row = M.loc[best_d]
    t = pd.DataFrame({"과열도": row.round(1), "w": W_kq[row.index]})
    t["기여"] = (t["과열도"] * t["w"] / W_kq[row.notna()].sum()).round(2)
    print(f"\n--- {d} 기간 최고일 {best_d.date()} (원점수 {BASE[best_d]:.1f} → 표시 {seg.max():.1f})")
    print(t.sort_values("기여", ascending=False).to_string())
    cold = t[t["과열도"] < 40]
    print(f"    발목: {list(cold.index)}  가중치 {cold['w'].sum():.1f}/{W_kq.sum():.1f}")

print()
print("=" * 150)
print("코스피 '상승 속도' 축이 비어 있는가 — 기존 지표들과의 관계")
mom20 = (kospi / kospi.shift(20) - 1) * 100
mom60 = (kospi / kospi.shift(60) - 1) * 100
above60 = (kospi / kospi.rolling(60).mean() - 1) * 100
for nm, s in [("20일 수익률", mom20), ("60일 수익률", mom60), ("60일선 이격도", above60)]:
    pk = np.mean([s.reindex(w).max() for w in WINS])
    tr = np.mean([s.reindex(kospi.index[max(0, kospi.index.get_loc(pd.Timestamp(d)) - WIN):kospi.index.get_loc(pd.Timestamp(d)) + 6]).min()
                  for d in ["2025-11-24", "2026-03-31", "2026-07-20"]])
    print(f"  {nm:14} 분위 {np.nanpercentile(s.dropna(), [5, 25, 50, 75, 95]).round(1)} | vs 전고점괴리 {spearman(s, kdf['gap'])[0]:+.3f} | vs 향후낙폭 {spearman(s, kdf['fwd_dd'])[0]:+.3f}")
    print(f"                 기존 종합점수와의 상관 {spearman(s, BASE)[0]:+.3f}")
