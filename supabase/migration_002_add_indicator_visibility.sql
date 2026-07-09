-- Hatzze — 마이그레이션 002: indicators.is_public 컬럼 추가
-- app/page.tsx가 특정 slug 5개만 하드코딩해서 보여주던 방식을, indicators 테이블을
-- category별로 전부 자동 나열하는 방식으로 바꾸면서 필요해졌다. 다른 지표 계산을
-- 위한 내부 캐시(kospi_close_raw, kospi_market_cap_raw)만 is_public=false로 표시해
-- 화면에서 제외하고, 새로 추가되는 지표는 기본값(true)으로 자동 노출된다.
-- Supabase SQL Editor에서 실행하세요.

alter table public.indicators
  add column if not exists is_public boolean not null default true;

comment on column public.indicators.is_public is '프론트엔드 노출 여부. false면 다른 지표 계산용 내부 캐시(예: kospi_close_raw)라 화면에 표시하지 않음';

update public.indicators
  set is_public = false
  where slug in ('kospi_close_raw', 'kospi_market_cap_raw');
