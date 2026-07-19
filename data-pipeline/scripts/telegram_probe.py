"""텔레그램 수집 스모크 테스트 — 채널/채팅방 최근 메시지를 읽어 필드를 출력한다.

DB에 아무것도 쓰지 않는다. 목적은 세 가지:
1. Telethon 세션으로 실제 연결·조회가 되는지 확인
2. 조회수(views)·포워드수(forwards)·본문·작성시각 필드가 실제로 잡히는지 눈으로 확인
   (특히 포워드수는 웹 프리뷰엔 없고 Client API에만 있어서, 여기서 검증한다)
3. 하루 메시지 볼륨을 가늠(감성 LLM 비용/설계 판단용)

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/telegram_probe.py FastStockNews          # 최근 20건
    python scripts/telegram_probe.py FastStockNews 50       # 최근 50건
    python scripts/telegram_probe.py https://t.me/이지스리서치방  # 초대링크/그룹도 가능(가입돼 있어야 함)

채팅방(그룹)은 그 계정이 멤버여야 읽힌다. 채널은 공개면 가입 없이도 읽을 수 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.sessions import StringSession  # noqa: E402
from telethon.sync import TelegramClient  # noqa: E402

from common.config import (  # noqa: E402
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION,
)
from common.timeutil import KST  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python scripts/telegram_probe.py <채널핸들|링크> [건수]")
        sys.exit(1)
    if not TELEGRAM_SESSION:
        print(
            "[오류] TELEGRAM_SESSION 이 없습니다. 먼저 아래로 세션을 발급하세요:\n"
            "  python scripts/generate_telegram_session.py"
        )
        sys.exit(1)
    if not (TELEGRAM_API_ID and TELEGRAM_API_HASH):
        print("[오류] TELEGRAM_API_ID / TELEGRAM_API_HASH 가 .env.local 에 없습니다.")
        sys.exit(1)

    target = sys.argv[1].strip()
    if target.startswith("@"):
        target = target[1:]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    with TelegramClient(
        StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH
    ) as client:
        entity = client.get_entity(target)
        title = getattr(entity, "title", None) or target
        subs = getattr(entity, "participants_count", None)
        subs_str = f" · 구독/멤버 {subs:,}" if subs else ""
        print(f"\n=== {title}{subs_str} — 최근 {limit}건 ===")
        print("     [id] 날짜(KST)   | 👁조회 ↗포워드 | 본문\n")

        seen = 0
        for msg in client.iter_messages(entity, limit=limit):
            seen += 1
            when = (
                msg.date.astimezone(KST).strftime("%m-%d %H:%M") if msg.date else "--"
            )
            views = f"{msg.views:,}" if msg.views is not None else "-"
            fwds = f"{msg.forwards:,}" if msg.forwards is not None else "-"
            text = (msg.message or "").replace("\n", " ").strip()
            if not text:
                text = "(미디어/텍스트 없음)"
            if len(text) > 64:
                text = text[:64] + "…"
            print(f"[{msg.id}] {when} | 👁{views} ↗{fwds} | {text}")

        print(f"\n조회 완료: {seen}건")


if __name__ == "__main__":
    main()
