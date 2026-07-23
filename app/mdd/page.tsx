import type { Metadata } from "next";

import { getSupabaseServer } from "@/lib/supabase-server";
import { MddExplorer, type StockOption } from "./MddExplorer";

export const metadata: Metadata = {
  title: "MDD 정밀분석 | hatzze",
  description:
    "종목별 고점 대비 낙폭과 과거 회복 기간을 봅니다. 지금 얼마나 빠졌는지, 이만큼 빠졌던 적이 얼마나 드문지, 회복까지 얼마나 걸렸는지.",
  alternates: { canonical: "/mdd" },
};

export const dynamic = "force-dynamic";

/**
 * MDD 분석 페이지. 검색용 종목 목록(코스피)만 서버가 실어 내려주고, 실제 낙폭
 * 계산은 클라이언트가 /api/mdd 를 호출해 받는다(상단 티커와 같은 온디맨드 방식).
 *
 * 코스피만 싣는 이유: (1) 첫 화면은 코스피부터 노출하기로 했고, (2) 코스닥은
 * 감자·합병·상폐가 잦아 수정주가 함정 검증을 한 번 더 하고 열기로 해서다.
 * 944행이라 PostgREST 1000행 캡 아래다. /api/mdd 자체는 코스닥 코드도 처리한다
 * (테마 비교의 코스닥 대표 종목은 그 경로로 이미 들어온다).
 */
async function loadKospiStocks(): Promise<StockOption[]> {
  try {
    const { data } = await getSupabaseServer()
      .from("stocks")
      .select("code, name, market")
      .eq("market", "KOSPI")
      .order("name", { ascending: true });
    return (data ?? []) as StockOption[];
  } catch {
    return [];
  }
}

/**
 * URL 파라미터로 특정 종목을 지정할 수 있다 — 카더라 리포트의 '급부상 종목'·'주요 종목
 * 리포트' 카드가 이 링크로 해당 종목 MDD 를 연다. URL 은 code·market 만 실어 깔끔하게
 * 두고(예: /mdd?code=058610&market=KOSDAQ), 이름은 여기서 code 로 stocks 에서 찾는다.
 * code 형식이 틀리면 null(기본 종목으로 연다).
 */
async function resolveInitial(sp: Record<string, string | string[] | undefined>): Promise<StockOption | null> {
  const code = typeof sp.code === "string" ? sp.code.trim() : "";
  if (!/^[0-9A-Z]{6}$/.test(code)) return null;
  const marketParam = sp.market === "KOSDAQ" ? "KOSDAQ" : sp.market === "KOSPI" ? "KOSPI" : null;

  // 이름을 code 로 조회한다. stocks 에 없으면(상폐·외국주 등) 이름 자리에 code 를 쓰고
  // market 은 URL 값을 그대로 믿는다 — 심볼(.KS/.KQ)만 맞으면 낙폭은 계산된다.
  let name = code;
  let market = marketParam;
  try {
    const { data } = await getSupabaseServer()
      .from("stocks")
      .select("name, market")
      .eq("code", code)
      .maybeSingle();
    if (data) {
      name = (data.name as string) ?? code;
      market = marketParam ?? ((data.market as string) ?? null);
    }
  } catch {
    // 조회 실패 시 위 기본값(code·URL market)으로 진행
  }
  return { code, name, market };
}

export default async function MddPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const [stocks, initial] = await Promise.all([loadKospiStocks(), resolveInitial(sp)]);
  // key 로 초기 종목이 바뀌면 리마운트 — /mdd?code=A → ?code=B 로 이동해도 반영된다.
  return <MddExplorer key={initial?.code ?? "default"} stocks={stocks} initial={initial} />;
}
