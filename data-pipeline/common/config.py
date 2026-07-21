import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

FRED_API_KEY = os.environ.get("FRED_API_KEY")
# 네이버 클라우드(NAVER API HUB) 키. Application 하나에 뉴스·검색어트렌드를 함께
# 등록해 두 API 를 이 키 하나로 호출한다(common/naver_client.py).
# 구 개발자센터 키(NAVER_CLIENT_ID/SECRET)는 2026-07-22 이관 완료로 제거했다.
NAVER_HUB_KEY_ID = os.environ.get("NAVER_HUB_KEY_ID")
NAVER_HUB_KEY = os.environ.get("NAVER_HUB_KEY")
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
# 분석 대상 채널 목록을 담은 구글시트의 ID(=URL의 /d/<ID>/ 부분). 목록을 public
# 레포에 커밋하지 않으려 URL이 아니라 ID만 env로 받아 sync가 CSV export를 조립한다.
TELEGRAM_CHANNELS_SHEET_ID = os.environ.get("TELEGRAM_CHANNELS_SHEET_ID")
