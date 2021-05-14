#from flask_login import UserMixin

from app.db_utilities import get_db_connection

class Playlist():
    def __init__(self, id_, name, thumbnail, published_at):
        self.id = id_
        self.name = name
        self.thumbnail = thumbnail
        self.published_at = published_at

    @staticmethod
    def get(playlist_id):
        db = get_db_connection()
        playlist = db.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        if not playlist:
            return None

        playlist = Playlist(
            id_=playlist[0], name=playlist[1], thumbnail=playlist[2], published_at=playlist[3]
        )
        return playlist

    @staticmethod
    def create(id_, name, thumbnail,published_at):
        db = get_db_connection()
        db.execute(
            "INSERT INTO playlists (id, name, thumbnail,published_at) "
            "VALUES (?, ?, ?, ?)",
            (id_, name, thumbnail,published_at),
        )
        db.commit()