import "server-only";

import type { Bar } from "@/lib/mdd";

/**
 * 야후 파이낸스 일봉 히스토리 조회 — MDD 분석용(server-only).
 *
 * 상단 티커·카더라의 현재가 조회(lib/yahoo-quote.ts)와 달리, 여기는 과거 수년치
 * 일봉 종가 배열이 필요하다. 두 가지 함정을 피한다:
 *
 *  1) `range=max` 로 부르면 야후가 interval 을 **조용히 무시하고 월봉**을 준다
 *     (355개월=356포인트). 그걸로 MDD 를 내면 −60% 처럼 그럴듯하지만 틀린 값이
 *     나온다(일봉 실제 −64.7%). 그래서 range 가 아니라 period1/period2 를 명시해
 *     일봉을 강제한다.
 *  2) close 는 수정주가(분할·감자 소급 반영)라 그대로 쓰고, adjclose 는 감자에서
 *     음수가 나오는 등 깨져 있어 쓰지 않는다(lib/mdd.ts 주석 참고).
 */

const SECONDS_PER_YEAR = 365 * 24 * 60 * 60;

/**
 * @param symbol 야후 심볼(예: "005930.KS", "000660.KS", "247540.KQ")
 * @param years  조회 기간(년). 넉넉히 받아와도 상장 이후만 돌아온다.
 * @returns 오래된→최신 순서의 일봉 종가. 실패(네트워크·비정상 응답·데이터 없음)면 null.
 */
export async function fetchDailyHistory(
  symbol: string,
  years: number,
): Promise<Bar[] | null> {
  const now = Math.floor(Date.now() / 1000);
  // 전체(years 아주 큼)여도 야후는 상장 이후만 준다. 여유로 하루 더 뺀다.
  const period1 = years >= 100 ? 0 : Math.max(0, now - Math.ceil(years * SECONDS_PER_YEAR) - 86_400);
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?period1=${period1}&period2=${now}&interval=1d`;

  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0" },
      // 일봉은 하루 한 번 바뀐다. 라우트가 CDN s-maxage 로도 감싸지만, 데이터
      // 캐시로도 15분 재검증을 걸어 같은 심볼 반복 조회의 야후 왕복을 줄인다.
      next: { revalidate: 900 },
    });
    if (!res.ok) return null;

    const result = (await res.json())?.chart?.result?.[0];
    const timestamps: unknown = result?.timestamp;
    const closes: unknown = result?.indicators?.quote?.[0]?.close;
    if (!Array.isArray(timestamps) || !Array.isArray(closes)) return null;

    const bars: Bar[] = [];
    for (let i = 0; i < timestamps.length; i++) {
      const t = timestamps[i];
      const c = closes[i];
      if (typeof t !== "number" || typeof c !== "number") continue; // 휴장·결측 봉은 건너뛴다
      bars.push({ date: new Date(t * 1000).toISOString().slice(0, 10), close: c });
    }
    return bars.length >= 2 ? bars : null;
  } catch {
    return null;
  }
}

/** KRX 시장 구분 → 야후 심볼 접미사. */
export function yahooSymbol(code: string, market: string | null | undefined): string {
  const suffix = market === "KOSDAQ" ? ".KQ" : ".KS";
  return `${code}${suffix}`;
}
