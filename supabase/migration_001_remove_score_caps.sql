-- Hatzze — 마이그레이션 001: normalized_score / daily_score.score 상한(100)·하한(0) 제약 제거
-- 과열도 스코어 계산 로직(scripts/calculate_score.py)이 지표별 진행률(Progress)을
-- 기준선 대비 그대로(100% 초과, 음수 가능) 반영하도록 설계되어 있어,
-- 기존 0~100 범위 체크 제약과 충돌한다. Supabase SQL Editor에서 실행하세요.

alter table public.indicator_values
  drop constraint if exists indicator_values_normalized_score_check;

alter table public.daily_score
  drop constraint if exists daily_score_score_check;
