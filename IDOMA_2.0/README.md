# IDOMA 2.5.0

IDOMA è un assistente personale locale per Windows. Il PC ospita il motore, il database, l'agente desktop, il microfono e le notifiche. L'interfaccia web/PWA permette di usare la chat anche da un altro dispositivo quando il PC è acceso e raggiungibile tramite una connessione privata.

## Stato della release

Questa release integra:
- applicazione residente nell'area di notifica di Windows;
- avvio automatico facoltativo con Windows;
- server locale e agente desktop avviati insieme;
- wake phrase **«Hey IDOMA»**, riconoscimento vocale locale con Vosk e Faster-Whisper, risposta vocale con pyttsx3;
- apertura controllata di applicazioni, cartelle e documenti;
- memoria personale con protezione contro il ripristino automatico di informazioni dimenticate;
- promemoria persistenti, notifiche Windows e riepiloghi giornalieri;
- impostazione locale predefinita e fallback cloud disattivato.

Non sono ancora integrati la sincronizzazione con Google/Outlook Calendar, l'accesso alla posta elettronica o una connessione iPhone remota già configurata. Non considerare queste funzioni disponibili finché non vengono collegate e testate.

## Requisiti e struttura delle cartelle

La struttura prevista riutilizza il progetto già presente sul PC:

```text
PersonalAI/
├── .venv/
├── personal_ai.db
├── vosk-model-small-it-0.22/
├── app.py                  # vecchia applicazione, conservata
├── main.py                 # vecchia applicazione, conservata
└── IDOMA_2.0/
    ├── Avvia IDOMA.bat
    ├── avvia_desktop.py
    ├── requirements-v2.txt
    └── idoma_v2/
```

Requisiti: Windows 10/11, Python 3.11 o compatibile, Ollama con il modello `qwen3:1.7b`, ambiente virtuale esistente `PersonalAI/.venv` e cartella del modello Vosk italiano `PersonalAI/vosk-model-small-it-0.22`.

Faster-Whisper usa il modello `base` per impostazione predefinita. Se non è già presente nella cache, il primo avvio può scaricarlo. La successiva trascrizione avviene localmente.

Per personalizzare porta, provider, orari dei briefing o soglia del microfono, copia `IDOMA_2.0/.env.example` in `IDOMA_2.0/.env` e modifica i valori desiderati. Il file `.env` non va caricato su GitHub.

## Avvio

1. Estrai `IDOMA_2.0` dentro la cartella `PersonalAI`, accanto al database e al modello Vosk.
2. Verifica che Ollama sia avviato e che `qwen3:1.7b` sia installato.
3. Fai doppio clic su **`IDOMA_2.0/Avvia IDOMA.bat`**.
4. Se mancano dipendenze, il launcher le installa nell'ambiente virtuale esistente. Non crea un secondo ambiente.
5. IDOMA avvia il server, l'agente Windows e i servizi di promemoria. L'icona resta accanto all'orologio.
6. Dal menu dell'icona scegli **Apri IDOMA**. Al primo accesso, scegli **Copia token API** dal menu dell'icona, incollalo in Impostazioni nell'interfaccia web e salva.

Dal menu dell'icona puoi anche:
- attivare o disattivare **Ascolto vocale attivo**;
- abilitare **Avvia con Windows**;
- scegliere **Esci da IDOMA** per arrestare i servizi.

## Voce

La wake phrase è **«Hey IDOMA»**. Puoi pronunciare il comando nella stessa frase, per esempio:

- «Hey IDOMA, apri Spotify».
- «Hey IDOMA, cerca il PDF della tesi».
- «Hey IDOMA, ricordami di chiamare mamma domani alle 10».

Vosk rileva la wake phrase; Faster-Whisper trascrive il comando in italiano; pyttsx3 legge la risposta. Il microfono può essere disattivato dal menu dell'icona. Il comportamento va ancora verificato sul microfono reale del Lenovo: soglia audio, rumore ambientale e disponibilità della voce italiana possono richiedere regolazioni.

## Promemoria e riepiloghi

Esempi di richieste:

- `Ricordami di chiamare mamma domani alle 10:30`
- `Ricordami di pagare la bolletta tra 20 minuti`
- `Ricordami di inviare il documento il 03/11 alle 9`

Se manca l'orario, IDOMA chiede di specificarlo. Puoi anche usare:

- `/promemoria` per vedere i promemoria attivi;
- `/completa 3` per completare il promemoria con ID 3;
- `/rimanda 3 10` per rimandarlo di dieci minuti;
- `/oggi` oppure «Organizza la giornata» per un riepilogo.

Le notifiche dei promemoria arrivano su Windows. I riepiloghi automatici sono impostati alle **08:00** e alle **21:00**. Puoi cambiare gli orari in `.env` tramite `IDOMA_MORNING_BRIEFING_TIME` e `IDOMA_EVENING_BRIEFING_TIME`; lascia il valore vuoto per disattivare il relativo riepilogo. Se IDOMA viene avviata entro quattro ore dall'orario programmato, recupera il riepilogo una sola volta.

Queste funzioni si basano sui promemoria locali. Il calendario esterno non è ancora sincronizzato.

## Privacy e accesso remoto

- Il server ascolta su `127.0.0.1` per impostazione predefinita.
- Il token API viene conservato in `IDOMA_2.0/.idoma_token`; puoi copiarlo dal menu dell'icona. Non condividerlo e non caricarlo su GitHub.
- Il fallback verso un provider cloud è disattivato. Per autorizzarlo esplicitamente, imposta `IDOMA_ALLOW_CLOUD=1` nel file `.env` e configura il provider.
- Non esporre la porta HTTP 8000 direttamente su Internet. Per l'accesso da iPhone usa una VPN o un tunnel cifrato. Il PC deve essere acceso e IDOMA in esecuzione.
- La PWA non è un backend cloud sempre attivo: con il PC spento, le funzioni locali e le notifiche non possono essere eseguite.

## Database e compatibilità con la vecchia applicazione

Il percorso predefinito del database resta `PersonalAI/personal_ai.db`. IDOMA aggiunge tabelle con prefisso `idoma2_`; non elimina né sovrascrive le tabelle storiche `messaggi`, `memorie` e `ricordi`. Le vecchie applicazioni e i relativi file vengono conservati.

**Non sostituire mai `personal_ai.db` con un database vuoto.** Prima di provare una nuova release, chiudi IDOMA e fai una copia di sicurezza del database.

## Test

Dalla cartella `IDOMA_2.0`, con l'ambiente virtuale attivato:

```powershell
python -m unittest discover -s tests -v
```

La suite copre memoria, instradamento dei comandi, sicurezza delle azioni, promemoria e coda delle attività desktop. I test automatici non sostituiscono la prova sul Lenovo: microfono, wake phrase, TTS, avvio automatico e notifiche Windows devono essere verificati sul dispositivo reale.

## Versione

`2.5.0` — desktop Windows, voce locale, promemoria e briefing proattivi.
