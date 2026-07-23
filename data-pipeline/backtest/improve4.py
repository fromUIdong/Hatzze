"""④안을 더 개선할 방법들을 하나씩 붙여 보고 실제로 좋아지는지 측정."""
import numpy as np
import pandas as pd
from datetime import timedelta

from engine import CAPPED, kdf, kospi, series, spearman
from plan4 import ANCH4, BASE4, P4, S4, TARGET, W4, anchors_of, apply_anchors, full, lin, raw, wavg

pd.set_option("display.width", 320)
LONG = list(P4)
rows = [full("④ 기준선", S4)]


def run(name, pmap, w, target=TARGET, smooth=None):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    a = [(float(np.percentile(b.dropna(), p)), t) for p, t in target]
    return full(name, apply_anchors(b, a))


# ── 개선 1. 코스닥: '코스피 대비 상대'를 버리고 '코스닥 자체 전고점 괴리'로 교체
kq = series["kosdaq_close_raw"]["raw"].astype(float)
kq_gap = {}
for d in kq.index:
    w_ = kq[(kq.index >= d - timedelta(days=365)) & (kq.index < d)]
    if len(w_) >= 20:
        kq_gap[d] = (kq[d] - w_.max()) / w_.max() * 100
kq_gap = pd.Series(kq_gap)
print("코스닥 자체 전고점 괴리 분위수:", np.percentile(kq_gap, [0, 25, 50, 75, 100]).round(1))
print(f"  vs 코스피 전고점괴리 Spearman {spearman(kq_gap, kdf['gap'])[0]:+.3f}  (froth면 +)")
print(f"  vs 향후 최대낙폭 Spearman {spearman(kq_gap, kdf['fwd_dd'])[0]:+.3f}")

P_kq = dict(P4)
P_kq["kosdaq_kospi_ratio"] = lin(kq_gap, -35, 3)
W_kq = W4.copy()
W_kq["kosdaq_kospi_ratio"] = 2.0
rows.append(run("＋코스닥을 자체 전고점괴리로", P_kq, W_kq))

# ── 개선 2. 풋/콜 방향 뒤집기 (실측이 역방향이므로)
pc = raw("put_call_ratio")
P_pc = dict(P_kq)
P_pc["put_call_ratio"] = lin(pc, 0.62, 1.30)
rows.append(run("＋풋콜 방향 반전", P_pc, W_kq))

# ── 개선 3. 평활
for sp in (3, 5, 10):
    rows.append(run(f"＋{sp}일 평활", P_kq, W_kq, smooth=sp))

# ── 개선 4. 앵커 목표를 위로
T_HI = [(5, 12), (25, 33), (50, 50), (75, 72), (90, 86), (97, 96)]
rows.append(run("＋앵커 상단 강화", P_kq, W_kq, target=T_HI))
rows.append(run("＋앵커 상단 강화 + 5일 평활", P_kq, W_kq, target=T_HI, smooth=5))

# ── 개선 5. 가중치 좌표하강
PM = pd.Series(False, index=kospi.index)
TM = pd.Series(False, index=kospi.index)
for d in ["2025-11-03", "2026-02-26", "2026-06-22"]:
    i = kospi.index.get_loc(pd.Timestamp(d)); PM.iloc[max(0, i - 7):i + 1] = True
for d in ["2025-11-24", "2026-03-31", "2026-07-20"]:
    i = kospi.index.get_loc(pd.Timestamp(d)); TM.iloc[max(0, i - 7):i + 1] = True


def obj(w):
    b = wavg(P_kq, w)
    if b.dropna().std() == 0:
        return -9e9
    spread = b[PM].mean() - b[TM].mean()
    r_dd = spearman(b, kdf["fwd_dd"])[0]
    return spread - 15 * max(0.0, r_dd)


best_w = W_kq.copy()
best = obj(best_w)
for _ in range(6):
    for k in best_w.index:
        for cand in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
            t = best_w.copy(); t[k] = cand
            v = obj(t)
            if v > best + 1e-9:
                best, best_w = v, t
rows.append(run("＋가중치 좌표하강 최적화", P_kq, best_w))
rows.append(run("＋최적화 + 5일 평활", P_kq, best_w, smooth=5))

print()
print("=" * 250)
print("개선안 비교 — 각 행은 ④에 해당 변경을 얹은 결과(코스닥 교체는 이후 행에 누적)")
print(pd.DataFrame(rows).set_index("안").to_string())

print()
print("=" * 250)
print("좌표하강이 찾은 가중치 vs ④")
cw = pd.DataFrame({"④": W_kq, "최적화": best_w})
cw["변화"] = cw["최적화"] - cw["④"]
print(cw.sort_values("④", ascending=False).round(2).to_string())
print(f"  합계 {W_kq.sum():.1f} → {best_w.sum():.1f}")
pd.to_pickle({"P_kq": P_kq, "W_kq": W_kq, "best_w": best_w, "T_HI": T_HI}, "improve4.pkl")
