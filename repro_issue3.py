"""repro_issue3.py — 用真实seed数据验证 Issue #3"""

from app import create_app
from services.search_service import search_songs

app = create_app()   # 用真实的 sqlite:///mixtape.db

with app.app_context():
    # "Crown Heights Anthem" by "Borough Kings" 是seed_data.py里3-tag歌曲之一
    results = search_songs("Crown")
    print(f"返回了 {len(results)} 条结果:")
    for r in results:
        print(f"  - {r['title']} / {r['artist']} (id={r['id']}, tags={r['tags']})")
