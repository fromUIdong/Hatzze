"""네이버 데이터랩 검색어트렌드 API 한 번 호출로 두 개의 생활소비 지표를 함께
가져와 Supabase indicator_values에 upsert한다.

- 오마카세·파인다이닝 웨이팅 검색 지수(fine_dining_search_index): 경험 소비 과열 신호
- 자영업 폐업·권리금 검색 지수(small_business_crisis_index): 실물경제 위기 신호

데이터랩 API는 한 요청에 keywordGroups를 여러 개 담아 그룹별 결과를 한 번에
돌려준다(그룹 자체는 fetch_naver_luxury_car_trend.py처럼 그룹 내 키워드
검색량을 합산한 0~100 상대지수). 두 지표가 완전히 다른 주제라 그룹은
분리하되, API 호출은 하나로 묶어 쿼터를 아낀다.

fetch_naver_trend.py와 동일하게 조회 기간(1년) 내 모든 날짜별 값을 매 실행마다
upsert한다. 같은 날짜를 다시 upsert해도 값을 덮어쓸 뿐이라 멱등적이며, 별도의
최초/이후 실행 분기가 필요 없다.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  # noqa: E402
from common.supabase_client import get_client  # noqa: E402

NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
LOOKBACK_DAYS = 365

GROUP_CONFIGS = [
    {
        "slug": "fine_dining_search_index",
        "group_name": "파인다이닝웨이팅",
        "keywords": [
            "오마카세 웨이팅", "파인다이닝 예약", "오마카세 예약",
            "파인다이닝 웨이팅", "오마카세", "파인다이닝",
        ],
        "meta": {
            "slug": "fine_dining_search_index",
            "name": "오마카세·파인다이닝 웨이팅 검색 지수",
            "category": "감성",
            "description_beginner": "오마카세·파인다이닝 웨이팅 검색이 늘어나면, 사람들이 여윳돈으로 값비싼 경험 소비에 지갑을 열고 있다는 뜻이에요. 씀씀이가 커질수록 시장 분위기도 들떠 있을 수 있어요",
            "unit": "pt",
        },
    },
    {
        "slug": "small_business_crisis_index",
        "group_name": "자영업폐업위기",
        "keywords": ["자영업 폐업", "권리금 없음", "가게 정리", "폐업 세일", "폐업"],
        "meta": {
            "slug": "small_business_crisis_index",
            "name": "자영업 폐업·권리금 검색 지수",
            "category": "감성",
            "description_beginner": "자영업 폐업·권리금 관련 검색이 늘어나는데 증시만 뜨겁다면, 실물경제와 주식시장 사이의 괴리가 그만큼 벌어지고 있다는 뜻이에요. 화려함 뒤에 숨은 위험한 신호일 수 있어요",
            "unit": "pt",
        },
    },
]


def fetch_search_trends() -> list[list[dict]]:
    """GROUP_CONFIGS와 같은 순서로 각 그룹의 일별 데이터 포인트 리스트를 반환."""
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    resp = requests.post(
        NAVER_DATALAB_URL,
        headers={
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            "Content-Type": "application/json",
        },
        data=json.dumps(
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "timeUnit": "date",
                "keywordGroups": [
                    {"groupName": g["group_name"], "keywords": g["keywords"]}
                    for g in GROUP_CONFIGS
                ],
            }
        ),
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    if len(results) != len(GROUP_CONFIGS):
        raise RuntimeError(
            f"네이버 데이터랩 응답 그룹 수({len(results)})가 요청 그룹 수"
            f"({len(GROUP_CONFIGS)})와 다릅니다"
        )

    data_by_group = []
    for config, result in zip(GROUP_CONFIGS, results):
        data_points = result["data"]
        if not data_points:
            raise RuntimeError(f"'{config['group_name']}' 그룹에 데이터가 없습니다")
        data_by_group.append(data_points)
    return data_by_group


def ensure_indicator(client, meta: dict) -> str:
    slug = meta["slug"]
    existing = client.table("indicators").select("id").eq("slug", slug).execute()
    if existing.data:
        indicator_id = existing.data[0]["id"]
        client.table("indicators").update(
            {k: v for k, v in meta.items() if k != "slug"}
        ).eq("id", indicator_id).execute()
        return indicator_id

    inserted = client.table("indicators").insert(meta).execute()
    return inserted.data[0]["id"]


def upsert_all(client, indicator_id: str, data_points: list[dict]) -> None:
    rows = [
        {
            "indicator_id": indicator_id,
            "date": point["period"],
            "raw_value": float(point["ratio"]),
        }
        for point in data_points
    ]
    client.table("indicator_values").upsert(
        rows, on_conflict="indicator_id,date"
    ).execute()


def main() -> None:
    data_by_group = fetch_search_trends()

    client = get_client()
    for config, data_points in zip(GROUP_CONFIGS, data_by_group):
        latest = data_points[-1]
        print(
            f"[Naver DataLab] '{config['group_name']}'({len(config['keywords'])}개 키워드) "
            f"{len(data_points)}일치 조회 완료 (최신 {latest['period']} 기준: {latest['ratio']})"
        )

        indicator_id = ensure_indicator(client, config["meta"])
        print(f"[Supabase] indicator '{config['slug']}' id: {indicator_id}")

        upsert_all(client, indicator_id, data_points)
        print(f"[Supabase] indicator_values upsert 완료: {len(data_points)}건")


if __name__ == "__main__":
    main()
