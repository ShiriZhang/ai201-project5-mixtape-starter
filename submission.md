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

### Issue #4: I got notified when a friend added my song to a playlist but not when they rated it

**How I reproduced it:**

Wrote `tests/repro_issue4.py`, a standalone script using an in-memory SQLite database (`create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})`). Created two users (a song sharer and a rater) and one song shared by the first user. Called `notification_service.get_notifications(sharer.id)` before and after calling `notification_service.rate_song(rater.id, song.id, 5)`.

The notification list was identical before and after the rating — confirming that rating a song produces no notification for the person who shared it, even though the two are different users.

**How I found the root cause:**

I opened `services/notification_service.py`, since that's the file the README attributes this issue to. I compared `rate_song` against `add_to_playlist` in the same file — the brief's hint pointed out that Issue #4's cause is architectural, so I looked for a structural difference between a notification path that works and one that doesn't. `add_to_playlist` ends with:

```python
if song.shared_by != added_by_user_id:
    create_notification(
        user_id=song.shared_by,
        notification_type="song_added_to_playlist",
        body=f"{adder.username} added your song '{song.title}' to the playlist '{playlist.name}'.",
    )
```

`rate_song` has no equivalent block — it validates the score, creates/updates the `Rating` row, commits, and returns. It never calls `create_notification` at all, despite living in the same file whose module docstring says "Notifications are generated when friends interact with a user's shared songs."

**The root cause:**
`rate_song` is missing a call to `create_notification`. The notification-creation mechanism itself works fine (proven by `add_to_playlist`'s working example) — it just was never wired up for the "rate a song" interaction. So rating someone else's shared song silently updates the `Rating` table but never notifies the original sharer, even though adding that same song to a playlist does.

**My fix and side-effect check:**
Added a call to `create_notification` at the end of `rate_song`, mirroring
`add_to_playlist`'s pattern exactly — notifying `song.shared_by` with a `song_rated` notification, guarded by `if song.shared_by != user_id` so a user rating their own shared song doesn't notify themselves:

```python
if song.shared_by != user_id:
    create_notification(
        user_id=song.shared_by,
        notification_type="song_rated",
        body=f"{rater.username} rated your song '{song.title}' with {score}/5.",
    )
```

Re-ran `repro_issue4.py` — the sharer's notification list now contains a new song_rated entry after rating. Ran the full test suite (`pytest tests/ -v`): all `test_streaks.py` and `test_search.py` tests still pass (13 total minus 2 pre-existing, unrelated `test_playlists.py` failures tied to the separate Issue #5, not touched by this change) — confirming this fix didn't affect streak or search behavior.

### Issue #5: The last song in a playlist never shows up

**How I reproduced it:**

Wrote `tests/repro_issue5.py`: created a playlist with 3 songs (via direct inserts into `playlist_entries` with `position` 1, 2, 3), then called `get_playlist_songs(playlist.id)`.


Song 3 (the one with the highest `position`) was missing. I also tested the boundary case of a playlist with exactly 1 song — before the fix, `get_playlist_songs()` returned **0** songs for it, which is an even clearer symptom of the same bug.

**How I found the root cause:**

The existing test suite already had `tests/test_playlists.py::test_playlist_returns_all_songs`, which fails with `assert len(songs) == 5` where actual was 4, and its own comment reads
`# Bug causes this to return 4`. That pointed me straight at
`services/playlist_service.py`'s `get_playlist_songs`. Reading it line by line, the query builds `songs` ordered ascending by `position`, then the return statement is:

```python
return [song.to_dict() for song in songs[:-1]]
```
`songs[:-1]` is a Python slice that returns every element except the last one.

**The root cause:**
`get_playlist_songs` queries all of a playlist's songs correctly, ordered by `position`, but then slices the result with `[:-1]` before returning — unconditionally dropping the last song in the ordered list. Since the list is sorted ascending by `position`, the "last" element is always the song with the highest position, i.e. the most recently added one at the end of the playlist. This directly contradicts the function's own docstring, which says "Note: This function returns all songs in the playlist." For a playlist with only 1 song, this slice returns an empty list instead of that one song.

**My fix and side-effect check:**
Changed the return statement to `return [song.to_dict() for song in songs]`, removing the slice entirely. Verified with `repro_issue5.py`: a 3-song playlist now returns all 3 songs, and the 1-song boundary case now correctly returns 1 song (not 0). Ran the full test suite (`pytest tests/ -v`) — all 13 tests pass, including the two previously-failing
`test_playlists.py` tests (test_playlist_returns_all_songs, test_playlist_returns_songs_in_order), with no regressions in streak or search tests.

### Issue #3: The same song keeps showing up twice in search

**How I reproduced it:**

Wrote `tests/repro_issue3.py`: created songs with 0, 1, and 3 tags in both an in-memory test database and against the real seeded `mixtape.db`, then called `search_songs()` with a query matching a 3-tag song. In every attempt, the returned list contained exactly one entry for that song — no visible duplicate.

However, `db.session.query(Song).outerjoin(song_tags, Song.id == song_tags.c.song_id).filter(...)` does produce row fan-out at the SQL level: for a song with 3 tags, `.count()` on that query returned 4 (1 row per matching `song_tags` row, plus other matching songs), while `.all()` returned only 2 mapped objects. This confirmed the join was multiplying rows at
the SQL level, but SQLAlchemy's legacy `Query.all()` automatically deduplicates mapped entities by primary key, which silently absorbed the duplication before it reached `search_songs()`'s return value in this environment.

**How I found the root cause:**

I initially assumed a 3-tag song would appear 3 times in the results and tried to reproduce that directly — it never did, across three separate attempts (isolated test data, real seed data, and an exact 24-hour-style boundary check adapted for this issue). That led me to read `tests/test_search.py`, which already contains `test_search_no_duplicates_multi_tag_song`, whose own comment says:
`assert len(matching) == 1  # Should be 1, bug causes it to be 3`. This is the test author's own description of the intended bug, and it was already passing — meaning the duplication described by the bug wasn't actually happening in this environment. That pushed me to check the SQL layer directly with `.count()` vs `.all()`, which is where I found the real discrepancy (4 vs 2).

**The root cause:**

`search_songs()` in `services/search_service.py` joins `Song` to `song_tags` via `.outerjoin(song_tags, Song.id == song_tags.c.song_id)`, but the `WHERE` clause only filters on `Song.title` and `Song.artist` — the join is never used for filtering or selecting tag data. Its only effect is that a song with N tags produces N matching rows at the SQL level for a single logical song. In this project's installed SQLAlchemy version, the legacy `Query.all()` API happens to deduplicate mapped entities by primary key automatically, so the visible symptom (duplicate dicts in the returned list) doesn't currently manifest. But the underlying defect — an unnecessary join that multiplies rows per tag with no filtering purpose — is real and fragile: it depends entirely on an ORM convenience behavior rather than the query itself being correct, and would produce actual duplicates under a different query execution style (e.g. SQLAlchemy 2.0-style `select()` execution, which does not auto-deduplicate unless `.unique()` is called explicitly).

**My fix and side-effect check:**

Removed the unnecessary `.outerjoin(song_tags, ...)` entirely, since it was never used to
filter or select anything:

```python
def search_songs(query: str) -> list[dict]:
    results = (
        db.session.query(Song)
        .filter(
            db.or_(
                Song.title.ilike(f"%{query}%"),
                Song.artist.ilike(f"%{query}%"),
            )
        )
        .all()
    )
    return [song.to_dict() for song in results]
```

Verified with `repro_issue3.py` that `.count()` and `len(.all())` are now both 1 for a 3-tag song match — the row-multiplication risk is eliminated at the SQL level, not just masked by ORM deduplication. Ran the full test suite (pytest tests/ -v): all tests pass, including the three `test_search_no_duplicates_*` tests and the unrelated streak/playlist tests, confirming no regressions.