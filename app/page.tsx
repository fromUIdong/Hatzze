import { getLatestDailyScore, getPublicIndicators } from "@/lib/data";
import type { DailyScore, IndicatorCategory, IndicatorWithLatestValue } from "@/lib/data";
import { formatIndicatorValue, formatKstDateTime } from "@/lib/format";
import { C, Icon, MONO } from "./ui";

// 지표는 하루 단위(GitHub Actions 배치)로 갱신되므로, 빌드 시점에 정적으로
// 굳어버리지 않도록 매 요청마다 서버에서 새로 조회한다.
export const dynamic = "force-dynamic";

function heatColor(score: number | null): string {
  if (score === null) return C.sub;
  if (score >= 100) return C.mania;
  if (score >= 70) return C.hot;
  if (score >= 33) return C.neutral;
  return C.cold;
}

// 0~100 "과열도" 게이지용 색 — 히어로 지수의 stage 구간(공포<25·보통<50·과열<75·광기)과
// 동일한 경계를 쓴다. heatColor는 "기준선 대비 진행률(100=Hit)" 의미라 70을 과열
// 경계로 두지만, 이런 게이지는 50이 과열 시작이라 별도 매핑이 맞다.
function overheatColor(pct: number | null): string {
  if (pct === null) return C.sub;
  if (pct >= 75) return C.mania;
  if (pct >= 50) return C.hot;
  if (pct >= 25) return C.neutral;
  return C.cold;
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
  history: number[];
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
    history: ind?.history ?? [],
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
        // 모든 카드의 divider(Foot 등) 가로 위치가 동일하도록 span과 무관하게
        // 안쪽 여백을 통일한다.
        padding: 24,
        display: "flex",
        flexDirection: "column",
        position: "relative",
        minHeight: minH,
        boxShadow: hit
          ? "0 8px 24px -12px rgba(255,107,129,0.35)"
          : "0 4px 6px -1px var(--c-shadow), 0 2px 4px -2px var(--c-shadow)",
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
    // 바깥 div: marginTop auto 로 카드 바닥에 붙이고(같은 줄 divider 높이 일치),
    // paddingTop 으로 divider 위에 항상 여백을 둔다 — 콘텐츠가 카드를 꽉 채워
    // auto 여백이 0이 돼도 divider가 콘텐츠에 붙지 않도록. 설명 영역은 2줄
    // (minHeight)로 통일한다.
    <div style={{ marginTop: "auto", paddingTop: 20 }}>
      <p
        style={{
          margin: 0,
          boxSizing: "border-box",
          minHeight: 53,
          paddingTop: 16,
          fontSize: 12,
          color,
          fontWeight: 600,
          borderTop: "1px solid var(--c-divider)",
          lineHeight: 1.5,
        }}
      >
        {text}
      </p>
    </div>
  );
}

// 과열도 진행 바 (세부 데이터가 없는 카드의 공용 시각화).
function HeatBar({ v }: { v: Pick }) {
  if (v.capped === null) return null;
  const c = overheatColor(v.capped); // 과열도 게이지는 stage 구간(50=과열) 색을 쓴다
  return (
    <div style={{ background: C.bg, borderRadius: 14, padding: "16px 18px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 800, marginBottom: 8 }}>
        <span style={{ color: C.sub }}>과열도</span>
        <span style={{ color: c, fontFamily: MONO }}>
          {Math.round(v.capped)}
          <span style={{ color: "var(--c-faint)" }}>/100</span>
        </span>
      </div>
      <div style={{ position: "relative", height: 10, background: C.track, borderRadius: 999, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${v.capped}%`,
            background: v.isHit ? `linear-gradient(90deg, ${C.hot}, ${C.mania})` : c,
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
  공포: { emoji: "🧊", color: C.cold, zone: "공포 구간" },
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
        boxShadow: "0 4px 6px -1px var(--c-shadow), 0 2px 4px -2px var(--c-shadow)",
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
          <span style={{ color: C.cold }}>공포</span>
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
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "var(--c-ink-soft)", fontWeight: 500 }}>
            오늘은 시장 지표 <b style={{ color: C.ink }}>{tradHits}개</b>, 감성 지표 <b style={{ color: C.ink }}>{socialHits}개</b>가 기준선을 넘었어요. 지표들이 가리키는 현재 시장 온도는 <b style={{ color: stage.color }}>{dailyScore.stage}</b> 구간이에요.
          </p>
        </div>
      </div>
    </section>
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

// 최근 값들의 실제 추세 스파크라인. data는 시간순(오래된→최신). 차트는 위 영역을
// 꽉 채우고(선 두께는 non-scaling-stroke로 일정), 라벨은 차트에 겹치지 않게 아래
// 오른쪽에 둔다.
function Sparkline({ data, color, label = "최근 30일" }: { data: number[]; color: string; label?: string }) {
  if (data.length < 2) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: C.sub }}>
        추세 데이터 쌓이는 중
      </div>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const W = 100;
  const H = 40;
  const pad = 4;
  const pts = data.map((val, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = pad + (1 - (val - min) / range) * (H - 2 * pad);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${W} ${H} L0 ${H} Z`;
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, position: "relative" }}>
        <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ position: "absolute", inset: 0 }}>
          <path d={area} fill={color} opacity={0.12} />
          <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <span style={{ alignSelf: "flex-end", fontSize: 9, fontWeight: 700, color: C.sub, marginTop: 4 }}>{label}</span>
    </div>
  );
}

// 레버리지 카드의 서브 진행률 바 (ETF 거래대금 / 선물 미결제약정)
function LevSubBar({ label, amount, value, color }: { label: string; amount: string | null; value: number; color: string }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 4 }}>{label}</div>
      {amount && <div style={{ fontFamily: MONO, fontSize: 15, fontWeight: 800, color: C.ink, marginBottom: 7 }}>{amount}</div>}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 700, color: C.sub, marginBottom: 5 }}>
        <span>과열도</span>
        <span style={{ color }}>
          {Math.round(value)}
          <span style={{ color: "var(--c-faint)" }}>/100</span>
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

// 비교 막대들의 차이를 시각적으로 강조한다 — 0이 아니라 최솟값 기준으로 스케일해
// 작은 차이도 눈에 띄게 만든다(정확한 크기는 각 막대의 숫자/배지로 전달). 값이 모두
// 같으면 전부 100으로 둔다.
function emphasizedHeights(values: number[], floorPct = 30): number[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max <= min) return values.map(() => 100);
  return values.map((v) => floorPct + ((v - min) / (max - min)) * (100 - floorPct));
}

// "평소/평균 대비 오늘" 비교 막대 높이 [평소, 오늘]. 평소를 중간 높이(baseH)에
// 고정하고 오늘을 비율만큼 비례시킨다 — 비율이 1이면 둘 다 같은 높이, 2배면 오늘이
// 두 배 높이. emphasizedHeights와 달리 작은 차이를 과장하지 않는다(1.0배≈동일 높이).
function ratioBarHeights(baseline: number | null, current: number | null, baseH = 55): [number, number] {
  if (!baseline || !current || baseline <= 0) return [baseH, baseH];
  return [baseH, Math.max(10, Math.min(100, (current / baseline) * baseH))];
}

// 아시아 카드의 4개국 상대 막대 (KOSPI=100 기준). heightPct는 차이를 강조한 0~100.
function AsiaBar({ label, sub, index, heightPct, color }: { label: string; sub: string; index: number; heightPct: number; color: string }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color }}>{Math.round(index)}</span>
      <div style={{ width: "100%", height: Math.max(10, (heightPct / 100) * 108), background: color, borderRadius: "6px 6px 0 0" }} />
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

// 김치 프리미엄 전용 양극 바 — 0을 중앙에 두고 음수(역프)면 왼쪽(파랑), 양수면
// 오른쪽(빨강)으로 채운다. ±10%를 최대로 스케일한다(업비트 기준값과 동일).
function UpbitKimchiBar({ premium }: { premium: number }) {
  const norm = Math.max(-1, Math.min(1, premium / 10));
  const pos = 50 + norm * 50;
  const color = premium >= 0 ? C.hot : C.cold;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
        <span>김치 프리미엄</span>
        <span style={{ color }}>{premium > 0 ? "+" : ""}{premium.toFixed(1)}%</span>
      </div>
      <div style={{ position: "relative", height: 8, background: C.bg, borderRadius: 999 }}>
        <div style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 2, background: "var(--c-marker)" }} />
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            background: color,
            borderRadius: 999,
            ...(premium >= 0 ? { left: "50%", width: `${pos - 50}%` } : { right: "50%", width: `${50 - pos}%` }),
          }}
        />
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
      <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 800, color: C.sub, width: 46, textAlign: "right" }}>{Math.round(pct)}점</span>
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
      <Big disp={v.disp} unit={v.unit} color={v.color} size={52} sub={ratio !== null ? `${ratio.toFixed(1)}배` : undefined} />
      <div style={{ background: C.bg, borderRadius: 14, padding: "18px 18px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
            <span>
              나라 경제 (GDP)
              {dt && dt.gdp_year ? (
                <span style={{ color: "var(--c-faint)", fontWeight: 600 }}> · 최근 4개 분기(~{dt.gdp_year} {dt.gdp_q}분기)</span>
              ) : null}
            </span>
            <span style={{ fontFamily: MONO }}>{dt && dt.gdp ? `약 ${jo(dt.gdp)}조원` : "기준 100"}</span>
          </div>
          <div style={{ height: 18, background: "var(--c-line)", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${gdpWidth}%`, background: "var(--c-hint)", borderRadius: 6 }} />
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
          <div style={{ height: 18, background: "var(--c-line)", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ height: "100%", width: "100%", background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 6 }} />
          </div>
        </div>
        <p style={{ margin: "2px 0 0", fontSize: 11, fontWeight: 700, color: "var(--c-ink-soft)", textAlign: "center" }}>
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
  // 종합 과열도 = ETF 거래대금·선물 미결제약정 과열도의 평균(아래 두 서브바의 평균).
  const heat = dt
    ? Math.round(((dt.etf_progress ?? 0) + (dt.futures_progress ?? 0)) / 2)
    : Math.round(v.capped ?? 0);
  // 종합 과열도(0~100) 자체의 구간 색을 쓴다 — v.color(기준선 진행률 기준)와 달리
  // 이 게이지는 50이 과열 시작이라 heat값을 그대로 stage 색에 매핑한다.
  const heatC = overheatColor(heat);
  const etfAmount =
    dt?.etf_value != null
      ? (() => {
          const f = formatIndicatorValue(dt.etf_value, "억원");
          return `${f.display}${f.displayUnit}`;
        })()
      : null;
  const oiAmount =
    dt?.futures_oi != null ? `${Math.round(dt.futures_oi).toLocaleString("ko-KR")}계약` : null;
  return (
    <Shell span={2} hit={v.isHit} minH={236}>
      {v.isHit && <HitBadge />}
      <Tag text={v.headline} color={heatC} />
      <TitleRow icon="rocket_launch" iconSize={30} color={heatC} name={<h3 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{v.name}</h3>} badge="당일 기준" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
        <span style={{ fontFamily: MONO, fontSize: 44, fontWeight: 800, color: heatC, lineHeight: 1, letterSpacing: "-0.03em" }}>{heat}</span>
        <span style={{ fontSize: 18, fontWeight: 800, color: "var(--c-faint)" }}>/ 100</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.sub, paddingBottom: 4 }}>종합 과열도</span>
      </div>
      <div style={{ background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ position: "relative", height: 12, background: C.line, borderRadius: 999 }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${Math.min(100, heat)}%`, background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 999 }} />
            <div style={{ position: "absolute", top: "50%", left: `${Math.min(100, heat)}%`, transform: "translate(-50%,-50%)", width: 14, height: 14, borderRadius: 999, background: heatC, border: `3px solid ${C.card}`, boxShadow: "0 1px 3px var(--c-shadow-strong)" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 700, color: C.sub, marginTop: 7 }}>
            <span>안심</span>
            <span style={{ color: C.hot }}>과열</span>
          </div>
        </div>
        {dt && (
          <>
            <div style={{ height: 1, background: "var(--c-divider-strong)" }} />
            <div style={{ display: "flex", gap: 22 }}>
              <LevSubBar label="ETF 거래대금" amount={etfAmount} value={dt.etf_progress ?? 0} color={C.hot} />
              <LevSubBar label="선물 미결제약정" amount={oiAmount} value={dt.futures_progress ?? 0} color={C.mania} />
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
      <TitleRow icon="speed" iconSize={30} color={v.color} name={<h3 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>{v.name}</h3>} badge="최근 한 달" />
      {verdict ? (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 34, fontWeight: 800, color: verdict.c, lineHeight: 1 }}>{verdict.t}</span>
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
              <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 2, background: "var(--c-marker)" }} />
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
  const c = overheatColor(v.capped); // 과열도 게이지는 stage 구간(50=과열) 색
  return (
    <Shell minH={230}>
      <Tag text={v.headline} color={c} />
      <TitleRow icon="monitor_heart" name={v.name} color={c} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4 }}>
        <HalfGauge score={v.capped ?? 0} color={c} />
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: c, lineHeight: 1 }}>{v.capped !== null ? Math.round(v.capped) : "-"}</span>
          <span style={{ fontSize: 13, fontWeight: 800, color: "var(--c-faint)" }}>/100</span>
          <span style={{ fontSize: 11, fontWeight: 800, color: c, marginLeft: 2 }}>과열도</span>
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
            <div style={{ fontSize: 9, color: "var(--c-muted)", fontWeight: 700 }}>각자 최근 1년 변동성 대비 현재 위치 (0=최저 ~ 100=최고)</div>
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
        <TitleRow icon="public" name={v.name} color={v.color} badge="최근 한 달" />
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
  // floorPct를 55로 올려 강조는 유지하되 과하지 않게 — 최소 막대가 55%까지만
  // 내려가 100 vs 117 같은 차이가 지나치게 벌어지지 않는다.
  const heights = emphasizedHeights(bars.map((b) => b.index), 55);
  return (
    <Shell span={2} minH={230}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="public" name={v.name} color={v.color} badge="최근 한 달" />
      <div style={{ fontSize: 9, color: "var(--c-muted)", fontWeight: 700, marginBottom: 4 }}>
        KOSPI를 100으로 둔 상대 지수 · 코스피 초과수익률 {v.raw !== null && v.raw > 0 ? "+" : ""}
        {v.disp}
        {v.unit}
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, paddingTop: 6 }}>
        {bars.map((b, i) => (
          <AsiaBar key={b.label} label={b.label} sub={b.sub} index={b.index} heightPct={heights[i]} color={b.color} />
        ))}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 9. 위험자산 vs 안전자산 — 금/코스닥 두 지표 결합 (둘 다 실제 값)
function SubRatio({ v, icon, label }: { v: Pick; icon: string; label: string }) {
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
        <span style={{ color: overheatColor(v.capped) }}>{v.capped !== null ? Math.round(v.capped) : "-"} / 100</span>
      </div>
      <div style={{ position: "relative", height: 10, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${v.capped ?? 0}%`, background: `linear-gradient(90deg,${C.hot},${C.mania})`, borderRadius: 999 }} />
      </div>
    </div>
  );
}

// 결합 카드는 두 서브값을 위쪽 행에, 두 간단 설명을 아래쪽 행에 나눠 담고, 그 사이에
// 카드 전체 폭 divider를 둔다 — 다른 카드들과 divider 가로 위치를 맞추기 위해서다.
function SubNote({ text }: { text: string }) {
  return (
    <p style={{ flex: 1, margin: 0, fontSize: 11, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>{text}</p>
  );
}

function CardRiskAssets({ gold, kosdaq }: { gold: Pick; kosdaq: Pick }) {
  return (
    <Shell span={2} minH={230}>
      <Tag text="위험자산 vs 안전자산" color={C.sub} />
      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        <SubRatio v={gold} icon="balance" label="코스피 강도 (vs 금)" />
        <div style={{ width: 1, background: C.line }} />
        <SubRatio v={kosdaq} icon="celebration" label="코스닥 강도 (vs 코스피)" />
      </div>
      <div style={{ display: "flex", gap: 32, marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--c-divider)" }}>
        <SubNote text={gold.desc} />
        <div style={{ width: 1 }} />
        <SubNote text={kosdaq.desc} />
      </div>
    </Shell>
  );
}

// 10. 거래대금 급증도 — 오늘 vs 30일 평균 (details 있으면 실제 평균, 없으면 과열기준 폴백)
function CardVolume({ v }: { v: Pick }) {
  const dt = v.details;
  const avg = dt?.avg_30d ?? null;
  const today = v.raw ?? null;
  const [avgH, todayH] = ratioBarHeights(avg, today);
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
          <span style={{ fontSize: 9, fontWeight: 700, color: C.sub }}>최근 거래일</span>
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
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 50 }}>
        <Sparkline data={v.history} color={v.color} />
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
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
        <div style={{ position: "relative", height: 12, borderRadius: 999, background: C.bg, overflow: "hidden" }}>
          <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${pos}%`, background: v.color }} />
        </div>
        <div style={{ position: "relative", height: 0 }}>
          <div className={warn && v.raw !== null && v.raw < 0 ? "hz-pulse-red" : undefined} style={{ position: "absolute", top: -13, transform: "translateX(-50%)", left: `${pos}%`, width: 16, height: 16, borderRadius: 999, background: v.color, border: `3px solid ${C.card}`, boxShadow: "0 1px 4px var(--c-shadow-strong)" }} />
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
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 56 }}>
        <Sparkline data={v.history} color={v.color} />
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
          <span style={{ background: "var(--c-blue-tint)", color: C.blue, fontWeight: 800, padding: "4px 9px", borderRadius: 6, fontSize: 9 }}>준비 중</span>
        </div>
        <TitleRow icon="credit_score" name={<span style={{ color: "var(--c-muted)" }}>신용융자 잔고</span>} color="var(--c-faint)" />
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="100%" height="70" viewBox="0 0 100 40" preserveAspectRatio="none">
            <path d="M0 34 L20 32 L40 28 L60 22 L80 15 L100 8" fill="none" stroke={C.line} strokeDasharray="4,3" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </div>
        <Foot text="빚내서 주식 사는 돈이 불어나면 과열의 대표 신호로 볼 수 있어요." color="var(--c-muted)" />
      </div>
    </Shell>
  );
}

// ── 소셜 지표 카드들 ──────────────────────────────────────────────

// '평소 대비 N배' — 절대 건수가 없는 네이버 검색지수(0~100 상대지수)를 직관적으로
// 보여준다. ratio = 현재 / 최근 30일 평균. 가운데 눈금(1배=평소)을 기준으로
// 오른쪽으로 넘으면 평소보다 활발(과열 방향).
function VsAvg({ ratio, size = 26 }: { ratio: number; size?: number }) {
  const c = ratio > 1.05 ? C.hot : ratio < 0.95 ? C.cold : C.sub;
  const arrow = ratio > 1.05 ? "↑" : ratio < 0.95 ? "↓" : "";
  const fill = Math.max(4, Math.min(100, (ratio / 2) * 100)); // 2배 = 꽉 참, 1배 = 50%
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 2 }}>평소 대비</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4, whiteSpace: "nowrap" }}>
        <span style={{ fontFamily: MONO, fontSize: size, fontWeight: 800, color: c, letterSpacing: "-0.03em" }}>{ratio.toFixed(1)}배</span>
        <span style={{ fontSize: 15, fontWeight: 800, color: c }}>{arrow}</span>
      </div>
      <div style={{ position: "relative", height: 8, background: C.bg, borderRadius: 999, marginTop: 8, overflow: "hidden" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${fill}%`, background: c, borderRadius: 999 }} />
        <div style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 2, background: "var(--c-marker)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontWeight: 700, color: C.sub, marginTop: 5 }}>
        <span>적음</span>
        <span>평소(1배)</span>
        <span>많음</span>
      </div>
    </div>
  );
}

// 라인+마커형 (초보검색/재테크도서/GitHub/자영업)
// 네이버 검색지수(초보검색/자영업)는 details.vs_avg가 있어 '평소 대비 N배'로,
// 그 외(재테크도서·GitHub)는 기존 값+과열기준 라인으로 보여준다.
function CardTrend({ v, icon }: { v: Pick; icon: string }) {
  const vsAvg = v.details?.vs_avg ?? null;
  return (
    <Shell minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon={icon} name={v.name} iconSize={22} color={v.color} />
      {vsAvg !== null ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <VsAvg ratio={vsAvg} />
        </div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
          </div>
          <div style={{ flex: 1, position: "relative", minHeight: 52 }}>
            <TrendLine color={v.color} down={(v.score ?? 0) < 33} />
            {v.thDisp && <span style={{ position: "absolute", top: 1, left: 2, fontSize: 8, fontWeight: 800, color: C.hot }}>과열 기준 {v.thDisp}</span>}
          </div>
        </>
      )}
      <Foot text={v.desc} />
    </Shell>
  );
}

// 중앙 기준 감성/카운트 바 (커뮤니티/뉴스)
// 감성 지표(뉴스·커뮤니티) — 과열도가 아니라 비관↔낙관 양극 게이지로 보여준다.
// raw = (긍정-부정)/전체*100 이라 -100~+100 범위. 중앙=중립, 좌=비관, 우=낙관.
function CardSentiment({ v, icon, span = 1 }: { v: Pick; icon: string; span?: 1 | 2 }) {
  const raw = v.raw ?? 0;
  // 감성 점수는 지표마다 크기가 크게 달라(디시 ±1, 뉴스 ±30) 절대 ±100 축에선
  // 한쪽이 늘 정중앙처럼 보인다. details.scale(자기 최근 |최대|)이 있으면 그걸로
  // 정규화해 '자기 최근 범위 대비'로 보여주되, 마커가 중앙 ±12(=38~62%)에서만
  // 움직이게 해 과하지 않게(은은하게) 한다. 0(중립)은 항상 중앙.
  const scale = v.details?.scale ?? null;
  const pos =
    scale && scale > 0
      ? 50 + Math.max(-1, Math.min(1, raw / scale)) * 12
      : Math.max(0, Math.min(100, (raw + 100) / 2));
  const optimistic = raw >= 0;
  const barColor = raw === 0 ? C.neutral : optimistic ? C.hot : C.cold;
  return (
    <Shell span={span} minH={210}>
      <Tag text={v.headline} color={barColor} />
      <TitleRow
        icon={icon}
        iconSize={22}
        color={barColor}
        name={v.name}
        right={
          <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: barColor }}>
            {raw > 0 ? "+" : ""}
            {v.disp}
            {v.unit}
          </span>
        }
      />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
        <div style={{ position: "relative", height: 16, background: C.bg, borderRadius: 999 }}>
          <div style={{ position: "absolute", left: "50%", top: -3, bottom: -3, width: 2, background: "var(--c-marker)" }} />
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              background: barColor,
              borderRadius: 999,
              ...(optimistic ? { left: "50%", width: `${pos - 50}%` } : { right: "50%", width: `${50 - pos}%` }),
            }}
          />
          <div style={{ position: "absolute", top: "50%", left: `${pos}%`, transform: "translate(-50%,-50%)", width: 14, height: 14, borderRadius: 999, background: barColor, border: `3px solid ${C.card}`, boxShadow: "0 1px 3px var(--c-shadow-strong)" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 800, marginTop: 8 }}>
          <span style={{ color: C.cold }}>비관</span>
          <span style={{ color: C.sub }}>중립</span>
          <span style={{ color: C.hot }}>낙관</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 유튜브 — 평소(기준) vs 오늘 막대 (HIT)
function CardYoutube({ v }: { v: Pick }) {
  const ratio = v.raw && v.threshold ? v.raw / v.threshold : null;
  const [baseH, todayH] = ratioBarHeights(v.threshold, v.raw);
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
            <div style={{ width: 26, height: `${todayH}%`, background: v.color, borderRadius: "5px 5px 0 0" }} />
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
      {v.details?.vs_avg != null ? (
        <VsAvg ratio={v.details.vs_avg} />
      ) : (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
          <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color: v.color }}>{v.disp}{v.unit}</span>
        </div>
      )}
    </div>
  );
}

function CardSpending({ luxury, dining }: { luxury: Pick; dining: Pick }) {
  return (
    <Shell span={2} minH={210}>
      <h3 style={{ margin: "0 0 18px", fontSize: 15, fontWeight: 800 }}>여윳돈이 향하는 곳</h3>
      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        <SubSpend v={luxury} icon="shopping_bag" />
        <div style={{ width: 1, background: C.line }} />
        <SubSpend v={dining} icon="restaurant" />
      </div>
      <div style={{ display: "flex", gap: 32, marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--c-divider)" }}>
        <SubNote text={luxury.desc} />
        <div style={{ width: 1 }} />
        <SubNote text={dining.desc} />
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
      <TitleRow icon="currency_bitcoin" iconSize={22} color={v.color} name={v.name} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
        {dt ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <UpbitKimchiBar premium={dt.kimchi_premium ?? 0} />
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
// 서울 맑은 날씨 — raw는 "맑음지수 = 10 - 전운량"(0~10, 클수록 맑음). "pt"는 뜻이
// 안 통해서, 날씨 표현(쾌청/맑음/흐림)과 "맑음지수 N/10"으로 직관적으로 보여준다.
function CardWeather({ v }: { v: Pick }) {
  const raw = v.raw ?? 0;
  const label = raw >= 8 ? "쾌청" : raw >= 6 ? "맑음" : raw >= 4 ? "구름 조금" : raw >= 2 ? "구름 많음" : "흐림";
  // 아이콘 기준을 라벨과 맞춘다 — 맑음(≥6)부터 해 아이콘, 그 아래는 구름 아이콘.
  const clear = raw >= 6;
  return (
    <Shell minH={210}>
      <Tag text={v.headline} color={v.color} />
      <TitleRow icon="wb_sunny" iconSize={22} name={v.name} color={v.color} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
        <Icon name={clear ? "clear_day" : "cloudy"} style={{ fontSize: 48, color: v.color }} />
        <span style={{ fontSize: 20, fontWeight: 800, color: C.ink }}>{label}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: C.sub }}>맑음지수 {raw.toFixed(1)} / 10</span>
        <div style={{ width: "100%", height: 8, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, raw * 10))}%`, background: `linear-gradient(90deg,${C.neutral},${C.hot})` }} />
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
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
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
                <CardRangeRate v={p("yield_curve_spread")} icon="trending_down" warn />
                <CardCopper v={p("copper_price_momentum")} />
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
                  <span style={{ fontSize: 11, fontWeight: 500, color: "var(--c-muted)" }}>아이디어가 있다면 알려주세요</span>
                </a>
              </div>
            </section>

      <p style={{ fontSize: 12, color: "var(--c-muted)", textAlign: "center", paddingBottom: 8 }}>
        이 서비스는 정보 제공 목적이며, 투자 조언이나 매수·매도 추천이 아닙니다.
      </p>
    </div>
  );
}
