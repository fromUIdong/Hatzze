"""디시인사이드 한국/미국 주식 마이너 갤러리의 오늘자 게시글 제목으로 커뮤니티 감성 지수를 계산해 Supabase에 upsert.

애초에 사용하던 "주식 갤러리"(neostock, 정갤)는 실제로는 성별 갈등/연애 잡담이
점령한 상태라(2026-07-09 기준 게시글 47건 중 주식 관련 1~2건) 감성 분석 대상으로
부적절하다고 판단해, 실제로 주식 논의가 활발한 마이너 갤러리 2곳으로 교체했다:
- 한국 주식 마이너 갤러리 (id=krstock)
- 미국 주식 마이너 갤러리 (id=stockus)

두 갤러리 모두 /mgallery/board/lists/ 경로를 쓰고, robots.txt(gall.dcinside.com)의
`User-agent: * / Allow: /`에 해당하며 개별 차단 목록(stock_new, stock_new2, rezero
등)에도 포함되어 있지 않아 스크래핑 가능하다.

감성 스코어 = (긍정 게시글 수 - 부정 게시글 수) / 전체 게시글 수 * 100 (-100~100).
두 갤러리의 게시글을 합산한 뒤 계산한다. 분류는 LLM(common/llm_sentiment)이 맡는다 —
예전 키워드 매칭은 제목 2,987건 중 95%가 어느 단어에도 안 걸려 중립 처리됐고("양닉 음전",
"롱숭이 계좌 정밀타격" 같은 갤러리 은어가 사전에 없었다), 지표가 사실상 5% 표본으로
계산되고 있었다. LLM 전환 후 분류율은 6% → 72%다.

--backfill(최근 30일)은 krstock만 대상으로 한다. stockus는 활동량이 너무 많아
(오늘자 게시글만 1,500건을 넘겨도 전날로 못 넘어감) 30일 전체 백필이 비현실적이라,
오늘부터의 값만 매일 누적한다.
"""

from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.details import merge_details, sentiment_details, store_abs_scale_details  # noqa: E402
from common.supabase_client import get_client  # noqa: E402
from common.timeutil import today_kst  # noqa: E402
from common.indicator import ensure_indicator  # noqa: E402
from common.llm_sentiment import LlmUnavailableError, classify_titles  # noqa: E402

GALLERY_IDS = ["krstock", "stockus"]
MGALLERY_LIST_URL = "https://gall.dcinside.com/mgallery/board/lists/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_DELAY_SEC = 1.5
MAX_PAGES = 30  # 무한 순회 방지용 안전장치 (갤러리별)

# stockus(미국 주식 갤러리)는 활동량이 너무 많아(오늘자 1,500건을 넘겨도 전날로
# 못 넘어감) 30일 전체 백필이 비현실적이다. krstock만 30일 백필하고, stockus는
# 오늘부터의 값만 매일 누적해 나간다.
BACKFILL_GALLERY_IDS = ["krstock"]

BACKFILL_DAYS = 30
DAY_BOUNDARY_DELAY_SEC = 4.0  # 하루치 수집이 끝나고 다음 날짜로 넘어갈 때 추가로 쉬는 시간
MAX_BACKFILL_PAGES = 300  # 무한 순회 방지용 안전장치 (갤러리별, 30일치라 페이지 수가 더 많이 필요)
# 갤러리 목록에는 간혹 "개념글"처럼 원래 날짜의 오래된 글이 최신 글 사이에 끼어
# 나오는 경우가 있다(정상적인 시간순 정렬을 깨뜨림). 이런 행 하나만 보고 바로
# 종료하면 실제로는 더 있는 데이터를 놓칠 수 있으므로, 목표 범위보다 오래된 행이
# 연속으로 여러 개 나올 때만 완전히 지난 것으로 판단한다.
OLD_ROW_STREAK_THRESHOLD = 5

# slug는 과거 neostock "게시글 수" 시절과 동일하게 유지해 기존 히스토리와 연결을
# 끊지 않는다. name/description/unit만 감성 지수에 맞게 바꾼다.
INDICATOR_SLUG = "dcinside_post_count"
INDICATOR_META = {
    "slug": INDICATOR_SLUG,
    "name": "디씨 주식 갤러리 감성 지수",
    "headline": "주식 갤러리 글에 드러난 낙관·비관",
    "category": "감성",
    "description_beginner": "낙관적인 얘기만 쏟아지면, 개인 투자 심리가 과열됐다는 신호예요",
    "unit": "pt",
}


def fetch_page(gallery_id: str, page: int) -> BeautifulSoup:
    resp = requests.get(
        MGALLERY_LIST_URL,
        params={"id": gallery_id, "page": page},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def collect_today_titles_for_gallery(gallery_id: str) -> list[str]:
    """오늘자 게시글 제목을 모은다.

    갤러리 목록에는 간혹 "개념글"처럼 다른 날짜의 글이 최신 글 사이에 끼어
    나온다(정상적인 시간순 정렬을 깨뜨림). 이런 행 하나만 보고 바로 종료하면
    실제로는 오늘 글이 훨씬 많이 남아있어도 거기서 멈춰버리므로(krstock에서
    45건 만에 조기 종료된 원인이었다), 오늘이 아닌 행이 연속으로 여러 개
    나올 때만 오늘자 수집이 끝난 것으로 판단한다.
    """
    today_str = today_kst().isoformat()
    titles: list[str] = []
    page = 1
    done = False
    consecutive_old_rows = 0

    while page <= MAX_PAGES and not done:
        soup = fetch_page(gallery_id, page)
        rows = soup.select("table.gall_list tbody tr")
        if not rows:
            break

        for row in rows:
            if row.get("data-type") == "icon_notice":
                continue  # 상단 고정 공지

            date_td = row.select_one("td.gall_date")
            title_attr = date_td.get("title") if date_td else None
            if not title_attr:
                continue  # 설문/광고 등 실제 게시글이 아닌 행 (title 속성 없음)

            post_date = title_attr[:10]  # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DD"

            if post_date != today_str:
                consecutive_old_rows += 1
                if consecutive_old_rows >= OLD_ROW_STREAK_THRESHOLD:
                    done = True
                    break
                continue
            consecutive_old_rows = 0

            title_link = row.select_one("td.gall_tit a:not(.reply_numbox)")
            titles.append(title_link.get_text(strip=True) if title_link else "")

        print(f"[DCInside:{gallery_id}] {page}페이지 조회 완료 (누적 {len(titles)}건)")

        page += 1
        if not done:
            time.sleep(REQUEST_DELAY_SEC)

    return titles


def collect_today_titles() -> list[str]:
    all_titles: list[str] = []
    for gallery_id in GALLERY_IDS:
        all_titles.extend(collect_today_titles_for_gallery(gallery_id))
        time.sleep(REQUEST_DELAY_SEC)
    return all_titles


def compute_sentiment(titles: list[str]) -> dict:
    labels = classify_titles(titles, source="커뮤니티 갤러리", slang=True)
    positive = labels.count("positive")
    negative = labels.count("negative")
    neutral = labels.count("neutral")

    total = len(titles)
    score = (positive - negative) / total * 100 if total else 0.0
    return {
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "total": total,
        "score": score,
    }


def collect_daily_titles_for_gallery(
    gallery_id: str, oldest_missing: str
) -> dict[str, list[str]]:
    day_titles: dict[str, list[str]] = {}
    current_day: str | None = None
    page = 1
    done = False
    consecutive_old_rows = 0

    while page <= MAX_BACKFILL_PAGES and not done:
        soup = fetch_page(gallery_id, page)
        rows = soup.select("table.gall_list tbody tr")
        if not rows:
            break

        for row in rows:
            if row.get("data-type") == "icon_notice":
                continue

            date_td = row.select_one("td.gall_date")
            title_attr = date_td.get("title") if date_td else None
            if not title_attr:
                continue

            post_date = title_attr[:10]

            if post_date < oldest_missing:
                consecutive_old_rows += 1
                if consecutive_old_rows >= OLD_ROW_STREAK_THRESHOLD:
                    done = True
                    break
                continue
            consecutive_old_rows = 0

            if post_date != current_day:
                if current_day is not None:
                    print(
                        f"[DCInside:{gallery_id}] {current_day} 수집 완료: "
                        f"{len(day_titles.get(current_day, []))}건"
                    )
                    time.sleep(DAY_BOUNDARY_DELAY_SEC)
                current_day = post_date

            title_link = row.select_one("td.gall_tit a:not(.reply_numbox)")
            title_text = title_link.get_text(strip=True) if title_link else ""
            day_titles.setdefault(post_date, []).append(title_text)

        print(f"[DCInside:{gallery_id}] {page}페이지 조회 완료")
        page += 1
        if not done:
            time.sleep(REQUEST_DELAY_SEC)

    if current_day is not None:
        print(
            f"[DCInside:{gallery_id}] {current_day} 수집 완료: "
            f"{len(day_titles.get(current_day, []))}건"
        )

    return day_titles


def backfill_daily_sentiment(client, indicator_id: str) -> None:
    """최근 BACKFILL_DAYS일치 감성 스코어를 두 갤러리 합산 기준으로 백필한다.

    이미 저장된 날짜라도 그 날짜의 게시글이 흩어져 있는 페이지 자체는 순서상
    반드시 거쳐가야 하지만(페이지네이션에 날짜 점프 기능이 없음), 이미 저장된
    날짜는 최종 저장 단계에서 제외해 중복 upsert를 하지 않는다.
    """
    today = today_kst()
    target_dates = {
        (today - timedelta(days=offset)).isoformat() for offset in range(BACKFILL_DAYS)
    }

    existing = (
        client.table("indicator_values")
        .select("date")
        .eq("indicator_id", indicator_id)
        .in_("date", list(target_dates))
        .execute()
    )
    existing_dates = {row["date"] for row in existing.data}
    missing_dates = target_dates - existing_dates

    if not missing_dates:
        print(f"[DCInside] 백필할 신규 날짜 없음 (최근 {BACKFILL_DAYS}일 모두 저장됨)")
        return

    oldest_missing = min(missing_dates)
    print(f"[DCInside] 백필 대상 {len(missing_dates)}일 (가장 오래된 날짜: {oldest_missing})")

    combined_titles: dict[str, list[str]] = {}
    for gallery_id in BACKFILL_GALLERY_IDS:
        gallery_titles = collect_daily_titles_for_gallery(gallery_id, oldest_missing)
        for d, titles in gallery_titles.items():
            combined_titles.setdefault(d, []).extend(titles)

    rows_to_save = []
    for d, titles in combined_titles.items():
        if d not in missing_dates:
            continue
        result = compute_sentiment(titles)
        score = round(result["score"], 2)
        rows_to_save.append(
            {"indicator_id": indicator_id, "date": d, "raw_value": score, "details": sentiment_details(result)}
        )
        print(
            f"[DCInside] {d}: 긍정 {result['positive']} / 부정 {result['negative']} / "
            f"중립 {result['neutral']} (전체 {result['total']}) -> {score}pt"
        )

    if rows_to_save:
        client.table("indicator_values").upsert(
            rows_to_save, on_conflict="indicator_id,date"
        ).execute()
    print(f"[DCInside] 백필 완료: {len(rows_to_save)}일치 저장")


def main() -> None:
    client = get_client()
    indicator_id = ensure_indicator(client, INDICATOR_META)
    print(f"[Supabase] indicator '{INDICATOR_SLUG}' id: {indicator_id}")

    if "--backfill" in sys.argv:
        backfill_daily_sentiment(client, indicator_id)
        # 감성 게이지가 '자기 최근 범위 대비'로 마커를 배치할 수 있게 스케일 저장.
        store_abs_scale_details(client, indicator_id)
        return

    titles = collect_today_titles()
    result = compute_sentiment(titles)
    today = today_kst().isoformat()

    print(
        f"[DCInside] 오늘({today}) 감성 분류 — 긍정 {result['positive']}건 / "
        f"부정 {result['negative']}건 / 중립 {result['neutral']}건 "
        f"(전체 {result['total']}건, 갤러리: {', '.join(GALLERY_IDS)})"
    )

    if result["total"]:
        neutral_ratio = result["neutral"] / result["total"] * 100
        if neutral_ratio >= 80:
            print(
                f"[WARNING] 중립 비율이 {neutral_ratio:.1f}%로 매우 높습니다. "
                "config/sentiment_keywords.py의 키워드를 보강하는 걸 권장합니다."
            )

    score = round(result["score"], 2)
    print(f"[DCInside] 감성 스코어: {score}pt")

    # 같은 날 재실행이면 이미 details가 있을 수 있어 병합해서 쓴다(공유 칸).
    client.table("indicator_values").upsert(
        {
            "indicator_id": indicator_id,
            "date": today,
            "raw_value": score,
            "details": merge_details(client, indicator_id, today, sentiment_details(result)),
        },
        on_conflict="indicator_id,date",
    ).execute()
    print(f"[Supabase] indicator_values upsert 완료: date={today}, raw_value={score}")

    # 감성 게이지가 '자기 최근 범위 대비'로 마커를 배치할 수 있게 스케일 저장.
    updated = store_abs_scale_details(client, indicator_id)
    print(f"[Supabase] 감성 스케일 details 저장 완료: {updated}건")


if __name__ == "__main__":
    try:
        main()
    except LlmUnavailableError as e:
        # 분류가 안 되면 그날 값을 쓰지 않는다 — 옛 키워드 방식으로 몰래 되돌아가면
        # 스케일이 다른 값이 시계열에 섞여 더 나쁘다. 워크플로우는 continue-on-error 다.
        print(f"[WARNING] [DCInside] LLM 분류 불가로 오늘 계산을 건너뜁니다: {e}")
