"""④＋ 개선 3차 — 고점 '기간' 정의별 달성도 + 빠진 축(상승 속도) 추가."""
import numpy as np
import pandas as pd

from engine import kdf, kospi, series, spearman
from plan4 import TARGET, apply_anchors, full, lin, raw, wavg
from improve4 import T_HI, W_kq
from improve4b import P_g

pd.set_option("display.width", 330)
PEAK_DAYS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGH_DAYS = ["2025-11-24", "2026-03-31", "2026-07-20"]


def wins(days, back, fwd=5):
    out = []
    for d in days:
        i = kospi.index.get_loc(pd.Timestamp(d))
        out.append(kospi.index[max(0, i - back): i + fwd + 1])
    return out


def build(pmap, w, target=T_HI, smooth=3):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    a = [(float(np.percentile(b.dropna(), p)), t) for p, t in target]
    return apply_anchors(b, a)


def peak_report(name, s, backs=(5, 10, 15, 20)):
    r = {"안": name}
    for b in backs:
        mx = [s.reindex(w).max() for w in wins(PEAK_DAYS, b)]
        r[f"±{b}일 기간최고"] = "/".join(f"{v:.0f}" for v in mx)
        r[f"{b}_min"] = round(min(mx), 1)
    tr = [s.reindex(w).mean() for w in wins(TROUGH_DAYS, 10)]
    r["저점기간 평균"] = "/".join(f"{v:.0f}" for v in tr)
    return r


S_plus = build(P_g, W_kq)
rows = [peak_report("④＋", S_plus)]
print("=" * 200)
print("A. ④＋ — 고점 기간 정의별 '기간 내 최고치' (요구: 세 기간 모두 75 이상)")
print(pd.DataFrame(rows).set_index("안").to_string())

# ── 빠진 축: 코스피 상승 속도 ──────────────────────────────────────────────
print()
print("=" * 200)
print("B. 새 축 후보 '코스피 상승 속도' — 기존 지표군과 얼마나 다른 정보인가")
BASE = wavg(P_g, W_kq)
cands = {
    "60일 수익률(%)": (kospi / kospi.shift(60) - 1) * 100,
    "120일 수익률(%)": (kospi / kospi.shift(120) - 1) * 100,
    "60일선 이격도(%)": (kospi / kospi.rolling(60).mean() - 1) * 100,
    "20/60일선 이격(%)": (kospi.rolling(20).mean() / kospi.rolling(60).mean() - 1) * 100,
}
for nm, s in cands.items():
    print(f"  {nm:18} 분위 {np.nanpercentile(s.dropna(), [5,25,50,75,95]).round(1)} | vs 전고점괴리 {spearman(s, kdf['gap'])[0]:+.3f} "
          f"| vs 향후낙폭 {spearman(s, kdf['fwd_dd'])[0]:+.3f} | 기존 종합과 중복 {spearman(s, BASE)[0]:+.3f}")

# 60일 수익률을 지표로: floor/ceiling = p15/p90 (관측 13.9~57.6 사이)
mom = ((kospi / kospi.shift(60) - 1) * 100).dropna()
f, c = float(np.percentile(mom, 15)), float(np.percentile(mom, 90))
print(f"\n  → 채택안: 60일 수익률, floor {f:.1f}% / ceiling {c:.1f}%")
P_m = dict(P_g)
P_m["kospi_speed_60d"] = lin(mom, f, c)

print()
print("=" * 200)
print("C. 상승 속도 축을 넣고 가중치를 얼마로?")
res = []
for wt in [0.0, 1.5, 2.5, 3.5, 4.5]:
    W = W_kq.copy()
    if wt > 0:
        W["kospi_speed_60d"] = wt
    s = build(P_m if wt > 0 else P_g, W)
    r = full(f"속도 w={wt}", s)
    pr = peak_report(f"속도 w={wt}", s)
    r["±10기간최고"] = pr["±10일 기간최고"]
    r["±5기간최고"] = pr["±5일 기간최고"]
    res.append(r)
print(pd.DataFrame(res).set_index("안")[["±5기간최고", "±10기간최고", "고점", "저점", "스프", "저온", "상온", "고온", "초고온", "r_gap", "r_dd", "낙폭Q", "단조"]].to_string())

# ── 발목 지표 정리 ────────────────────────────────────────────────────────
print()
print("=" * 200)
print("D. 고점에서 반복적으로 발목 잡는 지표들의 가중치를 더 낮추면")
W_base = W_kq.copy(); W_base["kospi_speed_60d"] = 3.5
variants = {
    "기준(속도 3.5)": W_base,
    "＋업비트 2.0→1.0": {**W_base, "upbit_speculation_index": 1.0},
    "＋업비트 1.0, 풋콜 1.0→0.5": {**W_base, "upbit_speculation_index": 1.0, "put_call_ratio": 0.5},
    "＋위 + 오마카세/명품 0.5→0.25": {**W_base, "upbit_speculation_index": 1.0, "put_call_ratio": 0.5,
                                 "fine_dining_search_index": 0.25, "luxury_consumption_index": 0.25},
}
res2 = []
for nm, W in variants.items():
    W = pd.Series(W)
    s = build(P_m, W)
    r = full(nm, s)
    pr = peak_report(nm, s)
    r["±5기간최고"] = pr["±5일 기간최고"]
    r["±10기간최고"] = pr["±10일 기간최고"]
    res2.append(r)
print(pd.DataFrame(res2).set_index("안")[["±5기간최고", "±10기간최고", "고점", "저점", "스프", "저온", "상온", "고온", "초고온", "r_gap", "r_dd", "낙폭Q", "단조"]].to_string())

pd.to_pickle({"P_m": P_m, "W_base": W_base, "mom_floor": f, "mom_ceil": c}, "plus2.pkl")
