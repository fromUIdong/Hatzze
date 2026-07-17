import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

FRED_API_KEY = os.environ.get("FRED_API_KEY")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
KRX_API_KEY = os.environ.get("KRX_API_KEY")
ECOS_API_KEY = os.environ.get("ECOS_API_KEY")
ALADIN_TTB_KEY = os.environ.get("ALADIN_TTB_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
KMA_API_KEY = os.environ.get("KMA_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # 선택 — 없으면 비인증으로 호출(rate limit만 낮음)
# 히어로 카드의 '오늘의 요약'을 Claude로 생성할 때 쓴다(generate_daily_summary.py).
# 없으면 요약 생성을 조용히 건너뛰므로, 나머지 파이프라인엔 영향이 없다.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

# 카더라 리포트 — 텔레그램 Client API(Telethon) 인증값.
# api_id/api_hash는 my.telegram.org에서 발급. TELEGRAM_SESSION은 Hun 계정으로
# 1회 로그인해 만든 StringSession 문자열(= 계정 로그인 권한이라 절대 커밋 금지).
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH")
TELEGRAM_SESSION = os.environ.get("TELEGRAM_SESSION")
