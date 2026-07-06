"""repro_issue2.py — verify the RECENT_THRESHOLD fix (30 minutes)"""

from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    me = User(username="me", email="me@example.com")
    friend_old = User(username="friend_old", email="fo@example.com")
    friend_recent = User(username="friend_recent", email="fr@example.com")
    db.session.add_all([me, friend_old, friend_recent])
    db.session.flush()

    for f in (friend_old, friend_recent):
        db.session.execute(friendships.insert().values(user_id=me.id, friend_id=f.id))
        db.session.execute(friendships.insert().values(user_id=f.id, friend_id=me.id))

    song_old = Song(title="Old Song", artist="X", shared_by=friend_old.id)
    song_recent = Song(title="Recent Song", artist="X", shared_by=friend_recent.id)
    db.session.add_all([song_old, song_recent])
    db.session.flush()

    now = datetime.now(timezone.utc)

    # friend_old: only event is 10 hours ago — should NOT show under a 30-minute window
    db.session.add(ListeningEvent(
        user_id=friend_old.id, song_id=song_old.id,
        listened_at=now - timedelta(hours=10),
    ))
    # friend_recent: only event is 15 minutes ago — should still show
    db.session.add(ListeningEvent(
        user_id=friend_recent.id, song_id=song_recent.id,
        listened_at=now - timedelta(minutes=15),
    ))
    db.session.commit()

    result = get_friends_listening_now(me.id)
    print(f"Returned {len(result)} result(s):")
    for r in result:
        print(f"  - friend={r['friend']['username']}, listened_at={r['listened_at']}")
