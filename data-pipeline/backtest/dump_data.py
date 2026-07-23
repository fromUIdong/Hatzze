"""indicator_values 전체 + 지표 메타를 스크래치패드 JSON으로 덤프."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.supabase_client import get_client  # noqa: E402

OUT = Path(__file__).parent

c = get_client()

inds = c.table("indicators").select("id,slug,name,weight,category,is_public,direction").execute().data
by_id = {r["id"]: r["slug"] for r in inds}
print(f"indicators: {len(inds)}")

rows = []
start = 0
while True:
    page = (
        c.table("indicator_values")
        .select("indicator_id,date,raw_value,normalized_score,details")
        .order("date")
        .range(start, start + 999)
        .execute()
        .data
    )
    if not page:
        break
    rows += page
    start += 1000
    print(f"  ...{len(rows)}")

for r in rows:
    r["slug"] = by_id.get(r.pop("indicator_id"), "?")

print(f"indicator_values: {len(rows)}")

ds = c.table("daily_score").select("date,score,stage").order("date").execute().data
print(f"daily_score: {len(ds)}")

(OUT / "indicators.json").write_text(json.dumps(inds, ensure_ascii=False))
(OUT / "values.json").write_text(json.dumps(rows, ensure_ascii=False))
(OUT / "daily_score.json").write_text(json.dumps(ds, ensure_ascii=False))

from collections import Counter  # noqa: E402

cnt = Counter(r["slug"] for r in rows)
for slug, n in sorted(cnt.items(), key=lambda x: -x[1]):
    dates = [r["date"] for r in rows if r["slug"] == slug]
    print(f"{slug:34} n={n:5}  {min(dates)} ~ {max(dates)}")
