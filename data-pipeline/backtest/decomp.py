"""핵심 날짜 기여 분해 + VKOSPI 정체 확인 + 가중치 최적화."""
import numpy as np
import pandas as pd

from engine import CAPPED, INDICATOR_WEIGHTS, kdf, kospi, series, spearman

pd.set_option("display.width", 260)
LONG = {k: v for k, v in CAPPED.items() if len(v) >= 150}
W = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
MAT = pd.DataFrame(LONG).reindex(kospi.index)

print("=" * 130)
print("A. VKOSPI raw 가 정말 '변동성'인가 — 코스피 레벨과의 관계")
vk = series["vkospi"]["raw"]
j = pd.concat([vk.rename("vkospi"), kospi], axis=1).dropna()
print(f"  vkospi vs 코스피 레벨   Pearson r = {np.corrcoef(j['vkospi'], j['kospi'])[0,1]:+.3f}")
print(f"  vkospi vs 코스피 레벨   Spearman r = {spearman(vk, kospi)[0]:+.3f}")
ret = kospi.pct_change().abs()
print(f"  vkospi vs |일간 등락률| Spearman r = {spearman(vk, ret)[0]:+.3f}  (진짜 변동성지수면 여기가 높아야 함)")
rv = kospi.pct_change().rolling(20).std() * np.sqrt(252) * 100
print(f"  vkospi vs 20일 실현변동성(연율%) Spearman r = {spearman(vk, rv)[0]:+.3f}")
print(f"  vkospi / 코스피 × 1000 분위수: {np.percentile((j['vkospi']/j['kospi']*1000), [0,25,50,75,100]).round(2)}")
print()
print("  실현변동성(연율 %) 월별:")
print(rv.resample("ME").median().round(1).to_string())

print()
print("=" * 130)
print("B. 두 고점의 기여 분해 (weight × progress / weight_sum)")
for d in ["2026-02-26", "2026-06-22", "2026-07-20"]:
    d = pd.Timestamp(d)
    row = MAT.loc[d]
    ok = row.notna()
    contrib = (row.fillna(0) * W) / W[ok].sum()
    t = pd.DataFrame({"progress": row.round(1), "w": W, "기여점수": contrib.round(2)}).sort_values("기여점수", ascending=False)
    print(f"\n--- {d.date()} 코스피 {kospi[d]:.0f} / 종합 {contrib.sum():.1f}")
    print(t.to_string())

print()
print("=" * 130)
print("C. 가중치 최적화 — 목적: 고점에서 높고 저점에서 낮게(스프레드 최대) + 과도한 편중 방지")
BIG_PEAKS = ["2026-02-26", "2026-06-22", "2025-11-03"]
BIG_TROUGHS = ["2026-03-31", "2026-07-20", "2025-11-24"]


def evt_mask(days, back=7):
    m = pd.Series(False, index=kospi.index)
    for d in days:
        d = pd.Timestamp(d)
        i = kospi.index.get_loc(d)
        m.iloc[max(0, i - back): i + 1] = True
    return m


pm, tm = evt_mask(BIG_PEAKS), evt_mask(BIG_TROUGHS)


def eval_w(wv: pd.Series) -> dict:
    num = (MAT.fillna(0) * wv).sum(axis=1)
    den = (MAT.notna() * wv).sum(axis=1)
    s = (num / den).where(den > 0)
    return dict(
        spread=float(s[pm].mean() - s[tm].mean()),
        r_gap=spearman(s, kdf["gap"])[0],
        r_f60=spearman(s, kdf["fwd60"])[0],
        r_dd=spearman(s, kdf["fwd_dd"])[0],
        peak=float(s[pm].mean()),
        trough=float(s[tm].mean()),
        mx=float(s.max()),
        mn=float(s.min()),
    )


print("현재 가중치:", {k: round(v, 2) for k, v in eval_w(W).items()})

# 지표별 단독 스프레드(= 그 지표만 100% 가중)
solo = {}
for slug in LONG:
    s = MAT[slug]
    solo[slug] = dict(
        spread=float(s[pm].mean() - s[tm].mean()),
        r_gap=spearman(s, kdf["gap"])[0],
        r_dd=spearman(s, kdf["fwd_dd"])[0],
        r_f60=spearman(s, kdf["fwd60"])[0],
        w=W[slug],
    )
sdf = pd.DataFrame(solo).T.astype(float).sort_values("spread", ascending=False)
print()
print("D. 지표 단독 성적 (spread=고점창−저점창 평균 progress)")
print(sdf.round(3).to_string())
sdf.to_pickle("solo.pkl")
