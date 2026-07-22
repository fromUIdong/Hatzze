"use client";

import { Fragment, useState } from "react";

import { C } from "../ui";
import { SectionHead } from "./SectionHead";

/**
 * 트렌딩 메시지의 기간 탭(오늘 / 최근 7일 / 최근 30일).
 *
 * 탭은 카드 머리 우측에 붙고 목록은 그 아래라, 둘을 한 컴포넌트가 감싸야 상태를
 * 공유할 수 있다. 그래서 SectionHead 까지 여기서 그린다(그래서 SectionHead 를
 * page.tsx 밖 별도 파일로 뺐다).
 *
 * ExpandableList 와 같은 원칙 — 조회와 목록 마크업은 서버 컴포넌트에 남기고,
 * 여기서는 어느 패널을 보여줄지만 관리한다. 세 창을 서버가 미리 렌더해 넘기므로
 * 탭을 눌러도 왕복이 없다.
 *
 * 패널에 key(기간)를 주는 게 중요하다 — 없으면 React 가 같은 자리의 같은
 * ExpandableList 를 재사용해 '더 보기'로 펼친 개수가 다음 탭으로 넘어간다
 * (30일에서 26개까지 펼친 뒤 오늘로 오면 8개가 전부 펼쳐진 채 '접기'가 뜬다).
 * key 를 주면 기간이 바뀔 때 새로 마운트되어 처음 6개부터 다시 보인다.
 */
export type TrendingPanel = {
  key: string;
  label: string;
  /** 0건이면 목록 대신 안내 문구를 보여주기 위한 값(탭에 숫자로 노출하진 않는다). */
  count: number;
  node: React.ReactNode;
};

export function TrendingTabs({
  icon,
  title,
  desc,
  panels,
}: {
  icon: string;
  title: string;
  desc?: string;
  panels: TrendingPanel[];
}) {
  const [active, setActive] = useState(panels[0]?.key);
  const current = panels.find((p) => p.key === active) ?? panels[0];

  const tabs = (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {panels.map((p) => {
        const on = p.key === current?.key;
        return (
          <button
            key={p.key}
            type="button"
            onClick={() => setActive(p.key)}
            aria-pressed={on}
            style={{
              padding: "6px 13px",
              borderRadius: 999,
              border: `1px solid ${on ? C.blue : C.line}`,
              background: on ? `${C.blue}14` : "transparent",
              color: on ? C.blue : C.sub,
              fontSize: 12,
              fontWeight: 800,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );

  return (
    <>
      <SectionHead icon={icon} title={title} desc={desc} right={tabs} />
      {current?.count === 0 ? (
        <p style={{ margin: 0, color: C.sub, fontSize: 13 }}>
          {current.label} 기준으로는 아직 화제 메시지가 없습니다.
        </p>
      ) : (
        <Fragment key={current?.key}>{current?.node}</Fragment>
      )}
    </>
  );
}
