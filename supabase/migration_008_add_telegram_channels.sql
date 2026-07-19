-- Hatzze — 마이그레이션 008: telegram_channels 테이블 추가 (카더라 리포트)
-- 분석 대상 텔레그램 채널 목록. source of truth는 Hun이 관리하는 구글시트이고,
-- sync_telegram_channels.py가 시트를 읽어 이 테이블로 upsert한다. 매일 수집기
-- (fetch_telegram_*)는 이 테이블에서 is_active=true 인 채널만 골라 메시지를 모은다.
--
-- title/subscriber_count 는 시트가 아니라 텔레그램(GetFullChannelRequest)에서
-- 오며 sync 실행마다 갱신된다. 구독자수는 채널 영향력 평가 지표로 쓴다.
--
-- ※ RLS는 켜되 공개 read 정책은 두지 않는다 — 레포가 public이라 "우리가 어떤
--   채널을 감시하는지" 목록 자체를 비공개로 유지하기 위함. 파이프라인은
--   SUPABASE_SECRET_KEY(service_role)로 접근해 RLS를 우회하므로 문제없다.
--   프론트에 노출이 필요해지면 집계 뷰/테이블로 필요한 것만 따로 연다.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_channels (
  id uuid primary key default gen_random_uuid(),
  handle text not null unique,
  title text,
  type text not null default 'channel' check (type in ('channel', 'group')),
  is_active boolean not null default true,
  subscriber_count integer,
  added_at timestamptz not null default now(),
  synced_at timestamptz,
  notes text
);

comment on table public.telegram_channels is '카더라 리포트 분석 대상 텔레그램 채널 목록. source of truth=구글시트, sync_telegram_channels.py가 upsert';
comment on column public.telegram_channels.handle is '@ 없이 정규화한 텔레그램 유저네임 (예: FastStockNews). 안정적 식별자';
comment on column public.telegram_channels.title is '텔레그램 표시명. sync가 GetFullChannelRequest로 갱신';
comment on column public.telegram_channels.type is 'channel(공개 채널) | group(가입 필요한 채팅방)';
comment on column public.telegram_channels.is_active is '수집 on/off 스위치. 시트에서 빠지면 sync가 false로 내린다(행은 보존)';
comment on column public.telegram_channels.subscriber_count is '구독자/멤버 수. 채널 영향력 지표. sync 실행마다 갱신';
comment on column public.telegram_channels.synced_at is 'title/subscriber_count 를 텔레그램에서 마지막으로 갱신한 시각';

create index if not exists telegram_channels_active_idx
  on public.telegram_channels (is_active);

alter table public.telegram_channels enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
