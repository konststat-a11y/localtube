from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import hash_password, require_admin
from .database import get_db
from .models import User, Video, VideoAccess
from .videos import scan_video_storage


router = APIRouter(prefix="/admin")


def admin_template(request: Request, template: str, context: dict):
    base = {"request": request, "user": context.get("user")}
    base.update(context)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template,
        context=base,
    )


@router.get("")
def dashboard(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return admin_template(
        request,
        "admin/dashboard.html",
        {
            "user": user,
            "users_count": db.query(User).count(),
            "videos_count": db.query(Video).count(),
            "available_videos_count": db.query(Video).filter(Video.is_available.is_(True)).count(),
        },
    )


@router.get("/users")
def users_page(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    error: str | None = None,
):
    return admin_template(
        request,
        "admin/users.html",
        {
            "user": user,
            "users": db.query(User).order_by(User.created_at.desc()).all(),
            "error": error,
        },
    )


@router.post("/users/create")
def create_user(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    is_admin: Annotated[bool, Form()] = False,
):
    del user
    username = username.strip()
    if not username or not password:
        return RedirectResponse(url="/admin/users?error=empty", status_code=status.HTTP_303_SEE_OTHER)

    new_user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/admin/users?error=exists", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/videos")
def videos_page(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    scan: str | None = None,
):
    return admin_template(
        request,
        "admin/videos.html",
        {
            "user": user,
            "videos": db.query(Video).order_by(Video.created_at.desc()).all(),
            "scan": scan,
        },
    )


@router.post("/videos/scan")
def scan_videos(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    del user
    created, updated, missing = scan_video_storage(db)
    return RedirectResponse(
        url=f"/admin/videos?scan=created:{created},updated:{updated},missing:{missing}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/videos/{video_id}/update")
def update_video(
    video_id: int,
    title: Annotated[str, Form()],
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    description: Annotated[str, Form()] = "",
    author: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "Без категории",
):
    del user
    video = db.query(Video).filter(Video.id == video_id).first()
    if video:
        video.title = title.strip() or video.filename
        video.description = description.strip()
        video.author = author.strip()
        video.category = category.strip() or "Без категории"
        db.commit()
    return RedirectResponse(url="/admin/videos", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/access")
def access_page(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    user_id: int | None = None,
):
    users = db.query(User).order_by(User.username.asc()).all()
    selected_user = db.query(User).filter(User.id == user_id).first() if user_id else (users[0] if users else None)
    selected_ids: set[int] = set()
    if selected_user:
        selected_ids = {
            item.video_id
            for item in db.query(VideoAccess).filter(VideoAccess.user_id == selected_user.id).all()
        }

    return admin_template(
        request,
        "admin/access.html",
        {
            "user": user,
            "users": users,
            "selected_user": selected_user,
            "videos": db.query(Video).order_by(Video.title.asc()).all(),
            "selected_ids": selected_ids,
        },
    )


@router.post("/access/update")
def update_access(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[int, Form()],
    video_ids: Annotated[list[int] | None, Form()] = None,
):
    del user
    video_ids = video_ids or []
    db.query(VideoAccess).filter(VideoAccess.user_id == user_id).delete()
    for video_id in video_ids:
        db.add(VideoAccess(user_id=user_id, video_id=video_id))
    db.commit()
    return RedirectResponse(url=f"/admin/access?user_id={user_id}", status_code=status.HTTP_303_SEE_OTHER)
