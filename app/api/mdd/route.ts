import { NextResponse } from "next/server";

import { analyzeDrawdown, drawdownSeries, type Bar } from "@/lib/mdd";
import { getSupabaseServer } from "@/lib/supabase-server";
import { themesForName, THEMES } from "@/lib/stock-themes";
import { fetchDailyHistory, yahooSymbol } from "@/lib/yahoo-history";

// MDD(최대낙폭) 분석. 야후 일봉을 호출 시점에 직접 받아 계산하고, 상단 티커
// (/api/ticker)와 같은 방식으로 CDN 에 15분 캐시한다 — 별도 크론·DB 없이.
// 일봉은 하루 한 번 바뀌므로 이 정도 캐시로 야후 부하를 충분히 던다.
export const dynamic = "force-dynamic";
// 시장·테마 대표 종목(최대 10개+코스피)의 히스토리를 병렬 조회한다. 넉넉히 준다.
export const maxDuration = 20;

/** 기간 프리셋(년). "all"은 상장 이후 전체(야후가 상장 이후만 준다). */
const YEARS: Record<string, number> = { "1": 1, "3": 3, "5": 5, "10": 10, all: 100 };
/** 코스피 지수 심볼 — 시장 대비 비교의 기준. 상단 티커와 같은 심볼을 쓴다. */
const KOSPI = "^KS11";

type Peer = { name: string; code: string; dd: number; isSelf: boolean };
type Theme = { name: string; peers: Peer[]; avgDd: number; sincePeakAvg: number | null };

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = (searchParams.get("code") ?? "").trim();
  const market = searchParams.get("market");
  const name = (searchParams.get("name") ?? "").trim();
  const yearsKey = searchParams.get("years") ?? "10";
  const years = YEARS[yearsKey] ?? 10;

  if (!/^[0-9A-Z]{6}$/.test(code)) {
    return NextResponse.json({ ok: false, error: "종목 코드가 올바르지 않습니다." }, { status: 400 });
  }

  const symbol = yahooSymbol(code, market);
  const bars = await fetchDailyHistory(symbol, years);
  const analysis = bars ? analyzeDrawdown(bars) : null;
  if (!analysis) {
    return NextResponse.json(
      { ok: false, error: "이 종목의 과거 시세를 불러오지 못했습니다." },
      { status: 502 },
    );
  }

  // 신고가 부근이면 설명할 하락 자체가 없다 — 원인 분해·시장 비교를 건너뛴다.
  const atHigh = analysis.currentDd > -1;
  const athDate = analysis.athDate;

  const [marketBars, theme] = await Promise.all([
    atHigh ? Promise.resolve(null) : fetchDailyHistory(KOSPI, years),
    buildThemeComparison(name, market, years, analysis.currentDd, athDate),
  ]);

  // 원인 분해 — 이 종목의 고점 이후, 같은 기간 시장·테마는 얼마나 움직였나.
  // stock 은 곧 currentDd(고점 이후 수익률과 같다). 시장·테마와 나란히 놓아
  // "시장 탓인가 종목 탓인가"를 보여준다. 정밀 요인분해가 아니라 같은 창 비교다.
  const marketSincePeak = marketBars ? returnSince(marketBars, athDate) : null;
  const attribution =
    !atHigh && (marketSincePeak !== null || theme?.sincePeakAvg != null)
      ? {
          sincePeakDays: daysBetween(athDate, analysis.asOf),
          stock: analysis.currentDd,
          market: marketSincePeak,
          theme: theme?.sincePeakAvg ?? null,
        }
      : null;

  return NextResponse.json(
    { ok: true, code, name, market, symbol, years: yearsKey, analysis, attribution, theme },
    { headers: { "Cache-Control": "public, s-maxage=900, stale-while-revalidate=600" } },
  );
}

const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);

/**
 * 기준일(date) 이후 마지막까지의 수익률(%). date 당시 이 종목이 존재해야 의미가
 * 있으므로, date 이상인 첫 봉이 date 로부터 14일 넘게 떨어져 있으면(=그때 상장 전)
 * 계산하지 않고 null 을 준다.
 */
function returnSince(bars: Bar[], date: string, toleranceDays = 14): number | null {
  const start = bars.find((b) => b.date >= date);
  if (!start || daysBetween(date, start.date) > toleranceDays) return null;
  const last = bars[bars.length - 1];
  if (last.date <= start.date) return null;
  return (last.close / start.close - 1) * 100;
}

/**
 * 같은 테마 대표 종목 비교. 두 가지를 함께 낸다:
 *  - peers/avgDd: 각 종목의 '현재 낙폭'(자기 고점 대비) — 테마 안 회복력 순위.
 *  - sincePeakAvg: '이 종목의 고점 이후' 같은 기간 대표 종목들의 평균 수익률 — 원인 분해용.
 * 자기 종목은 이미 계산한 currentDd 를 재사용하고, 나머지 피어만 병렬 조회한다.
 * 어느 테마에도 없으면 null(테마 카드를 띄우지 않는다).
 */
async function buildThemeComparison(
  name: string,
  market: string | null,
  years: number,
  selfDd: number,
  athDate: string,
): Promise<Theme | null> {
  if (!name) return null;
  const matched = themesForName(name);
  if (matched.length === 0) return null;
  const themeName = matched[0]; // 여러 테마에 걸치면 첫 번째(사전 순서 = 대표성 순서)
  const memberNames = THEMES[themeName].filter((n) => n !== name);

  // 대표 종목의 코드·시장을 stocks(공개 read)에서 한 번에 받는다. 이름은 KRX 정식명과
  // 정확히 일치한다(사전이 그 전제로 큐레이션돼 있다). 최대 10개라 1000행 캡과 무관.
  let members: { code: string; name: string; market: string | null }[] = [];
  try {
    const { data } = await getSupabaseServer()
      .from("stocks")
      .select("code, name, market")
      .in("name", memberNames);
    members = data ?? [];
  } catch {
    members = [];
  }

  const fetched = await Promise.all(
    members.map(async (m) => {
      const bars = await fetchDailyHistory(yahooSymbol(m.code, m.market), years);
      if (!bars) return null;
      const ds = drawdownSeries(bars);
      return { name: m.name, code: m.code, dd: ds[ds.length - 1].dd, sincePeak: returnSince(bars, athDate) };
    }),
  );

  const ok = fetched.filter((p): p is NonNullable<typeof p> => p !== null);
  const peers: Peer[] = ok.map((p) => ({ name: p.name, code: p.code, dd: p.dd, isSelf: false }));
  peers.push({ name, code: "", dd: selfDd, isSelf: true });
  peers.sort((a, b) => a.dd - b.dd); // 깊게 빠진 순

  // 자기 종목만 남으면(피어를 하나도 못 받음) 비교의 의미가 없다.
  if (peers.length < 2) return null;

  const avgDd = peers.reduce((s, p) => s + p.dd, 0) / peers.length;
  const sinceVals = ok.map((p) => p.sincePeak).filter((v): v is number => v !== null);
  const sincePeakAvg = sinceVals.length ? sinceVals.reduce((s, v) => s + v, 0) / sinceVals.length : null;

  return { name: themeName, peers, avgDd, sincePeakAvg };
}
