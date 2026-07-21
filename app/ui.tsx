// 대시보드와 셸(사이드바/탑바)이 공유하는 UI 프리미티브.
// 색은 전부 CSS 변수(app/globals.css)를 참조하므로, data-theme 전환 시 사용처를
// 하나도 안 건드리고 라이트/다크가 함께 바뀐다.
export const C = {
  cold: "var(--c-cold)", // 저온
  neutral: "var(--c-neutral)", // 상온
  hot: "var(--c-hot)", // 고온
  mania: "var(--c-mania)", // 초고온
  ink: "var(--c-ink)",
  sub: "var(--c-sub)",
  card: "var(--c-card)",
  bg: "var(--c-bg)",
  line: "var(--c-line)",
  track: "var(--c-track)",
  blue: "var(--c-blue)",
} as const;

// 햇쩨 지수(0~100)를 4구간 라벨로 매핑 — 파이프라인 calculate_score.py의
// stage_for_score와 동일 경계(25/50/75). 프론트는 저장된 stage 문자열 대신
// 점수에서 직접 계산해, 표시가 데이터와 항상 일치하고 라벨 변경에도 견고하다.
export function stageForScore(score: number): string {
  if (score < 25) return "저온";
  if (score < 50) return "상온";
  if (score < 75) return "고온";
  return "초고온";
}

// 숫자를 자릿수 고정으로 보여주려고 쓰던 이름. 예전엔 JetBrains Mono였는데, 그 서체엔
// 한글 글리프가 없어서 "31℃ · 상온"처럼 한글이 섞인 자리는 Pretendard도 건너뛰고 OS 기본
// 한글 폰트로 떨어졌다(맥·윈도우가 서로 다르게 보이던 원인). 이제 Pretendard 하나로 통일한다.
//
// 폭 고정은 서체가 아니라 tabular-nums로 낸다 — Pretendard가 이 기능을 지원해서
// 111/847/000이 모두 같은 폭으로 찍힌다. 실제 적용은 globals.css의 body 규칙이 맡는다.
export const MONO = "var(--font-pretendard), sans-serif";

export function Icon({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <span className="ms" style={style}>
      {name}
    </span>
  );
}
