import "server-only";

import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { IndicatorDetails } from "@/lib/data";

// 로컬 개발용 오버레이. 지표 설명(description_beginner)이나 서브값(details)을
// 운영 Supabase에 쓰기 전에, 로컬 dev 서버에서만 새 값을 얹어 미리 보기 위한
// 장치다. 프로젝트 루트의 dev-overrides.json(=.gitignore, 배포에 안 감)을
// 읽어 slug별로 덮어쓴다. 승인 후 실제 DB에 반영하고 이 파일을 비우면 된다.
//
// - NODE_ENV가 development가 아니면(=운영 빌드) 무조건 no-op → 운영엔 영향 없음.
// - 파일이 없거나 JSON이 깨져도 조용히 무시(no-op)한다.
// - dev에선 매 요청마다 파일을 다시 읽으므로, JSON을 고치고 새로고침하면
//   서버 재시작 없이 바로 반영된다.
export type DevOverrides = {
  names?: Record<string, string>;
  descriptions?: Record<string, string>;
  details?: Record<string, IndicatorDetails>;
  // 히어로 카드의 '오늘의 요약' 문장을 로컬에서만 미리 보기 위한 오버레이.
  summary?: string;
};

const EMPTY: DevOverrides = {};

export function getDevOverrides(): DevOverrides {
  if (process.env.NODE_ENV !== "development") return EMPTY;
  try {
    const raw = readFileSync(join(process.cwd(), "dev-overrides.json"), "utf-8");
    const parsed = JSON.parse(raw) as DevOverrides;
    return parsed && typeof parsed === "object" ? parsed : EMPTY;
  } catch {
    return EMPTY;
  }
}
