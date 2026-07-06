"""repro_issue2.py — 精确测试24小时边界"""

from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    me = User(username="me", email="me@example.com")
    friend_just_inside = User(username="friend_just_inside", email="fi@example.com")
    friend_just_outside = User(username="friend_just_outside", email="fo@example.com")
    db.session.add_all([me, friend_just_inside, friend_just_outside])
    db.session.flush()

    for f in (friend_just_inside, friend_just_outside):
        db.session.execute(friendships.insert().values(user_id=me.id, friend_id=f.id))
        db.session.execute(friendships.insert().values(user_id=f.id, friend_id=me.id))

    song_inside = Song(title="Just Inside", artist="X", shared_by=friend_just_inside.id)
    song_outside = Song(title="Just Outside", artist="X", shared_by=friend_just_outside.id)
    db.session.add_all([song_inside, song_outside])
    db.session.flush()

    now = datetime.now(timezone.utc)

    # 23小时59分钟前 —— 应该在24小时窗口内
    db.session.add(ListeningEvent(
        user_id=friend_just_inside.id, song_id=song_inside.id,
        listened_at=now - timedelta(hours=23, minutes=59),
    ))
    # 24小时1分钟前 —— 应该刚好超出24小时窗口
    db.session.add(ListeningEvent(
        user_id=friend_just_outside.id, song_id=song_outside.id,
        listened_at=now - timedelta(hours=24, minutes=1),
    ))
    db.session.commit()

    result = get_friends_listening_now(me.id)
    print(f"返回了 {len(result)} 条记录:")
    for r in result:
        print(f"  - friend={r['friend']['username']}, song={r['song']['title']}")
