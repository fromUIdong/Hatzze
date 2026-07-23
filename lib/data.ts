import "server-only";

import { getDevOverrides } from "@/lib/dev-overrides";
import { getSupabaseServer } from "@/lib/supabase-server";
import { fetchYahooQuote } from "@/lib/yahoo-quote";

export type DailyScore = {
  date: string;
  score: number;
  stage: string;
  updated_at: string;
  // LLM(Claude Haiku)이 생성한 오늘의 요약. 컬럼이 없거나(마이그레이션 전) 아직
  // 생성 전이면 null이고, 이땐 히어로가 기존 템플릿 문장으로 폴백한다.
  ai_summary: string | null;
};

// 지표별 서브값(예: 레버리지의 ETF/선물 진행률, 매수쏠림의 매수/매도/CB 건수,
// 아시아의 각국 수익률). 카드가 목업 원본 시각화를 그릴 때 쓴다. 컬럼이 없거나
// 값이 아직 안 채워졌으면 null이고, 그 경우 카드는 단순화된 폴백으로 렌더된다.
export type IndicatorDetails = Record<string, number>;

export type IndicatorCategory = "시장" | "감성";

// 레거시 category 값(정통/밈)을 현재 명칭(시장/감성)으로 정규화한다. DB 마이그레이션
// 전/중에도 프론트가 항상 새 값을 보도록 하는 안전장치 — 마이그레이션 후엔 no-op.
function normalizeCategory(raw: string): IndicatorCategory {
  if (raw === "정통" || raw === "시장") return "시장";
  return "감성"; // "밈" 또는 "감성"
}

export type IndicatorWithLatestValue = {
  id: string;
  slug: string;
  name: string;
  headline: string | null;
  category: IndicatorCategory;
  description_beginner: string;
  unit: string;
  direction: "high" | "low";
  latest: {
    date: string;
    raw_value: number;
    normalized_score: number | null;
    threshold: number | null;
    details: IndicatorDetails | null;
  } | null;
  // 최근 ~30일 raw_value(시간순, 오래된→최신). 카드가 추세 스파크라인을 그릴 때 쓴다.
  history: number[];
  /** 스파크라인 툴팁용 — 값에 날짜를 붙인 것. 거래일은 주말·휴장을 건너뛰어 역산할 수 없다. */
  historyPoints: { date: string; value: number }[];
};

export async function getLatestDailyScore(): Promise<DailyScore | null> {
  const query = (cols: string) =>
    getSupabaseServer()
      .from("daily_score")
      .select(cols)
      .order("date", { ascending: false })
      .limit(1)
      .maybeSingle();

  // ai_summary 컬럼이 아직 없는 환경(마이그레이션 007 전)에서도 페이지가 죽지
  // 않도록, 포함 조회가 실패하면 그 컬럼 없이 한 번 더 조회한다.
  let { data, error } = await query("date,score,stage,updated_at,ai_summary");
  if (error) {
    ({ data, error } = await query("date,score,stage,updated_at"));
  }
  if (error) throw error;
  if (!data) return null;

  // 동적 select라 supabase-js가 타입을 추론하지 못해 명시적으로 캐스팅한다.
  const row = data as unknown as {
    date: string;
    score: number;
    stage: string;
    updated_at: string;
    ai_summary?: string | null;
  };

  // 로컬 dev 전용 오버레이(운영 빌드에선 no-op). 운영 DB에 요약을 쓰기 전에
  // 로컬에서만 미리 문장을 얹어 보기 위한 장치.
  const summaryOverride = getDevOverrides().summary;

  return {
    date: row.date,
    score: row.score,
    stage: row.stage,
    updated_at: row.updated_at,
    ai_summary: summaryOverride ?? row.ai_summary ?? null,
  };
}

export async function getPublicIndicators(): Promise<IndicatorWithLatestValue[]> {
  // is_public=false인 지표(예: kospi_close_raw)는 다른 지표를 계산하기 위한
  // 내부용 캐시라 화면에 노출하지 않는다. 그 외에는 새로 추가되는 지표도
  // 코드 수정 없이 자동으로 표시된다.
  const baseCols =
    "id, slug, name, headline, category, description_beginner, unit, direction, created_at";

  const query = (valueCols: string) =>
    getSupabaseServer()
      .from("indicators")
      .select(`${baseCols}, indicator_values ( ${valueCols} )`)
      .eq("is_public", true)
      .order("created_at", { ascending: true })
      .order("date", { referencedTable: "indicator_values", ascending: false })
      .limit(30, { referencedTable: "indicator_values" });

  // details(JSONB) 컬럼이 아직 없는 환경(마이그레이션 전)에서도 페이지가 죽지
  // 않도록, details 포함 조회가 실패하면 details 없이 한 번 더 조회한다.
  let { data, error } = await query(
    "date, raw_value, normalized_score, threshold, details",
  );
  if (error) {
    ({ data, error } = await query(
      "date, raw_value, normalized_score, threshold",
    ));
  }
  if (error) throw error;

  // 동적 select 문자열이라 supabase-js가 반환 타입을 추론하지 못해, 조회한
  // 컬럼과 일치하는 형태로 명시적으로 캐스팅한다.
  type RawRow = {
    id: string;
    slug: string;
    name: string;
    headline: string | null;
    category: string;
    description_beginner: string;
    unit: string;
    direction: "high" | "low";
    indicator_values: {
      date: string;
      raw_value: number;
      normalized_score: number | null;
      threshold: number | null;
      details?: IndicatorDetails | null;
    }[];
  };

  // 로컬 dev 전용 오버레이(운영 빌드에선 no-op). 설명/서브값을 운영 DB에 쓰기
  // 전에 로컬에서만 미리 보기 위해 slug별로 덮어쓴다.
  const overrides = getDevOverrides();

  return ((data ?? []) as unknown as RawRow[]).map((row) => {
    const iv = row.indicator_values[0];
    const nameOverride = overrides.names?.[row.slug];
    const descOverride = overrides.descriptions?.[row.slug];
    const detailsOverride = overrides.details?.[row.slug];
    const baseDetails =
      (iv as { details?: IndicatorDetails | null } | undefined)?.details ?? null;
    return {
      id: row.id,
      slug: row.slug,
      name: nameOverride ?? row.name,
      headline: row.headline,
      category: normalizeCategory(row.category),
      description_beginner: descOverride ?? row.description_beginner,
      unit: row.unit,
      direction: row.direction,
      latest: iv
        ? {
            date: iv.date,
            raw_value: iv.raw_value,
            normalized_score: iv.normalized_score,
            threshold: iv.threshold,
            details: detailsOverride
              ? { ...(baseDetails ?? {}), ...detailsOverride }
              : baseDetails,
          }
        : null,
      // 조회는 최신순이므로 뒤집어 시간순(오래된→최신)으로 둔다.
      history: [...row.indicator_values].reverse().map((v) => v.raw_value),
      historyPoints: [...row.indicator_values]
        .reverse()
        .map((v) => ({ date: v.date, value: v.raw_value })),
    };
  });
}

/** 거래대금 상위 종목의 52주 신고가 대비 괴리율 (코스피 신고가 카드의 오른쪽 칸). */
export type StockHighGap = {
  name: string;
  code: string;
  price: number;
  high52: number;
  gapPct: number; // 음수 = 고점 아래
};

/**
 * 거래대금 상위 3종목이 각자 52주 신고가에서 얼마나 떨어져 있는지.
 *
 * 지수 괴리율만 보면 "코스피가 고점 대비 -25%"라는 한 덩어리 숫자뿐이라, 그 안에서
 * 주도주들이 어떤 상태인지는 안 보인다. 거래대금 상위 종목(= 지금 돈이 몰리는 곳)의
 * 개별 괴리율을 같이 두면 지수 숫자가 어디서 온 건지 읽힌다.
 *
 * 종목 선정은 turnover_concentration 지표가 이미 저장해 둔 details.top5(거래대금 순)를
 * 재사용한다 — 같은 자료를 두 번 긁지 않기 위해서다.
 *
 * **KRX 종가 기준을 쓴다.** 예전엔 야후 실시간이었는데, 같은 카드 왼쪽의 지수 괴리율은
 * KRX 종가라 한 카드에서 잣대가 갈렸다 — 배지에 "7/22 기준"이라 적어도 이 숫자는 그
 * 날짜의 값이 아니었고, 야후의 52주 고점은 장중 고가 기준이라 종가 기준인 지수 쪽보다
 * 구조적으로 높게 나온다. 지금은 stocks.close_price / high_52w(둘 다 KRX 종가)를 쓴다.
 *
 * high_52w 가 아직 없는 환경(마이그레이션 019 전이거나 fetch_stock_high52.py 미실행)에서는
 * 야후로 폴백해 칸이 비지 않게 한다.
 */
export async function getTopStockHighGaps(limit = 3): Promise<StockHighGap[]> {
  const { data: rows } = await getSupabaseServer()
    .from("indicators")
    .select("id,indicator_values(date,details)")
    .eq("slug", "turnover_concentration")
    .order("date", { referencedTable: "indicator_values", ascending: false })
    .limit(1, { referencedTable: "indicator_values" })
    .maybeSingle();

  const details = rows?.indicator_values?.[0]?.details as { top5?: { name: string }[] } | null;
  const names = (details?.top5 ?? []).map((s) => s.name).slice(0, limit);
  if (!names.length) return [];

  type Row = { code: string; name: string; market: string | null; close_price: number | null; high_52w?: number | null };
  // high_52w 컬럼이 없는 환경(마이그레이션 019 전)에서도 죽지 않도록, 실패하면 그 컬럼
  // 없이 다시 조회한다 — getPublicIndicators 의 details 폴백과 같은 패턴.
  const pick = (cols: string) => getSupabaseServer().from("stocks").select(cols).in("name", names);
  // eslint-disable-next-line prefer-const -- stocks 는 폴백 조회에서 재대입된다
  let { data: stocks, error } = await pick("code,name,market,close_price,high_52w");
  if (error) ({ data: stocks } = await pick("code,name,market,close_price"));
  const infoOf = new Map((stocks ?? []).map((s) => [(s as unknown as Row).name, s as unknown as Row]));

  const results = await Promise.all(
    names.map(async (name) => {
      const info = infoOf.get(name);
      if (!info) return null;

      // KRX 종가 기준 — 지수 괴리율과 같은 잣대.
      if (info.close_price && info.high_52w && info.high_52w > 0) {
        return {
          name,
          code: info.code,
          price: info.close_price,
          high52: info.high_52w,
          gapPct: (info.close_price / info.high_52w - 1) * 100,
        };
      }

      // 폴백: 52주 고점이 아직 없으면 야후로 채운다(잣대가 달라지지만 칸이 비는 것보단 낫다).
      const q = await fetchYahooQuote(`${info.code}.${info.market === "KOSDAQ" ? "KQ" : "KS"}`, {
        next: { revalidate: 600 },
      });
      if (!q || q.fiftyTwoWeekHigh === null || q.fiftyTwoWeekHigh <= 0) return null;
      return {
        name,
        code: info.code,
        price: Math.round(q.price),
        high52: Math.round(q.fiftyTwoWeekHigh),
        gapPct: (q.price / q.fiftyTwoWeekHigh - 1) * 100,
      };
    }),
  );
  return results.filter((r): r is StockHighGap => r !== null);
}
