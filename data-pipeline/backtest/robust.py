"""상승 속도 축의 과적합 점검 — 반기 분할, 기존 지표와의 중복, 이벤트 제외 검증."""
import numpy as np
import pandas as pd

from engine import kdf, kospi, series, spearman
from plan4 import apply_anchors, full, lin, wavg
from improve4 import T_HI, W_kq
from improve4b import P_g
from plus2 import P_m, W_base

pd.set_option("display.width", 330)
PEAK_DAYS = ["2025-11-03", "2026-02-26", "2026-06-22"]
mom = ((kospi / kospi.shift(60) - 1) * 100).dropna()

print("=" * 170)
print("A. 상승 속도가 기존 지표와 겹치는가")
for k in ["kospi_high_gap", "kospi_asia_relative_strength", "buffett_index", "kospi_volume_surge", "naver_search_trend"]:
    print(f"  60일 속도 vs {k:30} Spearman {spearman(mom, P_g[k])[0]:+.3f}")
print(f"  60일 속도 vs 전고점괴리(raw)              Spearman {spearman(mom, kdf['gap'])[0]:+.3f}")

print()
print("=" * 170)
print("B. 반기 분할 — 전반기/후반기 각각에서도 향후 낙폭을 설명하나")
half = kospi.index[len(kospi) // 2]
for nm, sl in [("전반 25-07~26-01", kospi.index[kospi.index < half]), ("후반 26-01~26-07", kospi.index[kospi.index >= half])]:
    m = mom.reindex(sl).dropna()
    d = kdf["fwd_dd"].reindex(sl)
    g = kdf["gap"].reindex(sl)
    print(f"  {nm}: n={len(m)}  vs 향후낙폭 {spearman(m, d)[0]:+.3f}  vs 전고점괴리 {spearman(m, g)[0]:+.3f}")

print()
print("=" * 170)
print("C. 블록 부트스트랩(20일 블록) — 향후 낙폭 상관의 95% 신뢰구간")


def boot(a, b, n_boot=3000, block=20, seed=1):
    j = pd.concat([a.rename("x"), b.rename("y")], axis=1).dropna()
    x, y = j["x"].rank().to_numpy(), j["y"].rank().to_numpy()
    n = len(x); rng = np.random.default_rng(seed); nb = int(np.ceil(n / block)); out = []
    for _ in range(n_boot):
        st = rng.integers(0, n - block + 1, nb)
        idx = np.concatenate([np.arange(s, s + block) for s in st])[:n]
        if x[idx].std() and y[idx].std():
            out.append(np.corrcoef(x[idx], y[idx])[0, 1])
    return np.percentile(out, [2.5, 50, 97.5])


lo, md, hi = boot(mom, kdf["fwd_dd"])
print(f"  60일 속도 vs 향후 최대낙폭: 중앙 {md:+.3f}  95%CI [{lo:+.3f}, {hi:+.3f}]  → {'유의' if hi < 0 else '비유의'}")
BASE_no = wavg(P_g, W_kq)
lo2, md2, hi2 = boot(BASE_no, kdf["fwd_dd"])
print(f"  ④＋ 종합점수 vs 향후 최대낙폭: 중앙 {md2:+.3f}  95%CI [{lo2:+.3f}, {hi2:+.3f}]")


def build(pmap, w, smooth=3):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    a = [(float(np.percentile(b.dropna(), p)), t) for p, t in T_HI]
    return apply_anchors(b, a)


print()
print("=" * 170)
print("D. 이벤트 하나를 빼고 앵커를 다시 잡아도 나머지 고점이 75를 넘나 (leave-one-out)")


def peakmax(s, day, back=5, fwd=5):
    i = kospi.index.get_loc(pd.Timestamp(day))
    return s.reindex(kospi.index[max(0, i - back):i + fwd + 1]).max()


for wt, pmap in [(0.0, P_g), (2.5, P_m), (3.5, P_m)]:
    W = W_kq.copy()
    if wt:
        W["kospi_speed_60d"] = wt
    for drop in PEAK_DAYS:
        keep = [d for d in kospi.index if abs((d - pd.Timestamp(drop)).days) > 45]
        b = wavg(pmap, W).ewm(span=3, adjust=False).mean()
        a = [(float(np.percentile(b.reindex(keep).dropna(), p)), t) for p, t in T_HI]
        s = apply_anchors(b, a)
        mx = [peakmax(s, d) for d in PEAK_DAYS]
        print(f"  속도 w={wt}  앵커를 '{drop} 제외'로 재산출 → 기간최고 {mx[0]:.0f}/{mx[1]:.0f}/{mx[2]:.0f}  (제외한 것 포함, 최저 {min(mx):.0f})")
    print()

print("=" * 170)
print("E. 속도 축 없이 발목 지표 조정만으로 75를 넘길 수 있나 (속도 미채택 대안)")
alts = {
    "④＋ 그대로": (P_g, W_kq),
    "업비트 1.0 · 풋콜 0.5 · VKOSPI 1.0": (P_g, pd.Series({**W_kq, "upbit_speculation_index": 1.0, "put_call_ratio": 0.5, "vkospi": 1.0})),
    "위 + 거래대금 5.0 · 전고점 4.5": (P_g, pd.Series({**W_kq, "upbit_speculation_index": 1.0, "put_call_ratio": 0.5,
                                                 "vkospi": 1.0, "kospi_volume_surge": 5.0, "kospi_high_gap": 4.5})),
}
res = []
for nm, (pm_, W) in alts.items():
    s = build(pm_, W)
    r = full(nm, s)
    r["기간최고±5"] = "/".join(f"{peakmax(s, d):.0f}" for d in PEAK_DAYS)
    res.append(r)
print(pd.DataFrame(res).set_index("안")[["기간최고±5", "고점", "저점", "스프", "r_gap", "r_dd", "낙폭Q", "단조"]].to_string())
