import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
VIDEO_STORAGE_DIR = BASE_DIR / "video_storage"
THUMBNAIL_DIR = VIDEO_STORAGE_DIR / "thumbnails"
PROFILE_AVATAR_DIR = STATIC_DIR / "uploads" / "avatars"
DATABASE_URL = f"sqlite:///{BASE_DIR / 'app.db'}"

SESSION_SECRET_KEY = "change-this-local-development-secret"
INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_PASSWORD = "admin"

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv"}
UPLOAD_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
DEFAULT_VIDEO_CATEGORY = "Без категорії"
VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}
STREAM_CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024 * 1024
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024
SUPPORTED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LOCAL_FFMPEG_PATH = BASE_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
FFMPEG_PATH = os.getenv("VIDEOCLOUD_FFMPEG_PATH", "ffmpeg")
