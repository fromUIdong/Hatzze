"""④＋＋ 최종안 확정 및 전면 검증."""
import numpy as np
import pandas as pd

from engine import INDICATOR_WEIGHTS, kdf, kospi, series, spearman
from plan4 import apply_anchors, full, lin, wavg
from improve4 import T_HI, W_kq
from improve4b import P_g

pd.set_option("display.width", 330)
PEAK_DAYS = ["2025-11-03", "2026-02-26", "2026-06-22"]
TROUGH_DAYS = ["2025-11-24", "2026-03-31", "2026-07-20"]

mom = ((kospi / kospi.shift(60) - 1) * 100).dropna()
MOM_F, MOM_C = 20.6, 51.3

P = dict(P_g)
P["kospi_speed_60d"] = lin(mom, MOM_F, MOM_C)

W = W_kq.copy()
W["kospi_speed_60d"] = 2.5
# (발목 지표 추가 감량은 11월 고점을 오히려 깎아 채택하지 않음)




def build(pmap, w, smooth=3, target=T_HI, anchor_idx=None):
    b = wavg(pmap, w)
    if smooth:
        b = b.ewm(span=smooth, adjust=False).mean()
    src = b if anchor_idx is None else b.reindex(anchor_idx)
    a = [(float(np.percentile(src.dropna(), p)), t) for p, t in target]
    return apply_anchors(b, a), a


S, ANCH = build(P, W)


def pmax(s, d, back=5, fwd=5):
    i = kospi.index.get_loc(pd.Timestamp(d))
    return s.reindex(kospi.index[max(0, i - back):i + fwd + 1]).max()


print("=" * 200)
print("④＋＋ 최종안")
print(f"  앵커(원점수→표시): {[(round(x, 1), y) for x, y in ANCH]}")
print(f"  상승 속도 지표: 코스피 60거래일 수익률, floor {MOM_F}% / ceiling {MOM_C}%")
print()
prev = {}
from improve4b import P_g as PG
S4p, _ = build(PG, W_kq)
rows = [full("④＋", S4p), full("④＋＋", S)]
for r, s in zip(rows, [S4p, S]):
    r["기간최고±5"] = "/".join(f"{pmax(s, d):.0f}" for d in PEAK_DAYS)
    r["기간최고±10"] = "/".join(f"{pmax(s, d, 10):.0f}" for d in PEAK_DAYS)
print(pd.DataFrame(rows).set_index("안")[["기간최고±5", "기간최고±10", "고점", "저점", "스프", "중앙", "저온", "상온", "고온", "초고온", "r_gap", "r_dd", "낙폭Q", "단조"]].to_string())

print()
print("=" * 200)
print("A. leave-one-out — 고점 하나를 앵커 산출에서 빼도 세 기간 모두 75를 넘나")
for drop in PEAK_DAYS:
    keep = pd.DatetimeIndex([d for d in kospi.index if abs((d - pd.Timestamp(drop)).days) > 45])
    s2, _ = build(P, W, anchor_idx=keep)
    mx = [pmax(s2, d) for d in PEAK_DAYS]
    print(f"  '{drop}' 제외 앵커 → 기간최고 {mx[0]:.0f}/{mx[1]:.0f}/{mx[2]:.0f}   최저 {min(mx):.0f}  {'OK' if min(mx) >= 75 else 'FAIL'}")

print()
print("B. 저점 기간(저점일 ±5)에서 최대치가 너무 높지 않은가")
for d in TROUGH_DAYS:
    i = kospi.index.get_loc(pd.Timestamp(d))
    seg = S.reindex(kospi.index[max(0, i - 5):i + 6]).dropna()
    print(f"  {d} 코스피 {kospi[pd.Timestamp(d)]:.0f} → 기간 최고 {seg.max():5.1f} / 평균 {seg.mean():5.1f} / 최저 {seg.min():5.1f}")

print()
print("=" * 200)
print("C. 월별")
m = pd.DataFrame({"코스피": kospi, "④＋": S4p, "④＋＋": S}).resample("ME").agg(
    {"코스피": "last", "④＋": "mean", "④＋＋": "mean"})
m["전월비%"] = (m["코스피"].pct_change() * 100).round(1)
m["국면"] = pd.cut(m["④＋＋"], [-1, 25, 50, 75, 101], labels=["저온", "상온", "고온", "초고온"])
print(m.round(1).to_string())
print(f"\n  최근값(2026-07-22) {S.dropna().iloc[-1]:.1f}")
print(f"  코스피 7,000+ 중앙 {S[kospi >= 7000].median():.1f} / 전고점 −3% 이내 중앙 {S[kdf['gap'] >= -3].median():.1f}")

print()
print("=" * 200)
print("D. 최종 가중치 (25개 + 신규 1개)")
SHORT = {"investor_deposit": 3.0, "individual_net_buy": 2.5, "dcinside_post_count": 2.0,
         "turnover_concentration": 2.0, "news_sentiment": 1.5, "brokerage_app_rank": 1.5,
         "youtube_finance_search_views": 1.0, "bestseller_finance_ratio": 1.0, "github_trading_bot_repos": 0.5}
full_w = W.copy()
for k, v in SHORT.items():
    full_w[k] = v
cmp = pd.DataFrame({"현행": pd.Series(INDICATOR_WEIGHTS), "④＋＋": full_w})
cmp["변화"] = cmp["④＋＋"] - cmp["현행"].fillna(0)
print(cmp.sort_values("④＋＋", ascending=False).to_string())
print(f"\n  현행 합 {cmp['현행'].sum():.1f} → ④＋＋ 합 {cmp['④＋＋'].sum():.1f}  (장기 {W.sum():.1f} + 단기 {sum(SHORT.values()):.1f})")
