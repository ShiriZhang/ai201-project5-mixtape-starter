# Mixtape Bug Hunt — Submission

## AI Usage
_(填在最后，milestone 4再回来写)_


## Codebase Map

### Main files and their roles

**Models**
- `models.py`: Defines 7 SQLAlchemy models — `User`, `Tag`, `Song`, `ListeningEvent`,
  `Rating`, `Playlist`, `Notification` — plus 3 association tables for many-to-many
  relationships: `friendships` (User↔User), `song_tags` (Song↔Tag), and
  `playlist_entries` (Playlist↔Song). `playlist_entries` isn't a plain join table —
  it carries extra columns (`position`, `added_by`, `added_at`), so a song's place in
  a playlist is stored explicitly rather than inferred from insertion order.

**Routes** (all under `routes/`, each a Flask Blueprint that parses the request and
delegates to a service function — no business logic lives here)
- `routes/songs.py`: search, get song detail, rate a song, log a listening event
- `routes/playlists.py`: create playlist, get playlist detail, get/add songs to a playlist
- `routes/users.py`: get user profile, get streak, get/mark notifications
- `routes/feed.py`: friends-listening-now feed, general activity feed

**Services** (all business logic lives here)
- `services/streak_service.py`: records a listening event and updates the user's
  consecutive-day listening streak (`record_listening_event`, `update_listening_streak`, `get_streak`)
- `services/feed_service.py`: builds the "friends listening now" feed (last 24h,
  deduped to one entry per friend) and a general activity feed (last N events,
  no time filter) — `get_friends_listening_now`, `get_activity_feed`
- `services/search_service.py`: searches songs by title/artist substring match,
  joined against tags — `search_songs`, `get_song`
- `services/notification_service.py`: creates and retrieves notifications —
  `create_notification` (generic), `add_to_playlist` (adds song + notifies original
  sharer), `rate_song` (saves/updates a rating), `get_notifications`, `mark_as_read`
- `services/playlist_service.py`: create playlists, fetch a playlist's songs in
  position order, fetch playlist metadata, list a user's playlists

### Data flow: user rates a song

1. Client sends `POST /songs/<song_id>/rate` with `{user_id, score}` in the body
   (`routes/songs.py:rate`).
2. The route pulls `user_id`/`score` out of the JSON body and calls
   `notification_service.rate_song(user_id, song_id, score)`.
3. `rate_song` validates the score is 1–5, loads the `Song` and `User`, checks
   whether a `Rating` already exists for this (user, song) pair — if yes it updates
   the existing row's score, if no it inserts a new `Rating` row — then commits.
4. It returns the `Rating` instance; the route serializes it with `.to_dict()` and
   responds `201`.

Note: despite living in `notification_service.py`, `rate_song` does **not** create a
`Notification`. Compare with `add_to_playlist` in the same file (used by
`POST /playlists/<id>/songs`), which *does* call `create_notification(...)` after
adding the song — notifying the original sharer if they weren't the one who added it.

### Patterns noticed

- **Routes are thin.** Every route function just parses `request`/JSON, calls exactly
  one service function, and formats the response (`jsonify(...)`, catching `ValueError`
  → 400/404). All actual logic lives in `services/`.
- **Notification creation is inconsistent.** `add_to_playlist` explicitly calls
  `create_notification(...)`; `rate_song`, which lives in the *same file*, doesn't call
  it at all — even though both represent a friend interacting with a song you shared.
  This looks like the mechanism exists but wasn't wired up for every interaction type.
- **IDs are UUID strings, not integers** (`generate_uuid()`), generated in Python
  rather than by the DB.


## Root Cause Analysis

### Issue #1: My listening streak keeps resetting

**How I reproduced it:**
Ran the existing test suite with `pytest tests/test_streaks.py -v` before any fix which failed on `test_streak_increments_on_sunday`.

**How I found the root cause:**
I opened `services/streak_service.py` and read `update_listening_streak`, which decides
whether to increment or reset the streak based on `days_since_last`. The decision logic is:

```python
if days_since_last == 0:
    return
elif days_since_last == 1 and today.weekday() != 6:
    user.listening_streak += 1
else:
    user.listening_streak = 1
```

**The root cause:**
The elif branch that increments the streak has an extra, incorrect condition:
today.weekday() != 6. Python's datetime.weekday() returns 6 for Sunday (Monday=0 ... Sunday=6). This condition was presumably meant to guard some week-boundary behavior, but as written it excludes Sundays from ever incrementing the streak — even when the user listened on consecutive days. Any streak update that lands on a Sunday takes the else branch and gets reset to 1, regardless of how long the actual streak was.

**My fix and side-effect check:**
Removed the `and today.weekday() != 6` clause, so the branch is simply
`elif days_since_last == 1:`. Ran `pytest tests/test_streaks.py -v` — all 5 tests pass, including `test_streak_increments_on_sunday`. Also ran the full suite (`pytest tests/ -v`) to confirm the change didn't affect the "same day" (no double count) or "skipped day" (reset) tests, which still pass unchanged.

<!-- 每修一个bug复制一份上面这个模板 -->
