# IDOMA 2.1.0 — Tool Engine e capacità desktop riutilizzabili

Questa release introduce il primo Tool Engine di IDOMA. Le richieste vengono instradate verso strumenti riutilizzabili, con parametri strutturati e risultati verificati dall’agente Windows. Non serve aggiungere una regola per ogni applicazione: l’apertura è generica. Si aggiungono ricerca dei file per nome, apertura delle cartelle utente e informazioni essenziali sul PC. Non cancella né sovrascrive i file della vecchia applicazione.

## Garanzia sui dati

- Il database predefinito resta `PersonalAI/personal_ai.db` (la cartella che contiene `IDOMA_2.0`).
- Le tabelle storiche `messaggi`, `memorie` e `ricordi` non vengono eliminate né riscritte.
- IDOMA 2.0 aggiunge soltanto le tabelle `idoma2_conversations` e `idoma2_messages`.
- Le memorie precedenti vengono lette direttamente dal database esistente.
- Non copiare un database vuoto sopra quello esistente.

## Avvio su Windows

1. Estrai la cartella `IDOMA_2.0` dentro `C:\Users\<utente>\Documents\PersonalAI`, accanto a `app.py`, `idoma_core.py` e `personal_ai.db`.
2. Avvia Ollama e verifica che `qwen3:1.7b` sia disponibile.
3. Fai doppio clic su `avvia_idoma_2.bat`.
4. Al primo avvio compare un token personale nel terminale. Copialo.
5. Apri `http://127.0.0.1:8000`, incolla il token in Impostazioni e salva.

L'ambiente virtuale esistente `PersonalAI/.venv` viene riutilizzato. Se non è presente, lo script crea un ambiente dedicato nella cartella `IDOMA_2.0/.venv`.

## Agente Windows (azioni sul PC)

Dopo aver avviato il server, apri una seconda finestra del terminale e avvia `run_desktop_agent.bat`. L'agente mantiene il collegamento con il server e accetta azioni strutturate e limitate: apertura di applicazioni individuate tramite collegamenti del menu Start, apertura di siti tramite URL HTTPS validati, Documenti e Download. Non esegue comandi PowerShell o codice arbitrario generato dall'AI.

Puoi scrivere in linguaggio naturale, ad esempio `Apri TikTok sul mio computer`, `Mi apri il browser?` oppure `Vorrei andare su YouTube`. Il modulo AI estrae l'intenzione e il nome del servizio senza richiedere una regola per ogni frase o applicazione. L'agente cerca prima l'app nel menu Start; se non la trova e il modello conosce con certezza il sito ufficiale, apre il sito HTTPS nel browser. Se non è sicuro dell'indirizzo, non inventa un URL. Se il PC è spento o l'agente non è avviato, IDOMA te lo segnala. Per un server cloud, imposta `IDOMA_SERVER_URL` nell'ambiente del PC in modo che punti al dominio pubblico HTTPS.

## iPhone

Questa PWA è già responsive. Per provarla mentre il PC è acceso, iPhone e PC devono essere sulla stessa rete Wi-Fi. Sul telefono apri l'indirizzo LAN del PC, non `127.0.0.1` (ad esempio `http://192.168.x.x:8000`). Windows Firewall potrebbe chiedere di autorizzare Python sulla rete privata.

Per installarla: apri l'indirizzo HTTPS del server in Safari, premi Condividi e scegli **Aggiungi alla schermata Home**.

**Importante:** questa prova in rete locale non rende IDOMA indipendente dal PC. Per usarlo quando il Lenovo è spento, il backend deve essere pubblicato su un server cloud sempre raggiungibile, con database persistente e un provider AI online configurato. La PWA è già predisposta a collegarsi a un URL server diverso da quello locale.

## Modelli AI

Il router usa Ollama in locale. **Il cloud è disattivato per impostazione predefinita**, anche se hai inserito le credenziali. Per autorizzare esplicitamente l’invio di richieste e contesto al provider online, imposta `IDOMA_ALLOW_CLOUD=1` nel file `.env`; per mantenere il comportamento locale lascia `IDOMA_ALLOW_CLOUD=0`.

Per il cloud crea un file `.env` copiando `.env.example` e inserisci i valori sul server, mai nel JavaScript della PWA. L'uso di un provider cloud può comportare costi: non è attivato automaticamente.

## Comandi memoria

- `/memoria` — mostra i ricordi già presenti nel database.
- `/ricorda ...` — aggiunge un ricordo nella tabella storica `ricordi`.
- `/dimentica ...` — elimina dalla tabella `ricordi` i ricordi che contengono il testo indicato.

## Architettura inclusa

- `idoma_v2/server`: API FastAPI e autenticazione Bearer.
- `idoma_v2/services`: orchestrazione conversazioni e memoria.
- `idoma_v2/providers`: instradamento tra Ollama e provider cloud OpenAI-compatible.
- `idoma_v2/web`: interfaccia web installabile come PWA.
- `idoma_v2/desktop_agent.py`: agente Windows con coda di attività e allowlist di azioni.

## Limiti espliciti di questa release

Questa è la nuova base backend/mobile, con apertura generica delle app e dei siti, non ancora la sostituzione completa dell'applicazione desktop precedente. Le azioni Windows (aprire programmi, gestire file locali), la voce integrata, i collegamenti a email/calendario e la distribuzione cloud definitiva sono i moduli successivi da collegare. Il vecchio `app.py`, `idoma_core.py`, `test_voce.py` e `personal_ai.db` restano al loro posto e continuano a essere disponibili.

## Pubblicazione cloud

Il `Dockerfile` prepara il backend per un host Docker. Prima della pubblicazione occorre configurare:
- `IDOMA_ENV=production`
- `IDOMA_API_TOKEN` con un segreto casuale lungo
- `IDOMA_DB_PATH` su un volume persistente
- un provider AI cloud, se il PC non deve essere acceso
- HTTPS e un dominio pubblico

Non pubblicare il servizio con il database su disco effimero: i dati potrebbero andare persi al riavvio o a una nuova distribuzione.


## IDOMA 2.0.2 fixes

- The chat waits briefly for the Desktop Agent and reports the actual Windows result or error instead of claiming that a queued task succeeded.
- Desktop Agent polls every second and logs each received task.
- Generic open-intent parsing falls back to a deterministic parser even when the local model returns `action=none`.
- Exact Start Menu shortcut matches are checked before fuzzy matching, and desktop search is limited to top-level shortcuts.
- Existing `personal_ai.db` is retained; no database deletion or reset is performed.
- Generic Windows URI-protocol fallback can launch apps registered with a protocol handler (without maintaining a per-app list).


## IDOMA 2.0.3 — correzione estrazione del nome dell'app

- Il nome dell'applicazione viene separato dalle formule conversazionali (ad esempio "un attimo", "un secondo", "per favore").
- Quando il modello AI estrae correttamente il nome dell'app, il parser non lo sovrascrive più con la frase letterale non ripulita.
- Il parser deterministico resta come fallback se il modello non restituisce un'entità utilizzabile.
- I test includono richieste come "puoi aprire un attimo spotify?" e "mi apri Spotify un secondo, per favore?".


## IDOMA 2.1.0 — Tool Engine

Il catalogo degli strumenti è consultabile tramite `GET /api/tools` (richiede il token). Le capacità Windows disponibili in questa release sono:

- `open_target`: apre applicazioni installate o siti HTTPS, senza un elenco fisso di app.
- `search_files`: cerca per nome nelle cartelle Desktop, Documenti e Download; non legge il contenuto dei file. La ricerca è limitata a 5.000 file per mantenere il PC reattivo.
- `open_folder`: apre Desktop, Documenti o Download.
- `open_path`: apre un percorso solo se si trova in una delle cartelle utente autorizzate.
- `pc_status`: restituisce nome del PC, sistema operativo e spazio disco disponibile.

Il Desktop Agent esegue esclusivamente strumenti registrati. Non esegue comandi PowerShell, script o codice generato dal modello. L’apertura di percorsi locali è confinata alle cartelle utente indicate; la ricerca è limitata ai nomi dei file.

### Test della release

I test automatici coprono l’estrazione delle intenzioni di apertura e il routing delle nuove capacità. Per questa build sono stati eseguiti 17 test automatici e la compilazione dei moduli Python. Il test finale dell’esecuzione delle azioni deve comunque essere effettuato sul PC Windows dell’utente.

### Prossime fasi

1. Memoria personale strutturata e recupero più pertinente, senza alterare i ricordi esistenti.
2. Strumenti documentali: lettura controllata di PDF e documenti, con conferma quando necessario.
3. Integrazioni email e calendario tramite autorizzazioni esplicite.
4. Pubblicazione cloud con database persistente e provider AI online, per rendere l’iPhone indipendente dal PC.


## IDOMA 2.2.0 — Memoria personale e cartelle Windows

Questa release aggiunge una memoria strutturata per associazioni personali e amplia la gestione delle cartelle. Le tabelle storiche `messaggi`, `memorie` e `ricordi` non vengono eliminate né riscritte. La nuova tabella `idoma2_memory_facts` viene aggiunta in modo non distruttivo allo stesso database.

### Insegnare un'associazione a IDOMA

Puoi scrivere in chat, per esempio:

- `Ricorda che il mio curriculum si chiama CB`
- `Quando dico CV intendo CB`
- `/associa curriculum = CB`

IDOMA salva l'associazione come fatto strutturato e la riutilizza nelle successive ricerche per nome. Per curriculum riconosce anche gli alias `CV`, `curriculum vitae` e `resume`; per tesi riconosce `tesi magistrale` e `thesis`. Le associazioni possono essere aggiornate ripetendo l'istruzione con un valore nuovo. `/memoria` mostra sia i ricordi storici sia i fatti strutturati.

### Cartelle personali Windows

L'agente risolve Desktop, Documenti, Download, Immagini, Musica e Video usando gli identificativi Known Folder di Windows, quindi funziona anche se le cartelle sono state rinominate, spostate o reindirizzate a OneDrive. Sono supportati alias italiani e inglesi come `galleria`, `foto`, `immagini`, `music` e `musica`.

### Ricerca file

La ricerca esamina i nomi dei file nelle cartelle personali disponibili, non i contenuti dei documenti. I termini brevi come `CB` vengono confrontati come parole complete, evitando corrispondenze casuali dentro parole più lunghe. Sono previsti limiti di sicurezza di 25.000 file o 7 secondi per mantenere il PC reattivo. I valori associati in memoria vengono aggiunti automaticamente alla ricerca.

### Test

Esegui i test da `IDOMA_2.0` con:

`python -m unittest discover -s tests -v`

La prova finale di apertura delle cartelle deve essere eseguita sul PC Windows dell'utente.


## IDOMA 2.3.0 — ricerca dentro i documenti

Questa release aggiunge la ricerca del contenuto, oltre alla ricerca dei nomi dei file. L'agente Windows può estrarre testo da PDF, Word `.docx`, Excel `.xlsx`, PowerPoint `.pptx` e file `.txt`, `.md`, `.csv` e `.rtf`. Per ogni risultato mostra nome, percorso e un estratto con riferimento a pagina, paragrafo, foglio o diapositiva quando disponibile. I file Word/Excel/PowerPoint nei vecchi formati binari `.doc`, `.xls` e `.ppt` non sono ancora supportati. I PDF composti soltanto da immagini/scansioni richiedono OCR e non vengono letti da questa versione.

L'indice dei documenti è conservato nella nuova tabella `idoma2_document_index` del database locale `personal_ai.db`: non viene creato un secondo archivio di testi e non vengono eliminate o modificate le tabelle precedenti. I documenti vengono reindicizzati solo quando cambia dimensione o data di modifica. Per contenere l'uso di memoria, l'indice gestisce fino a 1.200 documenti e conserva fino a 80.000 caratteri per file; la scansione è inoltre limitata a 24 secondi per richiesta. Se raggiunge un limite, IDOMA lo segnala e puoi ripetere la ricerca.

Esempi: `Trova il documento in cui si parla del progetto iDOMA`, `In quale file avevo scritto PID controller?`, `Cerca dentro i PDF la frase recupero del calore`, `Cerca nel contenuto dei documenti sostenibilità`. La ricerca è locale, per parole e frasi, non un sistema semantico/AI né OCR.


## IDOMA 2.3.1

- Le richieste come "trova sustainability nei miei file" vengono instradate alla ricerca nel contenuto dei documenti, non alla ricerca per nome.
- Le domande "dove ho scritto ..." e "in quali file ho scritto ..." sono riconosciute come ricerche documentali.
- Il limite della risposta dell'agente Windows è stato portato a 12.000 caratteri, evitando HTTP 422 quando la ricerca restituisce più risultati.


## IDOMA 2.3.2 — memoria personale affidabile

- Il pulsante iniziale **La mia memoria** invia direttamente `/memoria`; la richiesta non può più essere confusa con l'apertura di un sito. Anche frasi naturali come "Cosa ricordi di me?" e "Mostrami cosa ricordi di me usando il comando /memoria" vengono instradate alla memoria.
- Le istruzioni esplicite "Ricorda che mi chiamo Marco", "Ricordati che mi chiamo Marco" e "Tieni a mente che il mio nome è Marco" vengono salvate nella memoria personale strutturata.
- Le domande "Come mi chiamo?" e "Qual è il mio nome?" vengono risolte direttamente dalla memoria locale, senza attendere il modello AI.
- Al primo accesso dopo l'aggiornamento, IDOMA recupera anche le istruzioni esplicite sul nome presenti nelle conversazioni già salvate, così da non perdere un'informazione scritta prima di questa versione.
- Le modifiche sono additive: non vengono cancellati o sovrascritti i database, le conversazioni o i ricordi esistenti.

Test automatici della release: 44 test superati.


## IDOMA 2.3.3 — privacy e memoria affidabile

- Il provider cloud è ora disabilitato per impostazione predefinita. La presenza di una chiave API non autorizza da sola l'invio di dati: serve `IDOMA_ALLOW_CLOUD=1`.
- Il comando `/dimentica` rimuove anche le voci corrispondenti dalla vecchia tabella `memorie`, quando presente.
- Le informazioni dimenticate ricevono un blocco di recupero, così la scansione della cronologia non le reinserisce automaticamente. Un nuovo comando esplicito `/ricorda` può salvarle di nuovo.
- Il recupero automatico di vecchie istruzioni di memoria è limitato alla conversazione attiva.
- Il contesto strutturato inviato al modello viene filtrato in base alla richiesta, anziché includere indiscriminatamente tutti i fatti.
- Le richieste negative come `Non aprire Spotify` o `Non cercare il PDF` non vengono trasformate in azioni desktop.

- Gli URL generati dal modello non vengono più eseguiti: solo un indirizzo digitato direttamente dall'utente può essere aperto come URL; per gli altri nomi IDOMA cerca l'app installata o apre una ricerca web.
