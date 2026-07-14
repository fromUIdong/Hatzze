"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import type { DailyScore } from "@/lib/data";
import { formatIndicatorValue } from "@/lib/format";
import { C, Icon, MONO } from "./ui";

const NAV = [
  { href: "/", label: "시장 브리핑", icon: "monitoring" },
  { href: "/telegram", label: "카더라 리포트", icon: "forum" },
];

const STAGE_COLOR: Record<string, string> = {
  냉정: C.cold,
  보통: C.neutral,
  과열: C.hot,
  광기: C.mania,
};

// 탑바 시세 티커. 햇쩨 지수는 서버에서 받은 일간 점수를 쓰고, 나머지 종목/지수/
// 환율은 5분 시세 소스를 붙이기 전까지 자리표시(—)로 둔다.
type Quote = { label: string; value: string; change: number | null; color?: string };

function Sidebar() {
  const pathname = usePathname();
  return (
    <aside
      className="hz-sidebar"
      style={{ width: 248, flexShrink: 0, background: C.card, borderRight: `1px solid ${C.line}`, padding: "32px 0" }}
    >
      <div style={{ padding: "0 32px", marginBottom: 48 }}>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 800, color: C.blue, letterSpacing: "-0.04em" }}>HATZZE</h1>
        <p style={{ margin: "6px 0 0", fontSize: 10, fontWeight: 700, color: C.sub, textTransform: "uppercase", letterSpacing: "0.2em" }}>
          시장 과열도 분석
        </p>
      </div>
      <nav style={{ flex: 1, padding: "0 16px", display: "flex", flexDirection: "column", gap: 8 }}>
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "16px 20px",
                color: active ? C.blue : C.sub,
                fontWeight: active ? 700 : 600,
                background: active ? "var(--c-blue-tint)" : "transparent",
                borderRadius: 14,
                textDecoration: "none",
              }}
            >
              <Icon name={item.icon} />
              <span style={{ fontSize: 15 }}>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

function ThemeToggle({ initial }: { initial: "light" | "dark" }) {
  // 초기값은 서버가 쿠키로 SSR한 값(prop)이라 아이콘도 첫 렌더부터 정확하다.
  const [theme, setTheme] = useState<"light" | "dark">(initial);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    document.cookie = `hz-theme=${next}; path=/; max-age=31536000; SameSite=Lax`;
  };

  return (
    <button
      onClick={toggle}
      aria-label="다크 모드 전환"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 38,
        height: 38,
        borderRadius: 12,
        border: `1px solid ${C.line}`,
        background: C.bg,
        color: C.sub,
        cursor: "pointer",
        flexShrink: 0,
      }}
    >
      <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} style={{ fontSize: 20 }} />
    </button>
  );
}

function TickerItem({ q }: { q: Quote }) {
  const changeColor = q.change === null ? C.sub : q.change > 0 ? C.mania : q.change < 0 ? C.cold : C.sub;
  const arrow = q.change === null ? "" : q.change > 0 ? "▲" : q.change < 0 ? "▼" : "";
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 6, whiteSpace: "nowrap" }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>{q.label}</span>
      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 800, color: q.color ?? C.ink }}>{q.value}</span>
      {q.change !== null && (
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: changeColor }}>
          {arrow}
          {Math.abs(q.change).toFixed(1)}%
        </span>
      )}
    </div>
  );
}

function TopBar({ dailyScore, theme }: { dailyScore: DailyScore | null; theme: "light" | "dark" }) {
  const hatzze: Quote = dailyScore
    ? {
        label: "햇쩨 지수",
        value: `${formatIndicatorValue(dailyScore.score, "%").display}% · ${dailyScore.stage}`,
        change: null,
        color: STAGE_COLOR[dailyScore.stage] ?? C.ink,
      }
    : { label: "햇쩨 지수", value: "—", change: null };

  // 5분 시세 연동 전까지 자리표시(—). 연동 시 이 배열만 실데이터로 교체된다.
  const quotes: Quote[] = [
    hatzze,
    { label: "코스피", value: "—", change: null },
    { label: "코스닥", value: "—", change: null },
    { label: "SK하이닉스", value: "—", change: null },
    { label: "삼성전자", value: "—", change: null },
    { label: "원/달러", value: "—", change: null },
  ];

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
        gap: 16,
        padding: "0 24px",
      }}
    >
      <div
        className="hz-ticker"
        style={{ display: "flex", alignItems: "center", gap: 22, overflowX: "auto", minWidth: 0 }}
      >
        {quotes.map((q, i) => (
          <div key={q.label} style={{ display: "flex", alignItems: "center", gap: 22 }}>
            {i > 0 && <span style={{ width: 1, height: 18, background: C.line, flexShrink: 0 }} />}
            <TickerItem q={q} />
          </div>
        ))}
      </div>
      <ThemeToggle initial={theme} />
    </header>
  );
}

export default function AppShell({
  dailyScore,
  theme,
  children,
}: {
  dailyScore: DailyScore | null;
  theme: "light" | "dark";
  children: React.ReactNode;
}) {
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
        <TopBar dailyScore={dailyScore} theme={theme} />
        <main className="hz-scroll" style={{ flex: 1, overflowY: "auto", padding: 40 }}>
          {children}
        </main>
      </div>
    </div>
  );
}
