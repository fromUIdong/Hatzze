"""앵커 추정 편의 보정 — 단기 9개를 상수로 놓은 탓에 생긴 오차를 실측 한 점으로 맞춘다."""
import numpy as np
import pandas as pd

from engine import kospi
from plan4 import apply_anchors, full
from absolute import PEAKS, TROUGHS, prod

pd.set_option("display.width", 300)
LIVE_RAW = 31.92   # 2026-07-23 파이프라인 실측 원점수
EST_RAW = float(prod.dropna().iloc[-1])
print(f"추정 원점수(2026-07-22) {EST_RAW:.2f} vs 실측(2026-07-23) {LIVE_RAW:.2f} → 편의 {LIVE_RAW - EST_RAW:+.2f}")


def pmax(x, d, b=5, f=5):
    i = kospi.index.get_loc(pd.Timestamp(d))
    return x.reindex(kospi.index[max(0, i - b):i + f + 1]).max()


BASE = [(16, 0), (34, 31), (46, 50), (56, 72), (63, 86), (70, 96), (80, 100)]
rows = []
for sh in (0, -1, -2, -3):
    a = [(x + sh, y) for x, y in BASE]
    s = apply_anchors(prod, a).reindex(kospi.index)
    r = full(f"이동 {sh:+d}", s)
    r["기간최고"] = "/".join(f"{pmax(s, d):.0f}" for d in PEAKS)
    r["오늘(실측원점수)"] = round(float(np.interp(LIVE_RAW, [x for x, _ in a], [y for _, y in a])))
    rows.append(r)
print(pd.DataFrame(rows).set_index("안")[["기간최고", "고점", "저점", "오늘(실측원점수)", "중앙", "저온", "상온", "고온", "초고온", "낙폭Q", "단조"]].to_string())
