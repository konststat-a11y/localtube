from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class VideoUpdate(BaseModel):
    title: str
    description: str = ""
    author: str = ""
    category: str = "Без категории"
