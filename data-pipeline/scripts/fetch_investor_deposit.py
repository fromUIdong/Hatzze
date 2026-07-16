"""네이버 금융 '투자자예탁금 추이'에서 고객예탁금(대기 매수 자금)을 긁어 froth 지표로 저장.

froth 논리: 고객예탁금 = 증권계좌에 넣어뒀지만 아직 안 산 '대기 매수 현금'. 늘수록
'살 실탄'이 쌓인다 = froth(대기 매수세 유입). 급락장에 매도 후 현금 파킹으로도 늘 수 있어
양면성은 있지만, 통상 대기 매수세(강세 신호)로 해석한다.

예탁금은 수준 자체가 구조적으로 크고 우상향하므로, 절대값 threshold는 금방 낡는다.
그래서 youtube와 동일하게 '최근 평균(cumulative_average) 대비 급증(surge_map)'으로 과열을
본다 — 평균이면 상온(50), 평균보다 크게 늘면 초고온. (누적 평균이라 데이터가 오래 쌓이면
우상향 추세를 뒤늦게 반영하는 한계는 youtube와 동일 — 나중에 롤링 평균으로 개선 여지.)

소스는 네이버 금융 웹페이지(공식 API 아님) HTML 파싱. 한 페이지가 최근 ~한 달치를 준다.
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

NAVER_URL = "https://finance.naver.com/sise/sise_deposit.naver"
REQUEST_TIMEOUT_SEC = 15
WON_EOK_PER_JO = 10_000  # 1조원 = 10,000억원

INDICATOR_SLUG = "investor_deposit"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "투자자예탁금",
    "category": "시장",
    "headline": "살 돈이 쌓일 때",
    "description_beginner": "증권계좌에 대기 중인 매수 자금(예탁금)이 늘수록, 사려는 돈이 몰린다는 신호예요",
    "unit": "억원",
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    return client.table("indicators").insert(INDICATOR_META).execute().data[0]["id"]


def fetch_daily_deposit() -> list[tuple[str, float]]:
    """(YYYY-MM-DD, 고객예탁금 억원) 리스트를 최신순으로 반환 (단위: 억원)."""
    resp = requests.get(
        NAVER_URL,
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
            deposit = float(tds[1].replace(",", ""))  # 고객예탁금 = 2번째 컬럼(억원)
        except ValueError:
            continue
        out.append((f"20{yy}-{mm}-{dd}", deposit))
    return out


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    daily = fetch_daily_deposit()  # 최신순
    if not daily:
        print("[WARNING] 예탁금 데이터를 못 읽었다. 종료.")
        return
    print(f"[Naver] 고객예탁금 {len(daily)}일치 (최신 {daily[0][0]}={daily[0][1]/WON_EOK_PER_JO:.1f}조)")

    # 카드용: 최근 ~15일 예탁금(조)을 과거→현재 순으로 details에 남긴다.
    recent_jo = [round(v / WON_EOK_PER_JO, 1) for _, v in reversed(daily[:15])]
    for i, (d, v) in enumerate(daily):
        details = {"jo": round(v / WON_EOK_PER_JO, 1)}
        if i == 0:
            details["recent_jo"] = recent_jo
        client.table("indicator_values").upsert(
            {"indicator_id": indicator_id, "date": d, "raw_value": float(v), "details": details},
            on_conflict="indicator_id,date",
        ).execute()
    print(f"[Supabase] {len(daily)}일치 upsert. 최신={daily[0][0]} {daily[0][1]:,.0f}억")


if __name__ == "__main__":
    main()
