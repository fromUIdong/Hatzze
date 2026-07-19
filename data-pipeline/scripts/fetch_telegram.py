"""활성 텔레그램 채널의 최근 N일 메시지를 수집해 Supabase telegram_messages 에 upsert.

- 대상: telegram_channels 에서 is_active=true 인 채널(먼저 sync_telegram_channels.py로
  목록을 맞춰둔다).
- 방식: 채널마다 최신순으로 훑다가 WINDOW_DAYS 보다 오래된 메시지를 만나면 멈춘다.
  이 "최근 N일 창"을 매 실행마다 통째로 다시 upsert하므로, 신규 메시지 수집과
  기존 메시지의 조회수/포워드수 갱신이 동시에 이뤄진다(첫 실행 = N일 백필).
- upsert 키: (channel_handle, message_id). collected_at 은 payload에서 빼 최초
  수집 시각을 보존하고, updated_at 만 매번 현재 시각으로 갱신한다.

DB엔 telegram_messages 테이블이 있어야 한다(migration_009).

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/fetch_telegram.py            # 실제 수집·저장
    python scripts/fetch_telegram.py --dry-run  # 수집만, DB 안 씀
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.sessions import StringSession  # noqa: E402
from telethon.sync import TelegramClient  # noqa: E402

from common.config import (  # noqa: E402
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION,
)
from common.supabase_client import get_client  # noqa: E402
from common.timeutil import KST  # noqa: E402

WINDOW_DAYS = 7  # 매 실행 재수집하는 창(= 첫 실행 백필 범위)
MAX_SCAN_PER_CHANNEL = 2000  # 폭주 채널 안전 상한(보통 창 경계에서 먼저 멈춤)


def load_active_handles(client) -> list[str]:
    resp = (
        client.table("telegram_channels")
        .select("handle")
        .eq("is_active", True)
        .execute()
    )
    return [r["handle"] for r in resp.data]


def collect_channel(tg, handle: str, cutoff: datetime) -> list[dict]:
    """한 채널에서 cutoff 이후 메시지를 [row dict] 로 모은다."""
    entity = tg.get_entity(handle)
    rows: list[dict] = []
    scanned = 0
    for msg in tg.iter_messages(entity, limit=MAX_SCAN_PER_CHANNEL):
        scanned += 1
        if msg.date is None:
            continue
        if msg.date < cutoff:
            break
        rows.append(
            {
                "channel_handle": handle,
                "message_id": msg.id,
                "posted_at": msg.date.astimezone(timezone.utc).isoformat(),
                "views": msg.views,
                "forwards": msg.forwards,
                "replies": msg.replies.replies if msg.replies else None,
                "text": msg.message or None,
                "has_media": msg.media is not None,
                "edited_at": (
                    msg.edit_date.astimezone(timezone.utc).isoformat()
                    if msg.edit_date
                    else None
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]

    if not (TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION):
        print("[오류] TELEGRAM_API_ID/API_HASH/SESSION 이 .env.local 에 없습니다.")
        sys.exit(1)

    db = get_client()
    handles = load_active_handles(db)
    if not handles:
        print("[경고] 활성 채널이 없습니다. 먼저 sync_telegram_channels.py 를 실행하세요.")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    print(
        f"활성 채널 {len(handles)}개 · 최근 {WINDOW_DAYS}일"
        f"(≥ {cutoff.astimezone(KST):%Y-%m-%d %H:%M} KST) 수집"
        + (" · [dry-run]" if dry_run else "")
    )

    total = 0
    with TelegramClient(
        StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH
    ) as tg:
        for handle in handles:
            try:
                rows = collect_channel(tg, handle, cutoff)
            except Exception as exc:  # noqa: BLE001
                print(f"  {handle:<18} 실패: {type(exc).__name__}: {exc}")
                continue

            total += len(rows)
            fwd_max = max((r["forwards"] or 0 for r in rows), default=0)
            view_max = max((r["views"] or 0 for r in rows), default=0)
            print(
                f"  {handle:<18} {len(rows):>3}건 · 최대조회 {view_max:>7,} · 최대포워드 {fwd_max:>4}"
            )

            if not dry_run and rows:
                db.table("telegram_messages").upsert(
                    rows, on_conflict="channel_handle,message_id"
                ).execute()

    if dry_run:
        print(f"\n--dry-run: 총 {total}건 수집(표시만, DB 안 씀).")
    else:
        print(f"\n[Supabase] telegram_messages upsert 완료: 총 {total}건")


if __name__ == "__main__":
    main()
