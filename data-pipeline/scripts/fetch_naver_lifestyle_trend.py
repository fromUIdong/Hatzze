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

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.naver_client import search_trend  # noqa: E402
from common.details import store_vs_average_details  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402

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
            "headline": "오마카세·파인다이닝 검색량",
            "description_beginner": "오마카세·파인다이닝 검색이 늘면, 여윳돈으로 값비싼 경험 소비에 지갑을 열고 있다는 뜻입니다",
            "unit": "pt",
        },
    },
    {
        "slug": "small_business_crisis_index",
        "group_name": "자영업폐업위기",
        # 가게를 접는 쪽 검색만 모은다 — '창업'·'상권' 같은 진입 검색을 섞으면
        # 위기와 활황이 상쇄돼 신호가 죽는다. 폐업 절차·지원금·자산 처분까지 넓혀
        # 저변을 키웠다(데이터랩은 그룹 합산 후 0~100 정규화, 그룹당 20개까지).
        "keywords": [
            "자영업 폐업",
            "권리금 없음",
            "가게 정리",
            "폐업 세일",
            "폐업",
            "폐업 신고",
            "폐업 지원금",
            "소상공인 대출",
            "가게 양도",
            "점포 정리",
        ],
        "meta": {
            "slug": "small_business_crisis_index",
            # 이 slug 는 '실물–증시 괴리' 지표로 재정의됐다. 여기서 긁는 자영업 폐업 검색은
            # raw_value 로만 남고, 카드에 보이는 두 축과 점수 기여는 calculate_score 의
            # 괴리 override 가 만든다 — 실물축은 한국은행 CCSI, 증시축은 전고점 대비 낙폭이고
            # 둘을 각자 역대 백분위로 바꿔 "누가 더 강한가"를 잰다(2026-07-22 PR #69).
            # **그래서 headline·설명은 자영업이 아니라 CCSI 기준으로 쓴다.** 예전엔 이 META 가
            # 옛 설계(자영업 검색 × 신고가 근접)에 머물러 있어, 손으로 고쳐 둔 운영 DB 문구를
            # ensure_indicator 가 매 실행마다 되돌릴 뻔했다.
            "name": "실물–증시 괴리 지수",
            "category": "감성",
            "headline": "실물 경제와 증시, 누가 더 강한가",
            "description_beginner": "실물 경제(소비심리 CCSI)와 증시(전고점 근접도)를 각자 역대 순위로 견줘 어느 쪽이 더 강한지 봅니다. 증시가 실물을 크게 앞서면 실물 없는 거품을 의심해볼 만한 신호입니다",
            "unit": "pt",
        },
    },
]


def fetch_search_trends() -> list[list[dict]]:
    """GROUP_CONFIGS와 같은 순서로 각 그룹의 일별 데이터 포인트 리스트를 반환."""
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    resp = search_trend(
        {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "timeUnit": "date",
            "keywordGroups": [
                {"groupName": g["group_name"], "keywords": g["keywords"]}
                for g in GROUP_CONFIGS
            ],
        }
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

        # 카드가 'pt' 대신 '평소 대비 N배'를 보여줄 수 있게 30일 평균 대비 배수를
        # details에 채운다.
        updated = store_vs_average_details(client, indicator_id)
        print(f"[Supabase] 평소 대비 배수 details 저장 완료: {updated}건")


if __name__ == "__main__":
    main()
