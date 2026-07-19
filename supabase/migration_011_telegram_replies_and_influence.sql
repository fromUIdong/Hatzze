-- Hatzze — 마이그레이션 011: 트렌딩/영향력 점수용 컬럼 추가 (카더라 리포트)
-- 노션 계산법(채널 Influence Score + 트렌딩 메시지)을 지원하기 위한 확장.
--
-- (1) telegram_messages.replies: 트렌딩 점수 = Views×0.5 + Forwards×3.0 + Replies×1.5
--     에 필요한 댓글(스레드) 수. fetch_telegram.py 가 함께 수집한다.
-- (2) telegram_channel_stats 확장: 채널 파워 랭킹(Influence Score)을 매일 계산해
--     저장한다. 7일 전 점수와 비교(7D 변동)하려면 일별 저장이 필수다.
--     구성 지표(avg_views/view_rate/fwd_rate/weekly_posts)도 함께 저장해
--     채널 페이지 표시와 디버깅에 쓴다. calculate_channel_influence.py 가 채운다.
--
-- Supabase SQL Editor에서 실행하세요.

alter table public.telegram_messages
  add column if not exists replies integer;

comment on column public.telegram_messages.replies is '댓글(스레드) 수. 트렌딩 점수(Replies×1.5)에 사용. 없는 채널은 null';

alter table public.telegram_channel_stats
  add column if not exists avg_views numeric,
  add column if not exists view_rate numeric,
  add column if not exists fwd_rate numeric,
  add column if not exists weekly_posts integer,
  add column if not exists influence_score numeric,
  add column if not exists is_growing boolean;

comment on column public.telegram_channel_stats.avg_views is '최근 ~30개 게시물 평균 조회수';
comment on column public.telegram_channel_stats.view_rate is '뷰레이트(%) = avg_views / subscriber_count × 100';
comment on column public.telegram_channel_stats.fwd_rate is '포워드율(%) = 최근 게시물 포워드 합 / 조회수 합 × 100';
comment on column public.telegram_channel_stats.weekly_posts is '최근 7일 게시물 수(활동성)';
comment on column public.telegram_channel_stats.influence_score is '채널 영향력 점수(노션 계산법). 일반 ~52-100, 성장중 ~44-70';
comment on column public.telegram_channel_stats.is_growing is '성장 중 등급 여부(뷰레이트 3% 미만). 점수 페널티(×0.85) 적용 대상';
