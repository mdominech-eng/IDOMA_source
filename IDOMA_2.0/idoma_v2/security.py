from __future__ import annotations

import os
import secrets
from pathlib import Path
from .config import ENVIRONMENT, RELEASE_DIR

TOKEN_FILE = RELEASE_DIR / ".idoma_token"


def get_api_token() -> str:
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
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    print("\n[IDOMA] Creato il token personale API. Inseriscilo nelle impostazioni dell'app web:")
    print(token)
    print(f"[IDOMA] Copia di sicurezza del token: {TOKEN_FILE}\n")
    return token
