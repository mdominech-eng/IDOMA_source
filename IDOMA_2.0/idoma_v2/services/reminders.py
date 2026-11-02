from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_TIME = r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"


def is_reminder_intent(message: str) -> bool:
    value = message.casefold()
    return bool(re.search(r"\bricordami\b|^\s*/promemoria\b", value))


def parse_reminder_request(message: str, now: datetime | None = None) -> tuple[str, str] | None:
    """Parse common Italian reminder phrases into (title, UTC ISO timestamp).

    Supported forms include 'ricordami di X domani alle 10:30',
    'ricordami di X tra 20 minuti', and 'ricordami di X il 03/11 alle 9'.
    """
    value = " ".join(message.strip().split())
    prefix = re.match(r"^(?:idoma[, ]+)?ricordami\s+(?:di\s+)?(.+)$", value, flags=re.IGNORECASE)
    if not prefix:
        return None
    details = prefix.group(1).strip().rstrip(" .!?")
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()

    title = ""
    due: datetime | None = None

    relative = re.match(
        r"(?P<title>.+?)\s+(?:tra|fra)\s+(?P<count>\d{1,5})\s+(?P<unit>minuti|minuto|ore|ora|giorni|giorno)$",
        details,
        flags=re.IGNORECASE,
    )
    if relative:
        title = relative.group("title")
        count = int(relative.group("count"))
        unit = relative.group("unit").casefold()
        if count < 1:
            raise ValueError("Il promemoria deve essere impostato almeno un minuto nel futuro.")
        if unit.startswith("minut"):
            delta = timedelta(minutes=count)
        elif unit.startswith("or"):
            delta = timedelta(hours=count)
        else:
            delta = timedelta(days=count)
        if delta > timedelta(days=365):
            raise ValueError("Posso impostare un promemoria al massimo entro un anno.")
        due = current + delta

    explicit_date = re.match(
        rf"(?P<title>.+?)\s+il\s+(?P<day>\d{{1,2}})/(?P<month>\d{{1,2}})(?:/(?P<year>\d{{2,4}}))?\s+alle\s+{_TIME}$",
        details,
        flags=re.IGNORECASE,
    )
    if due is None and explicit_date:
        title = explicit_date.group("title")
        year_text = explicit_date.group("year")
        year = int(year_text) if year_text else current.year
        if year_text and len(year_text) == 2:
            year += 2000
        hour, minute = int(explicit_date.group("hour")), int(explicit_date.group("minute") or 0)
        try:
            due = current.replace(
                year=year,
                month=int(explicit_date.group("month")),
                day=int(explicit_date.group("day")),
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError as exc:
            raise ValueError("La data o l'orario del promemoria non sono validi.") from exc
        if due <= current:
            raise ValueError("La data indicata è già passata. Specifica una data futura.")

    day_time = re.match(
        rf"(?P<title>.+?)\s+(?P<day>oggi|domani|dopodomani)\s+alle\s+{_TIME}$",
        details,
        flags=re.IGNORECASE,
    )
    if due is None and day_time:
        title = day_time.group("title")
        day_word = day_time.group("day").casefold()
        days = {"oggi": 0, "domani": 1, "dopodomani": 2}[day_word]
        hour, minute = int(day_time.group("hour")), int(day_time.group("minute") or 0)
        try:
            due = (current + timedelta(days=days)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
        except ValueError as exc:
            raise ValueError("L'orario del promemoria non è valido.") from exc
        if due <= current:
            raise ValueError("L'orario indicato per oggi è già passato. Scegli un orario futuro.")

    if due is None:
        bare_time = re.match(
            rf"(?P<title>.+?)\s+alle\s+{_TIME}(?:\s+(?P<day>oggi|domani))?$",
            details,
            flags=re.IGNORECASE,
        )
        if bare_time:
            title = bare_time.group("title")
            day_word = (bare_time.group("day") or "").casefold()
            days = 1 if day_word == "domani" else 0
            hour, minute = int(bare_time.group("hour")), int(bare_time.group("minute") or 0)
            try:
                due = (current + timedelta(days=days)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
            except ValueError as exc:
                raise ValueError("L'orario del promemoria non è valido.") from exc
            if not day_word and due <= current:
                due += timedelta(days=1)
            elif due <= current:
                raise ValueError("L'orario indicato per oggi è già passato. Scegli un orario futuro.")

    if due is None:
        # Also accept: 'ricordami domani alle 10 di chiamare ...'
        reverse = re.match(
            rf"(?P<day>oggi|domani|dopodomani)\s+alle\s+{_TIME}\s+di\s+(?P<title>.+)$",
            details,
            flags=re.IGNORECASE,
        )
        if reverse:
            title = reverse.group("title")
            days = {"oggi": 0, "domani": 1, "dopodomani": 2}[reverse.group("day").casefold()]
            try:
                due = (current + timedelta(days=days)).replace(
                    hour=int(reverse.group("hour")),
                    minute=int(reverse.group("minute") or 0),
                    second=0,
                    microsecond=0,
                )
            except ValueError as exc:
                raise ValueError("L'orario del promemoria non è valido.") from exc
            if due <= current:
                raise ValueError("L'orario indicato è già passato. Scegli un orario futuro.")

    if due is None:
        return None
    title = " ".join(title.split()).strip(" ,.;:!?")
    if not title:
        raise ValueError("Dimmi che cosa devo ricordarti.")
    if len(title) > 300:
        title = title[:300]
    return title, due.astimezone(timezone.utc).isoformat(timespec="seconds")


def format_reminder_due(due_at: str) -> str:
    due = datetime.fromisoformat(due_at.replace("Z", "+00:00")).astimezone()
    return due.strftime("%d/%m/%Y alle %H:%M")


def handle_reminder_command(message: str) -> str | None:
    from ..db import (
        create_reminder, list_reminders, complete_reminder, snooze_reminder,
    )

    command = message.strip()
    folded = command.casefold()

    complete = re.fullmatch(r"/completa\s+(\d+)", command, flags=re.IGNORECASE)
    if complete:
        reminder_id = int(complete.group(1))
        return (
            f"Promemoria #{reminder_id} completato."
            if complete_reminder(reminder_id)
            else f"Non trovo un promemoria attivo con ID #{reminder_id}."
        )

    snooze = re.fullmatch(r"/rimanda\s+(\d+)(?:\s+(\d+))?", command, flags=re.IGNORECASE)
    if snooze:
        reminder_id = int(snooze.group(1))
        minutes = int(snooze.group(2) or 10)
        item = snooze_reminder(reminder_id, minutes)
        return (
            f"Va bene, ti ricorderò '{item['title']}' alle {format_reminder_due(item['due_at'])}."
            if item
            else f"Non trovo un promemoria attivo con ID #{reminder_id}."
        )

    show = bool(re.search(
        r"^/promemoria(?:\s|$)|\b(?:mostra|mostrami|elenca|vedi)\b.*\bpromemoria\b|"
        r"\bpromemoria\s+(?:attivi|in programma)\b|\bcosa devo ricordare\b",
        folded,
    ))
    if show:
        items = list_reminders(False, 50)
        if not items:
            return "Non hai promemoria attivi."
        lines = [
            f"#{item['id']} · {item['title']} · {format_reminder_due(item['due_at'])}"
            for item in items
        ]
        return "Ecco i tuoi promemoria:\n" + "\n".join(lines)

    if is_reminder_intent(command):
        try:
            parsed = parse_reminder_request(command)
        except ValueError as exc:
            return str(exc)
        if parsed is None:
            return (
                "Certo. Quando vuoi che te lo ricordi? "
                "Puoi dirmi, per esempio, 'domani alle 10' oppure 'tra 30 minuti'."
            )
        title, due_at = parsed
        item = create_reminder(title, due_at)
        return f"Va bene, ti ricorderò '{item['title']}' il {format_reminder_due(item['due_at'])}."

    return None
