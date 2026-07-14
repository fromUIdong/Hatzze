// 대시보드와 셸(사이드바/탑바)이 공유하는 UI 프리미티브.
// 색은 전부 CSS 변수(app/globals.css)를 참조하므로, data-theme 전환 시 사용처를
// 하나도 안 건드리고 라이트/다크가 함께 바뀐다.
export const C = {
  cold: "var(--c-cold)", // 냉정
  neutral: "var(--c-neutral)", // 보통
  hot: "var(--c-hot)", // 과열
  mania: "var(--c-mania)", // 광기
  ink: "var(--c-ink)",
  sub: "var(--c-sub)",
  card: "var(--c-card)",
  bg: "var(--c-bg)",
  line: "var(--c-line)",
  track: "var(--c-track)",
  blue: "var(--c-blue)",
} as const;

export const MONO = "'JetBrains Mono', monospace";

export function Icon({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <span className="ms" style={style}>
      {name}
    </span>
  );
}
