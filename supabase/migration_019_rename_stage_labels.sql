-- Hatzze — 마이그레이션 019: daily_score.stage 라벨 교체
--
-- 2026-07-16 에 구간 이름을 온도 계열로 바꿨는데(공포/보통/과열/광기 → 저온/상온/고온/초고온)
-- 그때 Supabase SQL Editor 에서 CHECK 제약만 손으로 고치고 레포에는 반영하지 않았다.
-- 그 결과 schema.sql 은 옛 라벨을 강제하고 있어서, 이 파일로 새 환경을 만들면
-- calculate_score.py 가 첫 실행에 제약 위반으로 죽는다 — 재현 가능한 환경 구성이 불가능했다.
--
-- 운영 DB는 이미 새 라벨로 돌고 있으므로 이 마이그레이션은 사실상 no-op 이지만,
-- 앞으로 만들 환경이 같은 상태가 되도록 기록을 남긴다.
--
-- Supabase SQL Editor에서 실행하세요.

-- 혹시 옛 라벨이 남아 있으면 먼저 옮긴다(제약을 다시 걸기 전에).
update public.daily_score set stage = '저온'   where stage = '냉정';
update public.daily_score set stage = '상온'   where stage = '보통';
update public.daily_score set stage = '고온'   where stage = '과열';
update public.daily_score set stage = '초고온' where stage = '광기';

alter table public.daily_score drop constraint if exists daily_score_stage_check;

alter table public.daily_score
  add constraint daily_score_stage_check
  check (stage in ('저온', '상온', '고온', '초고온'));

comment on column public.daily_score.stage is
  '점수 구간 라벨. calculate_score.stage_for_score 가 25/50/75 경계로 정한다(저온/상온/고온/초고온)';
