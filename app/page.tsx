import { getLatestDailyScore, getPublicIndicators } from "@/lib/data";
import type { DailyScore, IndicatorWithLatestValue } from "@/lib/data";
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
  blue: "#0064FF",
  track: "#c9cede",
} as const;

const MONO = "'JetBrains Mono', monospace";

// 과열도(normalized_score)에 따라 온도색을 고른다. direction과 무관하게
// normalized_score가 클수록 "과열"이라는 의미로 통일돼 있어 그대로 쓴다.
function heatColor(score: number | null): string {
  if (score === null) return C.sub;
  if (score >= 100) return C.mania;
  if (score >= 70) return C.hot;
  if (score >= 33) return C.neutral;
  return C.cold;
}

// slug → Material Symbols 아이콘. 순수 표현용이라 매핑에 없는(새로 추가된)
// 지표는 기본 아이콘으로 떨어질 뿐, 화면에서 사라지지 않는다.
const ICONS: Record<string, string> = {
  buffett_index: "payments",
  leverage_etf_volume: "rocket_launch",
  market_actions_30d: "speed",
  top10_market_cap_concentration: "pie_chart",
  kospi_high_gap: "vertical_align_top",
  vkospi: "monitor_heart",
  vix_vkospi_spread: "compare_arrows",
  kospi_asia_relative_strength: "public",
  kospi_gold_ratio: "balance",
  kosdaq_kospi_ratio: "celebration",
  kospi_volume_surge: "groups",
  usdkrw_volatility: "waves",
  us10y: "account_balance",
  copper_price_momentum: "bolt",
  yield_curve_spread: "trending_down",
  naver_search_trend: "search",
  dcinside_post_count: "forum",
  news_sentiment: "newspaper",
  bestseller_finance_ratio: "menu_book",
  youtube_finance_search_views: "play_circle",
  luxury_consumption_index: "shopping_bag",
  fine_dining_search_index: "restaurant",
  upbit_speculation_index: "currency_bitcoin",
  weather_sunshine_index: "wb_sunny",
  github_trading_bot_repos: "terminal",
  small_business_crisis_index: "storefront",
};

// slug → 집계 기간 배지. 없으면 배지를 그리지 않는다.
const PERIODS: Record<string, string> = {
  buffett_index: "당일 기준",
  leverage_etf_volume: "당일 기준",
  market_actions_30d: "최근 30일",
};

function Icon({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <span className="ms" style={style}>
      {name}
    </span>
  );
}

// ── 히어로: 반원 게이지 + 요약 ────────────────────────────────────
const STAGE_META: Record<
  string,
  { emoji: string; color: string; zone: string }
> = {
  냉정: { emoji: "🧊", color: C.cold, zone: "냉정 구간" },
  보통: { emoji: "⚖️", color: C.neutral, zone: "보통 구간" },
  과열: { emoji: "🔥", color: C.hot, zone: "과열 구간" },
  광기: { emoji: "🚨", color: C.mania, zone: "광기 구간" },
};

function HeroGauge({ score }: { score: number }) {
  const s = Math.max(0, Math.min(100, score));
  const arcLen = 389.6; // π * 124 (반원)
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
      <path
        d="M 26 150 A 124 124 0 0 1 274 150"
        fill="none"
        stroke={C.bg}
        strokeWidth={22}
        strokeLinecap="round"
      />
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

function Hero({
  dailyScore,
  tradHits,
  socialHits,
}: {
  dailyScore: DailyScore;
  tradHits: number;
  socialHits: number;
}) {
  const stage = STAGE_META[dailyScore.stage] ?? {
    emoji: "📊",
    color: C.neutral,
    zone: dailyScore.stage,
  };
  const scoreDisplay = formatIndicatorValue(dailyScore.score, "%").display;

  return (
    <section
      className="hz-hero"
      style={{
        background: C.card,
        borderRadius: 24,
        boxShadow:
          "0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.08)",
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      {/* Gauge */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
        <div style={{ position: "relative", width: 300, height: 172 }}>
          <HeroGauge score={dailyScore.score} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 78, textAlign: "center" }}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 58,
                fontWeight: 800,
                color: C.ink,
                letterSpacing: "-0.04em",
                lineHeight: 1,
              }}
            >
              {scoreDisplay}
              <span style={{ fontSize: 30 }}>%</span>
            </div>
            <div style={{ fontSize: 11, fontWeight: 800, color: stage.color, marginTop: 6 }}>
              지금 · {stage.zone}
            </div>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            width: 300,
            padding: "0 6px",
            fontSize: 10,
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          <span style={{ color: C.cold }}>냉정</span>
          <span style={{ color: C.neutral }}>보통</span>
          <span style={{ color: C.hot }}>과열</span>
          <span style={{ color: C.mania }}>광기</span>
        </div>
      </div>

      {/* Text */}
      <div style={{ flex: 1, minWidth: 280 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <span style={{ fontSize: 15, fontWeight: 800, color: C.blue }}>
            Hatzze Overheating Index
          </span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: `${stage.color}24`,
              color: stage.color,
              fontWeight: 800,
              fontSize: 16,
              padding: "5px 14px",
              borderRadius: 999,
              whiteSpace: "nowrap",
            }}
          >
            {stage.emoji} {dailyScore.stage}
          </span>
        </div>
        <p style={{ margin: "0 0 4px", fontSize: 11, color: C.sub, fontFamily: MONO }}>
          최종 업데이트 · {formatKstDateTime(dailyScore.updated_at)}
        </p>
        <div
          style={{
            marginTop: 20,
            background: C.bg,
            borderRadius: 16,
            padding: "22px 24px",
            display: "flex",
            gap: 14,
          }}
        >
          <Icon name="auto_awesome" style={{ color: C.blue, fontSize: 22 }} />
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#3a4453", fontWeight: 500 }}>
            오늘은 정통 지표 <b style={{ color: C.ink }}>{tradHits}개</b>, 소셜 지표{" "}
            <b style={{ color: C.ink }}>{socialHits}개</b>가 기준선을 넘었어요. 지표들이 가리키는
            현재 시장 온도는 <b style={{ color: stage.color }}>{dailyScore.stage}</b> 구간이에요.
          </p>
        </div>
      </div>
    </section>
  );
}

// ── 지표 카드 ─────────────────────────────────────────────────────
function IndicatorCard({ indicator }: { indicator: IndicatorWithLatestValue }) {
  const latest = indicator.latest;
  const hasValue = latest !== null;
  const rawScore = latest?.normalized_score ?? null;
  const capped = rawScore !== null ? Math.min(Math.max(rawScore, 0), 100) : null;
  const isHit = (rawScore ?? 0) >= 100;
  const color = heatColor(rawScore);

  const { display, displayUnit } = hasValue
    ? formatIndicatorValue(latest!.raw_value, indicator.unit)
    : { display: "-", displayUnit: indicator.unit };

  const threshold = latest?.threshold ?? null;
  const thresholdDisplay =
    threshold !== null ? formatIndicatorValue(threshold, indicator.unit) : null;
  const directionLabel = indicator.direction === "low" ? "이하" : "이상";

  const icon = ICONS[indicator.slug] ?? "insights";
  const period = PERIODS[indicator.slug];

  // HIT 카드는 붉은 테두리 + 그림자로 강조하고 2열을 차지해 눈에 띄게 한다.
  const cardStyle: React.CSSProperties = {
    background: C.card,
    borderRadius: 20,
    padding: 28,
    display: "flex",
    flexDirection: "column",
    position: "relative",
    minHeight: 236,
    boxShadow: isHit
      ? "0 8px 24px -12px rgba(255,107,129,0.35)"
      : "0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.08)",
    border: isHit ? "2px solid rgba(255,107,129,0.18)" : "2px solid transparent",
  };

  return (
    <div className={isHit ? "hz-span2" : undefined} style={cardStyle}>
      {isHit && (
        <span
          style={{
            position: "absolute",
            top: 22,
            right: 22,
            background: C.mania,
            color: "#fff",
            fontWeight: 800,
            fontSize: 11,
            padding: "6px 12px",
            borderRadius: 8,
          }}
        >
          🎯 HIT
        </span>
      )}

      {/* 캐치프레이즈(headline) */}
      {indicator.headline && (
        <p
          style={{
            margin: "0 0 14px",
            fontSize: 12,
            fontWeight: 800,
            fontStyle: "italic",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            color,
            paddingRight: isHit ? 64 : 0,
          }}
        >
          &ldquo;{indicator.headline}&rdquo;
        </p>
      )}

      {/* 아이콘 + 이름 + 기간 배지 */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <Icon name={icon} style={{ fontSize: 28, color }} />
        <h3
          style={{
            margin: 0,
            fontSize: 17,
            fontWeight: 800,
            color: C.ink,
            lineHeight: 1.2,
            wordBreak: "keep-all",
          }}
        >
          {indicator.name}
        </h3>
        {period && (
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
            {period}
          </span>
        )}
      </div>

      {/* 값 */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, marginBottom: 20 }}>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 44,
            fontWeight: 800,
            color,
            lineHeight: 1,
            letterSpacing: "-0.04em",
          }}
        >
          {display}
          {displayUnit && <span style={{ fontSize: 22 }}>{displayUnit}</span>}
        </span>
      </div>

      {/* 과열도 바 */}
      {capped !== null && (
        <div
          style={{
            background: C.bg,
            borderRadius: 14,
            padding: "16px 18px",
            marginBottom: 4,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 11,
              fontWeight: 800,
              marginBottom: 8,
            }}
          >
            <span style={{ color: C.sub }}>과열도</span>
            <span style={{ color, fontFamily: MONO }}>
              {Math.round(capped)}
              <span style={{ color: "#a9b0bd" }}>/100</span>
            </span>
          </div>
          <div style={{ position: "relative", height: 10, background: C.track, borderRadius: 999, overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${capped}%`,
                background: isHit
                  ? `linear-gradient(90deg, ${C.hot}, ${C.mania})`
                  : color,
                borderRadius: 999,
              }}
            />
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 9,
              fontWeight: 700,
              color: C.sub,
              marginTop: 7,
            }}
          >
            <span>안심</span>
            <span style={{ color: C.hot }}>과열 100</span>
          </div>
          {thresholdDisplay && (
            <p
              style={{
                margin: "8px 0 0",
                textAlign: "center",
                fontSize: 10,
                fontWeight: 700,
                color: C.sub,
                fontFamily: MONO,
              }}
            >
              기준선 {thresholdDisplay.display}
              {thresholdDisplay.displayUnit} {directionLabel}
            </p>
          )}
        </div>
      )}

      {/* 설명 */}
      <p
        style={{
          margin: "auto 0 0",
          paddingTop: 18,
          fontSize: 13,
          color: C.sub,
          fontWeight: 500,
          borderTop: "1px solid rgba(0,0,0,0.05)",
          marginTop: 18,
          lineHeight: 1.5,
        }}
      >
        {indicator.description_beginner}
      </p>
    </div>
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
    <aside
      className="hz-sidebar"
      style={{
        width: 248,
        flexShrink: 0,
        background: C.card,
        borderRight: `1px solid ${C.line}`,
        padding: "32px 0",
      }}
    >
      <div style={{ padding: "0 32px", marginBottom: 48 }}>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 800, color: C.blue, letterSpacing: "-0.04em" }}>
          HATZZE
        </h1>
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 10,
            fontWeight: 700,
            color: C.sub,
            textTransform: "uppercase",
            letterSpacing: "0.2em",
          }}
        >
          시장 과열도 분석
        </p>
      </div>
      <nav style={{ flex: 1, padding: "0 16px", display: "flex", flexDirection: "column", gap: 8 }}>
        {NAV.map((item) => (
          <span
            key={item.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "16px 20px",
              color: item.active ? C.blue : C.sub,
              fontWeight: item.active ? 700 : 600,
              background: item.active ? "rgba(0,100,255,0.08)" : "transparent",
              borderRadius: 14,
            }}
          >
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
    <header
      style={{
        height: 64,
        flexShrink: 0,
        background: C.card,
        borderBottom: `1px solid ${C.line}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 32px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: MONO, overflow: "hidden" }}>
        {dailyScore ? (
          <>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>햇쩨 지수</span>
            <span style={{ fontSize: 13, fontWeight: 800, color: stage?.color ?? C.ink }}>
              {formatIndicatorValue(dailyScore.score, "%").display}% · {dailyScore.stage}
            </span>
            <span
              className="hz-topbar-date"
              style={{ fontSize: 11, fontWeight: 600, color: C.sub, whiteSpace: "nowrap" }}
            >
              {formatKstDateTime(dailyScore.updated_at)}
            </span>
          </>
        ) : (
          <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>데이터 대기 중</span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ position: "relative" }}>
          <Icon
            name="search"
            style={{
              position: "absolute",
              left: 12,
              top: "50%",
              transform: "translateY(-50%)",
              color: C.sub,
              fontSize: 20,
            }}
          />
          <input
            placeholder="지표 검색..."
            style={{
              background: C.bg,
              border: "none",
              borderRadius: 12,
              padding: "9px 16px 9px 40px",
              fontSize: 12,
              width: 240,
              maxWidth: "40vw",
              color: C.ink,
              outline: "none",
              fontFamily: "inherit",
            }}
          />
        </div>
      </div>
    </header>
  );
}

// ── 페이지 ────────────────────────────────────────────────────────
export default async function Home() {
  const [dailyScore, indicators] = await Promise.all([
    getLatestDailyScore(),
    getPublicIndicators(),
  ]);

  const traditional = indicators.filter((i) => i.category === "정통");
  const meme = indicators.filter((i) => i.category === "밈");
  const countHits = (list: IndicatorWithLatestValue[]) =>
    list.filter((i) => (i.latest?.normalized_score ?? 0) >= 100).length;

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
          <div
            style={{
              maxWidth: 1180,
              margin: "0 auto",
              display: "flex",
              flexDirection: "column",
              gap: 56,
            }}
          >
            {dailyScore ? (
              <Hero
                dailyScore={dailyScore}
                tradHits={countHits(traditional)}
                socialHits={countHits(meme)}
              />
            ) : (
              <section
                style={{
                  background: C.card,
                  borderRadius: 24,
                  padding: 44,
                  textAlign: "center",
                  color: C.sub,
                }}
              >
                아직 계산된 스코어가 없습니다.
              </section>
            )}

            <section>
              <SectionHeading title="정통 지표" />
              <div className="hz-grid">
                {traditional.map((indicator) => (
                  <IndicatorCard key={indicator.id} indicator={indicator} />
                ))}
              </div>
            </section>

            <section>
              <SectionHeading title="소셜 지표" />
              <div className="hz-grid">
                {meme.map((indicator) => (
                  <IndicatorCard key={indicator.id} indicator={indicator} />
                ))}
                <a
                  href="#"
                  style={{
                    border: `2px dashed ${C.line}`,
                    borderRadius: 20,
                    padding: 24,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 10,
                    minHeight: 236,
                    color: C.sub,
                    textAlign: "center",
                  }}
                >
                  <Icon name="add_circle" style={{ fontSize: 34 }} />
                  <span style={{ fontSize: 14, fontWeight: 700 }}>새로운 지표 제보하기</span>
                  <span style={{ fontSize: 11, fontWeight: 500, color: "#8a919e" }}>
                    아이디어가 있다면 알려주세요
                  </span>
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
