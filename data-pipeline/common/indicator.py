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

    meta 에 담긴 키만 덮어쓴다 — is_public·weight·direction 은 META 에 없어서
    DB 값이 그대로 유지된다(가중치는 config/indicator_weights.py, 공개 여부는
    운영자가 DB에서 정하는 값이라 스크립트가 건드리면 안 된다).

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
