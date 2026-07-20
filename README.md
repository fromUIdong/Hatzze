# 🌡️ Hatzze — 코스피 과열도 지수

**데이터와 감성으로 읽는 시장.** 시장·감성 지표 **26개**를 매일 종합해, 지금 코스피가 얼마나 달아올랐는지를 하나의 **온도(℃)**로 보여주는 대시보드입니다.

🔗 **[hatzze.fun](https://hatzze.fun)**

> ⚠️ 햇쩨 지수와 저온·상온·고온·초고온 구간은 시장의 **과열 정도**를 나타낸 표현일 뿐, **재미·참고용이며 매수·매도 신호가 아닙니다.**

---

## 무엇을 보여주나요

**햇쩨 지수** — 26개 지표의 과열도를 가중 평균해 `0~100`을 시장 온도 `℃`로 표시합니다.

| 구간 | 점수 | 의미 |
|---|---|---|
| ❄️ 저온 | `0–24` | 시장이 차분·위축 |
| 🌡️ 상온 | `25–49` | 평범 |
| 🔥 고온 | `50–74` | 달아오르는 중 |
| 🌋 초고온 | `75–100` | 과열 |

그 밖에:

- **오늘의 요약** — 매일 그날의 데이터를 **Claude(Haiku)**가 3문단으로 브리핑합니다. (① 기준선을 넘은 지표 수 + 현재 구간 ② 오늘 가장 뜨거운 지표와 그 의미 ③ 최근 며칠 추세)
- **지표 카드 26장** — 지표별 과열도·실제 값·30일 추이·인포그래픽.
- **상단 시세 티커** — 코스피·코스닥·주요 종목·환율·비트코인 (10분 갱신).

---

## 아키텍처

```mermaid
flowchart LR
    A["24개 fetch 스크립트<br/>KRX · ECOS · 네이버 · 유튜브 · GitHub …"] --> B["calculate_score.py<br/>26개 지표 → 과열도 가중평균"]
    B --> C["generate_daily_summary.py<br/>Claude Haiku · 오늘의 요약"]
    C --> D[("Supabase<br/>PostgreSQL")]
    D --> E["Next.js 프론트엔드<br/>Vercel · hatzze.fun"]
    G["GitHub Actions<br/>매일 09:00 · 17:00 KST"] -.->|트리거| A
```

**파이프라인이 계산하고, 프론트는 읽기만 합니다.** 지표 수집·점수 계산·요약 생성은 GitHub Actions가 하루 2회(오전 9시 주 실행 + 오후 5시 실패 만회) 돌려 Supabase에 저장하고, Next.js는 매 요청마다 Supabase에서 최신 값을 읽어 렌더합니다.

### 서버 함수는 서울(icn1)에서 돈다

`vercel.json`의 `regions: ["icn1"]`은 성능상 필수입니다 — 지우지 마세요.

Vercel 함수는 기본값이 `iad1`(미국 버지니아)인데, Supabase는 `ap-northeast-2`(서울)에 있습니다. 기본값을 두면 렌더 중 쿼리 한 번마다 태평양을 왕복해 **쿼리당 ~200ms**가 붙습니다. `/telegram`은 쿼리가 24개라 이것만으로 몇 초가 됐습니다(수정 전 TTFB 2.9~5.4초).

`icn1`은 Supabase와 같은 리전이라 왕복이 한 자릿수 ms로 떨어집니다. Hobby 플랜도 **리전 개수만 1개 제한**이고 어느 리전을 고르는지는 자유입니다. 참고로 Yahoo Finance 등 미국 API 호출은 조금 느려지지만, `revalidate` 캐시가 걸려 있고 호출 수도 적어 영향이 작습니다.

---

## 폴더 구조

```
hatzze/
├─ app/                     # Next.js(App Router) 프론트엔드
│  ├─ page.tsx              #   메인 대시보드(히어로 지수 + 지표 카드)
│  ├─ AppShell.tsx          #   상단 티커·네비·다크모드 셸
│  └─ api/ticker/           #   실시간 시세 티커 API
├─ lib/                     # Supabase 조회·포맷 유틸(server-only)
├─ data-pipeline/           # Python 배치 파이프라인
│  ├─ scripts/              #   지표별 fetch_*.py + calculate_score.py + generate_daily_summary.py
│  ├─ config/               #   지표 임계값·가중치 설정
│  └─ common/               #   Supabase 클라이언트·공용 유틸
├─ supabase/                # 스키마 + 마이그레이션 SQL
└─ .github/workflows/       # daily-update.yml (일일 자동 실행)
```

---

## 지표 (26개)

<details>
<summary><b>시장 지표 (15개)</b> — 가격·수급·변동성 등 시장 데이터</summary>

- 코스피 신고가 대비 괴리율
- 버핏지수 (시가총액 / GDP)
- 코스피 거래대금 급증도
- VKOSPI (변동성지수)
- 금 대비 코스피 상대강도
- 원/달러 환율 변동성
- 코스피 대비 코스닥 상대강도
- 레버리지 ETF·선물 미결제약정 종합 지수
- 아시아 3국(일본·홍콩·대만) 대비 코스피 상대강도
- 최근 한 달 매매 안전장치 동향 (사이드카·서킷브레이커)
- VIX 대비 VKOSPI 스프레드
- 개인 순매수 강도
- 옵션 풋/콜 비율
- 투자자예탁금
- 거래대금 쏠림도 (상위10 종목 비중)

</details>

<details>
<summary><b>감성 지표 (11개)</b> — 검색·커뮤니티·소비 등 대중 심리</summary>

- 주식 초보 검색량 지수
- 디씨 주식 갤러리 감성 지수
- 경제뉴스 헤드라인 감성 지수
- 경제·재테크 도서 베스트셀러 비중
- 재테크 유튜브 검색 콘텐츠 조회수
- 명품·수입차 소비 검색 지수
- 오마카세·파인다이닝 웨이팅 검색 지수
- 실물–증시 괴리 지수
- 업비트 투기 과열 지수
- 깃헙 트레이딩봇 저장소 생성 수
- 증권 앱 인기차트 순위

</details>

---

## 기술 스택

| | |
|---|---|
| **프론트엔드** | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · Pretendard |
| **데이터 파이프라인** | Python 3.11 · Supabase Python SDK · Anthropic SDK (Claude Haiku) |
| **데이터베이스** | Supabase (PostgreSQL, RLS) |
| **자동화·배포** | GitHub Actions (일일 배치) · Vercel (프론트) |

---

## 로컬 개발

### 프론트엔드

```bash
npm install
npm run dev          # http://localhost:3000
```

### 데이터 파이프라인

```bash
cd data-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/calculate_score.py          # 지표 종합 점수 계산
python scripts/generate_daily_summary.py   # 오늘의 요약 생성
```

---

## 환경변수

`.env.example`을 복사해 `.env.local`에 키를 채웁니다.

```bash
cp .env.example .env.local
```

| 변수 | 용도 |
|---|---|
| `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` | 프론트엔드 읽기용 |
| `SUPABASE_SECRET_KEY` | 파이프라인 쓰기용 |
| `KRX_API_KEY` | 코스피 시세·신고가·시총·VKOSPI 등 |
| `ECOS_API_KEY` | 한국은행 GDP (버핏지수) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 데이터랩·종목토론방 |
| `YOUTUBE_API_KEY` | 유튜브 재테크 콘텐츠 |
| `ALADIN_TTB_KEY` | 알라딘 베스트셀러 |
| `ANTHROPIC_API_KEY` | 오늘의 요약(Claude Haiku) |
| `GITHUB_TOKEN` | 깃헙 검색 API (선택 — 없으면 비인증) |

---

## 자동화 (GitHub Actions)

`.github/workflows/daily-update.yml`이 매일 두 번 파이프라인을 실행합니다.

- **09:00 KST** — 주 실행 (장 시작 후)
- **17:00 KST** — 실패 시 자동 만회하는 재실행

각 지표 fetch는 `continue-on-error`로 개별 실패가 전체를 막지 않으며, 실패가 있으면 알림 이슈를 열어 추적합니다.

---

## Supabase 스키마

`supabase/schema.sql`을 Supabase SQL Editor에 붙여넣어 실행하면 `indicators`, `indicator_values`, `daily_score` 3개 테이블과 RLS(공개 읽기 전용·쓰기는 service_role)가 설정됩니다. 이후 스키마 변경은 `supabase/migration_*.sql` 파일로 관리합니다.

---

## 데이터 출처

KRX 정보데이터시스템 · 한국은행 ECOS · 네이버 데이터랩/오픈API · YouTube Data API · 알라딘 · GitHub Search API · Apple App Store · DCInside · Upbit · Yahoo Finance
