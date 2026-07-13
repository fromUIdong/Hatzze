import { getLatestDailyScore, getPublicIndicators } from "@/lib/data";
import type { DailyScore, IndicatorCategory, IndicatorWithLatestValue } from "@/lib/data";
import { formatIndicatorValue, formatKstDateTime } from "@/lib/format";

// 지표는 하루 단위(GitHub Actions 배치)로 갱신되므로, 빌드 시점에 정적으로
// 굳어버리지 않도록 매 요청마다 서버에서 새로 조회한다.
export const dynamic = "force-dynamic";

// ── 목업 색 팔레트 ────────────────────────────────────────────────
const C = {
  cold: "#5ea8d8", // 냉정
  neutral: "#a89f95", // 보통
  hot: "#ff9a4d", // 과열
  mania: "#ff6b81", // 광기
  ink: "#202632",
  sub: "#6B7684",
  card: "#E8EEFE",
  bg: "#D4DAEA",
  line: "#c2c6d8",
  track: "#c2c6d8",
  blue: "#0064FF",
} as const;

const MONO = "'JetBrains Mono', monospace";

function heatColor(score: number | null): string {
  if (score === null) return C.sub;
  if (score >= 100) return C.mania;
  if (score >= 70) return C.hot;
  if (score >= 33) return C.neutral;
  return C.cold;
}

function Icon({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <span className="ms" style={style}>
      {name}
    </span>
  );
}

// ── 지표 데이터 픽 ────────────────────────────────────────────────
type Ind = IndicatorWithLatestValue;

type Pick = {
  ind?: Ind;
  name: string;
  headline: string | null;
  desc: string;
  raw: number | null;
  score: number | null;
  capped: number | null;
  threshold: number | null;
  isHit: boolean;
  color: string;
  disp: string;
  unit: string;
  thDisp: string | null;
  dirLabel: string;
  details: Record<string, number> | null;
};

function pick(ind: Ind | undefined): Pick {
  const raw = ind?.latest?.raw_value ?? null;
  const score = ind?.latest?.normalized_score ?? null;
  const capped = score === null ? null : Math.min(Math.max(score, 0), 100);
  const threshold = ind?.latest?.threshold ?? null;
  const unit = ind?.unit ?? "";
  const f =
    raw !== null
      ? formatIndicatorValue(raw, unit)
      : { display: "-", displayUnit: unit };
  const tf = threshold !== null ? formatIndicatorValue(threshold, unit) : null;
  return {
    ind,
    name: ind?.name ?? "",
    headline: ind?.headline ?? null,
    desc: ind?.description_beginner ?? "",
    raw,
    score,
    capped,
    threshold,
    isHit: (score ?? 0) >= 100,
    color: heatColor(score),
    disp: f.display,
    unit: f.displayUnit,
    thDisp: tf ? `${tf.display}${tf.displayUnit}` : null,
    dirLabel: ind?.direction === "low" ? "이하" : "이상",
    details: ind?.latest?.details ?? null,
  };
}

// ── 공용 카드 조각 ────────────────────────────────────────────────
function Shell({
  span = 1,
  hit = false,
  minH = 230,
  children,
}: {
  span?: 1 | 2;
  hit?: boolean;
  minH?: number;
  children: React.ReactNode;
}) {
  return (
    <div
      className={span === 2 ? "hz-span2" : undefined}
      style={{
        background: C.card,
        borderRadius: 20,
        padding: span === 2 ? 30 : 24,
        display: "flex",
        flexDirection: "column",
        position: "relative",
        minHeight: minH,
        boxShadow: hit
          ? "0 8px 24px -12px rgba(255,107,129,0.35)"
          : "0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.08)",
        border: hit ? "2px solid rgba(255,107,129,0.18)" : "2px solid transparent",
      }}
    >
      {children}
    </div>
  );
}

function HitBadge({ label = "🎯 HIT", small = false }: { label?: string; small?: boolean }) {
  return (
    <span
      style={{
        position: "absolute",
        top: small ? 18 : 24,
        right: small ? 18 : 24,
        background: C.mania,
        color: "#fff",
        fontWeight: 800,
        fontSize: small ? 9 : 11,
        padding: small ? "4px 9px" : "6px 12px",
        borderRadius: small ? 6 : 8,
      }}
    >
      {label}
    </span>
  );
}

function Tag({ text, color }: { text: string | null; color: string }) {
  if (!text) return null;
  return (
    <p
      style={{
        margin: "0 0 12px",
        fontSize: 11,
        fontWeight: 800,
        fontStyle: "italic",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        color,
      }}
    >
      &ldquo;{text}&rdquo;
    </p>
  );
}

function TitleRow({
  icon,
  name,
  color = C.sub,
  iconSize = 24,
  badge,
  right,
}: {
  icon: string;
  name: React.ReactNode;
  color?: string;
  iconSize?: number;
  badge?: string;
  right?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginBottom: 14,
        justifyContent: right ? "space-between" : undefined,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name={icon} style={{ fontSize: iconSize, color }} />
        <span style={{ fontSize: 15, fontWeight: 800, color: C.ink, lineHeight: 1.2, wordBreak: "keep-all" }}>
          {name}
        </span>
        {badge && (
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: C.sub,
              background: C.bg,
              padding: "3px 8px",
              borderRadius: 999,
              whiteSpace: "nowrap",
            }}
          >
            {badge}
          </span>
        )}
      </div>
      {right}
    </div>
  );
}

function Big({
  disp,
  unit,
  color,
  size = 40,
  sub,
}: {
  disp: string;
  unit?: string;
  color: string;
  size?: number;
  sub?: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginBottom: 12 }}>
      <span
        style={{
          fontFamily: MONO,
          fontSize: size,
          fontWeight: 800,
          color,
          lineHeight: 1,
          letterSpacing: "-0.03em",
        }}
      >
        {disp}
        {unit && <span style={{ fontSize: size * 0.5 }}>{unit}</span>}
      </span>
      {sub && <span style={{ fontSize: 12, fontWeight: 800, color, paddingBottom: 6 }}>{sub}</span>}
    </div>
  );
}

function Foot({ text, color = C.sub }: { text: string; color?: string }) {
  return (
    <p
      style={{
        margin: "auto 0 0",
        paddingTop: 16,
        fontSize: 12,
        color,
        fontWeight: 600,
        borderTop: "1px solid rgba(0,0,0,0.05)",
        marginTop: 16,
        lineHeight: 1.5,
      }}
    >
      {text}
    </p>
  );
}

// 과열도 진행 바 (세부 데이터가 없는 카드의 공용 시각화).
function HeatBar({ v }: { v: Pick }) {
  if (v.capped === null) return null;
  return (
    <div style={{ background: C.bg, borderRadius: 14, padding: "16px 18px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 800, marginBottom: 8 }}>
        <span style={{ color: C.sub }}>과열도</span>
        <span style={{ color: v.color, fontFamily: MONO }}>
          {Math.round(v.capped)}
          <span style={{ color: "#a9b0bd" }}>/100</span>
        </span>
      </div>
      <div style={{ position: "relative", height: 10, background: C.track, borderRadius: 999, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${v.capped}%`,
            background: v.isHit ? `linear-gradient(90deg, ${C.hot}, ${C.mania})` : v.color,
            borderRadius: 999,
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 700, color: C.sub, marginTop: 7 }}>
        <span>안심</span>
        <span style={{ color: C.hot }}>과열 100</span>
      </div>
      {v.thDisp && (
        <p style={{ margin: "8px 0 0", textAlign: "center", fontSize: 10, fontWeight: 700, color: C.sub, fontFamily: MONO }}>
          기준선 {v.thDisp} {v.dirLabel}
        </p>
      )}
    </div>
  );
}

// ── 히어로 ────────────────────────────────────────────────────────
const STAGE_META: Record<string, { emoji: string; color: string; zone: string }> = {
  냉정: { emoji: "🧊", color: C.cold, zone: "냉정 구간" },
  보통: { emoji: "⚖️", color: C.neutral, zone: "보통 구간" },
  과열: { emoji: "🔥", color: C.hot, zone: "과열 구간" },
  광기: { emoji: "🚨", color: C.mania, zone: "광기 구간" },
};

function HeroGauge({ score }: { score: number }) {
  const s = Math.max(0, Math.min(100, score));
  const arcLen = 389.6;
  const dashoffset = arcLen * (1 - s / 100);
  const theta = ((180 - (s / 100) * 180) * Math.PI) / 180;
  const nx = 150 + 124 * Math.cos(theta);
  const ny = 150 - 124 * Math.sin(theta);
  return (
    <svg viewBox="0 0 300 172" style={{ width: 300, height: 172, overflow: "visible" }}>
      <defs>
        <linearGradient id="heroThermal" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={C.cold} />
          <stop offset="33%" stopColor={C.neutral} />
          <stop offset="66%" stopColor={C.hot} />
          <stop offset="100%" stopColor={C.mania} />
        </linearGradient>
      </defs>
      <path d="M 26 150 A 124 124 0 0 1 274 150" fill="none" stroke={C.bg} strokeWidth={22} strokeLinecap="round" />
      <path
        d="M 26 150 A 124 124 0 0 1 274 150"
        fill="none"
        stroke="url(#heroThermal)"
        strokeWidth={22}
        strokeLinecap="round"
        strokeDasharray={arcLen}
        strokeDashoffset={dashoffset}
      />
      <circle cx={nx} cy={ny} r={12} fill={C.blue} stroke={C.card} strokeWidth={4} />
    </svg>
  );
}

function Hero({ dailyScore, tradHits, socialHits }: { dailyScore: DailyScore; tradHits: number; socialHits: number }) {
  const stage = STAGE_META[dailyScore.stage] ?? { emoji: "📊", color: C.neutral, zone: dailyScore.stage };
  const scoreDisplay = formatIndicatorValue(dailyScore.score, "%").display;
  return (
    <section
      className="hz-hero"
      style={{
        background: C.card,
        borderRadius: 24,
        boxShadow: "0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.08)",
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
        <div style={{ position: "relative", width: 300, height: 172 }}>
          <HeroGauge score={dailyScore.score} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 78, textAlign: "center" }}>
            <div style={{ fontFamily: MONO, fontSize: 58, fontWeight: 800, color: C.ink, letterSpacing: "-0.04em", lineHeight: 1 }}>
              {scoreDisplay}
              <span style={{ fontSize: 30 }}>%</span>
            </div>
            <div style={{ fontSize: 11, fontWeight: 800, color: stage.color, marginTop: 6 }}>지금 · {stage.zone}</div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", width: 300, padding: "0 6px", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          <span style={{ color: C.cold }}>냉정</span>
          <span style={{ color: C.neutral }}>보통</span>
          <span style={{ color: C.hot }}>과열</span>
          <span style={{ color: C.mania }}>광기</span>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 280 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <span style={{ fontSize: 15, fontWeight: 800, color: C.blue }}>Hatzze Overheating Index</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: `${stage.color}24`, color: stage.color, fontWeight: 800, fontSize: 16, padding: "5px 14px", borderRadius: 999, whiteSpace: "nowrap" }}>
            {stage.emoji} {dailyScore.stage}
          </span>
        </div>
        <p style={{ margin: "0 0 4px", fontSize: 11, color: C.sub, fontFamily: MONO }}>최종 업데이트 · {formatKstDateTime(dailyScore.updated_at)}</p>
        <div style={{ marginTop: 20, background: C.bg, borderRadius: 16, padding: "22px 24px", display: "flex", gap: 14 }}>
          <Icon name="auto_awesome" style={{ color: C.blue, fontSize: 22 }} />
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#3a4453", fontWeight: 500 }}>
            오늘은 시장 지표 <b style={{ color: C.ink }}>{tradHits}개</b>, 감성 지표 <b style={{ color: C.ink }}>{socialHits}개</b>가 기준선을 넘었어요. 지표들이 가리키는 현재 시장 온도는 <b style={{ color: stage.color }}>{dailyScore.stage}</b> 구간이에요.
          </p>
        </div>
      </div>
    </section>
  );
}

// ── 사이드바 / 탑바 ───────────────────────────────────────────────
const NAV = [
  { icon: "dashboard", label: "대시보드", active: true },
  { icon: "thermostat", label: "시장 열기", active: false },
  { icon: "insights", label: "심화 분석", active: false },
  { icon: "notifications", label: "알림", active: false },
  { icon: "settings", label: "설정", active: false },
];

function Sidebar() {
  return (
    <aside className="hz-sidebar" style={{ width: 248, flexShrink: 0, background: C.card, borderRight: `1px solid ${C.line}`, padding: "32px 0" }}>
      <div style={{ padding: "0 32px", marginBottom: 48 }}>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 800, color: C.blue, letterSpacing: "-0.04em" }}>HATZZE</h1>
        <p style={{ margin: "6px 0 0", fontSize: 10, fontWeight: 700, color: C.sub, textTransform: "uppercase", letterSpacing: "0.2em" }}>시장 과열도 분석</p>
      </div>
      <nav style={{ flex: 1, padding: "0 16px", display: "flex", flexDirection: "column", gap: 8 }}>
        {NAV.map((item) => (
          <span key={item.label} style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", color: item.active ? C.blue : C.sub, fontWeight: item.active ? 700 : 600, background: item.active ? "rgba(0,100,255,0.08)" : "transparent", borderRadius: 14 }}>
            <Icon name={item.icon} />
            <span style={{ fontSize: 15 }}>{item.label}</span>
          </span>
        ))}
      </nav>
    </aside>
  );
}

function TopBar({ dailyScore }: { dailyScore: DailyScore | null }) {
  const stage = dailyScore ? STAGE_META[dailyScore.stage] : undefined;
  return (
    <header style={{ height: 64, flexShrink: 0, background: C.card, borderBottom: `1px solid ${C.line}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 32px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: MONO, overflow: "hidden" }}>
        {dailyScore ? (
          <>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>햇쩨 지수</span>
            <span style={{ fontSize: 13, fontWeight: 800, color: stage?.color ?? C.ink }}>
              {formatIndicatorValue(dailyScore.score, "%").display}% · {dailyScore.stage}
            </span>
            <span className="hz-topbar-date" style={{ fontSize: 11, fontWeight: 600, color: C.sub, whiteSpace: "nowrap" }}>
              {formatKstDateTime(dailyScore.updated_at)}
            </span>
          </>
        ) : (
          <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>데이터 대기 중</span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ position: "relative" }}>
          <Icon name="search" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: C.sub, fontSize: 20 }} />
          <input placeholder="지표 검색..." style={{ background: C.bg, border: "none", borderRadius: 12, padding: "9px 16px 9px 40px", fontSize: 12, width: 240, maxWidth: "40vw", color: C.ink, outline: "none", fontFamily: "inherit" }} />
        </div>
      </div>
    </header>
  );
}

// ── 소형 시각화 조각 ──────────────────────────────────────────────
function Donut({ pct, color }: { pct: number; color: string }) {
  const circ = 2 * Math.PI * 15.5;
  const fill = (Math.max(0, Math.min(100, pct)) / 100) * circ;
  return (
    <svg width="116" height="116" viewBox="0 0 36 36">
      <circle cx="18" cy="18" r="15.5" fill="none" stroke={C.bg} strokeWidth="5" />
      <circle cx="18" cy="18" r="15.5" fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${fill} ${circ - fill}`} transform="rotate(-90 18 18)" />
    </svg>
  );
}

// 반원 게이지 (과열도 0~100 → 바늘 각도).
function HalfGauge({ score, color }: { score: number; color: string }) {
  const s = Math.max(0, Math.min(100, score));
  const theta = ((180 - (s / 100) * 180) * Math.PI) / 180;
  const L = 78;
  const x2 = 96 + L * Math.cos(theta);
  const y2 = 90 - L * Math.sin(theta);
  return (
    <svg viewBox="0 0 196 100" style={{ width: 196, height: 86, overflow: "visible" }}>
      <path d="M 14 90 A 82 82 0 0 1 178 90" fill="none" stroke="#bfe0f2" strokeWidth="13" strokeLinecap="round" />
      <path d="M 96 8 A 82 82 0 0 1 178 90" fill="none" stroke="#ffd3ab" strokeWidth="13" strokeLinecap="round" />
      <line x1="96" y1="90" x2={x2} y2={y2} stroke={color} strokeWidth="3" strokeLinecap="round" />
      <circle cx="96" cy="90" r="6" fill={C.ink} />
    </svg>
  );
}

// 우상향/우하향 추세를 암시하는 장식용 라인 (실제 시계열이 아님).
function TrendLine({ color, down = false }: { color: string; down?: boolean }) {
  const d = down ? "M0 18 L25 22 L50 28 L75 34 L98 40" : "M0 42 L25 38 L50 30 L75 20 L98 14";
  return (
    <svg width="100%" height="100%" viewBox="0 0 100 52" preserveAspectRatio="none" style={{ position: "absolute", inset: 0 }}>
      <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// 레버리지 카드의 서브 진행률 바 (ETF 거래대금 / 선물 미결제약정)
function LevSubBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
        <span>{label}</span>
        <span style={{ color }}>
          {Math.round(value)}
          <span style={{ color: "#a9b0bd" }}>/100</span>
        </span>
      </div>
      <div style={{ height: 8, background: C.track, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
      </div>
    </div>
  );
}

// 매수쏠림 카드의 다이버징 카운트 바 (매수 / 매도 / CB)
function DivRow({ label, w, color }: { label: string; w: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ width: 82, fontSize: 11, fontWeight: 800, color, textAlign: "right" }}>{label}</span>
      <div style={{ flex: 1, height: 16, position: "relative", background: C.track, borderRadius: 999 }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.max(0, Math.min(100, w))}%`, background: color, borderRadius: 999 }} />
      </div>
    </div>
  );
}

// 아시아 카드의 4개국 상대 막대 (KOSPI=100 기준)
function AsiaBar({ label, sub, index, maxIndex, color }: { label: string; sub: string; index: number; maxIndex: number; color: string }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color }}>{Math.round(index)}</span>
      <div style={{ width: "100%", height: Math.max(8, (index / maxIndex) * 108), background: color, borderRadius: "6px 6px 0 0" }} />
      <span style={{ fontSize: 9, fontWeight: 800, color: C.sub, textAlign: "center", lineHeight: 1.25 }}>
        {label}
        <br />
        {sub}
      </span>
    </div>
  );
}

// 업비트 카드의 서브 바 (김치 프리미엄 / 거래량 강도) — 값 라벨은 우측 표시
function UpbitSubBar({ label, value, pct, color }: { label: string; value: string; pct: number; color: string }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
        <span>{label}</span>
        <span style={{ color }}>{value}</span>
      </div>
      <div style={{ height: 8, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} />
      </div>
    </div>
  );
}

// VIX/VKOSPI 카드의 백분위 바. 각 지수를 자기 1년 분포 내 백분위(0~100)로 바꾸면
// VIX와 VKOSPI를 같은 축에서 정직하게 비교할 수 있다(절대값 78 vs 15 오해 해소).
function VixPctRow({ flag, label, pct, color }: { flag: string; label: string; pct: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ width: 74, fontSize: 10, fontWeight: 800, color, textAlign: "right" }}>{flag} {label}</span>
      <div style={{ flex: 1, height: 9, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, pct))}%`, background: color, borderRadius: 999 }} />
      </div>
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, color: C.sub, width: 46, textAlign: "right" }}>{Math.round(pct)}%ile</span>
    </div>
  );
}

// ── 시장 지표 카드들 (목업 순서대로) ──────────────────────────────

// 1. 버핏지수 — 경제(GDP) vs 증시 시총 비교 (실제 값으로 복원 가능)
function CardBuffett({ v }: { v: Pick }) {
  const dt = v.details;
  const ratio = v.raw !== null ? v.raw / 100 : null; // 시총/GDP 배수
  const gdpWidth = v.raw && v.raw > 0 ? Math.min(100, (100 / v.raw) * 100) : 46;
  const jo = (won: number) => Math.round(won / 1e12).toLocaleString("ko-KR"); // 원 → 조원
  return (
    <Shell span={2} hit={v.isHit} minH={236}>
      {v.isHit && <HitBadge />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="payments" iconSize={30} color={v.color} name={<h3 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{v.name}</h3>} badge="당일 기준" />
      <Big disp={v.disp} unit={v.unit} color={v.color} size={52} sub={ratio !== null ? `${ratio.toFixed(1)}배 · 과열도 ${v.capped !== null ? Math.round(v.capped) : "-"}` : undefined} />
      <div style={{ background: C.bg, borderRadius: 14, padding: "18px 18px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
            <span>
              나라 경제 (GDP)
              {dt && dt.gdp_year ? (
                <span style={{ color: "#a9b0bd", fontWeight: 600 }}> · 최근 4개 분기(~{dt.gdp_year} {dt.gdp_q}분기)</span>
              ) : null}
            </span>
            <span style={{ fontFamily: MONO }}>{dt && dt.gdp ? `약 ${jo(dt.gdp)}조원` : "기준 100"}</span>
          </div>
          <div style={{ height: 18, background: "#c9cede", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${gdpWidth}%`, background: "#8a93a8", borderRadius: 6 }} />
          </div>
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 800, color: v.color, marginBottom: 6 }}>
            <span>증시 시가총액</span>
            <span style={{ fontFamily: MONO }}>
              {dt && dt.market_cap ? `약 ${jo(dt.market_cap)}조원 · ` : `${v.disp} · `}
              {ratio !== null ? `${ratio.toFixed(1)}배` : "-"}
            </span>
          </div>
          <div style={{ height: 18, background: "#c9cede", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ height: "100%", width: "100%", background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 6 }} />
          </div>
        </div>
        <p style={{ margin: "2px 0 0", fontSize: 11, fontWeight: 700, color: "#3a4453", textAlign: "center" }}>
          증시가 실물 경제보다 <span style={{ color: v.color }}>{ratio !== null ? `${ratio.toFixed(1)}배 커진` : "커진"}</span> 상태예요
        </p>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 2. 레버리지 지수 — 역대 범위 바 + ETF/선물 서브 진행률 (details 있으면 목업 원본)
function CardLeverage({ v }: { v: Pick }) {
  const dt = v.details;
  // 역대 최저/최고 사이에서 '지금' 위치. min/max가 있으면 실제 범위로, 없으면 과열도로.
  const hasRange =
    !!dt && dt.hist_max !== undefined && dt.hist_min !== undefined && dt.hist_max > dt.hist_min && v.raw !== null;
  const pos = hasRange
    ? Math.max(0, Math.min(100, ((v.raw! - dt!.hist_min) / (dt!.hist_max - dt!.hist_min)) * 100))
    : v.capped ?? 0;
  return (
    <Shell span={2} hit={v.isHit} minH={236}>
      {v.isHit && <HitBadge />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="rocket_launch" iconSize={30} color={v.color} name={<h3 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{v.name}</h3>} badge="당일 기준" />
      <Big disp={v.disp} unit={v.unit} color={v.color} size={44} sub={v.capped !== null ? `과열도 ${Math.round(v.capped)}` : undefined} />
      <div style={{ background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ position: "relative", height: 12, background: C.line, borderRadius: 999 }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pos}%`, background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 999 }} />
            <div style={{ position: "absolute", top: "50%", left: `${pos}%`, transform: "translate(-50%,-50%)", width: 14, height: 14, borderRadius: 999, background: v.color, border: `3px solid ${C.card}`, boxShadow: "0 1px 3px rgba(0,0,0,.25)" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 700, color: C.sub, marginTop: 7 }}>
            <span>역대 최저</span>
            <span style={{ color: v.color }}>지금 {Math.round(pos)}%</span>
            <span style={{ color: C.hot }}>역대 최고</span>
          </div>
        </div>
        {dt && (
          <>
            <div style={{ height: 1, background: "rgba(0,0,0,0.07)" }} />
            <div style={{ display: "flex", gap: 22 }}>
              <LevSubBar label="ETF 거래대금" value={dt.etf_progress ?? 0} color={C.hot} />
              <LevSubBar label="선물 미결제약정" value={dt.futures_progress ?? 0} color={C.mania} />
            </div>
          </>
        )}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 3. 매수 쏠림 지수 — 매수/매도/CB 다이버징 카운트 바 (details 있으면 목업 원본)
function CardMarketActions({ v }: { v: Pick }) {
  const dt = v.details;
  const buy = (v.raw ?? 0) > 0;
  const mag = v.threshold ? Math.min(100, (Math.abs(v.raw ?? 0) / Math.abs(v.threshold)) * 50) : 20;
  const buyN = dt?.buy ?? 0;
  const sellN = dt?.sell ?? 0;
  const maxC = Math.max(1, buyN, sellN, dt?.cb ?? 0);
  // 매수/매도 안전장치 중 무엇이 우세했는지 판정 — 종합 점수가 0이어도 방향은 보여준다.
  const verdict = !dt
    ? null
    : buyN > sellN
      ? { t: "매수 우세", c: C.hot }
      : sellN > buyN
        ? { t: "매도 우세", c: C.cold }
        : { t: "균형", c: C.neutral };
  return (
    <Shell span={2} hit={v.isHit} minH={236}>
      {v.isHit && <HitBadge />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="speed" iconSize={30} color={v.color} name={<h3 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{v.name}</h3>} badge="최근 30일" />
      {verdict ? (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 34, fontWeight: 800, color: verdict.c, lineHeight: 1 }}>{verdict.t}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: C.sub, paddingBottom: 4 }}>최근 30일 안전장치</span>
        </div>
      ) : (
        <Big disp={v.raw !== null && v.raw > 0 ? `+${v.disp}` : v.disp} color={v.color} size={44} sub="최근 30일 순 쏠림" />
      )}
      <div style={{ background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
        {dt ? (
          <>
            <DivRow label={`매수 ${dt.buy ?? 0}건`} w={((dt.buy ?? 0) / maxC) * 100} color={C.hot} />
            <DivRow label={`매도 ${dt.sell ?? 0}건`} w={((dt.sell ?? 0) / maxC) * 100} color={C.cold} />
            <DivRow label={`CB ${dt.cb ?? 0}건`} w={((dt.cb ?? 0) / maxC) * 100} color={C.sub} />
          </>
        ) : (
          <>
            <div style={{ position: "relative", height: 16, background: C.line, borderRadius: 999 }}>
              <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 2, background: "rgba(32,38,50,0.4)" }} />
              <div style={{ position: "absolute", top: 0, bottom: 0, borderRadius: 999, background: v.color, ...(buy ? { left: "50%", width: `${mag}%` } : { right: "50%", width: `${mag}%` }) }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 700, color: C.sub }}>
              <span style={{ color: C.cold }}>매도 우세</span>
              <span style={{ color: C.hot }}>매수 우세</span>
            </div>
          </>
        )}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 4. 상위 10종목 쏠림 — 도넛 (실제 비중으로 복원)
function CardTop10({ v }: { v: Pick }) {
  const pct = v.raw ?? 0;
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="pie_chart" name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
        <div style={{ position: "relative", width: 116, height: 116 }}>
          <Donut pct={pct} color={v.color} />
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: v.color, lineHeight: 1 }}>{v.disp}{v.unit}</span>
            <span style={{ fontSize: 8, fontWeight: 700, color: C.sub, marginTop: 2 }}>Top 10</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 14, fontSize: 10, fontWeight: 700, color: C.sub }}>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: 3, background: v.color }} />상위 10 · {v.disp}{v.unit}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: 3, background: C.line }} />나머지 · {v.raw !== null ? `${(100 - v.raw).toFixed(1)}%` : "-"}</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 5. 코스피 신고가 괴리율 — 세로 게이지 (실제 값으로 복원)
function CardHighGap({ v }: { v: Pick }) {
  const gap = v.raw ?? 0;
  const fillH = Math.max(0, Math.min(100, 100 - Math.abs(gap)));
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="vertical_align_top" name={v.name} color={v.color} />
      <div style={{ display: "flex", alignItems: "center", gap: 16, flex: 1 }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontFamily: MONO, fontSize: 34, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
          <span style={{ fontSize: 10, fontWeight: 700, color: C.sub, marginTop: 4 }}>{gap < 0 ? "전고점까지 남음" : "전고점 돌파"}</span>
        </div>
        <div style={{ flex: 1, alignSelf: "stretch", display: "flex", justifyContent: "center", padding: "6px 0" }}>
          <div style={{ width: 74, position: "relative", background: C.bg, borderRadius: 10, overflow: "hidden" }}>
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: `${fillH}%`, background: `linear-gradient(180deg,#7cbde6,${C.cold})` }} />
            <span style={{ position: "absolute", top: 6, right: 8, fontSize: 9, fontWeight: 800, color: C.ink }}>전고점</span>
          </div>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 6. VKOSPI — 반원 게이지 (과열도 + 실제 값)
function CardVkospi({ v }: { v: Pick }) {
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="monitor_heart" name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4 }}>
        <HalfGauge score={v.capped ?? 0} color={v.color} />
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: v.color, lineHeight: 1 }}>{v.capped !== null ? Math.round(v.capped) : "-"}</span>
          <span style={{ fontSize: 13, fontWeight: 800, color: "#a9b0bd" }}>/100</span>
          <span style={{ fontSize: 11, fontWeight: 800, color: v.color, marginLeft: 2 }}>과열도</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", width: 182, fontSize: 9, fontWeight: 800, marginTop: 2 }}>
          <span style={{ color: C.cold }}>안심</span>
          <span style={{ color: C.hot }}>과열</span>
        </div>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.sub, marginTop: 2 }}>실제 VKOSPI <b style={{ color: C.ink }}>{v.disp}</b> · 낮을수록 과열</div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 7. VIX 대비 VKOSPI — 각자 1년 분포 내 백분위로 정규화해 비교(스케일 무관).
// raw = VIX 백분위 - VKOSPI 백분위, 양수로 클수록 "한국만 유독 잠잠" = 방심.
function CardVixSpread({ v }: { v: Pick }) {
  const dt = v.details;
  const hasPct = !!dt && "vix_pct" in dt && "vkospi_pct" in dt;
  // 부호에 따라 방향 문구를 바꾼다 — 음수면 한국이 오히려 더 출렁이는 것이므로
  // "한국이 더 잠잠"이라고 하면 안 된다. 크기는 절댓값으로 보여준다.
  const rawv = v.raw ?? 0;
  const spread =
    rawv > 0
      ? { label: "한국이 더 잠잠", color: C.hot }
      : rawv < 0
        ? { label: "한국이 더 출렁", color: C.cold }
        : { label: "미·한 비슷", color: C.sub };
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="compare_arrows" name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
        {hasPct ? (
          <>
            <div style={{ fontSize: 9, color: "#8a919e", fontWeight: 700 }}>각자 최근 1년 대비 현재 변동성 수준(백분위)</div>
            <VixPctRow flag="🇺🇸" label="VIX" pct={dt!.vix_pct} color={C.mania} />
            <VixPctRow flag="🇰🇷" label="VKOSPI" pct={dt!.vkospi_pct} color={C.cold} />
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: C.bg, borderRadius: 10, padding: 9 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: C.sub }}>{spread.label}</span>
              <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 800, color: spread.color }}>
                {Math.abs(Math.round(rawv))}
                {v.unit}
              </span>
            </div>
          </>
        ) : (
          <HeatBar v={v} />
        )}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 8. 코스피 vs 아시아 — 4개국 상대 막대 (details 있으면 목업 원본, 없으면 과열도)
function CardAsia({ v }: { v: Pick }) {
  const dt = v.details;
  if (!dt) {
    return (
      <Shell span={2} minH={230}>
        <Tag text={v.headline} color={v.color} />
        <TitleRow icon="public" name={v.name} color={v.color} />
        <Big disp={v.raw !== null && v.raw > 0 ? `+${v.disp}` : v.disp} unit={v.unit} color={v.color} size={40} sub="아시아 3국 평균 대비" />
        <HeatBar v={v} />
        <Foot text={v.desc} />
      </Shell>
    );
  }
  const k = dt.kospi ?? 0;
  const bars = [
    { label: "KOSPI", sub: "한국", index: 100, color: C.blue },
    { label: "Nikkei", sub: "일본", index: 100 + ((dt.nikkei ?? 0) - k), color: C.hot },
    { label: "HangSeng", sub: "홍콩", index: 100 + ((dt.hangseng ?? 0) - k), color: C.cold },
    { label: "Taiex", sub: "대만", index: 100 + ((dt.taiex ?? 0) - k), color: C.neutral },
  ];
  const maxIndex = Math.max(...bars.map((b) => b.index), 1);
  return (
    <Shell span={2} minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="public" name={v.name} color={v.color} />
      <div style={{ fontSize: 9, color: "#8a919e", fontWeight: 700, marginBottom: 4 }}>
        KOSPI를 100으로 둔 상대 지수 · 코스피 초과수익률 {v.raw !== null && v.raw > 0 ? "+" : ""}
        {v.disp}
        {v.unit}
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, paddingTop: 6 }}>
        {bars.map((b) => (
          <AsiaBar key={b.label} label={b.label} sub={b.sub} index={b.index} maxIndex={maxIndex} color={b.color} />
        ))}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 9. 위험자산 vs 안전자산 — 금/코스닥 두 지표 결합 (둘 다 실제 값)
function SubRatio({ v, icon, label, note }: { v: Pick; icon: string; label: string; note: string }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Icon name={icon} style={{ fontSize: 20, color: C.sub }} />
        <span style={{ fontSize: 13, fontWeight: 800, wordBreak: "keep-all" }}>{label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 14 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>
        {v.thDisp && <span style={{ fontSize: 10, fontWeight: 700, color: C.sub }}>기준 {v.thDisp}</span>}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontWeight: 800, marginBottom: 6 }}>
        <span style={{ color: C.sub }}>과열도</span>
        <span style={{ color: v.color }}>{v.capped !== null ? Math.round(v.capped) : "-"} / 100</span>
      </div>
      <div style={{ position: "relative", height: 10, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${v.capped ?? 0}%`, background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 999 }} />
      </div>
      <p style={{ margin: "12px 0 0", fontSize: 11, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>{note}</p>
    </div>
  );
}

function CardRiskAssets({ gold, kosdaq }: { gold: Pick; kosdaq: Pick }) {
  return (
    <Shell span={2} minH={230}>
      <Tag text="위험자산 vs 안전자산" color={C.sub} />
      <div style={{ display: "flex", gap: 32 }}>
        <SubRatio v={gold} icon="balance" label="코스피 강도 (vs 금)" note={gold.desc} />
        <div style={{ width: 1, background: C.line }} />
        <SubRatio v={kosdaq} icon="celebration" label="코스닥 강도 (vs 코스피)" note={kosdaq.desc} />
      </div>
    </Shell>
  );
}

// 10. 거래대금 급증도 — 오늘 vs 30일 평균 (details 있으면 실제 평균, 없으면 과열기준 폴백)
function CardVolume({ v }: { v: Pick }) {
  const dt = v.details;
  const avg = dt?.avg_30d ?? null;
  const today = v.raw ?? null;
  const maxV = avg !== null && today !== null ? Math.max(avg, today, 1) : 1;
  const avgH = avg !== null && today !== null ? (avg / maxV) * 100 : 70;
  const todayH = avg !== null && today !== null ? (today / maxV) * 100 : 100;
  const avgFmt = avg !== null ? formatIndicatorValue(avg, "억원") : null;
  const surge = dt?.surge_pct ?? null;
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow
        icon="groups"
        name={v.name}
        color={v.color}
        right={
          surge !== null ? (
            <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color: surge >= 0 ? C.hot : C.cold }}>
              {surge >= 0 ? "+" : ""}
              {surge}%
            </span>
          ) : undefined
        }
      />
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, height: 120, flex: 1 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 6, height: "100%" }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, color: C.neutral }}>
            {avgFmt ? `${avgFmt.display}${avgFmt.displayUnit}` : v.thDisp ?? "-"}
          </span>
          <div style={{ width: "100%", height: `${avgH}%`, background: C.line, borderRadius: "6px 6px 0 0" }} />
          <span style={{ fontSize: 9, fontWeight: 700, color: C.sub }}>{avg !== null ? "30일 평균" : "과열 기준"}</span>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 6, height: "100%" }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>
          <div style={{ width: "100%", height: `${todayH}%`, background: v.color, borderRadius: "6px 6px 0 0" }} />
          <span style={{ fontSize: 9, fontWeight: 700, color: C.sub }}>오늘</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 11. 원/달러 환율 변동성 — 값 + 장식 파동 + 과열도
function CardFx({ v }: { v: Pick }) {
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="waves" name={v.name} color={v.color} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>±{v.disp}{v.unit}</span>
        <span style={{ fontSize: 11, fontWeight: 800, color: v.color }}>과열도 {v.capped !== null ? Math.round(v.capped) : "-"}</span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 50, display: "flex", alignItems: "center" }}>
        <svg width="100%" height="50" viewBox="0 0 100 50" preserveAspectRatio="none" style={{ position: "absolute", inset: 0 }}>
          <line x1="0" y1="25" x2="100" y2="25" stroke={C.line} strokeWidth="0.8" strokeDasharray="2,2" />
          <path d="M0 25 C5 20 9 20 13 25 S21 30 26 25 S34 20 39 25 S47 30 52 25 S60 20 65 25 S73 30 78 25 S86 20 91 25 S99 29 100 25" fill="none" stroke={v.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 12·14. 미국 10년물 금리 / 장단기 금리차 — 범위 바 + 마커
function CardRangeRate({ v, icon, warn = false }: { v: Pick; icon: string; warn?: boolean }) {
  const pos = v.capped !== null ? Math.max(4, Math.min(96, v.capped)) : 50;
  return (
    <Shell minH={230}>
      {warn && v.raw !== null && v.raw < 0 && <HitBadge label="⚠ 역전" small />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon={icon} name={v.name} color={v.color} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 20 }}>
        <span style={{ fontFamily: MONO, fontSize: 34, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
      </div>
      <div style={{ marginTop: "auto" }}>
        <div style={{ position: "relative", height: 12, borderRadius: 999, background: C.bg, overflow: "hidden" }}>
          <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${pos}%`, background: v.color }} />
        </div>
        <div style={{ position: "relative", height: 0 }}>
          <div className={warn ? "hz-pulse-red" : undefined} style={{ position: "absolute", top: -13, transform: "translateX(-50%)", left: `${pos}%`, width: 16, height: 16, borderRadius: 999, background: v.color, border: `3px solid ${C.card}`, boxShadow: "0 1px 4px rgba(0,0,0,.2)" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 800, color: C.sub, marginTop: 10 }}>
          <span>낮음</span>
          <span style={{ color: v.color }}>높음 · 부담</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 13. 구리 가격 모멘텀 — 값 + 장식 상승 라인 + 과열도
function CardCopper({ v }: { v: Pick }) {
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="bolt" name={v.name} color={v.color} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.raw !== null && v.raw > 0 ? "+" : ""}{v.disp}{v.unit}</span>
        <span style={{ fontSize: 11, fontWeight: 800, color: v.color }}>과열도 {v.capped !== null ? Math.round(v.capped) : "-"}</span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 56 }}>
        <TrendLine color={v.color} down={v.raw !== null && v.raw < 0} />
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 15. 신용융자 잔고 — DB 미보유 placeholder ("준비 중")
function CardComingSoon() {
  return (
    <Shell minH={230}>
      <div style={{ opacity: 0.85, display: "flex", flexDirection: "column", flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <p style={{ margin: 0, fontSize: 10, fontWeight: 800, fontStyle: "italic", textTransform: "uppercase", letterSpacing: "0.04em", color: C.sub }}>&ldquo;빚내서 사는 돈의 크기&rdquo;</p>
          <span style={{ background: "rgba(0,100,255,0.08)", color: C.blue, fontWeight: 800, padding: "4px 9px", borderRadius: 6, fontSize: 9 }}>준비 중</span>
        </div>
        <TitleRow icon="credit_score" name={<span style={{ color: "#8a919e" }}>신용융자 잔고</span>} color="#a9b0bd" />
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="100%" height="70" viewBox="0 0 100 40" preserveAspectRatio="none">
            <path d="M0 34 L20 32 L40 28 L60 22 L80 15 L100 8" fill="none" stroke={C.line} strokeDasharray="4,3" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </div>
        <Foot text="빚내서 주식 사는 돈이 불어나면 과열의 대표 신호로 볼 수 있어요." color="#8a919e" />
      </div>
    </Shell>
  );
}

// ── 소셜 지표 카드들 ──────────────────────────────────────────────

// 라인+마커형 (초보검색/재테크도서/GitHub/자영업)
function CardTrend({ v, icon }: { v: Pick; icon: string }) {
  return (
    <Shell minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon={icon} name={v.name} iconSize={22} color={v.color} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
        <span style={{ fontSize: 10, fontWeight: 800, color: v.color }}>과열도 {v.capped !== null ? Math.round(v.capped) : "-"}</span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 52 }}>
        <TrendLine color={v.color} down={(v.score ?? 0) < 33} />
        {v.thDisp && <span style={{ position: "absolute", top: 1, left: 2, fontSize: 8, fontWeight: 800, color: C.hot }}>과열 기준 {v.thDisp}</span>}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 중앙 기준 감성/카운트 바 (커뮤니티/뉴스)
function CardSentiment({ v, icon, span = 1 }: { v: Pick; icon: string; span?: 1 | 2 }) {
  return (
    <Shell span={span} minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon={icon} iconSize={22} color={v.color} name={v.name} right={<span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>} />
      <div style={{ marginTop: "auto" }}>
        <div style={{ position: "relative", height: 16, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${v.capped ?? 0}%`, background: v.isHit ? `linear-gradient(90deg,${C.hot},${C.mania})` : v.color, borderRadius: 999 }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 800, color: C.sub, marginTop: 8 }}>
          <span>안심</span>
          {v.thDisp && <span>기준 {v.thDisp} {v.dirLabel}</span>}
          <span style={{ color: C.hot }}>과열 100</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 유튜브 — 평소(기준) vs 오늘 막대 (HIT)
function CardYoutube({ v }: { v: Pick }) {
  const ratio = v.raw && v.threshold ? v.raw / v.threshold : null;
  const baseH = v.raw && v.threshold ? Math.max(15, Math.min(100, (v.threshold / v.raw) * 100)) : 34;
  return (
    <Shell hit={v.isHit} minH={210}>
      {v.isHit && <HitBadge label="✨ HIT" small />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="play_circle" iconSize={22} name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 88 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 6, height: "100%" }}>
            <div style={{ width: 26, height: `${baseH}%`, background: C.line, borderRadius: "5px 5px 0 0" }} />
            <span style={{ fontSize: 8, fontWeight: 700, color: C.sub }}>평소</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", gap: 6, height: "100%" }}>
            <div style={{ width: 26, height: "100%", background: v.color, borderRadius: "5px 5px 0 0" }} />
            <span style={{ fontSize: 8, fontWeight: 700, color: C.sub }}>오늘</span>
          </div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 800, color: v.color, lineHeight: 1 }}>{v.disp}{v.unit && <span style={{ fontSize: 14 }}>{v.unit}</span>}</div>
          {ratio !== null && <div style={{ fontSize: 9, fontWeight: 800, color: v.color, marginTop: 4 }}>평소 대비 {ratio.toFixed(1)}배</div>}
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 여윳돈이 향하는 곳 — 명품/오마카세 결합
function SubSpend({ v, icon }: { v: Pick; icon: string }) {
  return (
    <div style={{ flex: 1 }}>
      <Tag text={v.headline} color={v.color} />
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Icon name={icon} style={{ fontSize: 18, color: C.sub }} />
        <span style={{ fontSize: 12, fontWeight: 700, wordBreak: "keep-all" }}>{v.name}</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
        <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>
        <span style={{ fontSize: 10, fontWeight: 800, color: v.color, paddingBottom: 4 }}>과열도 {v.capped !== null ? Math.round(v.capped) : "-"}</span>
      </div>
      <p style={{ margin: "10px 0 0", fontSize: 11, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>{v.desc}</p>
    </div>
  );
}

function CardSpending({ luxury, dining }: { luxury: Pick; dining: Pick }) {
  return (
    <Shell span={2} minH={210}>
      <h3 style={{ margin: "0 0 18px", fontSize: 15, fontWeight: 800 }}>여윳돈이 향하는 곳</h3>
      <div style={{ display: "flex", gap: 32 }}>
        <SubSpend v={luxury} icon="shopping_bag" />
        <div style={{ width: 1, background: C.line }} />
        <SubSpend v={dining} icon="restaurant" />
      </div>
    </Shell>
  );
}

// 업비트 — 김치프리미엄 / 거래량 강도 서브바 (details 있으면 목업 원본)
function CardUpbit({ v }: { v: Pick }) {
  const dt = v.details;
  const volLabel = (p: number) => (p >= 100 ? "HIGH" : p >= 60 ? "MID" : "LOW");
  return (
    <Shell minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="currency_bitcoin" iconSize={22} color={v.color} name={v.name} right={<span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>} />
      <div style={{ marginTop: "auto" }}>
        {dt ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <UpbitSubBar
              label="김치 프리미엄"
              value={`${(dt.kimchi_premium ?? 0) > 0 ? "+" : ""}${(dt.kimchi_premium ?? 0).toFixed(1)}%`}
              pct={dt.kimchi_progress ?? 0}
              color={(dt.kimchi_premium ?? 0) >= 0 ? C.hot : C.cold}
            />
            <UpbitSubBar label="거래량 강도" value={volLabel(dt.volume_progress ?? 0)} pct={dt.volume_progress ?? 0} color={C.hot} />
          </div>
        ) : (
          <HeatBar v={v} />
        )}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 서울 맑은 날씨 — 아이콘 + 게이지 바
function CardWeather({ v }: { v: Pick }) {
  return (
    <Shell minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="wb_sunny" iconSize={22} name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10 }}>
        <Icon name={(v.score ?? 0) >= 50 ? "clear_day" : "cloudy"} style={{ fontSize: 52, color: v.color }} />
        <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 800, color: C.ink }}>{v.disp}{v.unit}</span>
        <div style={{ width: "100%", height: 8, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${v.capped ?? 0}%`, background: `linear-gradient(90deg,${C.neutral},${C.hot})` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", width: "100%", fontSize: 9, fontWeight: 700, color: C.sub }}>
          <span>흐림</span>
          <span>쾌청</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

function SectionHeading({ title }: { title: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
      <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: C.ink }}>{title}</h2>
      <div style={{ height: 1, flex: 1, background: C.line }} />
    </div>
  );
}

// ── 페이지 ────────────────────────────────────────────────────────
// 목업에서 명시적으로 배치·결합·순서가 정해진 slug들. 이 목록에 없는
// 공개 지표는 각 섹션 끝에 일반 카드로 덧붙여 자동 노출을 유지한다.
const LAID_OUT = new Set([
  "buffett_index", "leverage_etf_volume", "market_actions_30d", "top10_market_cap_concentration",
  "kospi_high_gap", "vkospi", "vix_vkospi_spread", "kospi_asia_relative_strength",
  "kospi_gold_ratio", "kosdaq_kospi_ratio", "kospi_volume_surge", "usdkrw_volatility",
  "us10y", "copper_price_momentum", "yield_curve_spread",
  "naver_search_trend", "dcinside_post_count", "news_sentiment", "bestseller_finance_ratio",
  "youtube_finance_search_views", "luxury_consumption_index", "fine_dining_search_index",
  "upbit_speculation_index", "weather_sunshine_index", "github_trading_bot_repos",
  "small_business_crisis_index",
]);

const FALLBACK_ICONS: Record<string, string> = {
  시장: "insights",
  감성: "tag",
};

function GenericCard({ v, icon }: { v: Pick; icon: string }) {
  return (
    <Shell hit={v.isHit} minH={210}>
      {v.isHit && <HitBadge label="🎯 HIT" small />}
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon={icon} iconSize={22} name={v.name} color={v.color} />
      <Big disp={v.disp} unit={v.unit} color={v.color} size={30} />
      <div style={{ marginTop: "auto" }}>
        <HeatBar v={v} />
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

export default async function Home() {
  const [dailyScore, indicators] = await Promise.all([getLatestDailyScore(), getPublicIndicators()]);

  const bySlug = new Map(indicators.map((i) => [i.slug, i]));
  const p = (slug: string) => pick(bySlug.get(slug));
  const countHits = (cat: IndicatorCategory) =>
    indicators.filter((i) => i.category === cat && (i.latest?.normalized_score ?? 0) >= 100).length;

  const extra = (cat: IndicatorCategory) =>
    indicators.filter((i) => i.category === cat && !LAID_OUT.has(i.slug));

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        background: C.bg,
        color: C.ink,
        fontFamily: "'Plus Jakarta Sans', var(--font-pretendard), sans-serif",
        WebkitFontSmoothing: "antialiased",
        overflow: "hidden",
      }}
    >
      <Sidebar />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar dailyScore={dailyScore} />
        <main className="hz-scroll" style={{ flex: 1, overflowY: "auto", padding: 40 }}>
          <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 56 }}>
            {dailyScore ? (
              <Hero dailyScore={dailyScore} tradHits={countHits("시장")} socialHits={countHits("감성")} />
            ) : (
              <section style={{ background: C.card, borderRadius: 24, padding: 44, textAlign: "center", color: C.sub }}>
                아직 계산된 스코어가 없습니다.
              </section>
            )}

            {/* 시장 지표 (category=시장) */}
            <section>
              <SectionHeading title="시장 지표" />
              <div className="hz-grid">
                <CardBuffett v={p("buffett_index")} />
                <CardLeverage v={p("leverage_etf_volume")} />
                <CardMarketActions v={p("market_actions_30d")} />
                <CardTop10 v={p("top10_market_cap_concentration")} />
                <CardHighGap v={p("kospi_high_gap")} />
                <CardVkospi v={p("vkospi")} />
                <CardVixSpread v={p("vix_vkospi_spread")} />
                <CardAsia v={p("kospi_asia_relative_strength")} />
                <CardRiskAssets gold={p("kospi_gold_ratio")} kosdaq={p("kosdaq_kospi_ratio")} />
                <CardVolume v={p("kospi_volume_surge")} />
                <CardFx v={p("usdkrw_volatility")} />
                <CardRangeRate v={p("us10y")} icon="account_balance" />
                <CardCopper v={p("copper_price_momentum")} />
                <CardRangeRate v={p("yield_curve_spread")} icon="trending_down" warn />
                <CardComingSoon />
                {extra("시장").map((i) => (
                  <GenericCard key={i.id} v={pick(i)} icon={FALLBACK_ICONS["시장"]} />
                ))}
              </div>
            </section>

            {/* 감성 지표 (category=감성) */}
            <section>
              <SectionHeading title="감성 지표" />
              <div className="hz-grid">
                <CardTrend v={p("naver_search_trend")} icon="search" />
                <CardSentiment v={p("dcinside_post_count")} icon="forum" span={2} />
                <CardSentiment v={p("news_sentiment")} icon="newspaper" />
                <CardTrend v={p("bestseller_finance_ratio")} icon="menu_book" />
                <CardYoutube v={p("youtube_finance_search_views")} />
                <CardSpending luxury={p("luxury_consumption_index")} dining={p("fine_dining_search_index")} />
                <CardUpbit v={p("upbit_speculation_index")} />
                <CardWeather v={p("weather_sunshine_index")} />
                <CardTrend v={p("github_trading_bot_repos")} icon="terminal" />
                <CardTrend v={p("small_business_crisis_index")} icon="storefront" />
                {extra("감성").map((i) => (
                  <GenericCard key={i.id} v={pick(i)} icon={FALLBACK_ICONS["감성"]} />
                ))}
                <a href="#" style={{ border: `2px dashed ${C.line}`, borderRadius: 20, padding: 24, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, minHeight: 210, color: C.sub, textAlign: "center" }}>
                  <Icon name="add_circle" style={{ fontSize: 34 }} />
                  <span style={{ fontSize: 14, fontWeight: 700 }}>새로운 지표 제보하기</span>
                  <span style={{ fontSize: 11, fontWeight: 500, color: "#8a919e" }}>아이디어가 있다면 알려주세요</span>
                </a>
              </div>
            </section>

            <p style={{ fontSize: 12, color: "#8a919e", textAlign: "center", paddingBottom: 8 }}>
              이 서비스는 정보 제공 목적이며, 투자 조언이나 매수·매도 추천이 아닙니다.
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
