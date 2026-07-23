"""지표 행 보장 — 모든 fetch 스크립트가 공유한다.

예전엔 이 함수가 25개 스크립트에 복붙돼 있었고, 구현이 6종으로 갈라져 있었다.
그중 5개만 이미 있는 행의 메타데이터를 UPDATE했고 **나머지 20개는 삽입만** 했다.
그래서 그 20개는 스크립트의 INDICATOR_META(이름·설명·단위)를 고쳐도 DB에 영영
반영되지 않았다 — 실제로 put_call_ratio의 unit이 코드 "배" / DB "" 로 어긋나
있었다(옵션 API 승인 전 손으로 넣은 행이 남아 있었기 때문).

그래서 여기 하나로 두고 **코드를 소스 오브 트루스로** 만든다: 행이 있으면
메타데이터를 덮어쓰고, 없으면 넣는다.
"""

from __future__ import annotations


def ensure_indicator(client, meta: dict) -> str:
    """slug 로 지표 행을 찾아 없으면 만들고, 있으면 메타데이터를 코드 기준으로 맞춘다.

    **meta 에 담긴 키만 덮어쓴다.** 그래서 무엇을 META 에 넣느냐가 곧 "코드가 관리하는
    필드"의 정의가 된다. 지금 기준은 이렇다:

    - name·headline·description_beginner·unit·category — 항상 META 에 둔다(코드가 관리)
    - is_public — 내부용 원본(kospi_close_raw 등)처럼 **코드가 성격상 확정하는** 지표만
      META 에 넣는다. 나머지는 운영자가 DB 에서 정하므로 넣지 않는다.
    - direction — 점수 계산은 config/indicator_thresholds.py 를 보지만, 카드의 "이하/이상"
      표기는 DB 컬럼을 보므로 둘을 맞춰야 하는 지표만 META 에 넣는다(put_call_ratio).
    - weight — **META 에 넣지 않는다.** 가중치의 소스 오브 트루스는
      config/indicator_weights.py 이고, calculate_score 가 실행마다 DB 를 그 값으로
      동기화한다. META 에도 두면 두 곳이 서로 덮어써 낡은 값이 되살아난다
      (2026-07-23 이전에 4개 스크립트가 그러고 있었다).

    반환: indicators.id
    """
    slug = meta["slug"]
    existing = client.table("indicators").select("id").eq("slug", slug).execute()
    if existing.data:
        indicator_id = existing.data[0]["id"]
        updates = {k: v for k, v in meta.items() if k != "slug"}
        if updates:
            client.table("indicators").update(updates).eq("id", indicator_id).execute()
        return indicator_id
    return client.table("indicators").insert(meta).execute().data[0]["id"]
