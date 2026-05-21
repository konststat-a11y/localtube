from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
VIDEO_STORAGE_DIR = BASE_DIR / "video_storage"
DATABASE_URL = f"sqlite:///{BASE_DIR / 'app.db'}"

SESSION_SECRET_KEY = "change-this-local-development-secret"
INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_PASSWORD = "admin"

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv"}
STREAM_CHUNK_SIZE = 1024 * 1024
