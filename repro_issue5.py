"""repro_issue5.py — 验证 Issue #5"""

from app import create_app, db
from models import User, Song, Playlist, playlist_entries
from services.playlist_service import get_playlist_songs

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    user = User(username="tester", email="tester@example.com")
    db.session.add(user)
    db.session.flush()

    playlist = Playlist(name="Test Playlist", created_by=user.id)
    db.session.add(playlist)
    db.session.flush()

    songs = [
        Song(title=f"Song {i}", artist="Artist", shared_by=user.id)
        for i in range(1, 4)  # 3首歌
    ]
    db.session.add_all(songs)
    db.session.flush()

    for i, song in enumerate(songs):
        db.session.execute(
            playlist_entries.insert().values(
                playlist_id=playlist.id,
                song_id=song.id,
                position=i + 1,
                added_by=user.id,
            )
        )
    db.session.commit()

    result = get_playlist_songs(playlist.id)
    print(f"playlist里放了 {len(songs)} 首歌，get_playlist_songs() 返回了 {len(result)} 条:")
    for r in result:
        print(f"  - {r['title']}")
