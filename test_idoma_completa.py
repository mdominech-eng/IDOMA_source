import json
import re
from pathlib import Path

import sounddevice as sd
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel

CARTELLA = Path(__file__).resolve().parent
PERCORSO_MODELLO = CARTELLA / "vosk-model-small-it-0.22"

FREQUENZA = 16000

print("Caricamento di Vosk...")
modello_vosk = Model(str(PERCORSO_MODELLO))

print("Caricamento di Whisper...")
modello_whisper = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
    cpu_threads=4
)

print("\nIDOMA è pronta.")
print("Pronuncia IDOMA per attivarla.")
print("Premi CTRL+C per terminare.\n")

try:
    riconoscitore = KaldiRecognizer(modello_vosk, FREQUENZA)

    with sd.RawInputStream(
        samplerate=FREQUENZA,
        blocksize=8000,
        dtype="int16",
        channels=1
    ) as stream:

        while True:
            dati, overflow = stream.read(4000)

            if riconoscitore.AcceptWaveform(bytes(dati)):
                risultato = json.loads(riconoscitore.Result())
                frase = risultato.get("text", "").lower().strip()

                if not frase:
                    continue

                print("Riconosciuto:", frase)

                parole = re.sub(
                    r"[^a-zàèéìòù ]", " ", frase
                ).split()

                if "idoma" in parole or "idioma" in parole:
                    print("\nIDOMA ATTIVATA!")
                    break

    # Il microfono viene riaperto per registrare il comando.
    print("Ora pronuncia il tuo comando...")

    audio = sd.rec(
        int(6 * FREQUENZA),
        samplerate=FREQUENZA,
        channels=1,
        dtype="float32"
    )
    sd.wait()

    print("Elaborazione del comando...")

    segmenti, informazioni = modello_whisper.transcribe(
        audio.flatten(),
        language="it",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False
    )

    comando = " ".join(
        segmento.text.strip() for segmento in segmenti
    ).strip()

    print("\nCOMANDO RICONOSCIUTO:", comando)

except KeyboardInterrupt:
    print("\nTest terminato.")

except Exception as errore:
    print("\nErrore:", errore)