
import array
import json
import math
import re
import time
from pathlib import Path

import sounddevice as sd
from vosk import Model, KaldiRecognizer


CARTELLA = Path(__file__).resolve().parent
PERCORSO_MODELLO = CARTELLA / "vosk-model-small-it-0.22"

_model = None


def carica_modello():
    global _model

    if _model is None:
        if not PERCORSO_MODELLO.exists():
            raise FileNotFoundError(
                "Non trovo il modello italiano: controlla la cartella "
                "vosk-model-small-it-0.22."
            )

        _model = Model(str(PERCORSO_MODELLO))

    return _model


def estrai_comando(frase):
    frase = frase.lower().strip()
    frase = re.sub(r"[^a-zàèéìòù ]", " ", frase)
    frase = re.sub(r"\s+", " ", frase).strip()

    risvegli = [
        r"\b(?:idoma|idioma)\b",
        r"\bi\s+doma\b",
        r"\bai\s+doma\b",
        r"\bdi\s+doma\b"
    ]

    for pattern in risvegli:
        risultato = re.search(pattern, frase)

        if risultato:
            return frase[risultato.end():].strip()

    return None


def ascolta_comando(stop_event=None, aggiorna_stato=None):

    model = carica_modello()

    # Utilizza la frequenza supportata dal microfono predefinito.
    dispositivo = sd.query_devices(kind="input")
    frequenza = int(dispositivo["default_samplerate"])
    nome_microfono = dispositivo["name"]

    recognizer = KaldiRecognizer(model, frequenza)

    attesa_comando = False
    scadenza = 0

    inizio_ascolto = time.monotonic()
    ultima_voce = None
    voce_iniziata = False
    audio_rilevato = False
    avviso_silenzio = 0
    risveglio_parziale = False

    def aggiorna(testo):
        if aggiorna_stato:
            aggiorna_stato(testo)

    def gestisci_frase(frase):
        nonlocal attesa_comando
        nonlocal scadenza
        nonlocal recognizer
        nonlocal risveglio_parziale

        frase = frase.strip().lower()

        if not frase:
            return None

        # Dopo il risveglio, la frase successiva è il comando.
        if attesa_comando:
            return frase

        # Cerca la parola IDOMA, anche se Vosk la trascrive
        # come "idioma" oppure "i doma".
        comando = estrai_comando(frase)

        if comando is not None:

            if comando:
                return comando

            # È stata pronunciata soltanto la parola IDOMA.
            attesa_comando = True
            scadenza = time.monotonic() + 15

            aggiorna("IDOMA attivata! Ora parla.")

            recognizer = KaldiRecognizer(model, frequenza)
            risveglio_parziale = False

        else:
            risveglio_parziale = False
            aggiorna("Non ho riconosciuto IDOMA. Riprova.")

        return None

    aggiorna(
        f"Microfono: {nome_microfono}. Pronuncia IDOMA..."
    )

    with sd.RawInputStream(
        samplerate=frequenza,
        blocksize=0,
        dtype="int16",
        channels=1
    ) as stream:

        while stop_event is None or not stop_event.is_set():

            dati, overflow = stream.read(4000)
            audio = bytes(dati)

            adesso = time.monotonic()

            # Controlla il volume del segnale ricevuto.
            campioni = array.array("h")
            campioni.frombytes(audio)

            if campioni:
                rms = math.sqrt(
                    sum(x * x for x in campioni) / len(campioni)
                )
            else:
                rms = 0

            if rms > 120:
                ultima_voce = adesso
                voce_iniziata = True

                if not audio_rilevato:
                    audio_rilevato = True
                    aggiorna(
                        "Microfono attivo: audio rilevato. Pronuncia IDOMA..."
                    )

            # Avvisa se il microfono sembra non ricevere audio.
            if (
                not audio_rilevato
                and adesso - inizio_ascolto > 6
                and adesso - avviso_silenzio > 6
            ):
                aggiorna(
                    "Microfono aperto, ma non rilevo audio. "
                    "Controlla il dispositivo di ingresso."
                )
                avviso_silenzio = adesso

            # Scadenza dei 15 secondi per pronunciare il comando.
            if attesa_comando and adesso > scadenza:
                attesa_comando = False
                recognizer = KaldiRecognizer(model, frequenza)
                aggiorna("Tempo scaduto. Pronuncia nuovamente IDOMA.")

            # Riconoscimento della frase completa.
            if recognizer.AcceptWaveform(audio):

                risultato = json.loads(recognizer.Result())
                frase = risultato.get("text", "")

                recognizer = KaldiRecognizer(model, frequenza)
                voce_iniziata = False
                ultima_voce = None

                comando = gestisci_frase(frase)

                if comando:
                    return comando

                continue

            # Controlla anche il riconoscimento parziale.
            risultato = json.loads(recognizer.PartialResult())
            parziale = risultato.get("partial", "")

            if (
                not attesa_comando
                and not risveglio_parziale
                and estrai_comando(parziale) is not None
            ):
                aggiorna(
                    "Ho sentito IDOMA. Completa la frase..."
                )
                risveglio_parziale = True

            # Sicurezza aggiuntiva: se Vosk non chiude la frase
            # autonomamente, la finalizza dopo 0,9 secondi di silenzio.
            if (
                voce_iniziata
                and ultima_voce is not None
                and adesso - ultima_voce > 0.9
            ):
                risultato = json.loads(recognizer.FinalResult())
                frase = risultato.get("text", "")

                recognizer = KaldiRecognizer(model, frequenza)
                voce_iniziata = False
                ultima_voce = None

                comando = gestisci_frase(frase)

                if comando:
                    return comando

    return None
