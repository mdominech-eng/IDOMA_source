from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
RELEASE_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = RELEASE_DIR.parent

# Load both project-level and release-level settings, without overriding real env vars.
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(RELEASE_DIR / ".env", override=False)

APP_NAME = "IDOMA"
APP_VERSION = "2.6.0"
DB_PATH = Path(os.getenv("IDOMA_DB_PATH", str(PROJECT_ROOT / "personal_ai.db"))).expanduser()
OLLAMA_URL = os.getenv("IDOMA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("IDOMA_OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_TIMEOUT = float(os.getenv("IDOMA_OLLAMA_TIMEOUT", "180"))
CLOUD_BASE_URL = os.getenv("IDOMA_CLOUD_BASE_URL", "").rstrip("/")
CLOUD_API_KEY = os.getenv("IDOMA_CLOUD_API_KEY", "")
CLOUD_MODEL = os.getenv("IDOMA_CLOUD_MODEL", "")
PREFER_LOCAL = os.getenv("IDOMA_PREFER_LOCAL", "1").lower() not in {"0", "false", "no"}
# Cloud use is opt-in: local data is never sent online just because Ollama is unavailable.
ALLOW_CLOUD = os.getenv("IDOMA_ALLOW_CLOUD", "0").lower() in {"1", "true", "yes"}
ENVIRONMENT = os.getenv("IDOMA_ENV", "development").lower()
CORS_ORIGINS = [x.strip() for x in os.getenv("IDOMA_CORS_ORIGINS", "*").split(",") if x.strip()]

MORNING_BRIEFING_TIME = os.getenv("IDOMA_MORNING_BRIEFING_TIME", "08:00").strip()
EVENING_BRIEFING_TIME = os.getenv("IDOMA_EVENING_BRIEFING_TIME", "21:00").strip()
