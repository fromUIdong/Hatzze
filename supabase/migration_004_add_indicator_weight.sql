-- Hatzze — 마이그레이션 004: indicators.weight 컬럼 추가 (가중 평균 스코어 계산용)
-- 지금까지 daily_score.score는 13개 지표의 capped_progress를 단순 평균했는데,
-- 지표별 신뢰도/설명력 차이(예: 버핏지수·美 10년물 금리는 핵심 지표, dcinside
-- 게시글 수는 참고용 밈 지표)를 반영하지 못했다. 지표별 weight를 두고
-- calculate_score.py가 가중 평균으로 계산하도록 바꾼다. 새로 추가되는 지표는
-- weight를 명시하지 않으면 기본값 1(최저 가중치)로 들어가, 검증 전 지표가 지수에
-- 과도한 영향을 주지 않는다.
-- Supabase SQL Editor에서 실행하세요.

alter table public.indicators
  add column if not exists weight numeric not null default 1;

comment on column public.indicators.weight is '햇쩨 지수(daily_score.score) 가중 평균 계산용 가중치. 새 지표는 기본값 1(최저 가중치)로 시작한다';

update public.indicators set weight = 5   where slug = 'buffett_index';
update public.indicators set weight = 5   where slug = 'us10y';
update public.indicators set weight = 4   where slug = 'kospi_high_gap';
update public.indicators set weight = 3   where slug = 'kospi_volume_surge';
update public.indicators set weight = 3   where slug = 'vkospi';
update public.indicators set weight = 2   where slug = 'kospi_gold_ratio';
update public.indicators set weight = 2   where slug = 'usdkrw_volatility';
update public.indicators set weight = 2   where slug = 'kosdaq_kospi_ratio';
update public.indicators set weight = 2   where slug = 'leverage_etf_volume';
update public.indicators set weight = 2   where slug = 'naver_search_trend';
update public.indicators set weight = 1   where slug = 'dcinside_post_count';
update public.indicators set weight = 1.5 where slug = 'news_sentiment';
update public.indicators set weight = 1   where slug = 'bestseller_finance_ratio';
