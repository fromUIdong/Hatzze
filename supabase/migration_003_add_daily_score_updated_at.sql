-- Hatzze — 마이그레이션 003: daily_score.updated_at 컬럼 추가
-- daily_score.created_at은 최초 INSERT 시점에만 찍히고, upsert로 같은 날짜 행을
-- 다시 갱신해도 값이 바뀌지 않는다(실제로 score가 여러 번 갱신됐는데도 created_at은
-- 최초 생성 시각에 고정된 채였음을 확인). 화면에 "정확한 갱신 시각"을 보여주려면
-- calculate_score.py가 매 실행마다 명시적으로 갱신하는 별도 컬럼이 필요하다.
-- Supabase SQL Editor에서 실행하세요.

alter table public.daily_score
  add column if not exists updated_at timestamptz not null default now();

comment on column public.daily_score.updated_at is 'daily_score 갱신 시각. calculate_score.py가 실행할 때마다 명시적으로 채운다(upsert가 자동으로 갱신해주는 값이 아님)';
