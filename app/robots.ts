import type { MetadataRoute } from "next";

const SITE_URL = "https://hatzze.fun";

// /robots.txt 자동 생성 — 전체 크롤링 허용 + 사이트맵 위치 안내.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
