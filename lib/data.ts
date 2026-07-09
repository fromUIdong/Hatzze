import "server-only";

import { supabaseServer } from "@/lib/supabase-server";

// MVP 5개 지표만 노출한다. kospi_close_raw / kospi_market_cap_raw 등은
// 다른 지표를 계산하기 위한 내부용 캐시라 프론트엔드에 보여주지 않는다.
const PUBLIC_INDICATOR_SLUGS = [
  "us10y",
  "kospi_high_gap",
  "buffett_index",
  "naver_search_trend",
  "dcinside_post_count",
] as const;

export type DailyScore = {
  date: string;
  score: number;
  stage: string;
};

export type IndicatorWithLatestValue = {
  id: string;
  slug: string;
  name: string;
  category: "정통" | "밈";
  description_beginner: string;
  unit: string;
  latest: {
    date: string;
    raw_value: number;
    normalized_score: number | null;
  } | null;
};

export async function getLatestDailyScore(): Promise<DailyScore | null> {
  const { data, error } = await supabaseServer
    .from("daily_score")
    .select("date,score,stage")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) throw error;
  return data;
}

export async function getPublicIndicators(): Promise<IndicatorWithLatestValue[]> {
  const { data, error } = await supabaseServer
    .from("indicators")
    .select(
      `
      id, slug, name, category, description_beginner, unit,
      indicator_values ( date, raw_value, normalized_score )
    `,
    )
    .in("slug", PUBLIC_INDICATOR_SLUGS)
    .order("date", { referencedTable: "indicator_values", ascending: false })
    .limit(1, { referencedTable: "indicator_values" });

  if (error) throw error;

  const indicators = (data ?? []).map((row) => ({
    id: row.id,
    slug: row.slug,
    name: row.name,
    category: row.category,
    description_beginner: row.description_beginner,
    unit: row.unit,
    latest: row.indicator_values[0] ?? null,
  }));

  const order = new Map<string, number>(
    PUBLIC_INDICATOR_SLUGS.map((slug, index) => [slug, index]),
  );
  return indicators.sort((a, b) => (order.get(a.slug) ?? 0) - (order.get(b.slug) ?? 0));
}
