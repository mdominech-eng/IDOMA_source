from __future__ import annotations

import json
import difflib
import re
import unicodedata
import os
import platform
import datetime
import shutil
import subprocess
import time
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, quote_plus

from .config import RELEASE_DIR
from .security import get_api_token
from .db import upsert_indexed_documents, list_indexed_documents, list_indexed_document_metadata

SERVER_URL = os.getenv("IDOMA_SERVER_URL", f"http://127.0.0.1:{os.getenv('IDOMA_PORT', '8000')}").rstrip("/")
TOKEN = get_api_token()
DEVICE_ID = os.getenv("IDOMA_DEVICE_ID", platform.node().lower().replace(" ", "-")[:100])
DEVICE_NAME = os.getenv("IDOMA_DEVICE_NAME", f"PC Windows · {platform.node()}")
POLL_SECONDS = 1.0


def api_post(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        SERVER_URL + path,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))



def _normalise_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value)


def _find_start_menu_shortcut(target: str) -> Path | None:
    """Find an installed app shortcut, checking exact names before fuzzy matches."""
    roots = [
        Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.getenv("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    desktop = Path.home() / "Desktop"
    wanted = _normalise_name(target)
    if not wanted:
        return None

    def shortcuts_in(root: Path, recursive: bool):
        if not root.is_dir():
            return
        try:
            items = root.rglob("*") if recursive else root.glob("*")
            for item in items:
                if item.is_file() and item.suffix.casefold() in {".lnk", ".url", ".appref-ms"}:
                    yield item
        except (OSError, PermissionError):
            return

    # Exact match pass first: common requests like "Spotify" should be quick.
    for root in roots:
        for shortcut in shortcuts_in(root, recursive=True):
            if _normalise_name(shortcut.stem) == wanted:
                return shortcut
    # Desktop shortcuts are checked only at top level to avoid scanning personal folders.
    for shortcut in shortcuts_in(desktop, recursive=False):
        if _normalise_name(shortcut.stem) == wanted:
            return shortcut

    candidates: list[tuple[float, Path]] = []
    for root in roots:
        for shortcut in shortcuts_in(root, recursive=True):
            stem = _normalise_name(shortcut.stem)
            if not stem:
                continue
            score = difflib.SequenceMatcher(None, wanted, stem).ratio()
            if wanted in stem or stem in wanted:
                score = max(score, 0.88)
            if score >= 0.78:
                candidates.append((score, shortcut))
    for shortcut in shortcuts_in(desktop, recursive=False):
        stem = _normalise_name(shortcut.stem)
        if stem:
            score = difflib.SequenceMatcher(None, wanted, stem).ratio()
            if wanted in stem or stem in wanted:
                score = max(score, 0.88)
            if score >= 0.78:
                candidates.append((score, shortcut))
    if candidates:
        candidates.sort(key=lambda item: (item[0], -len(str(item[1]))), reverse=True)
        if len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.08:
            return candidates[0][1]
    return None


def _open_safe_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Indirizzo web non valido: è richiesto un URL HTTPS.")
    webbrowser.open(url)
    return f"Aperto il sito {parsed.netloc}."


def _try_registered_protocol(target: str) -> bool:
    """Open only a small allowlist of benign Windows application protocols."""
    scheme = target.strip().casefold().rstrip(":")
    allowed = {
        "spotify", "steam", "ms-settings", "vscode", "slack",
        "zoommtg", "msteams", "teams", "mailto", "discord",
    }
    if scheme not in allowed:
        return False
    try:
        os.startfile(f"{scheme}:")  # type: ignore[attr-defined]
        return True
    except (OSError, ValueError):
        return False


def _open_generic_target(payload: dict) -> str:
    target = str(payload.get("target", "")).strip()
    target_type = str(payload.get("target_type", "auto"))
    url = payload.get("url")
    if not target or len(target) > 100:
        raise ValueError("Non ho riconosciuto il nome dell'app o del sito da aprire.")

    # Prefer an installed desktop app when the user did not explicitly provide
    # a website URL. Some local models label app names as "website" but omit URL.
    if target_type == "website" and isinstance(url, str) and url.strip():
        return _open_safe_url(url.strip())

    shortcut = _find_start_menu_shortcut(target)
    if shortcut is not None:
        os.startfile(str(shortcut))  # type: ignore[attr-defined]
        return f"Avviata l'applicazione {target} dal menu Start."

    if isinstance(url, str) and url.strip():
        return _open_safe_url(url.strip())

    # Generic fallback for applications registered with Windows URI protocols
    # (e.g. Spotify's protocol), without hardcoding a catalogue of app names.
    if _try_registered_protocol(target):
        return f"Avviata {target} tramite il protocollo registrato in Windows."

    if target_type == "app":
        raise FileNotFoundError(
            f"Non trovo {target} tra le applicazioni installate nel menu Start né tramite il protocollo registrato di Windows."
        )

    # Generic fallback: never guess a domain for an unknown service.
    search_url = "https://www.google.com/search?q=" + quote_plus(target + " official website")
    webbrowser.open(search_url)
    return f"Non ho trovato un'app installata per {target}; ho aperto una ricerca web per trovare il sito ufficiale."

def _known_windows_folder(folder: str) -> Path | None:
    """Resolve Windows Known Folders by their system IDs, independent of language/location."""
    if os.name != "nt":
        return None
    import ctypes
    import uuid
    from ctypes import wintypes

    known_ids = {
        "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
        "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
        "downloads": "374DE290-123F-4565-9164-39C4925E467B",
        "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
        "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
        "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
    }
    guid_text = known_ids.get(folder)
    if not guid_text:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    guid = GUID.from_buffer_copy(uuid.UUID(guid_text).bytes_le)
    result = ctypes.c_wchar_p()
    try:
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(result))
        if hr != 0 or not result.value:
            return None
        return Path(result.value)
    except Exception:
        return None
    finally:
        if result:
            try:
                ctypes.windll.ole32.CoTaskMemFree(result)
            except Exception:
                pass


def _user_roots() -> dict[str, Path]:
    """Return existing Windows Known Folders, including relocated/OneDrive folders."""
    home = Path.home()
    fallbacks = {
        "desktop": [home / "Desktop", home / "Scrivania"],
        "documents": [home / "Documents", home / "Documenti"],
        "downloads": [home / "Downloads", home / "Download"],
        "pictures": [home / "Pictures", home / "Immagini", home / "Photos", home / "Foto"],
        "music": [home / "Music", home / "Musica"],
        "videos": [home / "Videos", home / "Video"],
    }
    roots: dict[str, Path] = {}
    for key, candidates in fallbacks.items():
        known = _known_windows_folder(key)
        chosen = known if known and known.is_dir() else next((p for p in candidates if p.is_dir()), None)
        if chosen:
            roots[key] = chosen.resolve()
    return roots


def _normalise_search_text(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _search_files(payload: dict) -> str:
    query = str(payload.get("query", "")).strip()
    location = str(payload.get("location", "all")).casefold().strip()
    aliases = payload.get("aliases", [])
    if not query or len(query) > 120:
        raise ValueError("Specifica un nome o una parte del nome del file da cercare.")
    roots = _user_roots()
    if location != "all":
        if location not in roots:
            raise FileNotFoundError("La cartella scelta non è disponibile tra le cartelle personali configurate in Windows.")
        roots = {location: roots[location]}
    search_terms = [query]
    if isinstance(aliases, list):
        search_terms.extend(str(x)[:120] for x in aliases if str(x).strip())
    normalised_terms = []
    for term in search_terms:
        norm = _normalise_search_text(term)
        if norm and norm not in normalised_terms:
            normalised_terms.append(norm)
    if not normalised_terms:
        raise ValueError("La ricerca deve contenere almeno due caratteri utili.")

    matches: list[tuple[int, Path]] = []
    scanned = 0
    started = time.monotonic()
    max_files = 25000
    max_seconds = 7.0
    ignored = {"appdata", "node_modules", "__pycache__", "$recycle.bin", "system volume information"}
    for root in roots.values():
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.casefold() not in ignored]
            for name in files:
                scanned += 1
                candidate = Path(current) / name
                stem = _normalise_search_text(candidate.stem)
                tokens = set(stem.split())
                score = 0
                for term in normalised_terms:
                    term_tokens = term.split()
                    if stem == term:
                        score = max(score, 120)
                    elif term in stem and len(term) >= 4:
                        score = max(score, 70)
                    elif len(term_tokens) > 1 and term in stem:
                        score = max(score, 90)
                    elif all(token in tokens for token in term_tokens):
                        score = max(score, 55 if len(term_tokens) > 1 else 45)
                    elif any(len(token) >= 4 and token in stem for token in term_tokens):
                        score = max(score, 15)
                if score:
                    matches.append((score, candidate))
                if scanned >= max_files or time.monotonic() - started >= max_seconds:
                    break
            if scanned >= max_files or time.monotonic() - started >= max_seconds:
                break
        if scanned >= max_files or time.monotonic() - started >= max_seconds:
            break
    matches.sort(key=lambda item: (item[0], item[1].name.casefold()), reverse=True)
    if not matches:
        return f"Non ho trovato file con nome compatibile con '{query}' nelle cartelle personali cercate. Ho esaminato {scanned} file."
    if payload.get("open_first"):
        safe_extensions = {".pdf", ".doc", ".docx", ".rtf", ".txt", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}
        unique_best = len(matches) == 1 or matches[0][0] > matches[1][0]
        best = matches[0][1]
        if unique_best and best.suffix.casefold() in safe_extensions:
            os.startfile(str(best))  # type: ignore[attr-defined]
            return f"Ho aperto il file {best.name}: {best}."
    lines = [f"Ho trovato {len(matches)} corrispondenza/e per '{query}' (mostro al massimo 10):"]
    if payload.get("open_first"):
        lines.append("Ho trovato più possibilità oppure il primo risultato non è un documento apribile automaticamente. Dimmi quale vuoi aprire.")
    for index, (score, path) in enumerate(matches[:10], 1):
        lines.append(f"{index}. {path.name} — {path}")
    if scanned >= max_files or time.monotonic() - started >= max_seconds:
        lines.append(f"Ricerca interrotta al limite di sicurezza ({scanned} file o 7 secondi).")
    return "\n".join(lines)



SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".rtf"}


def _extract_document_text(path: Path) -> str:
    """Extract readable text with source locations; unsupported legacy formats are skipped."""
    suffix = path.suffix.casefold()
    chunks: list[str] = []
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    return ""
            except Exception:
                return ""
        for page_no, page in enumerate(reader.pages[:60], 1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                chunks.append(f"[Pagina {page_no}] {text}")
    elif suffix == ".docx":
        from docx import Document
        document = Document(str(path))
        for number, paragraph in enumerate(document.paragraphs, 1):
            if paragraph.text.strip():
                chunks.append(f"[Paragrafo {number}] {paragraph.text}")
        for table_no, table in enumerate(document.tables, 1):
            for row_no, row in enumerate(table.rows, 1):
                values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                line = " | ".join(value for value in values if value)
                if line:
                    chunks.append(f"[Tabella {table_no}, riga {row_no}] {line}")
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(str(path), read_only=True, data_only=True)
        try:
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows():
                    values = []
                    for cell in row:
                        if cell.value is not None:
                            value = str(cell.value).strip()
                            if value:
                                values.append(f"{cell.coordinate}: {value}")
                    if values:
                        chunks.append(f"[Foglio {sheet.title}] " + " | ".join(values))
                    if sum(map(len, chunks)) >= 140000:
                        break
                if sum(map(len, chunks)) >= 140000:
                    break
        finally:
            workbook.close()
    elif suffix == ".pptx":
        from pptx import Presentation
        presentation = Presentation(str(path))
        for slide_no, slide in enumerate(presentation.slides, 1):
            values = [shape.text.strip() for shape in slide.shapes if getattr(shape, "has_text_frame", False) and shape.text.strip()]
            if values:
                chunks.append(f"[Diapositiva {slide_no}] " + " | ".join(values))
    elif suffix in {".txt", ".md", ".csv", ".rtf"}:
        raw = ""
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                raw = path.read_text(encoding=encoding, errors="strict")
                break
            except (UnicodeError, OSError):
                continue
        if suffix == ".rtf":
            raw = re.sub(r"\\'[0-9a-fA-F]{2}", " ", raw)
            raw = re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", " ", raw)
        chunks.extend(line.strip() for line in raw.splitlines() if line.strip())
    return "\n".join(chunks)[:80000]


def _search_document_content(payload: dict) -> str:
    """Incrementally index supported local documents, then rank matching snippets."""
    query = str(payload.get("query", "")).strip()
    location = str(payload.get("location", "all")).casefold().strip()
    aliases = payload.get("aliases", [])
    if not query or len(query) > 120:
        raise ValueError("Dimmi quale argomento o frase cercare dentro i documenti.")

    roots = _user_roots()
    if location != "all":
        if location not in roots:
            raise FileNotFoundError("La cartella scelta non è disponibile tra le cartelle personali configurate in Windows.")
        roots = {location: roots[location]}

    terms = [query]
    if isinstance(aliases, list):
        terms.extend(str(item)[:120] for item in aliases if str(item).strip())
    normalized_terms = []
    for term in terms:
        normalized = _normalise_search_text(term)
        if normalized and normalized not in normalized_terms:
            normalized_terms.append(normalized)
    query_tokens = list(dict.fromkeys(token for term in normalized_terms for token in term.split() if len(token) >= 3))
    if not query_tokens:
        raise ValueError("La ricerca deve contenere almeno una parola di almeno tre lettere.")

    scanned = indexed_now = cached = skipped = 0
    cached_entries = {item["path"]: item for item in list_indexed_document_metadata()}
    pending_index: list[tuple[str, int, int, str, str]] = []
    started = time.monotonic()
    max_files, max_seconds = 12000, 24.0
    max_file_bytes = 20 * 1024 * 1024
    max_indexed_documents = 1200
    ignored = {"appdata", "node_modules", "__pycache__", "$recycle.bin", "system volume information", ".git", ".venv"}
    complete = True
    for root in roots.values():
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.casefold() not in ignored]
            for name in files:
                candidate = Path(current) / name
                if candidate.suffix.casefold() not in SUPPORTED_DOCUMENT_EXTENSIONS:
                    continue
                scanned += 1
                try:
                    resolved = candidate.resolve(strict=True)
                    if not any(resolved == base or base in resolved.parents for base in roots.values()):
                        skipped += 1
                        continue
                    stat = resolved.stat()
                    if stat.st_size <= 0 or stat.st_size > max_file_bytes:
                        skipped += 1
                        continue
                    old = cached_entries.get(str(resolved))
                    if old and old["modified_ns"] == stat.st_mtime_ns and old["size_bytes"] == stat.st_size:
                        cached += 1
                    elif not old and len(cached_entries) + len(pending_index) >= max_indexed_documents:
                        skipped += 1
                        complete = False
                        break
                    else:
                        try:
                            content = _extract_document_text(resolved)
                        except Exception:
                            skipped += 1
                            content = ""
                        if content.strip():
                            pending_index.append((str(resolved), stat.st_mtime_ns, stat.st_size, resolved.suffix, content))
                            indexed_now += 1
                        else:
                            skipped += 1
                except (OSError, PermissionError):
                    skipped += 1
                if scanned >= max_files or time.monotonic() - started >= max_seconds:
                    complete = False
                    break
            if not complete:
                break
        if not complete:
            break

    upsert_indexed_documents(pending_index)
    results: list[tuple[int, str, str, str]] = []
    allowed_roots = [base.resolve() for base in roots.values()]
    for item in list_indexed_documents():
        path = Path(item["path"])
        if not any(path == base or base in path.parents for base in allowed_roots):
            continue
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            if stat.st_mtime_ns != item["modified_ns"] or stat.st_size != item["size_bytes"]:
                continue
        except OSError:
            continue
        content = item["content"] or ""
        normalized_content = _normalise_search_text(content)
        best_line, best_score = "", 0
        for line in content.splitlines():
            normalized_line = _normalise_search_text(line)
            matched = [token for token in query_tokens if token in normalized_line]
            if not matched:
                continue
            score = len(matched) * 5 + sum(min(normalized_line.count(token), 4) for token in matched)
            if any(term and term in normalized_line for term in normalized_terms):
                score += 12
            if score > best_score:
                best_score, best_line = score, line
        if best_score:
            if any(term and term in normalized_content for term in normalized_terms):
                best_score += 5
            snippet = re.sub(r"\s+", " ", best_line).strip()
            if len(snippet) > 260:
                snippet = snippet[:257] + "..."
            results.append((best_score, item["path"], snippet, item["extension"]))

    results.sort(key=lambda item: (item[0], Path(item[1]).name.casefold()), reverse=True)
    if not results:
        note = " La scansione è stata parziale: ripeti la ricerca per completarla." if not complete else ""
        return (f"Non ho trovato corrispondenze per '{query}' nel contenuto dei documenti supportati. "
                f"File esaminati: {scanned}; nuovi documenti indicizzati: {indexed_now}; già in cache: {cached}; non leggibili o esclusi: {skipped}." + note)

    lines = [f"Ho trovato {len(results)} documento/i con contenuti compatibili con '{query}' (mostro i primi 8):"]
    for index, (score, path, snippet, extension) in enumerate(results[:8], 1):
        lines.append(f"{index}. {Path(path).name} ({extension})\n   Percorso: {path}\n   Estratto: {snippet}")
    lines.append(f"\nIndicizzazione: {indexed_now} nuovi/aggiornati, {cached} già in cache; {scanned} file controllati.")
    if not complete:
        lines.append("La scansione ha raggiunto il limite di sicurezza; ripeti la ricerca per continuare l'indicizzazione.")
    return "\n".join(lines)

def _open_folder(payload: dict) -> str:
    folder = str(payload.get("folder", "")).casefold().strip()
    roots = _user_roots()
    if folder not in roots:
        raise FileNotFoundError(f"La cartella personale '{folder}' non è stata trovata o non è configurata in Windows.")
    os.startfile(str(roots[folder]))  # type: ignore[attr-defined]
    return f"Aperta la cartella {roots[folder].name}."


def _open_path(payload: dict) -> str:
    raw = str(payload.get("path", "")).strip().strip('"')
    if not raw or len(raw) > 500:
        raise ValueError("Percorso non valido.")
    candidate = Path(raw).expanduser().resolve(strict=True)
    roots = list(_user_roots().values())
    allowed = False
    for root in roots:
        try:
            candidate.relative_to(root.resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise PermissionError("Per sicurezza posso aprire solo elementi nelle cartelle Desktop, Documenti e Download.")
    os.startfile(str(candidate))  # type: ignore[attr-defined]
    return f"Aperto: {candidate.name}."


def _pc_status() -> str:
    home_drive = Path.home().anchor or str(Path.home())
    usage = shutil.disk_usage(home_drive)
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    return (f"PC: {platform.node()}\nSistema: {platform.platform()}\n"
            f"Spazio libero sul disco principale: {free_gb:.1f} GB su {total_gb:.1f} GB.")


def _open_user_url(url: str) -> str:
    parsed = urlparse(url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Sono ammessi solo indirizzi HTTPS e HTTP verso il PC locale.")
    webbrowser.open(url)
    return f"Aperto il sito {url}."


def execute_task(action: str, payload: dict) -> str:
    """Execute only registered, constrained desktop tools. Never run generated shell commands."""
    if os.name != "nt":
        raise RuntimeError("L'agente desktop attualmente supporta Windows.")

    tools = {
        "open_target": _open_generic_target,
        "search_files": _search_files,
        "search_document_content": _search_document_content,
        "open_folder": _open_folder,
        "open_path": _open_path,
        "pc_status": lambda _payload: _pc_status(),
    }
    if action in tools:
        return tools[action](payload)

    if action == "open_spotify":
        try:
            os.startfile("spotify:")  # type: ignore[attr-defined]
        except OSError:
            webbrowser.open("https://open.spotify.com")
        return "Richiesta di apertura Spotify inviata."

    if action == "open_chrome":
        chrome = shutil.which("chrome")
        if chrome:
            subprocess.Popen([chrome], close_fds=True)
        else:
            try:
                os.startfile("chrome")  # type: ignore[attr-defined]
            except OSError:
                webbrowser.open("https://www.google.com")
        return "Richiesta di apertura del browser inviata."

    if action == "open_documents":
        path = Path.home() / "Documents"
        if not path.exists():
            path = Path.home() / "Documenti"
        if not path.exists():
            raise FileNotFoundError("Cartella Documenti non trovata.")
        os.startfile(str(path))  # type: ignore[attr-defined]
        return f"Aperta la cartella {path}."

    if action == "open_downloads":
        path = Path.home() / "Downloads"
        if not path.exists():
            path = Path.home() / "Download"
        if not path.exists():
            raise FileNotFoundError("Cartella Download non trovata.")
        os.startfile(str(path))  # type: ignore[attr-defined]
        return f"Aperta la cartella {path}."

    if action == "open_url":
        return _open_user_url(str(payload.get("url", "")))

    raise ValueError(f"Azione non autorizzata: {action}")


def run_agent(stop_event=None, status_callback=None, quiet: bool = True) -> None:
    """Run the Windows task worker in-process or as a standalone process."""
    if os.name != "nt":
        raise RuntimeError("L'agente desktop IDOMA è destinato a Windows.")

    def report(message: str) -> None:
        if status_callback:
            try:
                status_callback(message)
            except Exception:
                pass
        if not quiet:
            print(message, flush=True)

    report("IDOMA Desktop Agent avviato.")
    report(f"Server: {SERVER_URL}")
    heartbeat = {"device_id": DEVICE_ID, "device_name": DEVICE_NAME}
    while stop_event is None or not stop_event.is_set():
        try:
            result = api_post("/api/agent/claim", heartbeat)
            task = result.get("task")
            if task:
                task_id = int(task["id"])
                report(f"Attività #{task_id} ricevuta.")
                try:
                    message = execute_task(task["action"], task.get("payload") or {})
                    api_post("/api/agent/result", {"task_id": task_id, "result": message, "success": True})
                    report(f"Attività #{task_id} completata.")
                except Exception as exc:
                    api_post("/api/agent/result", {"task_id": task_id, "result": str(exc), "success": False})
                    report(f"Attività #{task_id} non riuscita: {exc}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            report(f"Server non raggiungibile: {exc}")
        if stop_event is not None:
            stop_event.wait(POLL_SECONDS)
        else:
            time.sleep(POLL_SECONDS)


def main() -> None:
    try:
        run_agent(quiet=False)
    except RuntimeError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
