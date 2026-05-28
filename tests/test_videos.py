import unittest
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Comment, User, Video, VideoAccess, VideoProgress, VideoReaction, ViewHistory, WatchLater
from app.videos import delete_video_relations, parse_range_header


class RangeHeaderTest(unittest.TestCase):
    def test_missing_range_returns_full_file(self) -> None:
        self.assertEqual(parse_range_header(None, 100), (0, 99, False))

    def test_open_ended_range(self) -> None:
        self.assertEqual(parse_range_header("bytes=10-", 100), (10, 99, True))

    def test_limited_range(self) -> None:
        self.assertEqual(parse_range_header("bytes=10-19", 100), (10, 19, True))

    def test_suffix_range(self) -> None:
        self.assertEqual(parse_range_header("bytes=-20", 100), (80, 99, True))

    def test_invalid_range_raises_416(self) -> None:
        with self.assertRaises(HTTPException) as error:
            parse_range_header("bytes=100-101", 100)
        self.assertEqual(error.exception.status_code, status.HTTP_416_RANGE_NOT_SATISFIABLE)


class DeleteVideoRelationsTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine)

    def test_delete_video_relations_removes_dependent_rows(self) -> None:
        db = self.SessionLocal()
        try:
            now = datetime(2026, 1, 1)
            user = User(username="user", password_hash="hash", created_at=now)
            video = Video(
                filename="video.mp4",
                title="Video",
                file_path="/tmp/video.mp4",
                created_at=now,
                updated_at=now,
            )
            db.add_all([user, video])
            db.flush()

            db.add_all(
                [
                    Comment(user_id=user.id, video_id=video.id, body="comment", created_at=now),
                    VideoAccess(user_id=user.id, video_id=video.id),
                    VideoProgress(
                        user_id=user.id,
                        video_id=video.id,
                        current_seconds=10,
                        duration_seconds=20,
                        updated_at=now,
                    ),
                    VideoReaction(
                        user_id=user.id,
                        video_id=video.id,
                        value=1,
                        created_at=now,
                        updated_at=now,
                    ),
                    ViewHistory(user_id=user.id, video_id=video.id, viewed_at=now),
                    WatchLater(user_id=user.id, video_id=video.id, created_at=now),
                ]
            )
            db.commit()

            delete_video_relations(db, video.id)
            db.commit()

            for model in (Comment, VideoProgress, VideoReaction, ViewHistory, WatchLater):
                self.assertEqual(db.query(model).filter(model.video_id == video.id).count(), 0)
            self.assertEqual(db.query(VideoAccess).filter(VideoAccess.video_id == video.id).count(), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
