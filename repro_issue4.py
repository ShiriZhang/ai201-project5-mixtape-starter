"""repro_issue4.py — verify Issue #4"""

from app import create_app, db
from models import User, Song, Playlist
from services.notification_service import rate_song, add_to_playlist, get_notifications

app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

with app.app_context():
    db.create_all()

    # create a user to share a song and another user to rate it
    sharer = User(username="sharer", email="sharer@example.com")
    rater = User(username="rater", email="rater@example.com")
    db.session.add_all([sharer, rater])
    db.session.commit()

    song = Song(title="Test Song", artist="Test Artist", shared_by=sharer.id)
    db.session.add(song)
    db.session.commit()

    print("Notifications before rating:", get_notifications(sharer.id))

    rate_song(rater.id, song.id, 5)

    print("Notifications after rating:", get_notifications(sharer.id))

    # compare the rate song notification with add to playlist notification
    playlist = Playlist(name="Test Playlist", created_by=rater.id)
    db.session.add(playlist)
    db.session.commit()

    # add_to_playlist(playlist.id, song.id, rater.id)

    print("Notifications after adding to playlist:", get_notifications(sharer.id))
