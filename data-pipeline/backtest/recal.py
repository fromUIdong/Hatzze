"""권장 눈금(floor/ceiling) 산출 + 권장 가중치 + 재조합 검증."""
import numpy as np
import pandas as pd

from engine import (
    BUFFETT,
    CAPPED,
    DIVERGENCE,
    HIGH_GAP,
    INDICATOR_THRESHOLDS,
    INDICATOR_WEIGHTS,
    kdf,
    kospi,
    series,
    spearman,
)

pd.set_option("display.width", 300)

BIG_PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
BIG_TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]


def evt_mask(days, back=7):
    m = pd.Series(False, index=kospi.index)
    for d in days:
        i = kospi.index.get_loc(pd.Timestamp(d))
        m.iloc[max(0, i - back): i + 1] = True
    return m


PM, TM = evt_mask(BIG_PEAKS), evt_mask(BIG_TROUGHS)


def raw_of(slug):
    if slug == "kospi_high_gap":
        return HIGH_GAP
    if slug == "buffett_index":
        return BUFFETT
    if slug == "small_business_crisis_index":
        return DIVERGENCE
    if slug == "kospi_volume_surge":
        det = series[slug]["details"]
        return pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)
    return series[slug]["raw"] if slug in series else None


# ---------------------------------------------------------------- 권장 눈금
# 규칙: p20 → 과열도 25, p88 → 과열도 75 (선형). 이러면 초고온 도달 ≈ 12%,
# 바닥 포화 ≈ 5% 안쪽, 중앙값이 40~60 안에 들어온다. direction=low는 좌우 반전.
def suggest(slug):
    r = raw_of(slug)
    if r is None or len(r) < 100:
        return None
    r = r.astype(float)
    low = INDICATOR_THRESHOLDS[slug].get("direction") == "low"
    p20, p50, p88 = np.percentile(r, [20, 50, 88])
    if low:
        p20, p88 = np.percentile(r, [80, 12])  # 낮을수록 과열
    span = 2 * (p88 - p20)
    if span == 0:
        return None
    f = p20 - 0.5 * (p88 - p20)
    c = f + span
    prog = ((r - f) / (c - f) * 100).clip(0, 100)
    return dict(
        floor=f, ceil=c, med=float(prog.median()),
        hot=float((prog >= 75).mean() * 100),
        cold=float((prog <= 25).mean() * 100),
        sat_lo=float((((r - f) / (c - f) * 100) <= 0).mean() * 100),
        sat_hi=float((((r - f) / (c - f) * 100) >= 100).mean() * 100),
        prog=prog,
    )


rows, newprog = [], {}
for slug in INDICATOR_THRESHOLDS:
    s = CAPPED.get(slug)
    if s is None or len(s) < 100:
        continue
    sg = suggest(slug)
    if sg is None:
        continue
    newprog[slug] = sg["prog"]
    rows.append(dict(
        slug=slug, w=INDICATOR_WEIGHTS[slug],
        cur_med=float(s.median()), cur_hot=float((s >= 75).mean() * 100),
        cur_lo=float((CAPPED[slug] <= 0).mean() * 100), cur_hi=float((CAPPED[slug] >= 100).mean() * 100),
        new_floor=sg["floor"], new_ceil=sg["ceil"],
        new_med=sg["med"], new_hot=sg["hot"], new_lo=sg["sat_lo"], new_hi=sg["sat_hi"],
    ))
rec = pd.DataFrame(rows).set_index("slug")
print("=" * 200)
print("A. 권장 눈금 (p20→25, p88→75 선형). cur_/new_ 는 그 눈금에서의 중앙값·초고온율·바닥포화율·천장포화율")
print(rec.round(2).to_string())
rec.to_pickle("rec.pkl")

# ---------------------------------------------------------------- 조합 비교
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
W_CUR = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})

# 권장 가중치: 동행성·이벤트 스프레드 기반 등급
solo = pd.read_pickle("solo.pkl")
W_NEW = W_CUR.copy()
ADJ = {
    # A: 검증된 froth 온도계 → 유지/상향
    "kospi_high_gap": 4.0,
    "kospi_volume_surge": 4.5,
    "naver_search_trend": 3.5,
    "kospi_asia_relative_strength": 2.0,
    # B: 유효하나 느리거나 약함 → 유지·소폭 조정
    "buffett_index": 2.0,
    "luxury_consumption_index": 0.5,
    "fine_dining_search_index": 0.5,
    "usdkrw_volatility": 1.0,
    "market_actions_30d": 2.0,
    "small_business_crisis_index": 1.5,
    "upbit_speculation_index": 2.0,
    "leverage_etf_volume": 2.0,
    # C: 이번 표본에서 온도계 실패 → 하향
    "vkospi": 1.5,
    "kospi_gold_ratio": 1.0,
    # D: 역방향 → 대폭 하향
    "put_call_ratio": 1.0,
    "kosdaq_kospi_ratio": 0.5,
}
for k, v in ADJ.items():
    if k in W_NEW.index:
        W_NEW[k] = v


def build(progmap, wv):
    mat = pd.DataFrame({k: progmap[k] for k in wv.index if k in progmap}).reindex(kospi.index)
    w = wv[[c for c in mat.columns]]
    num = (mat.fillna(0) * w).sum(axis=1)
    den = (mat.notna() * w).sum(axis=1)
    return (num / den).where(den > 0)


def report(name, s):
    print(f"\n[{name}]")
    print(f"  범위 {s.min():.1f} ~ {s.max():.1f}   중앙 {s.median():.1f}")
    print(f"  고점창 평균 {s[PM].mean():.1f} / 저점창 평균 {s[TM].mean():.1f} → 스프레드 {s[PM].mean()-s[TM].mean():.1f}")
    for d in BIG_PEAKS + BIG_TROUGHS:
        d = pd.Timestamp(d)
        tag = "고점" if d.strftime("%Y-%m-%d") in BIG_PEAKS else "저점"
        if d in s.index and not pd.isna(s[d]):
            print(f"    {tag} {d.date()} 코스피 {kospi[d]:>6.0f} → {s[d]:5.1f}")
    print(f"  vs 전고점괴리 r={spearman(s, kdf['gap'])[0]:+.3f}  vs 향후60일 r={spearman(s, kdf['fwd60'])[0]:+.3f}  vs 향후최대낙폭 r={spearman(s, kdf['fwd_dd'])[0]:+.3f}")
    j = pd.concat([s.rename('s'), kdf[["fwd20", "fwd60", "fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    print("  4분위별 향후 수익률(%):")
    print("   " + (j.groupby("q", observed=True)[["fwd20", "fwd60", "fwd_dd"]].mean() * 100).round(1).to_string().replace("\n", "\n   "))


CUR = {k: CAPPED[k] for k in LONG}
report("현행 눈금 + 현행 가중치", build(CUR, W_CUR))
report("권장 눈금 + 현행 가중치", build({**CUR, **newprog}, W_CUR))
report("현행 눈금 + 권장 가중치", build(CUR, W_NEW))
report("권장 눈금 + 권장 가중치", build({**CUR, **newprog}, W_NEW))

print()
print("=" * 200)
print("B. 권장 가중치 표")
cmpw = pd.DataFrame({"현행": W_CUR, "권장": W_NEW})
cmpw["변화"] = cmpw["권장"] - cmpw["현행"]
cmpw = cmpw.join(solo[["spread", "r_gap", "r_dd"]])
print(cmpw.sort_values("현행", ascending=False).round(3).to_string())
print(f"\n장기 16개 가중치합: 현행 {W_CUR.sum():.1f} → 권장 {W_NEW.sum():.1f}")
