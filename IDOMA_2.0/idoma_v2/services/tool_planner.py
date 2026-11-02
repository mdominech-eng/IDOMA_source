"""Generic intent routing for safe Windows desktop tools."""
from __future__ import annotations
import re
from typing import Any

FOLDER_ALIASES = {
    "documents": ("documenti", "documents"),
    "downloads": ("download", "downloads", "scaricati"),
    "desktop": ("desktop", "scrivania"),
    "pictures": ("immagini", "immagine", "galleria", "gallery", "foto", "photos", "pictures", "images"),
    "music": ("musica", "music", "audio", "brani"),
    "videos": ("video", "filmati", "movies"),
}


def _normalise(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split()).strip(" \t,.:;!?\"'")


def is_negated_action(text: str) -> bool:
    """Recognise explicit Italian negation before a desktop action."""
    value = _normalise(text)
    return bool(re.search(
        r"\bnon\s+(?:(?:mi|lo|la|li|le)\s+)?(?:apr\w*|avvi\w*|lanci\w*|cerc\w*|trov\w*|mostr\w*|vai\s+su|andare\s+su)\b"
        r"|\bnon\s+(?:voglio|devo|devi|serve|occorre)\s+(?:che\s+tu\s+)?(?:apra|apri|aprire|avvii|avviare|lanci|lanciare|cerchi|cercare|trovi|trovare)\b",
        value,
    ))


def _folder_from_text(text: str) -> str | None:

    value = _normalise(text)
    if not re.search(r"\b(apri|aprimi|aprire|mi apri|puoi aprire|potresti aprire|fammi vedere|mostra|vai|visualizza|raggiungi|portami|entra)\b", value):
        return None
    has_folder_context = bool(re.search(r"\b(cartella|directory|folder|contenuto|file)\b", value))
    for folder, aliases in FOLDER_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", value):
                # A direct folder alias after an open verb is sufficient. If the user
                # names an application explicitly, leave it to open_target instead.
                if has_folder_context or alias in {"galleria", "gallery", "immagini", "musica", "music", "download", "downloads", "documenti", "scrivania", "filmati"}:
                    return folder
    return None


def _search_query(text: str) -> str:
    value = _normalise(text)
    value = re.sub(r"\b(idoma|per favore|per piacere|per cortesia|gentilmente|per caso)\b", " ", value)
    value = re.sub(
        r"\b(trova|trovami|cerca|cercami|ricerca|individua|mostra|fammi vedere|apri|aprimi|dove ho salvato|dove si trova|"
        r"nei miei|nel mio|tra i miei|fra i miei|un|una|il|lo|la|i|gli|le|dei|degli|delle|file|documento|"
        r"documenti|pdf|word|excel|cartella|sul pc|sul computer|nel computer|nel pc|nei|nelle|nella|nel|della|dello|del|di|da|che|si|chiama|chiamato|chiamata|nome|denominato|denominata|miei|mie|mio|mia|su|sul|sulla|per|grazie|ultima|ultimo|versione|del|della)\b",
        " ", value,
    )
    value = re.sub(r"\s+", " ", value).strip(" \t,.:;!?\"'")
    return value[:120]



def _document_content_query(text: str) -> str | None:
    """Extract a topic when the user asks where a term occurs in personal files."""
    value = _normalise(text).rstrip(" ?!.")

    # Natural requests such as "trova sustainability nei miei file" should
    # search document contents, not filenames.
    captured_patterns = [
        r"^(?:trova|trovami|cerca|cercami|ricerca|individua)\s+(?:la\s+)?(?:parola\s+|frase\s+)?(.+?)\s+(?:nei|negli|nelle|nella|nel|dentro\s+i|dentro\s+le|tra\s+i|fra\s+i)\s+(?:miei\s+)?(?:file|documenti|documento|pdf|word|excel|fogli|presentazioni)$",
        r"^(?:dove\s+(?:ho|avevo)\s+scritto|in\s+quale\s+file\s+(?:ho|avevo)\s+scritto|in\s+quali\s+file\s+(?:ho|avevo)\s+scritto|in\s+quale\s+documento\s+(?:ho|avevo)\s+scritto)\s+(.+?)(?:\s+(?:nei|negli|nelle|nella|nel)\s+(?:miei\s+)?(?:file|documenti|pdf|word|excel))?$",
        r"^(?:in\s+quali\s+file|quali\s+file)\s+(?:ho|avevo)\s+scritto\s+(.+)$",
    ]
    for pattern in captured_patterns:
        match = re.match(pattern, value)
        if match:
            query = match.group(1)
            query = re.sub(r"\b(?:la|il|lo|un|una|parola|frase)\b", " ", query)
            query = re.sub(r"\s+", " ", query).strip(" \\t,.:;!?\\\"'")
            return query[:120] if len(query) >= 2 else None

    # More descriptive formulations: "trova il documento in cui si parla di..."
    patterns = [
        r"(?:cerca|cercami|ricerca|trova|trovami|individua)\s+(?:dentro|all(?:'|\s+)interno(?:\s+(?:di|dei|delle|della|del))?)\s+(?:(?:i|le|dei|delle|della|del)\s+)?(?:miei\s+)?(?:file|documenti|pdf|word|excel|fogli|presentazioni)\s+(?:la\s+)?(?:frase|parola)?\s*",
        r"(?:cerca|cercami|ricerca|trova|trovami|individua)\s+(?:nel\s+contenuto\s+dei\s+file|nel\s+contenuto\s+dei\s+documenti|nei\s+contenuti\s+dei\s+file)\s*",
        r"(?:trova|trovami|individua|cerca|cercami)\s+(?:il\s+)?documento\s+(?:in\s+cui\s+si\s+parla\s+(?:di|del|della|dei|degli|delle)|che\s+parla\s+(?:di|del|della)|che\s+contiene|dove\s+(?:ho|avevo)\s+scritto)\s*",
        r"(?:quale|qual)\s+documento\s+(?:contiene|parla\s+(?:di|del|della))\s*",
        r"mi\s+ricordi\s+in\s+quale\s+(?:file|documento)\s+(?:(?:ho|avevo)\s+)?scritto\s*",
        r"(?:in\s+quale|in\s+che)\s+(?:file|documento)\s+(?:(?:ho|avevo)\s+)?(?:scritto|parlato\s+di|menzionato)\s*",
        r"(?:dove\s+(?:ho|avevo)\s+scritto|in\s+quale\s+file\s+(?:ho|avevo)\s+parlato\s+di)\s*",
        r"(?:cerca|cercami|ricerca)\s+(?:nei\s+documenti|nei\s+file)\s+(?:dove\s+si\s+parla\s+(?:di|del|della)|che\s+parlano\s+(?:di|del|della)|che\s+contengono)\s*",
    ]
    query = value
    matched = False
    for pattern in patterns:
        cleaned, count = re.subn(pattern, "", query, count=1)
        if count:
            query = cleaned
            matched = True
            break
    if not matched:
        return None
    query = re.sub(r"\b(per favore|per piacere|per cortesia|gentilmente|mio|mia|miei|mie|il|lo|la|i|gli|le|un|una|di|del|della|dei|degli|delle|nel|nella|nei|nelle|che|si|parla|parlano|contiene|contengono|scritto|menzionato|file|documento|documenti|pdf|word|excel|foglio|fogli|presentazione|frase|parola)\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip(" \\t,.:;!?\\\"'")
    return query[:120] if len(query) >= 2 else None

def _is_file_search(text: str) -> bool:
    value = _normalise(text)
    has_verb = bool(re.search(r"\b(trova|trovami|cerca|cercami|ricerca|individua|dove ho salvato|dove si trova|mostra|aprimi|apri)\b", value))
    has_file_context = bool(re.search(r"\b(file|documento|documenti|pdf|word|excel|cartella|curriculum|cv|tesi|curriculum vitae)\b", value))
    return has_verb and has_file_context


def _is_pc_status(text: str) -> bool:
    value = _normalise(text)
    return bool(re.search(r"\b(stato del pc|stato del computer|com'e messo il pc|com'è messo il pc|informazioni sul pc|informazioni sul computer|spazio disponibile|spazio sul disco|quanto spazio|quanta memoria|risorse del pc|risorse del computer)\b", value))


def detect_additional_tool(message: str) -> tuple[str, dict] | None:
    if is_negated_action(message):
        return None
    folder = _folder_from_text(message)
    if folder:
        return "open_folder", {"folder": folder}
    content_query = _document_content_query(message)
    if content_query:
        return "search_document_content", {"query": content_query, "location": "all"}
    if _is_file_search(message):
        query = _search_query(message)
        if query:
            location = "all"
            value = _normalise(message)
            if "download" in value or "scaricat" in value:
                location = "downloads"
            elif "desktop" in value or "scrivania" in value:
                location = "desktop"
            elif "document" in value:
                location = "documents"
            elif any(x in value for x in ("immagini", "immagine", "galleria", "foto")):
                location = "pictures"
            elif any(x in value for x in ("musica", "music")):
                location = "music"
            elif "video" in value or "filmati" in value:
                location = "videos"
            open_first = bool(re.search(r"\b(apri|aprimi)\b", value))
            return "search_files", {"query": query, "location": location, "open_first": open_first}
    if _is_pc_status(message):
        return "pc_status", {}
    match = re.search(r"(?:[A-Za-z]:\\|\\\\)[^\r\n<>|?*\"]+", message)
    if match and re.search(r"\b(apri|mostra|visualizza)\b", message, re.IGNORECASE):
        return "open_path", {"path": match.group(0).strip().rstrip(" .,;:!?")}
    return None


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {"name": "open_target", "description": "Aprire un'applicazione installata o un sito HTTPS.", "location": "Windows"},
        {"name": "search_files", "description": "Cercare file per nome nelle cartelle personali Windows, anche usando alias memorizzati.", "location": "Windows"},
        {"name": "search_document_content", "description": "Cercare parole e argomenti all'interno di PDF, Word, Excel, PowerPoint e file di testo personali.", "location": "Windows"},
        {"name": "open_folder", "description": "Aprire Desktop, Documenti, Download, Immagini, Musica o Video secondo le cartelle personali configurate in Windows.", "location": "Windows"},
        {"name": "open_path", "description": "Aprire un percorso locale autorizzato nelle cartelle personali.", "location": "Windows"},
        {"name": "pc_status", "description": "Leggere informazioni essenziali sul PC e sullo spazio disco.", "location": "Windows"},
    ]
