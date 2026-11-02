from __future__ import annotations

import sqlite3
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from .config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Adds IDOMA 2 tables. Existing tables and records are never dropped or rewritten."""
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS idoma2_conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Nuova conversazione',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idoma2_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES idoma2_conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_messages_conversation
                ON idoma2_messages(conversation_id, id);
            CREATE TABLE IF NOT EXISTS idoma2_agent_devices (
                device_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idoma2_agent_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'queued',
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_agent_tasks_status
                ON idoma2_agent_tasks(status, id);
            CREATE TABLE IF NOT EXISTS idoma2_agent_task_messages (
                task_id INTEGER PRIMARY KEY,
                message_id INTEGER NOT NULL,
                FOREIGN KEY(task_id) REFERENCES idoma2_agent_tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES idoma2_messages(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS idoma2_memory_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                value TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'utente',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(category, subject)
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_memory_facts_category
                ON idoma2_memory_facts(category, subject);
            CREATE TABLE IF NOT EXISTS idoma2_memory_suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(category, subject, value)
            );
            CREATE TABLE IF NOT EXISTS idoma2_briefing_log (
                local_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(local_date, kind)
            );
            CREATE TABLE IF NOT EXISTS idoma2_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                notified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_reminders_due
                ON idoma2_reminders(status, due_at, notified_at);
            CREATE TABLE IF NOT EXISTS idoma2_document_index (
                path TEXT PRIMARY KEY,
                modified_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                extension TEXT NOT NULL,
                content TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_document_index_extension
                ON idoma2_document_index(extension);
        """)


def create_conversation(conversation_id: str, title: str = "Nuova conversazione") -> None:
    now = utc_now()
    with connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO idoma2_conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, title[:80], now, now),
        )


def update_conversation(conversation_id: str, title: str | None = None) -> None:
    with connection() as conn:
        if title:
            conn.execute(
                "UPDATE idoma2_conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title[:80], utc_now(), conversation_id),
            )
        else:
            conn.execute(
                "UPDATE idoma2_conversations SET updated_at = ? WHERE id = ?",
                (utc_now(), conversation_id),
            )


def save_message(conversation_id: str, role: str, content: str) -> int:
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO idoma2_messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, utc_now()),
        )
        conn.execute(
            "UPDATE idoma2_conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )
        return int(cur.lastrowid)


def list_conversations(limit: int = 50) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM idoma2_conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_messages(conversation_id: str, limit: int = 40) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.role, m.content, m.created_at, tm.task_id AS agent_task_id, t.status AS agent_task_status "
            "FROM idoma2_messages AS m "
            "LEFT JOIN idoma2_agent_task_messages AS tm ON tm.message_id = m.id "
            "LEFT JOIN idoma2_agent_tasks AS t ON t.id = tm.task_id "
            "WHERE m.conversation_id = ? ORDER BY m.id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_recent_user_messages(limit: int = 300) -> list[str]:
    """Read recent user-authored messages across conversations for explicit memory recovery."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT content FROM idoma2_messages WHERE role='user' ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 2000)),),
        ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def conversation_exists(conversation_id: str) -> bool:
    with connection() as conn:
        row = conn.execute("SELECT 1 FROM idoma2_conversations WHERE id = ?", (conversation_id,)).fetchone()
    return row is not None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def get_legacy_memories(limit: int = 60) -> list[dict]:
    """Reads old IDOMA memories in place; it does not migrate or delete them."""
    items: list[dict] = []
    with connection() as conn:
        if _table_exists(conn, "ricordi"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(ricordi)").fetchall()}
            if "contenuto" in cols:
                order = "id DESC" if "id" in cols else "rowid DESC"
                rows = conn.execute(f"SELECT contenuto FROM ricordi ORDER BY {order} LIMIT ?", (limit,)).fetchall()
                items.extend({"type": "ricordo", "content": row[0]} for row in rows if row[0])
        if _table_exists(conn, "memorie"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(memorie)").fetchall()}
            if {"chiave", "valore"}.issubset(cols):
                rows = conn.execute("SELECT chiave, valore FROM memorie ORDER BY chiave LIMIT ?", (limit,)).fetchall()
                items.extend({"type": "dato", "content": f"{row[0]}: {row[1]}"} for row in rows if row[1])
    return items[:limit]


def search_legacy_memories(query: str, limit: int = 12) -> list[str]:
    words = [w for w in query.lower().split() if len(w) > 3]
    all_items = get_legacy_memories(100)
    if not words:
        return [x["content"] for x in all_items[:limit]]
    ranked = []
    for item in all_items:
        content = item["content"]
        score = sum(word in content.lower() for word in words)
        if score:
            ranked.append((score, content))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [content for _, content in ranked[:limit]]


def add_legacy_memory(content: str, source: str = "idoma_2") -> bool:
    content = " ".join(content.split()).strip()
    if not content:
        return False
    with connection() as conn:
        if not _table_exists(conn, "ricordi"):
            conn.execute("""CREATE TABLE ricordi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contenuto TEXT NOT NULL COLLATE NOCASE UNIQUE,
                fonte TEXT NOT NULL DEFAULT 'utente',
                creato_il TEXT DEFAULT CURRENT_TIMESTAMP,
                aggiornato_il TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
        cur = conn.execute(
            "INSERT OR IGNORE INTO ricordi(contenuto, fonte) VALUES (?, ?)",
            (content[:1000], source),
        )
    return cur.rowcount > 0


def forget_legacy_memory(query: str) -> int:
    query = query.strip()
    if not query:
        return 0
    deleted = 0
    with connection() as conn:
        if _table_exists(conn, "ricordi"):
            cur = conn.execute("DELETE FROM ricordi WHERE contenuto LIKE ?", (f"%{query}%",))
            deleted += cur.rowcount
        # The legacy key/value table is also part of the user memory surface.
        if _table_exists(conn, "memorie"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(memorie)").fetchall()}
            if {"chiave", "valore"}.issubset(cols):
                cur = conn.execute(
                    "DELETE FROM memorie WHERE CAST(chiave AS TEXT) LIKE ? OR CAST(valore AS TEXT) LIKE ?",
                    (f"%{query}%", f"%{query}%"),
                )
                deleted += cur.rowcount
    return deleted


def init_agent_tables() -> None:
    with connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS idoma2_agent_devices (
                device_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idoma2_agent_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'queued',
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idoma2_agent_tasks_status
                ON idoma2_agent_tasks(status, id);
        """)


def agent_heartbeat(device_id: str, device_name: str) -> None:
    now = utc_now()
    with connection() as conn:
        conn.execute("""INSERT INTO idoma2_agent_devices(device_id, device_name, last_seen)
            VALUES (?, ?, ?) ON CONFLICT(device_id) DO UPDATE SET
            device_name=excluded.device_name, last_seen=excluded.last_seen""",
            (device_id, device_name[:100], now))


def agent_is_online(max_age_seconds: int = 25) -> bool:
    from datetime import datetime, timedelta, timezone
    with connection() as conn:
        row = conn.execute("SELECT last_seen FROM idoma2_agent_devices ORDER BY last_seen DESC LIMIT 1").fetchone()
    if not row:
        return False
    try:
        seen = datetime.fromisoformat(row[0])
        return datetime.now(timezone.utc) - seen <= timedelta(seconds=max_age_seconds)
    except ValueError:
        return False


def queue_agent_task(action: str, payload: dict | None = None) -> int:
    import json
    now = utc_now()
    with connection() as conn:
        cur = conn.execute("""INSERT INTO idoma2_agent_tasks(action, payload, status, created_at, updated_at)
            VALUES (?, ?, 'queued', ?, ?)""",
            (action, json.dumps(payload or {}, ensure_ascii=False), now, now))
        return int(cur.lastrowid)


def claim_agent_task() -> dict | None:
    import json
    now = utc_now()
    stale_before = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
    with connection() as conn:
        # Recover a task left running by a crash or forced shutdown.
        conn.execute(
            "UPDATE idoma2_agent_tasks SET status='queued', updated_at=? "
            "WHERE status='running' AND updated_at<?",
            (now, stale_before),
        )
        row = conn.execute("SELECT id, action, payload FROM idoma2_agent_tasks WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        cur = conn.execute("UPDATE idoma2_agent_tasks SET status='running', updated_at=? WHERE id=? AND status='queued'", (now, row[0]))
        if cur.rowcount != 1:
            return None
        return {"id": row[0], "action": row[1], "payload": json.loads(row[2] or "{}")}


def link_agent_task_message(task_id: int, message_id: int) -> None:
    """Associate the pending chat bubble with its task, including the fast-completion race."""
    with connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO idoma2_agent_task_messages(task_id, message_id) VALUES (?, ?)",
            (task_id, message_id),
        )
        task = conn.execute(
            "SELECT status, result FROM idoma2_agent_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if task and task["status"] in {"done", "failed"}:
            result = str(task["result"] or "")
            final_message = f"Fatto: {result}" if task["status"] == "done" else f"Non sono riuscito a completare l'attività: {result}"
            conn.execute("UPDATE idoma2_messages SET content=? WHERE id=?", (final_message, message_id))


def finish_agent_task(task_id: int, result: str, success: bool) -> None:
    clean_result = result[:12000]
    status = "done" if success else "failed"
    final_message = f"Fatto: {clean_result}" if success else f"Non sono riuscito a completare l'attività: {clean_result}"
    with connection() as conn:
        cur = conn.execute(
            "UPDATE idoma2_agent_tasks SET status=?, result=?, updated_at=? WHERE id=?",
            (status, clean_result, utc_now(), task_id),
        )
        if cur.rowcount:
            row = conn.execute(
                "SELECT message_id FROM idoma2_agent_task_messages WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE idoma2_messages SET content=? WHERE id=?",
                    (final_message, row[0]),
                )


def get_agent_task(task_id: int) -> dict | None:
    """Return the status/result of one desktop task without changing it."""
    with connection() as conn:
        row = conn.execute(
            "SELECT id, action, status, result, created_at, updated_at FROM idoma2_agent_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def claim_briefing(kind: str, local_date: str) -> bool:
    """Atomically claim one daily briefing so restarts do not duplicate it."""
    if kind not in {"morning", "evening"}:
        raise ValueError("Tipo di briefing non valido.")
    with connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO idoma2_briefing_log(local_date, kind, sent_at) VALUES (?, ?, ?)",
            (local_date, kind, utc_now()),
        )
    return cur.rowcount == 1


def create_reminder(title: str, due_at: str) -> dict:
    """Create a local reminder; due_at must be an ISO timestamp with timezone."""
    title = " ".join(str(title).split()).strip()[:300]
    if not title:
        raise ValueError("Il testo del promemoria è obbligatorio.")
    try:
        due = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("La data del promemoria non è valida.") from exc
    if due.tzinfo is None:
        raise ValueError("La data del promemoria deve includere il fuso orario.")
    due_utc = due.astimezone(timezone.utc).isoformat(timespec="seconds")
    now = utc_now()
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO idoma2_reminders(title, due_at, status, created_at, updated_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (title, due_utc, now, now),
        )
        row = conn.execute("SELECT * FROM idoma2_reminders WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_reminders(include_completed: bool = False, limit: int = 100) -> list[dict]:
    with connection() as conn:
        if include_completed:
            rows = conn.execute(
                "SELECT * FROM idoma2_reminders ORDER BY "
                "CASE status WHEN 'pending' THEN 0 ELSE 1 END, due_at ASC, id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM idoma2_reminders WHERE status='pending' "
                "ORDER BY due_at ASC, id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
    return [dict(row) for row in rows]


def get_due_reminders(limit: int = 30) -> list[dict]:
    now = utc_now()
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM idoma2_reminders "
            "WHERE status='pending' AND notified_at IS NULL AND due_at<=? "
            "ORDER BY due_at ASC LIMIT ?",
            (now, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_reminder_notified(reminder_id: int) -> bool:
    with connection() as conn:
        cur = conn.execute(
            "UPDATE idoma2_reminders SET notified_at=?, updated_at=? "
            "WHERE id=? AND status='pending' AND notified_at IS NULL",
            (utc_now(), utc_now(), int(reminder_id)),
        )
    return cur.rowcount == 1


def complete_reminder(reminder_id: int) -> bool:
    with connection() as conn:
        cur = conn.execute(
            "UPDATE idoma2_reminders SET status='completed', updated_at=? "
            "WHERE id=? AND status='pending'",
            (utc_now(), int(reminder_id)),
        )
    return cur.rowcount == 1


def snooze_reminder(reminder_id: int, minutes: int = 10) -> dict | None:
    minutes = max(1, min(int(minutes), 10080))
    due = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    due_at = due.isoformat(timespec="seconds")
    with connection() as conn:
        cur = conn.execute(
            "UPDATE idoma2_reminders SET due_at=?, notified_at=NULL, updated_at=? "
            "WHERE id=? AND status='pending'",
            (due_at, utc_now(), int(reminder_id)),
        )
        if cur.rowcount != 1:
            return None
        row = conn.execute("SELECT * FROM idoma2_reminders WHERE id=?", (int(reminder_id),)).fetchone()
    return dict(row)


def delete_reminder(reminder_id: int) -> bool:
    with connection() as conn:
        cur = conn.execute("DELETE FROM idoma2_reminders WHERE id=?", (int(reminder_id),))
    return cur.rowcount == 1


def save_memory_fact(category: str, subject: str, value: str, aliases: list[str] | None = None, source: str = "utente") -> None:
    """Save or update a structured personal fact without touching legacy memory tables."""
    import json
    category = " ".join(category.split()).strip().casefold()[:60]
    subject = " ".join(subject.split()).strip()[:120]
    value = " ".join(value.split()).strip()[:500]
    clean_aliases = []
    for alias in aliases or []:
        alias = " ".join(str(alias).split()).strip()[:120]
        if alias and alias.casefold() not in {x.casefold() for x in clean_aliases}:
            clean_aliases.append(alias)
    if not category or not subject or not value:
        raise ValueError("Categoria, concetto e valore sono obbligatori.")
    now = utc_now()
    with connection() as conn:
        conn.execute("""INSERT INTO idoma2_memory_facts
            (category, subject, value, aliases, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, subject) DO UPDATE SET
            value=excluded.value, aliases=excluded.aliases, source=excluded.source, updated_at=excluded.updated_at""",
            (category, subject, value, json.dumps(clean_aliases, ensure_ascii=False), source[:80], now, now))


def list_memory_facts(limit: int = 100) -> list[dict]:
    import json
    with connection() as conn:
        rows = conn.execute("SELECT * FROM idoma2_memory_facts ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["aliases"] = json.loads(item.get("aliases") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["aliases"] = []
        item["content"] = f"{item['subject']}: {item['value']}" + (f" (alias: {', '.join(item['aliases'])})" if item["aliases"] else "")
        item["type"] = "fatto_personale"
        result.append(item)
    return result


def find_memory_aliases(query: str, limit: int = 8) -> list[str]:
    """Return values associated with a concept/alias mentioned in a file search."""
    import json
    import unicodedata
    def norm(value: str) -> str:
        value = unicodedata.normalize("NFKD", value.casefold())
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(re.findall(r"[a-z0-9]+", value))
    q = norm(query)
    if not q:
        return []
    with connection() as conn:
        rows = conn.execute("SELECT subject, value, aliases FROM idoma2_memory_facts ORDER BY updated_at DESC LIMIT 300").fetchall()
    found = []
    for row in rows:
        try:
            aliases = json.loads(row["aliases"] or "[]")
        except (TypeError, json.JSONDecodeError):
            aliases = []
        labels = [row["subject"], *aliases]
        if any(norm(label) == q for label in labels if label):
            if row["value"] not in found:
                found.append(row["value"])
    return found[:limit]


def is_memory_suppressed(category: str, subject: str, value: str) -> bool:
    """Prevent a forgotten fact from being re-imported from old chat history."""
    candidate = " ".join(str(value).casefold().split())
    if not candidate:
        return False
    with connection() as conn:
        rows = conn.execute(
            "SELECT value FROM idoma2_memory_suppressions "
            "WHERE (category='*' OR category=?) AND (subject='*' OR subject=?)",
            (category, subject),
        ).fetchall()
    for row in rows:
        blocked = " ".join(str(row[0]).casefold().split())
        if not blocked:
            continue
        if category == "personal" and subject in {"nome", "name"} and blocked in {"nome", "name"}:
            return True
        if blocked in candidate or candidate in blocked:
            return True
    return False


def clear_memory_suppression(category: str, subject: str, value: str) -> None:
    """A new explicit remember instruction may intentionally restore a fact."""
    candidate = " ".join(str(value).casefold().split())
    with connection() as conn:
        conn.execute(
            "DELETE FROM idoma2_memory_suppressions WHERE "
            "((category=? AND subject=?) OR (category='*' AND subject='*')) "
            "AND (lower(value)=? OR lower(value)='nome' OR lower(value)='name')",
            (category, subject, candidate),
        )


def forget_memory_facts(query: str) -> int:
    """Delete matching facts and record tombstones so chat-history recovery cannot resurrect them."""
    query = " ".join(query.casefold().split()).strip()
    if not query:
        return 0
    import json
    deleted = 0
    with connection() as conn:
        rows = conn.execute("SELECT id, category, subject, value, aliases FROM idoma2_memory_facts").fetchall()
        ids = []
        suppressed = []
        for row in rows:
            try:
                aliases = json.loads(row["aliases"] or "[]")
            except (TypeError, json.JSONDecodeError):
                aliases = []
            fields = [row["subject"], row["value"], *aliases]
            if any(query == str(field).casefold().strip() or query in str(field).casefold() for field in fields):
                ids.append(row["id"])
                suppressed.append((row["category"], row["subject"], row["value"], utc_now()))
        if ids:
            placeholders = ",".join("?" for _ in ids)
            cur = conn.execute(f"DELETE FROM idoma2_memory_facts WHERE id IN ({placeholders})", ids)
            deleted = cur.rowcount
        # Suppress the requested phrase even when the fact existed only in chat history.
        conn.execute(
            "INSERT OR IGNORE INTO idoma2_memory_suppressions(category, subject, value, created_at) VALUES (?, ?, ?, ?)",
            ("*", "*", query, utc_now()),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO idoma2_memory_suppressions(category, subject, value, created_at) VALUES (?, ?, ?, ?)",
            suppressed,
        )
    return deleted


def get_indexed_document(path: str) -> dict | None:
    """Return one cached document entry, if it has already been indexed."""
    with connection() as conn:
        row = conn.execute(
            "SELECT path, modified_ns, size_bytes, extension, content, indexed_at FROM idoma2_document_index WHERE path=?",
            (path,),
        ).fetchone()
    return dict(row) if row else None


def upsert_indexed_document(path: str, modified_ns: int, size_bytes: int, extension: str, content: str) -> None:
    """Store extracted local document text for fast subsequent searches."""
    upsert_indexed_documents([(path, modified_ns, size_bytes, extension, content)])


def upsert_indexed_documents(entries: list[tuple[str, int, int, str, str]]) -> None:
    """Batch-update changed documents with one SQLite transaction."""
    if not entries:
        return
    now = utc_now()
    rows = [(path, int(modified_ns), int(size_bytes), extension.casefold(), content[:80000], now)
            for path, modified_ns, size_bytes, extension, content in entries]
    with connection() as conn:
        conn.executemany("""INSERT INTO idoma2_document_index
            (path, modified_ns, size_bytes, extension, content, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
            modified_ns=excluded.modified_ns, size_bytes=excluded.size_bytes,
            extension=excluded.extension, content=excluded.content, indexed_at=excluded.indexed_at""", rows)


def list_indexed_document_metadata() -> list[dict]:
    """Read lightweight cache metadata without loading document text into memory."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT path, modified_ns, size_bytes, extension FROM idoma2_document_index"
        ).fetchall()
    return [dict(row) for row in rows]


def list_indexed_documents() -> list[dict]:
    """List cached document text; callers filter stale paths before use."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT path, modified_ns, size_bytes, extension, content, indexed_at FROM idoma2_document_index"
        ).fetchall()
    return [dict(row) for row in rows]
