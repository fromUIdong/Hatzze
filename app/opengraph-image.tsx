import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

// 카톡·X·슬랙 등에서 hatzze.fun 링크를 공유할 때 뜨는 미리보기 이미지(1200×630).
// 한글 렌더를 위해 로컬 Pretendard OTF를 폰트로 넘긴다(Satori는 woff2 미지원, otf 지원).
export const runtime = "nodejs";
export const alt = "hatzze — 데이터와 감성으로 읽는 시장";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const GHOST =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 104">' +
  '<path d="M12,84 C6,42 22,8 50,8 C78,8 94,42 88,84 C86,95 80,95 77,87 C74,80 67,80 64,88 C61,96 54,96 51,88 C48,80 41,80 38,88 C35,96 28,96 25,87 C22,80 15,93 12,84 Z" fill="#0064ff"/>' +
  '<ellipse cx="39" cy="50" rx="9.5" ry="12" fill="#fff"/><circle cx="66" cy="52" r="7" fill="#fff"/><circle cx="42" cy="45" r="3" fill="#0064ff"/></svg>';

const FONT_DIR = "node_modules/pretendard/dist/public/static";

export default async function Image() {
  const [extraBold, medium] = await Promise.all([
    readFile(join(process.cwd(), FONT_DIR, "Pretendard-ExtraBold.otf")),
    readFile(join(process.cwd(), FONT_DIR, "Pretendard-Medium.otf")),
  ]);
  const ghost = `data:image/svg+xml;base64,${Buffer.from(GHOST).toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 100px",
          background: "#eef2ff",
          fontFamily: "Pretendard",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={ghost} width={132} height={137} alt="" />
          <div style={{ fontSize: 128, fontWeight: 800, color: "#25262f", letterSpacing: "-5px" }}>hatzze</div>
        </div>
        <div style={{ marginTop: 40, fontSize: 48, fontWeight: 800, color: "#25262f" }}>데이터와 감성으로 읽는 시장</div>
        <div style={{ marginTop: 20, fontSize: 30, fontWeight: 500, color: "#5b6474" }}>
          코스피 과열도를 매일 0~100 점수로 · 시장·감성 25개 지표
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: "Pretendard", data: extraBold, weight: 800, style: "normal" },
        { name: "Pretendard", data: medium, weight: 500, style: "normal" },
      ],
    },
  );
}
