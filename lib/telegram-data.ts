import "server-only";

import { cache } from "react";

import { sentimentTone } from "@/lib/format";
import { getSupabaseAdmin } from "@/lib/supabase-server";
import { changeRateOf, fetchYahooQuote } from "@/lib/yahoo-quote";

// 카더라 리포트 데이터 접근 계층. telegram_* 테이블은 비공개(공개 read 없음)라
// service_role 클라이언트(getSupabaseAdmin)로만 읽는다 — 서버에서만 호출된다.
// 종목명은 stocks(공개)에서 조인하고, 집계·정렬은 데이터가 작아 JS에서 처리한다.

const TREND_W_VIEWS = 0.5;
const TREND_W_FWD = 3.0;
const TREND_W_REPLIES = 1.5;

function daysAgoISO(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

/** 오늘(KST) 날짜 문자열. 아직 하루가 덜 찬 오늘을 집계에서 제외할 때 쓴다. */
function todayKstDate(): string {
  return new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/**
 * PostgREST는 한 번에 최대 1,000행만 준다 — 그 이상은 **에러 없이 잘린다**.
 * 일별 집계 테이블은 날짜가 쌓일수록 커져서(화제어는 하루 200행꼴) 이 상한을 넘기면
 * 최신 날짜가 통째로 빠지고, 그러면 "최근 3일 vs 이전" 같은 비교가 조용히 어긋난다.
 * 실제로 화제어 증감(▲▼)이 전부 사라지는 버그가 이 때문에 났다.
 * 행 수가 상한을 넘길 수 있는 조회는 전부 이 헬퍼로 페이지를 이어 받는다.
 */
async function fetchAllRows<T>(
  build: (from: number, to: number) => PromiseLike<{ data: T[] | null }>,
): Promise<T[]> {
  const PAGE = 1000;
  const out: T[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data } = await build(from, from + PAGE - 1);
    if (!data?.length) break;
    out.push(...data);
    if (data.length < PAGE) break;
  }
  return out;
}

export type TelegramSummary = {
  channelCount: number;
  totalSubscribers: number;
  totalMentions: number;
  activeChannels: number;
  messages7d: number;
  lastUpdated: string | null; // 파이프라인이 마지막으로 데이터를 갱신한 시각
};

/** 상단 요약 스탯 — 모니터링 채널 수·총 구독자·총 종목 언급·최근 7일 활성 채널. */
export async function getTelegramSummary(): Promise<TelegramSummary> {
  const db = getSupabaseAdmin();

  const { data: chans } = await db
    .from("telegram_channels")
    .select("handle,subscriber_count")
    .eq("is_active", true);
  const channelCount = chans?.length ?? 0;
  const totalSubscribers = (chans ?? []).reduce((s, c) => s + (c.subscriber_count ?? 0), 0);

  const { count: totalMentions } = await db
    .from("telegram_message_stocks")
    .select("id", { count: "exact", head: true });

  // 서로 다른 채널 수를 세려면 행을 다 봐야 한다 — 페이징 없이 select 하면 1000행에서
  // 잘려 활성 채널이 실제보다 적게 나온다(7일 메시지가 1,805건인데 1,000건만 보여
  // 12개 채널이 8개로 표시되던 버그).
  const recent = await fetchAllRows<{ channel_handle: string }>((from, to) =>
    db
      .from("telegram_messages")
      .select("channel_handle")
      .gte("posted_at", daysAgoISO(7))
      .range(from, to),
  );
  const activeChannels = new Set(recent.map((r) => r.channel_handle)).size;
  // 행을 세면 PostgREST 기본 1000행 상한에 걸려 항상 1,000이 된다 — count 쿼리로 정확히.
  const { count: messages7dCount } = await db
    .from("telegram_messages")
    .select("id", { count: "exact", head: true })
    .gte("posted_at", daysAgoISO(7));
  const messages7d = messages7dCount ?? 0;

  // 마지막 갱신 시각 — sync가 채널을 동기화한 시점이 파이프라인 실행 시각과 같다.
  const { data: synced } = await db
    .from("telegram_channels")
    .select("synced_at")
    .not("synced_at", "is", null)
    .order("synced_at", { ascending: false })
    .limit(1);
  const lastUpdated = synced?.[0]?.synced_at ?? null;

  return {
    channelCount,
    totalSubscribers,
    totalMentions: totalMentions ?? 0,
    activeChannels,
    messages7d,
    lastUpdated,
  };
}

// ─── 종목 일별 집계 공통 로더 ────────────────────────────────────────────────

/**
 * 점유율 비교용 평활 상수 — '언급 1회가 그날 대화에서 차지하는 몫'.
 * telegram_stock_daily 949건 실측: 언급 1회 종목의 점유율 중앙값 0.0018.
 * 배수를 낼 때 분자·분모에 함께 더해, 표본이 1회치뿐인 종목이 거대한 배수를
 * 받는 걸 막는다(자세한 이유는 getSurgingStocks 안 주석).
 */
const SHARE_SMOOTHING = 0.002;

type DailyRow = { stock_code: string; date: string; weighted_score: number; mention_count: number; channel_count: number };

async function loadStockDaily(days: number): Promise<{ rows: DailyRow[]; dates: string[] }> {
  const db = getSupabaseAdmin();
  const data = await fetchAllRows<DailyRow>((from, to) =>
    db
      .from("telegram_stock_daily")
      .select("stock_code,date,weighted_score,mention_count,channel_count")
      .gte("date", daysAgoISO(days).slice(0, 10))
      .order("date")
      .range(from, to),
  );
  // 오늘은 아직 하루가 덜 차서 일평균·추이를 왜곡한다 — 완료된 날만 쓴다.
  const today = todayKstDate();
  const rows = data.filter((r) => r.date < today);
  const dates = [...new Set(rows.map((r) => r.date))].sort();
  return { rows, dates };
}

/** 채널 핸들→(제목, 사진). photo 컬럼이 아직 없는 환경(마이그레이션 016 이전)에서도 안 깨지게 폴백. */
async function channelMeta(): Promise<{ titleOf: Map<string, string>; photoOf: Map<string, string | null> }> {
  const db = getSupabaseAdmin();
  let rows: { handle: string; title: string | null; photo?: string | null }[] = [];
  const withPhoto = await db.from("telegram_channels").select("handle,title,photo");
  if (withPhoto.error) {
    const basic = await db.from("telegram_channels").select("handle,title");
    rows = (basic.data ?? []) as typeof rows;
  } else {
    rows = (withPhoto.data ?? []) as typeof rows;
  }
  return {
    titleOf: new Map(rows.map((c) => [c.handle, c.title ?? c.handle])),
    photoOf: new Map(rows.map((c) => [c.handle, c.photo ?? null])),
  };
}

async function nameMap(codes: string[]): Promise<Map<string, string>> {
  if (!codes.length) return new Map();
  const db = getSupabaseAdmin();
  const { data } = await db.from("stocks").select("code,name").in("code", codes);
  return new Map((data ?? []).map((s) => [s.code as string, s.name as string]));
}

type StockInfo = { name: string; market: string | null; closePrice: number | null; changeRate: number | null; priceDate: string | null };

/**
 * 카드용 시세 — 야후 실시간(상단 티커와 같은 소스·같은 전일종가 규칙, lib/yahoo-quote).
 * KRX Open API는 며칠 지연돼 티커의 실시간 값과 크게 어긋나므로 표시용은 여기서 먼저
 * 가져오고, 실패하면 호출부가 KRX 저장 종가로 폴백한다.
 * 등락률을 못 내면 null을 준다 — 가격만 보여주면 변동을 오해할 수 있다.
 */
async function stockQuote(symbol: string): Promise<{ price: number; changeRate: number } | null> {
  const q = await fetchYahooQuote(symbol, { next: { revalidate: 600 } });
  if (!q) return null;
  const changeRate = changeRateOf(q);
  return changeRate === null ? null : { price: q.price, changeRate };
}

/** 종목명 + 최신 종가/등락률(마이그레이션 015 이전이면 가격은 null). */
async function stockInfoMap(codes: string[]): Promise<Map<string, StockInfo>> {
  if (!codes.length) return new Map();
  const db = getSupabaseAdmin();
  const { data, error } = await db
    .from("stocks")
    .select("code,name,market,close_price,change_rate,price_date")
    .in("code", codes);
  if (error) {
    // 가격 컬럼이 아직 없는 환경에서도 이름은 나오도록 폴백.
    const names = await nameMap(codes);
    return new Map(
      [...names].map(([c, n]) => [c, { name: n, market: null, closePrice: null, changeRate: null, priceDate: null }]),
    );
  }
  return new Map(
    (data ?? []).map((s) => [
      s.code as string,
      {
        name: s.name as string,
        market: (s.market as string) ?? null,
        closePrice: s.close_price ?? null,
        changeRate: s.change_rate != null ? Number(s.change_rate) : null,
        priceDate: s.price_date ?? null,
      },
    ]),
  );
}

// 종목명이 아닌 '주제' 태그용 키워드. 종목 태그가 없는 메시지에 붙인다.
// 종목 추출과 같은 방식(결정적 사전 매칭)이라 LLM 없이도 동작한다.
const TOPIC_KEYWORDS = [
  "HBM", "반도체", "금리", "환율", "관세", "실적", "수주", "공매도", "배당",
  "유가", "인플레", "연준", "FOMC", "경기침체", "증자", "공모주", "IPO",
  "2차전지", "조선", "방산", "원전", "AI", "로봇", "바이오", "부동산",
];

function extractTopics(text: string, limit = 2): string[] {
  const found: string[] = [];
  for (const k of TOPIC_KEYWORDS) {
    if (text.includes(k) && !found.includes(k)) found.push(k);
    if (found.length >= limit) break;
  }
  return found;
}

export type SurgingStock = {
  code: string;
  name: string;
  recentMentions: number;
  channelCount: number;
  ratio: number; // 최근 vs 평소 주목도 배수 (Infinity=신규 등장)
  isNew: boolean;
  series: number[]; // 일별 언급수(오래된→최신)
  market: string | null;
  closePrice: number | null;
  changeRate: number | null;
  priceDate: string | null;
  isLive: boolean; // true=야후 실시간, false=KRX 저장 종가(priceDate 기준)
};

/**
 * 급부상 종목 — 각 종목의 최근 활동이 평소 대비 얼마나 튀었나(momentum).
 * 최근 3일(완료된 날 기준) 일평균 weighted 를 그 이전 일평균과 비교한다.
 * 이전 기록이 없으면 신규 등장(🆕).
 */
export async function getSurgingStocks(limit = 5): Promise<SurgingStock[]> {
  const { rows, dates } = await loadStockDaily(14);
  if (!rows.length) return [];

  const recentN = Math.min(3, Math.max(1, dates.length - 1));
  const recentDateList = dates.slice(-recentN);
  const recentDates = new Set(recentDateList);
  const priorCount = Math.max(dates.length - recentN, 1);

  // 주말엔 전체 언급량이 평일의 1/10~1/20로 떨어져, 절대량으로 비교하면 모든 종목이
  // "감소"로 보여 카드가 비어버린다. 그래서 그날 전체 대비 '비중(share)'으로 비교해
  // 볼륨 수준의 영향을 제거하고 "대화에서 차지한 몫이 커졌나"만 본다.
  const dayTotal = new Map<string, number>();
  for (const r of rows) dayTotal.set(r.date, (dayTotal.get(r.date) ?? 0) + (Number(r.weighted_score) || 0));

  const byStock = new Map<
    string,
    { recentShare: number; recentM: number; priorShare: number; channels: number; byDate: Map<string, number> }
  >();
  for (const r of rows) {
    const a = byStock.get(r.stock_code) ?? { recentShare: 0, recentM: 0, priorShare: 0, channels: 0, byDate: new Map() };
    a.byDate.set(r.date, r.mention_count || 0);
    const total = dayTotal.get(r.date) || 0;
    const share = total > 0 ? (Number(r.weighted_score) || 0) / total : 0;
    if (recentDates.has(r.date)) {
      a.recentShare += share;
      a.recentM += r.mention_count || 0;
      a.channels = Math.max(a.channels, r.channel_count || 0);
    } else {
      a.priorShare += share;
    }
    byStock.set(r.stock_code, a);
  }

  const infoOf = await stockInfoMap([...byStock.keys()]);

  const scored = [...byStock.entries()]
    .map(([code, a]) => {
      const recentPerDay = a.recentShare / recentDateList.length;
      const base = a.priorShare / priorCount;
      const info = infoOf.get(code);
      return {
        code,
        name: info?.name ?? code,
        recentMentions: a.recentM,
        channelCount: a.channels,
        // 평활(+SHARE_SMOOTHING)한 뒤 나눈다. 그냥 나누면 분모가 거의 0인 종목이
        // "▲162.8배"처럼 터무니없는 배수를 받는데, 실제론 3일간 2회 언급·1개 채널이라
        // 표본이 사실상 없는 경우다. 상수는 '언급 1회가 만드는 몫'(실측 중앙값 0.0018)
        // 이라, 최근 몫이 1회치밖에 안 되면 배수가 2배 근처로 눌리고, 진짜 두꺼운
        // 급증(몫이 1회치의 수십 배)은 거의 그대로 남는다.
        ratio: (recentPerDay + SHARE_SMOOTHING) / (base + SHARE_SMOOTHING),
        isNew: base === 0,
        series: dates.map((d) => a.byDate.get(d) ?? 0),
        market: info?.market ?? null,
        closePrice: info?.closePrice ?? null,
        changeRate: info?.changeRate ?? null,
        priceDate: info?.priceDate ?? null,
        isLive: false,
      };
    })
    // 평활 덕에 신규 등장(base=0)도 유한한 배수를 받아 급증주와 같은 축에서 비교된다.
    // 예전엔 ratio=Infinity라 정렬을 독점해서 isNew를 3/2로 환산하는 보정이 필요했는데,
    // 그 보정은 "크게 등장한 신규"와 "1회 언급 신규"를 구분 못 했다. 이제 몫의 크기가
    // 그대로 반영돼 보정 없이 옳게 줄 선다.
    .sort((x, y) => y.ratio - x.ratio || y.recentMentions - x.recentMentions);

  // 카드 정원은 항상 채운다 — 기준을 만족한 종목만 넣으면 조용한 날에 4개·3개로 줄어
  // 레이아웃이 들쭉날쭉해진다. 다만 아무거나 끌어오면 안 되고 '덜 미더운 순서'로 메운다:
  //   ① 언급 2회↑ + 뚜렷하게 뛴 것(본래 기준)
  //   ② 언급 2회↑지만 상승폭이 완만한 것
  //   ③ 언급 1회 — 표본이 하나라 사실상 노이즈
  // ③을 ②보다 먼저 넣으면 4위 ▲1.3배 밑에 5위 ▲37배가 붙어 정렬이 깨져 보인다.
  // (평활 후에는 배수 자체가 눌리지만, '2회 이상'이라는 표본 하한은 그대로 둔다.)
  const tier = (s: SurgingStock) => (s.recentMentions < 2 ? 3 : s.ratio >= 1.3 ? 1 : 2);
  const list = [...scored].sort((x, y) => tier(x) - tier(y)).slice(0, limit);

  // 표시용 가격은 실시간(야후) 우선 — KRX 저장 종가는 며칠 지연돼 상단 티커와 어긋난다.
  // 조회 실패 시 KRX 종가(priceDate 라벨과 함께)를 그대로 쓴다.
  const quotes = await Promise.all(
    list.map((s) => stockQuote(`${s.code}.${s.market === "KOSDAQ" ? "KQ" : "KS"}`)),
  );
  list.forEach((s, i) => {
    const q = quotes[i];
    if (q) {
      s.closePrice = Math.round(q.price);
      s.changeRate = q.changeRate;
      s.isLive = true;
    }
  });

  return list;
}

export type StockTrend = {
  code: string;
  name: string;
  mentions: number;
  channels: number;
  series: number[];
};

/** 최근 7일 주목도 상위 종목 + 일별 언급 추이(스파크라인용). 종목 리포트에 쓴다. */
export async function getTopStocksWithTrend(limit = 6): Promise<StockTrend[]> {
  const { rows, dates } = await loadStockDaily(7);
  if (!rows.length) return [];

  const agg = new Map<string, { w: number; m: number; ch: number; byDate: Map<string, number> }>();
  for (const r of rows) {
    const a = agg.get(r.stock_code) ?? { w: 0, m: 0, ch: 0, byDate: new Map() };
    a.w += Number(r.weighted_score) || 0;
    a.m += r.mention_count || 0;
    a.ch = Math.max(a.ch, r.channel_count || 0);
    a.byDate.set(r.date, r.mention_count || 0);
    agg.set(r.stock_code, a);
  }

  const nameOf = await nameMap([...agg.keys()]);
  return [...agg.entries()]
    .sort((x, y) => y[1].w - x[1].w)
    .slice(0, limit)
    .map(([code, a]) => ({
      code,
      name: nameOf.get(code) ?? code,
      mentions: a.m,
      channels: a.ch,
      series: dates.map((d) => a.byDate.get(d) ?? 0),
    }));
}

export type TrendingMessage = {
  channelHandle: string;
  messageId: number;
  channelTitle: string;
  channelPhoto: string | null;
  text: string;
  views: number;
  forwards: number;
  replies: number;
  score: number;
  postedAt: string;
  stocks: string[]; // 이 메시지에서 추출된 종목명(태그)
  topics: string[]; // 종목 태그가 없을 때 붙는 핵심 주제 태그(금리·반도체 등)
};

/**
 * 트렌딩 메시지가 볼 수 있는 창.
 *
 * "today"는 일수가 아니라 KST 달력 기준이다 — 화면 라벨이 "오늘"이라 24시간
 * 롤링(daysAgoISO(1))으로 하면 어제 저녁 글이 늘 오늘 것으로 섞인다.
 * 다만 오전 첫 수집 전에는 전날 0시부터로 잡는다(아래 trendingTodayStartISO).
 */
export type TrendingWindow = "today" | number;

/** 수집 워크플로우의 첫 실행 시각(KST). .github/workflows/daily-update.yml 의 cron 과 맞춘다. */
const FIRST_COLLECTION_HOUR_KST = 9;

/**
 * '오늘' 창의 시작 시각.
 *
 * KST 오늘 0시로 그냥 잡으면 자정 직후 이 카드가 통째로 빈다 — 수집이 09시·17시에만
 * 돌아서 새벽에는 오늘 글이 DB 에 아예 없기 때문이다(실측 KST 2026-07-22 00:31:
 * 오늘 0건 / 어제 471건). 볼 게 없는 게 아니라 아직 안 담긴 것뿐인데 "아직 화제
 * 메시지가 없습니다" 만 뜬다.
 *
 * 그래서 첫 수집이 도는 09시 전에는 전날 0시를 창 시작으로 쓴다. 09시가 지나면
 * 그날 글이 담기므로 자연스럽게 오늘 0시로 넘어간다.
 */
function trendingTodayStartISO(): string {
  // Date.now()+9h 의 UTC 시각 = KST 시각(todayKstDate 와 같은 방식).
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const start = new Date(`${todayKstDate()}T00:00:00+09:00`);
  if (kstNow.getUTCHours() < FIRST_COLLECTION_HOUR_KST) {
    start.setUTCDate(start.getUTCDate() - 1);
  }
  return start.toISOString();
}

/** 트렌딩 메시지 TOP N (창: windowDays). 점수는 view가 지배적이라 view순으로 후보를 좁힌 뒤 정확 점수로 정렬. */
export async function getTrendingMessages(
  windowDays: TrendingWindow,
  limit = 8,
): Promise<TrendingMessage[]> {
  const db = getSupabaseAdmin();
  const since = windowDays === "today" ? trendingTodayStartISO() : daysAgoISO(windowDays);
  const { data: msgs } = await db
    .from("telegram_messages")
    .select("channel_handle,message_id,text,views,forwards,replies,posted_at")
    .gte("posted_at", since)
    .not("text", "is", null)
    .order("views", { ascending: false, nullsFirst: false })
    .limit(200);
  if (!msgs?.length) return [];

  const { titleOf, photoOf } = await channelMeta();

  const top = msgs
    .map((m) => ({
      channelHandle: m.channel_handle,
      messageId: m.message_id as number,
      channelTitle: titleOf.get(m.channel_handle) ?? m.channel_handle,
      channelPhoto: photoOf.get(m.channel_handle) ?? null,
      text: (m.text ?? "").replace(/\s+/g, " ").trim(),
      views: m.views ?? 0,
      forwards: m.forwards ?? 0,
      replies: m.replies ?? 0,
      score: (m.views ?? 0) * TREND_W_VIEWS + (m.forwards ?? 0) * TREND_W_FWD + (m.replies ?? 0) * TREND_W_REPLIES,
      postedAt: m.posted_at,
      stocks: [] as string[],
      topics: [] as string[],
    }))
    .filter((m) => m.text.length > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  // 각 메시지에서 추출해둔 종목을 태그로 붙인다(사전 기반 추출 결과 재사용).
  // message_id 는 채널별로만 유일해서 채널을 안 걸면 다른 채널의 같은 번호 메시지까지
  // 딸려온다(한 번호가 최대 60행). 아래에서 채널까지 포함한 키로 걸러내므로 결과는
  // 맞지만, 행이 많아지면 1000행 상한에 잘려 태그가 조용히 사라질 수 있어 페이징한다.
  const tags = await fetchAllRows<{ channel_handle: string; message_id: number; stock_code: string }>(
    (from, to) =>
      db
        .from("telegram_message_stocks")
        .select("channel_handle,message_id,stock_code")
        .in("message_id", top.map((m) => m.messageId))
        .range(from, to),
  );

  if (tags.length) {
    const nameOf = await nameMap([...new Set(tags.map((t) => t.stock_code))]);
    const byMsg = new Map<string, string[]>();
    for (const t of tags) {
      const key = `${t.channel_handle}|${t.message_id}`;
      const arr = byMsg.get(key) ?? [];
      const nm = nameOf.get(t.stock_code);
      if (nm && !arr.includes(nm)) arr.push(nm);
      byMsg.set(key, arr);
    }
    for (const m of top) m.stocks = (byMsg.get(`${m.channelHandle}|${m.messageId}`) ?? []).slice(0, 3);
  }

  // 특정 종목 이야기가 아니면 핵심 주제(금리·반도체 등)를 태그로 붙인다.
  for (const m of top) {
    if (m.stocks.length === 0) m.topics = extractTopics(m.text);
  }

  return top;
}

export type StockReport = {
  code: string;
  name: string;
  totalMentions: number;
  series: { date: string; mentions: number }[];
  channelCount: number; // 이 종목을 다룬 서로 다른 채널 수(관심의 폭)
  price: number | null; // 실시간 시세
  changeRate: number | null;
};

/** 종목 리포트 카드가 내세우는 구간. 카드 라벨("최근 7일")과 반드시 같아야 한다. */
const REPORT_WINDOW_DAYS = 7;

/**
 * 최근 N일 안에 올라온 메시지의 키 집합.
 *
 * telegram_message_stocks 에는 날짜가 없어서(메시지 PK만 갖는다) 종목 언급을 기간으로
 * 자르려면 메시지 쪽 posted_at 을 봐야 한다. 한 페이지에서 종목 리포트를 3개 만들며
 * 같은 집합을 세 번 쓰므로 React cache 로 요청당 한 번만 조회한다.
 */
const recentMessageKeys = cache(async (days: number): Promise<Set<string>> => {
  const db = getSupabaseAdmin();
  const rows = await fetchAllRows<{ channel_handle: string; message_id: number }>((from, to) =>
    db
      .from("telegram_messages")
      .select("channel_handle,message_id")
      .gte("posted_at", daysAgoISO(days))
      .range(from, to),
  );
  return new Set(rows.map((r) => `${r.channel_handle}|${r.message_id}`));
});

/** 종목 텔레그램 리포트 — 특정 종목의 최근 7일 언급 추이와 관심의 폭. */
export async function getStockReport(code: string): Promise<StockReport | null> {
  const db = getSupabaseAdmin();
  const { data: stock } = await db.from("stocks").select("name,market").eq("code", code).maybeSingle();
  if (!stock) return null;

  const { data: daily } = await db
    .from("telegram_stock_daily")
    .select("date,mention_count")
    .eq("stock_code", code)
    .gte("date", daysAgoISO(REPORT_WINDOW_DAYS).slice(0, 10))
    .order("date");
  const today = todayKstDate();
  // 언급이 0인 날은 집계 표에 행 자체가 없다. 있는 행만 그리면 종목마다 막대 개수가
  // 달라져, 나란히 놓인 두 차트가 서로 다른 기간을 그리게 된다(실측: 삼성전자 8칸,
  // 현대차 7칸 — 07-18이 통째로 빠졌다). "최근 이틀 급증" 같은 문장도 눌린 축 위에서
  // 읽히고, "최근 7일"이라는 라벨과도 안 맞는다.
  //
  // 그래서 창 전체의 날짜를 먼저 만들고 없는 날은 0으로 채운다 — 같은 파일의
  // getTopStocksWithTrend 가 이미 쓰는 방식이라 그쪽과도 축이 맞는다.
  const byDate = new Map((daily ?? []).map((d) => [d.date, d.mention_count || 0]));
  const series: { date: string; mentions: number }[] = [];
  for (let i = REPORT_WINDOW_DAYS - 1; i >= 0; i -= 1) {
    const d = new Date(`${today}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - i - 1); // 오늘은 아직 하루가 덜 차서 제외
    const iso = d.toISOString().slice(0, 10);
    series.push({ date: iso, mentions: byDate.get(iso) ?? 0 });
  }
  const totalMentions = series.reduce((s, d) => s + d.mentions, 0);

  // 채널 수도 같은 창으로 자른다 — 전체 기간으로 세면 모니터링 채널이 12개뿐이라
  // 금세 12로 포화돼 '관심의 폭'을 구분하지 못한다.
  // 이 표에는 날짜가 없어 서버에서 기간을 못 자른다 — 종목 하나의 전체 기간 언급을
  // 다 받아 와 아래에서 창으로 거른다. 인기 종목은 하루 30건꼴이라 한 달이면 1000행을
  // 넘기므로 반드시 페이징한다(안 하면 채널 수가 조용히 적게 나온다).
  const mentions = await fetchAllRows<{ channel_handle: string; message_id: number }>((from, to) =>
    db
      .from("telegram_message_stocks")
      .select("channel_handle,message_id")
      .eq("stock_code", code)
      .range(from, to),
  );
  const keys = await recentMessageKeys(REPORT_WINDOW_DAYS);
  const channelCount = new Set(
    mentions
      .filter((m) => keys.has(`${m.channel_handle}|${m.message_id}`))
      .map((m) => m.channel_handle),
  ).size;

  const quote = await stockQuote(`${code}.${stock.market === "KOSDAQ" ? "KQ" : "KS"}`);

  return {
    code,
    name: stock.name as string,
    totalMentions,
    series,
    channelCount,
    price: quote ? Math.round(quote.price) : null,
    changeRate: quote ? quote.changeRate : null,
  };
}

export type ThemeRotation = {
  theme: string;
  rank: number;
  rankChange: number | null; // 주간 순위 변동(+면 상승). 비교할 과거가 없으면 null
  sharePct: number;
  shareDelta: number | null; // 점유율 증감(%p)
  mentions: number;
  stockCount: number;
  series: number[]; // 일별 점유율 추이(오래된→최신)
};

/**
 * 테마 로테이션 — 테마별 언급 점유율·순위와 그 변화.
 * 절대 언급량은 주말에 급감해 비교가 안 되므로 '그날 전체 대비 점유율'로 본다.
 * 순위 변동·점유율 증감은 5일 이상 이전 데이터가 있을 때만 계산한다(축적 초기 왜곡 방지).
 */
export async function getThemeRotation(limit = 10): Promise<ThemeRotation[]> {
  const db = getSupabaseAdmin();
  const { data } = await db
    .from("telegram_theme_daily")
    .select("date,theme,share_pct,mention_count,stock_count")
    .gte("date", daysAgoISO(14).slice(0, 10));
  if (!data?.length) return [];

  const dates = [...new Set(data.map((r) => r.date))].sort();
  const latestDate = dates[dates.length - 1];
  const DAY = 24 * 60 * 60 * 1000;
  const daysBefore = (d: string) => (new Date(latestDate).getTime() - new Date(d).getTime()) / DAY;

  // 하루치끼리 비교하면 주말·수집 첫날처럼 표본이 얇은 날에 점유율이 요동친다.
  // 그래서 '최근 3일 평균' vs '5일 이상 이전 평균'으로 창을 잡아 비교한다.
  const recentDates = dates.slice(-3);
  const priorDates = dates.filter((d) => daysBefore(d) >= 5);

  // 최근 창에 한 번도 안 뜬 테마도 카드에는 0%로 남겨야 정원(10개)이 채워진다.
  // 그래서 집계 대상 테마는 '최근 창에 등장한 것'이 아니라 조회 구간 전체의 테마다.
  const allThemes = [...new Set(data.map((r) => r.theme))];

  const avgShare = (window: string[]) => {
    const sum = new Map<string, number>(allThemes.map((t) => [t, 0]));
    for (const r of data) {
      if (!window.includes(r.date)) continue;
      sum.set(r.theme, (sum.get(r.theme) ?? 0) + Number(r.share_pct));
    }
    // 그날 등장하지 않은 테마는 0으로 치므로 창 전체 일수로 나눈다.
    return new Map([...sum].map(([t, v]) => [t, v / Math.max(window.length, 1)]));
  };
  const rankMap = (shares: Map<string, number>) =>
    new Map([...shares].sort((a, b) => b[1] - a[1]).map(([t], i) => [t, i + 1]));

  const recentShare = avgShare(recentDates);
  const priorShare = priorDates.length ? avgShare(priorDates) : null;
  const currRank = rankMap(recentShare);
  const prevRank = priorShare ? rankMap(priorShare) : null;

  // 최근 창의 합계(언급수·종목수)는 표시용으로 최신일 값이 아니라 창 전체를 쓴다.
  const agg = new Map<string, { mentions: number; stocks: number }>();
  for (const r of data) {
    if (!recentDates.includes(r.date)) continue;
    const a = agg.get(r.theme) ?? { mentions: 0, stocks: 0 };
    a.mentions += r.mention_count ?? 0;
    a.stocks = Math.max(a.stocks, r.stock_count ?? 0);
    agg.set(r.theme, a);
  }

  const seriesOf = (theme: string) =>
    dates.map((d) => Number(data.find((r) => r.date === d && r.theme === theme)?.share_pct ?? 0));

  return [...recentShare.entries()]
    .map(([theme, share]) => {
      const before = priorShare?.get(theme);
      const pr = prevRank?.get(theme);
      const cr = currRank.get(theme) ?? 0;
      return {
        theme,
        rank: cr,
        rankChange: pr != null ? pr - cr : null,
        sharePct: share,
        shareDelta: before != null ? share - before : null,
        mentions: agg.get(theme)?.mentions ?? 0,
        stockCount: agg.get(theme)?.stocks ?? 0,
        series: seriesOf(theme),
      };
    })
    .sort((a, b) => a.rank - b.rank)
    .slice(0, limit);
}

export type ChannelRank = {
  handle: string;
  title: string;
  photo: string | null;
  rankChange: number | null; // 주간 순위 변동(+면 상승). 비교할 과거 스냅샷이 없으면 null
  subscriberCount: number | null;
  influenceScore: number;
  viewRate: number | null;
  isGrowing: boolean;
};

/** 채널 파워 랭킹 — 가장 최근 날짜의 Influence Score. */
export async function getChannelRanking(): Promise<ChannelRank[]> {
  const db = getSupabaseAdmin();
  // 채널 12개 × 하루 1행이라 석 달이면 1000행을 넘긴다 — 그때 잘리면 순위 변동 비교용
  // 과거 스냅샷이 사라지므로 미리 페이징해 둔다.
  const stats = await fetchAllRows<{
    channel_handle: string;
    date: string;
    subscriber_count: number | null;
    influence_score: number | null;
    view_rate: number | null;
    is_growing: boolean | null;
  }>((from, to) =>
    db
      .from("telegram_channel_stats")
      .select("channel_handle,date,subscriber_count,influence_score,view_rate,is_growing")
      .not("influence_score", "is", null)
      .order("date", { ascending: false })
      .range(from, to),
  );
  if (!stats.length) return [];

  const latest = new Map<string, (typeof stats)[number]>();
  for (const r of stats) if (!latest.has(r.channel_handle)) latest.set(r.channel_handle, r);

  // 주간 순위 변동 — 최신일과 "5일 이상 이전" 스냅샷의 순위를 비교한다.
  // 그만큼 히스토리가 없으면(축적 초기) null로 두고 화면에서 배지를 숨긴다.
  const dates = [...new Set(stats.map((r) => r.date))].sort();
  const latestDate = dates[dates.length - 1];
  const DAY = 24 * 60 * 60 * 1000;
  const baseDate = dates.find(
    (d) => (new Date(latestDate).getTime() - new Date(d).getTime()) / DAY >= 5,
  );
  const rankOn = (date: string) =>
    new Map(
      stats
        .filter((r) => r.date === date)
        .sort((a, b) => Number(b.influence_score) - Number(a.influence_score))
        .map((r, i) => [r.channel_handle, i + 1]),
    );
  const prevRanks = baseDate ? rankOn(baseDate) : null;
  const currRanks = rankOn(latestDate);

  const { titleOf, photoOf } = await channelMeta();

  return [...latest.values()]
    .map((r) => ({
      handle: r.channel_handle,
      title: titleOf.get(r.channel_handle) ?? r.channel_handle,
      photo: photoOf.get(r.channel_handle) ?? null,
      rankChange:
        prevRanks && prevRanks.has(r.channel_handle) && currRanks.has(r.channel_handle)
          ? (prevRanks.get(r.channel_handle) as number) - (currRanks.get(r.channel_handle) as number)
          : null,
      subscriberCount: r.subscriber_count,
      influenceScore: Number(r.influence_score),
      viewRate: r.view_rate != null ? Number(r.view_rate) : null,
      isGrowing: !!r.is_growing,
    }))
    .sort((a, b) => b.influenceScore - a.influenceScore);
}

export type RisingChannel = {
  handle: string | null;
  title: string;
  photo: string | null;
  subscriberCount: number;
  delta7d: number;
  isPlaceholder: boolean; // true=정원을 채우려 복제한 행
  spanDays: number; // 증감을 실제로 잰 구간(스냅샷 축적일). 7일 미만이면 카드도 그렇게 표기한다
};

/**
 * 뜨는 채널 — 스냅샷 사이의 구독자 증가. 스냅샷은 백필이 안 돼 하루씩만 쌓이므로,
 * 축적이 7일에 못 미치는 동안에는 잰 구간(spanDays)을 그대로 노출한다.
 */
export async function getRisingChannels(limit = 10): Promise<RisingChannel[]> {
  const db = getSupabaseAdmin();
  const { data } = await db
    .from("telegram_channel_stats")
    .select("channel_handle,date,subscriber_count")
    .gte("date", daysAgoISO(8).slice(0, 10));

  const byCh = new Map<string, { d: string; s: number }[]>();
  for (const r of data ?? []) {
    if (r.subscriber_count == null) continue;
    const arr = byCh.get(r.channel_handle) ?? [];
    arr.push({ d: r.date, s: r.subscriber_count });
    byCh.set(r.channel_handle, arr);
  }
  const { titleOf, photoOf } = await channelMeta();

  // 스냅샷은 백필이 안 돼 오늘부터 하루씩 쌓인다 — 지금 잰 구간이 며칠인지 그대로 알린다.
  const snapDates = [...new Set((data ?? []).map((r) => r.date))].sort();
  const spanDays = snapDates.length
    ? Math.round(
        (new Date(snapDates[snapDates.length - 1]).getTime() - new Date(snapDates[0]).getTime()) / (24 * 60 * 60 * 1000),
      )
    : 0;

  const real: RisingChannel[] = [];
  const flat: RisingChannel[] = [];
  for (const [h, arr] of byCh) {
    if (arr.length < 2) continue;
    arr.sort((a, b) => a.d.localeCompare(b.d));
    const delta = arr[arr.length - 1].s - arr[0].s;
    (delta > 0 ? real : flat).push({
      handle: h,
      title: titleOf.get(h) ?? h,
      photo: photoOf.get(h) ?? null,
      subscriberCount: arr[arr.length - 1].s,
      delta7d: delta,
      isPlaceholder: false,
      spanDays,
    });
  }
  real.sort((a, b) => b.delta7d - a.delta7d);
  flat.sort((a, b) => b.delta7d - a.delta7d);

  // 카드 정원은 항상 채운다. 실제로 늘어난 채널을 먼저 넣고, 모자라면 증감이 없거나
  // 줄어든 채널까지 순서대로 끌어온다(표시되는 증감은 실제값 그대로).
  // 지금은 모니터링 채널이 12개뿐이라 "늘어난 곳"만 세면 8개 안팎에서 멈춘다 —
  // 시트에 채널이 늘면 이 보충분은 자연히 밀려나 사라진다.
  const filled = [...real, ...flat].slice(0, limit);
  // 그래도 모자라면(채널 수 자체가 정원보다 적으면) '빈 행'으로 자리만 채운다.
  // 예전엔 마지막 행을 복제했는데, 그러면 같은 채널이 두 번 표시돼 없는 데이터를
  // 지어내는 꼴이었다 — 카드 높이를 지키자고 사용자에게 거짓을 보일 순 없다.
  while (filled.length && filled.length < limit) {
    filled.push({
      handle: null,
      title: "",
      photo: null,
      subscriberCount: 0,
      delta7d: 0,
      isPlaceholder: true,
      spanDays,
    });
  }
  return filled;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM 분석 계층 — analyze_telegram_messages.py 가 메시지별로 분류하고,
// calculate_telegram_sentiment.py 가 날짜·테마·화제어로 집계한 결과를 읽는다.
// 화면에 뜨는 비율·횟수는 전부 그 집계값이다(LLM이 센 게 아니다).
// ─────────────────────────────────────────────────────────────────────────────

/** 화제어가 카드에 오르기 위한 최소 언급 수(최근 7일). 한두 번 스친 말이 상위에
 *  끼면 "지금 무엇이 화제인가"라는 카드의 목적이 흐려진다. 집계 테이블에는 전부
 *  남아 있어서, 이 기준만 바꾸면 재계산 없이 반영된다. */
const MIN_KEYWORD_MENTIONS = 3;

export type EcosystemSentiment = {
  /** 낙관도 = 낙관 / (낙관 + 비관), 중립 제외. 카드 헤드라인 숫자.
   *  전체 대비 '긍정 비율'을 쓰면 안 된다 — 실측상 중립이 절반쯤이라 긍정 비율은
   *  구조적으로 낮게 나오고, 긍정(30%)이 비관(22%)보다 많은데도 '비관 우세'로
   *  읽히는 일이 생긴다. 바로 옆 테마별 막대도 같은 기준(중립 제외)이라 카드 안에서
   *  기준이 하나로 통일된다. */
  score: number;
  label: string;
  /** 헤드라인 숫자에 쓸 색 톤. label과 같은 구간에서 같이 나온다(sentimentTone). */
  tone: "hot" | "neutral" | "cold";
  positive: number;
  neutral: number;
  negative: number; // 셋의 합은 항상 100(반올림 보정). 아래 3분할 막대가 이걸 그린다
  messageCount: number;
  summary: string | null; // LLM 총평. 아직 생성 전이면 null
  /** 표본(positive/negative/total)을 같이 넘긴다 — 얇은 테마는 100:0 같은 극단값이
   *  나오는데, 몇 건 기준인지 보여줘야 그 숫자를 제대로 읽을 수 있다. */
  byTheme: { name: string; pos: number; positive: number; negative: number; total: number }[];
};

// 낙관도 → 라벨/색 구간은 시장 브리핑의 감성 카드와 공유한다(lib/format.ts sentimentTone).
// LLM에 맡기지 않고 결정적으로 정해서, 같은 수치면 두 화면이 항상 같은 말을 쓴다.

/** 합이 100이 되도록 반올림을 보정한다(단순 반올림은 99·101이 나와 막대가 어긋난다). */
function toPercents(pos: number, neu: number, neg: number): [number, number, number] {
  const total = pos + neu + neg;
  if (!total) return [0, 0, 0];
  const raw = [(pos / total) * 100, (neu / total) * 100, (neg / total) * 100];
  const floors = raw.map(Math.floor);
  let remainder = 100 - floors.reduce((s, v) => s + v, 0);
  // 소수부가 큰 순서로 남은 1%p씩 나눠 준다.
  const order = raw
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);
  const out = [...floors];
  for (const { i } of order) {
    if (remainder <= 0) break;
    out[i] += 1;
    remainder -= 1;
  }
  return [out[0], out[1], out[2]];
}

/**
 * 생태계 센티먼트 — 최근 7일 메시지 톤 구성 + 테마별 낙관 비중 + LLM 총평.
 * 테마는 파이프라인이 config/stock_themes.py(테마 로테이션과 같은 사전)로 묶어 둔 것이다.
 */
export async function getEcosystemSentiment(): Promise<EcosystemSentiment | null> {
  const db = getSupabaseAdmin();
  // 날짜 컬럼에 gte라 경계일이 포함된다 — 7일치를 보려면 오늘 포함 6일 전부터다.
  // daysAgoISO(7)이면 8일치가 잡혀 카드 헤더('최근 7일')와도, 같은 창을 latest-6으로
  // 잡는 파이프라인 총평(generate_telegram_narratives.py)과도 어긋났다.
  const since = daysAgoISO(6).slice(0, 10);
  const { data } = await db
    .from("telegram_sentiment_daily")
    .select("date,scope,positive_count,neutral_count,negative_count,message_count")
    .gte("date", since);
  if (!data?.length) return null;

  const agg = new Map<string, { pos: number; neu: number; neg: number; total: number }>();
  for (const r of data) {
    const a = agg.get(r.scope) ?? { pos: 0, neu: 0, neg: 0, total: 0 };
    a.pos += r.positive_count ?? 0;
    a.neu += r.neutral_count ?? 0;
    a.neg += r.negative_count ?? 0;
    a.total += r.message_count ?? 0;
    agg.set(r.scope, a);
  }

  const overall = agg.get("overall");
  if (!overall?.total) return null;
  const [positive, neutral, negative] = toPercents(overall.pos, overall.neu, overall.neg);

  // 테마 막대는 낙관↔비관 양분 구조라 중립을 뺀 대립 비율로 그린다.
  // 낙관/비관이 합쳐 8건은 돼야 비율에 의미가 있다(그 아래는 한두 건에 100:0이 되어
  // 실제보다 단정적으로 보인다). 남은 극단값은 표본을 툴팁으로 같이 보여 해석을 돕는다.
  const byTheme = [...agg.entries()]
    .filter(([scope, a]) => scope !== "overall" && a.pos + a.neg >= 8)
    .map(([scope, a]) => ({
      name: scope,
      pos: Math.round((a.pos / (a.pos + a.neg)) * 100),
      positive: a.pos,
      negative: a.neg,
      total: a.total,
    }))
    .sort((x, y) => y.total - x.total)
    .slice(0, 4);

  const { data: brief } = await db
    .from("telegram_daily_brief")
    .select("sentiment_summary")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();

  // 헤드라인은 중립을 뺀 낙관도 — 테마별 막대와 같은 기준으로 맞춘다(위 타입 주석 참고).
  const decided = overall.pos + overall.neg;
  const optimism = decided ? Math.round((overall.pos / decided) * 100) : 50;

  const { label, tone } = sentimentTone(optimism);

  return {
    score: optimism,
    label,
    tone,
    positive,
    neutral,
    negative,
    messageCount: overall.total,
    summary: (brief?.sentiment_summary as string | null) ?? null,
    byTheme,
  };
}

export type IssueKeyword = {
  word: string;
  count: number; // 최근 7일 언급 수(화면에 그대로 표시)
  /**
   * 관심 점유율의 방향. 비교할 과거가 없으면 null.
   *
   * 예전엔 boolean 이라 '변화 없음'을 담을 자리가 없었다 — `recentAvg >= priorAvg` 라
   * 두 값이 같으면 ▲가 붙었고, 최근 3일에 한 번도 안 나온 화제어(둘 다 0)까지 ▲로
   * 표시됐다. "관심이 늘었다"는 화살표가 관심이 사라진 말에 붙는 셈이었다.
   */
  trend: "up" | "flat" | "down" | null;
};

/**
 * 이슈 키워드 — 종목명이 아닌 화제어 순위.
 *
 * 증감(▲▼)은 **절대 언급 수가 아니라 그날 전체 화제어 중 점유율**로 본다.
 * 주말이면 전체 메시지가 평일의 1/10로 떨어져서, 절대량으로 비교하면 모든 화제어가
 * 일제히 ▼로 표시된다(실제로 그렇게 났다). 점유율로 보면 "관심이 이 화제어로
 * 옮겨갔는가"라는 원래 묻고 싶은 것이 남는다 — 테마 로테이션·급부상 종목이 같은 이유로
 * share 기반이다.
 *
 * 창은 테마 로테이션과 동일하게 최근 3일 평균 vs 5일 이상 이전 평균 — 하루치끼리
 * 비교하면 표본이 얇은 날에 요동친다.
 */
export async function getIssueKeywords(limit = 10): Promise<IssueKeyword[]> {
  const db = getSupabaseAdmin();
  // 화제어는 하루 200행꼴이라 2주면 1,000행 상한을 훌쩍 넘는다 — 반드시 페이징.
  const data = await fetchAllRows<{ date: string; keyword: string; mention_count: number }>(
    (from, to) =>
      db
        .from("telegram_keyword_daily")
        .select("date,keyword,mention_count")
        .gte("date", daysAgoISO(14).slice(0, 10))
        .order("date")
        .range(from, to),
  );
  if (!data.length) return [];

  const dates = [...new Set(data.map((r) => r.date))].sort();
  const latestDate = dates[dates.length - 1];
  const DAY = 24 * 60 * 60 * 1000;
  const daysBefore = (d: string) => (new Date(latestDate).getTime() - new Date(d).getTime()) / DAY;

  const recentDates = new Set(dates.slice(-3));
  const priorDates = new Set(dates.filter((d) => daysBefore(d) >= 5));
  const last7 = new Set(dates.filter((d) => daysBefore(d) < 7));

  // 그날 전체 화제어 언급 합 — 점유율의 분모.
  const dayTotal = new Map<string, number>();
  for (const r of data) {
    dayTotal.set(r.date, (dayTotal.get(r.date) ?? 0) + (r.mention_count ?? 0));
  }

  const total = new Map<string, number>();
  const recentShare = new Map<string, number>();
  const priorShare = new Map<string, number>();
  for (const r of data) {
    const n = r.mention_count ?? 0;
    if (last7.has(r.date)) total.set(r.keyword, (total.get(r.keyword) ?? 0) + n);
    const share = n / Math.max(dayTotal.get(r.date) ?? 1, 1);
    if (recentDates.has(r.date)) {
      recentShare.set(r.keyword, (recentShare.get(r.keyword) ?? 0) + share);
    }
    if (priorDates.has(r.date)) {
      priorShare.set(r.keyword, (priorShare.get(r.keyword) ?? 0) + share);
    }
  }

  const canCompare = priorDates.size > 0;
  return [...total.entries()]
    .filter(([, count]) => count >= MIN_KEYWORD_MENTIONS)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([word, count]) => {
      // 창 길이가 다르므로 '하루 평균 점유율'로 맞춰 비교한다.
      // 그날 등장하지 않은 화제어는 점유율 0으로 치므로 창 전체 일수로 나눈다.
      const recentAvg = (recentShare.get(word) ?? 0) / Math.max(recentDates.size, 1);
      const priorAvg = (priorShare.get(word) ?? 0) / Math.max(priorDates.size, 1);
      // 부동소수 비교라 정확히 같은 경우는 드물다 — 점유율 차이가 무시할 수준이면
      // 'flat' 으로 본다. 둘 다 0인 경우(최근 창에 한 번도 안 나온 말)도 여기 걸린다.
      const FLAT = 1e-6;
      const trend: IssueKeyword["trend"] = !canCompare
        ? null
        : Math.abs(recentAvg - priorAvg) < FLAT
          ? "flat"
          : recentAvg > priorAvg
            ? "up"
            : "down";
      return { word, count, trend };
    });
}

/**
 * 종목별 흐름 요약(LLM) — 가장 최근에 생성된 날짜분을 종목코드로 찾아 쓴다.
 * 파이프라인이 상위 몇 종목만 만들므로, 없는 종목은 카드에서 문단이 빠진다.
 */
export async function getStockNarratives(): Promise<Record<string, string>> {
  const db = getSupabaseAdmin();
  const { data: latest } = await db
    .from("telegram_stock_narrative")
    .select("date")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!latest?.date) return {};

  const { data } = await db
    .from("telegram_stock_narrative")
    .select("stock_code,narrative")
    .eq("date", latest.date);
  return Object.fromEntries((data ?? []).map((r) => [r.stock_code as string, r.narrative as string]));
}
