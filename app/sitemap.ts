import type { MetadataRoute } from "next";

const SITE_URL = "https://hatzze.fun";

// /sitemap.xml 자동 생성 — 공개 라우트 목록. 지표는 매일 갱신되므로 changeFrequency=daily.
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: SITE_URL, lastModified: now, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/kadera`, lastModified: now, changeFrequency: "daily", priority: 0.8 },
    { url: `${SITE_URL}/mdd`, lastModified: now, changeFrequency: "daily", priority: 0.7 },
  ];
}
