"""가설 검증: 고점에서 지수가 안 올라가는 게 ceiling 탓인가, 구조 탓인가."""
import numpy as np
import pandas as pd

from engine import BUFFETT, CAPPED, DIVERGENCE, HIGH_GAP, INDICATOR_THRESHOLDS, INDICATOR_WEIGHTS, kdf, kospi, series, spearman

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]

print("=" * 150)
print("A. 고점 3일의 지표별 과열도 — '천장에 눌린 것'과 '바닥에 있는 것'을 구분")
mat = pd.DataFrame({k: CAPPED[k] for k in LONG}).reindex(kospi.index)
t = mat.loc[[pd.Timestamp(d) for d in PEAKS]].T
t.columns = ["11/03", "02/26", "06/22"]
t["w"] = [INDICATOR_WEIGHTS[i] for i in t.index]
t["평균"] = t[["11/03", "02/26", "06/22"]].mean(axis=1)
print(t.sort_values("평균", ascending=False).round(1).to_string())

hi = t[t["평균"] >= 90]
lo = t[t["평균"] <= 40]
print(f"\n  고점 평균 90 이상(이미 천장): {list(hi.index)}  가중치 {hi['w'].sum():.1f}")
print(f"  고점 평균 40 이하(바닥권):   {list(lo.index)}  가중치 {lo['w'].sum():.1f}")
print("  → ceiling을 낮춰도 이미 100인 지표는 더 못 오른다. 문제는 바닥권 지표들이다.")

print()
print("=" * 150)
print("B. 구조적 상한 — 지표들이 서로 다른 날 뜨거워지면 가중평균은 원리상 못 오른다")
print(f"  지표 쌍 평균 상관(Spearman): {mat.corr(method='spearman').values[np.triu_indices(len(mat.columns), 1)].mean():+.3f}")
hot_n = (mat >= 75).sum(axis=1)
print(f"  하루에 동시에 초고온인 지표 수: 중앙 {hot_n.median():.0f} / 최대 {hot_n.max():.0f} / 16개 중")
print(f"  각 지표의 '자기 역사 최고치' 평균: {mat.max().mean():.1f}")
print("  각 지표가 자기 최고치를 찍은 날짜(전부 다른 날이면 합산이 안 됨):")
for c in mat.columns:
    print(f"    {c:32} 최고 {mat[c].max():5.1f} @ {mat[c].idxmax().date()}")

print()
print("=" * 150)
print("C. 상한 이론치 — 각 지표가 '그날 자기 값'이 아니라 '자기 역대 최고치'였다면?")
w = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
print(f"  모든 지표가 동시에 자기 최고치 → 가중평균 {(mat.max() * w).sum() / w.sum():.1f}")
print(f"  실제 관측 최고 종합점수 → {((mat.fillna(0) * w).sum(axis=1) / (mat.notna() * w).sum(axis=1)).max():.1f}")

print()
print("=" * 150)
print("D. ceiling을 실측 분위수로 낮추면 고점 판독이 얼마나 오르나")


def raw_of(slug):
    if slug == "kospi_high_gap":
        return HIGH_GAP
    if slug == "buffett_index":
        return BUFFETT
    if slug == "small_business_crisis_index":
        return DIVERGENCE
    if slug == "kospi_volume_surge":
        d = series[slug]["details"]
        return pd.Series({k: (v or {}).get("surge_pct") for k, v in d.items()}).dropna().astype(float)
    return series[slug]["raw"].astype(float)


# 현재 floor 유지 + ceiling만 실측 pXX 로
CUR_FLOOR = {
    "kospi_high_gap": -35.0, "kospi_volume_surge": -50.0, "naver_search_trend": 0.0,
    "vkospi": None, "kospi_gold_ratio": 0.0, "kosdaq_kospi_ratio": -20.0,
    "usdkrw_volatility": None, "put_call_ratio": None, "leverage_etf_volume": 0.0,
    "buffett_index": 105.0, "kospi_asia_relative_strength": -20.0,
    "luxury_consumption_index": 40.0, "fine_dining_search_index": 0.0,
    "upbit_speculation_index": 0.0, "market_actions_30d": 0.0,
    "small_business_crisis_index": 0.0,
}
LOWDIR = {"vkospi", "usdkrw_volatility", "put_call_ratio"}

for pct in [100, 95, 90, 85, 80]:
    newmat = {}
    for slug in LONG:
        r = raw_of(slug)
        f = CUR_FLOOR.get(slug)
        if slug in LOWDIR:
            # 낮을수록 과열: floor=관측 상위, ceiling=하위 (100-pct) 분위
            f = np.percentile(r, 90)
            c = np.percentile(r, 100 - pct)
        elif f is None:
            continue
        else:
            c = np.percentile(r, pct)
        newmat[slug] = ((r - f) / (c - f) * 100).clip(0, 100)
    m = pd.DataFrame(newmat).reindex(kospi.index)
    num = (m.fillna(0) * w).sum(axis=1)
    den = (m.notna() * w).sum(axis=1)
    s = (num / den).where(den > 0)
    pk = [s.get(pd.Timestamp(d), np.nan) for d in PEAKS]
    tr = [s.get(pd.Timestamp(d), np.nan) for d in TROUGHS]
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    print(f"  ceiling = 실측 p{pct:<3} | 중앙 {s.median():5.1f} 최대 {s.max():5.1f} | 고점 {pk[0]:.0f}/{pk[1]:.0f}/{pk[2]:.0f} 저점 {tr[0]:.0f}/{tr[1]:.0f}/{tr[2]:.0f} | 초고온 {(stg=='초고온').mean()*100:4.1f}% 저온 {(stg=='저온').mean()*100:4.1f}% | r_gap {spearman(s, kdf['gap'])[0]:+.3f}")
