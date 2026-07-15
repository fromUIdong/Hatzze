import type { Metadata } from "next";
import { C, Icon } from "../ui";

export const metadata: Metadata = {
  title: "카더라 리포트 | hatzze",
  description: "한국 주식 텔레그램 채널에서 가장 많이 언급되는 종목과 화제의 메시지를 분석합니다.",
};

const PREVIEW = [
  { icon: "trending_up", title: "가장 많이 언급된 종목", desc: "채널 전반에서 오늘 가장 자주 오르내린 종목 순위" },
  { icon: "campaign", title: "가장 많이 퍼진 메시지", desc: "여러 채널로 빠르게 확산된 화제의 메시지" },
  { icon: "insights", title: "채널 트렌드", desc: "언급량 급증·신규 등장 종목의 흐름" },
];

export default function TelegramPage() {
  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: C.ink }}>카더라 리포트</h2>
        <span
          style={{
            fontSize: 11,
            fontWeight: 800,
            color: C.hot,
            background: "var(--c-blue-tint)",
            padding: "4px 12px",
            borderRadius: 999,
          }}
        >
          준비 중
        </span>
        <div style={{ height: 1, flex: 1, background: C.line }} />
      </div>

      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: C.sub, maxWidth: 640 }}>
        한국 주식 관련 텔레그램 채널들을 모아 분석해요. 가장 많이 언급되는 기업, 가장 빠르게
        퍼지는 메시지 같은 걸 한눈에 보여드릴 예정이에요.
      </p>

      <div className="hz-grid">
        {PREVIEW.map((item) => (
          <div
            key={item.title}
            className="hz-span2"
            style={{
              background: C.card,
              borderRadius: 20,
              padding: 28,
              minHeight: 150,
              display: "flex",
              flexDirection: "column",
              gap: 12,
              border: `1px solid ${C.line}`,
            }}
          >
            <Icon name={item.icon} style={{ fontSize: 30, color: C.blue }} />
            <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: C.ink }}>{item.title}</h3>
            <p style={{ margin: 0, fontSize: 13, color: C.sub, lineHeight: 1.6 }}>{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
