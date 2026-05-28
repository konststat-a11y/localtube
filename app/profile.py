import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import hash_password, require_user, verify_password
from .config import MAX_AVATAR_SIZE_BYTES, PROFILE_AVATAR_DIR, SUPPORTED_AVATAR_EXTENSIONS
from .database import get_db
from .models import User, UserProfile, Video, VideoAccess, VideoProgress, VideoReaction, ViewHistory, WatchLater
from .videos import accessible_videos_query, get_author_profile_map, get_video_progress_map


router = APIRouter()


def get_or_create_profile(db: Session, user: User) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is not None:
        return profile

    profile = UserProfile(user_id=user.id, display_name="", bio="", avatar_path="")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def profile_template(
    request: Request,
    user: User,
    profile: UserProfile,
    context: dict | None = None,
    status_code: int = status.HTTP_200_OK,
):
    base = {
        "request": request,
        "user": user,
        "profile": profile,
        "stats": {},
        "profile_message": None,
        "profile_error": None,
        "password_message": None,
        "password_error": None,
        "is_own_profile": True,
        "profile_user": user,
        "uploaded_videos": [],
        "video_progress": {},
        "watch_later_ids": set(),
        "show_card_actions": True,
    }
    if context:
        base.update(context)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="profile.html",
        context=base,
        status_code=status_code,
    )


def account_template(
    request: Request,
    user: User,
    profile: UserProfile,
    context: dict | None = None,
    status_code: int = status.HTTP_200_OK,
):
    base = {
        "request": request,
        "user": user,
        "profile": profile,
        "profile_message": None,
        "profile_error": None,
        "password_message": None,
        "password_error": None,
    }
    if context:
        base.update(context)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="account.html",
        context=base,
        status_code=status_code,
    )


def collect_profile_stats(db: Session, user: User) -> dict:
    available_videos = (
        db.query(Video).filter(Video.is_available.is_(True)).count()
        if user.is_admin
        else db.query(VideoAccess).filter(VideoAccess.user_id == user.id).count()
    )
    return {
        "available_videos": available_videos,
        "viewed_videos": db.query(ViewHistory).filter(ViewHistory.user_id == user.id).count(),
        "watch_later": db.query(WatchLater).filter(WatchLater.user_id == user.id).count(),
        "liked_videos": (
            db.query(VideoReaction)
            .filter(VideoReaction.user_id == user.id, VideoReaction.value == 1)
            .count()
        ),
        "progress_items": db.query(VideoProgress).filter(VideoProgress.user_id == user.id).count(),
    }


def collect_public_profile_stats(db: Session, profile_user: User, uploaded_videos: list[Video]) -> dict:
    return {
        "uploaded_videos": len(uploaded_videos),
        "viewed_videos": db.query(ViewHistory).filter(ViewHistory.user_id == profile_user.id).count(),
        "liked_videos": (
            db.query(VideoReaction)
            .filter(VideoReaction.user_id == profile_user.id, VideoReaction.value == 1)
            .count()
        ),
        "progress_items": db.query(VideoProgress).filter(VideoProgress.user_id == profile_user.id).count(),
    }


def uploaded_videos_for_viewer(db: Session, viewer: User, profile_user: User) -> list[Video]:
    return (
        accessible_videos_query(db, viewer)
        .filter(Video.author == profile_user.username)
        .order_by(desc(Video.created_at), desc(Video.id))
        .all()
    )


def watch_later_ids_for_user(db: Session, user: User) -> set[int]:
    return {
        row[0]
        for row in db.query(WatchLater.video_id)
        .filter(WatchLater.user_id == user.id)
        .all()
    }


def normalize_email(email: str) -> str | None:
    email = email.strip().lower()
    if not email:
        return None
    if "@" not in email or len(email) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return email


def avatar_url(profile: UserProfile) -> str:
    if not profile.avatar_path:
        return ""
    return f"/static/uploads/avatars/{profile.avatar_path}"


def save_avatar_file(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in SUPPORTED_AVATAR_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported avatar format")

    PROFILE_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    target = PROFILE_AVATAR_DIR / filename
    bytes_written = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 256)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_AVATAR_SIZE_BYTES:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
                output.write(chunk)
    finally:
        upload.file.close()

    if bytes_written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return filename


@router.get("/account")
def account_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    saved: str | None = None,
    password: str | None = None,
):
    profile = get_or_create_profile(db, user)
    return account_template(
        request,
        user,
        profile,
        {
            "profile_message": "Профиль обновлен." if saved == "1" else None,
            "password_message": "Пароль изменен." if password == "1" else None,
        },
    )


@router.get("/profile")
def profile_page(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    saved: str | None = None,
    password: str | None = None,
):
    profile = get_or_create_profile(db, user)
    uploaded_videos = uploaded_videos_for_viewer(db, user, user)
    messages = {
        "profile_message": "Профиль обновлен." if saved == "1" else None,
        "password_message": "Пароль изменен." if password == "1" else None,
    }
    return profile_template(
        request,
        user,
        profile,
        {
            **messages,
            "stats": collect_profile_stats(db, user),
            "avatar_url": avatar_url(profile),
            "is_own_profile": True,
            "profile_user": user,
            "uploaded_videos": uploaded_videos,
            "video_progress": get_video_progress_map(db, user, uploaded_videos),
            "author_profiles": get_author_profile_map(db, uploaded_videos),
            "watch_later_ids": watch_later_ids_for_user(db, user),
            "show_card_actions": True,
        },
    )


@router.get("/users/{username}")
def public_profile_page(
    username: str,
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
):
    profile_user = db.query(User).filter(User.username == username).first()
    if profile_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if profile_user.id == user.id:
        return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)

    profile = get_or_create_profile(db, profile_user)
    uploaded_videos = uploaded_videos_for_viewer(db, user, profile_user)
    return profile_template(
        request,
        user,
        profile,
        {
            "stats": collect_public_profile_stats(db, profile_user, uploaded_videos),
            "avatar_url": avatar_url(profile),
            "is_own_profile": False,
            "profile_user": profile_user,
            "uploaded_videos": uploaded_videos,
            "video_progress": get_video_progress_map(db, user, uploaded_videos),
            "author_profiles": get_author_profile_map(db, uploaded_videos),
            "watch_later_ids": watch_later_ids_for_user(db, user),
            "show_card_actions": True,
        },
    )


@router.post("/account")
@router.post("/profile")
def update_profile(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    display_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    bio: Annotated[str, Form()] = "",
    avatar: Annotated[UploadFile | None, File()] = None,
):
    profile = get_or_create_profile(db, user)
    try:
        user.email = normalize_email(email)
        profile.display_name = display_name.strip()[:120]
        profile.bio = bio.strip()[:2000]
        profile.updated_at = datetime.utcnow()
        if avatar is not None and avatar.filename:
            old_avatar = profile.avatar_path
            profile.avatar_path = save_avatar_file(avatar)
            if old_avatar:
                try:
                    (PROFILE_AVATAR_DIR / old_avatar).unlink(missing_ok=True)
                except OSError:
                    pass
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return account_template(
            request,
            user,
            profile,
            {
                "profile_error": "Проверьте email или формат аватара.",
            },
            status_code=exc.status_code,
        )
    except IntegrityError:
        db.rollback()
        return account_template(
            request,
            user,
            profile,
            {
                "profile_error": "Этот email уже используется.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/account?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/account/password")
@router.post("/profile/password")
def update_password(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
    profile = get_or_create_profile(db, user)
    if not verify_password(current_password, user.password_hash):
        return account_template(
            request,
            user,
            profile,
            {
                "password_error": "Текущий пароль указан неверно.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not new_password or new_password != confirm_password:
        return account_template(
            request,
            user,
            profile,
            {
                "password_error": "Новый пароль и подтверждение не совпадают.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/account?password=1", status_code=status.HTTP_303_SEE_OTHER)
