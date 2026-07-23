import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // 에이전트 작업용 사본(.claude/worktrees)까지 검사하면 실제 경고가 묻힌다 —
    // 132개 파일에서 나온 9,000여 건에 진짜 경고 5건이 파묻혀 린트를 못 쓰는 상태였다.
    ".claude/**",
  ]),
]);

export default eslintConfig;
