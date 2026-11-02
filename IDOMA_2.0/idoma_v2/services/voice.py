from __future__ import annotations

import array
import json
from collections import deque
import math
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable

from ..config import PROJECT_ROOT

WAKE_MODEL_DIR = PROJECT_ROOT / "vosk-model-small-it-0.22"
WHISPER_MODEL_NAME = os.getenv("IDOMA_WHISPER_MODEL", "base")
AUDIO_BLOCK = 4000
TARGET_SAMPLE_RATE = 16000


def normalise_wake_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return " ".join(value.split())


def is_wake_phrase(text: str) -> bool:
    """Recognise Hey IDOMA and common Italian/Vosk transcription variants."""
    value = normalise_wake_text(text)
    if value in {"idoma", "i doma"}:
        # Vosk sometimes drops the English 'hey' even when the user says it.
        return True
    return bool(re.search(r"\b(?:hey|ehi|hei|ei|ai)\s+(?:i\s+)?(?:doma|idoma|idioma)\b", value))


def strip_wake_prefix(text: str) -> str:
    """Remove wake words and any pre-wake audio picked up by the short ring buffer."""
    spoken = text.strip()
    phrase = re.search(
        r"\b(?:hey|ehi|hei|ei|ai)[\s,.:;!?-]+(?:i\s+)?(?:idoma|idioma|doma)\b[\s,.:;!?-]*",
        spoken,
        flags=re.IGNORECASE,
    )
    if phrase:
        return spoken[phrase.end():].strip()
    # Vosk occasionally omits 'hey'; the wake listener has already confirmed
    # the trigger, so remove the first IDOMA token even if the buffer starts earlier.
    bare = re.search(r"\b(?:idoma|i\s+doma)\b[\s,.:;!?-]*", spoken, flags=re.IGNORECASE)
    return spoken[bare.end():].strip() if bare else spoken


class VoiceAssistant:
    """Offline wake-word listener + local Whisper transcription + local TTS."""

    def __init__(
        self,
        status_callback: Callable[[str], None],
        command_callback: Callable[[str], str],
        stop_event: threading.Event,
    ):
        self.status_callback = status_callback
        self.command_callback = command_callback
        self.stop_event = stop_event
        self._sd = None
        self._np = None
        self._wake_model = None
        self._whisper = None
        self._tts = None
        self._sample_rate = TARGET_SAMPLE_RATE

    def _status(self, message: str) -> None:
        try:
            self.status_callback(message)
        except Exception:
            pass

    def _load_models(self) -> None:
        if not WAKE_MODEL_DIR.is_dir():
            raise FileNotFoundError(
                f"Modello Vosk non trovato: {WAKE_MODEL_DIR}. "
                "La cartella vosk-model-small-it-0.22 deve restare nella cartella PersonalAI."
            )

        import numpy as np
        import sounddevice as sd
        import pyttsx3
        from vosk import Model
        from faster_whisper import WhisperModel

        self._np = np
        self._sd = sd
        device = sd.query_devices(kind="input")
        self._sample_rate = int(device["default_samplerate"])
        if self._sample_rate < 8000:
            raise RuntimeError("La frequenza del microfono non è supportata.")

        self._status("Caricamento del riconoscimento vocale locale…")
        self._wake_model = Model(str(WAKE_MODEL_DIR))
        self._whisper = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, min(4, os.cpu_count() or 2)),
        )
        self._tts = pyttsx3.init()
        self._tts.setProperty("rate", int(os.getenv("IDOMA_TTS_RATE", "180")))
        try:
            for voice in self._tts.getProperty("voices") or []:
                identity = f"{voice.id} {voice.name}".casefold()
                if "ital" in identity or "it-it" in identity:
                    self._tts.setProperty("voice", voice.id)
                    break
        except Exception:
            pass

    def _speak(self, text: str) -> None:
        if self._tts is None or not text:
            return
        # Spoken replies should be useful, but not read an entire long report aloud.
        spoken = text.strip()
        if len(spoken) > 900:
            spoken = spoken[:880].rsplit(" ", 1)[0] + ". Il resto è disponibile nella chat."
        try:
            self._tts.stop()
            self._tts.say(spoken)
            self._tts.runAndWait()
        except Exception as exc:
            self._status(f"Sintesi vocale non disponibile: {exc}")

    def _decode_audio_chunks(self, chunks):
        raw = b"".join(chunks)
        audio = self._np.frombuffer(raw, dtype=self._np.int16).astype(self._np.float32) / 32768.0
        return self._resample_audio(audio)

    def _resample_audio(self, audio):
        if self._sample_rate != TARGET_SAMPLE_RATE and len(audio):
            new_length = max(1, int(len(audio) * TARGET_SAMPLE_RATE / self._sample_rate))
            old_positions = self._np.arange(len(audio), dtype=self._np.float32)
            new_positions = self._np.linspace(0, max(0, len(audio) - 1), new_length, dtype=self._np.float32)
            audio = self._np.interp(new_positions, old_positions, audio).astype(self._np.float32)
        return audio

    def _listen_for_wake(self):
        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(self._wake_model, self._sample_rate)
        history = deque(maxlen=max(1, int(8 * self._sample_rate / AUDIO_BLOCK)))
        self._status("In ascolto: pronuncia «Hey IDOMA».")
        with self._sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=AUDIO_BLOCK,
            dtype="int16",
            channels=1,
        ) as stream:
            while not self.stop_event.is_set():
                data, _overflow = stream.read(AUDIO_BLOCK)
                audio = bytes(data)
                history.append(audio)
                if recognizer.AcceptWaveform(audio):
                    phrase = json.loads(recognizer.Result()).get("text", "")
                    if is_wake_phrase(phrase):
                        # Keep the phrase audio so Whisper can also hear a command
                        # spoken immediately after "Hey IDOMA" in the same sentence.
                        return self._decode_audio_chunks(list(history)), phrase
                    recognizer = KaldiRecognizer(self._wake_model, self._sample_rate)
        return None

    def _capture_command(self):
        chunks = []
        started = False
        started_at = time.monotonic()
        last_voice_at = started_at
        max_seconds = float(os.getenv("IDOMA_VOICE_MAX_SECONDS", "15"))
        silence_seconds = float(os.getenv("IDOMA_VOICE_SILENCE_SECONDS", "1.1"))
        threshold = int(os.getenv("IDOMA_VOICE_RMS_THRESHOLD", "180"))
        self._status("Ti ascolto…")

        with self._sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=AUDIO_BLOCK,
            dtype="int16",
            channels=1,
        ) as stream:
            while not self.stop_event.is_set():
                data, _overflow = stream.read(AUDIO_BLOCK)
                raw = bytes(data)
                samples = array.array("h")
                samples.frombytes(raw)
                if samples:
                    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
                else:
                    rms = 0.0
                now = time.monotonic()

                if rms >= threshold:
                    started = True
                    last_voice_at = now
                if started:
                    chunks.append(self._np.frombuffer(raw, dtype=self._np.int16).astype(self._np.float32) / 32768.0)
                    if now - last_voice_at >= silence_seconds or now - started_at >= max_seconds:
                        break
                elif now - started_at >= 5.0:
                    return None

        if not chunks or self.stop_event.is_set():
            return None
        audio = self._np.concatenate(chunks)
        return self._resample_audio(audio)

    def _transcribe(self, audio) -> str:
        segments, _info = self._whisper.transcribe(
            audio,
            language="it",
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def run_forever(self) -> None:
        self._load_models()
        self._status("IDOMA è pronta.")
        consecutive_audio_errors = 0
        while not self.stop_event.is_set():
            try:
                wake_result = self._listen_for_wake()
                if wake_result is None:
                    continue
                if self.stop_event.is_set():
                    break
                consecutive_audio_errors = 0
                self._status("IDOMA attivata.")
                wake_audio, _wake_text = wake_result
                self._status("Riconosco il comando…")
                command = strip_wake_prefix(self._transcribe(wake_audio))
                if not command:
                    self._speak("Dimmi, ti ascolto.")
                    audio = self._capture_command()
                    if audio is None:
                        if not self.stop_event.is_set():
                            self._speak("Non ho sentito nulla. Riprova quando vuoi.")
                        continue
                    self._status("Trascrivo il comando…")
                    command = self._transcribe(audio)
                if not command:
                    self._speak("Non ho capito. Puoi ripetere?")
                    continue
                self._status(f"Comando ricevuto: {command}")
                try:
                    reply = self.command_callback(command)
                except Exception as exc:
                    reply = f"Non riesco a completare la richiesta: {exc}"
                if reply:
                    self._speak(reply)
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                consecutive_audio_errors += 1
                self._status(f"Problema con microfono o modelli vocali: {exc}")
                if consecutive_audio_errors >= 3:
                    raise RuntimeError("Tre errori consecutivi del microfono. Controlla il dispositivo audio.") from exc
                self.stop_event.wait(3.0)
        self._status("Ascolto vocale disattivato.")
