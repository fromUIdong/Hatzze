import Link from "next/link";

import { GhostSymbol, Wordmark } from "./Logo";
import { C } from "./ui";

// SEO를 위해 시맨틱 <footer> + 내부 링크(<nav>) + 키워드가 담긴 사이트 소개글을
// 둔다. 색은 전부 CSS 변수(C.*)라 라이트/다크가 함께 전환된다.

// 실제 fetch 스크립트가 쓰는 소스를 카테고리별로 정리.
const SOURCE_GROUPS: { label: string; items: string }[] = [
  { label: "증시·시세", items: "한국거래소(KRX) · 야후 파이낸스" },
  { label: "거시·금리", items: "한국은행(ECOS) · 미 연준(FRED)" },
  { label: "검색·뉴스", items: "네이버 · 유튜브" },
  { label: "커뮤니티·소비", items: "디시인사이드 · 알라딘" },
  { label: "가상자산·기타", items: "업비트 · GitHub · 앱스토어" },
];

function FooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.sub, textDecoration: "none", padding: "4px 0" }}
    >
      {children}
    </Link>
  );
}

/** 외부 링크용. next/link 대신 <a> 를 써서 새 탭으로 연다(모양은 FooterLink 와 동일). */
function FooterExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{ display: "block", fontSize: 13, fontWeight: 600, color: C.sub, textDecoration: "none", padding: "4px 0" }}
    >
      {children}
    </a>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 800, color: C.ink, textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 10 }}>
      {children}
    </div>
  );
}

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer style={{ marginTop: 56, borderTop: `1px solid ${C.line}`, paddingTop: 36 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "40px 64px", justifyContent: "space-between" }}>
        {/* 브랜드 + 키워드 소개글 */}
        <div style={{ maxWidth: 380 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
            <GhostSymbol size={26} />
            <Wordmark size={26} />
          </span>
          <p style={{ margin: "14px 0 0", fontSize: 13, lineHeight: 1.75, color: C.sub }}>
            <b style={{ color: C.ink }}>hatzze(햇쩨)</b>는 코스피 시장의 <b style={{ color: C.ink }}>과열도</b>를
            시장 지표와 감성 지표로 종합해 매일 0~100 점수로 보여주는 대시보드입니다.
            버핏지수, VKOSPI, 레버리지 ETF, 공포·탐욕 심리 등 26개 지표를 한눈에 볼 수 있습니다.
          </p>
        </div>

        {/* 우측 그룹: 내부 링크 + 데이터 출처 */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "28px 48px" }}>
          <nav aria-label="바로가기">
            <GroupLabel>바로가기</GroupLabel>
            <FooterLink href="/">시장 브리핑</FooterLink>
            <FooterLink href="/kadera">카더라 리포트</FooterLink>
            {/* 사이드바가 모바일에서 숨겨져 커뮤니티 링크가 사라진다 — 내부 내비게이션과
                같은 방식으로 푸터에 두어 좁은 화면에서도 닿게 한다. */}
            <FooterExternalLink href="https://t.me/hatzze_kr">커뮤니티 합류</FooterExternalLink>
          </nav>
          <div>
            <GroupLabel>데이터 출처</GroupLabel>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, auto)", gap: "12px 32px" }}>
              {SOURCE_GROUPS.map((g) => (
                <div key={g.label} style={{ minWidth: 140 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.ink, marginBottom: 3 }}>{g.label}</div>
                  <div style={{ fontSize: 12, lineHeight: 1.55, color: C.sub }}>{g.items}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 하단 바: 면책 + 저작권 */}
      <div
        style={{
          marginTop: 28,
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 20px",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <p style={{ margin: 0, fontSize: 11, color: "var(--c-muted)" }}>
          이 서비스는 재미와 참고를 위한 정보 제공 목적이며, 투자 조언이나 매수·매도 추천이 아닙니다. 모든 투자 판단과 책임은 이용자 본인에게 있습니다.
        </p>
        <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: "var(--c-muted)" }}>Copyright © {year} hatzze. All rights reserved.</p>
      </div>
    </footer>
  );
}
