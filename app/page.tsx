import { getLatestDailyScore, getPublicIndicators, getTopStockHighGaps } from "@/lib/data";
import type { DailyScore, IndicatorCategory, IndicatorWithLatestValue, StockHighGap } from "@/lib/data";
import { formatEokMixed, formatIndicatorValue, formatKstUpdate, sentimentTone, shortDate } from "@/lib/format";
import { C, Icon, MONO, stageForScore } from "./ui";

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

// 0~100 "과열도" 게이지용 색 — 히어로 지수의 stage 구간(저온<25·상온<50·고온<75·초고온)과
// 동일한 경계를 쓴다. heatColor는 "기준선 대비 진행률(100=임계값 도달)" 의미라 70을 과열
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
  historyPoints: { date: string; value: number }[];
  /** 자료의 실제 기준일이 몇 영업일 뒤처졌나(0~1이면 정상). details.source_date 가 있을 때만. */
  staleDays: number;
};

/**
 * KRX가 최근 영업일치를 아직 안 낸 날에도 파이프라인은 '오늘' 행을 쓴다(며칠 전
 * 자료로 계산해서). 그래서 행 날짜만 보면 항상 최신처럼 보인다. 자료를 만든
 * 스크립트가 details.source_date(YYYYMMDD)를 남기면 여기서 지연을 구해
 * 카드에 "07-16 기준"을 띄운다.
 *
 * **달력 날짜가 아니라 영업일로 센다.** 주말엔 장이 안 열리니 금요일 자료를
 * 월요일에 보는 건 정상인데, 달력으로 세면 3일이라 멀쩡한 값에 낡음 딱지가 붙는다.
 * 반환값 = source_date 다음날부터 오늘까지의 평일 수:
 *   금요일 자료를 월요일에 → 1 (정상)
 *   목요일 자료를 월요일에 → 2 (금요일치를 건너뜀 = 지연)
 * 공휴일은 달력을 따로 안 봐서 하루치 과경고가 날 수 있는데, 지연을 놓치는 쪽보다
 * 낫다고 보고 감수한다.
 */
function staleBusinessDays(details: Record<string, number> | null): number {
  const sd = details?.source_date;
  if (!sd) return 0;
  const s = String(sd);
  const src = new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T00:00:00+09:00`);
  const kstToday = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
  const today = new Date(`${kstToday}T00:00:00+09:00`);

  let count = 0;
  const cursor = new Date(src);
  cursor.setUTCDate(cursor.getUTCDate() + 1); // 자료일 다음날부터 센다
  while (cursor <= today) {
    // KST 기준 요일 — src/today 모두 KST 자정이라 UTC 요일로 봐도 어긋나지 않는다.
    const dow = new Date(cursor.getTime() + 9 * 3600 * 1000).getUTCDay();
    if (dow !== 0 && dow !== 6) count += 1;
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return count;
}

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
    // Hit = 초고온 구간(진행률 ≥ 75) 진입 — 모든 지표의 진행률이 '과열도(0~100)'로 통일돼
    // 있어(youtube는 surge_map으로 평균 대비 급증을 매핑) 예외 없이 동일 기준.
    isHit: (capped ?? 0) >= 75,
    color: heatColor(score),
    disp: f.display,
    unit: f.displayUnit,
    thDisp: tf ? `${tf.display}${tf.displayUnit}` : null,
    dirLabel: ind?.direction === "low" ? "이하" : "이상",
    details: ind?.latest?.details ?? null,
    history: ind?.history ?? [],
    historyPoints: ind?.historyPoints ?? [],
    staleDays: staleBusinessDays(ind?.latest?.details ?? null),
  };
}

/**
 * 카드 배지 문구 — 자료가 뒤처졌으면 "당일 기준" 대신 실제 기준일을 밝힌다.
 * 1영업일 지연(어제 자료로 오늘 계산)은 거래소 공표 주기상 정상이라 조용히 넘기고,
 * 2영업일부터 = 나와야 할 영업일치를 건너뛰기 시작했을 때만 기준일로 바꿔 단다.
 */
function sourceBadge(v: Pick, fresh: string): string {
  if (v.staleDays < 2 || !v.details?.source_date) return fresh;
  const s = String(v.details.source_date);
  return `${shortDate(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`)} 기준`;
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
        borderRadius: 14,
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
      {hit && <HitBadge small={span === 1} />}
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


/**
 * 카드 머리 — 카더라 리포트(app/kadera의 SectionHead)와 같은 구조를 쓴다:
 * [아이콘 + 제목] 을 먼저 두고 그 아래 한 줄 설명을 붙인다.
 *
 * 예전엔 따옴표 친 기울임 헤드라인("꼭대기까지 남은 발걸음")이 제목 위에 먼저 왔고
 * 아이콘 색이 과열도에 따라 카드마다 달라 두 페이지가 다른 서비스처럼 보였다.
 * 아이콘은 파랑으로 고정한다 — 과열도는 카드 안의 수치·게이지가 이미 색으로 말한다.
 */
function TitleRow({
  icon,
  name,
  desc,
  iconSize = 22,
  badge,
  right,
}: {
  icon: string;
  name: React.ReactNode;
  /** 제목 아래 한 줄 설명. 카드 하단에 자세한 설명이 따로 있으므로 짧게 둔다. */
  desc?: string | null;
  iconSize?: number;
  badge?: string;
  right?: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          justifyContent: right ? "space-between" : undefined,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name={icon} style={{ fontSize: iconSize, color: C.blue }} />
          <span style={{ fontSize: 17, fontWeight: 800, color: C.ink, lineHeight: 1.2, wordBreak: "keep-all" }}>
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
        {/* height:0 으로 감싸 제목 행의 높이 계산에서 뺀다. 제목(17px)보다 큰 숫자가
            right로 들어오면(괴리도 28px) 행이 그만큼 높아지고, alignItems:center가
            제목을 아래로 밀어 같은 행 카드들끼리 제목·부제 세로 위치가 어긋났다.
            폭은 그대로 차지하므로 space-between 배치는 유지되고, 내용은 행 중앙선에
            걸쳐 넘치며 시각적으로는 지금과 같은 위치에 보인다. */}
        {right && (
          <div style={{ height: 0, display: "flex", alignItems: "center", flexShrink: 0 }}>
            {right}
          </div>
        )}
      </div>
      {desc && (
        <p style={{ margin: "7px 0 0", fontSize: 12, lineHeight: 1.5, color: C.sub, wordBreak: "keep-all" }}>{desc}</p>
      )}
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
    <div style={{ background: C.bg, borderRadius: 10, padding: "16px 18px" }}>
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
  저온: { emoji: "❄️", color: C.cold, zone: "저온 구간" },
  상온: { emoji: "🌡️", color: C.neutral, zone: "상온 구간" },
  고온: { emoji: "🔥", color: C.hot, zone: "고온 구간" },
  초고온: { emoji: "🌋", color: C.mania, zone: "초고온 구간" },
};

// LLM 요약 문장을 서식 있는 노드로 렌더한다.
//  - **...** → 굵게(중요 부분: 지표 이름·핵심 수치 등)
//  - 온도 단어(저온/상온/고온/초고온) → 해당 구간 색으로 굵게 (STAGE_META 색 재사용)
// 서식이 아닌 부분은 그대로 텍스트로 둔다(짝 안 맞는 별표는 글자로 노출).
function renderRichSummary(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, pi) => {
    const bold = /^\*\*[^*]+\*\*$/.test(part);
    const content = bold ? part.slice(2, -2) : part;
    return content.split(/(저온|상온|고온|초고온)/g).map((seg, si) => {
      const tempColor = STAGE_META[seg]?.color;
      if (tempColor) {
        return (
          <b key={`${pi}-${si}`} style={{ color: tempColor, fontWeight: 800 }}>
            {seg}
          </b>
        );
      }
      if (bold) {
        return (
          <b key={`${pi}-${si}`} style={{ color: C.ink }}>
            {seg}
          </b>
        );
      }
      return seg;
    });
  });
}

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
  // 저장된 stage 문자열 대신 점수에서 직접 구간을 계산해, 라벨 변경/과거 데이터에도 견고.
  const stageLabel = stageForScore(dailyScore.score);
  const stage = STAGE_META[stageLabel] ?? { emoji: "📊", color: C.neutral, zone: stageLabel };
  const scoreDisplay = formatIndicatorValue(dailyScore.score, "%").display;
  return (
    <section
      className="hz-hero"
      style={{
        background: C.card,
        borderRadius: 16,
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
              <span style={{ fontSize: 30 }}>℃</span>
            </div>
            <div style={{ fontSize: 11, fontWeight: 800, color: stage.color, marginTop: 6 }}>지금 · {stage.zone}</div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", width: 300, padding: "0 6px", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          <span style={{ color: C.cold }}>저온</span>
          <span style={{ color: C.neutral }}>상온</span>
          <span style={{ color: C.hot }}>고온</span>
          <span style={{ color: C.mania }}>초고온</span>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 280 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 22, fontWeight: 800, color: C.blue }}>햇쩨 지수</span>
            {/* 카더라 SectionHead 의 도움말과 같은 패턴(hz-tip-wide + help 아이콘). */}
            <span
              className="hz-tip hz-tip-wide hz-tip-below"
              data-tip="시장·감성 지표 26개의 과열도(0~100)를 가중 평균해 하나의 온도로 나타낸 값이에요. 지표마다 시장에 주는 신호의 무게가 달라서, 저마다 다른 가중치를 두고 합산해요. 25·50·75를 경계로 저온·상온·고온·초고온 구간이 나뉘어요."
              style={{ display: "inline-flex", cursor: "help" }}
            >
              <Icon name="help" style={{ fontSize: 16, color: C.sub }} />
            </span>
          </span>
          {/* 상태 텍스트는 옆의 "햇쩨 지수"(22px)와 같은 크기로 둔다 — 둘이 한 쌍으로 읽히는 자리라
              크기가 다르면 상태 쪽이 부속처럼 보인다. */}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: `${stage.color}24`, color: stage.color, fontWeight: 800, fontSize: 22, padding: "5px 14px", borderRadius: 999, whiteSpace: "nowrap" }}>
            {stage.emoji} {stageLabel}
          </span>
        </div>
        <p style={{ margin: "0 0 4px", fontSize: 11, color: C.sub, fontFamily: MONO }}>최종 업데이트 · {formatKstUpdate(dailyScore.updated_at)}</p>
        <div style={{ marginTop: 20, background: C.bg, borderRadius: 12, padding: "22px 24px", display: "flex", gap: 14 }}>
          <Icon name="auto_awesome" style={{ color: C.blue, fontSize: 22, flexShrink: 0 }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 15, lineHeight: 1.6, color: "var(--c-ink-soft)", fontWeight: 500 }}>
            {/* 고정 오프너 — 두 문장을 한 문단으로. 이 아래 LLM 문장들이 각각 한 문단씩
                붙어 전체가 3문단 정도가 된다. */}
            <p style={{ margin: 0 }}>오늘은 시장 지표 <b style={{ color: C.ink }}>{tradHits}개</b>, 감성 지표 <b style={{ color: C.ink }}>{socialHits}개</b>가 기준선을 넘었어요. 지표들이 가리키는 현재 시장 온도는 <b style={{ color: stage.color }}>{stageLabel}</b> 구간이에요.</p>
            {/* LLM(generate_daily_summary.py) 상세 요약을 문장별로 줄바꿈해 이어붙인다.
                없으면(마이그레이션 전이거나 생성 실패) 오프너만 보여준다. */}
            {dailyScore.ai_summary
              ? dailyScore.ai_summary
                  .split("\n")
                  .map((s) => s.trim())
                  .filter(Boolean)
                  .slice(0, 2)
                  .map((para, i) => (
                    <p key={i} style={{ margin: 0 }}>{renderRichSummary(para)}</p>
                  ))
              : null}
          </div>
        </div>
        <p style={{ margin: "12px 2px 0", fontSize: 11, lineHeight: 1.5, color: "var(--c-muted)" }}>
          저온·상온·고온·초고온은 시장의 과열 정도를 나타낸 표현일 뿐, 재미·참고용이며 매수·매도 신호가 아니에요.
        </p>
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
// 최근 값들의 실제 추세 스파크라인. data는 시간순(오래된→최신). 차트는 위 영역을
// 꽉 채우고(선 두께는 non-scaling-stroke로 일정), 라벨은 차트에 겹치지 않게 아래
// 오른쪽에 둔다.
function Sparkline({
  data,
  color,
  label = "최근 30일",
  tips,
}: {
  data: number[];
  color: string;
  label?: string;
  /** 지점별 툴팁 문구. data 와 길이가 같을 때만 적용한다. */
  tips?: string[];
}) {
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
        {/* 선 위에 보이지 않는 세로 띠를 깔아 지점별 툴팁을 준다. SVG path 자체에는
            hover 영역이 거의 없어서(선 두께 2px) 띠로 받아야 실제로 잡힌다. */}
        {tips && tips.length === data.length && (
          <div style={{ position: "absolute", inset: 0, display: "flex" }}>
            {tips.map((tip, i) => (
              <div key={i} className="hz-tip hz-vline" data-tip={tip} style={{ flex: 1, position: "relative" }} />
            ))}
          </div>
        )}
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
      <TitleRow desc={v.headline} icon="payments" name={v.name} badge={sourceBadge(v, "당일 기준")} />
      {/* 주요 수치 크기는 VKOSPI 카드(40)를 기준으로 맞춘다. */}
      <Big disp={v.disp} unit={v.unit} color={v.color} size={40} sub={ratio !== null ? `${ratio.toFixed(1)}배` : undefined} />
      <div style={{ background: C.bg, borderRadius: 10, padding: "18px 18px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.sub, marginBottom: 6 }}>
            {/* 1칸 카드라 폭이 좁다 — 분기 표기는 "~26년 1분기"로 줄여 한 줄에 들어가게 한다. */}
            <span style={{ whiteSpace: "nowrap" }}>
              나라 경제 (GDP)
              {dt && dt.gdp_year ? (
                <span style={{ color: "var(--c-faint)", fontWeight: 600 }}> · ~{String(dt.gdp_year).slice(2)}년 {dt.gdp_q}분기</span>
              ) : null}
            </span>
            <span style={{ fontFamily: MONO, whiteSpace: "nowrap" }}>{dt && dt.gdp ? `약 ${jo(dt.gdp)}조원` : "기준 100"}</span>
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
      <TitleRow desc={v.headline} icon="rocket_launch" name={v.name} badge="당일 기준" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
        {/* 주요 수치 크기는 VKOSPI 카드(40)를 기준으로 맞춘다. */}
        <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: heatC, lineHeight: 1, letterSpacing: "-0.03em" }}>{heat}</span>
        <span style={{ fontSize: 18, fontWeight: 800, color: "var(--c-faint)" }}>/ 100</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.sub, paddingBottom: 4 }}>종합 과열도</span>
      </div>
      <div style={{ background: C.bg, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
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
      <TitleRow desc={v.headline} icon="speed" name={v.name} badge="최근 한 달" />
      {verdict ? (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginBottom: 12 }}>
          {/* 다른 카드의 주요 수치(191%·48)와 '눈에 보이는 크기'를 맞춘 값이다. 한글은
              같은 font-size 라도 글리프가 em box 를 더 꽉 채워 숫자보다 커 보인다 —
              Pretendard 800 기준 실측으로 40px 일 때 숫자는 글자높이 29.1px, "매도 우세"는
              35.9px 였다. 32px 면 28.7px 라 숫자와 거의 같아진다. font-size 를 40 으로
              맞추면 수치는 같아도 화면에서는 이 카드만 커 보인다. */}
          <span style={{ fontSize: 32, fontWeight: 800, color: verdict.c, lineHeight: 1 }}>{verdict.t}</span>
        </div>
      ) : (
        <Big disp={v.raw !== null && v.raw > 0 ? `+${v.disp}` : v.disp} color={v.color} size={44} sub="최근 30일 순 쏠림" />
      )}
      <div style={{ background: C.bg, borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
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

// 거래대금 쏠림도 — 상위10 거래대금 비중 도넛 + 상위 종목 목록 (details 활용)
function CardTurnover({ v }: { v: Pick }) {
  const c = overheatColor(v.capped);
  const share = v.raw ?? 0; // 상위10 거래대금 비중 %
  const dt = v.details as unknown as { top5?: { name: string; share: number }[]; total_jo?: number } | null;
  const top5 = dt?.top5 ?? [];
  // 비중만으론 "얼마"인지 안 보인다 — 전체 거래대금(total_jo)에 비중을 곱해 금액으로 준다.
  const totalJo = dt?.total_jo ?? null;
  const donutTip =
    totalJo != null
      ? `전체 ${totalJo.toLocaleString("ko-KR")}조원 중 상위 10종목이 ${((totalJo * share) / 100).toFixed(1)}조원`
      : `상위 10종목이 전체 거래대금의 ${share.toFixed(1)}%`;
  return (
    <Shell hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline} icon="pie_chart" name={v.name} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14 }}>
        <div style={{ position: "relative", width: 116, height: 116 }}>
          <Donut pct={share} color={c} />
          {/* 툴팁은 도넛 바깥이 아니라 안쪽 라벨에 건다 — 116px 도넛 위에 걸면 툴팁이
              카드 제목·설명 자리까지 올라가 글자를 덮는다(실측 확인). */}
          <div className="hz-tip" data-tip={donutTip} style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: MONO, fontSize: 22, fontWeight: 800, color: c, lineHeight: 1 }}>{Math.round(share)}%</span>
            <span style={{ fontSize: 8, fontWeight: 700, color: C.sub, marginTop: 2 }}>상위10 거래</span>
          </div>
        </div>
        <div style={{ width: "100%", display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 18, rowGap: 6 }}>
          {top5.slice(0, 4).map((s, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, fontWeight: 700, gap: 6 }}>
              <span style={{ color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
              <span style={{ fontFamily: MONO, fontWeight: 800, color: C.sub, flexShrink: 0 }}>{s.share}%</span>
            </div>
          ))}
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

/**
 * 코스피 신고가 괴리율 — 지수 괴리율(왼쪽) + 거래대금 상위 3종목의 괴리율(오른쪽).
 *
 * 지수만 보면 "-25%"라는 한 덩어리 숫자뿐이라 그 안에서 주도주들이 어떤 상태인지 안
 * 보인다. 지금 돈이 몰리는 종목들이 각자 고점에서 얼마나 떨어져 있는지를 나란히 두면
 * 지수 숫자가 어디서 온 건지 읽힌다(종목 선정·산출은 lib/data.ts getTopStockHighGaps).
 */
function CardHighGap({ v, tops }: { v: Pick; tops: StockHighGap[] }) {
  const gap = v.raw ?? 0;
  const fillH = Math.max(0, Math.min(100, 100 - Math.abs(gap)));
  return (
    <Shell span={2} hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline} icon="vertical_align_top" name={v.name} badge={sourceBadge(v, "")} />
      <div style={{ display: "flex", gap: 24, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontFamily: MONO, fontSize: 34, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{gap > 0 ? "+" : ""}{v.disp}{v.unit}</span>
            <span style={{ fontSize: 10, fontWeight: 700, color: C.sub, marginTop: 4 }}>{gap > 0 ? "이전 전고점 돌파" : "전고점으로부터"}</span>
          </div>
          <div style={{ alignSelf: "stretch", display: "flex", justifyContent: "center", padding: "6px 0" }}>
            <div style={{ width: 74, position: "relative", background: C.bg, borderRadius: 10, overflow: "hidden" }}>
              <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: `${fillH}%`, background: `linear-gradient(180deg,#7cbde6,${C.cold})` }} />
              <span style={{ position: "absolute", top: 6, right: 8, fontSize: 9, fontWeight: 800, color: C.ink }}>전고점</span>
            </div>
          </div>
        </div>
        {tops.length > 0 && (
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 10, borderLeft: `1px solid ${C.line}`, paddingLeft: 24 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: C.sub }}>거래대금 상위 종목의 52주 고점 대비</span>
            {tops.map((s) => {
              // 고점 대비 낙폭이 클수록 막대가 짧다 — 지수 게이지와 같은 읽기 방향.
              const pct = Math.max(0, Math.min(100, 100 + s.gapPct));
              return (
                <div key={s.code} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: C.ink, width: 68, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
                  <div style={{ flex: 1, height: 6, borderRadius: 999, background: C.bg, overflow: "hidden", minWidth: 0 }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: C.cold, borderRadius: 999 }} />
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 800, color: C.cold, width: 46, textAlign: "right" }}>
                    {s.gapPct >= 0 ? "+" : ""}{s.gapPct.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 6. VKOSPI — 반원 게이지 (과열도 + 실제 값)
/**
 * VKOSPI — 숫자를 하나만 쓴다.
 *
 * 예전엔 "과열도 23/100"과 "실제 VKOSPI 87"을 같이 보여줬는데, 초보에겐 둘 중 뭘 봐야
 * 하는지도, 왜 하나는 낮고 하나는 높은지도(과열도는 낮을수록 과열이라 역방향) 알 수
 * 없었다. 지수 값 하나만 크게 두고, 그 값이 높은지 낮은지는 최근 30일 범위 안의
 * 위치로 보여준다 — "87"만 봐선 모르지만 "73~97 중 여기"면 바로 읽힌다.
 */
function CardVkospi({ v }: { v: Pick }) {
  const hist = v.history.filter((x) => typeof x === "number");
  const lo = hist.length ? Math.min(...hist) : null;
  const hi = hist.length ? Math.max(...hist) : null;
  const cur = v.raw;
  // 범위 안 위치(0=최저, 1=최고). 최근 30일이 평평하면 가운데로 둔다.
  const pos = cur !== null && lo !== null && hi !== null && hi > lo ? (cur - lo) / (hi - lo) : 0.5;
  // 색은 '불안의 크기' 기준 — 변동성이 높을수록 시장이 불안하다(과열도와 방향이 반대).
  const c = pos >= 0.66 ? C.cold : pos <= 0.33 ? C.hot : C.sub;
  const verdict = pos >= 0.66 ? "최근 30일 중 높은 편" : pos <= 0.33 ? "최근 30일 중 낮은 편" : "최근 30일 평균 수준";
  return (
    <Shell hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline} icon="monitor_heart" name={v.name} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
          <span style={{ fontFamily: MONO, fontSize: 40, fontWeight: 800, color: c, letterSpacing: "-0.03em", lineHeight: 1 }}>{v.disp}</span>
          <span style={{ fontSize: 12, fontWeight: 800, color: C.sub }}>변동성지수</span>
          <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 800, color: c }}>{verdict}</span>
        </div>
        <div>
          <div style={{ position: "relative", height: 8, borderRadius: 999, background: `linear-gradient(90deg, ${C.hot}, var(--c-track), ${C.cold})` }}>
            <span
              style={{
                position: "absolute",
                left: `${pos * 100}%`,
                top: -3,
                transform: "translateX(-50%)",
                width: 14,
                height: 14,
                borderRadius: "50%",
                background: C.ink,
                border: `2px solid ${C.card}`,
              }}
            />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 7, fontSize: 9, fontWeight: 800 }}>
            <span style={{ color: C.hot }}>방심 {lo !== null ? Math.round(lo) : "-"}</span>
            <span style={{ color: C.sub }}>최근 30일 범위</span>
            <span style={{ color: C.cold }}>불안 {hi !== null ? Math.round(hi) : "-"}</span>
          </div>
        </div>
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
      <Shell span={2} hit={v.isHit} minH={230}>
        <TitleRow desc={v.headline} icon="public" name={v.name} badge="최근 한 달" />
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
    <Shell span={2} hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline} icon="public" name={v.name} badge="최근 한 달" />
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
    <Shell span={2} hit={gold.isHit || kosdaq.isHit} minH={230}>
      <TitleRow icon="balance" name="위험자산 VS 안전자산" desc="금·코스피를 기준으로 본 위험 선호도" />
      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        <SubRatio v={gold} icon="balance" label="코스피 강도 (vs 금)" />
        <div style={{ width: 1, background: C.line }} />
        <SubRatio v={kosdaq} icon="celebration" label="코스닥 강도 (vs 코스피)" />
      </div>
      {/* 지표가 둘인 카드의 설명 줄. Foot 과 박스 모델을 똑같이 맞춰야 같은 행에 놓인
          카드끼리 divider 가 같은 높이에 온다 — marginTop:auto 로 바닥에 붙이고,
          바깥 paddingTop 20 + 안쪽 minHeight 53/paddingTop 16 까지 Foot 과 동일하게 둔다.
          (예전엔 marginTop:16 에 minHeight 가 없어 안전장치 카드와 3px 어긋났다.) */}
      <div style={{ marginTop: "auto", paddingTop: 20 }}>
        <div style={{ display: "flex", gap: 32, boxSizing: "border-box", minHeight: 53, paddingTop: 16, borderTop: "1px solid var(--c-divider)" }}>
          <SubNote text={gold.desc} />
          <div style={{ width: 1 }} />
          <SubNote text={kosdaq.desc} />
        </div>
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
    <Shell hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline}
        icon="groups"
        name={v.name}
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
    <Shell hit={v.isHit} minH={230}>
      <TitleRow desc={v.headline} icon="waves" name={v.name} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>±{v.disp}{v.unit}</span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 50 }}>
        <Sparkline
          data={v.history}
          color={v.color}
          tips={v.historyPoints.map((pt) => `${shortDate(pt.date)} · ±${pt.value.toFixed(2)}%`)}
        />
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
        <TitleRow
          icon="credit_score"
          name={<span style={{ color: "var(--c-muted)" }}>신용융자 잔고</span>}
          desc="빚내서 주식을 산 금액"
          right={
            <span style={{ background: "var(--c-blue-tint)", color: C.blue, fontWeight: 800, padding: "4px 9px", borderRadius: 6, fontSize: 9 }}>준비 중</span>
          }
        />
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

// 실물–증시 괴리 — 두 축(실물 스트레스/증시 강세)을 나란히 보여준다. 둘 다 높을수록
// 괴리도(둘의 곱)가 커진다 = "실물 없는 랠리".
function DivergenceBar({ label, hint, value, color }: { label: string; hint: string; value: number; color: string }) {
  const level = value >= 66 ? "높음" : value >= 33 ? "보통" : "낮음";
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 12, fontWeight: 800, color: C.ink, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 10, fontWeight: 600, color: C.sub, marginBottom: 6 }}>{hint}</div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontWeight: 800, marginBottom: 4 }}>
        <span style={{ color: C.sub }}>{level}</span>
        <span style={{ color, fontFamily: MONO }}>
          {Math.round(value)}
          <span style={{ color: "var(--c-faint)" }}>/100</span>
        </span>
      </div>
      <div style={{ height: 8, background: C.track, borderRadius: 999, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, value))}%`, background: color, borderRadius: 999 }} />
      </div>
    </div>
  );
}

function CardDivergence({ v }: { v: Pick }) {
  const dt = v.details;
  const real = dt?.real_stress ?? 0;
  const market = dt?.market_strength ?? 0;
  const div = dt?.divergence ?? v.capped ?? 0;
  const c = overheatColor(div);
  return (
    <Shell span={2} hit={v.isHit} minH={236}>
      <TitleRow desc={v.headline}
        icon="compare_arrows"
        name={v.name}
        right={
          <span style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: c, letterSpacing: "-0.02em" }}>{Math.round(div)}</span>
            <span style={{ fontSize: 12, fontWeight: 800, color: "var(--c-faint)" }}>/100</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>괴리도</span>
          </span>
        }
      />
      {/* 이 카드는 span=2 인데 내용이 짧아, 같은 행의 긴 카드(증권앱)에 맞춰 늘어난 만큼
          남는 공간이 Foot 의 marginTop:auto 로 전부 아래에 몰렸다 — 박스와 divider 사이만
          56px 로 벌어졌다. 박스에도 auto 를 줘 남는 공간을 위아래가 나눠 갖게 한다
          (auto 마진 두 개면 균등 분배). 고정값이 아니라 행 높이가 달라져도 유지된다. */}
      <div style={{ background: C.bg, borderRadius: 10, padding: 16, marginTop: "auto", display: "flex", gap: 22 }}>
        <DivergenceBar label="실물 스트레스" hint="소비심리 위축(CCSI)" value={real} color={C.cold} />
        <DivergenceBar label="증시 강세" hint="신고가 근접도" value={market} color={C.hot} />
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 라인+마커형 (초보검색/재테크도서/GitHub)
// 네이버 검색지수(초보검색)는 details.vs_avg가 있어 '평소 대비 N배'로,
// 그 외(재테크도서·GitHub)는 기존 값+과열기준 라인으로 보여준다.
function CardTrend({ v, icon, span }: { v: Pick; icon: string; span?: 1 | 2 }) {
  const vsAvg = v.details?.vs_avg ?? null;
  return (
    <Shell span={span} hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon={icon} name={v.name} />
      {vsAvg !== null ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <VsAvg ratio={vsAvg} />
        </div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}{v.unit}</span>
            {v.thDisp && <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 800, color: C.hot }}>과열 기준 {v.thDisp}</span>}
          </div>
          <div style={{ flex: 1, position: "relative", minHeight: 52 }}>
            <Sparkline data={v.history} color={v.color} />
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
// 감성 카드의 헤드라인은 '낙관:비관 비율'(중립 제외) — 카더라 리포트의 테마 막대와
// 같은 언어다. 'N pt'(순감성)는 정확하지만 그 수가 뭔지 설명 없이는 안 읽혔다.
//
// 비율은 raw_value(순감성)만으로 되돌릴 수 없어(중립 건수가 사라진다) 파이프라인이
// details에 남긴 건수를 쓴다. 그 키가 아직 없는 과거 행은 예전 표기로 폴백한다 —
// 파이프라인이 한 번 더 돌면 자연히 새 표기로 바뀐다.
function sentimentRatio(
  details: Record<string, number> | null,
): { pos: number; neg: number; decided: number; total: number } | null {
  const p = details?.pos_count;
  const n = details?.neg_count;
  if (typeof p !== "number" || typeof n !== "number") return null;
  const decided = p + n;
  // 낙관+비관이 몇 건 안 되면 한두 건에 100:0이 찍혀 실제보다 단정적으로 보인다.
  // 카더라 테마 막대와 같은 하한(8건)을 쓴다.
  if (decided < 8) return null;
  const pos = Math.round((p / decided) * 100);
  // 전체 건수(중립 포함)는 '몇 건을 보고 낸 비율인지' 캡션에 쓴다. 옛 행에 없을 수 있어
  // 없으면 낙관+비관만으로 대신한다.
  const total = typeof details?.total_count === "number" ? details.total_count : decided;
  return { pos, neg: 100 - pos, decided, total };
}

function CardSentiment({
  v,
  icon,
  // 무엇을 센 건수인지는 지표마다 다르다(디시=게시글, 뉴스=뉴스). "낙관:비관 · N건"처럼
  // 비율 설명을 반복하는 것보다, 표본이 뭔지 알려주는 쪽이 정보량이 크다.
  countNoun,
  span = 1,
}: {
  v: Pick;
  icon: string;
  countNoun: string;
  span?: 1 | 2;
}) {
  const raw = v.raw ?? 0;
  const ratio = sentimentRatio(v.details);
  // 막대는 헤드라인과 **같은 기준**을 써야 한다. 비율 표기가 가능한 날엔 낙관 비중을
  // 그대로 축에 올린다(50=중립). 한 카드 안에서 헤드라인은 낙관인데 막대는 비관을
  // 가리키는 모순이 생기지 않게 하려는 것 — 카더라 센티먼트의 색/라벨 어긋남과 같은 종류의
  // 사고를 여기서 미리 막는다.
  //
  // 건수가 없는 옛 행은 순감성(-100~100)으로 폴백한다. 뉴스·디시 모두 (긍정-부정)/전체×100
  // 이라 단위가 같으므로 공유 절대 축(bar 절반폭 = |순감성%|, ±50 캡)을 쓴다 — 지표별
  // details.scale로 정규화하면 디시가 자기 범위의 극단이라 뉴스보다 길어 보이는 착시가 났다.
  const pos = ratio ? ratio.pos : 50 + Math.max(-50, Math.min(50, raw));
  const optimistic = ratio ? ratio.pos >= 50 : raw >= 0;
  // 색도 라벨과 같은 3구간을 따른다. 단순히 50 기준으로 갈라 칠하면 55:45가 "중립"이라고
  // 적힌 채 낙관색이 되는, 카더라에서 고친 것과 똑같은 어긋남이 생긴다.
  const tone = ratio ? sentimentTone(ratio.pos).tone : null;
  const barColor = tone
    ? tone === "hot"
      ? C.hot
      : tone === "cold"
        ? C.cold
        : C.sub
    : raw === 0
      ? C.neutral
      : optimistic
        ? C.hot
        : C.cold;
  return (
    <Shell span={span} hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon={icon} name={v.name} />
      {ratio ? (
        /* 카더라 생태계 센티먼트와 같은 짜임 — 큰 수치 + 우세 라벨, 그 아래 기준 캡션.
           라벨·색 구간도 그쪽과 공유한다(lib/format.ts sentimentTone). */
        <div style={{ margin: "8px 0 0" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
            {/* 순서는 앱 전체에서 '비관 : 낙관'으로 통일한다(카더라 테마 막대도 동일). */}
            <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, letterSpacing: "-0.03em" }}>
              <span style={{ color: C.cold }}>{ratio.neg}</span>
              <span style={{ color: C.sub }}>:</span>
              <span style={{ color: C.hot }}>{ratio.pos}</span>
            </span>
            <span style={{ fontSize: 12, fontWeight: 800, color: barColor }}>{sentimentTone(ratio.pos).label}</span>
          </div>
          <div style={{ fontSize: 10, color: C.sub, marginTop: 4 }}>
            {countNoun} <span style={{ fontFamily: MONO }}>{ratio.total.toLocaleString("ko-KR")}</span>건 분석
          </div>
        </div>
      ) : (
        <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: barColor, letterSpacing: "-0.03em", margin: "8px 0 0" }}>
          {raw > 0 ? "+" : ""}
          {v.disp}
          {v.unit}
        </div>
      )}
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
      <TitleRow desc={v.headline} icon="play_circle" name={v.name} />
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
    <Shell span={2} hit={luxury.isHit || dining.isHit} minH={210}>
      <TitleRow icon="local_mall" name="여윳돈이 향하는 곳" desc="명품·외식 검색량으로 본 소비 심리" />
      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        <SubSpend v={luxury} icon="shopping_bag" />
        <div style={{ width: 1, background: C.line }} />
        <SubSpend v={dining} icon="restaurant" />
      </div>
      {/* 지표가 둘인 카드의 설명 줄. Foot 과 박스 모델을 똑같이 맞춰야 같은 행에 놓인
          카드끼리 divider 가 같은 높이에 온다 — marginTop:auto 로 바닥에 붙이고,
          바깥 paddingTop 20 + 안쪽 minHeight 53/paddingTop 16 까지 Foot 과 동일하게 둔다.
          (예전엔 marginTop:16 에 minHeight 가 없어 안전장치 카드와 3px 어긋났다.) */}
      <div style={{ marginTop: "auto", paddingTop: 20 }}>
        <div style={{ display: "flex", gap: 32, boxSizing: "border-box", minHeight: 53, paddingTop: 16, borderTop: "1px solid var(--c-divider)" }}>
          <SubNote text={luxury.desc} />
          <div style={{ width: 1 }} />
          <SubNote text={dining.desc} />
        </div>
      </div>
    </Shell>
  );
}

// 업비트 — 김치프리미엄 / 거래량 강도 서브바 (details 있으면 목업 원본)
function CardUpbit({ v }: { v: Pick }) {
  const dt = v.details;
  const volLabel = (p: number) => (p >= 100 ? "HIGH" : p >= 60 ? "MID" : "LOW");
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon="currency_bitcoin" name={v.name} />
      {/* 이 지표의 raw_value는 두 서브지표의 '기준값 대비 진행률' 가중평균이라 0~100
          과열도 점수다 — 감성 지표의 pt(순감성)와는 축이 다르다. 같은 'pt'를 달면
          둘이 같은 단위처럼 보여 오해를 키우므로 '/100'으로 척도를 드러낸다. */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 3, marginBottom: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 800, color: v.color, letterSpacing: "-0.03em" }}>{v.disp}</span>
        <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: C.sub }}>/100</span>
        <span style={{ fontSize: 10, fontWeight: 700, color: C.sub, marginLeft: 4 }}>과열도</span>
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

// 개인 순매수 강도 — 최근 5거래일 누적 + 일별 순매수/순매도 다이버징 바
function CardNetBuy({ v }: { v: Pick }) {
  const cum = v.raw ?? 0;
  const dt = v.details as unknown as { daily5?: number[]; dates5?: number[] } | null;
  const daily = dt?.daily5 ?? [];
  // 거래일은 주말·휴장을 건너뛰어 화면에서 역산할 수 없다 — 파이프라인이 넣어준
  // YYYYMMDD 정수를 그대로 쓴다. 옛 행에는 없을 수 있어 빈 배열로 폴백한다.
  const dates = dt?.dates5 ?? [];
  // YYYYMMDD 정수 → "M/D"(shortDate 는 하이픈 문자열을 받는다).
  const ymdShort = (ymd: number) => shortDate(`${String(ymd).slice(0, 4)}-${String(ymd).slice(4, 6)}-${String(ymd).slice(6, 8)}`);
  const maxAbs = Math.max(1, ...daily.map((d) => Math.abs(d)));
  const isBuy = cum >= 0;
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon="person" name={v.name} />
      <div style={{ margin: "6px 0 2px" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: C.sub }}>최근 5거래일 누적</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          {/* "12,929억"은 한눈에 안 읽히고 "1.3조원"은 끝자리가 날아간다 — 둘을 함께 쓴다. */}
          <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 800, color: isBuy ? C.hot : C.cold, letterSpacing: "-0.03em" }}>
            {cum >= 0 ? "+" : ""}{formatEokMixed(cum)}
          </span>
          <span style={{ fontSize: 12, fontWeight: 800, color: isBuy ? C.hot : C.cold }}>{isBuy ? "순매수" : "순매도"}</span>
        </div>
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, minHeight: 60 }}>
        {daily.map((d, i) => {
          const px = Math.round((Math.abs(d) / maxAbs) * 24);
          const buy = d >= 0;
          const ymd = dates[i];
          const label = ymd
            ? `${ymdShort(ymd)} · ${d >= 0 ? "+" : ""}${formatEokMixed(d)} ${d >= 0 ? "순매수" : "순매도"}`
            : `${d >= 0 ? "+" : ""}${formatEokMixed(d)}`;
          return (
            <div
              key={i}
              className="hz-tip"
              data-tip={label}
              style={{ flex: 1, position: "relative", height: 56 }}
            >
              <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: C.line }} />
              <div style={{ position: "absolute", left: "22%", right: "22%", height: px, background: buy ? C.hot : C.cold, borderRadius: 2, ...(buy ? { bottom: "50%" } : { top: "50%" }) }} />
            </div>
          );
        })}
      </div>
      {/* 예전엔 "5일 전 / 어제" 였는데 마지막 막대는 보통 '오늘'이라 틀린 표기였다.
          이제 dates5 가 있으니 실제 거래일을 적는다(거래일이라 달력상 5일 전이 아닐 수도 있다). */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontWeight: 700, color: "var(--c-faint)", marginTop: -4, marginBottom: 2 }}>
        <span>{dates.length ? ymdShort(dates[0]) : "5일 전"}</span>
        <span>{dates.length ? ymdShort(dates[dates.length - 1]) : "최근"}</span>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 투자자예탁금 — 대기 매수 자금(조원) + 최근 추이
function CardDeposit({ v }: { v: Pick }) {
  const c = overheatColor(v.capped);
  const jo = (v.details as unknown as { jo?: number })?.jo ?? (v.raw ?? 0) / 10000;
  // 예전엔 details.recent_jo(조원 배열)를 썼지만 날짜가 없어 툴팁을 못 만들었다.
  // historyPoints 는 날짜를 갖고 있고 값은 억원이라 1e4 로 나눠 조원으로 맞춘다.
  const points = v.historyPoints.map((pt) => ({ date: pt.date, jo: pt.value / 10000 }));
  const recent = points.length
    ? points.map((pt) => pt.jo)
    : ((v.details as unknown as { recent_jo?: number[] })?.recent_jo ?? []);
  const change = recent.length >= 2 ? recent[recent.length - 1] - recent[0] : 0;
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon="savings" name={v.name} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, margin: "6px 0 4px" }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: c, letterSpacing: "-0.03em" }}>{jo.toFixed(1)}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>조원</span>
        <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 800, color: change >= 0 ? C.hot : C.cold }}>
          최근 {change >= 0 ? "+" : ""}{change.toFixed(1)}조
        </span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 52 }}>
        <Sparkline
          data={recent}
          color={c}
          tips={points.length === recent.length ? points.map((pt) => `${shortDate(pt.date)} · ${pt.jo.toFixed(1)}조원`) : undefined}
        />
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 옵션 풋/콜 비율 — 콜(탐욕) vs 풋(공포) 거래량 비중. (KRX 옵션 API 승인 전까지 임시 데이터)
function CardPutCall({ v }: { v: Pick }) {
  const dt = v.details as unknown as {
    put_vol?: number; call_vol?: number; put_eok?: number; call_eok?: number;
  } | null;
  const put = dt?.put_vol ?? 0;
  const call = dt?.call_vol ?? 0;
  // 계약 수는 행사가마다 단가가 달라 규모 감각을 못 준다 — 툴팁엔 거래대금을 쓴다.
  const tip = (kind: "call" | "put") => {
    const vol = kind === "call" ? call : put;
    const eok = kind === "call" ? dt?.call_eok : dt?.put_eok;
    const head = kind === "call" ? "콜(상승 베팅)" : "풋(하락 대비)";
    return eok != null
      ? `${head} · ${formatEokMixed(eok)} · ${vol.toLocaleString("ko-KR")}계약`
      : `${head} · ${vol.toLocaleString("ko-KR")}계약`;
  };
  const total = put + call || 1;
  const callShare = (call / total) * 100;
  const ratio = call > 0 ? put / call : 0; // 풋/콜
  const greedy = callShare >= 50;
  const c = greedy ? C.hot : C.cold;
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon="casino" name={v.name} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "6px 0 14px" }}>
        <span style={{ fontFamily: MONO, fontSize: 26, fontWeight: 800, color: c, letterSpacing: "-0.03em" }}>{ratio.toFixed(2)}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>풋/콜</span>
        <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 800, color: c }}>{greedy ? "콜 우세" : "풋 우세"}</span>
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 8 }}>
        <div style={{ display: "flex", height: 24, borderRadius: 8, overflow: "hidden" }}>
          <div className="hz-tip" data-tip={tip("call")} style={{ width: `${callShare}%`, background: C.hot, display: "flex", alignItems: "center", paddingLeft: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: "#fff" }}>콜 {Math.round(callShare)}%</span>
          </div>
          <div className="hz-tip" data-tip={tip("put")} style={{ width: `${100 - callShare}%`, background: C.cold, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: "#fff" }}>풋 {Math.round(100 - callShare)}%</span>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontWeight: 800 }}>
          <span style={{ color: C.hot }}>콜 = 상승 베팅</span>
          <span style={{ color: C.cold }}>풋 = 하락 대비</span>
        </div>
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

// 증권 앱 인기차트 순위 — 차트인 앱 수 + 최고 순위 + 앱 목록 (details 활용)
function CardBrokerage({ v }: { v: Pick }) {
  const c = overheatColor(v.capped);
  const count = v.details?.count ?? 0;
  const topRank = v.details?.top_rank ?? null;
  const charted =
    (v.details as unknown as { charted?: { name: string; rank: number }[] })?.charted ?? [];
  // 긴 앱 이름을 짧게: 첫 구분자(-, (, ,) 앞부분만, 18자 제한
  const shortName = (n: string) => (n.split(/[-(,]/)[0].trim().slice(0, 18) || n);
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon="leaderboard" name={v.name} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "6px 0 10px" }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 800, color: c, letterSpacing: "-0.03em" }}>{count}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.sub }}>개 앱 인기차트 진입</span>
        {topRank !== null && (
          <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 800, color: c }}>최고 {topRank}위</span>
        )}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5 }}>
        {charted.slice(0, 4).map((app, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, fontWeight: 700, gap: 8 }}>
            <span style={{ color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{shortName(app.name)}</span>
            <span style={{ fontFamily: MONO, fontWeight: 800, color: C.sub, flexShrink: 0 }}>{app.rank}위</span>
          </div>
        ))}
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
  "buffett_index", "leverage_etf_volume", "market_actions_30d", "turnover_concentration",
  "kospi_high_gap", "vkospi", "kospi_asia_relative_strength",
  "kospi_gold_ratio", "kosdaq_kospi_ratio", "kospi_volume_surge", "usdkrw_volatility",
  "individual_net_buy", "put_call_ratio", "investor_deposit",
  "naver_search_trend", "dcinside_post_count", "news_sentiment", "bestseller_finance_ratio",
  "youtube_finance_search_views", "luxury_consumption_index", "fine_dining_search_index",
  "upbit_speculation_index", "github_trading_bot_repos", "brokerage_app_rank",
  "small_business_crisis_index",
]);

const FALLBACK_ICONS: Record<string, string> = {
  시장: "insights",
  감성: "tag",
};

function GenericCard({ v, icon }: { v: Pick; icon: string }) {
  return (
    <Shell hit={v.isHit} minH={210}>
      <TitleRow desc={v.headline} icon={icon} name={v.name} />
      <Big disp={v.disp} unit={v.unit} color={v.color} size={30} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
        <HeatBar v={v} />
      </div>
      <Foot text={v.desc} />
    </Shell>
  );
}

export default async function Home() {
  const [dailyScore, indicators, topGaps] = await Promise.all([
    getLatestDailyScore(),
    getPublicIndicators(),
    getTopStockHighGaps(3),
  ]);

  const bySlug = new Map(indicators.map((i) => [i.slug, i]));
  const p = (slug: string) => pick(bySlug.get(slug));
  // 카드 isHit과 완전히 동일한 기준(youtube 예외 포함)으로 히어로 카운트를 맞춘다.
  const countHits = (cat: IndicatorCategory) =>
    indicators.filter((i) => i.category === cat && pick(i).isHit).length;

  const extra = (cat: IndicatorCategory) =>
    indicators.filter((i) => i.category === cat && !LAID_OUT.has(i.slug));

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 56 }}>
            {dailyScore ? (
              <Hero dailyScore={dailyScore} tradHits={countHits("시장")} socialHits={countHits("감성")} />
            ) : (
              <section style={{ background: C.card, borderRadius: 16, padding: 44, textAlign: "center", color: C.sub }}>
                아직 계산된 스코어가 없습니다.
              </section>
            )}

            {/* 시장 지표 (category=시장) */}
            <section>
              <SectionHeading title="시장 지표" />
              <div className="hz-grid">
                {/* 순서 = 가중치(config/indicator_weights.py) × 직관성 × 변동성.
                    ① 가중치 1·2위(4.5/4.0)를 2칸으로 맨 앞에 — 둘 다 설명이 필요 없는 지표다.
                    ② 그 다음 핵심 수급·심리를 1칸으로 묶고,
                    ③ 콘텐츠가 풍부한 2칸 카드들, ④ 해석이 한 단계 필요한 지표 순.
                    버핏지수는 예전에 맨 앞이었지만 분기 GDP 기반이라 30일 변동계수가
                    0.04로 거의 안 움직여(가중치 주석의 "느림·비타이밍"과 같은 이유) 뒤로 뺐다. */}
                <CardHighGap v={p("kospi_high_gap")} tops={topGaps} />
                <CardVolume v={p("kospi_volume_surge")} />
                <CardDeposit v={p("investor_deposit")} />
                <CardVkospi v={p("vkospi")} />
                <CardNetBuy v={p("individual_net_buy")} />
                <CardPutCall v={p("put_call_ratio")} />
                <CardTurnover v={p("turnover_concentration")} />
                <CardMarketActions v={p("market_actions_30d")} />
                <CardRiskAssets gold={p("kospi_gold_ratio")} kosdaq={p("kosdaq_kospi_ratio")} />
                <CardBuffett v={p("buffett_index")} />
                <CardLeverage v={p("leverage_etf_volume")} />
                <CardFx v={p("usdkrw_volatility")} />
                <CardAsia v={p("kospi_asia_relative_strength")} />
                <CardComingSoon />
                {/* 순서 = 가중치 × 직관성 × 변동성. 칸 합계 20으로 5행이 정확히 채워진다.
                    VIX 대비 VKOSPI 스프레드는 내렸다 — 1년의 76%가 과열도 0이라 종합점수에
                    기여하지 못했고, VKOSPI 에서 파생된 지표라 VKOSPI 카드와 겹쳤다.
                    그 한 칸을 버핏지수(1→2칸)로 돌려 총량은 그대로다.
                    행 구성: [신고가2·거래대금·예탁금] [VKOSPI·순매수·풋콜·쏠림]
                             [안전장치2·위험자산2] [버핏2·레버리지2]
                             [환율·아시아2·준비중] */}
                {extra("시장").map((i) => (
                  <GenericCard key={i.id} v={pick(i)} icon={FALLBACK_ICONS["시장"]} />
                ))}
              </div>
            </section>

            {/* 감성 지표 (category=감성) */}
            <section>
              <SectionHeading title="감성 지표" />
              <div className="hz-grid">
                {/* 시장 지표와 같은 원칙으로 순서만 바꿨다 — 칸 수는 기존과 동일(12칸).
                    검색량(가중치 3.0)과 코인 투기를 앞세우고, 명품·오마카세는 재미는 크지만
                    가중치 0.5+0.5에 후행 지표라 뒤로, 베스트셀러는 30일간 값이 2종류뿐일
                    만큼 안 움직여 맨 뒤로 뺐다.
                    행 구성: [검색량·코인·디씨·뉴스] [증권앱·유튜브·실물괴리2]
                             [명품2·봇레포·베스트셀러] — 3행이 정확히 채워진다. */}
                <CardTrend v={p("naver_search_trend")} icon="search" />
                <CardUpbit v={p("upbit_speculation_index")} />
                <CardSentiment v={p("dcinside_post_count")} icon="forum" countNoun="게시글" />
                <CardSentiment v={p("news_sentiment")} icon="newspaper" countNoun="뉴스" />
                <CardBrokerage v={p("brokerage_app_rank")} />
                <CardYoutube v={p("youtube_finance_search_views")} />
                <CardDivergence v={p("small_business_crisis_index")} />
                <CardSpending luxury={p("luxury_consumption_index")} dining={p("fine_dining_search_index")} />
                <CardTrend v={p("github_trading_bot_repos")} icon="terminal" />
                <CardTrend v={p("bestseller_finance_ratio")} icon="menu_book" />
                {extra("감성").map((i) => (
                  <GenericCard key={i.id} v={pick(i)} icon={FALLBACK_ICONS["감성"]} />
                ))}
                <a href="https://forms.gle/P4wzp2DkP2wyTPWP9" target="_blank" rel="noopener noreferrer" style={{ border: `2px dashed ${C.line}`, borderRadius: 14, padding: 24, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, minHeight: 210, color: C.sub, textAlign: "center" }}>
                  <Icon name="add_circle" style={{ fontSize: 34 }} />
                  <span style={{ fontSize: 14, fontWeight: 700 }}>새로운 지표 제보하기</span>
                  <span style={{ fontSize: 11, fontWeight: 500, color: "var(--c-muted)" }}>아이디어가 있다면 알려주세요</span>
                </a>
              </div>
            </section>
    </div>
  );
}
