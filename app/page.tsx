import { getLatestDailyScore, getPublicIndicators } from "@/lib/data";
import type { IndicatorWithLatestValue } from "@/lib/data";

// 지표는 하루 단위(GitHub Actions 배치)로 갱신되므로, 빌드 시점에 정적으로
// 굳어버리지 않도록 매 요청마다 서버에서 새로 조회한다.
export const dynamic = "force-dynamic";

function IndicatorCard({ indicator }: { indicator: IndicatorWithLatestValue }) {
  const hasValue = indicator.latest !== null;
  const isHit = (indicator.latest?.normalized_score ?? 0) >= 100;

  return (
    <div className="border rounded p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{indicator.name}</h3>
        {hasValue && (
          <span
            className={
              isHit
                ? "text-xs font-bold text-red-600"
                : "text-xs text-gray-400"
            }
          >
            {isHit ? "● Hit" : "○"}
          </span>
        )}
      </div>
      <p className="text-2xl mt-1">
        {hasValue ? indicator.latest!.raw_value : "-"}
        <span className="text-sm text-gray-500 ml-1">{indicator.unit}</span>
      </p>
      <p className="text-sm text-gray-500 mt-2">{indicator.description_beginner}</p>
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
    <main className="max-w-2xl mx-auto p-6 space-y-10">
      <section className="border rounded p-6 text-center">
        {dailyScore ? (
          <>
            <p className="text-sm text-gray-500">{dailyScore.date} 기준</p>
            <p className="text-5xl font-bold mt-2">{dailyScore.score}%</p>
            <span className="inline-block mt-3 px-3 py-1 rounded-full bg-gray-100 text-sm font-medium">
              {dailyScore.stage}
            </span>
          </>
        ) : (
          <p className="text-gray-500">아직 계산된 스코어가 없습니다.</p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">정통 지표</h2>
        <div className="space-y-3">
          {traditional.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">밈 지표</h2>
        <div className="space-y-3">
          {meme.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </div>
      </section>

      <p className="text-xs text-gray-400 text-center pt-4">
        이 서비스는 정보 제공 목적이며, 투자 조언이나 매수·매도 추천이 아닙니다.
      </p>
    </main>
  );
}
