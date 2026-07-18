-- Hatzze — 마이그레이션 014: telegram_stock_daily 일별 종목 집계 (카더라 리포트)
-- telegram_message_stocks(추출 종목) × telegram_messages(시각·조회·포워드)를
-- 종목·날짜(KST)별로 집계한다. 급부상 종목·종목 리포트·테마 로테이션의 토대.
-- calculate_stock_daily.py 가 매 실행 재계산해 upsert한다.
--
-- weighted_score = 그날 그 종목을 언급한 메시지들의 트렌딩 점수 합
--   (메시지별 views×0.5 + forwards×3.0 + replies×1.5). 채널 크기·확산이 조회/
--   포워드에 이미 반영돼 있어 별도 채널가중 없이 "주목도"를 나타낸다.
-- mention_count = 언급 메시지 수(단순 빈도). 급부상은 이 둘의 일자간 변화로 본다.
--
-- ※ telegram_messages 파생이라 비공개(RLS 켜되 공개 read 없음). 프론트는
--   서버사이드(service_role)로 읽고 종목명은 stocks(공개)에서 조인한다.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_stock_daily (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  stock_code text not null references public.stocks (code),
  mention_count integer not null default 0,
  channel_count integer not null default 0,
  sum_views bigint not null default 0,
  sum_forwards integer not null default 0,
  weighted_score numeric not null default 0,
  created_at timestamptz not null default now(),
  unique (date, stock_code)
);

comment on table public.telegram_stock_daily is '일별·종목별 텔레그램 언급 집계. 급부상/리포트/테마의 토대';
comment on column public.telegram_stock_daily.date is '메시지 작성일(KST) 기준';
comment on column public.telegram_stock_daily.mention_count is '그날 이 종목을 언급한 메시지 수(단순 빈도)';
comment on column public.telegram_stock_daily.channel_count is '그날 이 종목을 언급한 서로 다른 채널 수';
comment on column public.telegram_stock_daily.weighted_score is '언급 메시지들의 트렌딩 점수 합(주목도 가중)';

create index if not exists tg_stock_daily_stock_date_idx
  on public.telegram_stock_daily (stock_code, date desc);
create index if not exists tg_stock_daily_date_idx
  on public.telegram_stock_daily (date desc);

alter table public.telegram_stock_daily enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
