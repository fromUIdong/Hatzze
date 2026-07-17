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

const KST_DATETIME_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const KST_DATE_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  weekday: "short",
});

/**
 * 날짜 문자열("YYYY-MM-DD")을 KST 기준 "YYYY-MM-DD(요일)"로 표시한다.
 * 데일리 스코어는 매일 아침(KST 09:00) 갱신되는 하루 단위 스냅샷이라, 정확한 갱신
 * 시각(updated_at)의 분 단위 변동 대신 "그 날짜 + 오전 9시" 라벨을 쓰기 위한 포맷.
 * (오후 fallback 재실행이 돌아 updated_at이 늦어져도 표시는 흔들리지 않게 한다.)
 */
export function formatKstDate(dateStr: string): string {
  // KST 자정으로 고정해 파싱해야 요일/날짜가 달력 날짜와 어긋나지 않는다.
  const parts = KST_DATE_FORMATTER.formatToParts(new Date(`${dateStr}T00:00:00+09:00`));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  const weekday = get("weekday").replace("요일", "");
  return `${get("year")}-${get("month")}-${get("day")}(${weekday})`;
}

/**
 * ISO 타임스탬프를 한국시간(KST) 기준 "YYYY-MM-DD(요일) HH:MM 기준" 형식으로 표시한다.
 */
export function formatKstDateTime(isoString: string): string {
  const parts = KST_DATETIME_FORMATTER.formatToParts(new Date(isoString));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";

  const year = get("year");
  const month = get("month");
  const day = get("day");
  const weekday = get("weekday").replace("요일", "");
  const hour = get("hour");
  const minute = get("minute");

  return `${year}-${month}-${day}(${weekday}) ${hour}:${minute} 기준`;
}
