// HATZZE 로고 — 소문자 워드마크(hatzze) + 유령 심볼 + 가로 lockup.
//
// 워드마크: Bricolage Grotesque 700, tracking -0.035em. 색은 테마 인식
//   var(--c-logo-ink)(라이트=잉크 / 다크=흰색). 폰트는 layout.tsx의 Google
//   Fonts CDN 링크로 로드한다.
// 심볼: 브랜드 유령. 원본 SVG는 #0064ff 고정이지만, 앱 전반의 블루와 함께
//   다크모드에서 밝아지도록 몸통/눈동자를 var(--c-blue)로 참조한다(눈은 흰색).

const FONT = "'Bricolage Grotesque', sans-serif";

export function Wordmark({
  size = 30,
  color = "var(--c-logo-ink)",
}: {
  size?: number;
  color?: string;
}) {
  return (
    <span
      style={{
        fontFamily: FONT,
        fontWeight: 700,
        fontSize: size,
        letterSpacing: "-0.035em",
        lineHeight: 1,
        color,
        display: "inline-block",
      }}
    >
      hatzze
    </span>
  );
}

// 브랜드 유령 심볼. size는 높이(px), 폭은 viewBox 비율(100/104)로 따라간다.
export function GhostSymbol({
  size = 30,
  color = "var(--c-blue)",
}: {
  size?: number;
  color?: string;
}) {
  return (
    <svg
      width={size * (100 / 104)}
      height={size}
      viewBox="0 0 100 104"
      fill="none"
      role="img"
      aria-label="hatzze"
      style={{ display: "block", flexShrink: 0 }}
    >
      <path
        d="M12,84 C6,42 22,8 50,8 C78,8 94,42 88,84 C86,95 80,95 77,87 C74,80 67,80 64,88 C61,96 54,96 51,88 C48,80 41,80 38,88 C35,96 28,96 25,87 C22,80 15,93 12,84 Z"
        fill={color}
      />
      <ellipse cx="39" cy="50" rx="9.5" ry="12" fill="#fff" />
      <circle cx="66" cy="52" r="7" fill="#fff" />
      <circle cx="42" cy="45" r="3" fill={color} />
    </svg>
  );
}

// 가로 lockup(심볼 + 워드마크) — 사이드바/헤더용.
export function LogoLockup({
  symbolSize = 30,
  wordmarkSize = 32,
  gap = 11,
}: {
  symbolSize?: number;
  wordmarkSize?: number;
  gap?: number;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap }}>
      <GhostSymbol size={symbolSize} />
      <Wordmark size={wordmarkSize} />
    </span>
  );
}
