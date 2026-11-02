import sys
import math
import threading

from PySide6.QtCore import Qt, QTimer, QObject, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient
from idoma_core import IDOMACore

from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
)

BG = "#101216"
SIDEBAR = "#171a20"
PANEL = "#1b1f27"
BORDER = "#292f3a"
TEXT = "#f1f3f6"
MUTED = "#929baa"
ACCENT = "#66aaff"


class ChatWorker(QObject):
    finished = Signal(str)

    def __init__(self, core, message):
        super().__init__()
        self.core = core
        self.message = message

    @Slot()
    def run(self):
        try:
            response = self.core.elabora_messaggio(self.message)
        except Exception as error:
            response = f"Si è verificato un errore: {error}"
        self.finished.emit(str(response))


class VoiceWorker(QThread):
    transcript = Signal(str)
    status = Signal(str)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()

    def run(self):
        try:
            from test_voce import ascolta_comando

            comando = ascolta_comando(
                self.stop_event,
                self.status.emit
            )

            if comando and not self.stop_event.is_set():
                self.transcript.emit(comando)

        except Exception as errore:
            self.error.emit(str(errore))

    def stop(self):
        self.stop_event.set()


class GlowOrb(QWidget):
    """Orb animato leggero, disegnato direttamente da Qt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(190, 190)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)  # 20 aggiornamenti al secondo

    def animate(self):
        self.phase = (self.phase + 0.045) % math.tau
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = 57 * (1 + 0.035 * math.sin(self.phase))

        glow = QRadialGradient(cx, cy, radius * 2)
        glow.setColorAt(0, QColor(52, 139, 255, 105))
        glow.setColorAt(0.48, QColor(42, 105, 220, 42))
        glow.setColorAt(1, QColor(20, 35, 65, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(int(cx-radius*2), int(cy-radius*2),
                            int(radius*4), int(radius*4))

        core = QRadialGradient(cx-radius*.28, cy-radius*.34, radius*1.65)
        core.setColorAt(0, QColor(173, 220, 255))
        core.setColorAt(.28, QColor(82, 165, 255))
        core.setColorAt(.72, QColor(45, 105, 210))
        core.setColorAt(1, QColor(25, 48, 105))
        painter.setBrush(core)
        painter.setPen(QColor(135, 195, 255, 115))
        painter.drawEllipse(int(cx-radius), int(cy-radius),
                            int(radius*2), int(radius*2))


class MessageBubble(QFrame):
    def __init__(self, author, message, is_user=False):
        super().__init__()
        self.setObjectName("userMessage" if is_user else "assistantMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        author_label = QLabel(author.upper())
        author_label.setObjectName("messageAuthor")
        body = QLabel(message)
        body.setObjectName("messageBody")
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(author_label)
        layout.addWidget(body)


class IdomaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IDOMA")
        self.resize(1240, 820)
        self.setMinimumSize(900, 620)

        self.core = IDOMACore()
        self.worker_thread = None
        self.worker = None
        self.voice_thread = None

        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.create_sidebar())

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.create_header())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(34, 28, 34, 24)
        self.chat_layout.setSpacing(16)
        self.chat_layout.addStretch(1)
        self.scroll.setWidget(self.chat_content)
        main_layout.addWidget(self.scroll, 1)
        main_layout.addWidget(self.create_composer())

        root_layout.addWidget(main, 1)
        self.setCentralWidget(root)
        self.show_welcome()
        self.apply_style()

    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(12)

        brand_row = QHBoxLayout()
        brand = QLabel("IDOMA")
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        version = QLabel("LOCAL AI")
        version.setObjectName("version")
        brand_row.addWidget(version)
        layout.addLayout(brand_row)

        self.new_chat_button = QPushButton("+   Nuova conversazione")
        self.new_chat_button.setObjectName("newChatButton")
        self.new_chat_button.clicked.connect(self.new_conversation)
        layout.addWidget(self.new_chat_button)

        section = QLabel("SPAZIO PERSONALE")
        section.setObjectName("sidebarSection")
        layout.addWidget(section)

        memory = self.sidebar_button("◈   Memoria personale")
        memory.clicked.connect(self.show_memory)
        layout.addWidget(memory)

        settings = self.sidebar_button("⚙   Impostazioni")
        settings.clicked.connect(lambda: self.show_notice(
            "Impostazioni",
            "Qui aggiungeremo le impostazioni di voce, modello AI e aspetto."
        ))
        layout.addWidget(settings)

        recent = QLabel("RECENTI")
        recent.setObjectName("sidebarSection")
        layout.addSpacing(18)
        layout.addWidget(recent)

        history = self.sidebar_button("•   Prima conversazione")
        history.setEnabled(False)
        layout.addWidget(history)
        layout.addStretch()

        footer = QLabel("Assistente personale\nEsecuzione locale")
        footer.setObjectName("sidebarFooter")
        layout.addWidget(footer)
        return sidebar

    def sidebar_button(self, label):
        button = QPushButton(label)
        button.setObjectName("sidebarButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def create_header(self):
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(70)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(30, 0, 30, 0)

        title = QLabel("Assistente")
        title.setObjectName("headerTitle")
        layout.addWidget(title)
        layout.addStretch()

        self.status_label = QLabel("●  IDOMA LOCALE")
        self.status_label.setObjectName("statusPill")
        layout.addWidget(self.status_label)
        return header

    def create_composer(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(28, 12, 28, 22)
        outer_layout.setSpacing(8)

        composer = QFrame()
        composer.setObjectName("composer")
        row = QHBoxLayout(composer)
        row.setContentsMargins(16, 12, 12, 12)
        row.setSpacing(10)

        self.input = QPlainTextEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Scrivi un messaggio a IDOMA...")
        self.input.setFixedHeight(58)
        self.input.setTabChangesFocus(True)
        row.addWidget(self.input, 1)

        self.mic_button = QPushButton("♫")
        self.mic_button.setObjectName("iconButton")
        self.mic_button.setToolTip("Attiva il riconoscimento vocale")
        self.mic_button.clicked.connect(self.toggle_voice)

        row.addWidget(self.mic_button)

        self.send_button = QPushButton("↑")
        self.send_button.setObjectName("sendButton")
        self.send_button.setToolTip("Invia")
        self.send_button.clicked.connect(self.send_message)
        row.addWidget(self.send_button)

        outer_layout.addWidget(composer)
        self.composer_hint = QLabel(
            "Motore locale pronto • Qwen3 1.7B • Memoria SQLite"
        )
        self.composer_hint.setObjectName("composerHint")
        self.composer_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(self.composer_hint)
        return outer

    def clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def show_welcome(self):
        self.clear_chat()
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setContentsMargins(0, 42, 0, 20)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(GlowOrb(), alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Come posso aiutarti?")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Il tuo assistente personale, intelligente e locale.")
        subtitle.setObjectName("welcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        for label, prompt in [
            ("Memoria", "Cosa ricordi di me?"),
            ("Ricerca", "Cerca informazioni sul web"),
            ("Assistente", "Quali cose puoi fare?")
        ]:
            card = QPushButton(label + "\n" + prompt)
            card.setObjectName("suggestionCard")
            card.setMinimumSize(175, 66)
            card.clicked.connect(
                lambda checked=False, value=prompt:
                self.input.setPlainText(value)
            )
            cards.addWidget(card)

        layout.addSpacing(14)
        layout.addLayout(cards)
        self.chat_layout.addWidget(
            welcome, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self.chat_layout.addStretch(1)

    def add_message(self, author, message, is_user=False):
        bubble = MessageBubble(author, message, is_user)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if is_user:
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)

        wrapper = QWidget()
        wrapper.setLayout(row)
        self.chat_layout.insertWidget(
            max(0, self.chat_layout.count() - 1), wrapper
        )
        QTimer.singleShot(
            80,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            )
        )

    def send_message(self):
        if self.worker_thread is not None:
            return

        message = self.input.toPlainText().strip()
        if not message:
            return

        if self.chat_layout.count():
            first = self.chat_layout.itemAt(0).widget()
            if first and first.findChild(QLabel, "welcomeTitle"):
                self.clear_chat()
                self.chat_layout.addStretch(1)

        self.add_message("Tu", message, is_user=True)
        self.input.clear()

        self.send_button.setEnabled(False)
        self.input.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.status_label.setText("●  IDOMA STA ELABORANDO")
        self.composer_hint.setText("Attendi: sto preparando la risposta...")

        self.worker_thread = QThread(self)
        self.worker = ChatWorker(self.core, message)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.show_response)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self.worker_finished)
        self.worker_thread.start()


    def toggle_voice(self):
        # Se il microfono è già attivo, interrompe l'ascolto.
        if self.voice_thread is not None and self.voice_thread.isRunning():
            self.voice_thread.stop()
            self.mic_button.setEnabled(False)
            self.composer_hint.setText("Interruzione dell'ascolto...")
            return

        # Evita di avviare un comando vocale mentre IDOMA sta rispondendo.
        if self.worker_thread is not None:
            self.composer_hint.setText(
                "Attendi che IDOMA termini la risposta."
            )
            return

        self.mic_button.setText("■")
        self.mic_button.setToolTip("Interrompi l'ascolto")

        self.status_label.setText("● IDOMA IN ASCOLTO")
        self.composer_hint.setText(
            "Pronuncia IDOMA per attivarla, poi comunica il comando."
        )

        self.voice_thread = VoiceWorker()

        self.voice_thread.status.connect(self.voice_status)
        self.voice_thread.transcript.connect(self.voice_transcribed)
        self.voice_thread.error.connect(self.voice_error)
        self.voice_thread.finished.connect(self.voice_finished)

        self.voice_thread.start()


    def voice_status(self, messaggio):
        self.status_label.setText("● IDOMA IN ASCOLTO")
        self.composer_hint.setText(messaggio)


    def voice_transcribed(self, comando):
        self.input.setPlainText(comando)
        self.send_message()


    def voice_error(self, errore):
        self.show_notice(
            "Errore microfono",
            f"Non è stato possibile utilizzare il microfono:\n\n{errore}"
        )


    def voice_finished(self):
        self.voice_thread = None

        self.mic_button.setEnabled(True)
        self.mic_button.setText("♫")
        self.mic_button.setToolTip("Attiva il riconoscimento vocale")

        # Non sovrascrive lo stato se IDOMA sta già elaborando un comando.
        if self.worker_thread is None:
            self.status_label.setText("● IDOMA LOCALE")
            self.composer_hint.setText(
                "Motore locale pronto • Qwen3 1.7B • Memoria SQLite"
            )


    def show_response(self, response):
        self.add_message("IDOMA", response, is_user=False)

    def worker_finished(self):
        self.worker_thread = None
        self.worker = None
        self.send_button.setEnabled(True)
        self.input.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.status_label.setText("●  IDOMA LOCALE")
        self.composer_hint.setText(
            "Motore locale pronto • Qwen3 1.7B • Memoria SQLite"
        )
        self.input.setFocus()

    def show_memory(self):
        self.input.setPlainText("/memoria")
        self.send_message()

    def new_conversation(self):
        if self.worker_thread is not None:
            return
        self.core.nuova_conversazione()
        self.input.clear()
        self.show_welcome()

    def show_notice(self, title, message):
        QMessageBox.information(self, title, message)

    def closeEvent(self, event):
        if self.voice_thread is not None:
            if self.voice_thread.isRunning():
                self.voice_thread.stop()
                self.voice_thread.wait()

        event.accept()

    def apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget#root {{
                background: {BG}; color: {TEXT};
                font-family: "Segoe UI"; font-size: 10pt;
            }}
            QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
            QLabel#brand {{ color: {TEXT}; font-size: 19pt; font-weight: 700; letter-spacing: 2px; }}
            QLabel#version, QLabel#sidebarSection {{ color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
            QPushButton#newChatButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 9px; padding: 12px; text-align: left; font-weight: 600; }}
            QPushButton#newChatButton:hover, QPushButton#sidebarButton:hover {{ background: #242a35; }}
            QPushButton#sidebarButton {{ background: transparent; color: #c4cad4; border: none; border-radius: 8px; padding: 11px 9px; text-align: left; }}
            QPushButton#sidebarButton:disabled {{ color: #737b89; }}
            QLabel#sidebarFooter {{ color: {MUTED}; font-size: 9pt; padding: 10px 2px; border-top: 1px solid {BORDER}; }}
            QFrame#header {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
            QLabel#headerTitle {{ color: {TEXT}; font-size: 13pt; font-weight: 600; }}
            QLabel#statusPill {{ color: #9dbce4; background: #1a2b40; border: 1px solid #294568; border-radius: 12px; padding: 7px 11px; font-size: 8pt; font-weight: 700; }}
            QLabel#welcomeTitle {{ color: {TEXT}; font-size: 23pt; font-weight: 600; }}
            QLabel#welcomeSubtitle {{ color: {MUTED}; font-size: 11pt; }}
            QPushButton#suggestionCard {{ background: {PANEL}; color: #cbd5e3; border: 1px solid {BORDER}; border-radius: 12px; padding: 12px; text-align: left; }}
            QPushButton#suggestionCard:hover {{ background: #242a35; border: 1px solid #426b9b; }}
            QFrame#composer {{ background: {PANEL}; border: 1px solid #343c49; border-radius: 16px; }}
            QPlainTextEdit#messageInput {{ background: transparent; color: {TEXT}; border: none; selection-background-color: #367fe0; font-size: 11pt; }}
            QPushButton#iconButton {{ background: #252c37; color: #c5d9f3; border: 1px solid #384455; border-radius: 12px; min-width: 42px; min-height: 42px; font-size: 16pt; }}
            QPushButton#sendButton {{ background: #367fe0; color: white; border: none; border-radius: 12px; min-width: 42px; min-height: 42px; font-size: 19pt; font-weight: 700; }}
            QPushButton#sendButton:hover {{ background: #4b91ed; }}
            QLabel#composerHint {{ color: #778191; font-size: 8pt; }}
            QFrame#userMessage {{ background: #24364b; border: 1px solid #35516f; border-radius: 14px; }}
            QFrame#assistantMessage {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
            QLabel#messageAuthor {{ color: #8ebeff; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
            QLabel#messageBody {{ color: {TEXT}; font-size: 10pt; }}
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ background: {BG}; width: 9px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: #343c49; border-radius: 4px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IDOMA")
    app.setFont(QFont("Segoe UI", 10))
    window = IdomaWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
