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
 * "최종 업데이트" 라벨. 파이프라인은 KST 09:00(주 실행)·17:00(재실행)에만 도는데,
 * 실제 완료 시각은 몇 분~몇십 분 늦어질 수 있어(예: 18:19) 그대로 쓰면 헷갈린다.
 * 그래서 updated_at의 KST 시(hour)로 오전/오후 실행을 판별해 "오전 9:00" 또는
 * "오후 5:00"으로 스냅해 표시한다. → "YYYY-MM-DD(요일) 오전 9:00 기준"
 */
export function formatKstUpdate(isoString: string): string {
  const parts = KST_UPDATE_FORMATTER.formatToParts(new Date(isoString));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";

  const weekday = get("weekday").replace("요일", "");
  // 9시와 17시의 중간(13시)을 경계로 오전/오후 실행을 가른다.
  const slot = Number(get("hour")) < 13 ? "오전 9:00" : "오후 5:00";

  return `${get("year")}-${get("month")}-${get("day")}(${weekday}) ${slot} 기준`;
}
