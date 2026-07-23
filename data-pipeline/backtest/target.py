"""요구조건 역산: 고점 3개 모두 ≥70, 저점 3개 모두 ≤35 를 만족하는 조합 찾기."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, spearman
from lift import PEAKS, TROUGHS, W_CUR, W_REC, scaled, stretch, topk, wavg

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
cur = pd.DataFrame({k: CAPPED[k] for k in LONG}).reindex(kospi.index)


def score(name, s):
    s = s.reindex(kospi.index)
    pk = np.array([s.get(pd.Timestamp(d), np.nan) for d in PEAKS])
    tr = np.array([s.get(pd.Timestamp(d), np.nan) for d in TROUGHS])
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    j = pd.concat([s.rename("s"), kdf[["fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    dd = (j.groupby("q", observed=True)["fwd_dd"].mean() * 100).round(1).tolist()
    mono = all(dd[i] >= dd[i + 1] for i in range(3))
    ok = (pk >= 70).all() and (tr <= 35).all()
    return dict(name=name, 고점=f"{pk[0]:.0f}/{pk[1]:.0f}/{pk[2]:.0f}", 저점=f"{tr[0]:.0f}/{tr[1]:.0f}/{tr[2]:.0f}",
                중앙=round(s.median(), 1), 저온=round((stg == "저온").mean() * 100, 1),
                상온=round((stg == "상온").mean() * 100, 1), 고온=round((stg == "고온").mean() * 100, 1),
                초고온=round((stg == "초고온").mean() * 100, 1),
                r_gap=round(spearman(s, kdf["gap"])[0], 3), 낙폭단조="O" if mono else "-",
                낙폭Q4=dd[3], 충족="**O**" if ok else "-")


p90, p85 = scaled(90), scaled(85)
rows = []
rows.append(score("① 현행", wavg(cur, W_CUR)))
rows.append(score("A1 ceiling p90 + 권고W", wavg(p90, W_REC)))
rows.append(score("A2 ceiling p85 + 권고W", wavg(p85, W_REC)))
rows.append(score("B  현행눈금 + 권고W + 재척도", stretch(wavg(cur, W_REC))))
rows.append(score("C  현행눈금 + 권고W + top60", topk(cur, W_REC, 0.6)))
rows.append(score("D  p90 + 권고W + top75", topk(p90, W_REC, 0.75)))
rows.append(score("E  p90 + 권고W + 재척도", stretch(wavg(p90, W_REC))))
rows.append(score("F  현행눈금 + 권고W + top60 + 재척도", stretch(topk(cur, W_REC, 0.6))))
rows.append(score("G  p90 + 권고W + top60 + 재척도", stretch(topk(p90, W_REC, 0.6))))

# 재척도 앵커를 요구조건에 맞춰 직접 조정
for lo_t, hi_t in [(15, 90), (10, 95), (20, 85)]:
    rows.append(score(f"H  현행눈금+권고W+top60+재척도({lo_t}~{hi_t})",
                      stretch(topk(cur, W_REC, 0.6), 5, 95, lo_t, hi_t)))

df = pd.DataFrame(rows).set_index("name")
print("=" * 230)
print("요구조건: 고점 3개 모두 ≥70  AND  저점 3개 모두 ≤35")
print(df.to_string())

print()
print("=" * 230)
print("최종 후보 F 의 월별 추이")
s = stretch(topk(cur, W_REC, 0.6)).reindex(kospi.index)
m = pd.DataFrame({"코스피": kospi, "점수": s}).resample("ME").agg({"코스피": "last", "점수": "mean"})
m["국면"] = pd.cut(m["점수"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print(f"\n  최근값(2026-07-22): {s.dropna().iloc[-1]:.1f}")
