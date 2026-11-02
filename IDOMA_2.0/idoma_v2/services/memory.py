"""Structured personal memory helpers for IDOMA."""
from __future__ import annotations
import re
import unicodedata
from ..db import (save_memory_fact, list_memory_facts, find_memory_aliases, is_memory_suppressed, clear_memory_suppression, add_legacy_memory, get_legacy_memories)


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _canonical_subject(subject: str) -> tuple[str, list[str]]:
    raw = " ".join(subject.strip().split()).strip(" .,:;!?\"'")
    folded = _normalise(raw)
    if folded in {"curriculum", "curriculum vitae", "cv", "resume", "resumé"}:
        return "curriculum", ["curriculum", "curriculum vitae", "cv", "resume", "resumé"]
    if folded in {"tesi", "thesis", "tesi magistrale"}:
        return "tesi", ["tesi", "tesi magistrale", "thesis"]
    return raw.casefold(), [raw]


def parse_memory_instruction(message: str) -> tuple[str, str, list[str]] | None:
    """Recognise explicit user-authored concept -> filename associations."""
    text = message.strip()
    patterns = [
        r"^/associa\s+(.+?)\s*(?:=|:|->|\bcome\b|\bvuol dire\b)\s*(.+?)\s*$",
        r"^(?:idoma[, ]+)?(?:ricorda che\s+)?(?:il mio\s+|la mia\s+)?(.+?)\s+(?:si chiama|è|e')\s+(?:il file\s+|il documento\s+|il pdf\s+)?(.+?)\s*$",
        r"^(?:idoma[, ]+)?quando dico\s+(.+?)\s+(?:intendo|mi riferisco a)\s+(.+?)\s*$",
        r"^(.+?)\s*(?:=|->)\s*(.+?)\s*$",
    ]
    for index, pattern in enumerate(patterns):
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        subject, value = match.group(1).strip(), match.group(2).strip()
        subject = re.sub(r"^(?:il|la|mio|mia|file|documento)\s+", "", subject, flags=re.IGNORECASE).strip()
        value = re.sub(r"[.!?]+$", "", value).strip(" \t\"'“”‘’")
        # Keep this first release deliberately focused on personal file aliases.
        if _normalise(subject) not in {
            "curriculum", "curriculum vitae", "cv", "resume", "resumé",
            "tesi", "tesi magistrale", "thesis", "documento", "file"
        }:
            continue
        if not value or len(value) > 120:
            continue
        canonical, aliases = _canonical_subject(subject)
        return canonical, value, aliases
    return None


def remember_file_alias(message: str) -> bool:
    parsed = parse_memory_instruction(message)
    if not parsed:
        return False
    subject, value, aliases = parsed
    save_memory_fact("file_alias", subject, value, aliases, source="istruzione_esplicita_utente")
    return True


def aliases_for_search(query: str) -> list[str]:
    return find_memory_aliases(query)


def structured_memory_context(query: str = "", limit: int = 10) -> list[str]:
    """Return only structured facts relevant to the current request."""
    tokens = set(_normalise(query).split())
    if not tokens:
        return []
    ranked = []
    for item in list_memory_facts(200):
        searchable = _normalise(" ".join([
            str(item.get("subject", "")), str(item.get("value", "")),
            " ".join(item.get("aliases", [])),
        ]))
        score = sum(1 for token in tokens if token in searchable.split())
        if score:
            ranked.append((score, item.get("updated_at", ""), item["content"]))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [content for _, _, content in ranked[:max(1, min(int(limit), 30))]]


def parse_personal_memory_instruction(message: str) -> tuple[str, str, list[str]] | None:
    """Recognise explicit requests to remember basic personal identity facts."""
    text = " ".join(message.strip().split())
    patterns = [
        r"^(?:idoma[, ]+)?(?:ricorda(?:ti)? che|tieni a mente che|non dimenticare che)\s+(?:io\s+)?mi chiamo\s+(.+?)\s*[.!?]*$",
        r"^(?:idoma[, ]+)?(?:ricorda(?:ti)? che|tieni a mente che|non dimenticare che)\s+(?:il mio nome|il mio nominativo)\s+(?:è|e')\s+(.+?)\s*[.!?]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip(" \t,.:;!?\"'“”‘’")
        if not value or len(value) > 80:
            return None
        # Preserve the spelling supplied by the user while normalising an all-lowercase first letter.
        if value and value[0].islower():
            value = value[0].upper() + value[1:]
        return "nome", value, ["nome", "nome personale", "come mi chiamo"]
    return None


def remember_personal_fact(message: str, *, allow_override: bool = True) -> bool:
    parsed = parse_personal_memory_instruction(message)
    if not parsed:
        return False
    subject, value, aliases = parsed
    if is_memory_suppressed("personal", subject, value):
        if not allow_override:
            return False
        clear_memory_suppression("personal", subject, value)
    save_memory_fact("personal", subject, value, aliases, source="istruzione_esplicita_utente")
    return True


def personal_name_from_memory(legacy_memories: list[dict] | None = None) -> str | None:
    """Return a remembered name from structured or legacy personal memories."""
    facts = list_memory_facts(100)
    for item in facts:
        if item.get("category") == "personal" and item.get("subject", "").casefold() in {"nome", "name"}:
            value = str(item.get("value", "")).strip()
            if value and not is_memory_suppressed("personal", "nome", value):
                return value
    memories = legacy_memories or []
    patterns = (
        r"\bmi chiamo\s+([A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*(?:\s+[A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*)?)",
        r"\bil mio nome\s+(?:è|e')\s+([A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*(?:\s+[A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*)?)",
    )
    for item in memories:
        content = str(item.get("content", ""))
        for pattern in patterns:
            match = re.search(pattern, content, flags=re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name and not is_memory_suppressed("personal", "nome", name):
                    return name[0].upper() + name[1:]
    return None



def parse_device_memory_instruction(message: str) -> tuple[str, list[str]] | None:
    """Extract a computer/device model from an explicit remember instruction."""
    text = " ".join(message.strip().split())
    prefix = re.match(
        r"^(?:idoma[, ]+)?(?:ricorda(?:ti)? che|tieni a mente che|non dimenticare che)\s+(.+)$",
        text, flags=re.IGNORECASE,
    )
    if not prefix:
        return None
    fact = prefix.group(1).strip(" .!?")
    patterns = (
        r"^(?:ti scrivo|sto scrivendo) da\s+(?:un|una|il mio|la mia)?\s*(.+)$",
        r"^(?:uso|utilizzo|ho)\s+(?:un|una|il mio|la mia)?\s*(?:computer|pc|portatile|laptop)?\s*(.+)$",
        r"^(?:il mio|la mia)\s+(?:computer|pc|portatile|laptop)\s+(?:è|e')\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, fact, flags=re.IGNORECASE)
        if not match:
            continue
        device = re.sub(r"\s+", " ", match.group(1).strip(" \t,.;:!?\"'“”‘’"))
        if not device or len(device) > 120:
            return None
        device = re.sub(r"\blenovo\b", "Lenovo", device, flags=re.IGNORECASE)
        device = re.sub(r"\bideapad\b", "IdeaPad", device, flags=re.IGNORECASE)
        device = re.sub(r"\bflex\b", "Flex", device, flags=re.IGNORECASE)
        if device and device[0].islower():
            device = device[0].upper() + device[1:]
        return device, ["computer", "PC", "portatile", "laptop", "dispositivo", "Lenovo"]
    return None


def remember_general_personal_fact(message: str, *, allow_override: bool = True) -> str | None:
    """Save an explicit natural-language memory request, not arbitrary chat."""
    text = " ".join(message.strip().split())
    prefix = re.match(
        r"^(?:idoma[, ]+)?(?:ricorda(?:ti)? che|tieni a mente che|non dimenticare che)\s+(.+)$",
        text, flags=re.IGNORECASE,
    )
    if not prefix:
        return None
    fact = prefix.group(1).strip(" .!?")
    if not fact or len(fact) > 500:
        return None
    device = parse_device_memory_instruction(message)
    if device:
        value, aliases = device
        if is_memory_suppressed("personal", "computer", value) and not allow_override:
            return None
        if allow_override:
            clear_memory_suppression("personal", "computer", value)
        save_memory_fact("personal", "computer", value, aliases, source="istruzione_esplicita_utente")
        add_legacy_memory(f"Computer: {value}", "istruzione_esplicita_utente")
        return f"Computer: {value}"
    if allow_override:
        add_legacy_memory(fact, "istruzione_esplicita_utente")
    return fact


def personal_device_from_memory() -> str | None:
    """Return the remembered computer model, preferring structured memory."""
    for item in list_memory_facts(200):
        if item.get("category") == "personal" and item.get("subject", "").casefold() in {"computer", "pc", "portatile"}:
            value = str(item.get("value", "")).strip()
            if value and not is_memory_suppressed("personal", "computer", value):
                return value
    for item in get_legacy_memories(200):
        match = re.search(r"^computer:\s*(.+)$", str(item.get("content", "")), flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None
