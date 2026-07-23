"""지표별 눈금 진단 + 코스피 대비 동행성/선행성 측정."""
import numpy as np
import pandas as pd
from datetime import timedelta

from engine import CAPPED, PROG, INDICATOR_WEIGHTS, kdf, kospi, spearman, pearson

pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)

PEAKS = ["2025-07-30", "2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-08-01", "2025-11-24", "2026-03-31", "2026-07-20"]
BIG_PEAKS = ["2026-02-26", "2026-06-22"]
BIG_TROUGHS = ["2026-03-31", "2026-07-20"]


def window_mean(s: pd.Series, days: list[str], back: int = 7, fwd: int = 0) -> float:
    """이벤트일 기준 [-back, +fwd] 영업일 창의 평균 progress."""
    vals = []
    for d in days:
        d = pd.Timestamp(d)
        idx = kospi.index
        if d not in idx:
            continue
        i = idx.get_loc(d)
        win = idx[max(0, i - back) : i + fwd + 1]
        w = s.reindex(win).dropna()
        if len(w):
            vals.append(w.mean())
    return float(np.mean(vals)) if vals else float("nan")


rows = []
for slug, s in CAPPED.items():
    raw_p = PROG[slug]
    n = len(s)
    floor_pct = float((raw_p <= 0).mean() * 100)
    ceil_pct = float((raw_p >= 100).mean() * 100)
    hot_pct = float((s >= 75).mean() * 100)
    cold_pct = float((s <= 25).mean() * 100)

    r_gap, n_gap = spearman(s, kdf["gap"])
    r_bwd, _ = spearman(s, kdf["bwd20"])
    r_f20, n20 = spearman(s, kdf["fwd20"])
    r_f60, _ = spearman(s, kdf["fwd60"])
    r_dd, _ = spearman(s, kdf["fwd_dd"])

    pk = window_mean(s, BIG_PEAKS)
    tr = window_mean(s, BIG_TROUGHS)

    rows.append(
        dict(
            slug=slug,
            w=INDICATOR_WEIGHTS.get(slug, np.nan),
            n=n,
            med=float(s.median()),
            std=float(s.std()),
            floor=floor_pct,
            ceil=ceil_pct,
            hot=hot_pct,
            cold=cold_pct,
            r_gap=r_gap,
            r_bwd=r_bwd,
            r_f20=r_f20,
            r_f60=r_f60,
            r_dd=r_dd,
            peak=pk,
            trough=tr,
            spread=pk - tr,
            n_ovl=n20,
        )
    )

df = pd.DataFrame(rows).set_index("slug")
df = df.sort_values("w", ascending=False)

print("=" * 250)
print("A. 눈금 진단 (progress 분포) — floor/ceil = 원본 progress가 0이하/100이상인 날 비율")
print(
    df[["w", "n", "med", "std", "floor", "ceil", "hot", "cold"]]
    .round(1)
    .to_string()
)

print()
print("=" * 250)
print("B. 코스피 대비 (Spearman). r_gap/r_bwd = 동행성(+가 맞음), r_f20/r_f60/r_dd = 선행성(−가 맞음)")
print(
    df[["w", "n_ovl", "r_gap", "r_bwd", "r_f20", "r_f60", "r_dd"]].round(3).to_string()
)

print()
print("=" * 250)
print("C. 이벤트 정렬 — 대형 고점(2026-02-26, 2026-06-22) / 대형 저점(2026-03-31, 2026-07-20) 직전 7영업일 평균 progress")
print(df[["w", "peak", "trough", "spread"]].round(1).to_string())

df.to_pickle("diag.pkl")

print()
print("=" * 250)
print("D. 유의성 참고 — n=232 기준 |r|>0.13 이면 p<0.05 (독립 표본 가정, 자기상관 때문에 실제론 더 보수적으로 봐야 함)")

# 블록 부트스트랩으로 r_f20 신뢰구간
def block_boot(s, target, n_boot=2000, block=20, seed=0):
    j = pd.concat([s.rename("x"), target.rename("y")], axis=1).dropna()
    if len(j) < 40:
        return np.nan, np.nan
    x = j["x"].rank().to_numpy()
    y = j["y"].rank().to_numpy()
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, nb)
        idx = np.concatenate([np.arange(s0, s0 + block) for s0 in starts])[:n]
        xa, ya = x[idx], y[idx]
        if xa.std() == 0 or ya.std() == 0:
            continue
        out.append(np.corrcoef(xa, ya)[0, 1])
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


ci = {}
for slug, s in CAPPED.items():
    lo, hi = block_boot(s, kdf["fwd20"])
    ci[slug] = (lo, hi)
cidf = pd.DataFrame(ci, index=["lo95", "hi95"]).T
res = df[["w", "r_f20"]].join(cidf).round(3)
res["유의"] = np.where(
    res["lo95"].notna() & ((res["lo95"] > 0) | (res["hi95"] < 0)), "O", "-"
)
print(res.to_string())
