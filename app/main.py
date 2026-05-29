from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import admin, auth, models, profile, videos
from .config import PROFILE_AVATAR_DIR, SESSION_SECRET_KEY, STATIC_DIR, TEMPLATE_DIR, VIDEO_STORAGE_DIR
from .database import SessionLocal
from .models import UserProfile


def format_bytes(value: int) -> str:
    size = float(value or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def format_datetime(value) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%Y %H:%M")


def inject_current_profile(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        return {"current_profile": None}

    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile is None:
            return {"current_profile": None}
        return {
            "current_profile": {
                "display_name": profile.display_name,
                "avatar_path": profile.avatar_path,
            }
        }
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Локальний відеосайт")
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, same_site="lax")

    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    templates.env.filters["bytes"] = format_bytes
    templates.env.filters["datetime"] = format_datetime
    templates.context_processors.append(inject_current_profile)
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(auth.router)
    app.include_router(videos.router)
    app.include_router(profile.router)
    app.include_router(admin.router)

    @app.on_event("startup")
    def startup() -> None:
        VIDEO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        PROFILE_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        db = SessionLocal()
        try:
            auth.ensure_initial_admin(db)
        finally:
            db.close()

    @app.exception_handler(status.HTTP_401_UNAUTHORIZED)
    def unauthorized_handler(request: Request, exc):
        del exc
        if request.url.path.startswith("/videos/"):
            return PlainTextResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return app


app = create_app()

__all__ = ["app", "models"]
