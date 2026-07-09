import "server-only";

import { supabaseServer } from "@/lib/supabase-server";

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
  // is_public=false인 지표(예: kospi_close_raw)는 다른 지표를 계산하기 위한
  // 내부용 캐시라 화면에 노출하지 않는다. 그 외에는 새로 추가되는 지표도
  // 코드 수정 없이 자동으로 표시된다.
  const { data, error } = await supabaseServer
    .from("indicators")
    .select(
      `
      id, slug, name, category, description_beginner, unit, created_at,
      indicator_values ( date, raw_value, normalized_score )
    `,
    )
    .eq("is_public", true)
    .order("created_at", { ascending: true })
    .order("date", { referencedTable: "indicator_values", ascending: false })
    .limit(1, { referencedTable: "indicator_values" });

  if (error) throw error;

  return (data ?? []).map((row) => ({
    id: row.id,
    slug: row.slug,
    name: row.name,
    category: row.category,
    description_beginner: row.description_beginner,
    unit: row.unit,
    latest: row.indicator_values[0] ?? null,
  }));
}
