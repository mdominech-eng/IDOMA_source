from __future__ import annotations

import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from dataclasses import dataclass

from ..config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, PREFER_LOCAL,
)


class ProviderUnavailable(RuntimeError):
    pass


@dataclass
class AIResponse:
    content: str
    provider: str
    model: str


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ask_ollama(messages: list[dict]) -> AIResponse:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096, "num_predict": 700, "num_thread": 4},
    }
    data = _post_json(OLLAMA_URL, payload, {}, OLLAMA_TIMEOUT)
    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise ProviderUnavailable("Ollama ha restituito una risposta vuota.")
    return AIResponse(content, "ollama", OLLAMA_MODEL)


def _ask_cloud(messages: list[dict]) -> AIResponse:
    if not (CLOUD_BASE_URL and CLOUD_API_KEY and CLOUD_MODEL):
        raise ProviderUnavailable(
            "Nessun modello online configurato. Per ora avvia Ollama sul PC oppure configura un provider cloud in .env."
        )
    url = CLOUD_BASE_URL + "/chat/completions"
    payload = {"model": CLOUD_MODEL, "messages": messages, "temperature": 0.7}
    data = _post_json(url, payload, {"Authorization": f"Bearer {CLOUD_API_KEY}"}, 90)
    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise ProviderUnavailable("Il provider cloud ha restituito un formato di risposta non riconosciuto.")
    if not content:
        raise ProviderUnavailable("Il provider cloud ha restituito una risposta vuota.")
    return AIResponse(content, "cloud", CLOUD_MODEL)


def ask_ai(messages: list[dict]) -> AIResponse:
    errors = []
    providers = ([_ask_ollama, _ask_cloud] if PREFER_LOCAL else [_ask_cloud, _ask_ollama])
    for provider in providers:
        try:
            return provider(messages)
        except (URLError, TimeoutError, HTTPError, OSError, ValueError, ProviderUnavailable) as exc:
            errors.append(str(exc))
    raise ProviderUnavailable("; ".join(errors) or "Nessun provider AI disponibile.")
