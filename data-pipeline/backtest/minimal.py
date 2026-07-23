"""기계장치를 최소로 쓰면서 요구조건을 만족하는 조합 찾기 + 월별 서사 점검."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, spearman
from lift import PEAKS, TROUGHS, W_CUR, W_REC, scaled, stretch, topk, wavg
from target import score

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
cur = pd.DataFrame({k: CAPPED[k] for k in LONG}).reindex(kospi.index)

cands = {
    "① 현행": wavg(cur, W_CUR),
    "가중치만 (기계장치 0)": wavg(cur, W_REC),
    "ceiling p85 + 권고W (기계장치 0)": wavg(scaled(85), W_REC),
    "ceiling p80 + 권고W (기계장치 0)": wavg(scaled(80), W_REC),
    "권고W + 재척도 (장치 1)": stretch(wavg(cur, W_REC)),
    "ceiling p85 + 권고W + 재척도 (장치 1)": stretch(wavg(scaled(85), W_REC)),
    "ceiling p80 + 권고W + 재척도 (장치 1)": stretch(wavg(scaled(80), W_REC)),
    "권고W + top60 + 재척도 (장치 2)": stretch(topk(cur, W_REC, 0.6)),
    "ceiling p90 + 권고W + top60 + 재척도 (장치 3)": stretch(topk(scaled(90), W_REC, 0.6)),
}
rows = [score(k, v) for k, v in cands.items()]
print("=" * 230)
print("요구조건: 고점 3개 모두 ≥70  AND  저점 3개 모두 ≤35   (기계장치 = 개별 눈금 외에 추가되는 계산 단계 수)")
print(pd.DataFrame(rows).set_index("name").to_string())

print()
print("=" * 230)
print("유력 후보 3개의 월별 서사 — 실제 시장과 말이 되나")
pick = {
    "ceiling p85 + 권고W": wavg(scaled(85), W_REC),
    "ceiling p85 + 권고W + 재척도": stretch(wavg(scaled(85), W_REC)),
    "권고W + top60 + 재척도": stretch(topk(cur, W_REC, 0.6)),
}
out = pd.DataFrame({"코스피": kospi})
for k, v in pick.items():
    out[k] = v.reindex(kospi.index)
m = out.resample("ME").agg({"코스피": "last", **{k: "mean" for k in pick}})
m["코스피 전월비%"] = (m["코스피"].pct_change() * 100).round(1)
print(m.round(1).to_string())
print()
for k, v in pick.items():
    s = v.reindex(kospi.index).dropna()
    print(f"  {k:34} 최근값(07-22) {s.iloc[-1]:5.1f}")
