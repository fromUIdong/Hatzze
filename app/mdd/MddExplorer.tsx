"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { DrawdownCharacter, DrawdownPoint, Episode, MddAnalysis } from "@/lib/mdd";
import { C, Icon, MONO } from "../ui";

export type StockOption = { code: string; name: string; market: string | null };

type Peer = { name: string; code: string; dd: number; isSelf: boolean };
type ThemeCmp = { name: string; peers: Peer[]; avgDd: number; sincePeakAvg: number | null };
type Attribution = { sincePeakDays: number; stock: number; market: number | null; theme: number | null };
type MddResult = {
  ok: true;
  code: string;
  name: string;
  market: string | null;
  years: string;
  analysis: MddAnalysis;
  attribution: Attribution | null;
  theme: ThemeCmp | null;
};

const PERIODS: { key: string; label: string }[] = [
  { key: "1", label: "1년" },
  { key: "3", label: "3년" },
  { key: "5", label: "5년" },
  { key: "10", label: "10년" },
  { key: "all", label: "전체" },
];

const DEFAULT: StockOption = { code: "005930", name: "삼성전자", market: "KOSPI" };

const fmtPct = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}%`;
const fmtWon = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`;
const fmtDays = (d: number) => {
  const yrs = d / 365;
  return yrs >= 1 ? `${d.toLocaleString("ko-KR")}일 (약 ${yrs.toFixed(1)}년)` : `${d.toLocaleString("ko-KR")}일`;
};

export function MddExplorer({ stocks, initial }: { stocks: StockOption[]; initial?: StockOption | null }) {
  // initial 은 URL(?code=…)로 지정된 종목. 없으면 기본 종목(삼성전자)으로 연다.
  const [selected, setSelected] = useState<StockOption>(initial ?? DEFAULT);
  const [years, setYears] = useState("10");
  const [data, setData] = useState<MddResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    // 조회는 외부 시스템(야후) 동기화라 effect 가 맞다. setState 를 effect 본문에
    // 직접 부르지 않고 이 async 함수 안에서만 호출한다(cascading-render 린트 회피).
    const run = async () => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({
        code: selected.code,
        market: selected.market ?? "KOSPI",
        name: selected.name,
        years,
      });
      try {
        const res = await fetch(`/api/mdd?${params}`);
        const json = await res.json();
        if (!active) return;
        if (json.ok) setData(json as MddResult);
        else setError(json.error ?? "불러오지 못했습니다.");
      } catch {
        if (active) setError("네트워크 오류로 불러오지 못했습니다.");
      } finally {
        if (active) setLoading(false);
      }
    };
    run();
    return () => {
      active = false;
    };
  }, [selected, years]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <header>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: C.ink, display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="trending_down" style={{ fontSize: 28, color: C.cold }} />
          MDD 정밀분석
        </h1>
        <p style={{ margin: "8px 0 0", color: C.sub, fontSize: 14, lineHeight: 1.6 }}>
          종목이 고점에서 <b style={{ color: C.ink }}>얼마나 빠졌는지</b>, 이만큼 빠진 적이 <b style={{ color: C.ink }}>얼마나 드문지</b>, 과거엔 회복까지 <b style={{ color: C.ink }}>얼마나 걸렸는지</b>를 봅니다.
        </p>
      </header>

      <Controls stocks={stocks} selected={selected} onSelect={setSelected} years={years} onYears={setYears} />

      {loading && <Skeleton />}
      {!loading && error && <ErrorCard message={error} />}
      {!loading && !error && data && <Results data={data} />}

      <p style={{ margin: 0, color: C.faint, fontSize: 12, lineHeight: 1.7 }}>
        모든 수치는 <b style={{ color: C.sub }}>종가</b> 기준이며 액면분할·감자를 반영한 수정주가입니다. 시세 출처는 Yahoo Finance이고,
        표본이 한 사이클 남짓이라 회복 기간은 <b style={{ color: C.sub }}>범위</b>로만 참고하십시오. 과거 통계는 재미·참고용이며 매수·매도 신호가 아닙니다.
      </p>
    </div>
  );
}

/* ── 조회 바: 종목 검색 + 기간 토글 ─────────────────────────────── */
function Controls({
  stocks,
  selected,
  onSelect,
  years,
  onYears,
}: {
  stocks: StockOption[];
  selected: StockOption;
  onSelect: (s: StockOption) => void;
  years: string;
  onYears: (y: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return stocks
      .filter((s) => s.name.toLowerCase().includes(q) || s.code.startsWith(q))
      .slice(0, 8);
  }, [query, stocks]);

  const pick = (s: StockOption) => {
    onSelect(s);
    setQuery("");
    setOpen(false);
  };

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
      <div ref={boxRef} style={{ position: "relative", flex: "1 1 260px", minWidth: 220 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "0 14px", height: 44 }}>
          <Icon name="search" style={{ fontSize: 20, color: C.sub }} />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            placeholder={`${selected.name} · 다른 종목 검색`}
            style={{ flex: 1, border: "none", outline: "none", background: "transparent", color: C.ink, fontSize: 15, minWidth: 0 }}
          />
        </div>
        {open && matches.length > 0 && (
          <ul style={{ position: "absolute", top: 50, left: 0, right: 0, zIndex: 20, listStyle: "none", margin: 0, padding: 6, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: `0 8px 24px ${C.shadow}` }}>
            {matches.map((s) => (
              <li key={s.code}>
                <button
                  onClick={() => pick(s)}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", padding: "9px 10px", border: "none", background: "transparent", borderRadius: 8, cursor: "pointer", color: C.ink, fontSize: 14, textAlign: "left" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = C.bg)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <span style={{ fontWeight: 600 }}>{s.name}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: C.faint }}>{s.code}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        {PERIODS.map((p) => {
          const on = p.key === years;
          return (
            <button
              key={p.key}
              onClick={() => onYears(p.key)}
              aria-pressed={on}
              style={{ padding: "9px 15px", borderRadius: 999, border: `1px solid ${on ? C.blue : C.line}`, background: on ? "var(--c-blue-tint)" : "transparent", color: on ? C.blue : C.sub, fontSize: 13, fontWeight: 800, cursor: "pointer", whiteSpace: "nowrap" }}
            >
              {p.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── 결과 ─────────────────────────────────────────────────────── */
function Results({ data }: { data: MddResult }) {
  const a = data.analysis;
  // 2열 배치: 헤드라인·테마는 full(넓어야 함), 나머지 컴팩트 카드는 둘씩.
  // 진단 페어[원인|성격] → 이력 페어[회복|Top5] 순으로 자연히 채워진다.
  return (
    <div className="mdd-grid">
      <div className="mdd-full">
        <Headline data={data} />
      </div>
      {data.attribution && (
        <Attribution
          attr={data.attribution}
          themeName={data.theme?.name ?? null}
          themePeers={data.theme?.peers.filter((p) => !p.isSelf).map((p) => p.name) ?? []}
          athDate={a.athDate}
        />
      )}
      {a.character && <Character ch={a.character} />}
      {a.recovery && <Recovery a={a} />}
      {a.topDrawdowns.length > 0 && <TopDrawdowns eps={a.topDrawdowns} />}
      {data.theme && (
        <div className="mdd-full">
          <Theme theme={data.theme} />
        </div>
      )}
    </div>
  );
}

const card: React.CSSProperties = { background: C.card, border: `1px solid ${C.line}`, borderRadius: 16, padding: 24, minWidth: 0 };

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ fontSize: 12, fontWeight: 700, padding: "4px 10px", borderRadius: 8, background: C.bg, color: C.sub, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function Headline({ data }: { data: MddResult }) {
  const a = data.analysis;
  const atHigh = a.currentDd > -1;
  const approxYears = (Date.parse(a.asOf) - Date.parse(a.firstDate)) / (365 * 86_400_000);
  const requested = data.years === "all" ? Infinity : Number(data.years);
  // 요청한 기간보다 상장 이력이 짧으면 "최근 10년"은 거짓이 된다 — 실제 구간으로 바꾼다.
  const truncated = data.years !== "all" && approxYears < requested - 0.5;
  const periodLabel =
    data.years === "all" || truncated ? `상장 이후·약 ${Math.max(1, Math.round(approxYears))}년` : `최근 ${data.years}년`;

  // 정직성 경고 — 겹쳐 쌓지 않고 필요한 것만.
  const cautions: string[] = [];
  if (data.years === "all")
    cautions.push("전체 구간에는 합병·감자·액면병합이 섞여 있어, 아주 오래된 낙폭은 지금의 회사와 다를 수 있습니다.");
  else if (truncated) cautions.push(`상장한 지 약 ${Math.round(approxYears)}년이라 요청한 기간보다 데이터가 짧습니다.`);
  if (approxYears < 2) cautions.push("표본이 짧아 더 오래된 종목과 같은 무게로 보지 마십시오.");
  return (
    <section style={card}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 20, fontWeight: 800, color: C.ink }}>{data.name}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, color: C.faint }}>{data.code}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Badge>{periodLabel}</Badge>
          <Badge>{a.asOf} 종가</Badge>
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 13, color: C.sub, marginBottom: 6 }}>고점 대비</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <span style={{ fontSize: 52, fontWeight: 800, lineHeight: 1, color: atHigh ? C.ink : C.cold }}>
            {atHigh ? "신고가 부근" : fmtPct(a.currentDd)}
          </span>
          {!atHigh && (
            <span style={{ fontSize: 15, color: C.sub, lineHeight: 1.6 }}>
              {periodLabel} 중 이보다 깊었던 날은 <b style={{ color: C.ink }}>{Math.round(a.deeperThanNowPct)}%</b>뿐입니다
            </span>
          )}
        </div>
        <div style={{ fontSize: 13, color: C.faint, marginTop: 10 }}>
          {fmtWon(a.price)} · 최고 {fmtWon(a.ath)} ({a.athDate})
        </div>
      </div>

      <Underwater series={a.underwater} mdd={a.mdd} />

      {cautions.map((c, i) => (
        <p key={i} style={{ margin: `${i === 0 ? 14 : 6}px 0 0`, fontSize: 12, color: C.sub, lineHeight: 1.6 }}>
          <Icon name="info" style={{ fontSize: 14, verticalAlign: -2, marginRight: 4 }} />
          {c}
        </p>
      ))}
    </section>
  );
}

/* 고점 대비 낙폭 곡선(언더워터). dd 는 0 이하이고 아래로 갈수록 깊다. */
function Underwater({ series, mdd }: { series: DrawdownPoint[]; mdd: number }) {
  const W = 720;
  const H = 176;
  const floor = Math.min(mdd, -1); // 0 나눗셈·완전 평평 방지
  const n = series.length;
  const x = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
  const y = (dd: number) => (dd / floor) * H;

  const line = series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.dd).toFixed(1)}`).join(" ");
  const area = `${line} L${W},0 Z`;

  // 연도 경계(1월로 처음 넘어가는 지점)를 눈금으로. 첫 데이터 지점은 연중(예: 2016-07)에
  // 시작해 완전한 연도가 아니고, x=0 이라 라벨이 왼쪽으로 잘린다("2016"→"16"). 그래서
  // i=0 은 건너뛰고 실제 1월 경계부터만 찍는다.
  const ticks: { x: number; year: number }[] = [];
  for (let i = 1; i < n; i++) {
    const yr = Number(series[i].date.slice(0, 4));
    if (Number(series[i - 1].date.slice(0, 4)) !== yr) ticks.push({ x: x(i), year: yr });
  }
  // 그리드 라인(0/절반/바닥) 라벨.
  const rows = [0, floor / 2, floor];

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 -6 ${W} ${H + 26}`} width="100%" role="img" aria-label={`고점 대비 낙폭 곡선. 현재 ${fmtPct(series[n - 1].dd)}, 기간 최저 ${fmtPct(mdd)}`}>
        <line x1="0" y1="0" x2={W} y2="0" stroke={C.line} strokeWidth="1" />
        {rows.slice(1).map((dd, i) => (
          <line key={i} x1="0" y1={y(dd)} x2={W} y2={y(dd)} stroke={C.line} strokeWidth="1" strokeDasharray="2 5" />
        ))}
        <path d={area} fill={C.cold} fillOpacity="0.14" />
        <path d={line} fill="none" stroke={C.cold} strokeWidth="1.6" strokeLinejoin="round" />
        <circle cx={W} cy={y(series[n - 1].dd)} r="4.5" fill={C.cold} stroke={C.card} strokeWidth="2" />
        {rows.map((dd, i) => (
          <text key={i} x="3" y={y(dd) + (i === 0 ? 12 : -4)} fontSize="11" fill={C.faint}>
            {Math.round(dd)}%
          </text>
        ))}
        {ticks.map((t, i) => (
          <text key={i} x={t.x} y={H + 16} fontSize="11" fill={C.faint} textAnchor="middle">
            {t.year}
          </text>
        ))}
      </svg>
      {/* 시장 브리핑 지표 카드와 같은 크로스헤어 — 보이지 않는 세로 띠가 hover 시 기준선(hz-vline)과
          툴팁(hz-tip)을 낸다. 연도 라벨 높이(≈26px)만큼 아래로 남는 띠는 무시할 수준이다. */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 26, display: "flex" }}>
        {series.map((p, i) => (
          <div key={i} className="hz-tip hz-vline" data-tip={`${p.date} · ${fmtWon(p.close)} · 고점 대비 ${fmtPct(p.dd)}`} style={{ flex: 1, position: "relative" }} />
        ))}
      </div>
    </div>
  );
}

/* 이 하락이 시장 탓인지 종목 탓인지 — 고점 이후 같은 기간 종목/시장/테마 비교. */
function Attribution({
  attr,
  themeName,
  themePeers,
  athDate,
}: {
  attr: Attribution;
  themeName: string | null;
  themePeers: string[];
  athDate: string;
}) {
  const rows: { label: string; v: number; self: boolean; help?: string }[] = [{ label: "이 종목", v: attr.stock, self: true }];
  if (attr.market !== null) rows.push({ label: "코스피", v: attr.market, self: false });
  if (attr.theme !== null)
    rows.push({
      label: `${themeName ?? "테마"} 대표`,
      v: attr.theme,
      self: false,
      // "○○ 대표"가 어떤 종목인지 툴팁으로 밝힌다 — 이 종목은 뺀 나머지 대표 종목 평균이다.
      help: themePeers.length ? `${themePeers.join(" · ")}. 이 테마 대표 종목의 평균입니다 (이 종목 제외).` : undefined,
    });
  const worst = Math.max(...rows.map((r) => Math.abs(r.v)), 1);

  // 판단 기준은 시장(없으면 테마). 종목이 기준보다 얼마나 더/덜 빠졌나.
  const bench = attr.market ?? attr.theme;
  const gap = bench !== null ? attr.stock - bench : 0;
  const verdict =
    bench === null
      ? "같은 기간 종목의 낙폭입니다."
      : gap >= 8
        ? "시장이 빠지는 와중에 상대적으로 버틴 편입니다."
        : gap <= -8
          ? "시장·업종보다 더 깊게 빠졌습니다. 종목 고유 요인이 있는지 볼 대목입니다."
          : "거의 시장을 따라 움직였습니다. 이 하락의 대부분은 시장 전체가 함께 빠진 것입니다.";

  return (
    <section style={card}>
      <SectionTitle icon="call_split" title="이 하락, 시장 탓일까 종목 탓일까" />
      <p style={{ margin: "0 0 4px", color: C.ink, fontSize: 15, fontWeight: 700, lineHeight: 1.6 }}>{verdict}</p>
      <p style={{ margin: "0 0 16px", color: C.faint, fontSize: 12 }}>
        고점({athDate}) 이후 {attr.sincePeakDays.toLocaleString("ko-KR")}일, 같은 기간을 나란히 놓고 비교합니다.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r) => {
          // 고점 이후 수익률이라 시장·테마는 상승(+)일 수도 있다 — 부호로 색을 가른다
          // (하락=파랑, 상승=빨강, 티커와 같은 한국장 관례). 자기 종목만 진하게.
          const barColor = r.v >= 0 ? C.mania : C.cold;
          return (
            <div key={r.label} style={{ display: "grid", gridTemplateColumns: "118px minmax(0,1fr) 56px", alignItems: "center", gap: 10 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 3, minWidth: 0 }}>
                <span style={{ fontSize: 13, color: r.self ? C.ink : C.sub, fontWeight: r.self ? 700 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}</span>
                {r.help && (
                  <span className="hz-tip hz-tip-wide" data-tip={r.help} style={{ flexShrink: 0, display: "inline-flex", cursor: "help", color: C.faint }}>
                    <Icon name="help" style={{ fontSize: 14 }} />
                  </span>
                )}
              </span>
              <span style={{ height: 8, background: C.bg, borderRadius: 4, overflow: "hidden" }}>
                <span style={{ display: "block", height: "100%", width: `${(Math.abs(r.v) / worst) * 100}%`, background: barColor, opacity: r.self ? 1 : 0.5, borderRadius: 4 }} />
              </span>
              <span style={{ fontSize: 13, textAlign: "right", color: r.self ? C.ink : C.sub, fontWeight: r.self ? 700 : 400 }}>{fmtPct(r.v)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Recovery({ a }: { a: MddAnalysis }) {
  const r = a.recovery!;

  // 지금 깊이에서 회복한 전례가 없으면(대개 역대 최대 낙폭) 회복 통계를 낼 표본이 없다.
  // "아직 회복 못 함 1건" 타일 하나만 덩그러니 두는 대신, 얼마나 오래 미회복 중인지를 보여준다.
  if (r.recoveredCount === 0) {
    const days = Math.round((Date.parse(a.asOf) - Date.parse(a.athDate)) / 86_400_000);
    const yrs = days / 365;
    return (
      <section style={card}>
        <SectionTitle icon="history" title="회복까지 걸린 시간" />
        <p style={{ margin: "0 0 16px", color: C.sub, fontSize: 14, lineHeight: 1.7 }}>
          이만큼(<b style={{ color: C.ink }}>{fmtPct(a.currentDd)}</b>) 깊게 빠진 뒤 <b style={{ color: C.ink }}>회복한 전례가 없습니다</b>. 지금이 이 종목의 역대 최대 낙폭입니다.
        </p>
        <div style={{ background: C.bg, borderRadius: 12, padding: "14px 16px" }}>
          <div style={{ fontSize: 12, color: C.sub, marginBottom: 6 }}>고점({a.athDate}) 이후 지금까지</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 26, fontWeight: 800, color: C.mania }}>{days.toLocaleString("ko-KR")}일</span>
            <span style={{ fontSize: 14, color: C.sub }}>{yrs >= 1 ? `약 ${yrs.toFixed(1)}년째 회복 못 함` : "회복 못 함"}</span>
          </div>
        </div>
      </section>
    );
  }

  const tiles: { label: string; value: string; accent?: boolean }[] = [
    { label: "최단 회복", value: fmtDays(r.minDays!) },
    { label: "중앙값", value: fmtDays(r.medianDays!) },
    { label: "최장 회복", value: fmtDays(r.maxDays!) },
  ];
  if (r.unrecoveredCount > 0) tiles.push({ label: "아직 회복 못 함", value: `${r.unrecoveredCount}건`, accent: true });

  return (
    <section style={card}>
      <SectionTitle icon="history" title="회복까지 걸린 시간" />
      <p style={{ margin: "0 0 16px", color: C.sub, fontSize: 14, lineHeight: 1.7 }}>
        과거 이만큼(<b style={{ color: C.ink }}>{fmtPct(a.currentDd)}</b> 이상) 빠졌던 건 <b style={{ color: C.ink }}>{r.similarCount}번</b>이고,
        그중 <b style={{ color: C.ink }}>{r.recoveredCount}번</b>은 고점을 되찾았습니다.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {tiles.map((t, i) => (
          <div key={i} style={{ flex: "1 1 160px", minWidth: 150, background: C.bg, borderRadius: 12, padding: "12px 14px" }}>
            <div style={{ fontSize: 12, color: C.sub, marginBottom: 4 }}>{t.label}</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: t.accent ? C.mania : C.ink }}>{t.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* 이 하락의 속도 — 급락형 vs 완만형. 같은 깊이라도 빨리 빠진 건 빨리 회복하는 편. */
function Character({ ch }: { ch: DrawdownCharacter }) {
  const isFast = ch.currentClass === "fast";
  const curLabel = isFast ? "급락형" : "완만형";
  const hasBuckets = Boolean(ch.fast || ch.slow);
  const compare =
    ch.fast && ch.slow
      ? `이 종목의 과거 하락은 급락형이 완만형보다 회복이 ${ch.fast.medianRecovery < ch.slow.medianRecovery ? "빨랐" : "느렸"}습니다.`
      : null;
  const tiles: { label: string; sub: string; b: { count: number; medianRecovery: number } | null; on: boolean }[] = [
    { label: "급락형", sub: "빠르게 빠진 하락", b: ch.fast, on: isFast },
    { label: "완만형", sub: "오래 흘러내린 하락", b: ch.slow, on: !isFast },
  ];
  return (
    <section style={card}>
      <SectionTitle icon="bolt" title="이 하락의 성격" />
      <p style={{ margin: `0 0 ${hasBuckets ? 4 : 12}px`, color: C.sub, fontSize: 14, lineHeight: 1.7 }}>
        지금은 <b style={{ color: C.ink }}>{curLabel}</b>입니다. 고점 이후 <b style={{ color: C.ink }}>{ch.currentTroughDays.toLocaleString("ko-KR")}일</b> 만에 저점({fmtPct(ch.currentTroughDepth)})까지 빠졌습니다.
        {compare && ` ${compare}`}
      </p>
      {hasBuckets ? (
        <>
          <p style={{ margin: "0 0 14px", color: C.faint, fontSize: 12 }}>과거 −15% 이상 하락을 속도로 나눈 회복 기간(중앙값)입니다.</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {tiles.map((t) =>
              t.b ? (
                <div key={t.label} style={{ flex: "1 1 160px", minWidth: 150, background: t.on ? "var(--c-blue-tint)" : C.bg, border: `1px solid ${t.on ? C.blue : "transparent"}`, borderRadius: 12, padding: "12px 14px" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: t.on ? C.blue : C.ink }}>
                    {t.label} <span style={{ fontWeight: 400, color: C.faint }}>· {t.b.count}번</span>
                  </div>
                  <div style={{ fontSize: 12, color: C.sub, margin: "1px 0 8px" }}>{t.sub}</div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: C.ink }}>{fmtDays(t.b.medianRecovery)}</div>
                </div>
              ) : null,
            )}
          </div>
        </>
      ) : (
        <p style={{ margin: 0, color: C.faint, fontSize: 12, lineHeight: 1.6 }}>
          <Icon name="info" style={{ fontSize: 14, verticalAlign: -2, marginRight: 4 }} />
          이 기간엔 비교할 과거 하락이 부족합니다. 기간을 넓히면 급락형·완만형 회복을 비교할 수 있습니다.
        </p>
      )}
    </section>
  );
}

function Theme({ theme }: { theme: ThemeCmp }) {
  const worst = Math.max(...theme.peers.map((p) => Math.abs(p.dd)), 1);
  const self = theme.peers.find((p) => p.isSelf)!;
  // 깊게 빠진 순 등수 — dd 가 더 음수(깊음)인 종목 수 +1. 1위 = 가장 깊게 빠짐.
  const rank = theme.peers.filter((p) => p.dd < self.dd).length + 1;
  const lead =
    rank === 1
      ? "테마에서 가장 깊게 빠졌습니다."
      : rank === theme.peers.length
        ? "테마에서 가장 덜 빠졌습니다."
        : `테마 ${theme.peers.length}종목 중 낙폭 ${rank}위입니다.`;
  return (
    <section style={card}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 4 }}>
        <SectionTitle icon="hub" title={`${theme.name} 대표 ${theme.peers.length}종목 안에서`} noMargin />
        <Badge>평균 {fmtPct(theme.avgDd)}</Badge>
      </div>
      <p style={{ margin: "6px 0 16px", color: C.sub, fontSize: 14, lineHeight: 1.7 }}>
        <b style={{ color: C.ink }}>{self.name}</b>. {lead}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {theme.peers.map((p) => (
          <div key={p.code || p.name} style={{ display: "grid", gridTemplateColumns: "104px minmax(0,1fr) 52px", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: p.isSelf ? C.ink : C.sub, fontWeight: p.isSelf ? 700 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
            <span style={{ height: 8, background: C.bg, borderRadius: 4, overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", width: `${(Math.abs(p.dd) / worst) * 100}%`, background: p.isSelf ? C.cold : C.track, borderRadius: 4 }} />
            </span>
            <span style={{ fontSize: 13, textAlign: "right", color: p.isSelf ? C.ink : C.sub, fontWeight: p.isSelf ? 700 : 400 }}>{Math.round(p.dd)}%</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function TopDrawdowns({ eps }: { eps: Episode[] }) {
  return (
    <section style={card}>
      <SectionTitle icon="leaderboard" title="역대 낙폭 Top 5" />
      <div style={{ display: "flex", flexDirection: "column" }}>
        {eps.map((e, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
            <span style={{ width: 20, fontFamily: MONO, fontWeight: 800, fontSize: 14, color: C.faint }}>{i + 1}</span>
            <span style={{ flex: 1, fontSize: 13, color: C.sub, minWidth: 0 }}>{e.peakDate} 고점</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: C.cold, width: 64, textAlign: "right" }}>{Math.round(e.depth)}%</span>
            <span style={{ fontSize: 12, color: e.recovered ? C.sub : C.mania, width: 140, textAlign: "right" }}>
              {e.recovered ? `${e.days.toLocaleString("ko-KR")}일 만에 회복` : `${e.days.toLocaleString("ko-KR")}일째 미회복`}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── 보조 ─────────────────────────────────────────────────────── */
function SectionTitle({ icon, title, noMargin }: { icon: string; title: string; noMargin?: boolean }) {
  return (
    <h2 style={{ margin: noMargin ? 0 : "0 0 14px", fontSize: 16, fontWeight: 800, color: C.ink, display: "flex", alignItems: "center", gap: 8 }}>
      <Icon name={icon} style={{ fontSize: 20, color: C.sub }} />
      {title}
    </h2>
  );
}

function Skeleton() {
  return (
    <div style={{ ...card, height: 320, display: "flex", alignItems: "center", justifyContent: "center", color: C.faint, fontSize: 14 }}>
      불러오는 중…
    </div>
  );
}

function ErrorCard({ message }: { message: string }) {
  return (
    <div style={{ ...card, display: "flex", alignItems: "center", gap: 10, color: C.sub, fontSize: 14 }}>
      <Icon name="error_outline" style={{ fontSize: 20, color: C.mania }} />
      {message}
    </div>
  );
}
