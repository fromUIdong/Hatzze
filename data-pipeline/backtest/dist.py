"""지표별 raw_value 실측 분위수 + 현재 눈금이 그 분포 어디에 놓였는지."""
import numpy as np
import pandas as pd

from engine import BUFFETT, DIVERGENCE, HIGH_GAP, INDICATOR_THRESHOLDS, series, CAPPED

pd.set_option("display.width", 260)

Q = [0, 5, 10, 25, 50, 75, 90, 95, 100]


def raw_of(slug):
    if slug == "kospi_high_gap":
        return HIGH_GAP
    if slug == "buffett_index":
        return BUFFETT
    if slug == "small_business_crisis_index":
        return DIVERGENCE
    if slug == "kospi_volume_surge":
        det = series[slug]["details"]
        return pd.Series(
            {d: (v or {}).get("surge_pct") for d, v in det.items()}
        ).dropna().astype(float)
    return series[slug]["raw"] if slug in series else None


print("=" * 200)
print("raw_value 실측 분위수 (kospi_volume_surge는 surge_pct)")
print(f"{'slug':32} {'n':>4} " + " ".join(f"p{q:<7}" for q in Q) + "  현재눈금")
for slug, cfg in INDICATOR_THRESHOLDS.items():
    r = raw_of(slug)
    if r is None or not len(r):
        continue
    qs = np.percentile(r.astype(float), Q)
    scale = "  ".join(f"{v:>8.4g}" for v in qs)
    if "relative_surge" in cfg:
        note = f"floor={cfg['relative_surge']['floor']} ceil={cfg['relative_surge']['ceil']}"
    elif "surge_map" in cfg:
        note = f"surge floor={cfg['surge_map']['floor']} ceil={cfg['surge_map']['ceil']} (기준선=누적평균)"
    else:
        note = f"thr={cfg.get('threshold')}"
        if "floor" in cfg:
            note += f" floor={cfg['floor']}"
        if "kink" in cfg:
            note += f" kink={cfg['kink']}"
        if cfg.get("direction") == "low":
            note += " dir=LOW"
    print(f"{slug:32} {len(r):>4} {scale}   {note}")

print()
print("=" * 200)
print("현재 눈금 하에서 각 progress 분위수가 어디인가")
print(f"{'slug':32} " + " ".join(f"p{q:<5}" for q in Q))
for slug in INDICATOR_THRESHOLDS:
    s = CAPPED.get(slug)
    if s is None or not len(s):
        continue
    qs = np.percentile(s, Q)
    print(f"{slug:32} " + " ".join(f"{v:>6.1f}" for v in qs))
