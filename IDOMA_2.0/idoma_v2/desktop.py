from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from datetime import timedelta

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .config import PACKAGE_DIR, MORNING_BRIEFING_TIME, EVENING_BRIEFING_TIME
from .security import get_api_token
from .server.main import app as api_app


BIND_HOST = os.getenv("IDOMA_BIND_HOST", "127.0.0.1")
PORT = int(os.getenv("IDOMA_PORT", "8000"))
LOCAL_URL = f"http://127.0.0.1:{PORT}"


class ApiServerThread(QThread):
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.server = None

    def run(self):
        try:
            import uvicorn
            config = uvicorn.Config(
                api_app,
                host=BIND_HOST,
                port=PORT,
                log_level="error",
                access_log=False,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as exc:
            self.failed.emit(str(exc))

    def stop(self):
        if self.server is not None:
            self.server.should_exit = True


class AgentThread(QThread):
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()

    def run(self):
        try:
            from .desktop_agent import run_agent
            run_agent(self.stop_event, self.status.emit, quiet=True)
        except Exception as exc:
            self.status.emit(f"Agente desktop non disponibile: {exc}")

    def stop(self):
        self.stop_event.set()


class ReminderThread(QThread):
    reminder_due = Signal(dict)
    briefing_due = Signal(dict)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    @staticmethod
    def _within_briefing_window(now, configured: str) -> bool:
        try:
            hour_text, minute_text = configured.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return False
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            elapsed = now - scheduled
            return timedelta(0) <= elapsed <= timedelta(hours=4)
        except (TypeError, ValueError):
            return False

    def run(self):
        from datetime import datetime
        from .db import get_due_reminders, mark_reminder_notified, claim_briefing
        from .services.reminders import build_daily_briefing, build_evening_briefing

        while not self.stop_event.is_set():
            try:
                for item in get_due_reminders():
                    if mark_reminder_notified(item["id"]):
                        self.reminder_due.emit(item)

                now = datetime.now().astimezone()
                local_date = now.date().isoformat()
                if self._within_briefing_window(now, MORNING_BRIEFING_TIME):
                    if claim_briefing("morning", local_date):
                        self.briefing_due.emit({
                            "kind": "morning",
                            "message": build_daily_briefing(now),
                        })
                if self._within_briefing_window(now, EVENING_BRIEFING_TIME):
                    if claim_briefing("evening", local_date):
                        self.briefing_due.emit({
                            "kind": "evening",
                            "message": build_evening_briefing(now),
                        })
            except Exception:
                # A temporary database lock must not terminate the reminder service.
                pass
            self.stop_event.wait(15.0)


class VoiceThread(QThread):
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.conversation_id = None

    def stop(self):
        self.stop_event.set()

    def send_command(self, command: str) -> str:
        payload = {"message": command}
        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id
        request = urllib.request.Request(
            f"{LOCAL_URL}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {get_api_token()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=190) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", str(exc))
            except Exception:
                detail = str(exc)
            raise RuntimeError(str(detail)) from exc
        self.conversation_id = result.get("conversation_id") or self.conversation_id
        return str(result.get("reply") or "Ho ricevuto la richiesta.")

    def run(self):
        try:
            from .services.voice import VoiceAssistant
            service = VoiceAssistant(self.status.emit, self.send_command, self.stop_event)
            service.run_forever()
        except Exception as exc:
            self.status.emit(f"Ascolto vocale non disponibile: {exc}")


class IdomaTrayController(QObject):
    voice_toggle_requested = Signal(bool)

    def __init__(self, application: QApplication):
        super().__init__()
        self.application = application
        self.server_thread = ApiServerThread()
        self.agent_thread = AgentThread()
        self.reminder_thread = ReminderThread()
        self.agent_started = False
        self.voice_thread = None
        self.voice_status = "Avvio del servizio vocale…"
        self.server_ready = False
        self._shutting_down = False
        api_app.state.idoma_controller = self
        self.voice_toggle_requested.connect(self.set_voice_enabled)

        icon_path = PACKAGE_DIR / "web" / "icon-192.png"
        self.tray = QSystemTrayIcon(QIcon(str(icon_path)), self)
        self.tray.setToolTip("IDOMA · assistente personale")

        menu = QMenu()
        open_action = QAction("Apri IDOMA", self)
        open_action.triggered.connect(self.open_idoma)
        menu.addAction(open_action)

        token_action = QAction("Copia token API", self)
        token_action.triggered.connect(self.copy_token)
        menu.addAction(token_action)

        self.voice_action = QAction("Ascolto vocale attivo", self)
        self.voice_action.setCheckable(True)
        self.voice_action.setChecked(True)
        self.voice_action.toggled.connect(self.set_voice_enabled)
        menu.addAction(self.voice_action)

        menu.addSeparator()
        self.autostart_action = QAction("Avvia con Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.autostart_enabled())
        self.autostart_action.toggled.connect(self.set_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()
        exit_action = QAction("Esci da IDOMA", self)
        exit_action.triggered.connect(self.application.quit)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        self.server_thread.failed.connect(self.on_server_error)
        self.agent_thread.status.connect(self.on_agent_status)
        self.reminder_thread.reminder_due.connect(self.on_reminder_due)
        self.reminder_thread.briefing_due.connect(self.on_briefing_due)
        self.server_thread.start()

        self.startup_timer = QTimer(self)
        self.startup_timer.timeout.connect(self.check_server_ready)
        self.startup_timer.start(400)

        self.application.aboutToQuit.connect(self.shutdown)

    def check_server_ready(self):
        server = self.server_thread.server
        if server is not None and server.started:
            self.startup_timer.stop()
            self.server_ready = True
            if not self.agent_started:
                self.agent_started = True
                self.agent_thread.start()
            if self.voice_action.isChecked():
                self.start_voice()
            if not self.reminder_thread.isRunning():
                self.reminder_thread.start()
            self.tray.showMessage("IDOMA", "Server locale e agente desktop avviati.", QSystemTrayIcon.MessageIcon.Information, 3500)
        elif not self.server_thread.isRunning():
            self.startup_timer.stop()
            self.tray.showMessage("IDOMA", "Il server non è riuscito ad avviarsi. Controlla che la porta sia libera.", QSystemTrayIcon.MessageIcon.Warning, 6000)

    def open_idoma(self):
        webbrowser.open(LOCAL_URL)

    def copy_token(self):
        try:
            token = get_api_token()
            self.application.clipboard().setText(token)
            self.tray.showMessage("IDOMA", "Token API copiato negli appunti.", QSystemTrayIcon.MessageIcon.Information, 3000)
        except Exception as exc:
            QMessageBox.critical(None, "IDOMA", f"Non riesco a leggere il token API: {exc}")

    def on_agent_status(self, message: str):
        if "non disponibile" in message.casefold() or "non raggiungibile" in message.casefold():
            self.tray.setToolTip("IDOMA · verifica il collegamento al PC")
            self.tray.showMessage("IDOMA", message, QSystemTrayIcon.MessageIcon.Warning, 4000)
        else:
            self.tray.setToolTip("IDOMA · assistente personale")

    def request_voice_enabled(self, enabled: bool):
        """Thread-safe bridge from the local HTTP API to the Qt UI thread."""
        self.voice_toggle_requested.emit(bool(enabled))

    def set_voice_enabled(self, enabled: bool):
        self.voice_action.blockSignals(True)
        self.voice_action.setChecked(bool(enabled))
        self.voice_action.blockSignals(False)
        if enabled:
            self.voice_status = "Avvio del servizio vocale…"
            if self.server_ready:
                self.start_voice()
        else:
            self.voice_status = "Ascolto vocale disattivato."
            self.stop_voice()

    def start_voice(self):
        if self.voice_thread is not None and self.voice_thread.isRunning():
            return
        self.voice_thread = VoiceThread()
        self.voice_thread.status.connect(self.on_voice_status)
        self.voice_thread.finished.connect(self.on_voice_finished)
        self.voice_thread.start()

    def stop_voice(self, wait_for_exit: bool = False):
        thread = self.voice_thread
        if thread is None:
            return
        thread.stop()
        # Toggling the microphone must not freeze the tray UI. During full
        # shutdown we wait for the current transcription/TTS operation to finish.
        if wait_for_exit and thread.isRunning():
            thread.wait(60000)
        if not thread.isRunning():
            self.voice_thread = None

    def on_voice_finished(self):
        if not self.voice_action.isChecked() or self._shutting_down:
            self.voice_status = "Ascolto vocale disattivato."
        if self.voice_action.isChecked() and not self._shutting_down:
            self.voice_action.blockSignals(True)
            self.voice_action.setChecked(False)
            self.voice_action.blockSignals(False)
            self.tray.showMessage(
                "IDOMA",
                "Ascolto vocale terminato. Puoi riattivarlo dal menu.",
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
        if self.voice_thread is not None and not self.voice_thread.isRunning():
            self.voice_thread = None

    def on_voice_status(self, message: str):
        self.voice_status = str(message)
        lowered = message.casefold()
        if "in ascolto" in lowered or "idoma è pronta" in lowered:
            self.tray.setToolTip("IDOMA · ascolto vocale attivo")
        elif "non disponibile" in lowered or "problema con" in lowered:
            self.tray.setToolTip("IDOMA · verifica microfono o modelli vocali")
            self.tray.showMessage(
                "IDOMA",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )
        elif "ascolto vocale disattivato" in lowered:
            self.tray.setToolTip("IDOMA · assistente personale")

    def on_briefing_due(self, briefing: dict):
        kind = briefing.get("kind")
        heading = "Buongiorno" if kind == "morning" else "Riepilogo serale"
        message = str(briefing.get("message") or "Non ci sono aggiornamenti.")
        if len(message) > 240:
            message = message[:230].rsplit(" ", 1)[0] + "… Apri IDOMA per il riepilogo completo."
        self.tray.showMessage(
            f"IDOMA · {heading}",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            15000,
        )

    def on_reminder_due(self, reminder: dict):
        title = str(reminder.get("title") or "Promemoria")
        self.tray.showMessage(
            "IDOMA · Promemoria",
            title,
            QSystemTrayIcon.MessageIcon.Information,
            10000,
        )

    def on_server_error(self, message: str):
        self.tray.showMessage("IDOMA", f"Errore del server: {message}", QSystemTrayIcon.MessageIcon.Critical, 7000)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_idoma()

    @staticmethod
    def autostart_command() -> str:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        runner = pythonw if pythonw.exists() else executable
        runner_script = PACKAGE_DIR.parent / "avvia_desktop.py"
        return f'"{runner}" "{runner_script}"'

    @staticmethod
    def autostart_enabled() -> bool:
        if os.name != "nt":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                value, _ = winreg.QueryValueEx(key, "IDOMA")
                return bool(value)
        except (OSError, FileNotFoundError):
            return False

    def set_autostart(self, enabled: bool):
        if os.name != "nt":
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                if enabled:
                    winreg.SetValueEx(key, "IDOMA", 0, winreg.REG_SZ, self.autostart_command())
                else:
                    try:
                        winreg.DeleteValue(key, "IDOMA")
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(not enabled)
            self.autostart_action.blockSignals(False)
            QMessageBox.warning(None, "IDOMA", f"Non riesco a modificare l'avvio automatico: {exc}")

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        if hasattr(self, "startup_timer"):
            self.startup_timer.stop()
        self.stop_voice(wait_for_exit=True)
        self.reminder_thread.stop()
        if self.reminder_thread.isRunning():
            self.reminder_thread.wait(5000)
        self.agent_thread.stop()
        if self.agent_thread.isRunning():
            self.agent_thread.wait(15000)
        self.server_thread.stop()
        if self.server_thread.isRunning():
            self.server_thread.wait(7000)
        self.tray.hide()


def main():
    if os.name != "nt":
        raise SystemExit("L'app desktop IDOMA è destinata a Windows.")
    application = QApplication(sys.argv)
    application.setApplicationName("IDOMA")
    application.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "IDOMA", "La barra delle applicazioni di Windows non è disponibile.")
        return 1
    controller = IdomaTrayController(application)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
