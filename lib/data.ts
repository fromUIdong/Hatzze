import "server-only";

import { getDevOverrides } from "@/lib/dev-overrides";
import { getSupabaseServer } from "@/lib/supabase-server";

export type DailyScore = {
  date: string;
  score: number;
  stage: string;
  updated_at: string;
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
};

export async function getLatestDailyScore(): Promise<DailyScore | null> {
  const { data, error } = await getSupabaseServer()
    .from("daily_score")
    .select("date,score,stage,updated_at")
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
  const baseCols =
    "id, slug, name, headline, category, description_beginner, unit, direction, created_at";

  const query = (valueCols: string) =>
    getSupabaseServer()
      .from("indicators")
      .select(`${baseCols}, indicator_values ( ${valueCols} )`)
      .eq("is_public", true)
      .order("created_at", { ascending: true })
      .order("date", { referencedTable: "indicator_values", ascending: false })
      .limit(1, { referencedTable: "indicator_values" });

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
    };
  });
}
