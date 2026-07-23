"""④안의 정확한 구성과 전체 백테스트 결과 — 문서용 확정 수치."""
import numpy as np
import pandas as pd

from engine import BUFFETT, CAPPED, DIVERGENCE, HIGH_GAP, INDICATOR_WEIGHTS, kdf, kospi, series, spearman

pd.set_option("display.width", 320)
LONG = [k for k in CAPPED if len(CAPPED[k]) >= 150]
PEAKS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGHS = ["2025-11-24", "2026-03-31", "2026-07-20"]

# ---------------------------------------------------------------- ④ 구성요소
W4 = pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG})
W4.update(pd.Series({
    "kospi_volume_surge": 4.5, "kospi_high_gap": 4.0, "naver_search_trend": 3.5,
    "kospi_asia_relative_strength": 2.0, "leverage_etf_volume": 2.0,
    "upbit_speculation_index": 2.0, "usdkrw_volatility": 1.0, "vkospi": 1.5,
    "kospi_gold_ratio": 1.0, "put_call_ratio": 1.0, "kosdaq_kospi_ratio": 0.5,
}))


def lin(s, f, c):
    return ((s - f) / (c - f) * 100).clip(0, 100)


def raw(slug):
    return series[slug]["raw"].astype(float)


det = series["kospi_volume_surge"]["details"]
surge = pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)
absv = series["kospi_volume_surge"]["raw"]
lvl = pd.Series({d: float((absv.iloc[max(0, i - 250):i] < absv.iloc[i]).mean() * 100)
                 for i, d in enumerate(absv.index) if i >= 60})

P4 = {k: CAPPED[k] for k in LONG}
P4["kospi_high_gap"] = pd.Series(
    {d: (75 + (v + 1.5) / 6.5 * 25) if v >= -1.5 else (v + 35) / 33.5 * 75 for d, v in HIGH_GAP.items()}).clip(0, 100)
P4["naver_search_trend"] = lin(raw("naver_search_trend"), 0, 48)
P4["upbit_speculation_index"] = lin(raw("upbit_speculation_index"), 0, 75)
P4["usdkrw_volatility"] = lin(raw("usdkrw_volatility"), 0.85, 0.20)
P4["leverage_etf_volume"] = lin(raw("leverage_etf_volume"), 38, 74)
P4["kospi_asia_relative_strength"] = lin(raw("kospi_asia_relative_strength"), -10, 23)
P4["fine_dining_search_index"] = lin(raw("fine_dining_search_index"), 18, 48)
P4["luxury_consumption_index"] = lin(raw("luxury_consumption_index"), 48, 78)
P4["kospi_gold_ratio"] = lin(raw("kospi_gold_ratio"), 0.70, 2.2)
P4["kospi_volume_surge"] = (lin(surge, -55, 85).reindex(lvl.index) * 0.7 + lvl * 0.3).dropna()

TARGET = [(5, 12), (25, 33), (50, 50), (75, 68), (90, 82), (97, 93)]


def wavg(pmap, w):
    m = pd.DataFrame({k: pmap[k] for k in w.index if k in pmap}).reindex(kospi.index)
    ww = w[m.columns]
    return ((m.fillna(0) * ww).sum(axis=1) / (m.notna() * ww).sum(axis=1)).where((m.notna() * ww).sum(axis=1) > 0)


def anchors_of(s):
    return [(float(np.percentile(s.dropna(), p)), t) for p, t in TARGET]


def apply_anchors(s, a):
    return pd.Series(np.interp(s, [x for x, _ in a], [y for _, y in a]), index=s.index).where(s.notna())


BASE4 = wavg(P4, W4)
ANCH4 = anchors_of(BASE4)
S4 = apply_anchors(BASE4, ANCH4)


def full(name, s):
    s = pd.Series(s).reindex(kospi.index)
    pk = np.array([s.get(pd.Timestamp(d), np.nan) for d in PEAKS])
    tr = np.array([s.get(pd.Timestamp(d), np.nan) for d in TROUGHS])
    stg = pd.cut(s.dropna(), [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
    j = pd.concat([s.rename("s"), kdf[["fwd20", "fwd60", "fwd_dd"]]], axis=1).dropna()
    j["q"] = pd.qcut(j["s"], 4, labels=list("1234"))
    g = j.groupby("q", observed=True)[["fwd20", "fwd60", "fwd_dd"]].mean() * 100
    dd = g["fwd_dd"].round(1).tolist()
    f60 = g["fwd60"].round(0).tolist()
    return dict(안=name, 고점=f"{pk[0]:.0f}/{pk[1]:.0f}/{pk[2]:.0f}", 저점=f"{tr[0]:.0f}/{tr[1]:.0f}/{tr[2]:.0f}",
                스프=round(pk.mean() - tr.mean(), 1), 중앙=round(s.median(), 1),
                저온=round((stg == "저온").mean() * 100), 상온=round((stg == "상온").mean() * 100),
                고온=round((stg == "고온").mean() * 100), 초고온=round((stg == "초고온").mean() * 100),
                r_gap=round(spearman(s, kdf["gap"])[0], 3), r_dd=round(spearman(s, kdf["fwd_dd"])[0], 3),
                낙폭Q=str(dd), fwd60Q=str(f60),
                단조="O" if all(dd[i] >= dd[i + 1] for i in range(3)) else "-")


print("=" * 240)
print("④안 구성")
print(f"  앵커(원점수→표시): {[(round(x, 1), y) for x, y in ANCH4]}")
print()
print(pd.DataFrame([
    full("① 현행", wavg({k: CAPPED[k] for k in LONG}, pd.Series({k: INDICATOR_WEIGHTS[k] for k in LONG}))),
    full("④ 앵커 적용 전(=③)", BASE4),
    full("④ 최종", S4),
]).set_index("안").to_string())

print()
print("④ 월별")
m = pd.DataFrame({"코스피": kospi, "④": S4}).resample("ME").agg({"코스피": "last", "④": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["④"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print(f"\n  최근값(2026-07-22) {S4.dropna().iloc[-1]:.1f}")

pd.to_pickle({"P4": P4, "W4": W4, "S4": S4, "BASE4": BASE4, "TARGET": TARGET}, "plan4.pkl")
