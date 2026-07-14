import { NextResponse } from "next/server";

// 탑바 시세 티커용 라이브 시세. 야후 파이낸스 차트 JSON(지수·종목·환율·나스닥 선물)과
// 업비트 API(비트코인, KRW)에서 모아 반환한다. 별도 크론/DB 없이 이 라우트가
// 호출될 때 소스에서 직접 가져오되, CDN에 10분 캐시(s-maxage)를 걸어 소스를
// 과도하게 때리지 않는다. 탑바(클라이언트)는 10분마다 이 라우트를 폴링한다.
export const dynamic = "force-dynamic";

type Quote = { key: string; label: string; value: string; change: number | null };

const YAHOO: { key: string; label: string; symbol: string; digits: number }[] = [
  { key: "nasdaq", label: "나스닥 선물", symbol: "NQ=F", digits: 0 },
  { key: "kospi", label: "코스피", symbol: "^KS11", digits: 2 },
  { key: "kosdaq", label: "코스닥", symbol: "^KQ11", digits: 2 },
  { key: "samsung", label: "삼성전자", symbol: "005930.KS", digits: 0 },
  { key: "skhynix", label: "SK하이닉스", symbol: "000660.KS", digits: 0 },
  { key: "usdkrw", label: "원/달러", symbol: "KRW=X", digits: 1 },
];

const fmt = (n: number, digits: number) =>
  n.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

async function fetchYahoo(item: (typeof YAHOO)[number]): Promise<Quote> {
  const fallback: Quote = { key: item.key, label: item.label, value: "—", change: null };
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(item.symbol)}?interval=1d&range=5d`,
      { headers: { "User-Agent": "Mozilla/5.0" }, cache: "no-store" },
    );
    if (!res.ok) return fallback;
    const result = (await res.json())?.chart?.result?.[0];
    const meta = result?.meta;
    const price = meta?.regularMarketPrice;
    if (typeof price !== "number") return fallback;
    // 전일 종가: 일봉 배열이 심볼마다 오늘 바를 다르게 반영한다 — 선물은 마지막 바가
    // 진행 중인 현재 세션(close == 현재가)이고, KR 지수는 오늘 바가 늦게 붙어 마지막
    // 바가 어제인 경우도 있다. 그래서 "마지막 종가가 현재가와 (거의) 같으면 그건 현재
    // 세션이므로 그 직전 종가를, 다르면 마지막 종가를" 전일로 삼는다.
    const closes: number[] = (result?.indicators?.quote?.[0]?.close ?? []).filter(
      (x: unknown): x is number => typeof x === "number",
    );
    let prev: number | null = null;
    if (closes.length >= 1) {
      const last = closes[closes.length - 1];
      const lastIsCurrent = Math.abs(last - price) / price < 0.0005;
      prev = lastIsCurrent ? (closes.length >= 2 ? closes[closes.length - 2] : null) : last;
    }
    if (prev === null && typeof meta?.chartPreviousClose === "number") prev = meta.chartPreviousClose;
    const change = typeof prev === "number" && prev !== 0 ? (price / prev - 1) * 100 : null;
    return { key: item.key, label: item.label, value: fmt(price, item.digits), change };
  } catch {
    return fallback;
  }
}

async function fetchBtc(): Promise<Quote> {
  const fallback: Quote = { key: "btc", label: "비트코인", value: "—", change: null };
  try {
    const res = await fetch("https://api.upbit.com/v1/ticker?markets=KRW-BTC", { cache: "no-store" });
    if (!res.ok) return fallback;
    const t = (await res.json())?.[0];
    const price = t?.trade_price;
    if (typeof price !== "number") return fallback;
    // KRW 절대값은 자리가 길어 억 단위로 압축해 보여준다(예: 1.38억).
    const value = `${(price / 1e8).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}억`;
    const change = typeof t?.signed_change_rate === "number" ? t.signed_change_rate * 100 : null;
    return { key: "btc", label: "비트코인", value, change };
  } catch {
    return fallback;
  }
}

export async function GET() {
  const [nasdaq, kospi, kosdaq, samsung, skhynix, usdkrw, btc] = await Promise.all([
    ...YAHOO.map(fetchYahoo),
    fetchBtc(),
  ]);
  // 원하는 티커 순서: 나스닥 선물 · 코스피 · 코스닥 · 삼성전자 · SK하이닉스 · 비트코인 · 원/달러
  const quotes: Quote[] = [nasdaq, kospi, kosdaq, samsung, skhynix, btc, usdkrw];

  return NextResponse.json(
    { quotes, updatedAt: new Date().toISOString() },
    { headers: { "Cache-Control": "public, s-maxage=600, stale-while-revalidate=300" } },
  );
}
