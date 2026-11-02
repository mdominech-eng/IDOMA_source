import sounddevice as sd
from faster_whisper import WhisperModel

FREQUENZA = 16000
DURATA = 5

print("Caricamento di Whisper...")
modello = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
    cpu_threads=4
)

print("\nWhisper è pronto.")
input("Premi INVIO e poi pronuncia una frase...")

print("\nTi ascolto...")
audio = sd.rec(
    int(DURATA * FREQUENZA),
    samplerate=FREQUENZA,
    channels=1,
    dtype="float32"
)
sd.wait()

print("Elaborazione...")
segmenti, informazioni = modello.transcribe(
    audio.flatten(),
    language="it",
    beam_size=5,
    vad_filter=True,
    condition_on_previous_text=False
)

testo = " ".join(
    segmento.text.strip() for segmento in segmenti
).strip()

print("\nLingua rilevata:", informazioni.language)
print("TESTO RICONOSCIUTO:", testo if testo else "Nessuna voce riconosciuta.")