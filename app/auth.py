from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_admin(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user = require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


def render_auth_form(
    request: Request,
    template: str,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template,
        context={"request": request, "user": None, "error": error},
        status_code=status_code,
    )


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return render_auth_form(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
):
    user = get_user_by_username(db, username.strip())
    if user is None or not verify_password(password, user.password_hash):
        return render_auth_form(
            request,
            "login.html",
            "Неверный логин или пароль.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register")
def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return render_auth_form(request, "register.html")


@router.post("/register")
def register(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
):
    username = username.strip()
    if not username or not password:
        return render_auth_form(
            request,
            "register.html",
            "Укажите логин и пароль.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return render_auth_form(
            request,
            "register.html",
            "Пользователь с таким логином уже существует.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


def ensure_initial_admin(db: Session) -> None:
    from .config import INITIAL_ADMIN_PASSWORD, INITIAL_ADMIN_USERNAME

    existing_admin = db.query(User).filter(User.is_admin.is_(True)).first()
    if existing_admin:
        return

    admin = User(
        username=INITIAL_ADMIN_USERNAME,
        password_hash=hash_password(INITIAL_ADMIN_PASSWORD),
        is_admin=True,
    )
    db.add(admin)
    db.commit()
