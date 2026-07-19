-- Hatzze — 마이그레이션 009: telegram_messages 테이블 추가 (카더라 리포트)
-- 수집한 텔레그램 메시지 원본. fetch_telegram.py 가 활성 채널의 "최근 N일" 창을
-- 매 실행마다 다시 긁어 upsert(on_conflict=channel_handle,message_id)한다 —
-- 신규 메시지 수집과 기존 메시지의 조회수/포워드수 갱신을 한 번에 처리한다.
-- (views/forwards 는 시간이 지나며 계속 늘어서, 한 번 insert로 얼려두면 "가장 많이
--  본/퍼진 메시지"가 부정확해진다. N일 창 밖으로 나간 메시지는 값이 사실상
--  포화된 상태라 더 갱신하지 않는다.)
--
-- 종목추출·감성 결과는 이 단계에선 저장하지 않는다(다음 단계에서 별도 컬럼/테이블).
--
-- ※ telegram_channels 와 마찬가지로 RLS는 켜되 공개 read 정책을 두지 않는다.
--   원본 메시지는 anon 키로 노출하지 않고, 프론트는 집계 뷰/서버사이드(service_role)로
--   필요한 것만 읽는다.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_messages (
  id uuid primary key default gen_random_uuid(),
  channel_handle text not null references public.telegram_channels (handle) on delete cascade,
  message_id bigint not null,
  posted_at timestamptz not null,
  views integer,
  forwards integer,
  text text,
  has_media boolean not null default false,
  edited_at timestamptz,
  collected_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (channel_handle, message_id)
);

comment on table public.telegram_messages is '수집한 텔레그램 메시지 원본. fetch_telegram.py가 최근 N일 창을 매 실행 재수집해 upsert';
comment on column public.telegram_messages.message_id is '채널 내 메시지 ID(텔레그램). channel_handle과 함께 유니크';
comment on column public.telegram_messages.posted_at is '메시지 작성 시각(UTC 저장, 표시할 때 KST 변환)';
comment on column public.telegram_messages.views is '조회수. 시간이 지나며 증가하므로 재수집 창 안에서 갱신된다';
comment on column public.telegram_messages.forwards is '포워드(공유) 수. 확산도 지표. Client API에서만 제공';
comment on column public.telegram_messages.has_media is '사진/영상 등 미디어 포함 여부(text가 비어도 미디어만 있는 메시지 구분용)';
comment on column public.telegram_messages.collected_at is '이 메시지를 처음 수집한 시각(upsert 갱신 시 보존)';
comment on column public.telegram_messages.updated_at is '조회수/포워드/본문을 마지막으로 갱신한 시각(매 upsert마다 갱신)';

create index if not exists telegram_messages_posted_at_idx
  on public.telegram_messages (posted_at desc);
create index if not exists telegram_messages_channel_posted_idx
  on public.telegram_messages (channel_handle, posted_at desc);

alter table public.telegram_messages enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
