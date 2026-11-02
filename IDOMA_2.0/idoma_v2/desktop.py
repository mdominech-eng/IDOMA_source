from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .config import PACKAGE_DIR
from .security import TOKEN_FILE, get_api_token
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


class IdomaTrayController(QObject):
    def __init__(self, application: QApplication):
        super().__init__()
        self.application = application
        self.server_thread = ApiServerThread()
        self.agent_thread = AgentThread()
        self.agent_started = False

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

        menu.addSeparator()
        self.autostart_action = QAction("Avvia con Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.autostart_enabled())
        self.autostart_action.toggled.connect(self.set_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()
        exit_action = QAction("Esci da IDOMA", self)
        exit_action.triggered.connect(self.shutdown)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        self.server_thread.failed.connect(self.on_server_error)
        self.agent_thread.status.connect(self.on_agent_status)
        self.server_thread.start()

        self.startup_timer = QTimer(self)
        self.startup_timer.timeout.connect(self.check_server_ready)
        self.startup_timer.start(400)

        self.application.aboutToQuit.connect(self.shutdown)

    def check_server_ready(self):
        server = self.server_thread.server
        if server is not None and server.started:
            self.startup_timer.stop()
            if not self.agent_started:
                self.agent_started = True
                self.agent_thread.start()
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
        if hasattr(self, "startup_timer"):
            self.startup_timer.stop()
        self.agent_thread.stop()
        if self.agent_thread.isRunning():
            self.agent_thread.wait(15000)
        self.server_thread.stop()
        if self.server_thread.isRunning():
            self.server_thread.wait(7000)
        self.tray.hide()
        self.application.quit()


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
