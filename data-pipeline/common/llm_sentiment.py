"""짧은 글 제목의 시장 감성 분류 — 디시 갤러리·뉴스 헤드라인이 함께 쓴다.

**왜 키워드 매칭을 버렸나.** 예전엔 config/sentiment_keywords.py 의 긍정/부정 단어를
제목에 부분 문자열로 대조했다. 실측하니 디시 갤러리 제목 2,987건 중 **2,840건(95%)이
어느 키워드에도 안 걸려 중립** 처리됐다 — 지표가 사실상 5% 표본으로 계산되고 있었다.
걸러진 제목들은 사람이 보면 감성이 뚜렷했다:
    "양닉 음전으로 뚜벅뚜벅ㅋㅋㅋ"  "롱숭이 계좌 정밀타격ㅋㅋ"  "숏신사 롱신사 무승부"
갤러리 은어는 계속 새로 생기므로 사전을 키우는 방식으로는 못 따라간다.

분류는 "글쓴이가 **시장 방향**을 어떻게 보는가"다. 글쓴이 개인의 손익이 아니라
시장에 대한 낙관/비관을 본다 — 남의 손실을 비웃는 글도 '시장이 빠진다'는 쪽이면
negative 다.

배치 크기가 telegram 분류기(15)보다 훨씬 큰 이유: 여기 입력은 한 줄짜리 제목이라
한 건당 토큰이 20 안팎이다. 크게 묶어야 하루 3천 건을 적은 호출로 끝낼 수 있다.
"""

from __future__ import annotations

import json
import os
import time

from anthropic import Anthropic

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 80
MAX_RETRIES = 3
RETRY_BASE_DELAY_SEC = 2
TITLE_CAP = 120  # 제목이 이보다 길면 잘라 넣는다(비용·토큰 방어)

_SLANG = """\
[커뮤니티 은어 참고]
- 롱/숏: 상승/하락 베팅. "롱숭이"·"숏쟁이"는 각 진영을 낮춰 부르는 말.
- 음전: 상승하던 게 하락 전환. 양전: 그 반대.
- 양닉/미장: 미국 증시·나스닥. 국장: 국내 증시.
- 존버: 손실을 버티며 보유. 물렸다: 고점에 사서 손실 중.
- 종베: 종가 베팅. 따상: 공모주 상장 첫날 급등.
남을 조롱하는 글이라도 **시장 방향**으로 판단하세요 —
"롱숭이 계좌 정밀타격ㅋㅋ"는 시장이 빠졌다는 뜻이라 negative 입니다."""

_SYSTEM_TEMPLATE = """\
당신은 한국 주식 {source}의 제목을 분류하는 분석기입니다.
각 제목이 **주식시장 방향을 어떻게 보는지**를 판단해 JSON으로만 답합니다.

- positive: 상승·호재·낙관. 오른다, 좋다, 기대된다, 사자는 분위기.
- negative: 하락·악재·비관. 빠진다, 나쁘다, 위험하다, 손실·공포 분위기.
- neutral: 방향성이 없음. 단순 사실 전달, 일정·공지, 질문, 잡담, 광고,
  방향을 알 수 없는 짧은 말.

판단 기준은 **글쓴이 개인의 손익이 아니라 시장 방향**입니다.
애매하면 neutral 로 두세요 — 억지로 한쪽에 넣지 마세요.
{extra}
[입력] 각 제목은 "### <번호>" 줄로 시작합니다.
[출력] 모든 번호에 대해 정확히 하나씩, 입력 순서대로 결과를 만드세요."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "neutral", "negative"],
                    },
                },
                "required": ["n", "sentiment"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


class LlmUnavailableError(Exception):
    """API 키가 없거나 재시도까지 실패했을 때. 호출부가 그날 계산을 건너뛰게 한다."""


def _client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LlmUnavailableError("ANTHROPIC_API_KEY 가 없습니다")
    return Anthropic(api_key=key)


def _system(source: str, slang: bool) -> str:
    return _SYSTEM_TEMPLATE.format(source=source, extra=(_SLANG + "\n\n") if slang else "")


def _classify_batch(client: Anthropic, batch: list[str], system: str) -> dict[int, str]:
    prompt = "\n\n".join(
        f"### {i}\n{t[:TITLE_CAP]}" for i, t in enumerate(batch, start=1)
    )
    last: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                # 분류는 매번 같은 답이 나와야 한다. 기본값(1.0)으로 두면 편차가 큰데,
                # 2026-07-21 실측에서 **완전히 동일한 제목 2,987건**을 몇 분 간격으로 두 번
                # 분류했더니 낙관도가 36% ↔ 48%로 갈렸다. 우리 구간표(비관 0~40 / 중립
                # 41~59)를 넘나드는 폭이라 입력이 그대로인데 화면 라벨이 뒤집힌다 —
                # "어제보다 나빠졌다"가 시장 변화인지 분류 흔들림인지 구분할 수 없게 된다.
                # 0으로 두면 편차가 크게 줄어든다(완전히 0이 되지는 않는다).
                temperature=0,
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            )
            raw = "".join(b.text for b in resp.content if b.type == "text")
            return {int(r["n"]): r["sentiment"] for r in json.loads(raw).get("results", [])}
        except Exception as e:  # noqa: BLE001 — 네트워크·파싱 모두 재시도 대상
            last = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY_SEC * attempt)
    raise LlmUnavailableError(f"배치 분류가 {MAX_RETRIES}번 모두 실패했습니다: {last}")


def classify_titles(titles: list[str], *, source: str, slang: bool = False) -> list[str]:
    """제목마다 "positive"/"negative"/"neutral" 을 돌려준다(입력과 같은 순서·길이).

    응답에 빠진 번호는 neutral 로 채운다 — 한 건이 비었다고 그날 전체를 버리는 것보다
    낫고, 중립은 점수에 영향을 주지 않는 안전한 기본값이다.
    """
    if not titles:
        return []
    client = _client()
    system = _system(source, slang)
    out: list[str] = []
    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start : start + BATCH_SIZE]
        got = _classify_batch(client, batch, system)
        out.extend(got.get(i, "neutral") for i in range(1, len(batch) + 1))
    return out
