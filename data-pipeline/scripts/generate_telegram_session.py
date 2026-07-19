"""텔레그램 StringSession을 1회 발급하는 스크립트 (로컬에서 Hun이 직접 실행).

Telethon은 사람 계정으로 로그인해 채널·채팅방 메시지를 읽는다. 그 로그인 상태
(세션)를 .session 파일이 아니라 '문자열' 형태(StringSession)로 뽑아, 루트
`.env.local`(로컬)과 GitHub secret `TELEGRAM_SESSION`(자동 실행)에 넣어 매일
배치에서 재사용한다.

준비물: my.telegram.org > API development tools 에서 발급받은 api_id / api_hash.
env(TELEGRAM_API_ID / TELEGRAM_API_HASH)에 없으면 실행 중에 직접 입력받는다.

실행:
    cd data-pipeline && source .venv/bin/activate
    python scripts/generate_telegram_session.py

폰으로 온 인증코드(+2단계 인증 비밀번호가 있으면 그것도)를 입력하면 마지막에
세션 문자열이 출력된다. 그 문자열을 루트 `.env.local`의 `TELEGRAM_SESSION=` 에
붙여넣는다.

보안: 이 세션 문자열 = 계정 로그인 권한 그 자체다. 절대 커밋·공유하지 말 것.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.sessions import StringSession  # noqa: E402
from telethon.sync import TelegramClient  # noqa: E402

from common.config import TELEGRAM_API_HASH, TELEGRAM_API_ID  # noqa: E402


def _resolve(name: str, current: str | None) -> str:
    if current:
        return current
    value = input(f"{name} 입력: ").strip()
    if not value:
        print(f"[오류] {name} 이(가) 비어 있습니다.")
        sys.exit(1)
    return value


def main() -> None:
    api_id = _resolve("api_id", TELEGRAM_API_ID)
    api_hash = _resolve("api_hash", TELEGRAM_API_HASH)

    print(
        "\n텔레그램에 로그인합니다. 폰번호(국가코드 포함, 예: +8210xxxxxxxx)와\n"
        "폰으로 온 인증코드를 순서대로 입력하세요. (2단계 인증을 켜뒀다면 비밀번호도)\n"
    )
    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        me = client.get_me()
        session_str = client.session.save()

    print("\n" + "=" * 64)
    print(f"로그인 성공: {me.first_name} (@{me.username}) · id={me.id}")
    print("=" * 64)
    print(
        "\n아래 문자열을 루트 .env.local 의 TELEGRAM_SESSION= 에 그대로 붙여넣으세요."
        "\n(운영 자동 실행용으로는 GitHub secret TELEGRAM_SESSION 에도 동일하게 등록)"
        "\n※ 계정 로그인 권한이므로 절대 커밋·공유 금지\n"
    )
    print(session_str)
    print()


if __name__ == "__main__":
    main()
