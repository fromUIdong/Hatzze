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

const SITE_URL = "https://hatzze.fun";
const TITLE = "hatzze | 데이터와 감성으로 읽는 시장";
const DESCRIPTION =
  "시장 지표와 감성 지표로 오늘의 코스피 과열도를 확인하세요. 버핏지수·VKOSPI·레버리지 등 26개 지표를 매일 0~100 점수로.";

// opengraph-image.tsx(파일 컨벤션)가 openGraph/twitter 이미지를 자동으로 채운다.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  keywords: ["코스피 과열도", "시장 과열도", "버핏지수", "VKOSPI", "공포탐욕지수", "증시 심리", "코스피 지표", "hatzze", "햇쩨"],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: "ko_KR",
    url: SITE_URL,
    siteName: "hatzze",
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
  },
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
        {/* 본문·숫자는 전부 Pretendard(위에서 next/font/local로 자체 호스팅)라 CDN에서
            받아오는 건 두 가지뿐이다: 워드마크 전용 Bricolage Grotesque와 Material Symbols
            아이콘. 둘 다 빌드 시점 폰트 페치 실패를 피하려고 런타임 CDN 링크로 둔다.
            (예전엔 Plus Jakarta Sans·JetBrains Mono도 받았는데, 한글 글리프가 없어 서체가
             갈리는 원인이라 Pretendard로 통일하며 걷어냈다.) */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block"
          rel="stylesheet"
        />
        {/* 구조화 데이터(JSON-LD) — 검색엔진에 사이트/조직 정보를 명시적으로 제공. */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@graph": [
                {
                  "@type": "WebSite",
                  "@id": `${SITE_URL}/#website`,
                  url: SITE_URL,
                  name: "hatzze",
                  alternateName: "햇쩨",
                  description: DESCRIPTION,
                  inLanguage: "ko-KR",
                  publisher: { "@id": `${SITE_URL}/#organization` },
                },
                {
                  "@type": "Organization",
                  "@id": `${SITE_URL}/#organization`,
                  name: "hatzze",
                  url: SITE_URL,
                  logo: `${SITE_URL}/icon.svg`,
                },
              ],
            }),
          }}
        />
      </head>
      {/* 일부 브라우저 확장(예: ColorZilla의 cz-shortcut-listen)이 hydration 전에
          <body>에 속성을 주입해 불일치 경고를 낸다. body 자신의 속성 불일치만
          무시한다 — 내부 컴포넌트 hydration 검사에는 영향 없다. */}
      <body className="font-sans" suppressHydrationWarning>
        <AppShell dailyScore={dailyScore} theme={theme}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
