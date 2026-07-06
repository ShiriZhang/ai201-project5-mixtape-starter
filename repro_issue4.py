"""repro_issue4.py — 手动复现脚本，验证 Issue #4"""

from app import create_app, db
from models import User, Song, Playlist
from services.notification_service import rate_song, add_to_playlist, get_notifications

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    # 造两个用户：一个分享歌的人，一个去互动的人
    sharer = User(username="sharer", email="sharer@example.com")
    rater = User(username="rater", email="rater@example.com")
    db.session.add_all([sharer, rater])
    db.session.commit()

    song = Song(title="Test Song", artist="Test Artist", shared_by=sharer.id)
    db.session.add(song)
    db.session.commit()

    print("评分前，分享者的通知:", get_notifications(sharer.id))

    rate_song(rater.id, song.id, 5)

    print("评分后，分享者的通知:", get_notifications(sharer.id))

    # 对比组：加playlist是否会通知
    playlist = Playlist(name="Test Playlist", created_by=rater.id)
    db.session.add(playlist)
    db.session.commit()

    # add_to_playlist(playlist.id, song.id, rater.id)

    print("加入playlist后，分享者的通知:", get_notifications(sharer.id))
