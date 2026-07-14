import type { Metadata } from "next";
import localFont from "next/font/local";
import { cookies } from "next/headers";
import "./globals.css";
import AppShell from "./AppShell";
import { getLatestDailyScore } from "@/lib/data";
import type { DailyScore } from "@/lib/data";

const pretendard = localFont({
  src: "../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  variable: "--font-pretendard",
  display: "swap",
  weight: "45 920",
});

export const metadata: Metadata = {
  title: "Hatzze — 코스피 과열도 판독기",
  description: "시장 지표와 감성 지표로 오늘의 코스피 과열도를 확인하세요.",
};

// 사이드바/탑바는 모든 페이지가 공유하므로 레이아웃에서 점수를 받아 셸에 넘긴다.
// env가 없는 빌드 환경에서도 죽지 않도록 실패 시 null로 둔다(탑바가 —로 표시).
export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let dailyScore: DailyScore | null = null;
  try {
    dailyScore = await getLatestDailyScore();
  } catch {
    dailyScore = null;
  }

  // 테마는 쿠키로 관리한다 — 서버가 여기서 읽어 <html data-theme>를 SSR하면
  // 클라이언트와 값이 일치해 hydration 불일치도, 첫 페인트 깜빡임도 없다.
  const theme = (await cookies()).get("hz-theme")?.value === "dark" ? "dark" : "light";

  return (
    <html lang="ko" data-theme={theme} className={`${pretendard.variable} h-full antialiased`}>
      <head>
        {/* 대시보드 목업이 쓰는 웹폰트. Pretendard는 위에서 로컬로 자체
            호스팅하지만, 본문/숫자용 서체와 Material Symbols 아이콘은
            빌드 시점 폰트 페치 실패를 피하려고 런타임 CDN 링크로 둔다. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block"
          rel="stylesheet"
        />
      </head>
      <body className="font-sans">
        <AppShell dailyScore={dailyScore} theme={theme}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
