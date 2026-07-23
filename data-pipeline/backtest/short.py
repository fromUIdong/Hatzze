"""① VKOSPI 대안(변동성 위험프리미엄) ② 단기 히스토리 지표 눈금 권고."""
import numpy as np
import pandas as pd

from engine import CAPPED, INDICATOR_THRESHOLDS, INDICATOR_WEIGHTS, kdf, kospi, series, spearman
from recal import PM, TM

pd.set_option("display.width", 300)

print("=" * 170)
print("A. VKOSPI 대안 — 변동성 위험프리미엄(VKOSPI − 20일 실현변동성). 낮을수록 방심=과열")
vk = series["vkospi"]["raw"]
rv = (kospi.pct_change().rolling(20).std() * np.sqrt(252) * 100)
vrp = (vk - rv).dropna()
print(f"  VRP 분위수 {np.percentile(vrp,[0,10,25,50,75,90,100]).round(1)}")
p20, p88 = np.percentile(vrp, [80, 12])
f = p20 - 0.5 * (p88 - p20)
c = f + 2 * (p88 - p20)
prog = ((vrp - f) / (c - f) * 100).clip(0, 100).reindex(kospi.index)
print(f"  권장 눈금 floor(={f:.1f}) → 과열 0 / ceiling(={c:.1f}) → 과열 100")
for nm, s in [("현행 thr=20 dir=low", (20 / vk * 100).clip(0, 100).reindex(kospi.index)), ("VRP 눈금", prog)]:
    print(f"  {nm:22} 중앙 {s.median():5.1f} 초고온 {(s>=75).mean()*100:4.1f}% | 고점 {s[PM].mean():5.1f} 저점 {s[TM].mean():5.1f} 스프 {s[PM].mean()-s[TM].mean():+6.1f} | r_gap {spearman(s,kdf['gap'])[0]:+.3f} r_dd {spearman(s,kdf['fwd_dd'])[0]:+.3f}")
print("  월별 VRP 중앙값:")
print("   " + vrp.resample("ME").median().round(1).to_string().replace("\n", "\n   "))

print()
print("=" * 170)
print("B. 단기 히스토리 지표 — 관측 분포 대비 현재 임계값 위치와 잠정 권고")
SHORT = ["dcinside_post_count", "news_sentiment", "individual_net_buy", "investor_deposit",
         "turnover_concentration", "brokerage_app_rank", "bestseller_finance_ratio",
         "github_trading_bot_repos", "youtube_finance_search_views"]
for slug in SHORT:
    if slug not in series:
        continue
    r = series[slug]["raw"].astype(float)
    cfg = INDICATOR_THRESHOLDS[slug]
    s = CAPPED[slug]
    q = np.percentile(r, [0, 25, 50, 75, 100])
    p20, p88 = np.percentile(r, [20, 88])
    f = p20 - 0.5 * (p88 - p20)
    c = f + 2 * (p88 - p20)
    print(f"\n  {slug}  (n={len(r)}, w={INDICATOR_WEIGHTS[slug]})")
    print(f"    관측 raw: min {q[0]:.4g} / p25 {q[1]:.4g} / 중앙 {q[2]:.4g} / p75 {q[3]:.4g} / max {q[4]:.4g}")
    print(f"    현재 설정: {cfg}")
    print(f"    현재 과열도: 중앙 {s.median():.1f}, 초고온 {(s>=75).mean()*100:.0f}%, 바닥포화 {(s<=0).mean()*100:.0f}%, 천장포화 {(s>=100).mean()*100:.0f}%")
    print(f"    분포기반 잠정 눈금: floor {f:.4g} → ceiling {c:.4g}")
