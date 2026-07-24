/**
 * 지표 값의 크기에 따라 소수점 표시를 자동으로 결정한다.
 * - 절댓값 10 미만: 소수점 둘째자리까지 (작은 숫자는 소수점 변화가 의미 있음)
 * - 절댓값 10 이상: 정수로 표시 (0 방향으로 버림 — 예: 212.96 -> 212, -20.49 -> -20)
 * - unit이 "억원"이고 절댓값 10000 이상(=1조 이상)이면 "조원" 단위로 전환
 *
 * 특정 지표를 하드코딩하지 않고 값의 크기만 보고 판단하므로, 새로 추가되는
 * 지표에도 코드 수정 없이 그대로 적용된다.
 */
export function formatIndicatorValue(
  value: number,
  unit: string,
): { display: string; displayUnit: string } {
  if (unit === "억원" && Math.abs(value) >= 10000) {
    const jo = value / 10000;
    return {
      display: jo.toLocaleString("ko-KR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }),
      displayUnit: "조원",
    };
  }

  if (unit === "억원") {
    return {
      display: Math.trunc(value).toLocaleString("ko-KR"),
      displayUnit: unit,
    };
  }

  const display =
    Math.abs(value) < 10
      ? value.toLocaleString("ko-KR", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : Math.trunc(value).toLocaleString("ko-KR");

  return { display, displayUnit: unit };
}

const KST_UPDATE_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  weekday: "short",
  hour: "2-digit",
  hourCycle: "h23",
});

/**
 * 정기 실행의 **표기용 완료 시각**(KST). cron 발화 시각이 아니라 완료를 여기에 맞춰 스냅한다.
 * 아침 완료 ~11:00, 오후 완료 ~20:00(7시로 스냅) — .github/workflows/daily-update.yml 의
 * '발화+큐지연' 설계 참고.
 */
const SCHEDULED_HOURS_KST = [11, 19];
/** 예정 시각에서 이만큼 안에 끝났으면 "예정대로 돌았다"고 보고 정각으로 스냅한다. */
const SCHEDULE_SLACK_HOURS = 3;

/**
 * "최종 업데이트" 라벨.
 *
 * 파이프라인 완료가 KST 11:00·17:00 근처가 되도록 발화 시각을 설계했다(cron 은 그보다
 * 앞서 발화하고 GitHub 예약 큐 지연 90~150분이 실행을 그 시각으로 밀어준다 — 자세한 건
 * 워크플로 cron 주석). 완료는 그래도 날마다 흔들리므로, 예정 시각 ±3시간 안이면 그 정각으로
 * 스냅하고(정기 실행의 깔끔함 유지), 벗어난 실행(수동·재시도)은 실제 시각을 적어 거짓말을
 * 막는다 — 예전엔 무조건 정각 스냅이라 KST 23:28 에 끝난 실행이 "오후 5:00 기준"으로 표시됐다.
 */
export function formatKstUpdate(isoString: string): string {
  const parts = KST_UPDATE_FORMATTER.formatToParts(new Date(isoString));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";

  const weekday = get("weekday").replace("요일", "");
  const hour = Number(get("hour"));

  const scheduled = SCHEDULED_HOURS_KST.find((h) => Math.abs(hour - h) <= SCHEDULE_SLACK_HOURS);
  const time =
    scheduled !== undefined
      ? `${scheduled < 12 ? "오전" : "오후"} ${scheduled % 12 || 12}:00`
      : `${hour < 12 ? "오전" : "오후"} ${hour % 12 || 12}시경`;

  return `${get("year")}-${get("month")}-${get("day")}(${weekday}) ${time} 기준`;
}

/**
 * 툴팁·미니차트 축의 짧은 날짜 표기. "YYYY-MM-DD" 또는 "MM-DD" 를 "M/D" 로 바꾼다.
 * 예: "2026-07-16" → "7/16", "07-16" → "7/16". 툴팁마다 date.slice(5) 를 흩뿌리지
 * 않고 여기 하나로 모아, 표기(하이픈↔슬래시)를 한 곳에서 바꾼다.
 */
export function shortDate(iso: string): string {
  const [, mm, dd] = iso.length > 5 ? iso.split("-") : ["", ...iso.split("-")];
  return `${Number(mm)}/${Number(dd)}`;
}

/**
 * 억 단위 금액을 "1조 2,929억"처럼 조와 억을 함께 읽는 형태로 만든다.
 *
 * formatIndicatorValue 는 1조를 넘으면 "1.3조원"으로 반올림하는데, 순매수처럼
 * 끝자리까지 의미가 있는 금액은 그렇게 뭉개면 규모 감각이 오히려 흐려진다.
 * "12,929억"은 한눈에 안 읽히고 "1.3조원"은 정보가 날아가므로 둘을 함께 쓴다.
 */
export function formatEokMixed(eok: number): string {
  const abs = Math.abs(Math.round(eok));
  const sign = eok < 0 ? "-" : "";
  if (abs < 10000) return `${sign}${abs.toLocaleString("ko-KR")}억`;
  const jo = Math.floor(abs / 10000);
  const rest = abs % 10000;
  if (rest === 0) return `${sign}${jo.toLocaleString("ko-KR")}조`;
  return `${sign}${jo.toLocaleString("ko-KR")}조 ${rest.toLocaleString("ko-KR")}억`;
}

/**
 * 낙관도(중립 제외한 낙관 비중 %) → 라벨 + 색 톤.
 *
 * 카더라 리포트의 생태계 센티먼트와 시장 브리핑의 감성 카드(디시·뉴스)가 **같은 구간·같은
 * 말**을 쓰도록 여기 하나로 모아 둔다. 두 화면이 같은 성격의 수치를 다른 말로 부르면
 * 사용자가 매번 다시 배워야 한다.
 *
 * 라벨과 색을 한 번에 돌려주는 게 핵심이다 — 예전엔 라벨만 구간으로 정하고 색은 화면에서
 * 낙관색으로 고정해 둬서, 중립 구간의 위쪽(59%)이 "중립"이라고 적힌 채 낙관색으로 칠해지는
 * 모순이 있었다.
 */
export function sentimentTone(optimismPct: number): {
  label: string;
  tone: "hot" | "neutral" | "cold";
} {
  // 구간: 비관 0~40 · 중립 41~59 · 낙관 60~100.
  if (optimismPct >= 60) return { label: "낙관 우세", tone: "hot" };
  if (optimismPct >= 41) return { label: "중립", tone: "neutral" };
  return { label: "비관 우세", tone: "cold" };
}
