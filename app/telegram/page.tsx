import type { Metadata } from "next";

import {
  getChannelRanking,
  getRisingChannels,
  getStockReport,
  getSurgingStocks,
  getTelegramSummary,
  getThemeRotation,
  getTopStocksWithTrend,
  getTrendingMessages,
} from "@/lib/telegram-data";

import { formatKstUpdate } from "@/lib/format";

import { C, Icon, MONO } from "../ui";
import { ExpandableList } from "./ExpandableList";

export const metadata: Metadata = {
  title: "카더라 리포트 | hatzze",
  description: "한국 주식 텔레그램 채널에서 가장 많이 언급되는 종목과 화제의 메시지를 분석합니다.",
};

export const dynamic = "force-dynamic";

// 생태계 센티먼트·이슈 키워드·종목 흐름 요약은 아직 LLM 분석이 없어 데모 데이터다.
// TODO(LLM 파이프라인 구축 시 실데이터로 교체).
// 이슈 키워드 — 종목명이 아닌 화제어. LLM 추출 예정(현재 데모).
const KEYWORDS_DEMO = [
  { word: "HBM", count: 128, up: true },
  { word: "관세", count: 96, up: true },
  { word: "실적발표", count: 84, up: false },
  { word: "금리인하", count: 72, up: true },
  { word: "수주", count: 61, up: true },
  { word: "공매도", count: 45, up: false },
  { word: "환율", count: 38, up: true },
  { word: "밸류업", count: 31, up: false },
  { word: "外人수급", count: 27, up: true },
  { word: "공모주", count: 22, up: false },
];

// 종목별 흐름 요약 — LLM(Claude Haiku)으로 최근 7일 언급을 요약할 자리.
// 카드 높이가 종목마다 들쭉날쭉하지 않도록 길이를 75~80자로 맞춘다
// (반칸 카드 폭에서 3줄로 떨어지는 구간. 83자를 넘기면 4줄이 돼 높이가 어긋난다).
// 실제 LLM을 붙일 때도 프롬프트에 같은 글자수 제약을 넣을 것.
// TODO(파이프라인 스텝 구축 시 DB에서 조회로 교체). 현재는 데모 문구.
const STOCK_NARRATIVE_DEMO: Record<string, string> = {
  "000660":
    "HBM 수급과 실적 기대가 주중 내내 반복적으로 언급되며 최상위 화제를 지켰지만, 주말로 갈수록 언급이 눈에 띄게 식는 흐름이 나타났어요.",
  "005930":
    "미국 ADR 상장 검토 소식이 여러 채널로 확산되며 언급이 크게 튀었고, 파운드리 회복 기대가 뒤따라 붙으면서 관심이 주 후반까지 이어졌어요.",
  "034730":
    "지주사 밸류업과 자회사 지분 이슈가 반복해서 등장했지만, 언급량 자체는 대형주 대비 크지 않아 화제의 중심에서는 한 발 비켜서 있었어요.",
};

const SENTIMENT_DEMO = {
  score: 62,
  label: "낙관 우세",
  // 시장 브리핑 히어로처럼 LLM이 쓰는 오늘의 총평(현재 데모).
  summary:
    "반도체·방산에 대한 기대가 이번 주 내내 대화를 주도하면서 전반적인 톤은 낙관 쪽에 기울어 있어요. 다만 조선·원전은 언급이 줄고 비관 비중이 늘어, 관심이 특정 테마로 쏠리는 모습이에요.",
  positive: 62,
  neutral: 23,
  negative: 15,
  byTheme: [
    { name: "반도체", pos: 74 },
    { name: "방산", pos: 66 },
    { name: "조선", pos: 45 },
    { name: "원전", pos: 31 },
  ],
};

function compact(n: number): string {
  if (n >= 10000) return `${Math.round(n / 1000)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return `${n}`;
}

function formatKR(n: number): string {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1).replace(/\.0$/, "")}억`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1).replace(/\.0$/, "")}만`;
  return n.toLocaleString("ko-KR");
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 60) return `${Math.max(1, min)}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  return `${Math.floor(hr / 24)}일 전`;
}

function Sparkline({ data, height = 20, width = 3 }: { data: number[]; height?: number; width?: number }) {
  const max = Math.max(1, ...data);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height }}>
      {data.map((v, i) => (
        <div key={i} style={{ width, height: `${Math.max(2, (v / max) * height)}px`, background: C.blue, opacity: 0.7, borderRadius: 2 }} />
      ))}
    </div>
  );
}

/** 채널 프로필 사진. 없으면 첫 글자 이니셜 아바타로 폴백. */
function Avatar({ photo, title, size = 30 }: { photo: string | null; title: string; size?: number }) {
  const common: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: "50%",
    flexShrink: 0,
    objectFit: "cover",
    border: `1px solid ${C.line}`,
  };
  if (photo) return <img src={photo} alt="" style={common} />;
  return (
    <span
      style={{
        ...common,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: C.track,
        color: C.sub,
        fontSize: size * 0.42,
        fontWeight: 800,
      }}
    >
      {title.trim().charAt(0)}
    </span>
  );
}

function SectionHead({
  icon,
  title,
  note,
  desc,
  noteHelp,
}: {
  icon: string;
  title: string;
  note?: string;
  desc?: string;
  noteHelp?: string;
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name={icon} style={{ fontSize: 22, color: C.blue }} />
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: C.ink }}>{title}</h3>
        {note && (
          <span style={{ fontSize: 11, fontWeight: 700, color: C.sub, marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 4 }}>
            {note}
            {noteHelp && (
              <span className="hz-tip hz-tip-wide" data-tip={noteHelp} style={{ display: "inline-flex", cursor: "help" }}>
                <Icon name="help" style={{ fontSize: 14, color: C.sub }} />
              </span>
            )}
          </span>
        )}
      </div>
      {desc && <p style={{ margin: "7px 0 0", fontSize: 12, lineHeight: 1.5, color: C.sub }}>{desc}</p>}
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: C.card,
  borderRadius: 16,
  padding: 24,
  border: `1px solid ${C.line}`,
};

const subCard: React.CSSProperties = {
  background: C.bg,
  borderRadius: 12,
  border: `1px solid ${C.line}`,
};

const rankNum: React.CSSProperties = {
  width: 18,
  textAlign: "right",
  fontFamily: MONO,
  fontWeight: 800,
  fontSize: 14,
  flexShrink: 0,
};

const badge = (bg: string, color: string): React.CSSProperties => ({
  fontSize: 11,
  fontWeight: 800,
  color,
  background: bg,
  padding: "3px 9px",
  borderRadius: 999,
  whiteSpace: "nowrap",
});

const span = (n: number): React.CSSProperties => ({ gridColumn: `span ${n}` });

export default async function TelegramPage() {
  const topStocks = await getTopStocksWithTrend(3);
  const [summary, surging, trending, channels, rising, themes, reports] = await Promise.all([
    getTelegramSummary(),
    getSurgingStocks(5),
    getTrendingMessages(7, 6),
    getChannelRanking(),
    getRisingChannels(10),
    getThemeRotation(10),
    Promise.all(topStocks.map((s) => getStockReport(s.code))),
  ]);
  const stockReports = reports.filter((r): r is NonNullable<typeof r> => r !== null);

  const channelItems = channels.map((c, i) => (
    <li key={c.handle}>
      <a href={`https://t.me/${c.handle}`} target="_blank" rel="noopener noreferrer" className="hz-row-link">
      <span style={{ ...rankNum, color: i < 3 ? C.blue : C.sub }}>{i + 1}</span>
      <Avatar photo={c.photo} title={c.title} />
      <div style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {c.title}
            {c.rankChange !== null && c.rankChange !== 0 && (
              <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 800, color: c.rankChange > 0 ? C.hot : C.cold }}>
                {c.rankChange > 0 ? "▲" : "▼"}
                {Math.abs(c.rankChange)}계단
              </span>
            )}
            {c.isGrowing && <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 800, color: C.hot }}>성장중</span>}
          </div>
          <div style={{ fontSize: 11, fontFamily: MONO, color: C.sub }}>
            구독자 수 {c.subscriberCount ? compact(c.subscriberCount) : "-"}
            {c.viewRate != null && ` · 조회율 ${c.viewRate.toFixed(1)}%`}
          </div>
        </div>
        <span style={{ fontFamily: MONO, fontWeight: 800, fontSize: 18, color: C.blue }}>{c.influenceScore.toFixed(0)}</span>
      </div>
      </a>
    </li>
  ));

  const miniStats = [
    { label: "모니터링 채널", value: `${summary.channelCount}개` },
    { label: "총 구독자", value: formatKR(summary.totalSubscribers) },
    { label: "활성 채널 (7일)", value: `${summary.activeChannels}개` },
    { label: "총 메시지 (7일)", value: `${summary.messages7d.toLocaleString("ko-KR")}개` },
  ];

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* 헤더 */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: C.ink }}>카더라 리포트</h2>
        <span style={{ fontSize: 11, fontWeight: 800, color: C.blue, background: "var(--c-blue-tint)", padding: "4px 12px", borderRadius: 999 }}>
          베타
        </span>
        <div style={{ height: 1, flex: 1, background: C.line }} />
      </div>
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, color: C.sub }}>
        한국 주식 텔레그램 채널들이 <b style={{ color: C.ink }}>지금 무엇에 주목하는지</b>를 모아 보여줘요.
        조회·확산·언급량을 종합한 <b style={{ color: C.ink }}>화제성</b> 지표이며, 매수·매도 신호가 아니에요.
      </p>

      <div className="hz-grid">
        {/* 모니터링 현황 (1칸) */}
        <div style={{ ...cardStyle, display: "flex", flexDirection: "column" }}>
          <SectionHead icon="monitoring" title="모니터링 현황" desc="추적 중인 텔레그램 채널 규모" />
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            {miniStats.map((s) => (
              <div key={s.label} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 12, color: C.sub, fontWeight: 600 }}>{s.label}</span>
                <span style={{ fontSize: 18, fontWeight: 800, color: C.ink }}>{s.value}</span>
              </div>
            ))}
          </div>
          {/* TODO: 구글폼 URL 연결 */}
          <a
            href="#"
            style={{
              marginTop: "auto",
              paddingTop: 16,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              fontSize: 12,
              fontWeight: 700,
              color: C.blue,
            }}
          >
            <Icon name="add_circle" style={{ fontSize: 16 }} />
            채널 등록 신청
          </a>
        </div>

        {/* 생태계 센티먼트 (3칸) — LLM 분석 (데모) */}
        <div style={{ ...cardStyle, ...span(3) }}>
          <SectionHead
            icon="psychology"
            title="텔레그램 생태계 센티먼트"
            note="최근 7일 · LLM 분석"
            desc="메시지 톤으로 본 시장 분위기"
          />
          {summary.lastUpdated && (
            <p style={{ margin: "-8px 0 14px", fontSize: 11, color: C.sub, fontFamily: MONO }}>
              최종 업데이트 · {formatKstUpdate(summary.lastUpdated)}
            </p>
          )}
          <p
            style={{
              margin: "0 0 18px",
              fontSize: 13,
              lineHeight: 1.7,
              color: "var(--c-ink-soft)",
              background: C.bg,
              border: `1px solid ${C.line}`,
              borderRadius: 12,
              padding: "13px 15px",
            }}
          >
            <Icon name="auto_awesome" style={{ fontSize: 15, color: C.blue, marginRight: 6, verticalAlign: "-3px" }} />
            {SENTIMENT_DEMO.summary}
          </p>
          <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "center" }}>
            {/* 메시지 톤 종합 — 점수와 그 근거 막대를 한 덩어리로 묶는다 */}
            <div style={{ flex: "1 1 300px", minWidth: 280 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{ fontSize: 40, fontWeight: 800, color: C.hot, lineHeight: 1 }}>{SENTIMENT_DEMO.score}%</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{SENTIMENT_DEMO.label}</span>
              </div>
              <div style={{ fontSize: 11, color: C.sub, margin: "6px 0 10px" }}>메시지 톤 종합</div>
              <div style={{ display: "flex", height: 14, borderRadius: 999, overflow: "hidden" }}>
                <div style={{ width: `${SENTIMENT_DEMO.positive}%`, background: C.hot }} />
                <div style={{ width: `${SENTIMENT_DEMO.neutral}%`, background: C.track }} />
                <div style={{ width: `${SENTIMENT_DEMO.negative}%`, background: C.cold }} />
              </div>
              <div style={{ display: "flex", gap: 14, marginTop: 9, fontSize: 11, color: C.sub, flexWrap: "wrap" }}>
                <span><b style={{ color: C.hot }}>■</b> 긍정 {SENTIMENT_DEMO.positive}%</span>
                <span><b style={{ color: C.sub }}>■</b> 중립 {SENTIMENT_DEMO.neutral}%</span>
                <span><b style={{ color: C.cold }}>■</b> 비관 {SENTIMENT_DEMO.negative}%</span>
              </div>
            </div>

            <div style={{ flex: "1 1 250px", minWidth: 235, display: "flex", flexDirection: "column", gap: 9 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.sub, display: "flex", justifyContent: "space-between" }}>
                <span>인기 테마별 낙관 ↔ 비관</span>
              </div>
              {SENTIMENT_DEMO.byTheme.map((t) => (
                <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 46, fontSize: 11, fontWeight: 700, color: C.ink, flexShrink: 0 }}>{t.name}</span>
                  {/* 낙관(왼쪽)과 비관(오른쪽)을 한 바에 나눠 담아 비율이 바로 보이게 */}
                  <div style={{ flex: 1, display: "flex", height: 8, borderRadius: 999, overflow: "hidden" }}>
                    <div style={{ width: `${t.pos}%`, background: C.hot }} />
                    <div style={{ width: `${100 - t.pos}%`, background: C.cold }} />
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.sub, width: 62, textAlign: "right", whiteSpace: "nowrap" }}>
                    <b style={{ color: C.hot }}>{t.pos}</b>:<b style={{ color: C.cold }}>{100 - t.pos}</b>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ② 급부상 종목 (전체폭) */}
        <div style={{ ...cardStyle, ...span(4) }}>
          <SectionHead
            icon="local_fire_department"
            title="급부상 종목"
            note="최근 3일 vs 평소"
            desc="평소보다 언급이 갑자기 뛴 종목"
          />
          {surging.length === 0 ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 급부상 신호가 뚜렷한 종목이 없어요. 데이터가 쌓일수록 또렷해져요.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 12 }}>
              {/* auto-fill: 종목 수가 적어도 타일이 전체폭으로 늘어나지 않게 */}
              {surging.map((s) => (
                <div key={s.code} style={{ ...subCard, padding: "15px 16px", minWidth: 0 }}>
                  {/* 1) 종목 — 이름 + 코드 */}
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, minWidth: 0 }}>
                    <span style={{ fontWeight: 800, fontSize: 15, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {s.name}
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: C.sub, flexShrink: 0 }}>{s.code}</span>
                  </div>

                  {/* 2) 시세 — 가격 + 등락률 */}
                  <div style={{ marginTop: 9, display: "flex", alignItems: "baseline", gap: 7, flexWrap: "wrap" }}>
                    {s.closePrice != null ? (
                      <>
                        <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 800, color: C.ink }}>
                          {s.closePrice.toLocaleString("ko-KR")}원
                        </span>
                        {s.changeRate != null && (
                          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: s.changeRate >= 0 ? C.hot : C.cold }}>
                            {s.changeRate >= 0 ? "▲" : "▼"}
                            {Math.abs(s.changeRate).toFixed(2)}%
                          </span>
                        )}
                      </>
                    ) : (
                      <span style={{ fontSize: 12, color: C.sub }}>가격 정보 준비 중</span>
                    )}
                  </div>

                  {/* 3) 텔레그램 화제도 — 급등 배지 + 언급/채널 */}
                  <div style={{ marginTop: 12, paddingTop: 11, borderTop: `1px solid ${C.line}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                      <span style={{ ...badge(s.isNew ? "var(--c-blue-tint)" : `${C.hot}22`, s.isNew ? C.blue : C.hot), marginLeft: -9 }}>
                        {s.isNew ? "🆕 신규 등장" : `언급 ▲ ${s.ratio.toFixed(1)}배`}
                      </span>
                    </div>
                    <div style={{ marginTop: 7, fontSize: 11, fontFamily: MONO, color: C.sub }}>
                      최근 {s.recentMentions}회 언급 · {s.channelCount}개 채널
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ⑥ 트렌딩 메시지 (전체폭) — 종목/주제 태그 포함 */}
        <div style={{ ...cardStyle, ...span(4) }}>
          <SectionHead
            icon="campaign"
            title="트렌딩 메시지"
            note="최근 7일"
            desc="조회·공유로 가장 널리 퍼진 메시지"
          />
          {trending.length === 0 ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 화제 메시지가 없어요.</p>
          ) : (
            // 3열 그리드 — 한 줄에 3개씩. 카드가 좁아지는 대신 세로로 길어져
            // 실제 텔레그램 메시지처럼 읽힌다.
            <ol
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
                gap: 12,
              }}
            >
              {trending.map((m, i) => (
                <li key={`${m.channelHandle}-${m.messageId}`} style={{ display: "flex" }}>
                  {/* 원문 메시지로 이동 — 텔레그램 공개 채널은 t.me/핸들/메시지ID 로 열린다 */}
                  <a
                    href={`https://t.me/${m.channelHandle}/${m.messageId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hz-lift"
                    style={{
                      ...subCard,
                      padding: "13px 15px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 9,
                      textDecoration: "none",
                      width: "100%",
                      minHeight: 168,
                    }}
                  >
                    {/* 보낸 채널 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                      <span style={{ ...rankNum, width: 14, fontSize: 12, color: i < 3 ? C.hot : C.sub }}>{i + 1}</span>
                      <Avatar photo={m.channelPhoto} title={m.channelTitle} size={22} />
                      <b
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: C.blue,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {m.channelTitle}
                      </b>
                      <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: MONO, color: C.sub, whiteSpace: "nowrap" }}>
                        {timeAgo(m.postedAt)}
                      </span>
                    </div>

                    {/* 본문 */}
                    <p
                      style={{
                        margin: 0,
                        flex: 1,
                        fontSize: 13,
                        lineHeight: 1.6,
                        color: C.ink,
                        display: "-webkit-box",
                        WebkitLineClamp: 5,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {m.text}
                    </p>

                    {/* 지표 + 종목/주제 태그(공유 수 오른쪽) */}
                    <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap", fontSize: 11, fontFamily: MONO, color: C.sub }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                        <Icon name="visibility" style={{ fontSize: 13 }} /> {compact(m.views)}
                      </span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                        <Icon name="shortcut" style={{ fontSize: 13 }} /> {compact(m.forwards)}
                      </span>
                      {m.replies > 0 && (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                          <Icon name="chat_bubble" style={{ fontSize: 12 }} /> {m.replies}
                        </span>
                      )}
                      {m.stocks.map((st) => (
                        <span key={st} style={badge("var(--c-blue-tint)", C.blue)}>{st}</span>
                      ))}
                      {m.topics.map((t) => (
                        <span key={t} style={badge(C.track, C.sub)}>#{t}</span>
                      ))}
                    </div>
                  </a>
                </li>
              ))}
            </ol>
          )}
        </div>

        {/* ④ 테마 로테이션 (½) */}
        <div style={{ ...cardStyle, ...span(2) }}>
          <SectionHead
            icon="donut_small"
            title="테마 로테이션"
            note="최근 7일 · 점유율/순위"
            desc="관심이 어느 테마로 옮겨가는지"
          />
          {themes.length === 0 ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 집계된 테마가 없어요.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {themes.map((t) => (
                <div key={t.theme} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ ...rankNum, color: C.sub }}>{t.rank}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 7, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 800, fontSize: 14, color: C.ink }}>{t.theme}</span>
                      {t.rankChange !== null && t.rankChange !== 0 && (
                        <span style={{ fontSize: 10, fontWeight: 800, color: t.rankChange > 0 ? C.hot : C.cold }}>
                          {t.rankChange > 0 ? "▲" : "▼"}
                          {Math.abs(t.rankChange)}계단
                        </span>
                      )}
                      {t.shareDelta !== null && Math.abs(t.shareDelta) >= 0.1 && (
                        <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 12, fontWeight: 700, color: t.shareDelta >= 0 ? C.hot : C.cold }}>
                          {t.shareDelta >= 0 ? "▲" : "▼"}
                          {Math.abs(t.shareDelta).toFixed(1)}%p
                        </span>
                      )}
                    </div>
                    <div style={{ margin: "6px 0 5px", height: 8, background: C.track, borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ width: `${Math.min(100, t.sharePct * 2.6)}%`, height: "100%", background: C.blue, borderRadius: 999 }} />
                    </div>
                    <div style={{ fontSize: 11, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      점유율 <b style={{ color: C.ink, fontFamily: MONO }}>{t.sharePct.toFixed(1)}%</b> · 종목 {t.stockCount}개 ·{" "}
                      <span style={{ fontFamily: MONO }}>{t.mentions}회</span>
                    </div>
                  </div>
                  <Sparkline data={t.series} height={26} width={4} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ⑤ 주요 종목 리포트 (½) — 3종목 상세 */}
        <div style={{ ...cardStyle, ...span(2) }}>
          <SectionHead
            icon="query_stats"
            title="주요 종목 리포트"
            note="최근 7일 · 상위 3종목"
            desc="가장 많이 회자된 종목의 추이와 흐름"
          />
          {stockReports.length === 0 ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 리포트를 만들 종목이 없어요.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {stockReports.map((r) => {
                const max = Math.max(1, ...r.series.map((s) => s.mentions));
                return (
                  <div key={r.code} style={{ ...subCard, padding: 16, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                      <span style={{ fontSize: 18, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11, color: C.sub }}>{r.code}</span>
                      {r.price != null && (
                        <span style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: 5, whiteSpace: "nowrap" }}>
                          <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 800, color: C.ink }}>
                            {r.price.toLocaleString("ko-KR")}원
                          </span>
                          {r.changeRate != null && (
                            <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: r.changeRate >= 0 ? C.hot : C.cold }}>
                              {r.changeRate >= 0 ? "▲" : "▼"}
                              {Math.abs(r.changeRate).toFixed(2)}%
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 48, margin: "14px 0 10px" }}>
                      {r.series.map((d) => (
                        <div key={d.date} className="hz-tip" data-tip={`${d.date.slice(5)} · ${d.mentions}회`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                          <div style={{ width: "100%", height: `${Math.max(4, (d.mentions / max) * 36)}px`, background: C.blue, borderRadius: 3, opacity: 0.85 }} />
                          <span style={{ fontSize: 8, fontFamily: MONO, color: C.sub }}>{d.date.slice(5)}</span>
                        </div>
                      ))}
                    </div>
                    {STOCK_NARRATIVE_DEMO[r.code] && (
                      <p
                        style={{
                          margin: "0 0 12px",
                          fontSize: 12,
                          lineHeight: 1.6,
                          color: "var(--c-ink-soft)",
                          background: C.track,
                          borderRadius: 10,
                          padding: "10px 12px",
                        }}
                      >
                        <Icon name="auto_awesome" style={{ fontSize: 13, color: C.blue, marginRight: 5, verticalAlign: "-2px" }} />
                        {STOCK_NARRATIVE_DEMO[r.code]}
                      </p>
                    )}
                    <div style={{ display: "flex", gap: 12, fontSize: 11, fontFamily: MONO, color: C.sub, marginBottom: 12 }}>
                      <span>언급 {r.totalMentions}회</span>
                      <span>·</span>
                      <span>{r.channelCount}개 채널</span>
                    </div>

                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ③ 채널 파워 랭킹 (½) */}
        <div style={{ ...cardStyle, ...span(2) }}>
          <SectionHead
            icon="military_tech"
            title="채널 파워 랭킹"
            note="영향력 점수"
            desc="조회율·확산력까지 반영한 채널 영향력"
            noteHelp="조회율(평균 조회수÷구독자 수), 포워드율, 구독자 규모, 주간 게시물 수를 각각 구간 점수로 환산해 합산한 뒤 52~100 범위로 보정한 점수예요. 구독자만 많고 실제로 안 읽히는 채널은 점수가 낮게 나와요."
          />
          {channels.length === 0 ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 채널 점수가 없어요.</p>
          ) : (
            <ExpandableList items={channelItems} initial={10} step={10} />
          )}
        </div>

        {/* ① 뜨는 채널 (¼) */}
        <div style={cardStyle}>
          <SectionHead icon="rocket_launch" title="뜨는 채널" note="7일" desc="최근 구독자가 많이 늘어난 채널" />
          {/* 간격을 이슈 키워드 카드의 행 높이(pitch 53px)에 맞춰 두 카드의 순위가 나란히 보이게 한다 */}
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 18 }}>
            {rising.map((r, i) => {
              const body = (
                <>
                  <span style={{ ...rankNum, color: C.sub }}>{i + 1}</span>
                  <Avatar photo={r.photo} title={r.title} size={26} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.title}</div>
                    <div style={{ fontSize: 10, fontFamily: MONO, color: C.sub }}>구독자 수 {compact(r.subscriberCount)}</div>
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: C.hot, whiteSpace: "nowrap" }}>
                    ▲{r.delta7d.toLocaleString("ko-KR")}명
                  </span>
                </>
              );
              // 실제 채널일 때만 링크로 감싼다 — 데모 채널은 연결할 대상이 없다.
              return (
                <li key={r.title}>
                  {r.handle ? (
                    <a href={`https://t.me/${r.handle}`} target="_blank" rel="noopener noreferrer" className="hz-row-link">
                      {body}
                    </a>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>{body}</div>
                  )}
                </li>
              );
            })}
          </ol>
        </div>

        {/* 이슈 키워드 (¼) — 종목이 아닌 화제어 (LLM 추출 예정, 현재 데모) */}
        <div style={cardStyle}>
          <SectionHead icon="tag" title="이슈 키워드" note="7일" desc="종목명이 아닌 화제어" />
          <div style={{ display: "flex", flexDirection: "column", gap: 23 }}>
            {KEYWORDS_DEMO.map((k, i) => {
              const max = KEYWORDS_DEMO[0].count;
              return (
                <div key={k.word} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <span style={{ ...rankNum, color: C.sub }}>{i + 1}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 6 }}>
                      <span style={{ fontWeight: 700, fontSize: 13, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{k.word}</span>
                      <span style={{ fontFamily: MONO, fontSize: 11, color: k.up ? C.hot : C.cold, flexShrink: 0 }}>
                        {k.up ? "▲" : "▼"} {k.count}회
                      </span>
                    </div>
                    <div style={{ marginTop: 5, height: 5, background: C.track, borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ width: `${(k.count / max) * 100}%`, height: "100%", background: C.blue, borderRadius: 999, opacity: 0.8 }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
