"""상대창 맹점(거래대금)·역방향 지표(풋콜/코스닥/금) 원인 규명."""
import numpy as np
import pandas as pd

from engine import CAPPED, kdf, kospi, series, spearman

pd.set_option("display.width", 260)

print("=" * 130)
print("A. 거래대금 — 절대 수준 vs 30일 상대(surge_pct)")
det = series["kospi_volume_surge"]["details"]
absv = series["kospi_volume_surge"]["raw"]  # 억원
surge = pd.Series({d: (v or {}).get("surge_pct") for d, v in det.items()}).dropna().astype(float)
avg30 = pd.Series({d: (v or {}).get("avg_30d") for d, v in det.items()}).dropna().astype(float)
t = pd.DataFrame({"거래대금_조": absv / 10000, "30일평균_조": avg30 / 10000, "surge%": surge, "kospi": kospi}).dropna()
print(t.resample("ME").agg({"거래대금_조": "median", "30일평균_조": "median", "surge%": "median", "kospi": "last"}).round(1).to_string())
print(f"\n  절대 거래대금 vs 코스피 Spearman = {spearman(absv, kospi)[0]:+.3f}")
print(f"  surge%(30일상대) vs 코스피 Spearman = {spearman(surge, kospi)[0]:+.3f}")
print(f"  절대 거래대금 vs 전고점괴리 Spearman = {spearman(absv, kdf['gap'])[0]:+.3f}")
print(f"  surge% vs 전고점괴리 Spearman = {spearman(surge, kdf['gap'])[0]:+.3f}")

print()
print("=" * 130)
print("B. 풋/콜 비율 raw — 고점/저점 구간")
pc = series["put_call_ratio"]["raw"]
print(pc.resample("ME").agg(["min", "median", "max"]).round(3).to_string())
print(f"\n  put_call raw vs 전고점괴리 Spearman = {spearman(pc, kdf['gap'])[0]:+.3f}  (froth면 −여야 콜쏠림=고점)")
print(f"  put_call raw vs 코스피 20일 수익률 Spearman = {spearman(pc, kdf['bwd20'])[0]:+.3f}")

print()
print("=" * 130)
print("C. 코스닥 상대강도(20일 초과수익) raw")
kq = series["kosdaq_kospi_ratio"]["raw"]
print(kq.resample("ME").median().round(2).to_string())
print(f"  vs 전고점괴리 Spearman = {spearman(kq, kdf['gap'])[0]:+.3f}")
print(f"  vs 코스피 20일수익률 Spearman = {spearman(kq, kdf['bwd20'])[0]:+.3f}")

print()
print("=" * 130)
print("D. 금 대비 코스피 raw")
gr = series["kospi_gold_ratio"]["raw"]
print(gr.resample("ME").median().round(3).to_string())

print()
print("=" * 130)
print("E. 초보검색·업비트 — 절대 수준이 정말 안 올랐나")
for slug in ["naver_search_trend", "upbit_speculation_index", "luxury_consumption_index", "fine_dining_search_index", "market_actions_30d"]:
    s = series[slug]["raw"]
    print(f"\n{slug}")
    print(s.resample("ME").median().round(2).to_string())
