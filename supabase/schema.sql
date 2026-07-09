-- Hatzze (코스피 과열도 판독기) — 초기 스키마
-- Supabase SQL Editor에 그대로 붙여넣어 실행하세요.

-- ============================================================
-- 1. indicators — 지표 메타데이터
-- ============================================================
create table if not exists public.indicators (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  category text not null check (category in ('정통', '밈')),
  description_beginner text not null,
  unit text not null,
  is_public boolean not null default true,
  created_at timestamptz not null default now()
);

comment on table public.indicators is '지표 메타데이터 (정통/밈 트랙 구분)';
comment on column public.indicators.slug is '코드에서 참조하는 안정적인 식별자 (예: us_10y_yield)';
comment on column public.indicators.description_beginner is '초보자용 한줄 설명';
comment on column public.indicators.is_public is '프론트엔드 노출 여부. false면 다른 지표 계산용 내부 캐시(예: kospi_close_raw)라 화면에 표시하지 않음';

alter table public.indicators enable row level security;

create policy "indicators_public_read"
  on public.indicators
  for select
  to anon, authenticated
  using (true);

-- ============================================================
-- 2. indicator_values — 지표별 일별 값
-- ============================================================
create table if not exists public.indicator_values (
  id uuid primary key default gen_random_uuid(),
  indicator_id uuid not null references public.indicators (id) on delete cascade,
  date date not null,
  raw_value numeric not null,
  normalized_score numeric,
  created_at timestamptz not null default now(),
  unique (indicator_id, date)
);

comment on table public.indicator_values is '지표별 일별 원시값 및 정규화 스코어(기준선 대비 진행률 %, 100 초과·음수 가능)';

create index if not exists indicator_values_indicator_id_date_idx
  on public.indicator_values (indicator_id, date desc);

alter table public.indicator_values enable row level security;

create policy "indicator_values_public_read"
  on public.indicator_values
  for select
  to anon, authenticated
  using (true);

-- ============================================================
-- 3. daily_score — 날짜별 종합 과열도 스코어
-- ============================================================
create table if not exists public.daily_score (
  date date primary key,
  score numeric not null,
  stage text not null check (stage in ('냉정', '보통', '과열', '광기')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.daily_score is '날짜별 종합 과열도 스코어(지표별 진행률 평균 %, 100 초과·음수 가능) 및 단계';
comment on column public.daily_score.updated_at is 'daily_score 갱신 시각. calculate_score.py가 실행할 때마다 명시적으로 채운다(upsert가 자동으로 갱신해주는 값이 아님)';

alter table public.daily_score enable row level security;

create policy "daily_score_public_read"
  on public.daily_score
  for select
  to anon, authenticated
  using (true);

-- ============================================================
-- 쓰기 정책 안내
-- ============================================================
-- 위 세 테이블 모두 RLS는 켜져 있지만 SELECT(읽기) 정책만 부여했습니다.
-- INSERT/UPDATE는 anon/authenticated 역할에 허용하지 않았으므로,
-- data-pipeline 배치 스크립트는 SUPABASE_SECRET_KEY(service_role)를 사용해
-- RLS를 우회하여 데이터를 적재해야 합니다. service_role 키는 서버/배치
-- 환경에만 보관하고 프론트엔드에 노출하지 마세요.
