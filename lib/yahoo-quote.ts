import "server-only";

/**
 * 야후 파이낸스 시세 조회 — 상단 티커와 카더라 리포트가 함께 쓴다.
 *
 * 두 곳에 같은 코드가 복붙돼 있었는데, 실제로 한 번 어긋난 적이 있다(종목 리포트의
 * 등락률이 상단 티커와 달라 보였다). 같은 종목이 화면 두 곳에서 다른 등락률로 보이면
 * 그 자체가 버그라, 전일 종가 판정 규칙을 여기 한 곳에만 둔다.
 */

export type YahooQuote = {
  price: number;
  /** 전일 종가. 판정 불가면 null — 등락률을 못 낸다는 뜻. */
  prevClose: number | null;
};

/** Next 의 fetch 확장(next.revalidate)까지 받는 init 타입. */
type FetchInit = RequestInit & { next?: { revalidate?: number } };

/**
 * 전일 종가 판정: 일봉 배열이 심볼마다 오늘 바를 다르게 반영한다 — 선물은 마지막 바가
 * 진행 중인 현재 세션(close == 현재가)이고, KR 지수는 오늘 바가 늦게 붙어 마지막 바가
 * 어제인 경우도 있다. 그래서 "마지막 종가가 현재가와 (거의) 같으면 그건 현재 세션이므로
 * 그 직전 종가를, 다르면 마지막 종가를" 전일로 삼는다.
 */
function resolvePrevClose(closes: number[], price: number, chartPreviousClose: unknown): number | null {
  let prev: number | null = null;
  if (closes.length >= 1) {
    const last = closes[closes.length - 1];
    const lastIsCurrent = Math.abs(last - price) / price < 0.0005;
    prev = lastIsCurrent ? (closes.length >= 2 ? closes[closes.length - 2] : null) : last;
  }
  if (prev === null && typeof chartPreviousClose === "number") prev = chartPreviousClose;
  return prev;
}

/** 시세를 가져온다. 실패(네트워크·비정상 응답·가격 없음)면 null. */
export async function fetchYahooQuote(symbol: string, init: FetchInit): Promise<YahooQuote | null> {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=5d`,
      { headers: { "User-Agent": "Mozilla/5.0" }, ...init },
    );
    if (!res.ok) return null;
    const result = (await res.json())?.chart?.result?.[0];
    const price = result?.meta?.regularMarketPrice;
    if (typeof price !== "number") return null;

    const closes: number[] = (result?.indicators?.quote?.[0]?.close ?? []).filter(
      (x: unknown): x is number => typeof x === "number",
    );
    return { price, prevClose: resolvePrevClose(closes, price, result?.meta?.chartPreviousClose) };
  } catch {
    return null;
  }
}

/** 등락률(%). 전일 종가를 못 구했으면 null. */
export function changeRateOf(q: YahooQuote): number | null {
  return typeof q.prevClose === "number" && q.prevClose !== 0 ? (q.price / q.prevClose - 1) * 100 : null;
}
