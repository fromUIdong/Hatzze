"""네이버 금융 '투자자별 매매동향(일별)'에서 코스피 개인 순매수를 긁어,
최근 5거래일 누적 개인 순매수(억원)를 froth 지표로 Supabase에 upsert.

froth 논리: 개인(개미)이 순매수로 몰릴수록 = 개미가 고점을 떠받침 = 과열 신호
(개미 순매수는 흔히 고점권의 역발상 신호다 — 외인·기관이 팔 때 개미가 사면 고점 물림).
순매도(음수)는 froth 0으로 바닥 처리(NEGATIVE_CURRENT_CLAMP_SLUGS).

단일일은 하루 등락이 커서(±수만 억) 노이즈라, 그날 포함 직전 5거래일 누적으로 완만히 본다.
소스는 네이버 금융 웹페이지(공식 API 아님) HTML 파싱 — 페이지 구조 변경 리스크가 있다.
KRX Open API엔 투자자별 서비스가 없고, KRX MDC는 세션·해외(러너) 차단 문제가 있어 네이버를 쓴다.
백필은 한 페이지가 주는 최근 ~10거래일 범위에서만(그때부터 매일 누적).
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

NAVER_URL = "https://finance.naver.com/sise/investorDealTrendDay.naver"
SOSOK_KOSPI = "01"
WINDOW = 5  # 최근 5거래일 누적
REQUEST_TIMEOUT_SEC = 15

INDICATOR_SLUG = "individual_net_buy"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "개인 순매수 강도",
    "category": "시장",
    "headline": "개인 투자자의 최근 순매수 흐름",
    "description_beginner": "개인 투자자가 순매수로 몰릴수록, 개미가 시장을 떠받치는 과열 신호일 수 있어요",
    "unit": "억원",
}


def fetch_daily_individual() -> list[tuple[str, float]]:
    """(YYYY-MM-DD, 개인 순매수 억원) 리스트를 최신순으로 반환 (헤더 단위: 억원)."""
    bizdate = date.today().strftime("%Y%m%d")
    resp = requests.get(
        NAVER_URL,
        params={"bizdate": bizdate, "sosok": SOSOK_KOSPI},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/sise/"},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "html.parser")

    out: list[tuple[str, float]] = []
    for tr in soup.select("tr"):
        tds = [td.get_text(strip=True) for td in tr.select("td")]
        if len(tds) < 2:
            continue
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", tds[0])  # 날짜 YY.MM.DD
        if not m:
            continue
        yy, mm, dd = m.groups()
        try:
            individual = float(tds[1].replace(",", ""))  # 개인 = 2번째 컬럼
        except ValueError:
            continue
        out.append((f"20{yy}-{mm}-{dd}", individual))
    return out


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    daily = fetch_daily_individual()  # 최신순
    if len(daily) < WINDOW:
        print(f"[WARNING] 데이터가 {len(daily)}일치뿐이라 {WINDOW}일 누적을 못 만든다. 종료.")
        return
    print(f"[Naver] 개인 순매수 {len(daily)}일치 수집 (최신 {daily[0][0]}={daily[0][1]:+,.0f}억)")

    # 각 날짜 D에 대해 D 포함 직전 5거래일 누적 개인 순매수(억원)
    rows = []
    for i in range(len(daily) - WINDOW + 1):
        d = daily[i][0]
        window = daily[i : i + WINDOW]  # 최신순 (D, D-1, ... D-4)
        cum = sum(v for _, v in window)
        # 카드용: 5일 일별 순매수를 과거→현재 순으로. today = 그날 순매수.
        details = {
            "today": round(window[0][1], 0),
            "daily5": [round(v, 0) for _, v in reversed(window)],
        }
        rows.append((d, cum, details))
    for d, cum, details in rows:
        client.table("indicator_values").upsert(
            {"indicator_id": indicator_id, "date": d, "raw_value": float(cum), "details": details},
            on_conflict="indicator_id,date",
        ).execute()
    print(f"[Supabase] {len(rows)}일치 upsert(최근 5일 누적). 최신={rows[0][0]} {rows[0][1]:+,.0f}억")


if __name__ == "__main__":
    main()
