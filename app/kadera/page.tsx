import type { Metadata } from "next";

import {
  getChannelRanking,
  getEcosystemSentiment,
  getIssueKeywords,
  getRisingChannels,
  getStockNarratives,
  getStockReport,
  getSurgingStocks,
  getTelegramSummary,
  getThemeRotation,
  getTopStocksWithTrend,
  getTrendingMessages,
} from "@/lib/telegram-data";
import type { TrendingMessage } from "@/lib/telegram-data";

import { formatKstUpdate } from "@/lib/format";

import { C, Icon, MONO } from "../ui";
import { ExpandableList } from "./ExpandableList";
import { SectionHead } from "./SectionHead";
import { TrendingTabs } from "./TrendingTabs";

export const metadata: Metadata = {
  title: "카더라 리포트 | hatzze",
  description: "한국 주식 텔레그램 채널에서 가장 많이 언급되는 종목과 화제의 메시지를 분석합니다.",
  // 루트 레이아웃이 canonical "/" 를 선언해 하위 페이지가 그대로 물려받는다. 그대로 두면
  // 이 페이지가 홈의 중복이라고 선언하는 셈이라 검색엔진이 색인하지 않는다. 자기 주소로
  // 덮어써야 sitemap 에 올린 것이 실제 색인으로 이어진다.
  alternates: { canonical: "/kadera" },
};

export const dynamic = "force-dynamic";

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

const cardStyle: React.CSSProperties = {
  background: C.card,
  borderRadius: 16,
  padding: 24,
  border: `1px solid ${C.line}`,
  // 그리드 칸 안에서 카드가 내용에 밀려 넓어지지 않도록(칸 비율 고정). 긴 채널명 등은
  // 카드 안에서 말줄임 처리되어야지, 카드를 늘려선 안 된다.
  minWidth: 0,
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


/**
 * 트렌딩 메시지 목록(3열 그리드). 기간 탭이 세 벌을 미리 렌더해 넘기므로
 * 목록 마크업만 여기로 뽑아 재사용한다 — 조회는 서버에 그대로 남는다.
 */
function TrendingList({ items }: { items: TrendingMessage[] }) {
  const nodes = items.map((m, i) => (
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
        ));

  // 3열 그리드 — 한 줄에 3개씩. 카드가 좁아지는 대신 세로로 길어져 실제 텔레그램
  // 메시지처럼 읽힌다. 채널 파워 랭킹과 같은 더 보기(+10)를 붙인다.
  return (
    <ExpandableList
      items={nodes}
      initial={6}
      step={10}
      listStyle={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
        gap: 12,
      }}
    />
  );
}

export default async function KaderaPage() {
  const topStocks = await getTopStocksWithTrend(3);
  const [
    summary,
    surging,
    trendingToday,
    trending,
    trendingMonth,
    channels,
    rising,
    themes,
    reports,
    sentiment,
    keywords,
    narratives,
  ] =
    await Promise.all([
      getTelegramSummary(),
      getSurgingStocks(5),
      // 기간 탭이 즉시 전환되도록 세 창을 한 번에 받아둔다(병렬이라 지연은 한 번 분).
      // 6건만 보여주고 '더 보기'로 10건씩 늘리므로, 세 번 펼칠 만큼(36) 미리 받아둔다.
      getTrendingMessages("today", 36),
      getTrendingMessages(7, 36),
      getTrendingMessages(30, 36),
      getChannelRanking(),
      getRisingChannels(10),
      getThemeRotation(10),
      Promise.all(topStocks.map((s) => getStockReport(s.code))),
      getEcosystemSentiment(),
      getIssueKeywords(10),
      getStockNarratives(),
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
          <a
            href="https://forms.gle/PRapNH9rz8YuF2zu9"
            target="_blank"
            rel="noopener noreferrer"
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

        {/* 생태계 센티먼트 (3칸) — 메시지별 LLM 분류를 집계한 결과 */}
        <div className="hz-c3" style={cardStyle}>
          <SectionHead
            icon="psychology"
            title="텔레그램 생태계 센티먼트"
            note="최근 7일 · LLM 분석"
            desc="메시지 톤으로 본 시장 분위기"
            noteHelp="수집한 메시지를 한 건씩 비관/중립/낙관으로 분류한 뒤, 편을 든 것끼리만 견준 비율이에요. 사실을 담담히 전하는 시황·공시 요약은 중립으로 보고 빼는데, 이런 글이 원래 절반쯤 돼서 같이 세면 분위기가 아무리 좋아도 늘 비관 쪽으로 기울어 보이거든요. 테마별 막대도 같은 기준이에요."
          />
          {summary.lastUpdated && (
            <p style={{ margin: "-8px 0 14px", fontSize: 11, color: C.sub, fontFamily: MONO }}>
              최종 업데이트 · {formatKstUpdate(summary.lastUpdated)}
            </p>
          )}
          {!sentiment ? (
            <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 분석된 메시지가 없어요.</p>
          ) : (
            <>
              {sentiment.summary && (
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
                  {sentiment.summary}
                </p>
              )}
              <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "center" }}>
                {/* 메시지 톤 종합 — 점수와 그 근거 막대를 한 덩어리로 묶는다 */}
                <div style={{ flex: "1 1 300px", minWidth: 280 }}>
                  {/* 이 카드가 답하는 건 "지금 분위기 좋아, 나빠?" 하나다. 그래서 숫자도 한 벌만
                      쓴다 — 예전엔 헤드라인이 낙관도(중립 제외, 59%)이고 아래 막대는 중립 포함
                      구성(낙관 32%)이라, 한 카드에서 '낙관'이 두 숫자로 나와 어느 쪽이 진짜인지
                      알 수 없었다. 이제 비관:낙관 한 기준으로만 말하고, 막대는 그 비율을 그림으로
                      반복한다(숫자와 그림이 어긋날 수가 없다). 중립은 얼마나 뺐는지만 각주로. */}
                  <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontSize: 40, fontWeight: 800, lineHeight: 1 }}>
                      <span style={{ color: C.cold }}>{100 - sentiment.score}</span>
                      <span style={{ color: C.sub }}>:</span>
                      <span style={{ color: C.hot }}>{sentiment.score}</span>
                    </span>
                    {/* 유저가 실제로 가져가는 답은 이 라벨이다 — 색도 여기가 tone을 쓴다. */}
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: 800,
                        color: sentiment.tone === "hot" ? C.hot : sentiment.tone === "cold" ? C.cold : C.sub,
                      }}
                    >
                      {sentiment.label}
                    </span>
                  </div>
                  {/* 두 라벨을 막대의 양 끝에 붙여 어느 쪽이 어느 색인지 위치로 바로 읽히게 한다. */}
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, margin: "6px 0 6px" }}>
                    <span style={{ color: C.cold }}>비관</span>
                    <span style={{ color: C.hot }}>낙관</span>
                  </div>
                  <div style={{ display: "flex", height: 14, borderRadius: 999, overflow: "hidden" }}>
                    <div style={{ width: `${100 - sentiment.score}%`, background: C.cold }} />
                    <div style={{ width: `${sentiment.score}%`, background: C.hot }} />
                  </div>
                  <div style={{ marginTop: 9, fontSize: 11, color: C.sub }}>
                    총 <span style={{ fontFamily: MONO }}>{sentiment.messageCount.toLocaleString("ko-KR")}</span>건 중{" "}
                    <span style={{ fontFamily: MONO }}>{sentiment.neutral}</span>%는 중립이라 빼고 계산했어요
                  </div>
                </div>

                {sentiment.byTheme.length > 0 && (
                  <div style={{ flex: "1 1 250px", minWidth: 235, display: "flex", flexDirection: "column", gap: 9 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: C.sub, display: "flex", justifyContent: "space-between" }}>
                      {/* 중립을 뺀 기준이라는 설명은 왼쪽 종합 막대 각주에 이미 있다 —
                          같은 카드 안에서 두 번 말할 필요는 없다. */}
                      <span>인기 테마별 비관 ↔ 낙관</span>
                    </div>
                    {sentiment.byTheme.map((t) => (
                      <div
                        key={t.name}
                        className="hz-tip"
                        data-tip={`${t.name} 언급 ${t.total}건 중 비관 ${t.negative}건 · 낙관 ${t.positive}건 (중립 제외 비율)`}
                        style={{ display: "flex", alignItems: "center", gap: 8 }}
                      >
                        {/* 실제 테마명은 '지주·밸류업'·'인터넷·플랫폼'처럼 길어서
                            데모용 폭(46px)으론 줄바꿈이 나 행 높이가 어긋난다 */}
                        <span
                          style={{
                            width: 64,
                            fontSize: 11,
                            fontWeight: 700,
                            color: C.ink,
                            flexShrink: 0,
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {t.name}
                        </span>
                        {/* 비관(왼쪽)과 낙관(오른쪽)을 한 바에 나눠 담아 비율이 바로 보이게.
                            순서는 시장 브리핑 감성 카드와 맞춘 '비관 : 낙관'이다. */}
                        <div style={{ flex: 1, display: "flex", height: 8, borderRadius: 999, overflow: "hidden" }}>
                          <div style={{ width: `${100 - t.pos}%`, background: C.cold }} />
                          <div style={{ width: `${t.pos}%`, background: C.hot }} />
                        </div>
                        <span style={{ fontFamily: MONO, fontSize: 10, color: C.sub, width: 62, textAlign: "right", whiteSpace: "nowrap" }}>
                          <b style={{ color: C.cold }}>{100 - t.pos}</b>:<b style={{ color: C.hot }}>{t.pos}</b>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* ② 급부상 종목 (전체폭) */}
        <div className="hz-c4" style={cardStyle}>
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
        <div className="hz-c4" style={cardStyle}>
          {/* 머리(SectionHead)는 TrendingTabs 안에서 그린다 — 기간 탭이 머리 우측에
              들어가고 목록은 그 아래라, 둘을 한 컴포넌트가 감싸야 상태를 공유한다. */}
          <TrendingTabs
            icon="campaign"
            title="트렌딩 메시지"
            desc="조회·공유로 가장 널리 퍼진 메시지"
            panels={[
              { key: "today", label: "오늘", count: trendingToday.length, node: <TrendingList items={trendingToday} /> },
              { key: "w1", label: "최근 7일", count: trending.length, node: <TrendingList items={trending} /> },
              { key: "m1", label: "최근 30일", count: trendingMonth.length, node: <TrendingList items={trendingMonth} /> },
            ]}
          />
        </div>

        {/* ④ 테마 로테이션 (½) */}
        <div className="hz-c2" style={cardStyle}>
          <SectionHead
            icon="donut_small"
            title="테마 로테이션"
            note="최근 3일 vs 이전"
            desc="관심이 어느 테마로 옮겨가는지"
            noteHelp="최근 3일 평균 점유율을 5일 이상 이전 평균과 비교해요. 하루치끼리 비교하면 주말처럼 표본이 얇은 날에 점유율이 크게 요동쳐서, 며칠씩 묶어 안정적으로 봐요."
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
                      {/* 막대 길이 = 점유율 그대로. 예전엔 얇은 테마를 키우려 2.6배를 곱했는데
                          38.5%만 넘으면 전부 100%로 꽉 차 1위 테마가 늘 만땅으로 보였다.
                          0%가 아닌 테마는 최소 3px는 남겨 존재 자체는 보이게 한다. */}
                      <div
                        style={{
                          width: `${Math.min(100, t.sharePct)}%`,
                          minWidth: t.sharePct > 0 ? 3 : 0,
                          height: "100%",
                          background: C.blue,
                          borderRadius: 999,
                        }}
                      />
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
        <div className="hz-c2" style={cardStyle}>
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
                    {narratives[r.code] && (
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
                        {narratives[r.code]}
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
        <div className="hz-c2" style={cardStyle}>
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
          {/* 스냅샷은 백필이 안 돼 하루씩 쌓인다 — 7일치가 차기 전엔 실제로 잰 구간을 적는다 */}
          <SectionHead
            icon="rocket_launch"
            title="뜨는 채널"
            note={`${Math.min(7, rising[0]?.spanDays || 7)}일`}
            desc="최근 구독자가 많이 늘어난 채널"
          />
          {/* 간격을 이슈 키워드 카드의 행 높이(pitch 53px)에 맞춰 두 카드의 순위가 나란히 보이게 한다 */}
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 18 }}>
            {rising.map((r, i) => {
              // 채널 수가 정원보다 적을 때 채워 넣은 빈 행 — 높이만 지키고 아무것도 안 그린다.
              // (아바타 26px + 행 패딩에 맞춘 높이라 아래 실제 행과 pitch가 같다.)
              if (r.isPlaceholder) {
                return <li key={`empty-${i}`} style={{ height: 26 }} aria-hidden />;
              }
              const body = (
                <>
                  <span style={{ ...rankNum, color: C.sub }}>{i + 1}</span>
                  <Avatar photo={r.photo} title={r.title} size={26} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.title}</div>
                    <div style={{ fontSize: 10, fontFamily: MONO, color: C.sub }}>구독자 수 {compact(r.subscriberCount)}</div>
                  </div>
                  {/* 정원을 채우느라 증감이 없거나 줄어든 채널까지 들어올 수 있어 부호를 그대로 쓴다 */}
                  <span
                    style={{
                      fontFamily: MONO,
                      fontSize: 11,
                      fontWeight: 700,
                      color: r.delta7d > 0 ? C.hot : r.delta7d < 0 ? C.cold : C.sub,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {r.delta7d > 0 ? "▲" : r.delta7d < 0 ? "▼" : ""}
                    {Math.abs(r.delta7d).toLocaleString("ko-KR")}명
                  </span>
                </>
              );
              // 핸들이 있는 채널만 링크로 감싼다.
              return (
                <li key={`${r.handle ?? r.title}-${i}`}>
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

        {/* 이슈 키워드 (¼) — 종목이 아닌 화제어. analyze_telegram_messages.py 가 메시지별로
            뽑고 calculate_telegram_sentiment.py 가 telegram_keyword_daily 로 집계한 실데이터. */}
        <div style={cardStyle}>
          <SectionHead icon="tag" title="이슈 키워드" note="7일" desc="종목명이 아닌 화제어" />
          <div style={{ display: "flex", flexDirection: "column", gap: 23 }}>
            {keywords.length === 0 ? (
              <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>아직 뽑을 화제어가 없어요.</p>
            ) : (
              keywords.map((k, i) => {
                const max = keywords[0].count;
                return (
                  <div key={k.word} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <span style={{ ...rankNum, color: C.sub }}>{i + 1}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 6 }}>
                        <span style={{ fontWeight: 700, fontSize: 13, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{k.word}</span>
                        {/* 비교할 과거가 아직 없으면 화살표를 숨긴다 — ▲▼ 아무거나 붙이면 거짓말이 된다 */}
                        <span style={{ fontFamily: MONO, fontSize: 11, color: k.up == null ? C.sub : k.up ? C.hot : C.cold, flexShrink: 0 }}>
                          {k.up == null ? "" : k.up ? "▲ " : "▼ "}{k.count}회
                        </span>
                      </div>
                      <div style={{ marginTop: 5, height: 5, background: C.track, borderRadius: 999, overflow: "hidden" }}>
                        <div style={{ width: `${(k.count / max) * 100}%`, height: "100%", background: C.blue, borderRadius: 999, opacity: 0.8 }} />
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
