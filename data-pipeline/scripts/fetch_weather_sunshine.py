"""공공데이터포털의 기상청 ASOS(종관기상관측) 일자료 API로 서울(지점번호 108)의
전운량을 받아와 "맑음지수"(10 - 전운량)로 변환해 Supabase에 저장.

행동경제학의 "Sunshine Effect"(화창한 날 위험자산 선호가 올라간다는 연구)에서
착안한 실험적/재미 지표다 — 다른 12개 시장 지표와 달리 실제 시장 데이터가
아니라 날씨 데이터를 쓴다.

엔드포인트는 apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList이다
(기상청이 직접 운영하는 apihub.kma.go.kr가 아니라 공공데이터포털이 중계하는
버전 — 두 곳의 인증키 포맷이 서로 달라서 실제 호출해 확인했다. KMA_API_KEY는
공공데이터포털 serviceKey다). 응답의 avgTca 필드가 "평균 전운량"(0~10, 낮을수록
맑음)이다.

실제 호출로 확인한 사실:
- API가 "전날 자료까지만 제공"을 명시적으로 강제한다 — endDt에 오늘을 넣으면
  그냥 빈 값이 아니라 에러(code=99)를 반환한다. 그래서 조회 상한(endDt)은
  항상 어제로 잡는다. 그 안에서도 "정확히 어제"라고 하드코딩하지 않고, 응답에
  실제로 존재하는 가장 최근 날짜를 그대로 찾아서 저장한다 — 공휴일 등으로
  어제 자료도 아직 안 올라왔을 가능성에 대비한, 지난 공매도 지표 설계와
  동일한 원칙이다.
- 날짜 범위 조회가 1년치(366일)까지 한 번의 호출로 전부 내려온다(페이지네이션
  불필요할 정도로 충분히 큼) — 그래서 매일 실행 시에도 백필과 최신값 갱신을
  구분하지 않고, 매번 최근 BACKFILL_DAYS일 전체를 다시 조회해 upsert한다
  (indicator_id+date unique라 중복 걱정 없음, KRX처럼 날짜별로 존재 여부를
  미리 조회해 diff를 낼 필요가 없을 만큼 API 호출 자체가 가볍다).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import KMA_API_KEY  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

KMA_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
SEOUL_STATION_ID = "108"
BACKFILL_DAYS = 365
REQUEST_TIMEOUT_SEC = 20
PAGE_SIZE = 400  # 1년치(366일)가 한 페이지에 다 들어오는 걸 확인함

INDICATOR_SLUG = "weather_sunshine_index"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "한국 맑은 날씨 지수",
    "category": "감성",
    "description_beginner": "화창하면 위험한 투자에도 대범해진대요. 믿기지 않으시겠지만 과학적인 데이터랍니다.",
    "unit": "pt",
}


def ensure_indicator(client) -> str:
    existing = (
        client.table("indicators").select("id").eq("slug", INDICATOR_SLUG).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    inserted = client.table("indicators").insert(INDICATOR_META).execute()
    return inserted.data[0]["id"]


def fetch_asos_daily_range(start: date, end: date) -> list[dict]:
    """[start, end] 구간의 서울 지점 일자료를 (date, avg_tca) 리스트로 반환.
    전운량이 비어있는 날(관측 결측 등)은 건너뛴다.
    """
    page_no = 1
    rows: list[dict] = []
    total_count = None

    while total_count is None or len(rows) < total_count:
        resp = requests.get(
            KMA_URL,
            params={
                "serviceKey": KMA_API_KEY,
                "dataCd": "ASOS",
                "dateCd": "DAY",
                "startDt": start.strftime("%Y%m%d"),
                "endDt": end.strftime("%Y%m%d"),
                "stnIds": SEOUL_STATION_ID,
                "dataType": "JSON",
                "numOfRows": str(PAGE_SIZE),
                "pageNo": str(page_no),
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()

        header = data.get("response", {}).get("header", {})
        if header.get("resultCode") != "00":
            raise RuntimeError(
                f"기상청 ASOS API 오류: {header.get('resultMsg')} (code={header.get('resultCode')})"
            )

        body = data["response"]["body"]
        total_count = body.get("totalCount", 0)
        items = body.get("items", {}).get("item", [])
        if not items:
            break

        for item in items:
            avg_tca = item.get("avgTca")
            if avg_tca in (None, ""):
                continue  # 관측 결측일 — 건너뜀
            rows.append({"date": item["tm"], "avg_tca": float(avg_tca)})

        page_no += 1

    return rows


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    today = date.today()
    # ASOS 일자료는 "전날 자료까지"만 제공한다 — endDt에 오늘을 넣으면
    # API가 아예 에러(code=99)를 반환한다. 그래서 조회 상한을 어제로 잡되,
    # latest 계산은 그 안에서 실제로 존재하는 가장 최근 날짜를 그대로 쓴다
    # (공휴일 등으로 어제 자료도 아직 없을 가능성에 대비).
    query_end = today - timedelta(days=1)
    start = today - timedelta(days=BACKFILL_DAYS)
    rows = fetch_asos_daily_range(start, query_end)
    if not rows:
        raise RuntimeError("기상청 ASOS API가 데이터를 반환하지 않았습니다")

    latest = max(rows, key=lambda r: r["date"])
    lag_days = (today - date.fromisoformat(latest["date"])).days
    print(
        f"[KMA] 조회 가능한 가장 최근 날짜: {latest['date']} (오늘 대비 {lag_days}일 지연), "
        f"전운량={latest['avg_tca']}"
    )

    upsert_rows = [
        {
            "indicator_id": indicator_id,
            "date": r["date"],
            "raw_value": round(10 - r["avg_tca"], 2),
        }
        for r in rows
    ]
    client.table("indicator_values").upsert(
        upsert_rows, on_conflict="indicator_id,date"
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: {len(upsert_rows)}건")
    latest_index = round(10 - latest["avg_tca"], 2)
    print(f"[weather_sunshine_index] 가장 최근({latest['date']}) 맑음지수: {latest_index}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] weather_sunshine_index 계산 실패, 건너뜁니다: {e}")
        sys.exit(1)
