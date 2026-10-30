import os


class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    ARCHIVES_DIR = os.environ.get("ARCHIVES_DIR", "/data/archivi")
    DATA_DIR = os.environ.get("DATA_DIR", "/data/app")
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", os.path.join(DATA_DIR, "index.sqlite3")
    )

    PAGE_SIZE_DEFAULT = int(os.environ.get("PAGE_SIZE_DEFAULT", "50"))
    PAGE_SIZE_MAX = int(os.environ.get("PAGE_SIZE_MAX", "200"))
    ATTACHMENT_MAX_BYTES = int(
        os.environ.get("ATTACHMENT_MAX_BYTES", str(50 * 1024 * 1024))
    )

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
