"""메시지 단위 분류(telegram_message_analysis)를 날짜·테마·화제어로 집계한다.

  telegram_sentiment_daily : 날짜 × scope('overall' | 테마명) 별 톤 카운트
  telegram_keyword_daily   : 날짜 × 화제어 언급 수

**LLM을 호출하지 않는다.** 화면에 뜨는 수치("긍정 62%", "HBM 128회")는 모델이 지어내는
게 아니라 여기서 센다. 종목추출·테마 로테이션과 같은 철학이고, 덕분에 분류를 다시 하지
않고도 집계 규칙만 바꿔 재계산할 수 있다.

집계 규칙:
- **날짜는 KST 기준**(calculate_stock_daily.py 와 동일). 러너가 UTC라 그냥 쓰면 하루 어긋난다.
- **테마 매핑**: 메시지 → telegram_message_stocks → stocks → config/stock_themes.py.
  테마 로테이션 카드와 같은 사전을 공유해야 두 카드가 어긋나지 않는다.
- **메시지 톤을 그 메시지가 언급한 모든 종목/테마에 동일하게 적용한다.** 한 메시지가 두
  종목을 서로 다른 톤으로 말하는 경우는 v1에서 감수한다 — 종목별로 나누려면 호출이 종목
  수만큼 늘어나는데, 실측상 대부분의 메시지는 단일 종목을 중심으로 쓰인다.
- **화제어 정규화**: 소문자·공백 제거로 버킷을 만들고(HBM/hbm/H B M 이 한 칸에 모임),
  ALIASES 로 표기 흔들림을 통합한 뒤, 일반어·종목명·길이 이상치를 버린다.
  화면 표기는 그 버킷에서 가장 자주 쓰인 실제 표기를 고른다 — 사전에 없는 새 이슈도
  자연스러운 표기로 나온다.

extract/stock_daily/theme_daily 와 마찬가지로 **매 실행 전량 재계산**한다(삭제 후 삽입).

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/calculate_telegram_sentiment.py --dry-run   # 계산·미리보기만
    python scripts/calculate_telegram_sentiment.py             # 저장
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.supabase_client import get_client  # noqa: E402
from common.timeutil import KST  # noqa: E402
from config.issue_keywords import (  # noqa: E402
    ALIASES,
    EXCLUDE,
    MAX_KEYWORD_LEN,
    MIN_KEYWORD_LEN,
)
from config.stock_extraction import ALIASES as STOCK_ALIASES  # noqa: E402
from config.stock_themes import THEMES  # noqa: E402

OVERALL = "overall"

# 정규화 시 지우는 것: 공백·가운뎃점·하이픈·언더스코어.
# "금리 인하" / "금리·인하" / "금리-인하" 가 한 버킷에 모이게 한다.
STRIP_RE = re.compile(r"[\s·\-_]+")


def load_all(db, table: str, columns: str) -> list[dict]:
    rows, start = [], 0
    while True:
        page = db.table(table).select(columns).range(start, start + 999).execute().data
        if not page:
            break
        rows += page
        start += 1000
    return rows


def norm(word: str) -> str:
    """비교용 정규화 키. 표기만 다르고 뜻이 같은 말을 한 버킷에 모은다."""
    return STRIP_RE.sub("", word.strip().lower())


def bucket_of(word: str) -> tuple[str, str | None]:
    """화제어 → (버킷 키, 사전이 정한 대표 표기 or None)."""
    key = norm(word)
    canonical = ALIASES.get(key)
    if canonical:
        return norm(canonical), canonical
    return key, None


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    db = get_client()

    analysis = load_all(
        db, "telegram_message_analysis", "channel_handle,message_id,sentiment,keywords"
    )
    if not analysis:
        print("[경고] telegram_message_analysis 가 비어 있습니다. "
              "먼저 analyze_telegram_messages.py 를 실행하세요.")
        return

    messages = load_all(db, "telegram_messages", "channel_handle,message_id,posted_at")
    date_of = {
        (m["channel_handle"], m["message_id"]): datetime.fromisoformat(m["posted_at"])
        .astimezone(KST)
        .date()
        .isoformat()
        for m in messages
        if m.get("posted_at")
    }

    # 종목 → 테마 (테마 로테이션과 같은 사전). stocks 에 없는 이름은 조용히 건너뛴다.
    stocks = load_all(db, "stocks", "code,name")
    code_of = {s["name"]: s["code"] for s in stocks}
    themes_of_code: dict[str, list[str]] = defaultdict(list)
    for theme, names in THEMES.items():
        for name in names:
            code = code_of.get(name)
            if code:
                themes_of_code[code].append(theme)

    mentions = load_all(db, "telegram_message_stocks", "channel_handle,message_id,stock_code")
    codes_of_msg: dict[tuple[str, int], set[str]] = defaultdict(set)
    for m in mentions:
        codes_of_msg[(m["channel_handle"], m["message_id"])].add(m["stock_code"])

    # 화제어에서 제외할 종목명 집합(정규화 키). 종목은 telegram_message_stocks 가
    # 담당하므로 화제어에 끼면 중복이다. 코스닥이 적재되면 자동으로 따라 늘어난다.
    stock_words = {norm(s["name"]) for s in stocks} | {norm(a) for a in STOCK_ALIASES}

    # ── 집계 ────────────────────────────────────────────────────────────────
    tone: dict[tuple[str, str], Counter] = defaultdict(Counter)  # (date, scope) -> 톤 카운트
    kw_hits: dict[tuple[str, str], int] = defaultdict(int)       # (date, 버킷) -> 횟수
    kw_spellings: dict[str, Counter] = defaultdict(Counter)      # 버킷 -> 실제 표기 빈도
    skipped_no_date = 0

    for a in analysis:
        key = (a["channel_handle"], a["message_id"])
        date = date_of.get(key)
        if not date:
            skipped_no_date += 1
            continue

        sentiment = a["sentiment"]
        tone[(date, OVERALL)][sentiment] += 1

        # 이 메시지가 언급한 종목들이 속한 테마 전부에 같은 톤을 반영(중복 제거).
        msg_themes = {t for code in codes_of_msg.get(key, ()) for t in themes_of_code.get(code, ())}
        for theme in msg_themes:
            tone[(date, theme)][sentiment] += 1

        for word in a.get("keywords") or []:
            b, canonical = bucket_of(word)
            if len(b) < MIN_KEYWORD_LEN or len(b) > MAX_KEYWORD_LEN:
                continue
            if b in EXCLUDE or b in stock_words:
                continue
            kw_hits[(date, b)] += 1
            # 사전이 대표 표기를 정했으면 그걸, 아니면 실제 표기 중 최빈값을 쓴다.
            kw_spellings[b][canonical or word.strip()] += 1

    sentiment_rows = [
        {
            "date": date,
            "scope": scope,
            "positive_count": c["positive"],
            "neutral_count": c["neutral"],
            "negative_count": c["negative"],
            "message_count": sum(c.values()),
        }
        for (date, scope), c in sorted(tone.items())
    ]
    keyword_rows = [
        {
            "date": date,
            "keyword": kw_spellings[b].most_common(1)[0][0],
            "mention_count": n,
        }
        for (date, b), n in sorted(kw_hits.items())
    ]

    # ── 미리보기 ────────────────────────────────────────────────────────────
    dates = sorted({r["date"] for r in sentiment_rows})
    print(f"[집계] 분류 {len(analysis)}건 → 센티먼트 {len(sentiment_rows)}행 · "
          f"키워드 {len(keyword_rows)}행 · 날짜 {len(dates)}일 ({dates[0]} ~ {dates[-1]})")
    if skipped_no_date:
        print(f"[안내] 원본 메시지를 못 찾아 건너뛴 분류 {skipped_no_date}건")

    latest = dates[-1]
    overall = next((r for r in sentiment_rows if r["date"] == latest and r["scope"] == OVERALL), None)
    if overall:
        n = max(1, overall["message_count"])
        print(f"  {latest} 전체 {n}건 → 긍정 {overall['positive_count'] * 100 // n}% · "
              f"중립 {overall['neutral_count'] * 100 // n}% · "
              f"비관 {overall['negative_count'] * 100 // n}%")
    top_theme = sorted(
        (r for r in sentiment_rows if r["date"] == latest and r["scope"] != OVERALL),
        key=lambda r: r["message_count"],
        reverse=True,
    )[:5]
    for r in top_theme:
        n = max(1, r["message_count"])
        print(f"    {r['scope']}: {n}건 · 긍정 {r['positive_count'] * 100 // n}%")

    recent_kw = Counter()
    for r in keyword_rows:
        if r["date"] >= dates[max(0, len(dates) - 7)]:
            recent_kw[r["keyword"]] += r["mention_count"]
    print(f"  최근 화제어 상위: {', '.join(f'{w}({n})' for w, n in recent_kw.most_common(12))}")

    if dry_run:
        print("[dry-run] 저장하지 않고 종료합니다.")
        return

    # ── 저장 (전량 재계산: 삭제 후 삽입) ────────────────────────────────────
    for table, rows in (
        ("telegram_sentiment_daily", sentiment_rows),
        ("telegram_keyword_daily", keyword_rows),
    ):
        # 전량 재계산 — PostgREST는 조건 없는 delete를 막으므로 항상 참인 조건을 준다
        # (calculate_theme_daily.py 와 같은 패턴).
        db.table(table).delete().neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        for i in range(0, len(rows), 500):
            db.table(table).insert(rows[i : i + 500]).execute()
        print(f"[Supabase] {table} {len(rows)}행 저장")


if __name__ == "__main__":
    main()
