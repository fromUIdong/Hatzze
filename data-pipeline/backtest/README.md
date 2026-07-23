# backtest — 지표 눈금·가중치 검증

`docs/indicator-audit-2026-07-23.md`의 모든 숫자를 만든 스크립트다.
`engine.py`가 `scripts/calculate_score.compute_progress`를 **그대로 import** 하므로,
`config/indicator_thresholds.py`·`indicator_weights.py`를 고친 뒤 다시 돌리면
같은 표가 새 설정 기준으로 나온다.

## 실행

```bash
cd data-pipeline && .venv/bin/python backtest/dump_data.py
```

먼저 `dump_data.py`로 Supabase 전체를 이 폴더에 JSON으로 내려받는다(1회).
그 다음은 순서 무관하게 돌릴 수 있다 — 단 `verify.py`는 `decomp.py`가 만든
`solo.pkl`이 필요하다.

| 스크립트 | 내용 | 문서 대응 |
|---|---|---|
| `dump_data.py` | `indicator_values` 5,580행 + 지표 메타 + `daily_score` 덤프 | §1-1 |
| `engine.py` | progress 시계열 재현, 짧은 히스토리 3개 재구성, 코스피 정답지 | §1 |
| `validate.py`* | 재구성 검증, 국소 고점/저점 추출 | §1-1, §1-3 |
| `analyze.py` | 지표별 분포·상관·이벤트 정렬 + 블록 부트스트랩 신뢰구간 | §2-1, §2-2 |
| `dist.py` | raw 분위수 vs 현재 눈금 위치 | §2-1 |
| `compose.py` | 종합점수 재구성, 구조적 하한, VKOSPI 스케일 점검 | §0-1, §2-1 |
| `decomp.py` | 고점/저점 기여 분해, 지표 단독 성적(`solo.pkl` 생성) | §2-3 |
| `probe.py` | 상대창 맹점·역방향 지표 원인 규명 | §3-1, §3-3 |
| `recal.py` | 권고 눈금 산출(p20→25, p88→75) | §4-1 |
| `final.py` | VKOSPI·high_gap·거래대금 대안 튜닝 | §3-2, §4-2 |
| `short.py` | 변동성 위험프리미엄 검증 + 단기 히스토리 지표 권고 | §3-2, §4-1 |
| `table.py` | 반올림한 권고 눈금 재검증 | §4-1 |
| `verify.py` | 문서에 적은 숫자 그대로 4개 조합 재계산 | §4-4 |
| `ceiling.py` | "ceiling이 빡센가" 가설 검증 + 무상관 평균의 구조적 압축 | §7-1, §7-2 |
| `lift.py` | 고점 판독을 올리는 네 방법 비교(ceiling/재척도/상위-k/혼합) | §7-3 |
| `target.py` · `minimal.py` | 요구조건(고점 70+ / 저점 저온) 역산, 기계장치 최소화 | §7-4 |
| `anchors.py` | 재척도 앵커 상수 확정 | §7-3 |
| `pctmap.py` | 백분위 앵커 매핑(`percentile_from_anchors` 패턴) | §7-3, §7-4 |
| `menu.py` | 최종 7개 조합 비교 + 월별 서사 | §7-4, §7-5 |
| `plan4.py` | ④안 확정 구성(가중치·눈금·거래대금·앵커)과 백테스트 | §8-1, §8-2 |
| `improve4.py` | ④ 개선 1차 — 코스닥 교체·풋콜 반전·평활·앵커·좌표하강 | §8-3, §8-5 |
| `improve4b.py` | ④ 개선 2차 — 괴리 클램프 제거·VKOSPI 제외, ④＋ 확정 | §8-3, §8-4 |
| `peakwin.py` | 고점 '기간' 정의별 달성도 + 고점에서 발목 잡는 지표 분해 | §9-1 |
| `plus2.py` | 빠진 축(상승 속도) 후보 비교와 가중치 탐색 | §9-2, §9-3 |
| `robust.py` | 속도 축 과적합 점검 — 반기 분할·블록 부트스트랩·leave-one-out | §9-2, §9-3 |
| `final4pp.py` | ④＋＋ 확정안 전면 검증 | §9-4, §9-5 |
| `prodanchor.py` | **운영(26개) 기준 앵커 산출** — 코드에 박은 상수가 여기서 나온다 | §9-7 |
| `outer.py` | 앵커 양끝(0·100 지점) 여유분 선택 | §9-7 |

> 눈금·가중치를 다시 바꾸면 `prodanchor.py`를 반드시 다시 돌려 `calculate_score.py`의
> `SCORE_DISPLAY_ANCHORS`를 갱신할 것 — 원점수 분포가 움직이면 앵커가 어긋난다.

\* `validate.py`는 스크래치패드에만 있던 1회성 검증 스크립트라 여기엔 없다.

## 주의

- 덤프 JSON·pkl은 `.gitignore` 처리했다(운영 DB 스냅샷).
- `engine.py`의 `buffett_index`는 **프록시**다(시총 히스토리가 15일뿐이라 코스피 지수로 역산).
- 표본이 사이클 1개라 방향은 믿되 소수점은 믿지 말 것 — 문서 §1-4 참고.

## 9-8 이후 추가 (절대 앵커로 전환)

| 스크립트 | 내용 | 문서 대응 |
|---|---|---|
| `refix.py` | 과적합된 floor 되돌림 + 코스닥 제거 효과 | §9-8 |
| `absolute.py` | **표시 눈금을 원점수 절대 수준에 앵커** — 확정안이 여기서 나온다 | §9-8 |
| `shift.py` | 단기 9개 상수 가정이 만든 편의를 실측으로 보정(−2) | §9-8 |

> `prodanchor.py`(백분위 앵커)는 **더 이상 쓰지 않는다** — 표본이 마니아 해라 그 해의
> 하위 5%가 곧 12점이 되는 문제 때문이다. 기록용으로만 남겨 뒀다.

## 최종 (지금 설정 검증)

| 스크립트 | 내용 |
|---|---|
| `current.py` | **config·calculate_score 상수를 그대로 import** 해 지금 설정의 성적을 낸다. 눈금/가중치를 바꾸면 이것만 다시 돌리면 된다 |

```bash
cd data-pipeline && .venv/bin/python backtest/dump_data.py && .venv/bin/python backtest/current.py
```

결과는 `docs/indicator-changes-2026-07-23.md` §5 에 정리돼 있다.
