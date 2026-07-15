import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // OG 이미지(app/opengraph-image.tsx)가 런타임에 읽는 Pretendard OTF를 프로덕션
  // 번들에 확실히 포함시킨다 — 없으면 배포 환경에서 폰트 로딩이 실패할 수 있다.
  outputFileTracingIncludes: {
    "/opengraph-image": ["./node_modules/pretendard/dist/public/static/Pretendard-*.otf"],
  },
};

export default nextConfig;
