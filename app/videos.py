import mimetypes
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from .auth import get_current_user, redirect_to_login, require_user
from .config import (
    FFMPEG_PATH,
    MAX_UPLOAD_SIZE_BYTES,
    STREAM_CHUNK_SIZE,
    SUPPORTED_VIDEO_EXTENSIONS,
    THUMBNAIL_DIR,
    UPLOAD_VIDEO_EXTENSIONS,
    VIDEO_MEDIA_TYPES,
    VIDEO_STORAGE_DIR,
)
from .database import SessionLocal, get_db
from .models import Comment, User, UserProfile, Video, VideoAccess, VideoProgress, VideoReaction, ViewHistory, WatchLater


router = APIRouter()
ACTIVE_STREAMS: dict[int, set[Event]] = {}
ACTIVE_STREAMS_LOCK = Lock()
DEFAULT_CATEGORY = "Без категории"


def register_active_stream(video_id: int) -> Event:
    stop_event = Event()
    with ACTIVE_STREAMS_LOCK:
        ACTIVE_STREAMS.setdefault(video_id, set()).add(stop_event)
    return stop_event


def unregister_active_stream(video_id: int, stop_event: Event) -> None:
    with ACTIVE_STREAMS_LOCK:
        streams = ACTIVE_STREAMS.get(video_id)
        if not streams:
            return
        streams.discard(stop_event)
        if not streams:
            ACTIVE_STREAMS.pop(video_id, None)


def stop_active_streams(video_id: int, timeout_seconds: float = 1.2) -> None:
    deadline = time.monotonic() + timeout_seconds
    with ACTIVE_STREAMS_LOCK:
        streams = list(ACTIVE_STREAMS.get(video_id, set()))

    for stop_event in streams:
        stop_event.set()

    while time.monotonic() < deadline:
        with ACTIVE_STREAMS_LOCK:
            if not ACTIVE_STREAMS.get(video_id):
                return
        time.sleep(0.05)


def delete_file_with_retries(path: Path, attempts: int = 12, delay_seconds: float = 0.2) -> bool:
    if not path.exists() or not path.is_file():
        return True

    for _ in range(attempts):
        try:
            path.unlink()
            return True
        except PermissionError:
            time.sleep(delay_seconds)
    return False


def remove_video_record(db: Session, video_id: int) -> None:
    video = db.query(Video).filter(Video.id == video_id).first()
    delete_video_thumbnail(video_id)
    db.query(VideoAccess).filter(VideoAccess.video_id == video_id).delete()
    if video is not None:
        db.delete(video)
    db.commit()


def delete_video_file_in_background(video_id: int, path: Path) -> None:
    def worker() -> None:
        for _ in range(60):
            stop_active_streams(video_id)
            try:
                if delete_file_with_retries(path, attempts=5, delay_seconds=0.2):
                    db = SessionLocal()
                    try:
                        remove_video_record(db, video_id)
                    finally:
                        db.close()
                    return
            except OSError:
                pass
            time.sleep(1)

    Thread(target=worker, daemon=True).start()


def user_can_access_video(db: Session, user: User, video: Video) -> bool:
    if user.is_admin:
        return True
    return (
        db.query(VideoAccess)
        .filter(VideoAccess.user_id == user.id, VideoAccess.video_id == video.id)
        .first()
        is not None
    )


def user_can_delete_video(user: User, video: Video) -> bool:
    return user.is_admin or video.author == user.username


def accessible_videos_query(db: Session, user: User):
    query = db.query(Video).filter(Video.is_available.is_(True))
    if user.is_admin:
        return query
    return query.join(VideoAccess).filter(VideoAccess.user_id == user.id)


def public_videos_query(db: Session):
    return db.query(Video).filter(Video.is_available.is_(True))


def ensure_video_access(db: Session, user: User, video_id: int) -> Video:
    video = db.query(Video).filter(Video.id == video_id, Video.is_available.is_(True)).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not user_can_access_video(db, user, video):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return video


def record_view_history(db: Session, user: User, video: Video) -> None:
    entry = (
        db.query(ViewHistory)
        .filter(ViewHistory.user_id == user.id, ViewHistory.video_id == video.id)
        .first()
    )
    if entry is None:
        db.add(ViewHistory(user_id=user.id, video_id=video.id, viewed_at=datetime.utcnow()))
    else:
        entry.viewed_at = datetime.utcnow()
    db.commit()


def get_video_progress(db: Session, user: User, video: Video) -> VideoProgress | None:
    progress = (
        db.query(VideoProgress)
        .filter(VideoProgress.user_id == user.id, VideoProgress.video_id == video.id)
        .first()
    )
    if progress is None or progress.duration_seconds <= 0 or progress.current_seconds <= 0:
        return None
    return progress


def get_video_progress_map(db: Session, user: User | None, videos: list[Video]) -> dict[int, VideoProgress]:
    if user is None or not videos:
        return {}
    video_ids = [video.id for video in videos]
    rows = (
        db.query(VideoProgress)
        .filter(
            VideoProgress.user_id == user.id,
            VideoProgress.video_id.in_(video_ids),
            VideoProgress.current_seconds > 0,
            VideoProgress.duration_seconds > 0,
        )
        .all()
    )
    return {progress.video_id: progress for progress in rows}


def get_author_profile_map(db: Session, videos: list[Video]) -> dict[str, UserProfile]:
    authors = sorted({video.author for video in videos if video.author})
    if not authors:
        return {}
    rows = (
        db.query(UserProfile)
        .join(User, User.id == UserProfile.user_id)
        .filter(User.username.in_(authors))
        .all()
    )
    return {profile.user.username: profile for profile in rows if profile.user is not None}


def user_has_watch_later(db: Session, user: User, video: Video) -> bool:
    return (
        db.query(WatchLater.id)
        .filter(WatchLater.user_id == user.id, WatchLater.video_id == video.id)
        .first()
        is not None
    )


def get_user_reaction(db: Session, user: User, video: Video) -> int:
    reaction = (
        db.query(VideoReaction)
        .filter(VideoReaction.user_id == user.id, VideoReaction.video_id == video.id)
        .first()
    )
    return reaction.value if reaction else 0


def get_reaction_counts(db: Session, video: Video) -> tuple[int, int]:
    likes = (
        db.query(VideoReaction)
        .filter(VideoReaction.video_id == video.id, VideoReaction.value == 1)
        .count()
    )
    dislikes = (
        db.query(VideoReaction)
        .filter(VideoReaction.video_id == video.id, VideoReaction.value == -1)
        .count()
    )
    return likes, dislikes


def resolve_storage_path(path: Path) -> Path:
    resolved = path.resolve()
    storage_root = VIDEO_STORAGE_DIR.resolve()
    try:
        resolved.relative_to(storage_root)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return resolved


def video_path_exists(db: Session, path: Path) -> bool:
    resolved = str(path.resolve())
    return path.exists() or db.query(Video.id).filter(Video.file_path == resolved).first() is not None


def sanitize_upload_stem(filename: str) -> str:
    original = Path(filename or "").name
    stem = Path(original).stem.strip()
    stem = re.sub(r"[^0-9A-Za-zА-Яа-я._ -]+", "_", stem).strip(" ._")
    if not stem:
        stem = "video"
    return stem


def build_transcoded_upload_paths(db: Session, filename: str) -> tuple[Path, Path]:
    original = Path(filename or "").name
    suffix = Path(original).suffix.lower()
    if suffix not in UPLOAD_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported video format")

    stem = sanitize_upload_stem(original)
    VIDEO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = resolve_storage_path(VIDEO_STORAGE_DIR / f"{stem}.mp4")
    counter = 1
    while video_path_exists(db, target_path):
        target_path = resolve_storage_path(VIDEO_STORAGE_DIR / f"{stem}-{counter}.mp4")
        counter += 1

    source_path = resolve_storage_path(VIDEO_STORAGE_DIR / f".{target_path.stem}.upload{suffix}")
    source_counter = 1
    while source_path.exists():
        source_path = resolve_storage_path(VIDEO_STORAGE_DIR / f".{target_path.stem}.upload-{source_counter}{suffix}")
        source_counter += 1
    return source_path, target_path


def guess_video_media_type(path: Path) -> str:
    return VIDEO_MEDIA_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def get_thumbnail_path(video_id: int) -> Path:
    return resolve_storage_path(THUMBNAIL_DIR / f"{video_id}.jpg")


def resolve_ffmpeg_path() -> str:
    configured_path = Path(FFMPEG_PATH)
    if configured_path.exists():
        return str(configured_path)

    found_path = shutil.which(FFMPEG_PATH)
    if found_path:
        return found_path

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ffmpeg is required for video transcoding",
    )


def transcode_to_browser_mp4(source_path: Path, target_path: Path) -> None:
    ffmpeg_path = resolve_ffmpeg_path()
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-sn",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(target_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not start ffmpeg: {exc}",
        ) from exc

    if result.returncode != 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not transcode video to browser-compatible MP4",
        )


def generate_video_thumbnail(video_id: int, video_path: Path) -> bool:
    if not video_path.exists() or not video_path.is_file():
        return False

    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    thumbnail_path = get_thumbnail_path(video_id)
    temp_path = resolve_storage_path(THUMBNAIL_DIR / f".{video_id}.tmp.jpg")
    try:
        ffmpeg_path = resolve_ffmpeg_path()
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-2",
            "-q:v",
            "3",
            str(temp_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (HTTPException, OSError):
        temp_path.unlink(missing_ok=True)
        return False

    if result.returncode != 0 or not temp_path.exists():
        temp_path.unlink(missing_ok=True)
        return False

    temp_path.replace(thumbnail_path)
    return True


def ensure_video_thumbnail(video: Video) -> bool:
    thumbnail_path = get_thumbnail_path(video.id)
    if thumbnail_path.exists() and thumbnail_path.is_file():
        return True
    return generate_video_thumbnail(video.id, Path(video.file_path))


def delete_video_thumbnail(video_id: int) -> None:
    try:
        get_thumbnail_path(video_id).unlink(missing_ok=True)
    except OSError:
        pass


def safe_redirect_path(path: str | None, fallback: str = "/") -> str:
    if path and path.startswith("/") and not path.startswith("//"):
        return path
    return fallback


def wants_json(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def format_datetime_for_json(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%Y %H:%M")


def grant_video_access_to_regular_users(db: Session, video_id: int) -> None:
    user_ids = [row[0] for row in db.query(User.id).filter(User.is_admin.is_(False)).all()]
    for user_id in user_ids:
        exists = (
            db.query(VideoAccess.id)
            .filter(VideoAccess.user_id == user_id, VideoAccess.video_id == video_id)
            .first()
        )
        if exists is None:
            db.add(VideoAccess(user_id=user_id, video_id=video_id))


def sync_missing_uploaded_video_access(db: Session, user: User) -> None:
    if user.is_admin:
        return

    accessible_video_ids = {
        row[0]
        for row in db.query(VideoAccess.video_id).filter(VideoAccess.user_id == user.id).all()
    }
    missing_video_ids = [
        row[0]
        for row in db.query(Video.id)
        .filter(
            Video.is_available.is_(True),
            Video.author != "",
            Video.id.not_in(accessible_video_ids or {-1}),
        )
        .all()
    ]
    for video_id in missing_video_ids:
        db.add(VideoAccess(user_id=user.id, video_id=video_id))
    if missing_video_ids:
        db.commit()


def ensure_default_video_access(db: Session, user: User) -> None:
    if user.is_admin:
        return

    has_access = db.query(VideoAccess).filter(VideoAccess.user_id == user.id).first()
    if has_access:
        return

    video_ids = [row[0] for row in db.query(Video.id).filter(Video.is_available.is_(True)).all()]
    for video_id in video_ids:
        db.add(VideoAccess(user_id=user.id, video_id=video_id))
    if video_ids:
        db.commit()


def apply_video_sort(query, sort: str, order: str):
    direction = asc if order == "asc" else desc
    if sort == "title":
        return query.order_by(direction(Video.title), desc(Video.created_at))
    return query.order_by(direction(Video.created_at), asc(Video.title))


def scan_video_storage(db: Session) -> tuple[int, int, int]:
    VIDEO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    db.query(Video).update({Video.is_available: False})
    created = 0
    updated = 0
    seen_paths: set[str] = set()
    thumbnail_candidates: list[Video] = []

    for path in VIDEO_STORAGE_DIR.rglob("*"):
        if THUMBNAIL_DIR in path.parents:
            continue
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            continue

        resolved = str(path.resolve())
        seen_paths.add(resolved)
        size = path.stat().st_size
        video = db.query(Video).filter(Video.file_path == resolved).first()
        if video is None:
            video = Video(
                filename=path.name,
                title=path.stem,
                description="",
                author="",
                category="Без категории",
                file_path=resolved,
                size_bytes=size,
                is_available=True,
            )
            db.add(video)
            created += 1
        else:
            video.filename = path.name
            video.size_bytes = size
            video.is_available = True
            video.updated_at = datetime.utcnow()
            updated += 1
        thumbnail_candidates.append(video)

    db.commit()
    for video in thumbnail_candidates:
        ensure_video_thumbnail(video)
    missing = db.query(Video).filter(Video.is_available.is_(False)).count()
    return created, updated, missing


@router.get("/")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    category: Annotated[str | None, Query()] = None,
    section: Annotated[str | None, Query(pattern="^(history|watch_later|liked)$")] = None,
    login: Annotated[bool, Query()] = False,
    sort: Annotated[str, Query(pattern="^(title|date)$")] = "date",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
):
    user = get_current_user(request, db)
    if user is not None:
        ensure_default_video_access(db, user)
        sync_missing_uploaded_video_access(db, user)

    base_query = accessible_videos_query(db, user) if user is not None else public_videos_query(db)
    categories = [
        row[0]
        for row in base_query.with_entities(Video.category)
        .distinct()
        .order_by(asc(Video.category))
        .all()
        if row[0]
    ]

    section_title = None
    if section and user is None:
        return redirect_to_login()
    if section == "history":
        section_title = "История просмотров"
        videos = (
            accessible_videos_query(db, user)
            .join(ViewHistory, ViewHistory.video_id == Video.id)
            .filter(ViewHistory.user_id == user.id)
            .order_by(desc(ViewHistory.viewed_at))
            .all()
        )
    elif section == "watch_later":
        section_title = "Смотреть позже"
        videos = (
            accessible_videos_query(db, user)
            .join(WatchLater, WatchLater.video_id == Video.id)
            .filter(WatchLater.user_id == user.id)
            .order_by(desc(WatchLater.created_at))
            .all()
        )
    elif section == "liked":
        section_title = "Понравившиеся видео"
        videos = (
            accessible_videos_query(db, user)
            .join(VideoReaction, VideoReaction.video_id == Video.id)
            .filter(VideoReaction.user_id == user.id, VideoReaction.value == 1)
            .order_by(desc(VideoReaction.updated_at))
            .all()
        )
    else:
        query = base_query
        if category:
            query = query.filter(Video.category == category)
        videos = apply_video_sort(query, sort, order).all()

    watch_later_ids: set[int] = set()
    if user is not None:
        watch_later_ids = {
            row[0]
            for row in db.query(WatchLater.video_id)
            .filter(WatchLater.user_id == user.id)
            .all()
        }
    video_progress = get_video_progress_map(db, user, videos)
    author_profiles = get_author_profile_map(db, videos)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "user": user,
            "videos": videos,
            "categories": categories,
            "current_category": category,
            "current_section": section,
            "section_title": section_title,
            "show_login": login and user is None,
            "show_upload": request.query_params.get("upload") == "1" and user is not None,
            "sort": sort,
            "order": order,
            "watch_later_ids": watch_later_ids,
            "video_progress": video_progress,
            "author_profiles": author_profiles,
        },
    )


@router.post("/videos/upload")
def upload_video(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    media_file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
):
    source_path, target_path = build_transcoded_upload_paths(db, media_file.filename or "")
    bytes_written = 0
    try:
        with source_path.open("wb") as output:
            while True:
                chunk = media_file.file.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    source_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Video file is too large",
                    )

        if bytes_written == 0:
            source_path.unlink(missing_ok=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        transcode_to_browser_mp4(source_path, target_path)
        transcoded_size = target_path.stat().st_size
        now = datetime.utcnow()
        video = Video(
            filename=target_path.name,
            title=title.strip() or target_path.stem,
            description="",
            author=user.username,
            category=DEFAULT_CATEGORY,
            file_path=str(target_path),
            size_bytes=transcoded_size,
            created_at=now,
            updated_at=now,
            is_available=True,
        )
        db.add(video)
        db.flush()
        grant_video_access_to_regular_users(db, video.id)
        video_id = video.id
        db.commit()
        ensure_video_thumbnail(video)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        source_path.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Video file already exists",
        ) from exc
    except Exception:
        db.rollback()
        source_path.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        raise
    finally:
        media_file.file.close()
        source_path.unlink(missing_ok=True)

    return RedirectResponse(url=f"/watch/{video_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/videos/{video_id}/thumbnail")
def video_thumbnail(
    video_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    user = get_current_user(request, db)
    video = db.query(Video).filter(Video.id == video_id, Video.is_available.is_(True)).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if user is not None and not user_can_access_video(db, user, video):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    thumbnail_path = get_thumbnail_path(video.id)
    if not thumbnail_path.exists() and not ensure_video_thumbnail(video):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.post("/history/clear")
def clear_history(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
):
    db.query(ViewHistory).filter(ViewHistory.user_id == user.id).delete()
    db.commit()
    return RedirectResponse(url="/?section=history", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/videos/{video_id}/progress")
def save_video_progress(
    video_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    current_seconds: Annotated[int, Form()],
    duration_seconds: Annotated[int, Form()],
):
    video = ensure_video_access(db, user, video_id)
    duration_seconds = max(duration_seconds, 0)
    current_seconds = max(current_seconds, 0)
    if duration_seconds <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    current_seconds = min(current_seconds, duration_seconds)
    progress = (
        db.query(VideoProgress)
        .filter(VideoProgress.user_id == user.id, VideoProgress.video_id == video.id)
        .first()
    )
    if duration_seconds - current_seconds <= 2:
        if progress is not None:
            db.delete(progress)
            db.commit()
        return JSONResponse({"saved": False, "current_seconds": 0, "duration_seconds": duration_seconds})

    if progress is None:
        progress = VideoProgress(
            user_id=user.id,
            video_id=video.id,
            current_seconds=current_seconds,
            duration_seconds=duration_seconds,
            updated_at=datetime.utcnow(),
        )
        db.add(progress)
    else:
        progress.current_seconds = current_seconds
        progress.duration_seconds = duration_seconds
        progress.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse(
        {
            "saved": True,
            "current_seconds": current_seconds,
            "duration_seconds": duration_seconds,
        }
    )


@router.post("/videos/{video_id}/watch-later")
def toggle_watch_later(
    request: Request,
    video_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    next_url: Annotated[str | None, Form(alias="next")] = None,
):
    video = ensure_video_access(db, user, video_id)
    entry = (
        db.query(WatchLater)
        .filter(WatchLater.user_id == user.id, WatchLater.video_id == video.id)
        .first()
    )
    if entry is None:
        db.add(WatchLater(user_id=user.id, video_id=video.id))
        in_watch_later = True
    else:
        db.delete(entry)
        in_watch_later = False
    db.commit()
    if wants_json(request):
        return JSONResponse(
            {
                "in_watch_later": in_watch_later,
                "label": "Убрать из «Смотреть позже»" if in_watch_later else "Смотреть позже",
            }
        )
    return RedirectResponse(
        url=safe_redirect_path(next_url, f"/watch/{video.id}"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/videos/{video_id}/reaction")
def set_video_reaction(
    request: Request,
    video_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    value: Annotated[int, Form()],
):
    video = ensure_video_access(db, user, video_id)
    if value not in (-1, 1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    reaction = (
        db.query(VideoReaction)
        .filter(VideoReaction.user_id == user.id, VideoReaction.video_id == video.id)
        .first()
    )
    if reaction is None:
        db.add(VideoReaction(user_id=user.id, video_id=video.id, value=value))
    elif reaction.value == value:
        db.delete(reaction)
    else:
        reaction.value = value
        reaction.updated_at = datetime.utcnow()
    db.commit()
    likes_count, dislikes_count = get_reaction_counts(db, video)
    user_reaction = get_user_reaction(db, user, video)
    if wants_json(request):
        return JSONResponse(
            {
                "likes_count": likes_count,
                "dislikes_count": dislikes_count,
                "user_reaction": user_reaction,
            }
        )
    return RedirectResponse(url=f"/watch/{video.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/videos/{video_id}/comments")
def add_comment(
    request: Request,
    video_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    body: Annotated[str, Form()],
):
    video = ensure_video_access(db, user, video_id)
    body = body.strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    comment = Comment(user_id=user.id, video_id=video.id, body=body[:2000])
    db.add(comment)
    db.commit()
    db.refresh(comment)
    if wants_json(request):
        return JSONResponse(
            {
                "comment": {
                    "id": comment.id,
                    "username": user.username,
                    "body": comment.body,
                    "created_at": format_datetime_for_json(comment.created_at),
                    "can_delete": True,
                }
            }
        )
    return RedirectResponse(url=f"/watch/{video.id}#comments", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/comments/{comment_id}/delete")
def delete_comment(
    request: Request,
    comment_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    video = db.query(Video).filter(Video.id == comment.video_id).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if comment.user_id != user.id and not user.is_admin and video.author != user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    video_id = comment.video_id
    db.delete(comment)
    db.commit()
    if wants_json(request):
        return JSONResponse({"deleted": True, "comment_id": comment_id})
    return RedirectResponse(url=f"/watch/{video_id}#comments", status_code=status.HTTP_303_SEE_OTHER)



@router.post("/videos/{video_id}/delete")
def delete_video(
    video_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not user_can_delete_video(user, video):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    path = resolve_storage_path(Path(video.file_path))
    stop_active_streams(video.id)
    try:
        file_deleted = delete_file_with_retries(path)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete video file: {exc}",
        )

    if not file_deleted:
        video.is_available = False
        video.updated_at = datetime.utcnow()
        db.query(VideoAccess).filter(VideoAccess.video_id == video.id).delete()
        db.commit()
        delete_video_file_in_background(video.id, path)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    try:
        remove_video_record(db, video.id)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete video: {exc}",
        )
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/watch/{video_id}")
def watch_video(
    video_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    user = get_current_user(request, db)
    if user is None:
        return redirect_to_login()

    video = db.query(Video).filter(Video.id == video_id, Video.is_available.is_(True)).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not user_can_access_video(db, user, video):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    record_view_history(db, user, video)

    accessible_ids = [item.id for item in accessible_videos_query(db, user).order_by(asc(Video.id)).all()]
    current_index = accessible_ids.index(video.id)
    previous_id = accessible_ids[current_index - 1] if current_index > 0 else None
    next_id = accessible_ids[current_index + 1] if current_index < len(accessible_ids) - 1 else None
    related_videos = (
        accessible_videos_query(db, user)
        .filter(Video.id != video.id, Video.category == video.category)
        .order_by(func.random())
        .limit(8)
        .all()
    )
    author_profiles = get_author_profile_map(db, [video, *related_videos])
    autoplay_id = next_id or (related_videos[0].id if related_videos else None)
    likes_count, dislikes_count = get_reaction_counts(db, video)
    video_progress = get_video_progress(db, user, video)
    comments = (
        db.query(Comment)
        .filter(Comment.video_id == video.id)
        .order_by(asc(Comment.created_at))
        .all()
    )

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="watch.html",
        context={
            "request": request,
            "user": user,
            "video": video,
            "previous_id": previous_id,
            "next_id": next_id,
            "autoplay_id": autoplay_id,
            "can_delete": user_can_delete_video(user, video),
            "related_videos": related_videos,
            "author_profiles": author_profiles,
            "likes_count": likes_count,
            "dislikes_count": dislikes_count,
            "user_reaction": get_user_reaction(db, user, video),
            "in_watch_later": user_has_watch_later(db, user, video),
            "video_progress": video_progress,
            "comments": comments,
        },
    )


def parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int, bool]:
    if not range_header:
        return 0, file_size - 1, False

    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not match:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)

    start_raw, end_raw = match.groups()
    if not start_raw and not end_raw:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)

    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else file_size - 1
    else:
        suffix_length = int(end_raw)
        if suffix_length == 0:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        start = max(file_size - suffix_length, 0)
        end = file_size - 1

    if start >= file_size or end < start:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
    return start, min(end, file_size - 1), True


def iter_file_range(video_id: int, path: Path, start: int, end: int, stop_event: Event):
    try:
        with path.open("rb") as file:
            file.seek(start)
            remaining = end - start + 1
            while remaining > 0 and not stop_event.is_set():
                chunk = file.read(min(STREAM_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    finally:
        unregister_active_stream(video_id, stop_event)


@router.get("/videos/{video_id}/stream")
def stream_video(
    video_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    user = require_user(request, db)
    video = db.query(Video).filter(Video.id == video_id, Video.is_available.is_(True)).first()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not user_can_access_video(db, user, video):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    path = Path(video.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    file_size = path.stat().st_size
    start, end, partial = parse_range_header(range_header, file_size)
    content_length = end - start + 1
    media_type = guess_video_media_type(path)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }
    response_status = status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    stop_event = register_active_stream(video.id)
    return StreamingResponse(
        iter_file_range(video.id, path, start, end, stop_event),
        status_code=response_status,
        headers=headers,
        media_type=media_type,
    )
