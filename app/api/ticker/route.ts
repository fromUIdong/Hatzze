import { NextResponse } from "next/server";

import { changeRateOf, fetchYahooQuote } from "@/lib/yahoo-quote";

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
  // 조회·전일종가 판정은 lib/yahoo-quote 한 곳에 있다 — 카더라 리포트의 종목 카드가
  // 같은 규칙을 써야 같은 종목이 두 화면에서 다른 등락률로 보이지 않는다.
  const q = await fetchYahooQuote(item.symbol, { cache: "no-store" });
  if (!q) return fallback;
  return { key: item.key, label: item.label, value: fmt(q.price, item.digits), change: changeRateOf(q) };
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
