"""최종 메뉴 — '코스피 높을 때 70+'를 만드는 세 경로와 각각의 대가."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, series, spearman
from lift import PEAKS, TROUGHS, W_CUR, W_REC, topk, wavg
from recal import newprog
from pctmap import TARGET, apply_anchors, make_anchors

pd.set_option("display.width", 320)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]

# §4-2 거래대금 절대축(7:3)
det = series["kospi_volume_surge"]["details"]
surge = pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)
absv = series["kospi_volume_surge"]["raw"]
lvl = {}
for i, d in enumerate(absv.index):
    h = absv.iloc[max(0, i - 250): i]
    if len(h) >= 60:
        lvl[d] = float((h < absv.iloc[i]).mean() * 100)
lvl = pd.Series(lvl)
vol_fix = (((surge + 55) / 140 * 100).clip(0, 100).reindex(lvl.index) * 0.7 + lvl * 0.3).dropna()

REC = {**{k: CAPPED[k] for k in LONG}, **{k: v for k, v in newprog.items() if k in LONG}}
REC_V = {**REC, "kospi_volume_surge": vol_fix}

# 가격축 강화 옵션: 전고점 위치·밸류에 더 무게
W_PRICE = W_REC.copy()
W_PRICE["kospi_high_gap"] = 6.0
W_PRICE["buffett_index"] = 3.0
W_PRICE["kospi_volume_surge"] = 5.0


def rep(name, s):
    s = pd.Series(s).reindex(kospi.index)
    pk = np.array([s.get(pd.Timestamp(d), np.nan) for d in PEAKS])
    tr = np.array([s.get(pd.Timestamp(d), np.nan) for d in TROUGHS])
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    j = pd.concat([s.rename("s"), kdf[["fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    dd = (j.groupby("q", observed=True)["fwd_dd"].mean() * 100).round(1).tolist()
    hi = s[kospi >= 7000].median()
    near = s[kdf["gap"] >= -3].median()
    return dict(안=name, 고점=f"{pk[0]:.0f}/{pk[1]:.0f}/{pk[2]:.0f}", 저점=f"{tr[0]:.0f}/{tr[1]:.0f}/{tr[2]:.0f}",
                코스피7000이상=round(hi, 1), 전고점3퍼이내=round(near, 1),
                저온=round((stg == "저온").mean() * 100), 상온=round((stg == "상온").mean() * 100),
                고온=round((stg == "고온").mean() * 100), 초고온=round((stg == "초고온").mean() * 100),
                r_gap=round(spearman(s, kdf["gap"])[0], 3),
                단조="O" if all(dd[i] >= dd[i + 1] for i in range(3)) else "-")


def mapped(base):
    return apply_anchors(base, make_anchors(base))


rows = [
    rep("① 현행", wavg(pd.DataFrame(({k: CAPPED[k] for k in LONG})).reindex(kospi.index), W_CUR)),
    rep("② 권고눈금+권고W (문서 §4)", wavg(pd.DataFrame(REC).reindex(kospi.index), W_CUR * 0 + W_REC)),
    rep("③ ②+거래대금 절대축", wavg(pd.DataFrame(REC_V).reindex(kospi.index), W_REC)),
    rep("④ ③+백분위 앵커매핑", mapped(wavg(pd.DataFrame(REC_V).reindex(kospi.index), W_REC))),
    rep("⑤ ④+가격축 강화", mapped(wavg(pd.DataFrame(REC_V).reindex(kospi.index), W_PRICE))),
    rep("⑥ ③+상위60% 집계+앵커매핑", mapped(topk(pd.DataFrame(REC_V).reindex(kospi.index), W_REC, 0.6))),
    rep("⑦ ③+상위75% 집계+앵커매핑", mapped(topk(pd.DataFrame(REC_V).reindex(kospi.index), W_REC, 0.75))),
]
print("=" * 230)
print("요구조건: 코스피 고점권에서 70+ / 폭락 바닥에서 저온")
print(pd.DataFrame(rows).set_index("안").to_string())

print()
print("=" * 230)
best = mapped(topk(pd.DataFrame(REC_V).reindex(kospi.index), W_REC, 0.6))
print("⑥ 안의 월별 서사")
m = pd.DataFrame({"코스피": kospi, "점수": best}).resample("ME").agg({"코스피": "last", "점수": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["점수"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print()
for lbl, d in zip(["고점 11/03", "저점 11/24", "고점 02/26", "저점 03/31", "고점 06/22", "저점 07/20"],
                  PEAKS[:1] + TROUGHS[:1] + PEAKS[1:2] + TROUGHS[1:2] + PEAKS[2:] + TROUGHS[2:]):
    d = pd.Timestamp(d)
    if d in best.index and not pd.isna(best[d]):
        print(f"    {lbl}  코스피 {kospi[d]:>6.0f} → {best[d]:5.1f}")
print(f"\n  앵커(원점수→표시): {[(round(x,1), y) for x, y in make_anchors(topk(pd.DataFrame(REC_V).reindex(kospi.index), W_REC, 0.6))]}")
