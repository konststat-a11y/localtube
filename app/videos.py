import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from .auth import get_current_user, redirect_to_login, require_user
from .config import STREAM_CHUNK_SIZE, SUPPORTED_VIDEO_EXTENSIONS, VIDEO_STORAGE_DIR
from .database import get_db
from .models import User, Video, VideoAccess


router = APIRouter()


def user_can_access_video(db: Session, user: User, video: Video) -> bool:
    if user.is_admin:
        return True
    return (
        db.query(VideoAccess)
        .filter(VideoAccess.user_id == user.id, VideoAccess.video_id == video.id)
        .first()
        is not None
    )


def accessible_videos_query(db: Session, user: User):
    query = db.query(Video).filter(Video.is_available.is_(True))
    if user.is_admin:
        return query
    return query.join(VideoAccess).filter(VideoAccess.user_id == user.id)


def public_videos_query(db: Session):
    return db.query(Video).filter(Video.is_available.is_(True))


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

    db.query(Video).update({Video.is_available: False})
    created = 0
    updated = 0
    seen_paths: set[str] = set()

    for path in VIDEO_STORAGE_DIR.rglob("*"):
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

    db.commit()
    missing = db.query(Video).filter(Video.is_available.is_(False)).count()
    return created, updated, missing


@router.get("/")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    category: Annotated[str | None, Query()] = None,
    login: Annotated[bool, Query()] = False,
    sort: Annotated[str, Query(pattern="^(title|date)$")] = "date",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
):
    user = get_current_user(request, db)
    if user is not None:
        ensure_default_video_access(db, user)

    base_query = accessible_videos_query(db, user) if user is not None else public_videos_query(db)
    categories = [
        row[0]
        for row in base_query.with_entities(Video.category)
        .distinct()
        .order_by(asc(Video.category))
        .all()
        if row[0]
    ]

    query = base_query
    if category:
        query = query.filter(Video.category == category)
    videos = apply_video_sort(query, sort, order).all()

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "user": user,
            "videos": videos,
            "categories": categories,
            "current_category": category,
            "show_login": login and user is None,
            "sort": sort,
            "order": order,
        },
    )


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
    autoplay_id = next_id or (related_videos[0].id if related_videos else None)

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
            "related_videos": related_videos,
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


def iter_file_range(path: Path, start: int, end: int):
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


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
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }
    response_status = status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        iter_file_range(path, start, end),
        status_code=response_status,
        headers=headers,
        media_type=media_type,
    )
