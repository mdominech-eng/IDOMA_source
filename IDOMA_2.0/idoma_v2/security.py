from __future__ import annotations

import os
import secrets
from pathlib import Path

from .config import ENVIRONMENT, RELEASE_DIR

TOKEN_FILE = RELEASE_DIR / ".idoma_token"


def get_api_token() -> str:
    """Return the local API token without ever printing it to stdout or logs."""
    configured = os.getenv("IDOMA_API_TOKEN", "").strip()
    if configured:
        return configured

    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token

    if ENVIRONMENT == "production":
        raise RuntimeError("In produzione devi impostare IDOMA_API_TOKEN.")

    token = secrets.token_urlsafe(36)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        # Windows ACLs are managed by the current user's profile permissions.
        pass
    return token
