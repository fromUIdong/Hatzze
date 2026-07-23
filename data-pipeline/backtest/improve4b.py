"""④ 개선 2차 — 괴리 클램프 제거 / VKOSPI 제외 / 조합 확정."""
import numpy as np
import pandas as pd
from datetime import timedelta

from engine import CCSI_PCTILE_ANCHORS, HIGH_GAP, KOSPI_DD_PCTILE_ANCHORS, kdf, kospi, series, spearman
from engine import percentile_from_anchors
from plan4 import P4, S4, TARGET, W4, apply_anchors, full, lin, raw, wavg
from improve4 import P_kq, W_kq, T_HI

pd.set_option("display.width", 320)
rows = [full("④ 기준선", S4)]


def run(name, pmap, w, target=TARGET, smooth=None):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    a = [(float(np.percentile(b.dropna(), p)), t) for p, t in target]
    return full(name, apply_anchors(b, a))


rows.append(run("A. 코스닥 교체", P_kq, W_kq))

# ── G. 실물–증시 괴리: max(0, lead) 클램프 제거 → lead(−100~+100)를 0~100으로
ccsi = series["consumer_sentiment_index"]["raw"]
ccsi = ccsi.reindex(ccsi.index.union(kospi.index)).ffill().reindex(kospi.index)
lead = {}
for d in kospi.index:
    if d in HIGH_GAP.index and not pd.isna(ccsi[d]):
        real = percentile_from_anchors(float(ccsi[d]), CCSI_PCTILE_ANCHORS)
        mkt = percentile_from_anchors(float(HIGH_GAP[d]), KOSPI_DD_PCTILE_ANCHORS)
        lead[d] = mkt - real
lead = pd.Series(lead)
print("괴리 lead 분위수(클램프 전):", np.percentile(lead, [0, 10, 25, 50, 75, 90, 100]).round(1))
print(f"  lead vs 전고점괴리 {spearman(lead, kdf['gap'])[0]:+.3f}  vs 향후낙폭 {spearman(lead, kdf['fwd_dd'])[0]:+.3f}")
P_g = dict(P_kq)
P_g["small_business_crisis_index"] = lin(lead, -75, 45)
rows.append(run("A+G. 괴리 클램프 제거", P_g, W_kq))

# ── F. VKOSPI 제외
W_f = W_kq.copy()
W_f["vkospi"] = 0.0
rows.append(run("A+G+F. VKOSPI 제외", P_g, W_f[W_f > 0]))
W_f2 = W_kq.copy(); W_f2["vkospi"] = 0.5
rows.append(run("A+G. VKOSPI 0.5로", P_g, W_f2))

# ── B. 평활
rows.append(run("A+G +3일 평활", P_g, W_kq, smooth=3))
rows.append(run("A+G +5일 평활", P_g, W_kq, smooth=5))

# ── C. 앵커 상단
rows.append(run("A+G +앵커상단", P_g, W_kq, target=T_HI))
rows.append(run("A+G +앵커상단 +3일 평활", P_g, W_kq, target=T_HI, smooth=3))
rows.append(run("A+G +앵커상단 +5일 평활", P_g, W_kq, target=T_HI, smooth=5))

print()
print("=" * 250)
print(pd.DataFrame(rows).set_index("안").to_string())

# ── 최종 후보 확정
FIN_P, FIN_W = P_g, W_kq
b = wavg(FIN_P, FIN_W).ewm(span=3, adjust=False).mean()
anch = [(float(np.percentile(b.dropna(), p)), t) for p, t in T_HI]
s = apply_anchors(b, anch)
print()
print("=" * 250)
print("④＋ 확정안: 코스닥 교체 + 괴리 클램프 제거 + 3일 평활 + 앵커 상단강화")
print(f"  앵커(원점수→표시): {[(round(x, 1), y) for x, y in anch]}")
m = pd.DataFrame({"코스피": kospi, "점수": s}).resample("ME").agg({"코스피": "last", "점수": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["점수"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print()
for lbl, d in [("고점 2025-11-03", "2025-11-03"), ("저점 2025-11-24", "2025-11-24"),
               ("고점 2026-02-26", "2026-02-26"), ("저점 2026-03-31", "2026-03-31"),
               ("고점 2026-06-22", "2026-06-22"), ("저점 2026-07-20", "2026-07-20")]:
    d = pd.Timestamp(d)
    if d in s.index and not pd.isna(s[d]):
        print(f"    {lbl}  코스피 {kospi[d]:>6.0f} → {s[d]:5.1f}")
print(f"\n  최근값 {s.dropna().iloc[-1]:.1f}")
print(f"  코스피 7,000+ 중앙 {s[kospi >= 7000].median():.1f} / 전고점 −3% 이내 중앙 {s[kdf['gap'] >= -3].median():.1f}")
print()
print(pd.DataFrame([full("④＋ 확정", s)]).set_index("안").to_string())
