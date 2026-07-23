"""바깥 앵커(0·100 지점) 선택 — 관측 범위 밖에서 점수가 멈추지 않게 여유를 얼마나 둘까."""
import numpy as np
import pandas as pd

from engine import kospi
from plan4 import apply_anchors, full
from prodanchor import PEAKS, TROUGHS, prod_raw

pd.set_option("display.width", 300)
CORE = [(36.5, 12), (41.7, 33), (46.8, 50), (53.1, 72), (58.7, 86), (66.3, 96)]


def pmax(x, d, b=5, f=5):
    i = kospi.index.get_loc(pd.Timestamp(d))
    return x.reindex(kospi.index[max(0, i - b):i + f + 1]).max()


print(f"원점수 관측 범위: {prod_raw.min():.2f} ~ {prod_raw.max():.2f}")
rows = []
for lo, hi in [(None, None), (24.8, 70.5), (24.0, 74.0), (22.0, 78.0), (20.0, 82.0)]:
    a = CORE if lo is None else [(lo, 0)] + CORE + [(hi, 100)]
    x = apply_anchors(prod_raw, a).reindex(kospi.index)
    r = full(f"{lo}~{hi}", x)
    pk = "/".join(f"{pmax(x, d):.0f}" for d in PEAKS)
    tr = "/".join(f"{x.get(pd.Timestamp(d), float('nan')):.0f}" for d in TROUGHS)
    rows.append(dict(바깥앵커=f"{lo}~{hi}" if lo else "없음(클램프)", 기간최고=pk, 저점=tr,
                     범위=f"{x.min():.1f}~{x.max():.1f}", 저온=r["저온"], 초고온=r["초고온"],
                     단조=r["단조"], 최근=round(x.dropna().iloc[-1], 1)))
print(pd.DataFrame(rows).set_index("바깥앵커").to_string())
