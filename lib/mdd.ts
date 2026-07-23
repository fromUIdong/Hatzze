/**
 * MDD(최대낙폭) 분석 — 순수 계산.
 *
 * 야후 일봉 종가 배열 하나로 낙폭 시계열·역대 낙폭 사건·회복 통계를 낸다.
 * server-only 를 붙이지 않는다(순수 함수라 테스트·재사용이 쉽도록). 데이터 조회는
 * lib/yahoo-history.ts, 화면은 app/mdd 가 맡고 여기는 숫자만 만든다.
 *
 * 기준은 전부 **종가**다. 야후의 close 는 액면분할·감자를 소급 조정한 수정주가라
 * (삼성전자 2018년 50:1 분할이 되감겨 있다) 장기 낙폭이 왜곡되지 않는다. 반면
 * adjclose 는 감자에서 음수가 나오는 등 깨져 있어 쓰지 않는다(SK하이닉스 실측).
 */

export type Bar = { date: string; close: number };

/** 각 시점의 고점 대비 낙폭(%). dd 는 0 이하이고, 새 고점에서 0 이 된다. */
export type DrawdownPoint = { date: string; close: number; dd: number };

/**
 * 고점→저점→회복을 한 사건으로 본 하락 에피소드.
 * depth 는 음수(%), days 는 고점일부터 회복일(미회복이면 마지막일)까지의 달력 일수.
 */
export type Episode = {
  peakDate: string;
  troughDate: string;
  depth: number;
  /** 고점을 회복한 날. 아직 회복 못 했으면 null. */
  recoveryDate: string | null;
  /** 고점→회복(미회복이면 마지막)까지의 달력 일수. */
  days: number;
  /** 고점→저점까지의 달력 일수 — 하락 '속도'(급락형/완만형)를 가른다. */
  troughDays: number;
  recovered: boolean;
};

/**
 * 하락의 '성격' — 얼마나 빠르게 빠졌나. 같은 −30%라도 며칠 만에 급락한 것과
 * 몇 달에 걸쳐 흘러내린 것은 회복 양상이 크게 다르다(급락은 빨리, 완만은 오래).
 */
export type DrawdownCharacter = {
  /** 현재 하락의 고점→저점 달력 일수·깊이. */
  currentTroughDays: number;
  currentTroughDepth: number;
  currentClass: "fast" | "slow";
  /** 과거 급락형(빠른 하락)의 사례 수와 회복 일수 중앙값. 사례 없으면 null. */
  fast: { count: number; medianRecovery: number } | null;
  slow: { count: number; medianRecovery: number } | null;
};

/** 고점→저점이 이 일수 이하면 급락형, 넘으면 완만형. */
const CHARACTER_SPLIT_DAYS = 75;
/** 성격 분석에 넣을 '의미 있는' 하락의 최소 깊이(%). 잔물결은 뺀다. */
const CHARACTER_MIN_DEPTH = -15;

export type RecoveryStats = {
  /** 지금과 같거나 더 깊었던 사건 수(진행 중 포함). */
  similarCount: number;
  recoveredCount: number;
  unrecoveredCount: number;
  /** 회복한 사건들의 달력 일수. 회복 사례가 없으면 null. */
  minDays: number | null;
  medianDays: number | null;
  maxDays: number | null;
};

export type MddAnalysis = {
  firstDate: string;
  asOf: string;
  tradingDays: number;
  price: number;
  ath: number;
  athDate: string;
  currentDd: number;
  /** 조회 구간에서 지금보다 더 깊게 빠져 있던 날의 비율(%). */
  deeperThanNowPct: number;
  mdd: number;
  mddDate: string;
  underwater: DrawdownPoint[];
  recovery: RecoveryStats | null;
  character: DrawdownCharacter | null;
  topDrawdowns: Episode[];
};

/** 종가 배열 → 시점별 고점 대비 낙폭. */
export function drawdownSeries(bars: Bar[]): DrawdownPoint[] {
  const out: DrawdownPoint[] = [];
  let peak = -Infinity;
  for (const b of bars) {
    if (b.close > peak) peak = b.close;
    out.push({ date: b.date, close: b.close, dd: (b.close / peak - 1) * 100 });
  }
  return out;
}

/**
 * 고점에서 시작해 그 고점을 되찾을 때까지를 한 에피소드로 끊는다.
 *
 * 새 고점을 만나면 직전 하락 국면을 '회복됨'으로 종료하고, 마지막까지 고점을 못
 * 넘겼으면 '미회복'(진행 중)으로 남긴다. 진행 중 사건은 recovered=false 라 회복
 * 통계(회복일수)에서 빠진다 — 아직 안 끝난 하락을 "N일 만에 회복"으로 세면 평균이
 * 부당하게 짧아진다.
 */
export function episodes(bars: Bar[]): Episode[] {
  const eps: Episode[] = [];
  if (bars.length === 0) return eps;

  let peak = bars[0].close;
  let peakDate = bars[0].date;
  let trough = bars[0].close;
  let troughDate = bars[0].date;

  const daysBetween = (a: string, b: string) =>
    Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);

  for (const b of bars) {
    if (b.close >= peak) {
      if (trough < peak) {
        eps.push({
          peakDate,
          troughDate,
          depth: (trough / peak - 1) * 100,
          recoveryDate: b.date,
          days: daysBetween(peakDate, b.date),
          troughDays: daysBetween(peakDate, troughDate),
          recovered: true,
        });
      }
      peak = b.close;
      peakDate = b.date;
      trough = b.close;
      troughDate = b.date;
    } else if (b.close < trough) {
      trough = b.close;
      troughDate = b.date;
    }
  }

  if (trough < peak) {
    eps.push({
      peakDate,
      troughDate,
      depth: (trough / peak - 1) * 100,
      recoveryDate: null,
      days: daysBetween(peakDate, bars[bars.length - 1].date),
      troughDays: daysBetween(peakDate, troughDate),
      recovered: false,
    });
  }

  return eps;
}

function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

/**
 * 지금과 같거나 더 깊었던 사건들의 회복 통계.
 * currentDd 는 음수(%). 표본이 적으므로 화면은 평균이 아니라 범위로 보여준다.
 */
function recoveryStats(eps: Episode[], currentDd: number): RecoveryStats | null {
  // 지금이 사실상 신고가면(≈0) '비슷한 깊이'라는 개념이 성립하지 않는다.
  if (currentDd > -1) return null;
  const similar = eps.filter((e) => e.depth <= currentDd);
  if (similar.length === 0) {
    return { similarCount: 0, recoveredCount: 0, unrecoveredCount: 0, minDays: null, medianDays: null, maxDays: null };
  }
  const recovered = similar.filter((e) => e.recovered);
  const days = recovered.map((e) => e.days);
  return {
    similarCount: similar.length,
    recoveredCount: recovered.length,
    unrecoveredCount: similar.length - recovered.length,
    minDays: days.length ? Math.min(...days) : null,
    medianDays: days.length ? median(days) : null,
    maxDays: days.length ? Math.max(...days) : null,
  };
}

/**
 * 하락의 성격(급락형/완만형)과 성격별 회복 통계.
 * currentDd 는 음수(%). 지금 하락이 뚜렷하지 않거나(−8% 초과) 표본이 얇으면 null.
 */
function drawdownCharacter(eps: Episode[], currentDd: number): DrawdownCharacter | null {
  if (currentDd > -8) return null;
  // 진행 중(미회복) 마지막 사건이 곧 '현재 하락'이다.
  const current = eps.length && !eps[eps.length - 1].recovered ? eps[eps.length - 1] : null;
  if (!current) return null;

  // 표본이 얇으면 급락/완만 비교는 생략하되(버킷 null), 섹션 자체는 살려 둔다 —
  // 현재 하락의 성격(급락/완만)만이라도 보여주고, 화면이 "기간을 넓히라"고 안내한다.
  const meaningful = eps.filter((e) => e.recovered && e.depth <= CHARACTER_MIN_DEPTH);
  const enough = meaningful.length >= 3;

  const bucket = (fast: boolean) => {
    if (!enough) return null;
    const days = meaningful.filter((e) => (e.troughDays <= CHARACTER_SPLIT_DAYS) === fast).map((e) => e.days);
    return days.length ? { count: days.length, medianRecovery: median(days) } : null;
  };

  return {
    currentTroughDays: current.troughDays,
    currentTroughDepth: current.depth,
    currentClass: current.troughDays <= CHARACTER_SPLIT_DAYS ? "fast" : "slow",
    fast: bucket(true),
    slow: bucket(false),
  };
}

/** 낙폭 시계열을 최대 maxPoints 개로 균등 다운샘플한다(마지막 점은 항상 포함). */
function downsample(series: DrawdownPoint[], maxPoints: number): DrawdownPoint[] {
  if (series.length <= maxPoints) return series;
  const step = Math.ceil(series.length / maxPoints);
  const out: DrawdownPoint[] = [];
  for (let i = 0; i < series.length; i += step) out.push(series[i]);
  const last = series[series.length - 1];
  if (out[out.length - 1] !== last) out.push(last);
  return out;
}

/** 종가 시계열 하나를 받아 화면에 필요한 모든 수치를 낸다. */
export function analyzeDrawdown(bars: Bar[]): MddAnalysis | null {
  if (bars.length < 2) return null;

  const ds = drawdownSeries(bars);
  const last = ds[ds.length - 1];

  let ath = -Infinity;
  let athDate = bars[0].date;
  let mdd = 0;
  let mddDate = bars[0].date;
  for (const p of ds) {
    if (p.close > ath) {
      ath = p.close;
      athDate = p.date;
    }
    if (p.dd < mdd) {
      mdd = p.dd;
      mddDate = p.date;
    }
  }

  const deeperDays = ds.filter((p) => p.dd <= last.dd).length;
  const eps = episodes(bars);

  return {
    firstDate: bars[0].date,
    asOf: last.date,
    tradingDays: bars.length,
    price: last.close,
    ath,
    athDate,
    currentDd: last.dd,
    deeperThanNowPct: (deeperDays / ds.length) * 100,
    mdd,
    mddDate,
    underwater: downsample(ds, 220),
    recovery: recoveryStats(eps, last.dd),
    character: drawdownCharacter(eps, last.dd),
    topDrawdowns: [...eps].sort((a, b) => a.depth - b.depth).slice(0, 5),
  };
}
