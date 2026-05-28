from pydantic import BaseModel

from .config import DEFAULT_VIDEO_CATEGORY


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class VideoUpdate(BaseModel):
    title: str
    description: str = ""
    author: str = ""
    category: str = DEFAULT_VIDEO_CATEGORY
