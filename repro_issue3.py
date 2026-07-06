"""repro_issue3.py — verify Issue #3 fix against real seed data"""

from app import create_app, db
from models import Song, song_tags
from services.search_service import search_songs

app = create_app()   # uses the real sqlite:///mixtape.db

with app.app_context():
    # Build the same query search_songs now uses, to check the raw SQL row count
    query = db.session.query(Song).filter(
        db.or_(
            Song.title.ilike("%Crown%"),
            Song.artist.ilike("%Crown%"),
        )
    )
    print("Raw SQL row count (count):", query.count())
    print("Mapped ORM object count (all):", len(query.all()))

    # Call the actual service function to confirm the result
    results = search_songs("Crown")
    print(f"\nsearch_songs returned {len(results)} result(s):")
    for r in results:
        print(f"  - {r['title']} / {r['artist']} (id={r['id']}, tags={r['tags']})")
