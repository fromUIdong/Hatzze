-- Hatzze — 마이그레이션 010: telegram_channel_stats 테이블 추가 (카더라 리포트)
-- 채널별 일별 스냅샷. "최근 뜨는 채널(7일 구독자 상승세)"과 채널 파워 랭킹의
-- 시계열 근거로 쓴다.
--
-- 텔레그램은 과거 구독자수를 주지 않으므로 백필이 불가능하다 — 매일 스냅샷을
-- 남겨야 추세가 생긴다. sync_telegram_channels.py 가 실행마다 오늘(KST) 행을
-- upsert한다(하루 여러 번 돌면 최신값으로 덮어씀).
--
-- ※ telegram_channels/messages 와 동일하게 RLS는 켜되 공개 read 정책은 없음.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_channel_stats (
  id uuid primary key default gen_random_uuid(),
  channel_handle text not null references public.telegram_channels (handle) on delete cascade,
  date date not null,
  subscriber_count integer,
  captured_at timestamptz not null default now(),
  unique (channel_handle, date)
);

comment on table public.telegram_channel_stats is '채널별 일별 스냅샷(구독자수). 뜨는 채널/파워 랭킹의 시계열 근거. 백필 불가라 매일 기록';
comment on column public.telegram_channel_stats.date is '스냅샷 기준일(KST). channel_handle과 함께 유니크';
comment on column public.telegram_channel_stats.subscriber_count is '그날 관측한 구독자/멤버 수';

create index if not exists telegram_channel_stats_channel_date_idx
  on public.telegram_channel_stats (channel_handle, date desc);

alter table public.telegram_channel_stats enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
