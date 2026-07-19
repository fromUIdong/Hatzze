-- Hatzze — 마이그레이션 018: 카더라 리포트 LLM 분석 계층 (테이블 5개)
--
-- /telegram 대시보드에 남아 있던 데모 카드 3개(생태계 센티먼트 · 이슈 키워드 ·
-- 종목 흐름 요약)를 실데이터로 바꾸기 위한 저장 계층이다. 3단으로 나눈다:
--
--   [1] 분류(LLM·돈)   telegram_message_analysis   ← analyze_telegram_messages.py
--   [2] 집계(결정적)   telegram_sentiment_daily    ← calculate_telegram_sentiment.py
--                      telegram_keyword_daily
--   [3] 글쓰기(LLM)    telegram_daily_brief        ← generate_telegram_narratives.py
--                      telegram_stock_narrative
--
-- 왜 메시지 단위로 저장하나: 하루치 요약만 만들어 두면 다음 날 비교할 대상이 없다.
-- 메시지 단위로 한 번 분류해 두면 날짜·테마·종목 어느 축으로든 다시 집계할 수 있고,
-- "긍정 62%" 같은 수치를 LLM이 지어내는 게 아니라 SQL이 센다(종목추출·테마 로테이션과
-- 같은 철학). 히스토리가 필요한 지표는 빨리 붙일수록 이득이라는 원칙도 같다.
--
-- 왜 [2]와 [3]을 나누나: [2]는 매 실행 전량 재계산(삭제 후 삽입)한다. LLM 산출물을
-- 거기 같이 두면 매일 지워지므로 [3]은 별도 테이블에 보존한다.
--
-- ※ 전부 telegram_* 파생이라 동일하게 비공개(RLS 켜되 공개 read 정책 없음).
--   프론트는 service_role(getSupabaseAdmin)로 서버사이드에서만 읽는다.
--
-- Supabase SQL Editor에서 실행하세요.


-- ─────────────────────────────────────────────────────────────────────────────
-- [1] 메시지 단위 분류 — 유일하게 비용이 드는 단계라 한 번 한 건은 다시 안 한다.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.telegram_message_analysis (
  id uuid primary key default gen_random_uuid(),
  channel_handle text not null,
  message_id bigint not null,
  sentiment text not null check (sentiment in ('positive', 'neutral', 'negative')),
  keywords text[] not null default '{}',
  model text not null,
  analyzed_at timestamptz not null default now(),
  unique (channel_handle, message_id),
  foreign key (channel_handle, message_id)
    references public.telegram_messages (channel_handle, message_id) on delete cascade
);

comment on table public.telegram_message_analysis is '메시지별 LLM 분류(톤·화제어). 증분 처리 — 이미 분석한 메시지는 다시 호출하지 않는다';
comment on column public.telegram_message_analysis.sentiment is '메시지 톤: positive(낙관) | neutral(중립) | negative(비관). 시황 서술은 중립으로 분류';
comment on column public.telegram_message_analysis.keywords is '종목명이 아닌 화제어 0~3개(자유 추출). 표기 흔들림은 집계 단계의 별칭 사전이 흡수';
comment on column public.telegram_message_analysis.model is '분류에 쓴 모델 ID. 모델을 바꿨을 때 어느 행이 어느 모델 산출인지 구분해 선택적 재분석이 가능하도록';

create index if not exists tg_msg_analysis_msg_idx
  on public.telegram_message_analysis (channel_handle, message_id);

alter table public.telegram_message_analysis enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.


-- ─────────────────────────────────────────────────────────────────────────────
-- [2] 일별 집계 — LLM 없음. 매 실행 전량 재계산(extract/stock_daily 와 동일).
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.telegram_sentiment_daily (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  scope text not null,
  positive_count integer not null default 0,
  neutral_count integer not null default 0,
  negative_count integer not null default 0,
  message_count integer not null default 0,
  created_at timestamptz not null default now(),
  unique (date, scope)
);

comment on table public.telegram_sentiment_daily is '일별 메시지 톤 집계. scope=''overall''(전체) 또는 테마명(config/stock_themes.py)';
comment on column public.telegram_sentiment_daily.scope is '''overall'' = 그날 분석된 전체 메시지. 그 외에는 테마명 — 테마 로테이션 카드와 같은 사전을 공유해 두 카드가 일관되게 한다';
comment on column public.telegram_sentiment_daily.message_count is '해당 scope에서 분류된 메시지 수. 비율 계산의 분모이자, 표본이 얇은 날을 걸러내는 기준';

create index if not exists tg_sentiment_daily_date_idx
  on public.telegram_sentiment_daily (date desc);
create index if not exists tg_sentiment_daily_scope_date_idx
  on public.telegram_sentiment_daily (scope, date desc);

alter table public.telegram_sentiment_daily enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.


create table if not exists public.telegram_keyword_daily (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  keyword text not null,
  mention_count integer not null default 0,
  created_at timestamptz not null default now(),
  unique (date, keyword)
);

comment on table public.telegram_keyword_daily is '일별 화제어 언급 집계. 증감(▲▼)은 프론트가 최근 3일 평균 대 그 이전 평균으로 계산';
comment on column public.telegram_keyword_daily.keyword is '별칭 정규화를 마친 표기(config/issue_keywords.py의 ALIASES 적용 후)';

create index if not exists tg_keyword_daily_date_idx
  on public.telegram_keyword_daily (date desc);
create index if not exists tg_keyword_daily_keyword_date_idx
  on public.telegram_keyword_daily (keyword, date desc);

alter table public.telegram_keyword_daily enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.


-- ─────────────────────────────────────────────────────────────────────────────
-- [3] LLM 글쓰기 산출물 — 하루 1회 생성하고 보존한다([2] 재계산에 지워지지 않게).
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.telegram_daily_brief (
  id uuid primary key default gen_random_uuid(),
  date date not null unique,
  sentiment_summary text,
  model text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.telegram_daily_brief is '카더라 리포트의 하루치 총평(LLM). 현재는 센티먼트 카드 상단 2문장';
comment on column public.telegram_daily_brief.sentiment_summary is '집계된 수치만 근거로 쓴 2문장. 매수·매도·투자권유·목표가·전망은 프롬프트에서 금지(공개 저장소 + 법적 이유)';


alter table public.telegram_daily_brief enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.


create table if not exists public.telegram_stock_narrative (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  stock_code text not null references public.stocks (code),
  narrative text not null,
  model text,
  created_at timestamptz not null default now(),
  unique (date, stock_code)
);

comment on table public.telegram_stock_narrative is '종목별 최근 흐름 요약(LLM). 그날 주목도 상위 종목만 생성한다';
comment on column public.telegram_stock_narrative.narrative is '75~80자. 반칸 카드에서 정확히 3줄로 떨어지는 길이 — 83자를 넘기면 4줄이 되어 카드 높이가 어긋난다';

create index if not exists tg_stock_narrative_date_idx
  on public.telegram_stock_narrative (date desc);

alter table public.telegram_stock_narrative enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
