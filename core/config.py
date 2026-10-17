"""Configuration settings for DispatchMind."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory for the repository
ROOT_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = ROOT_DIR

# Load environment variables from .env if present
load_dotenv(ROOT_DIR / ".env")


def get_bool(name: str, default: bool = False) -> bool:
    """Parse boolean value from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def get_int(name: str, default: int = 0) -> int:
    """Parse integer value from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


# Core flags
DEMO_MODE: bool = get_bool("DEMO_MODE", default=True)

# Google API Keys and Models
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")

# Maps and External APIs
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", os.getenv("MAPS_API_KEY", ""))
MAPS_API_KEY: str = GOOGLE_MAPS_API_KEY
OPEN_METEO_BASE_URL: str = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1")

# GCP Project and Cloud Storage
GOOGLE_CLOUD_PROJECT: str = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("FIRESTORE_PROJECT_ID", ""))
FIRESTORE_PROJECT_ID: str = GOOGLE_CLOUD_PROJECT
GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
GCS_BUCKET: str = os.getenv("GCS_BUCKET", "")

# Telegram Messaging
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_DISPATCHER_CHAT_ID: str = os.getenv("TELEGRAM_DISPATCHER_CHAT_ID", "")

# Operational Thresholds
MONITOR_INTERVAL_SEC: int = get_int("MONITOR_INTERVAL_SEC", default=30)
AUTO_APPLY_MAX_DELAY_MIN: int = get_int("AUTO_APPLY_MAX_DELAY_MIN", default=20)

# Depot Default Coordinates (Central Chennai depot)
DEPOT_LAT: float = float(os.getenv("DEPOT_LAT", "13.0067"))
DEPOT_LNG: float = float(os.getenv("DEPOT_LNG", "80.2025"))
DEPOT_PINCODE: str = os.getenv("DEPOT_PINCODE", "600032")

# Local Storage Paths
DATA_DIR: Path = ROOT_DIR / "data"
LOCAL_STORE_DIR: Path = Path(os.getenv("LOCAL_STORE_DIR", str(DATA_DIR / "local_store")))
LOCAL_STORE_PATH: Path = DATA_DIR / "local_store.json"
