-- Hatzze — 마이그레이션 019: stocks 에 52주 최고 종가 추가
--
-- 코스피 신고가 카드는 지수 괴리율(왼쪽)과 거래대금 상위 종목의 52주 고점 대비
-- (오른쪽)를 나란히 보여준다. 그런데 왼쪽은 KRX 종가 기준인데 오른쪽만 야후
-- 실시간이라 한 카드 안에서 기준이 갈렸다 — 배지에 "7/22 기준"이라 적어도
-- 오른쪽 숫자는 그 날짜의 값이 아니었다.
--
-- KRX 일별매매정보(stk_bydd_trd/ksq_bydd_trd)에는 52주 고점 필드가 없어서,
-- fetch_stock_high52.py 가 최근 52주치를 훑어 종목별 최고 종가를 직접 구해 넣는다.
-- 지수 쪽(kospi_high_gap)과 같은 '종가 기준'이라 두 숫자를 같은 잣대로 비교할 수 있다.
--
-- Supabase SQL Editor에서 실행하세요.

alter table public.stocks
  add column if not exists high_52w integer,
  add column if not exists high_52w_date date;

comment on column public.stocks.high_52w is
  '최근 52주 최고 종가(KRX TDD_CLSPRC 기준). 지수의 52주 신고가와 같은 종가 기준이다';
comment on column public.stocks.high_52w_date is
  '위 최고 종가를 기록한 날짜. 언제 찍은 고점인지 카드 툴팁에 쓴다';
