import "server-only";

import { getSupabaseAdmin } from "@/lib/supabase-server";

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

  const { data: recent } = await db
    .from("telegram_messages")
    .select("channel_handle")
    .gte("posted_at", daysAgoISO(7));
  const activeChannels = new Set((recent ?? []).map((r) => r.channel_handle)).size;
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

type DailyRow = { stock_code: string; date: string; weighted_score: number; mention_count: number; channel_count: number };

async function loadStockDaily(days: number): Promise<{ rows: DailyRow[]; dates: string[] }> {
  const db = getSupabaseAdmin();
  const { data } = await db
    .from("telegram_stock_daily")
    .select("stock_code,date,weighted_score,mention_count,channel_count")
    .gte("date", daysAgoISO(days).slice(0, 10));
  // 오늘은 아직 하루가 덜 차서 일평균·추이를 왜곡한다 — 완료된 날만 쓴다.
  const today = todayKstDate();
  const rows = ((data ?? []) as DailyRow[]).filter((r) => r.date < today);
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
 * 야후 파이낸스 실시간 시세(상단 티커와 같은 소스). KRX Open API는 며칠 지연돼
 * 티커의 실시간 값과 크게 어긋나므로, 표시용 가격은 여기서 우선 가져온다.
 * 실패하면 호출부가 KRX 저장 종가로 폴백한다.
 */
async function fetchYahooQuote(symbol: string): Promise<{ price: number; changeRate: number } | null> {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=5d`,
      { headers: { "User-Agent": "Mozilla/5.0" }, next: { revalidate: 600 } },
    );
    if (!res.ok) return null;
    const result = (await res.json())?.chart?.result?.[0];
    const price = result?.meta?.regularMarketPrice;
    if (typeof price !== "number") return null;

    // 전일 종가 판정은 상단 티커(app/api/ticker)와 동일한 규칙을 쓴다 — 같은 종목이
    // 두 곳에서 다른 등락률로 보이지 않도록. 마지막 일봉 종가가 현재가와 (거의) 같으면
    // 그건 진행 중인 오늘 세션이므로 그 직전 종가를 전일로 삼는다.
    const closes: number[] = (result?.indicators?.quote?.[0]?.close ?? []).filter(
      (x: unknown): x is number => typeof x === "number",
    );
    let prev: number | null = null;
    if (closes.length >= 1) {
      const last = closes[closes.length - 1];
      const lastIsCurrent = Math.abs(last - price) / price < 0.0005;
      prev = lastIsCurrent ? (closes.length >= 2 ? closes[closes.length - 2] : null) : last;
    }
    if (prev === null && typeof result?.meta?.chartPreviousClose === "number") prev = result.meta.chartPreviousClose;
    if (typeof prev !== "number" || !prev) return null;
    return { price, changeRate: (price / prev - 1) * 100 };
  } catch {
    return null;
  }
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

  const list = [...byStock.entries()]
    .filter(([, a]) => a.recentM >= 2) // 1회성 언급 노이즈 제거
    .map(([code, a]) => {
      const recentPerDay = a.recentShare / recentDateList.length;
      const base = a.priorShare / priorCount;
      const info = infoOf.get(code);
      return {
        code,
        name: info?.name ?? code,
        recentMentions: a.recentM,
        channelCount: a.channels,
        ratio: base > 0 ? recentPerDay / base : Infinity,
        isNew: base === 0,
        series: dates.map((d) => a.byDate.get(d) ?? 0),
        market: info?.market ?? null,
        closePrice: info?.closePrice ?? null,
        changeRate: info?.changeRate ?? null,
        priceDate: info?.priceDate ?? null,
        isLive: false,
      };
    })
    .filter((s) => s.ratio >= 1.3 || s.isNew) // 평소보다 뚜렷하게 뛴 것만
    // 신규 등장(ratio=Infinity)이 정렬을 독점하지 않도록 유한한 강도로 환산해
    // 배수 급증주와 같은 축에서 비교한다.
    .sort((x, y) => {
      const strength = (s: SurgingStock) => (s.isNew ? (s.recentMentions >= 3 ? 3 : 2) : s.ratio);
      return strength(y) - strength(x) || y.recentMentions - x.recentMentions;
    })
    .slice(0, limit);

  // 표시용 가격은 실시간(야후) 우선 — KRX 저장 종가는 며칠 지연돼 상단 티커와 어긋난다.
  // 조회 실패 시 KRX 종가(priceDate 라벨과 함께)를 그대로 쓴다.
  const quotes = await Promise.all(
    list.map((s) => fetchYahooQuote(`${s.code}.${s.market === "KOSDAQ" ? "KQ" : "KS"}`)),
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

/** 트렌딩 메시지 TOP N (창: windowDays). 점수는 view가 지배적이라 view순으로 후보를 좁힌 뒤 정확 점수로 정렬. */
export async function getTrendingMessages(windowDays: number, limit = 8): Promise<TrendingMessage[]> {
  const db = getSupabaseAdmin();
  const { data: msgs } = await db
    .from("telegram_messages")
    .select("channel_handle,message_id,text,views,forwards,replies,posted_at")
    .gte("posted_at", daysAgoISO(windowDays))
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
  const { data: tags } = await db
    .from("telegram_message_stocks")
    .select("channel_handle,message_id,stock_code")
    .in("message_id", top.map((m) => m.messageId));

  if (tags?.length) {
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
  topChannels: { title: string; count: number }[];
  channelCount: number; // 이 종목을 다룬 서로 다른 채널 수(관심의 폭)
  price: number | null; // 실시간 시세
  changeRate: number | null;
  topMessage: { text: string; channelTitle: string; views: number; forwards: number } | null;
};

/** 종목 텔레그램 리포트 — 특정 종목의 일별 언급 추이 + 언급 상위 채널. */
export async function getStockReport(code: string): Promise<StockReport | null> {
  const db = getSupabaseAdmin();
  const { data: stock } = await db.from("stocks").select("name,market").eq("code", code).maybeSingle();
  if (!stock) return null;

  const { data: daily } = await db
    .from("telegram_stock_daily")
    .select("date,mention_count")
    .eq("stock_code", code)
    .gte("date", daysAgoISO(10).slice(0, 10))
    .order("date");
  const today = todayKstDate();
  const series = (daily ?? []).filter((d) => d.date < today).map((d) => ({ date: d.date, mentions: d.mention_count || 0 }));
  const totalMentions = series.reduce((s, d) => s + d.mentions, 0);

  const { data: mentions } = await db
    .from("telegram_message_stocks")
    .select("channel_handle,message_id")
    .eq("stock_code", code);
  const counts = new Map<string, number>();
  for (const m of mentions ?? []) counts.set(m.channel_handle, (counts.get(m.channel_handle) ?? 0) + 1);

  const { data: channels } = await db.from("telegram_channels").select("handle,title");
  const titleOf = new Map((channels ?? []).map((c) => [c.handle, (c.title as string) ?? c.handle]));
  const topChannels = [...counts.entries()]
    .map(([h, count]) => ({ title: titleOf.get(h) ?? h, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 3);

  // 대표 메시지 — 이 종목을 언급한 메시지 중 가장 널리 퍼진 것. "왜 화제인지"를 보여준다.
  let topMessage: StockReport["topMessage"] = null;
  const ids = [...new Set((mentions ?? []).map((m) => m.message_id))].slice(0, 300);
  if (ids.length) {
    const { data: msgs } = await db
      .from("telegram_messages")
      .select("channel_handle,message_id,text,views,forwards,replies")
      .in("message_id", ids)
      .not("text", "is", null)
      .order("views", { ascending: false, nullsFirst: false })
      .limit(50);
    const pairs = new Set((mentions ?? []).map((m) => `${m.channel_handle}|${m.message_id}`));
    const best = (msgs ?? [])
      .filter((m) => pairs.has(`${m.channel_handle}|${m.message_id}`))
      .map((m) => ({
        text: (m.text ?? "").replace(/\s+/g, " ").trim(),
        channelTitle: titleOf.get(m.channel_handle) ?? m.channel_handle,
        views: m.views ?? 0,
        forwards: m.forwards ?? 0,
        score: (m.views ?? 0) * TREND_W_VIEWS + (m.forwards ?? 0) * TREND_W_FWD + (m.replies ?? 0) * TREND_W_REPLIES,
      }))
      .sort((a, b) => b.score - a.score)[0];
    if (best) topMessage = { text: best.text, channelTitle: best.channelTitle, views: best.views, forwards: best.forwards };
  }

  const quote = await fetchYahooQuote(`${code}.${stock.market === "KOSDAQ" ? "KQ" : "KS"}`);

  return {
    code,
    name: stock.name as string,
    totalMentions,
    series,
    topChannels,
    channelCount: counts.size,
    price: quote ? Math.round(quote.price) : null,
    changeRate: quote ? quote.changeRate : null,
    topMessage,
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

  const avgShare = (window: string[]) => {
    const sum = new Map<string, number>();
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
  const { data: stats } = await db
    .from("telegram_channel_stats")
    .select("channel_handle,date,subscriber_count,influence_score,view_rate,is_growing")
    .not("influence_score", "is", null)
    .order("date", { ascending: false });
  if (!stats?.length) return [];

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
  handle: string | null; // 실데이터일 때만 존재(데모 채널은 실제 링크 대상이 없음)
  title: string;
  photo: string | null;
  subscriberCount: number;
  delta7d: number;
  isPlaceholder: boolean;
};

/**
 * 뜨는 채널(7일 구독자 증가). 스냅샷이 아직 7일치가 없어 실제 증감을 못 구하면
 * 완성본처럼 보이도록 데모 데이터로 채운다 — 7일치가 쌓이면 실데이터로 자동 대체된다.
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

  const real: RisingChannel[] = [];
  for (const [h, arr] of byCh) {
    if (arr.length < 2) continue;
    arr.sort((a, b) => a.d.localeCompare(b.d));
    const delta = arr[arr.length - 1].s - arr[0].s;
    if (delta <= 0) continue; // "뜨는" 채널이므로 실제로 늘어난 곳만
    real.push({
      handle: h,
      title: titleOf.get(h) ?? h,
      photo: photoOf.get(h) ?? null,
      subscriberCount: arr[arr.length - 1].s,
      delta7d: delta,
      isPlaceholder: false,
    });
  }
  // 스냅샷이 며칠치뿐이면 "7일 증가"가 사실상 하루치 차이라 카드 의미가 없다
  // (▲0명·▲-1명 같은 값이 뜬다). 충분히 쌓인 뒤에만 실데이터로 전환한다.
  const snapshotDays = new Set((data ?? []).map((r) => r.date)).size;
  if (snapshotDays >= 5 && real.length >= 3) {
    return real.sort((a, b) => b.delta7d - a.delta7d).slice(0, limit);
  }

  // TODO(스냅샷 7일치 축적 후 제거): 데모용 placeholder 데이터.
  return [
    { handle: null, title: "급등주 라이브", photo: null, subscriberCount: 58200, delta7d: 4300, isPlaceholder: false },
    { handle: null, title: "실전 투자노트", photo: null, subscriberCount: 46700, delta7d: 3150, isPlaceholder: false },
    { handle: null, title: "테마주 헌터", photo: null, subscriberCount: 33400, delta7d: 2480, isPlaceholder: false },
    { handle: null, title: "코스닥 스나이퍼", photo: null, subscriberCount: 21900, delta7d: 1760, isPlaceholder: false },
    { handle: null, title: "새벽 차트방", photo: null, subscriberCount: 15600, delta7d: 1210, isPlaceholder: false },
    { handle: null, title: "반도체 소부장 인사이트", photo: null, subscriberCount: 28800, delta7d: 1120, isPlaceholder: false },
    { handle: null, title: "미국주식 야간반", photo: null, subscriberCount: 41300, delta7d: 980, isPlaceholder: false },
    { handle: null, title: "공시 알리미", photo: null, subscriberCount: 19400, delta7d: 870, isPlaceholder: false },
    { handle: null, title: "배당주 모임", photo: null, subscriberCount: 12700, delta7d: 640, isPlaceholder: false },
    { handle: null, title: "IPO 공모주 캘린더", photo: null, subscriberCount: 24100, delta7d: 520, isPlaceholder: false },
  ].slice(0, limit);
}
