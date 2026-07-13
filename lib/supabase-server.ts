import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/**
 * Supabase 클라이언트를 모듈 로드 시점이 아니라 첫 호출 시점에 생성한다.
 *
 * 모듈 최상위에서 곧바로 만들면, 환경변수가 없는 빌드 환경(예: Vercel에
 * SUPABASE_* 가 아직 설정되지 않은 상태)에서 `next build`의 page-data 수집
 * 단계가 이 모듈을 import하자마자 throw해 빌드 자체가 실패한다. 지연 초기화하면
 * 빌드는 통과하고, 실제 요청으로 데이터를 조회하는 시점에만(그때도 env가
 * 없으면) 명확한 에러로 실패한다 — fail-fast는 유지하되 빌드를 막지 않는다.
 */
export function getSupabaseServer(): SupabaseClient {
  if (client) return client;

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_PUBLISHABLE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    throw new Error(
      "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY 환경변수가 설정되어 있지 않습니다.",
    );
  }

  // 읽기 전용 조회이므로 service_role이 아닌 publishable(anon) 키를 사용한다.
  // indicators/indicator_values/daily_score 테이블은 RLS에 공개 SELECT 정책이 있다.
  client = createClient(supabaseUrl, supabaseKey, {
    auth: { persistSession: false },
  });

  return client;
}
