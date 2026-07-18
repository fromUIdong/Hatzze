-- Hatzze — 마이그레이션 012: stocks 상장종목 마스터 (카더라 리포트 종목추출용)
-- KOSPI/KOSDAQ 상장 종목의 코드↔종목명 사전. fetch_krx_stocks.py 가 KRX
-- 일별 시세 엔드포인트(stk_bydd_trd/ksq_bydd_trd)의 최신 가용일 데이터로 채운다.
-- 이 사전이 텔레그램 메시지에서 종목을 뽑는 하이브리드 추출의 base가 된다.
--
-- ※ telegram_* 테이블과 달리 이건 '감시 대상'이 아니라 일반 공개 정보(상장사
--   목록)이므로 공개 read 정책을 둔다 — 프론트가 종목명 표시에 바로 쓴다.
--
-- Supabase SQL Editor에서 실행하세요.

create table if not exists public.stocks (
  code text primary key,
  name text not null,
  market text,
  sect_type text,
  updated_at timestamptz not null default now()
);

comment on table public.stocks is 'KOSPI/KOSDAQ 상장종목 코드↔명 마스터. 텔레그램 종목추출 사전 base';
comment on column public.stocks.code is '6자리 단축코드(KRX ISU_CD, 예: 005930)';
comment on column public.stocks.name is 'KRX 종목명(ISU_NM)';
comment on column public.stocks.market is 'KOSPI | KOSDAQ (KRX MKT_NM)';
comment on column public.stocks.sect_type is 'KRX 소속부/구분(SECT_TP_NM). 업종 분류와는 다를 수 있음(참고용)';

create index if not exists stocks_name_idx on public.stocks (name);

alter table public.stocks enable row level security;

create policy "stocks_public_read"
  on public.stocks
  for select
  to anon, authenticated
  using (true);
