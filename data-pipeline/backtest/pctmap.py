"""종합점수를 '역대 백분위 앵커'로 매핑 — 코드에 이미 있는 percentile_from_anchors 패턴 재사용."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, spearman
from lift import PEAKS, TROUGHS, W_CUR, W_REC, scaled, wavg
from recal import newprog

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
cur = pd.DataFrame({k: CAPPED[k] for k in LONG}).reindex(kospi.index)
rec = pd.DataFrame({**{k: CAPPED[k] for k in LONG}, **{k: v for k, v in newprog.items() if k in LONG}}).reindex(kospi.index)

# 표시 목표: 원점수 분위수 → 화면 점수
TARGET = [(5, 12), (25, 33), (50, 50), (75, 68), (90, 82), (97, 93)]


def make_anchors(s):
    """원점수의 실측 분위수와 목표 표시값을 짝지어 앵커 리스트를 만든다."""
    return [(float(np.percentile(s.dropna(), p)), t) for p, t in TARGET]


def apply_anchors(s, anchors):
    xs = [a[0] for a in anchors]
    ys = [a[1] for a in anchors]
    return pd.Series(np.interp(s, xs, ys), index=s.index).where(s.notna())


def rep(name, s, show_anchor=None):
    s = s.reindex(kospi.index)
    pk = np.array([s.get(pd.Timestamp(d), np.nan) for d in PEAKS])
    tr = np.array([s.get(pd.Timestamp(d), np.nan) for d in TROUGHS])
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    j = pd.concat([s.rename("s"), kdf[["fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    dd = (j.groupby("q", observed=True)["fwd_dd"].mean() * 100).round(1).tolist()
    mono = "O" if all(dd[i] >= dd[i + 1] for i in range(3)) else "-"
    ok = "**O**" if (pk >= 70).all() and (tr <= 40).all() else "-"
    print(f"  {name:30} 고점 {pk[0]:4.0f}/{pk[1]:4.0f}/{pk[2]:4.0f} 저점 {tr[0]:4.0f}/{tr[1]:4.0f}/{tr[2]:4.0f} | 중앙 {s.median():5.1f} 최근 {s.dropna().iloc[-1]:5.1f} | "
          f"저온 {(stg=='저온').mean()*100:4.1f}% 상온 {(stg=='상온').mean()*100:4.1f}% 고온 {(stg=='고온').mean()*100:4.1f}% 초고온 {(stg=='초고온').mean()*100:4.1f}% | "
          f"r_gap {spearman(s, kdf['gap'])[0]:+.3f} 단조 {mono} 충족 {ok}")


print("=" * 210)
print("목표 매핑: 원점수 p5→12, p25→33, p50→50, p75→68, p90→82, p97→93 (구간 선형보간)")
print()
cases = {
    "현행 눈금 + 현행 가중치": wavg(cur, W_CUR),
    "현행 눈금 + 권고 가중치": wavg(cur, W_REC),
    "권고 눈금 + 권고 가중치": wavg(rec, W_REC),
    "ceiling p85 + 권고 가중치": wavg(scaled(85), W_REC),
}
best = None
for nm, base in cases.items():
    print(f"[{nm}]")
    rep("  매핑 전", base)
    a = make_anchors(base)
    mapped = apply_anchors(base, a)
    rep("  백분위 앵커 매핑 후", mapped)
    print(f"     앵커: {[(round(x,1), y) for x, y in a]}")
    print()
    if nm == "권고 눈금 + 권고 가중치":
        best = (base, a, mapped)

base, anchors, s = best
print("=" * 210)
print("확정안(권고 눈금 + 권고 가중치 + 백분위 앵커) 월별 서사")
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
print()
print(f"  코스피 8,000+ 인 날 점수 중앙 {s[kospi >= 8000].median():.1f} (n={(kospi>=8000).sum()})")
print(f"  코스피 7,000+ 인 날 점수 중앙 {s[kospi >= 7000].median():.1f} (n={(kospi>=7000).sum()})")
print(f"  전고점 −3% 이내인 날 점수 중앙 {s[kdf['gap'] >= -3].median():.1f} (n={(kdf['gap']>=-3).sum()})")
print(f"  전고점 −15% 이하인 날 점수 중앙 {s[kdf['gap'] <= -15].median():.1f} (n={(kdf['gap']<=-15).sum()})")
