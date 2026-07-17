-- Hatzze — 마이그레이션 007: daily_score.ai_summary 컬럼 추가
-- 히어로 카드의 '오늘의 요약' 문장을 LLM(Claude Haiku)으로 생성해 저장하는 컬럼.
-- generate_daily_summary.py가 매 실행마다 최신 daily_score 행에 채운다.
-- 값이 없으면(마이그레이션 전이거나 요약 생성 실패) 프론트는 기존 템플릿 문장으로
-- 폴백하므로 화면이 깨지지 않는다.
-- Supabase SQL Editor에서 실행하세요.

alter table public.daily_score
  add column if not exists ai_summary text;

comment on column public.daily_score.ai_summary is 'LLM(Claude Haiku)이 생성한 오늘의 시장 과열도 요약(2~3문장). generate_daily_summary.py가 채우며, null이면 프론트가 기존 템플릿 문장으로 폴백한다';
