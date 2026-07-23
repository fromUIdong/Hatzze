"""문서용 최종 표 — 반올림한 권고 눈금으로 재검증."""
import numpy as np
import pandas as pd

from engine import BUFFETT, CAPPED, DIVERGENCE, HIGH_GAP, INDICATOR_THRESHOLDS, INDICATOR_WEIGHTS, kdf, kospi, series, spearman
from recal import PM, TM

pd.set_option("display.width", 300)


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
    return series[slug]["raw"].astype(float)


# 반올림한 권고 눈금 (floor, ceiling). None = 유지
REC = {
    "kospi_high_gap":               ("piecewise", -35, -1.5, 5),
    "kospi_volume_surge":           ("linear", -55, 85),
    "naver_search_trend":           ("linear", 0, 48),
    "vkospi":                       ("keep", None, None),
    "kospi_gold_ratio":             ("linear", 0.70, 2.2),
    "kosdaq_kospi_ratio":           ("keep", None, None),
    "usdkrw_volatility":            ("linear_low", 0.85, 0.20),
    "put_call_ratio":               ("linear_low", 1.30, 0.62),
    "leverage_etf_volume":          ("linear", 38, 74),
    "buffett_index":                ("keep", None, None),
    "kospi_asia_relative_strength": ("linear", -10, 23),
    "luxury_consumption_index":     ("linear", 48, 78),
    "fine_dining_search_index":     ("linear", 18, 48),
    "upbit_speculation_index":      ("linear", 0, 75),
    "market_actions_30d":           ("linear", 0, 0.60),
    "small_business_crisis_index":  ("keep", None, None),
}

rows = []
for slug, spec in REC.items():
    r = raw_of(slug)
    cur = CAPPED[slug]  # 지표 자체 관측일 기준(§2-1과 같은 분모)
    kind = spec[0]
    if kind == "keep":
        new = cur
        note = "유지"
    elif kind == "piecewise":
        _, f, k, c = spec
        new = pd.Series({d: (75 + (v - k) / (c - k) * 25) if v >= k else (v - f) / (k - f) * 75 for d, v in r.items()}).clip(0, 100)
        note = f"floor {f} / kink {k} / ceil {c}"
    else:
        _, f, c = spec
        new = ((r - f) / (c - f) * 100).clip(0, 100)
        note = f"floor {f} → ceil {c}"

    def pack(s):
        s = s.dropna()
        return dict(med=s.median(), hot=(s >= 75).mean() * 100, lo=(s <= 0).mean() * 100,
                    hi=(s >= 100).mean() * 100, sp=0.0, minv=s.min())

    a, b = pack(cur), pack(new)
    rows.append(dict(slug=slug, w=INDICATOR_WEIGHTS[slug], 권고=note,
                     현_중앙=a["med"], 현_초고온=a["hot"], 현_바닥=a["lo"], 현_천장=a["hi"], 현_최소=a["minv"], 현_스프=a["sp"],
                     신_중앙=b["med"], 신_초고온=b["hot"], 신_바닥=b["lo"], 신_천장=b["hi"], 신_최소=b["minv"], 신_스프=b["sp"]))

t = pd.DataFrame(rows).set_index("slug")
print("=" * 250)
print("최종 권고 눈금 검증 (반올림한 숫자로)")
print(t.round(1).to_string())
