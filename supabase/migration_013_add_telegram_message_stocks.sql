-- Hatzze — 마이그레이션 013: telegram_message_stocks 테이블 (카더라 리포트 종목추출)
-- 텔레그램 메시지에서 추출한 종목 언급. extract_telegram_stocks.py 가 채운다.
-- 급부상 종목·종목 리포트·테마 로테이션이 이 표를 집계해 만들어진다.
-- 메시지 1건에서 같은 종목은 한 행(중복 제거). 언급 강도는 나중에 조회수/포워드로
-- 가중한다(telegram_messages 조인).
--
-- ※ telegram_messages 파생이라 동일하게 비공개(RLS 켜되 공개 read 없음). 종목명은
--   stocks(공개)에서 조인해 표시하고, "어느 메시지가 그 종목을 언급했나"는 비공개.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.telegram_message_stocks (
  id uuid primary key default gen_random_uuid(),
  channel_handle text not null,
  message_id bigint not null,
  stock_code text not null references public.stocks (code),
  match_text text,
  method text,
  created_at timestamptz not null default now(),
  unique (channel_handle, message_id, stock_code),
  foreign key (channel_handle, message_id)
    references public.telegram_messages (channel_handle, message_id) on delete cascade
);

comment on table public.telegram_message_stocks is '텔레그램 메시지별 추출 종목(중복 제거). 급부상/리포트/테마 집계의 소스';
comment on column public.telegram_message_stocks.stock_code is 'stocks.code 참조(6자리 단축코드)';
comment on column public.telegram_message_stocks.match_text is '본문에서 실제 매칭된 문자열(종목명/별칭/약자)';
comment on column public.telegram_message_stocks.method is '추출 경로: dict(사전명) | alias(별칭) | llm(보강)';

create index if not exists tg_msg_stocks_stock_idx
  on public.telegram_message_stocks (stock_code);
create index if not exists tg_msg_stocks_msg_idx
  on public.telegram_message_stocks (channel_handle, message_id);

alter table public.telegram_message_stocks enable row level security;
-- 공개 read 정책 없음(의도적). service_role 키만 접근.
