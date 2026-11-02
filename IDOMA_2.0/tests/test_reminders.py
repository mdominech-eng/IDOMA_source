import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import idoma_v2.db as db
from idoma_v2.services.reminders import parse_reminder_request, handle_reminder_command, build_daily_briefing


class ReminderParsingTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone(timedelta(hours=1)))

    def test_parse_tomorrow_with_time(self):
        title, due = parse_reminder_request("Ricordami di chiamare mamma domani alle 10:30", self.now)
        self.assertEqual(title, "chiamare mamma")
        self.assertEqual(due, "2026-11-03T09:30:00+00:00")

    def test_parse_relative_minutes(self):
        title, due = parse_reminder_request("Ricordami di pagare la bolletta tra 20 minuti", self.now)
        self.assertEqual(title, "pagare la bolletta")
        self.assertEqual(due, "2026-11-02T11:20:00+00:00")

    def test_parse_explicit_date(self):
        title, due = parse_reminder_request("Ricordami di inviare il documento il 03/11 alle 9", self.now)
        self.assertEqual(title, "inviare il documento")
        self.assertEqual(due, "2026-11-03T08:00:00+00:00")

    def test_parse_reverse_order(self):
        title, due = parse_reminder_request("Ricordami domani alle 10 di chiamare il medico", self.now)
        self.assertEqual(title, "chiamare il medico")
        self.assertEqual(due, "2026-11-03T09:00:00+00:00")

    def test_courtesy_prefix_is_supported(self):
        title, due = parse_reminder_request("Per favore, ricordami di chiamare mamma domani alle 10:30", self.now)
        self.assertEqual(title, "chiamare mamma")
        self.assertEqual(due, "2026-11-03T09:30:00+00:00")

    def test_mi_ricordi_form_is_supported(self):
        title, due = parse_reminder_request("Mi ricordi di inviare il file domani alle 9", self.now)
        self.assertEqual(title, "inviare il file")
        self.assertEqual(due, "2026-11-03T08:00:00+00:00")

    def test_missing_time_requests_clarification(self):
        self.assertIsNone(parse_reminder_request("Ricordami di comprare il latte", self.now))

    def test_invalid_past_today_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_reminder_request("Ricordami di chiamare oggi alle 9", self.now)


class ReminderStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.tmp.name) / "idoma.sqlite3")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_reminder_is_listed_and_notified_once(self):
        due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
        item = db.create_reminder("Test promemoria", due)
        self.assertEqual(db.list_reminders()[0]["id"], item["id"])
        self.assertEqual(len(db.get_due_reminders()), 1)
        self.assertTrue(db.mark_reminder_notified(item["id"]))
        self.assertEqual(db.get_due_reminders(), [])
        self.assertFalse(db.mark_reminder_notified(item["id"]))

    def test_complete_reminder(self):
        due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
        item = db.create_reminder("Completare test", due)
        self.assertTrue(db.complete_reminder(item["id"]))
        self.assertEqual(db.list_reminders(), [])

    def test_snooze_reminder_moves_due_time(self):
        due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
        item = db.create_reminder("Rimandare test", due)
        updated = db.snooze_reminder(item["id"], 15)
        self.assertIsNotNone(updated)
        self.assertGreater(datetime.fromisoformat(updated["due_at"]), datetime.now(timezone.utc))
        self.assertIsNone(updated["notified_at"])

    def test_daily_briefing_groups_overdue_today_and_upcoming(self):
        now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        db.create_reminder("Scadenza passata", (now - timedelta(days=1)).isoformat())
        db.create_reminder("Chiamare mamma", (now + timedelta(hours=2)).isoformat())
        db.create_reminder("Riunione", (now + timedelta(days=1)).isoformat())
        result = build_daily_briefing(now)
        self.assertIn("Scadenza passata", result)
        self.assertIn("Chiamare mamma", result)
        self.assertIn("Riunione", result)

    def test_chat_command_creates_and_lists_reminders(self):
        result = handle_reminder_command("Ricordami di chiamare mamma domani alle 10")
        self.assertIn("ti ricorderò", result)
        listing = handle_reminder_command("/promemoria")
        self.assertIn("chiamare mamma", listing)


if __name__ == "__main__":
    unittest.main()
