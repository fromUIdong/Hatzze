"""과적합된 floor 를 '절대 의미가 있는 값'으로 되돌리고, 코스닥 제거 후 다시 검증."""
import numpy as np
import pandas as pd

from engine import kdf, kospi, series, spearman
from plan4 import apply_anchors, full, lin, wavg
from improve4 import W_kq
from improve4b import P_g
from prodanchor import means as SHORT_MEANS

import sys
sys.path.insert(0, "/Users/hun/hatzze/data-pipeline")
from config.indicator_weights import INDICATOR_WEIGHTS as W  # noqa: E402

pd.set_option("display.width", 330)
PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]
mom = ((kospi / kospi.shift(60) - 1) * 100).dropna()

SHORT = list(SHORT_MEANS)
short_contrib = sum(W[s] * SHORT_MEANS[s] for s in SHORT)
short_w = sum(W[s] for s in SHORT)


def pmax(x, d, b=5, f=5):
    i = kospi.index.get_loc(pd.Timestamp(d))
    return x.reindex(kospi.index[max(0, i - b):i + f + 1]).max()


TARGET = [(5, 12), (25, 33), (50, 50), (75, 72), (90, 86), (97, 96)]


def run(name, pmap, wl, target=TARGET, outer=(22.0, 78.0)):
    long_raw = wavg(pmap, wl)
    prod = (long_raw * wl.sum() + short_contrib) / (wl.sum() + short_w)
    core = [(float(np.percentile(prod.dropna(), p)), t) for p, t in target]
    a = [(outer[0], 0)] + core + [(outer[1], 100)]
    s = apply_anchors(prod, a).reindex(kospi.index)
    r = full(name, s)
    r["기간최고"] = "/".join(f"{pmax(s, d):.0f}" for d in PEAKS)
    r["최근"] = round(s.dropna().iloc[-1], 1)
    r["원점수최근"] = round(prod.dropna().iloc[-1], 1)
    r["앵커"] = [round(x, 1) for x, _ in core]
    return r, s, prod


rows = []
# ① 현재 배포 상태
P0 = dict(P_g)
P0["kospi_speed_60d"] = lin(mom, 20.6, 51.3)
r, _, _ = run("① 지금 (속도 floor 20.6)", P0, W_kq.copy().pipe(lambda w: w.set_axis(w.index)) .append(pd.Series({"kospi_speed_60d": 2.5})) if False else pd.concat([W_kq, pd.Series({"kospi_speed_60d": 2.5})]))
rows.append(r)

# ② 속도 floor 를 절대 기준(0%)으로
P1 = dict(P_g)
P1["kospi_speed_60d"] = lin(mom, 0.0, 50.0)
W1 = pd.concat([W_kq, pd.Series({"kospi_speed_60d": 2.5})])
r, _, _ = run("② 속도 floor 0 / ceil 50", P1, W1)
rows.append(r)

# ③ ② + 아시아 floor 되돌림(-10 → -20, ceil 23 → 20)
P2 = dict(P1)
P2["kospi_asia_relative_strength"] = lin(series["kospi_asia_relative_strength"]["raw"], -20.0, 20.0)
r, _, _ = run("③ ②+아시아 floor −20", P2, W1)
rows.append(r)

# ④ ③ + 명품 floor 48 → 42
P3 = dict(P2)
P3["luxury_consumption_index"] = lin(series["luxury_consumption_index"]["raw"], 42.0, 78.0)
r, _, _ = run("④ ③+명품 floor 42", P3, W1)
rows.append(r)

# ⑤ ④ + 코스닥 지표 제거
P4 = {k: v for k, v in P3.items() if k != "kosdaq_kospi_ratio"}
W2 = W1.drop("kosdaq_kospi_ratio")
r, s5, prod5 = run("⑤ ④+코스닥 제거", P4, W2)
rows.append(r)

print("=" * 250)
print("floor 되돌림 + 코스닥 제거 효과")
print(pd.DataFrame(rows).set_index("안")[["기간최고", "고점", "저점", "최근", "원점수최근", "스프", "저온", "상온", "고온", "초고온", "r_gap", "r_dd", "낙폭Q", "단조"]].to_string())

print()
print("=" * 250)
print("⑤ 상태에서 '오늘 30 초반'을 만들려면 앵커 목표를 어떻게 잡아야 하나")
print(f"  오늘 원점수 {prod5.dropna().iloc[-1]:.1f} / 분포 p5={np.percentile(prod5.dropna(),5):.1f} p25={np.percentile(prod5.dropna(),25):.1f} p50={np.percentile(prod5.dropna(),50):.1f}")
for tgt, outer in [
    ([(5, 12), (25, 33), (50, 50), (75, 72), (90, 86), (97, 96)], (22.0, 78.0)),
    ([(5, 22), (25, 38), (50, 52), (75, 72), (90, 86), (97, 96)], (14.0, 82.0)),
    ([(5, 28), (25, 42), (50, 55), (75, 73), (90, 86), (97, 96)], (10.0, 84.0)),
]:
    r, s, _ = run(f"목표 p5→{tgt[0][1]}", P4, W2, target=tgt, outer=outer)
    print(f"  p5→{tgt[0][1]:>2} | 기간최고 {r['기간최고']} | 고점 {r['고점']} | 저점 {r['저점']} | 최근 {r['최근']:5.1f} | 저온 {r['저온']}% 상온 {r['상온']}% 고온 {r['고온']}% 초고온 {r['초고온']}% | 단조 {r['단조']}")
