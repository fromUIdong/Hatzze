from supabase import Client, create_client

from .config import SUPABASE_SECRET_KEY, SUPABASE_URL

PAGE_SIZE = 1000  # PostgREST 기본 상한


def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def load_all(db, table: str, columns: str) -> list[dict]:
    """표 전체를 페이지를 이어 받아 읽는다.

    PostgREST는 한 번에 최대 1,000행만 주는데 **에러 없이 조용히 자른다**. 그래서
    행이 그 이상 쌓일 수 있는 표를 그냥 select 하면 뒷부분이 소리 없이 사라진다.
    실제로 코스닥 승인으로 stocks 가 944 → 2,765행이 되자 종목 사전에서 1,765개가
    잘려나갔다(KOSPI만일 땐 944행이라 우연히 안 걸리던 잠복 버그였다).

    **행 수가 1,000을 넘길 수 있는 조회는 반드시 이걸 쓸 것.**
    """
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            db.table(table)
            .select(columns)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data
        )
        if not page:
            break
        rows += page
        start += PAGE_SIZE
    return rows
