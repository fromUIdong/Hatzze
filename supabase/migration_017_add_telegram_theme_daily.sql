-- Hatzze — 마이그레이션 017: telegram_theme_daily 일별 테마 집계 (카더라 리포트)
-- telegram_stock_daily(종목 일별 집계)를 config/stock_themes.py 의 테마 사전으로
-- 묶어 테마별 일별 지표를 만든다. "관심이 어느 테마로 옮겨가는가"(로테이션)를
-- 보려면 순위·점유율의 시계열이 필요해서 매일 저장한다.
--
-- share_pct = 그날 전체 언급 주목도(weighted) 중 이 테마가 차지한 비중(%).
--   절대량은 주말에 10분의 1로 떨어져 비교가 안 되므로 비중으로 기록한다
--   (급부상 종목 계산과 같은 이유).
-- rank = 그날 share_pct 기준 순위. 주간 순위 변동은 이 값을 날짜 간 비교해 구한다.
--
-- ※ telegram_* 파생이라 동일하게 비공개(RLS 켜되 공개 read 없음).
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_theme_daily (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  theme text not null,
  mention_count integer not null default 0,
  weighted_score numeric not null default 0,
  share_pct numeric not null default 0,
  stock_count integer not null default 0,
  rank integer,
  created_at timestamptz not null default now(),
  unique (date, theme)
);

comment on table public.telegram_theme_daily is '일별 테마 집계. telegram_stock_daily를 테마 사전(config/stock_themes.py)으로 묶은 결과';
comment on column public.telegram_theme_daily.share_pct is '그날 전체 주목도 중 이 테마 비중(%). 주말 볼륨 급감의 영향을 제거하려 절대량 대신 비중을 쓴다';
comment on column public.telegram_theme_daily.stock_count is '그날 이 테마에서 실제로 언급된 종목 수';
comment on column public.telegram_theme_daily.rank is '그날 share_pct 기준 순위. 날짜 간 비교로 주간 순위 변동을 계산';

create index if not exists tg_theme_daily_date_idx on public.telegram_theme_daily (date desc);
create index if not exists tg_theme_daily_theme_date_idx on public.telegram_theme_daily (theme, date desc);

alter table public.telegram_theme_daily enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
