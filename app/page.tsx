import { getLatestDailyScore, getPublicIndicators } from "@/lib/data";
import type { IndicatorWithLatestValue } from "@/lib/data";
import { formatIndicatorValue } from "@/lib/format";

// 지표는 하루 단위(GitHub Actions 배치)로 갱신되므로, 빌드 시점에 정적으로
// 굳어버리지 않도록 매 요청마다 서버에서 새로 조회한다.
export const dynamic = "force-dynamic";

const STAGE_ORDER = ["냉정", "보통", "과열", "광기"] as const;

const STAGE_BADGE_CLASS: Record<string, string> = {
  냉정: "bg-sky-500/10 text-sky-300",
  보통: "bg-neutral-500/15 text-neutral-300",
  과열: "bg-amber-500/10 text-amber-300",
  광기: "bg-red-500/10 text-red-300",
};

const STAGE_BAR_CLASS: Record<string, string> = {
  냉정: "bg-sky-500/70",
  보통: "bg-neutral-500/70",
  과열: "bg-amber-500/70",
  광기: "bg-red-500/70",
};

function StageGauge({ stage }: { stage: string }) {
  const stageIndex = STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]);

  return (
    <div className="mt-5 mx-auto max-w-xs">
      <div className="relative">
        <div className="flex h-2 rounded-full overflow-hidden">
          {STAGE_ORDER.map((s) => (
            <div key={s} className={`flex-1 ${STAGE_BAR_CLASS[s]}`} />
          ))}
        </div>
        {stageIndex !== -1 && (
          <div
            className="absolute -top-1 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-neutral-950 bg-neutral-50 shadow"
            style={{ left: `${(stageIndex + 0.5) * 25}%` }}
          />
        )}
      </div>
      <div className="flex justify-between mt-1.5 text-[11px] text-neutral-500">
        {STAGE_ORDER.map((s) => (
          <span key={s}>{s}</span>
        ))}
      </div>
    </div>
  );
}

function IndicatorCard({ indicator }: { indicator: IndicatorWithLatestValue }) {
  const hasValue = indicator.latest !== null;
  const normalizedScore = indicator.latest?.normalized_score ?? null;
  const isHit = (normalizedScore ?? 0) >= 100;
  const barWidth =
    normalizedScore !== null ? Math.min(Math.max(normalizedScore, 0), 100) : 0;
  const { display, displayUnit } = hasValue
    ? formatIndicatorValue(indicator.latest!.raw_value, indicator.unit)
    : { display: "-", displayUnit: indicator.unit };
  const normalizedScoreDisplay =
    normalizedScore !== null ? formatIndicatorValue(normalizedScore, "%") : null;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium text-neutral-100">{indicator.name}</h3>
        {hasValue && (
          <span
            className={
              isHit
                ? "text-xs font-semibold text-red-400"
                : "text-xs text-neutral-600"
            }
          >
            {isHit ? "● Hit" : "○"}
          </span>
        )}
      </div>
      <p className="text-2xl font-semibold mt-1 text-neutral-100">
        {display}
        <span className="text-sm font-normal text-neutral-500 ml-1">
          {displayUnit}
        </span>
      </p>

      {normalizedScoreDisplay !== null && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-neutral-500">과열도</span>
            <span
              className={
                isHit
                  ? "font-semibold text-red-400"
                  : "text-neutral-400"
              }
            >
              {normalizedScoreDisplay.display}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-neutral-800 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                isHit ? "bg-red-500" : "bg-neutral-500"
              }`}
              style={{ width: `${barWidth}%` }}
            />
          </div>
        </div>
      )}

      <p className="text-sm text-neutral-500 mt-2 leading-relaxed">
        {indicator.description_beginner}
      </p>
    </div>
  );
}

export default async function Home() {
  const [dailyScore, indicators] = await Promise.all([
    getLatestDailyScore(),
    getPublicIndicators(),
  ]);

  const traditional = indicators.filter((i) => i.category === "정통");
  const meme = indicators.filter((i) => i.category === "밈");

  return (
    <main className="max-w-2xl mx-auto p-6 space-y-12">
      <div className="text-center">
        <span className="text-2xl font-extrabold tracking-[0.2em] text-neutral-100">
          HATZZE
        </span>
      </div>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-8 sm:p-10 text-center">
        {dailyScore ? (
          <>
            <p className="text-sm text-neutral-500">{dailyScore.date} 기준</p>
            <p className="text-6xl sm:text-7xl font-bold mt-3 tracking-tight text-neutral-50">
              {formatIndicatorValue(dailyScore.score, "%").display}%
            </p>
            <span
              className={`inline-block mt-4 px-4 py-1.5 rounded-full text-sm font-medium ${
                STAGE_BADGE_CLASS[dailyScore.stage] ??
                "bg-neutral-500/15 text-neutral-300"
              }`}
            >
              {dailyScore.stage}
            </span>
            <StageGauge stage={dailyScore.stage} />
          </>
        ) : (
          <p className="text-neutral-500">아직 계산된 스코어가 없습니다.</p>
        )}
      </section>

      <section>
        <h2 className="text-base font-semibold text-neutral-300 mb-3">
          정통 지표
        </h2>
        <div className="space-y-3">
          {traditional.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold text-neutral-300 mb-3">
          밈 지표
        </h2>
        <div className="space-y-3">
          {meme.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </div>
      </section>

      <p className="text-xs text-neutral-600 text-center pt-4">
        이 서비스는 정보 제공 목적이며, 투자 조언이나 매수·매도 추천이 아닙니다.
      </p>
    </main>
  );
}
