"""'고점에서 70+'를 만드는 네 가지 방법 비교 — ceiling 하향 / 종합점수 재척도 / 상위-k 집계 / 혼합."""
import numpy as np
import pandas as pd

from engine import BUFFETT, CAPPED, DIVERGENCE, HIGH_GAP, INDICATOR_WEIGHTS, kdf, kospi, series, spearman

pd.set_option("display.width", 300)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]
W_CUR = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
W_REC = W_CUR.copy()
for k, v in {"kospi_volume_surge": 4.5, "kospi_high_gap": 4.0, "naver_search_trend": 3.5,
             "kospi_asia_relative_strength": 2.0, "leverage_etf_volume": 2.0,
             "upbit_speculation_index": 2.0, "usdkrw_volatility": 1.0, "vkospi": 1.5,
             "kospi_gold_ratio": 1.0, "put_call_ratio": 1.0, "kosdaq_kospi_ratio": 0.5}.items():
    W_REC[k] = v


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


CUR_FLOOR = {"kospi_high_gap": -35.0, "kospi_volume_surge": -50.0, "naver_search_trend": 0.0,
             "kospi_gold_ratio": 0.0, "kosdaq_kospi_ratio": -20.0, "leverage_etf_volume": 0.0,
             "buffett_index": 105.0, "kospi_asia_relative_strength": -20.0,
             "luxury_consumption_index": 40.0, "fine_dining_search_index": 0.0,
             "upbit_speculation_index": 0.0, "market_actions_30d": 0.0,
             "small_business_crisis_index": 0.0}
LOWDIR = {"vkospi", "usdkrw_volatility", "put_call_ratio"}


def scaled(pct):
    out = {}
    for slug in LONG:
        r = raw_of(slug)
        if slug in LOWDIR:
            f, c = np.percentile(r, 90), np.percentile(r, 100 - pct)
        else:
            f, c = CUR_FLOOR[slug], np.percentile(r, pct)
        out[slug] = ((r - f) / (c - f) * 100).clip(0, 100)
    return pd.DataFrame(out).reindex(kospi.index)


def wavg(m, w):
    num = (m.fillna(0) * w).sum(axis=1)
    den = (m.notna() * w).sum(axis=1)
    return (num / den).where(den > 0)


def topk(m, w, frac=0.6):
    """상위 frac 비중의 지표만 평균 — '여러 개가 동시에 비명 지르는 것'을 살린다."""
    out = {}
    for d, row in m.iterrows():
        r = row.dropna()
        if r.empty:
            continue
        ww = w[r.index]
        order = r.sort_values(ascending=False)
        cw = ww[order.index].cumsum()
        keep = order[cw <= max(ww.sum() * frac, ww.iloc[0])]
        if keep.empty:
            keep = order.iloc[:1]
        out[d] = float((keep * ww[keep.index]).sum() / ww[keep.index].sum())
    return pd.Series(out)


def stretch(s, lo_p=5, hi_p=95, lo_t=15, hi_t=90):
    """종합점수를 자기 역사 분위수로 재척도 — 순위는 그대로, 눈금만 편다."""
    lo, hi = np.percentile(s.dropna(), [lo_p, hi_p])
    return (lo_t + (s - lo) / (hi - lo) * (hi_t - lo_t)).clip(0, 100)


def rep(name, s):
    s = s.reindex(kospi.index)
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    pk = [s.get(pd.Timestamp(d), np.nan) for d in PEAKS]
    tr = [s.get(pd.Timestamp(d), np.nan) for d in TROUGHS]
    j = pd.concat([s.rename("s"), kdf[["fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    dd = (j.groupby("q", observed=True)["fwd_dd"].mean() * 100).round(1).tolist()
    print(f"{name:30} 중앙 {s.median():5.1f} 범위 {s.min():4.1f}~{s.max():5.1f} | 고점 {pk[0]:.0f}/{pk[1]:.0f}/{pk[2]:.0f} 저점 {tr[0]:.0f}/{tr[1]:.0f}/{tr[2]:.0f} 스프 {np.nanmean(pk)-np.nanmean(tr):5.1f} | "
          f"저온 {(stg=='저온').mean()*100:4.1f}% 고온 {(stg=='고온').mean()*100:4.1f}% 초고온 {(stg=='초고온').mean()*100:4.1f}% | r_gap {spearman(s, kdf['gap'])[0]:+.3f} 낙폭Q {dd}")


cur = pd.DataFrame({k: CAPPED[k] for k in LONG}).reindex(kospi.index)
p90 = scaled(90)
p85 = scaled(85)

print("=" * 210)
print("기준")
rep("① 현행", wavg(cur, W_CUR))
print()
print("A. ceiling 하향만 (Hun 가설)")
rep("  ceiling p90 + 현행 가중", wavg(p90, W_CUR))
rep("  ceiling p90 + 권고 가중", wavg(p90, W_REC))
rep("  ceiling p85 + 권고 가중", wavg(p85, W_REC))
print()
print("B. 종합점수 재척도 (개별 눈금은 그대로, 순위 보존)")
rep("  현행 + 재척도", stretch(wavg(cur, W_CUR)))
rep("  권고가중 + 재척도", stretch(wavg(cur, W_REC)))
print()
print("C. 상위-k 집계 (무상관 평균의 압축을 푼다)")
for f in [0.75, 0.6, 0.5]:
    rep(f"  현행 눈금 top{f:.0%} + 권고가중", topk(cur, W_REC, f))
print()
print("D. 혼합 — ceiling p90 + 권고가중 + 상위 60%")
rep("  p90 + 권고 + top60%", topk(p90, W_REC, 0.6))
rep("  p90 + 권고 + top75%", topk(p90, W_REC, 0.75))
print()
print("E. 혼합 — ceiling p90 + 권고가중 + 재척도")
rep("  p90 + 권고 + 재척도", stretch(wavg(p90, W_REC)))
