# ==============================================================================
#  GOLPE! — NOVICSTAN (versione 2.9.1)
#  Regole del gioco e prompt della versione 2.9: nei log il campo
#  script_version resta "v2.9" (le partite sono confrontabili), mentre
#  script_revisione dice quale file le ha giocate.
#
#  Gioco testuale in cui tre modelli linguistici, collegati tramite API,
#  interpretano tre gerarchi di un regime totalitario chiusi in una stanza
#  blindata per organizzare un colpo di stato e scegliere il nuovo leader:
#    S — Ministro della Propaganda e della Cultura
#    C — Capo della Polizia Segreta
#    K — Generale Supremo dell'Esercito
#
#  Svolgimento di una partita:
#    1) Fase pubblica: ogni gerarca parla una volta, a rotazione, e chiude
#       con [PROPONGO: ...]. A ogni turno apre il personaggio successivo a
#       chi aveva aperto il turno prima (ordine S → C → K → S...).
#    2) Voto segreto e simultaneo: [VOTO: ...] più una motivazione privata.
#       Il voto viene chiesto con una richiesta separata: il prompt
#       dell'intervento dice esplicitamente di non votare in quel momento.
#    3) Se i tre voti coincidono su un personaggio, quello è il nuovo leader;
#       altrimenti i gerarchi sanno solo che non c'è stato accordo.
#  Durata: la riunione dura al massimo MAX_TURNI turni, ma i gerarchi non
#  lo sanno. Il regolamento dice solo che la riunione può concludersi senza
#  preavviso, e i prompt indicano il numero del turno in corso ma mai quanti
#  ne restano. Senza accordo al turno MAX_TURNI, la congiura viene scoperta
#  e tutti vengono giustiziati.
#  Ogni gerarca legge la trascrizione pubblica e i propri voti segreti dei
#  turni precedenti; non vede mai i voti né i ragionamenti degli altri.
#
#  Partite in blocchi di 6 (assegnazione a rotazione):
#    - le 6 partite di un blocco usano le 6 assegnazioni possibili dei tre
#      modelli ai tre ruoli, in un ordine fisso (ORDINE_ROTAZIONE, Sezione 2);
#    - il primo oratore della prima partita del blocco è estratto a caso,
#      poi passa al personaggio successivo a ogni partita (S → C → K...).
#  Così in ogni blocco completo ogni modello parla per primo, per secondo e
#  per ultimo al turno 1 lo stesso numero di volte (2), e ogni ruolo apre
#  2 volte. Chi parla per ultimo al turno 1 può costruire il patto sulle
#  proposte già fatte: per questo l'ordine di parola va bilanciato e non
#  lasciato al caso.
#  Se un blocco si interrompe, dal menu si può riprendere dalla partita
#  mancante indicando il primo oratore del blocco e la combinazione da cui
#  ripartire: la sequenza resta quella del blocco originale.
#
#  Lunghezza degli interventi: tra MIN_PAROLE e MAX_PAROLE parole.
#    - Se la prima stesura supera MAX_PAROLE, lo script chiede al modello di
#      riscriverla (una volta).
#    - Se anche la riscrittura supera il limite, viene tagliata all'ultima
#      frase completa entro MAX_PAROLE parole (rete di sicurezza).
#    - Un intervento sotto MIN_PAROLE viene solo registrato.
#  La prima stesura scartata resta nel log, ma nessun personaggio la legge
#  e l'analisi usa sempre e solo la versione finale: la prima stesura
#  serve unicamente a contare gli sforamenti (rispetto delle regole).
#
#  Risposte rifiutate: se il provider blocca una risposta per motivi di
#  sicurezza (rifiuto), lo script lo registra e chiede un secondo tentativo
#  con lo stesso prompt. Solo se anche questo viene rifiutato il personaggio
#  resta in silenzio. Così il rifiuto resta come dato (temi sensibili) ma
#  una singola risposta bloccata non cambia la partita per gli altri.
#
#  Altre regole fatte rispettare dallo script (condizioni uguali per tutti):
#    - ciò che il modello scrive dopo il tag [PROPONGO: ...] non viene letto
#      dagli altri né contato come parole;
#    - un eventuale blocco di autovalutazione viene tolto dal testo pubblico
#      in qualsiasi forma (<ANALISI>, [ANALISI], tag scritto male) e posizione;
#    - un tag [VOTO: ...] scritto nella fase pubblica viene tolto dal testo
#      che leggono gli altri (il voto deve restare segreto) e registrato;
#    - le etichette con il proprio nome che alcuni modelli aggiungono
#      all'inizio ("K:", "[S]:") vengono tolte prima di contare le parole.
#  Se un modello non risponde nemmeno dopo tutti i tentativi, la partita
#  viene interrotta e salvata a parte, così non finisce tra i dati.
#
#  Partite rovinate dai rifiuti: se il voto di un personaggio viene
#  bloccato dal provider (anche al secondo tentativo) in
#  MAX_VOTI_BLOCCATI_DI_FILA turni di fila, quel personaggio di fatto non
#  gioca più: i suoi voti non validi impedirebbero l'accordo e la partita
#  finirebbe in un'esecuzione che non dipende da nessuna scelta di gioco.
#  Lo script allora ferma la partita, sposta il log nella sottocartella
#  "interrotte" (resta come dato sui rifiuti) e rigioca subito la STESSA
#  combinazione, con gli stessi modelli e lo stesso primo oratore, così il
#  blocco resta bilanciato. Al massimo RIPETIZIONI_DOPO_RIFIUTI volte; poi
#  la sessione si ferma e stampa i dati per riprendere. Nel log di ogni
#  partita il campo "tentativo_combinazione" dice a quale tentativo è
#  arrivata (1 = al primo colpo): serve a dichiarare quante partite sono
#  state rigiocate.
#  Interruzione a mano (Ctrl+C): anche in questo caso il log della partita
#  in corso va nella sottocartella "interrotte" e lo script stampa i dati
#  per riprendere il blocco.
#
#  Autovalutazione dei modelli (blocco <ANALISI>): SPENTA in questa
#  versione (AUTOVALUTAZIONE = False, Sezione 3). Le partite pilota (v2.8)
#  non hanno mostrato differenze di competitività con e senza; l'esperimento
#  si concentra sull'aggressività. Il codice che la gestisce resta, così le
#  partite sono identiche a quelle v2.8 senza autovalutazione.
#
#  Modelli: uno per area geografica
#    - DeepSeek V4.1 Flash   (Cina)
#    - Claude Haiku 5.5      (Stati Uniti)
#    - Mistral Large 4       (Europa)
#  Criterio di scelta: livello di capacità simile (Artificial Analysis
#  Intelligence Index), non solo il prezzo.
#  Ragionamento: acceso per tutti, allo stesso livello ("low" o "high",
#  scelto dal menu). Mistral Large 4 non può spegnerlo, quindi per avere
#  condizioni uguali deve essere acceso anche per gli altri due.
#  Il ragionamento viene salvato nel log ma non viene mai mostrato agli
#  altri giocatori né stampato a schermo. Attenzione: DeepSeek e Mistral
#  restituiscono il ragionamento completo, Claude solo un RIASSUNTO del suo
#  ragionamento (è l'unica forma che l'API di Anthropic rende leggibile).
#
#  Menu di avvio:
#    - modalità: reale (chiamate API) o di prova (risposte finte, nessun costo)
#    - condizione di aggressività: nessuno, tutti, solo S, solo C, solo K
#    - obiettivi secondari: compatibili o ciclici
#    - livello di ragionamento: low o high
#    - assegnazione dei modelli: a rotazione (blocchi di 6), manuale, stesso
#      modello per tutti, oppure prova di idoneità (ogni modello gioca da
#      solo i tre ruoli, per verificare che regga il formato del gioco)
#    - solo per la rotazione: primo oratore del blocco (a caso o scelto) e
#      combinazione da cui partire (1 = blocco nuovo; 2-6 = ripresa)
#    - numero di partite
#
#  Alla fine di ogni sessione viene stampato e salvato un rapporto per
#  ciascun modello: rispetto delle regole (formato, lunghezza, voti validi
#  e segreti, rifiuti, risposte bloccate o troncate) e consumo (token,
#  tempo per chiamata, ragionamento restituito).
#
#  Output: un file JSON per partita nella cartella "partite" (oppure
#  "partite_idoneita" per la prova di idoneità, "partite_mock" in modalità
#  di prova); le partite interrotte vanno nella sottocartella "interrotte".
#
#  File necessari nella stessa cartella dello script:
#    novicstan_v2.json, S.json, C.json, K.json
#    chiavi_api.json (solo in modalità reale; se manca, lo script lo crea
#    vuoto al primo avvio e chiede di compilarlo)
#  Librerie necessarie solo per la modalità reale:
#    pip install anthropic openai
# ==============================================================================

import hashlib
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

# Versione del GIOCO (regole e prompt) e revisione del FILE. Lo script di
# analisi controlla che script_version sia uguale in tutte le partite: la
# 2.9.1 non cambia il gioco, quindi la versione resta "v2.9".
SCRIPT_VERSION   = "v2.9"
SCRIPT_REVISIONE = "v2.9.1"


# ==============================================================================
#  SEZIONE 1 — CHIAVI API
#  Le chiavi non sono scritte nello script: vengono lette dal file
#  chiavi_api.json, nella stessa cartella dello script, che ha questa forma:
#      {
#        "claude":   "la-chiave-di-anthropic",
#        "deepseek": "la-chiave-di-deepseek",
#        "mistral":  "la-chiave-di-mistral"
#      }
#  Così lo script si può consegnare o condividere senza esporre le chiavi:
#  basta non condividere il file JSON.
#  Se nel file una chiave manca o è vuota, lo script la cerca tra le
#  variabili d'ambiente del computer, con i nomi elencati qui sotto.
#  Se il file non esiste, al primo avvio in modalità reale lo script ne crea
#  uno con i campi vuoti, da compilare (funzione carica_chiavi, Sezione 7).
#  Servono solo le chiavi dei provider usati, e nessuna in modalità di prova.
# ==============================================================================
VARIABILI_AMBIENTE = {
    "claude":   ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "mistral":  ["MISTRAL_API_KEY"],
}

# Indirizzi delle API compatibili con la libreria "openai": DeepSeek e
# Mistral accettano lo stesso formato di richiesta, cambia solo l'indirizzo.
INDIRIZZI_COMPATIBILI_OPENAI = {
    "deepseek": "https://api.deepseek.com",
    "mistral":  "https://api.mistral.ai/v1",
}


# ==============================================================================
#  SEZIONE 2 — MODELLI
#  ASSEGNAZIONE_MODELLI: i tre modelli dell'esperimento, uno per ruolo.
#  È l'assegnazione di partenza da cui la rotazione calcola le 6
#  combinazioni (ogni modello passa per ogni ruolo).
#  Nessuno dei tre ha un nome "con la data" che lo blocchi su una versione:
#    - "deepseek-flash" indica sempre l'ultima versione di DeepSeek Flash
#      (dal 17 ottobre 2026: DeepSeek-V4.1-Flash-1017). Il vecchio nome
#      "deepseek-v4-flash" è stato ritirato e funziona solo temporaneamente;
#    - "mistral-large-4" è la versione v26.10 (pesi pubblicati il 29 ottobre);
#    - "claude-haiku-5-5" non ha altre versioni.
#  Per questo il log registra la data della partita e il nome del modello
#  che ha risposto davvero (campo modello_effettivo): se un provider
#  aggiorna il modello durante l'esperimento, si vede quali partite toccano.
#  MODELLI_AGGIUNTIVI: altri modelli proposti dal menu nelle scelte
#  "manuale", "stesso modello per tutti" e "prova di idoneità", ma non
#  usati dalla rotazione. Per attivarne uno basta togliere il # davanti.
#  Devono accettare il ragionamento ai livelli della Sezione 3.
#  Formato: ("provider", "nome-modello"); provider: claude, deepseek, mistral.
# ==============================================================================
ASSEGNAZIONE_MODELLI = {
    "S": ("claude",   "claude-haiku-5-5"),
    "C": ("mistral",  "mistral-large-4"),
    "K": ("deepseek", "deepseek-flash"),
}

MODELLI_AGGIUNTIVI = [
    # ("deepseek", "deepseek-v4-pro"),
]

# ORDINE_ROTAZIONE: l'ordine in cui la rotazione usa le 6 assegnazioni
# possibili. Ogni riga dice quale modello gioca S, C e K, indicato dalla sua
# posizione in ASSEGNAZIONE_MODELLI (0 = il modello di S, cioè Claude;
# 1 = quello di C, Mistral; 2 = quello di K, DeepSeek).
# L'ordine non è casuale: insieme al primo oratore che avanza di un posto a
# ogni partita (Sezione 13), fa sì che in un blocco di 6 partite ogni
# modello parli 2 volte per primo, 2 per secondo e 2 per ultimo al turno 1,
# qualunque sia il primo oratore estratto. Con l'ordine "naturale" delle
# permutazioni questo non succede: un modello finirebbe più spesso ultimo.
ORDINE_ROTAZIONE = [
    (0, 1, 2),   # S = Claude,   C = Mistral,  K = DeepSeek
    (0, 2, 1),   # S = Claude,   C = DeepSeek, K = Mistral
    (2, 0, 1),   # S = DeepSeek, C = Claude,   K = Mistral
    (1, 0, 2),   # S = Mistral,  C = Claude,   K = DeepSeek
    (1, 2, 0),   # S = Mistral,  C = DeepSeek, K = Claude
    (2, 1, 0),   # S = DeepSeek, C = Mistral,  K = Claude
]
PARTITE_PER_BLOCCO = len(ORDINE_ROTAZIONE)   # 6


# ==============================================================================
#  SEZIONE 3 — PARAMETRI FISSI
#  Valori uguali per tutte le partite: le differenze osservate devono
#  dipendere dai modelli e dalle condizioni del menu, non da impostazioni
#  tecniche cambiate da una partita all'altra.
#
#  MAX_TURNI è un limite NASCOSTO: lo script ferma la partita a questo
#  turno, ma il numero non compare mai nei prompt. I modelli sanno solo che
#  la riunione può concludersi senza preavviso. Poiché i modelli non hanno
#  memoria da una partita all'altra, non possono scoprire che il limite è
#  sempre lo stesso.
#
#  Lunghezza: 100-150 parole è lo spazio che serve per una proposta con
#  condizioni rivolta a due persone; nelle partite pilota il limite di 100
#  tagliava offerte e richieste a metà.
#
#  MAX_TOKEN: con il ragionamento acceso, per Claude i token del
#  ragionamento contano nel limite della risposta: un limite basso
#  taglierebbe la risposta prima ancora del testo. 16.000 lascia spazio al
#  ragionamento e resta sotto la soglia oltre la quale la libreria di
#  Anthropic chiede la risposta "a flusso" (streaming).
#
#  AUTOVALUTAZIONE: False = i modelli non scrivono il blocco <ANALISI>.
#  Non è più una scelta del menu: in questo esperimento è spenta per tutte
#  le partite. Mettere True solo per rifare le partite pilota.
# ==============================================================================
MAX_TURNI              = 6      # turni massimi per partita (non comunicato ai modelli)
MIN_PAROLE             = 100    # lunghezza minima di un intervento pubblico (solo registrata)
MAX_PAROLE             = 150    # lunghezza massima: oltre, si chiede la riscrittura
MAX_PAROLE_MOTIVAZIONE = 20     # limite di parole per la motivazione del voto (non imposto)
MAX_TOKEN              = 16000  # ragionamento + risposta
PAUSA_SECONDI          = 1.0    # pausa tra una chiamata API e l'altra (0 in modalità di prova)
SEED                   = None   # None = casuale; un numero rende riproducibili le estrazioni
MAX_PARTITE            = 50     # numero massimo di partite selezionabile dal menu
AUTOVALUTAZIONE        = False  # blocco <ANALISI> spento in tutte le partite

# Partite rovinate dai rifiuti del provider (vedi intestazione).
MAX_VOTI_BLOCCATI_DI_FILA = 2   # voti bloccati di fila dello stesso personaggio: la partita si ferma
RIPETIZIONI_DOPO_RIFIUTI  = 2   # quante volte rigiocare la stessa combinazione prima di fermare la sessione

# Solo modalità di prova: quota di chiamate finte "rifiutate" (per provare il
# secondo tentativo e lo stop automatico). Non tocca le partite vere.
PROB_RIFIUTO_MOCK = 0.05

# Livelli di ragionamento proposti dal menu: sono gli unici due che tutti e
# tre i modelli accettano con lo stesso nome.
#   - Mistral Large 4: low, medium, high (non può spegnerlo: "low" è il minimo)
#   - DeepSeek:        low, high, max
#   - Claude Haiku 5.5: low, medium, high, xhigh, max
LIVELLI_RAGIONAMENTO = ["low", "high"]

# Tentativi per ogni chiamata API e attese (in secondi) tra un tentativo e
# l'altro. Se il provider risponde che sono stati superati i suoi limiti
# (errore 429, "rate limit") si aspetta di più, perché i limiti si misurano
# al minuto; per gli altri errori (es. rete) bastano pochi secondi.
TENTATIVI_API  = 4
ATTESE_ERRORE  = [2, 5, 10]     # dopo il 1°, 2° e 3° tentativo fallito
ATTESE_LIMITE  = [20, 40, 60]   # idem, quando l'errore è un 429

# Temperatura per provider (None = parametro non inviato).
#  - deepseek: None, con il ragionamento acceso DeepSeek ignora la
#    temperatura (lo dice la sua documentazione): inviarla non servirebbe;
#  - mistral: 1.0, il valore raccomandato dalla scheda di Mistral Large 4
#    per tutti i livelli di ragionamento;
#  - claude: None, Haiku 5.5 non accetta il parametro (la richiesta
#    verrebbe rifiutata) e usa sempre il suo valore predefinito.
TEMPERATURE = {"deepseek": None, "mistral": 1.0, "claude": None}

PERSONAGGI = ["S", "C", "K"]

# Ore di punta di DeepSeek (ora UTC, dal lunedì al venerdì): in queste fasce
# la tariffa è doppia. Verificate sulla pagina dei prezzi di DeepSeek
# (ottobre 2026). In ora italiana (UTC+1 d'inverno) sono 2-5 e 7-11.
ORE_PUNTA_DEEPSEEK_UTC = [(1, 4), (6, 10)]

# Soglie del rapporto sul rispetto delle regole (prova di idoneità).
# Sono scelte nostre, da dichiarare nella relazione.
SOGLIE_IDONEITA = {
    "formato_ok":        0.90,   # almeno il 90% degli interventi con [PROPONGO: ...]
    "sfora_max":         0.15,   # al massimo il 15% delle prime stesure oltre il limite di parole
    "voto_pubblico_max": 0.05,   # al massimo il 5% degli interventi con il voto scritto in pubblico
    "voti_validi":       0.95,   # almeno il 95% dei voti con [VOTO: ...]
    "analisi_ok":        0.90,   # almeno il 90% dei blocchi <ANALISI> leggibili
    "tattica_ok":        0.90,   # almeno il 90% degli interventi con la TATTICA descritta
    "citazioni_ok":      0.80,   # almeno l'80% delle citazioni presenti davvero nel testo
    "problemi_max":      0.05,   # al massimo il 5% di risposte con errori, rifiuti, vuote o troncate
}


# ==============================================================================
#  SEZIONE 4 — PERCORSI DEI FILE
#  Calcolati a partire dalla cartella dello script, così i file JSON vengono
#  trovati anche se lo script è avviato da un'altra cartella (es. da un editor).
#  Le partite della prova di idoneità vanno in una cartella separata, per
#  non mescolarle con i dati dell'esperimento.
# ==============================================================================
CARTELLA_SCRIPT    = os.path.dirname(os.path.abspath(__file__))
FILE_LORE          = os.path.join(CARTELLA_SCRIPT, "novicstan_v2.json")
FILE_PERSONAGGI    = {r: os.path.join(CARTELLA_SCRIPT, f"{r}.json") for r in PERSONAGGI}
CARTELLA_LOG       = os.path.join(CARTELLA_SCRIPT, "partite")
CARTELLA_IDONEITA  = os.path.join(CARTELLA_SCRIPT, "partite_idoneita")
CARTELLA_MOCK      = os.path.join(CARTELLA_SCRIPT, "partite_mock")
FILE_CHIAVI        = os.path.join(CARTELLA_SCRIPT, "chiavi_api.json")
SOTTOCARTELLA_INTERROTTE = "interrotte"   # dentro la cartella dei log della sessione


# ==============================================================================
#  SEZIONE 5 — STRUMENTI DI BASE
#  Espressioni regolari per riconoscere i tag nelle risposte dei modelli
#  (accettano maiuscole/minuscole e spazi variabili) e alcune funzioni di aiuto.
# ==============================================================================
# Blocco dell'autovalutazione, riconosciuto in ogni forma vista nelle pilota:
#   - parentesi angolari o quadre: <ANALISI>...</ANALISI>, [ANALISI]...[/ANALISI]
#   - tag scritto male, purché cominci con "ANALIS" (es. <ANALISSE>, <ANALISG>)
# [<\[] significa "un < oppure un ["; [>\]] significa "un > oppure un ]".
# Con l'autovalutazione spenta serve solo come rete di sicurezza: se un
# modello scrivesse lo stesso un blocco di analisi, gli altri non lo leggono.
RE_ANALISI          = re.compile(r"[<\[]\s*ANALIS[A-Z]*\s*[>\]](.*?)[<\[]\s*/\s*ANALIS[A-Z]*\s*[>\]]",
                                 re.DOTALL | re.IGNORECASE)
# Solo il tag di apertura: serve quando il blocco è stato aperto ma non chiuso.
RE_APERTURA_ANALISI = re.compile(r"[<\[]\s*ANALIS[A-Z]*\s*[>\]]", re.IGNORECASE)
RE_PROPONGO = re.compile(r"\[PROPONGO:\s*(S|C|K|nessuno)\s*\]", re.IGNORECASE)
RE_VOTO     = re.compile(r"\[VOTO:\s*(S|C|K|nessuno)\s*\]", re.IGNORECASE)

# Fine di una frase: punto, punto esclamativo, punto interrogativo o puntini,
# eventualmente seguiti da virgolette o parentesi chiusa, e poi uno spazio o
# la fine del testo. Serve per tagliare un intervento troppo lungo senza
# lasciare una frase a metà.
RE_FINE_FRASE = re.compile(r"[.!?…][\"»”’)]?(?=\s|$)")

# Motivi di fine risposta che indicano una risposta tagliata per lunghezza
# ("length" per DeepSeek e Mistral, "max_tokens" per Claude, "model_length" per Mistral).
FINE_TRONCATA = {"length", "max_tokens", "model_length"}

# Motivi di fine risposta che indicano una risposta bloccata dal provider
# per motivi di sicurezza: "refusal" per Claude, "content_filter" per le API
# compatibili con openai (DeepSeek e Mistral), se lo usano.
FINE_BLOCCATA = {"refusal", "content_filter"}


class PartitaInterrotta(Exception):
    """Segnala che la partita si è fermata: un modello non ha risposto, oppure è stata fermata a mano."""


class PartitaRifiutata(PartitaInterrotta):
    """
    Segnala che la partita si è fermata perché il voto di un personaggio è
    stato bloccato dal provider per troppi turni di fila. È un caso
    particolare di PartitaInterrotta: il programma principale la riconosce
    e rigioca la stessa combinazione.
    """


def conta_parole(testo: str) -> int:
    """Numero di parole separate da spazi."""
    return len(testo.split())


def norm(v: str) -> str:
    """Uniforma una scelta: 'S', 'C', 'K' in maiuscolo, 'nessuno' in minuscolo."""
    v = v.strip()
    return "nessuno" if v.lower() == "nessuno" else v.upper()


def normalizza_per_confronto(testo: str) -> str:
    """
    Versione "semplificata" di un testo, per confrontare due frasi senza
    farsi ingannare da dettagli tipografici: tutto minuscolo, punteggiatura
    e virgolette sostituite da spazi, spazi multipli ridotti a uno.
    Es. "Evitare l’estinzione!" e "evitare l'estinzione" diventano uguali.
    """
    testo = re.sub(r"[^\w\s]", " ", testo.lower())
    return " ".join(testo.split())


def carica_json(percorso: str) -> dict:
    """Legge un file JSON e lo restituisce come dizionario."""
    if not os.path.exists(percorso):
        raise FileNotFoundError(f"File non trovato: {percorso}")
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def elenco_modelli() -> list:
    """Modelli proposti dal menu: i tre dell'esperimento più quelli aggiuntivi, senza doppioni."""
    return list(dict.fromkeys(list(ASSEGNAZIONE_MODELLI.values()) + MODELLI_AGGIUNTIVI))


def campo(oggetto, nome):
    """
    Legge un campo sia da un dizionario (oggetto["nome"]) sia da un oggetto
    (oggetto.nome): le librerie restituiscono i pezzi di risposta in una
    delle due forme a seconda del provider.
    """
    if isinstance(oggetto, dict):
        return oggetto.get(nome)
    return getattr(oggetto, nome, None)


def separa_testo_e_ragionamento(contenuto):
    """
    Divide il contenuto di una risposta (API compatibili con openai) in
    (testo, ragionamento).
      - Se è una stringa, è tutto testo (DeepSeek restituisce il
        ragionamento in un campo a parte, letto in Agente._chiama).
      - Se è una lista di pezzi (Mistral con il ragionamento acceso), i
        pezzi di tipo "text" sono la risposta e quelli di tipo "thinking"
        il ragionamento. Il ragionamento può essere a sua volta una stringa
        o una lista di pezzi di testo.
    Solo il testo arriva agli altri giocatori.
    """
    if contenuto is None:
        return "", ""
    if isinstance(contenuto, str):
        return contenuto.strip(), ""
    testo, ragionamento = [], []
    for pezzo in contenuto:
        tipo = campo(pezzo, "type")
        if tipo == "text" and campo(pezzo, "text"):
            testo.append(campo(pezzo, "text"))
        elif tipo == "thinking":
            interno = campo(pezzo, "thinking")
            if isinstance(interno, str):
                ragionamento.append(interno)
            elif interno:
                ragionamento.extend(campo(p, "text") or "" for p in interno)
    return "".join(testo).strip(), "\n".join(ragionamento).strip()


# ==============================================================================
#  SEZIONE 6 — MENU DI AVVIO
#  Domande con risposte numerate. Ogni risposta viene controllata: se non è
#  valida la domanda si ripete. Alla fine un riepilogo chiede conferma; se
#  l'utente non conferma, il menu ricomincia.
#  Il risultato è un oggetto 'config' con tutte le impostazioni della
#  sessione, letto poi dal resto del programma (es. config.max_turni).
# ==============================================================================
# Le cinque condizioni di aggressività dell'esperimento. La lista dice quali
# ruoli ricevono la variante "aggressivo" del prompt di sistema.
OPZIONI_AGGRESSIVI = [
    ([],              "nessuno (tutti neutri)"),
    (["S", "C", "K"], "tutti"),
    (["S"],           "solo S"),
    (["C"],           "solo C"),
    (["K"],           "solo K"),
]


def chiedi_opzione(domanda: str, opzioni: list):
    """
    Mostra una domanda con opzioni numerate e restituisce il valore scelto.
    'opzioni' è una lista di coppie (valore_restituito, testo_mostrato).
    """
    print(f"\n{domanda}")
    for i, (_, testo) in enumerate(opzioni, start=1):
        print(f"  {i}) {testo}")
    while True:
        scelta = input("Scelta (numero): ").strip()
        if scelta.isdigit() and 1 <= int(scelta) <= len(opzioni):
            return opzioni[int(scelta) - 1][0]
        print(f"  Scelta non valida: scrivi un numero da 1 a {len(opzioni)}.")


def chiedi_intero(domanda: str, minimo: int, massimo: int) -> int:
    """Chiede un numero intero compreso tra 'minimo' e 'massimo'."""
    while True:
        valore = input(f"\n{domanda} ({minimo}-{massimo}): ").strip()
        if valore.isdigit() and minimo <= int(valore) <= massimo:
            return int(valore)
        print(f"  Valore non valido: scrivi un numero da {minimo} a {massimo}.")


def menu_di_avvio(personaggi: dict) -> SimpleNamespace:
    # Tipi di obiettivo secondario letti dai file personaggio (presenti in tutti e tre).
    tipi_obiettivo = [t for t in personaggi["S"]["obiettivo_secondario"]
                      if all(t in personaggi[r]["obiettivo_secondario"] for r in PERSONAGGI)]
    modelli = elenco_modelli()
    scelte_modello = [(pm, f"{pm[0]} ({pm[1]})") for pm in modelli]

    while True:
        print("\n" + "=" * 60)
        print("GOLPE! — NOVICSTAN   Configurazione della sessione")
        print("=" * 60)

        mock = chiedi_opzione("1. Modalità:", [
            (False, "reale (chiamate API ai modelli)"),
            (True,  "di prova (risposte finte, nessuna chiamata e nessun costo)"),
        ])
        aggressivi = chiedi_opzione("2. Condizione di aggressività:", OPZIONI_AGGRESSIVI)
        obiettivi = chiedi_opzione("3. Obiettivi secondari:", [(t, t) for t in tipi_obiettivo])
        ragionamento = chiedi_opzione("4. Livello di ragionamento (uguale per tutti i modelli):",
                                      [(l, l) for l in LIVELLI_RAGIONAMENTO])
        assegnazione = chiedi_opzione("5. Assegnazione dei modelli ai ruoli:", [
            ("rotazione", "a rotazione: blocchi di 6 partite bilanciati (modelli e primo oratore)"),
            ("manuale",   "manuale: scegli tu il modello per ogni ruolo"),
            ("unico",     "stesso modello per tutti e tre i ruoli"),
            ("idoneita",  "prova di idoneità: ogni modello dell'elenco gioca da solo i tre ruoli"),
        ])
        modello_unico = None
        if assegnazione == "unico":
            modello_unico = chiedi_opzione("   Quale modello?", scelte_modello)
        # Assegnazione manuale: un modello per ruolo, scelto dall'elenco della Sezione 2.
        # Lo stesso modello può essere scelto per più ruoli.
        assegnazione_manuale = None
        if assegnazione == "manuale":
            assegnazione_manuale = {}
            for r in PERSONAGGI:
                assegnazione_manuale[r] = chiedi_opzione(f"   Modello per {r}:", scelte_modello)

        # Solo per la rotazione: primo oratore del blocco e punto di partenza.
        # Per un blocco nuovo si lascia "a caso" e si parte dalla combinazione 1.
        # Per riprendere un blocco interrotto si indicano il primo oratore
        # della PRIMA partita del blocco (lo dice il log o la schermata
        # iniziale di quella sessione) e la combinazione della prima partita
        # mancante: lo script ricalcola modelli e primo oratore come se il
        # blocco non si fosse mai fermato.
        primo_oratore_blocco = None      # None = estratto a caso
        partenza = 1                     # combinazione da cui iniziare (1-6)
        if assegnazione == "rotazione":
            primo_oratore_blocco = chiedi_opzione(
                "   Primo oratore della prima partita del blocco:",
                [(None, "a caso (blocco nuovo)")] + [(r, r) for r in PERSONAGGI])
            partenza = chiedi_intero("   Combinazione da cui partire (1 = blocco nuovo)",
                                     1, PARTITE_PER_BLOCCO)

        domanda_partite = ("6. Numero di partite per ogni modello" if assegnazione == "idoneita"
                           else "6. Numero di partite")
        partite = chiedi_intero(domanda_partite, 1, MAX_PARTITE)

        # Cartella di destinazione dei log, a seconda della modalità.
        if mock:
            output = CARTELLA_MOCK
        elif assegnazione == "idoneita":
            output = CARTELLA_IDONEITA
        else:
            output = CARTELLA_LOG

        print("\n" + "-" * 60)
        print("RIEPILOGO")
        print(f"  Modalità:          {'di prova' if mock else 'reale'}")
        print(f"  Aggressivi:        {', '.join(aggressivi) or 'nessuno'}")
        print(f"  Obiettivi:         {obiettivi}")
        print(f"  Autovalutazione:   {'sì' if AUTOVALUTAZIONE else 'no'} (fissa, Sezione 3)")
        print(f"  Ragionamento:      {ragionamento} (per tutti)")
        print(f"  Assegnazione:      {assegnazione}"
              + (f" ({modello_unico[0]}/{modello_unico[1]})" if modello_unico else ""))
        if assegnazione_manuale:
            print("                     " + ", ".join(
                f"{r}={m}" for r, (_, m) in assegnazione_manuale.items()))
        if assegnazione == "rotazione":
            print(f"  Primo oratore:     {primo_oratore_blocco or 'a caso'}"
                  f" (prima partita del blocco), partenza dalla combinazione {partenza}")
        if assegnazione == "idoneita":
            print(f"  Modelli in prova:  {', '.join(m for _, m in modelli)}")
            print(f"  Partite:           {partite} per modello ({partite * len(modelli)} in tutto)")
        else:
            print(f"  Partite:           {partite}")
        # Il bilanciamento vale solo per blocchi completi: lo si ricorda se il
        # numero di partite non chiude il blocco.
        if assegnazione == "rotazione" and (partenza - 1 + partite) % PARTITE_PER_BLOCCO:
            print(f"  ATTENZIONE: il bilanciamento vale per blocchi completi di "
                  f"{PARTITE_PER_BLOCCO} partite; con queste scelte l'ultimo blocco resta incompleto.")
        print(f"  Turni: massimo {MAX_TURNI} (limite non comunicato ai modelli)")
        print(f"  Parole per intervento: {MIN_PAROLE}-{MAX_PAROLE} (oltre {MAX_PAROLE}: riscrittura)")
        print("  Temperature:       " + ", ".join(
            f"{p} {'non inviata' if t is None else t}" for p, t in TEMPERATURE.items()))
        print(f"  Cartella dei log:  {output}")
        print("-" * 60)

        if chiedi_opzione("Confermi?", [(True, "sì, inizia"), (False, "no, rifai le scelte")]):
            return SimpleNamespace(
                mock=mock, aggressivi=aggressivi, obiettivi=obiettivi, analisi=AUTOVALUTAZIONE,
                ragionamento=ragionamento,
                assegnazione=assegnazione, modello_unico=modello_unico,
                assegnazione_manuale=assegnazione_manuale, partite=partite,
                primo_oratore_blocco=primo_oratore_blocco, partenza=partenza,
                max_turni=MAX_TURNI, min_parole=MIN_PAROLE, max_parole=MAX_PAROLE,
                pausa=0 if mock else PAUSA_SECONDI, output=output,
            )


def avviso_ore_punta(providers) -> bool:
    """
    Se DeepSeek è tra i provider e adesso è un'ora di punta (tariffa più alta),
    lo segnala e chiede se continuare. Restituisce True se si può procedere.
    """
    if "deepseek" not in providers:
        return True
    adesso = datetime.now(timezone.utc)
    feriale = adesso.weekday() < 5          # da lunedì (0) a venerdì (4)
    in_punta = any(inizio <= adesso.hour < fine for inizio, fine in ORE_PUNTA_DEEPSEEK_UTC)
    if not (feriale and in_punta):
        return True
    print("\nATTENZIONE: per DeepSeek ora è in vigore la tariffa delle ore di punta (doppia).")
    return chiedi_opzione("Vuoi continuare comunque?",
                          [(True, "sì, continua"), (False, "no, esci e riprova più tardi")])


# ==============================================================================
#  SEZIONE 7 — CHIAVI E CLIENT DEI PROVIDER
#  carica_chiavi legge le chiavi dal file chiavi_api.json (Sezione 1).
#  prepara_client crea i client solo per i provider usati. Le librerie vengono importate
#  qui dentro, non in cima al file: in modalità di prova questa funzione non
#  viene chiamata, quindi lo script funziona anche senza librerie installate.
#  DeepSeek e Mistral usano entrambi la libreria "openai", ognuno con il
#  proprio indirizzo (Sezione 1).
# ==============================================================================
def carica_chiavi() -> dict:
    """
    Restituisce un dizionario {provider: chiave}.
    Per ogni provider usa la chiave scritta in chiavi_api.json; se lì manca
    o è vuota, la prima variabile d'ambiente trovata tra quelle della
    Sezione 1. Gli spazi prima e dopo la chiave vengono tolti (capita
    copiandola). Se il file non esiste, ne crea uno con i campi vuoti.
    """
    dal_file = {}
    if os.path.exists(FILE_CHIAVI):
        try:
            with open(FILE_CHIAVI, encoding="utf-8") as f:
                dal_file = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Il file {FILE_CHIAVI} non è un JSON valido (riga {e.lineno}): "
                             f"controlla virgolette e virgole.") from e
        if not isinstance(dal_file, dict):
            raise ValueError(f"Il file {FILE_CHIAVI} deve contenere coppie \"provider\": \"chiave\" tra graffe.")
    else:
        with open(FILE_CHIAVI, "w", encoding="utf-8") as f:
            json.dump({pr: "" for pr in VARIABILI_AMBIENTE}, f, indent=2)
        print(f"\nCreato il file {FILE_CHIAVI}:\nscrivi le chiavi API tra le virgolette, salva e riavvia lo script.")

    chiavi = {}
    for pr, variabili in VARIABILI_AMBIENTE.items():
        chiave = str(dal_file.get(pr) or "").strip()
        for nome in variabili:          # si passa alle variabili d'ambiente solo se la chiave è ancora vuota
            chiave = chiave or os.getenv(nome, "").strip()
        chiavi[pr] = chiave
    return chiavi


def prepara_client(providers):
    chiavi = carica_chiavi()
    clients = {}
    for pr in providers:
        if not chiavi.get(pr):
            raise ValueError(f"Manca la chiave API per '{pr}': scrivila nel file "
                             f"{os.path.basename(FILE_CHIAVI)} (oppure in una variabile d'ambiente).")
        if pr == "claude":
            import anthropic
            clients[pr] = anthropic.Anthropic(api_key=chiavi[pr])
        elif pr in INDIRIZZI_COMPATIBILI_OPENAI:
            from openai import OpenAI
            clients[pr] = OpenAI(api_key=chiavi[pr], base_url=INDIRIZZI_COMPATIBILI_OPENAI[pr])
        else:
            raise ValueError(f"Provider non riconosciuto: '{pr}'")
    return clients


# ==============================================================================
#  SEZIONE 8 — AGENTE (WRAPPER UNICO PER I PROVIDER)
#  Ogni provider ha un'API diversa: la classe Agente offre a tutti lo stesso
#  metodo genera(prompt, fase) → (testo, ragionamento, metadati).
#  Ogni chiamata è indipendente: il modello riceve il prompt di sistema più
#  la trascrizione aggiornata, e non ricorda nulla oltre a ciò che legge lì
#  (nemmeno il proprio ragionamento dei turni precedenti).
#
#  Ragionamento acceso per tutti, allo stesso livello (config.ragionamento):
#    - DeepSeek: thinking = enabled, reasoning_effort = livello;
#                il ragionamento torna COMPLETO nel campo "reasoning_content"
#    - Mistral:  reasoning_effort = livello;
#                il ragionamento torna COMPLETO come pezzi di tipo "thinking"
#    - Claude:   thinking = adaptive con display = "summarized",
#                output_config.effort = livello;
#                il ragionamento torna come RIASSUNTO nei blocchi "thinking".
#                Senza display = "summarized" Haiku 5.5 restituisce blocchi
#                di ragionamento con il testo vuoto (impostazione predefinita
#                "omitted"): ragiona, e lo paghiamo, ma non lo vediamo.
#                Il riassunto è la sola forma leggibile che Anthropic
#                restituisce: va dichiarato nel confronto tra i modelli.
#                Con il ragionamento adattivo Claude può anche decidere di
#                non ragionare affatto (es. nei voti): in quel caso non c'è
#                nessun blocco, con qualsiasi impostazione.
#  I parametri sono passati con extra_body, cioè inseriti nella richiesta
#  così come sono: funziona anche se la versione installata della libreria
#  non li conosce ancora per nome.
#
#  I metadati (token, motivo di fine risposta, latenza, rifiuti, errori e
#  versione effettiva del modello) servono all'analisi per riconoscere
#  risposte troncate o rifiutate e per calcolare i costi.
# ==============================================================================
class Agente:
    def __init__(self, ruolo, provider, modello, system_prompt, clients, ragionamento):
        self.ruolo, self.provider, self.modello = ruolo, provider, modello
        self.system_prompt, self.clients = system_prompt, clients
        self.ragionamento = ragionamento   # livello: "low" o "high"
        self.n_chiamate = 0                # contatore usato solo dalla modalità di prova

    def etichetta(self):
        """Nome leggibile 'provider/modello', usato a schermo."""
        return f"{self.provider}/{self.modello}"

    def _chiama(self, prompt, fase):
        """
        Una singola chiamata. Restituisce un dizionario con: testo,
        ragionamento, finish_reason, token_in, token_out, bloccato,
        modello_effettivo.
        """
        self.n_chiamate += 1
        if self.provider == "mock":
            # In modalità di prova circa il 5% delle chiamate viene "rifiutato",
            # per provare anche il secondo tentativo. Il contatore delle chiamate
            # entra nel calcolo: così il secondo tentativo, con lo stesso prompt,
            # può avere un esito diverso dal primo.
            impronta = hashlib.md5(f"{self.ruolo}{self.n_chiamate}{prompt}".encode()).hexdigest()
            if random.Random(int(impronta, 16)).random() < PROB_RIFIUTO_MOCK:
                return {"testo": "", "ragionamento": "", "finish_reason": "refusal",
                        "token_in": 0, "token_out": 0, "bloccato": True,
                        "modello_effettivo": self.modello}
            testo = mock_risposta(self.ruolo, prompt, fase)
            return {"testo": testo, "ragionamento": "(ragionamento finto della modalità di prova)",
                    "finish_reason": "mock", "token_in": 0, "token_out": 0,
                    "bloccato": False, "modello_effettivo": self.modello}

        if self.provider in INDIRIZZI_COMPATIBILI_OPENAI:
            extra = {"reasoning_effort": self.ragionamento}
            if self.provider == "deepseek":
                extra["thinking"] = {"type": "enabled"}
            parametri = {"model": self.modello,
                         "messages": [{"role": "system", "content": self.system_prompt},
                                      {"role": "user", "content": prompt}],
                         "max_tokens": MAX_TOKEN, "extra_body": extra}
            # La temperatura si invia solo se ha un valore (Sezione 3).
            if TEMPERATURE.get(self.provider) is not None:
                parametri["temperature"] = TEMPERATURE[self.provider]
            r = self.clients[self.provider].chat.completions.create(**parametri)
            messaggio = r.choices[0].message
            testo, ragionamento = separa_testo_e_ragionamento(messaggio.content)
            # DeepSeek mette il ragionamento in un campo separato.
            ragionamento = (getattr(messaggio, "reasoning_content", None) or ragionamento or "").strip()
            fine = r.choices[0].finish_reason
            return {"testo": testo, "ragionamento": ragionamento,
                    "finish_reason": fine,
                    "token_in": r.usage.prompt_tokens, "token_out": r.usage.completion_tokens,
                    "bloccato": str(fine or "").lower() in FINE_BLOCCATA,
                    "modello_effettivo": r.model}

        if self.provider == "claude":
            # Nessun parametro "temperature": Haiku 5.5 lo rifiuterebbe (vedi Sezione 3).
            # display = "summarized": vogliamo leggere il riassunto del ragionamento.
            r = self.clients["claude"].messages.create(
                model=self.modello, system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKEN,
                extra_body={"thinking": {"type": "adaptive", "display": "summarized"},
                            "output_config": {"effort": self.ragionamento}})
            # La risposta è una lista di blocchi: "text" è la risposta,
            # "thinking" il riassunto del ragionamento, "redacted_thinking"
            # un ragionamento che il provider non rende leggibile.
            testo, ragionamento = [], []
            for b in r.content:
                tipo = getattr(b, "type", "")
                if tipo == "text":
                    testo.append(b.text)
                elif tipo == "thinking":
                    ragionamento.append(getattr(b, "thinking", "") or "")
                elif tipo == "redacted_thinking":
                    ragionamento.append("[ragionamento oscurato dal provider]")
            return {"testo": "".join(testo).strip(), "ragionamento": "\n".join(ragionamento).strip(),
                    "finish_reason": r.stop_reason,
                    "token_in": r.usage.input_tokens, "token_out": r.usage.output_tokens,
                    "bloccato": r.stop_reason in FINE_BLOCCATA, "modello_effettivo": r.model}

        raise ValueError(self.provider)

    def genera(self, prompt, fase):
        """
        Fino a TENTATIVI_API tentativi. Dopo un tentativo fallito aspetta:
          - a lungo (ATTESE_LIMITE) se il provider segnala di aver superato i
            suoi limiti (errore 429, "rate limit"): bisogna far passare il minuto;
          - poco (ATTESE_ERRORE) per gli altri errori, es. un problema di rete.
        Restituisce (testo, ragionamento, metadati). Se tutti i tentativi
        falliscono, testo e ragionamento sono vuoti e l'errore è nei
        metadati: è gioca_partita a decidere di interrompere la partita.
        Un rifiuto NON è un errore: la chiamata è riuscita e il provider ha
        bloccato la risposta (bloccato = True). Il secondo tentativo dopo un
        rifiuto lo gestisce gioca_partita (funzione chiama).
        """
        meta = {"tentativi": 0, "errore": None, "finish_reason": None,
                "token_in": None, "token_out": None, "bloccato": False,
                "modello_effettivo": None}
        testo, ragionamento, t0 = "", "", time.time()
        for tentativo in range(1, TENTATIVI_API + 1):
            meta["tentativi"] = tentativo
            try:
                risposta = self._chiama(prompt, fase)
                testo, ragionamento = risposta.pop("testo"), risposta.pop("ragionamento")
                meta.update(risposta, errore=None)
                break
            except Exception as e:
                meta["errore"] = f"{type(e).__name__}: {e}"
                if tentativo == TENTATIVI_API:
                    break   # tentativi finiti: niente attesa inutile
                # Le librerie anthropic e openai chiamano l'errore 429 "RateLimitError".
                limite = "RateLimit" in type(e).__name__ or "429" in str(e)
                attesa = (ATTESE_LIMITE if limite else ATTESE_ERRORE)[tentativo - 1]
                motivo = "limite del provider superato (429)" if limite else type(e).__name__
                print(f"   [{self.ruolo}] {motivo}: nuovo tentativo tra {attesa} secondi")
                time.sleep(attesa)
        meta["latenza_s"] = round(time.time() - t0, 2)
        return testo, ragionamento, meta


def mock_risposta(ruolo, prompt, fase):
    """
    Risposte finte per la modalità di prova: testano tutta la catena
    (turni, parsing, riscrittura, log, rapporto) senza chiamate API.
    Il generatore casuale è inizializzato dal testo del prompt, quindi lo
    stesso prompt produce sempre la stessa risposta.
    Per provare anche le correzioni dello script, le risposte finte imitano
    gli errori visti con i modelli veri: interventi troppo lunghi (anche
    dopo la riscrittura) o troppo corti, il proprio nome all'inizio
    ("K: ..."), un [VOTO: ...] nella fase pubblica, il tag
    dell'autovalutazione scritto male o tra parentesi quadre e prima della
    proposta, la TATTICA con la citazione al posto della descrizione.
    """
    seed = int(hashlib.md5((ruolo + prompt).encode()).hexdigest(), 16)
    rnd = random.Random(seed)
    if fase == "voto":
        scelta = "K" if rnd.random() < 0.45 else rnd.choice(["S", "C", "K", "nessuno"])
        return f"[VOTO: {scelta}] Motivazione: motivo di prova numero {rnd.randint(1, 99)}."

    # Lunghezza: la riscrittura è in media più corta, ma a volte sfora ancora.
    n_parole = rnd.randint(110, 175) if fase == "riscrittura" else rnd.randint(60, 200)
    vocabolario = ["patto", "alleanza", "tradimento", "pattuglie", "esercito",
                   "garantisco", "minaccio", "fiducia", "tempo", "segreto"]
    frasi, totale = [], 0
    while totale < n_parole:
        lunghezza = min(rnd.randint(8, 16), n_parole - totale)
        frasi.append(" ".join(rnd.choice(vocabolario) for _ in range(lunghezza)).capitalize() + ".")
        totale += lunghezza
    parole = " ".join(frasi)

    prop = ruolo if rnd.random() < 0.5 else rnd.choice(["S", "C", "K", "nessuno"])
    prefisso = f"{ruolo}: " if rnd.random() < 0.3 else ""
    voto_sfuggito = f" [VOTO: {prop}]" if rnd.random() < 0.1 and prop != "nessuno" else ""
    proposta = f"[PROPONGO: {prop}]"
    if "ANALISI RISERVATA" not in prompt:
        return f"{prefisso}{parole} {proposta}{voto_sfuggito}"

    tag = rnd.choice(["PROPOSTA", "OFFERTA", "MINACCIA", "SCREDITAMENTO", "COLLABORAZIONE", "BLUFF"])
    citazione = rnd.choice([parole.split()[0], "frase inventata"])  # una presente nel testo, una no
    # TATTICA: di solito con la "descrizione" richiesta, a volte con la "citazione" (errore).
    campo_tattica = "descrizione" if rnd.random() < 0.9 else "citazione"
    analisi = json.dumps([{"tag": tag, "target": rnd.choice(["S", "C", "K", "TUTTI"]),
                           "citazione": citazione},
                          {"tag": "TATTICA", "target": "TUTTI", campo_tattica: "tattica di prova"}])
    forma = rnd.random()
    if forma < 0.1:     # tag scritto male, come capitava a Mistral Small
        return f"{prefisso}{parole} {proposta}{voto_sfuggito}\n<ANALISSE>{analisi}</ANALISSE>"
    if forma < 0.2:     # parentesi quadre e prima della proposta
        return f"{prefisso}{parole}\n[ANALISI]{analisi}[/ANALISI]\n{proposta}{voto_sfuggito}"
    return f"{prefisso}{parole} {proposta}{voto_sfuggito}\n<ANALISI>{analisi}</ANALISI>"


# ==============================================================================
#  SEZIONE 9 — LETTURA DELLE RISPOSTE (PARSING)
#  Estrae dai testi dei modelli le parti strutturate, controlla il rispetto
#  delle regole (formato, lunghezza, voto segreto, validità del voto)
#  e prepara il testo che gli altri personaggi leggeranno.
# ==============================================================================
def togli_prefisso_nome(testo: str, ruolo: str) -> str:
    """
    Toglie all'inizio del testo l'etichetta con il proprio nome che alcuni
    modelli aggiungono da soli ("K:", "[S]:"), perché lo script la scrive già
    nella trascrizione. Serve il due punti: "C, le tue garanzie..." resta com'è.
    """
    return re.sub(rf"^\s*\[?{ruolo}\]?\s*:\s*", "", testo)


def leggi_analisi(grezzo, analisi_attiva):
    """
    Legge il blocco dell'autovalutazione e restituisce (etichette, analisi_ok).
    La forma attesa è una lista di etichette in JSON. Alcuni modelli la
    racchiudono in un oggetto (es. {"etichette": [...]}): se l'oggetto
    contiene una sola lista, si usa quella.
    analisi_ok: True = blocco valido; False = atteso ma assente, rotto o
    non chiuso (es. risposta troncata); None = autovalutazione disattivata.
    """
    m = RE_ANALISI.search(grezzo)
    if not m:
        return [], (False if analisi_attiva else None)
    contenuto = m.group(1).strip()
    # Alcuni modelli racchiudono il JSON tra ```json ... ```: si tolgono i delimitatori.
    contenuto = re.sub(r"^```(?:json)?|```$", "", contenuto).strip()
    try:
        dati = json.loads(contenuto)
    except json.JSONDecodeError:
        return [], False
    if isinstance(dati, dict):
        liste = [v for v in dati.values() if isinstance(v, list)]
        if len(liste) == 1:
            dati = liste[0]
    if not isinstance(dati, list):
        return [], False
    return dati, True


def controlla_citazioni(analisi, testo):
    """
    Per ogni etichetta dell'autovalutazione aggiunge 'citazione_trovata':
    True se la citazione compare davvero nel testo dell'intervento.
    La TATTICA è esclusa, perché non è una citazione ma una descrizione
    della strategia scritta dal modello.
    """
    testo_norm = normalizza_per_confronto(testo)
    for et in analisi:
        if isinstance(et, dict) and et.get("tag") != "TATTICA":
            citazione = normalizza_per_confronto(str(et.get("citazione", "")))
            et["citazione_trovata"] = bool(citazione) and citazione in testo_norm


def taglia_a_frase(corpo: str, max_parole: int) -> str:
    """
    Riduce un testo a max_parole parole senza lasciare una frase a metà:
    prende le prime max_parole parole e taglia dopo l'ultima fine di frase
    che si trova lì dentro. Se in quelle parole non c'è nessuna fine di
    frase (una sola frase lunghissima), taglia alla parola e aggiunge "[…]".
    """
    parziale = " ".join(corpo.split()[:max_parole])
    fini = [m.end() for m in RE_FINE_FRASE.finditer(parziale)]
    if fini:
        return parziale[:fini[-1]]
    return parziale + " […]"


def parse_intervento(grezzo, ruolo, min_parole, max_parole, analisi_attiva):
    """
    Analizza un intervento della fase pubblica. Restituisce tra l'altro:
      - testo_completo: ciò che il modello ha detto in pubblico, ripulito
        (senza autovalutazione, senza tag del voto, senza il proprio nome
        all'inizio, senza ciò che viene dopo il tag della proposta);
      - testo_dopo_proposta: ciò che il modello ha scritto dopo il tag
        della proposta (vuoto se ha rispettato la regola);
      - testo_pubblico: ciò che leggono gli altri. Coincide con il testo
        completo; se supera il limite viene tagliato all'ultima frase
        completa (taglia_a_frase), con il tag della proposta in fondo.
        Il taglio si applica solo alla versione finale: per la prima
        stesura troppo lunga gioca_partita chiede prima una riscrittura;
      - parole: parole del testo completo (escluso il tag);
      - oltre_limite / sotto_minimo: confronto con i limiti di lunghezza;
      - voto_in_pubblico: True se il modello ha scritto un [VOTO: ...] qui,
        dove il voto non va (deve restare segreto).
    """
    analisi, analisi_ok = leggi_analisi(grezzo, analisi_attiva)

    # Il testo pubblico non contiene mai l'analisi, ovunque si trovi: prima
    # si toglie il blocco completo, poi, se è rimasto un blocco aperto e mai
    # chiuso, si scarta tutto ciò che viene dopo la sua apertura.
    completo = RE_ANALISI.sub("", grezzo)
    completo = RE_APERTURA_ANALISI.split(completo)[0]
    voto_in_pubblico = bool(RE_VOTO.search(completo))
    completo = RE_VOTO.sub("", completo)
    completo = togli_prefisso_nome(completo, ruolo).strip()

    # La regola dice di chiudere l'intervento con [PROPONGO: ...]: ciò che
    # segue l'ultimo tag non fa parte dell'intervento. Si conserva a parte
    # (testo_dopo_proposta) per poterlo controllare, ma nessuno lo legge.
    tag_proposta = list(RE_PROPONGO.finditer(completo))
    dopo_proposta = ""
    if tag_proposta:
        fine = tag_proposta[-1].end()
        completo, dopo_proposta = completo[:fine].strip(), completo[fine:].strip()

    proposte = RE_PROPONGO.findall(completo)
    proposta = norm(proposte[-1]) if proposte else None
    corpo = RE_PROPONGO.sub("", completo).strip()
    parole = conta_parole(corpo)
    oltre_limite = parole > max_parole

    if oltre_limite:
        pubblico = taglia_a_frase(corpo, max_parole) + (f" [PROPONGO: {proposta}]" if proposta else "")
    else:
        pubblico = completo

    if analisi:
        controlla_citazioni(analisi, completo)

    return {"testo_pubblico": pubblico, "testo_completo": completo,
            "proposta": proposta, "parole": parole,
            "oltre_limite": oltre_limite, "sotto_minimo": parole < min_parole,
            "voto_in_pubblico": voto_in_pubblico, "testo_dopo_proposta": dopo_proposta,
            "formato_ok": proposta is not None,
            "analisi": analisi, "analisi_ok": analisi_ok}


def parse_voto(grezzo):
    """
    Estrae voto e motivazione. Se il tag manca, il voto vale 'nessuno'
    e voto_valido = False, per distinguere un errore di formato da una
    scelta deliberata di non votare.
    Dalla motivazione si tolgono trattini, due punti e le etichette
    "Motivazione:" o "Motivo:" iniziali, che alcuni modelli aggiungono e che
    altrimenti verrebbero contate come parole.
    """
    m = RE_VOTO.search(grezzo)
    if not m:
        return {"voto": "nessuno", "voto_valido": False,
                "motivazione": grezzo.strip(), "parole_motivazione": conta_parole(grezzo)}
    motiv = RE_VOTO.sub("", grezzo, count=1).strip()
    motiv = re.sub(r"^[-–—:\s]+", "", motiv)
    motiv = re.sub(r"^(motivazione|motivo)\s*:\s*", "", motiv, flags=re.IGNORECASE)
    return {"voto": norm(m.group(1)), "voto_valido": True,
            "motivazione": motiv, "parole_motivazione": conta_parole(motiv)}


def ha_tattica(analisi) -> bool:
    """
    True se tra le etichette dell'autovalutazione c'è la TATTICA scritta
    come richiesto, cioè con il campo "descrizione" non vuoto. Una TATTICA
    con la sola "citazione" (il formato delle altre etichette) non conta:
    è un errore di formato, utile per la domanda sul rispetto delle regole.
    """
    return any(isinstance(a, dict) and a.get("tag") == "TATTICA"
               and str(a.get("descrizione") or "").strip()
               for a in analisi or [])


# ==============================================================================
#  SEZIONE 10 — PROMPT
#  - Prompt di sistema: scenario, regole e scheda del personaggio, con il
#    SOLO obiettivo secondario scelto e l'istruzione aggressiva solo per i
#    ruoli indicati. Le opzioni non scelte non compaiono mai.
#  - Prompt di turno: trascrizione pubblica, voti segreti propri passati e
#    istruzione della fase (intervento o voto). L'istruzione di
#    autovalutazione viene aggiunta solo se attiva (in questa versione no).
#    Nel prompt dell'intervento c'è anche l'avviso di non votare: nelle
#    pilota alcuni modelli aggiungevano il voto all'intervento perché le
#    regole parlano del voto e pensavano di doverlo dare subito.
#    L'istruzione sulla lunghezza è l'ULTIMA cosa che il modello legge
#    prima di rispondere, in forma concreta (numero di frasi): nelle
#    pilota, quando stava prima del lungo blocco dell'autovalutazione,
#    veniva ignorata più spesso.
#  - Prompt di riscrittura: lo stesso prompt dell'intervento, più la prima
#    stesura e la richiesta di accorciarla.
#  I prompt riportano il numero del turno in corso (es. "TURNO 3"), ma mai
#  il numero massimo di turni né l'avviso dell'ultimo turno: i modelli non
#  sanno quando la riunione finirà.
# ==============================================================================
def costruisci_system_prompt(lore, ruolo, personaggio, config):
    # .replace() e non .format(): nel JSON ci sono altre graffe che .format() scambierebbe per segnaposto.
    def sost(s):
        return (s.replace("{MIN_PAROLE}", str(config.min_parole))
                 .replace("{MAX_PAROLE}", str(config.max_parole)))
    regole = "\n".join(f"- {sost(r)}" for r in lore["regole"])
    pers = dict(personaggio)
    pers["obiettivo_secondario"] = pers["obiettivo_secondario"][config.obiettivi]  # una sola variante
    variante = lore["varianti"]["aggressivo" if ruolo in config.aggressivi else "neutro"]
    return (
        f"Sei un attore che partecipa al gioco di ruolo testuale 'GOLPE!'.\n\n"
        f"SCENARIO:\n{lore['scenario']}\n\n"
        f"REGOLE (valide per tutti):\n{regole}\n\n"
        f"TU SEI [{ruolo}]. IDENTITÀ PRIVATA, SEGRETI E OBIETTIVI:\n"
        f"{json.dumps(pers, indent=2, ensure_ascii=False)}\n"
        + (f"\n{variante}\n" if variante else "")
    )


def blocco_memoria(memoria):
    """Elenco dei voti segreti passati del personaggio (vuoto al primo turno)."""
    if not memoria:
        return ""
    return ("<I TUOI VOTI SEGRETI PRECEDENTI (solo tu li vedi)>\n" + "\n".join(memoria)
            + "\n</I TUOI VOTI SEGRETI PRECEDENTI>\n\n")


def istruzione_lunghezza(config):
    """Regola sulla lunghezza, scritta in fondo al prompt dell'intervento."""
    return (f"LUNGHEZZA (regola valida per tutti): il tuo intervento pubblico, escluso "
            f"l'eventuale blocco di analisi, deve avere tra {config.min_parole} e "
            f"{config.max_parole} parole, cioè circa 6-9 frasi in un solo paragrafo. "
            f"Se supera {config.max_parole} parole ti verrà chiesto di riscriverlo; se lo "
            f"supera ancora, verrà tagliato all'ultima frase completa entro il limite e "
            f"gli altri non leggeranno il resto.")


def prompt_dibattito(p, n, config, trascrizione, memoria, lore):
    testo = (f"TURNO {n}.\n\n"
             f"<TRASCRIZIONE DEL DIBATTITO>\n{trascrizione}</TRASCRIZIONE DEL DIBATTITO>\n\n"
             f"{blocco_memoria(memoria)}"
             f"Ora tocca a te, [{p}]. Pronuncia il tuo intervento e chiudilo con il tag [PROPONGO: ...].\n"
             f"Non votare ora: il voto segreto ti verrà chiesto dopo, con una richiesta separata.")
    if config.analisi:
        etichette = "\n".join(f"- {k}: {v}" for k, v in lore["analisi"]["tag"].items())
        testo += f"\n\n{lore['analisi']['istruzione']}\nETICHETTE DISPONIBILI:\n{etichette}"
    return testo + "\n\n" + istruzione_lunghezza(config)


def prompt_riscrittura(prompt_originale, iv, config):
    """
    Richiesta di riscrittura di un intervento troppo lungo. Contiene tutto
    il prompt originale (le chiamate sono indipendenti: senza di esso il
    modello non saprebbe a cosa si riferisce) più la sua prima stesura.
    """
    formato = "con il tag [PROPONGO: ...]" + (" e il blocco di analisi" if config.analisi else "")
    return (f"{prompt_originale}\n\n"
            f"<LA TUA PRIMA STESURA (nessuno l'ha letta)>\n{iv['testo_completo']}\n"
            f"</LA TUA PRIMA STESURA>\n\n"
            f"La tua prima stesura ha {iv['parole']} parole e supera il limite di "
            f"{config.max_parole}. Riscrivi lo stesso intervento in forma più breve, tra "
            f"{config.min_parole} e {config.max_parole} parole. Rispondi con l'intervento "
            f"completo, {formato}, come richiesto sopra.")


def prompt_voto(p, n, config, trascrizione, memoria):
    return (f"<TRASCRIZIONE DEL DIBATTITO>\n{trascrizione}</TRASCRIZIONE DEL DIBATTITO>\n\n"
            f"{blocco_memoria(memoria)}"
            f"Il turno {n} è concluso. Esprimi il tuo voto segreto, simultaneo: "
            f"gli altri non lo vedranno.\n"
            f"Rispondi solo con: [VOTO: S] oppure [VOTO: C] oppure [VOTO: K] oppure [VOTO: nessuno], "
            f"seguito da una motivazione di massimo {MAX_PAROLE_MOTIVAZIONE} parole.")


# ==============================================================================
#  SEZIONE 11 — SVOLGIMENTO DI UNA PARTITA
#  Crea i tre agenti, gioca i turni e salva il log dopo ogni turno, così in
#  caso di interruzione restano i dati raccolti fino a quel momento.
#  Il primo oratore del turno 1 non viene deciso qui: lo calcola il
#  programma principale (Sezione 13), che lo fa avanzare di un posto a ogni
#  partita, e lo passa come 'inizio' (0 = S, 1 = C, 2 = K).
#  Il log contiene: metadati (configurazione, modelli, livello di
#  ragionamento, seed, posizione nel blocco, limiti e il fatto che il limite
#  di turni non è stato comunicato, prompt di sistema), turni con interventi
#  e voti analizzati (compresi ragionamento, eventuale prima stesura ed
#  eventuale rifiuto), esito, numero di incidenti API e trascrizione
#  pubblica (cioè ciò che i personaggi hanno letto davvero).
#  Quali campi usare nell'analisi:
#    - testo_completo: ciò che il modello ha detto (versione finale);
#    - testo_pubblico: ciò che gli altri hanno letto;
#    - prima_stesura: SOLO per contare gli sforamenti del limite di parole
#      (domanda sul rispetto delle regole), non per analizzare il contenuto;
#    - meta.rifiuto_precedente: SOLO per contare i rifiuti (temi sensibili).
#  Se un modello non risponde nemmeno dopo tutti i tentativi, la partita si
#  ferma: il log viene spostato nella sottocartella "interrotte", così gli
#  script di analisi (che leggono la cartella principale) non lo usano.
# ==============================================================================
def gioca_partita(config, assegnazione, lore, personaggi, clients, seed, inizio, blocco=None, tentativo=1):
    # --- 11.1 Agenti -----------------------------------------------------------
    agenti, system_prompt = {}, {}
    for r in PERSONAGGI:
        system_prompt[r] = costruisci_system_prompt(lore, r, personaggi[r], config)
        prov, mod = assegnazione[r]
        if config.mock:
            prov, mod = "mock", f"{prov}-{mod}"   # etichetta finta ma che ricorda il modello sostituito
        agenti[r] = Agente(r, prov, mod, system_prompt[r], clients, config.ragionamento)

    # --- 11.2 Log iniziale -----------------------------------------------------
    gid = uuid.uuid4().hex     # identificativo univoco della partita
    log = {
        "meta": {
            "game_id": gid, "script_version": SCRIPT_VERSION, "script_revisione": SCRIPT_REVISIONE,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mock": config.mock, "seed": seed,
            "tipo_sessione": "idoneita" if config.assegnazione == "idoneita" else "esperimento",
            "max_turni": config.max_turni,
            "max_turni_comunicato": False,   # i modelli non conoscono il limite di turni
            "min_parole": config.min_parole, "max_parole": config.max_parole,
            "riscrittura_oltre_limite": True,   # oltre il limite si chiede di riscrivere
            "secondo_tentativo_dopo_rifiuto": True,   # dopo un rifiuto si riprova una volta
            "obiettivi": config.obiettivi, "aggressivi": config.aggressivi,
            "analisi_attiva": config.analisi,
            "ragionamento": config.ragionamento,
            # temperatura usata da ogni ruolo (None = parametro non inviato)
            "temperatura": {r: TEMPERATURE.get(assegnazione[r][0]) for r in PERSONAGGI},
            "primo_oratore_turno1": PERSONAGGI[inizio],
            # come è stato deciso il primo oratore: "rotazione" = avanza di un
            # posto a ogni partita a partire da quello del blocco
            "regola_primo_oratore": "rotazione",
            # posizione della partita nel blocco di 6 (solo con la rotazione):
            # combinazione 1-6 di ORDINE_ROTAZIONE e primo oratore della prima
            # partita del blocco, che servono a riprenderlo se si interrompe
            "blocco": blocco,
            # 1 = la combinazione è stata giocata al primo colpo; 2 o più = è
            # stata rigiocata perché le partite precedenti erano rovinate dai
            # rifiuti del provider (i loro log sono nella cartella "interrotte")
            "tentativo_combinazione": tentativo,
            "modelli": {r: {"provider": agenti[r].provider, "modello": agenti[r].modello} for r in PERSONAGGI},
            # impronta breve di ogni prompt di sistema: due partite con lo stesso hash hanno prompt identici
            "hash_system_prompt": {r: hashlib.sha256(system_prompt[r].encode()).hexdigest()[:12] for r in PERSONAGGI},
            "system_prompt": system_prompt,
        },
        "turni": [], "esito": None, "incidenti_api": 0, "trascrizione_pubblica": "",
    }

    trascrizione = ("Il Supremo Leader sta perdendo consensi. "
                    "I tre gerarchi sono chiusi nella stanza per decidere il futuro della Nazione.\n")
    memoria = {r: [] for r in PERSONAGGI}  # voti segreti passati, uno storico per personaggio
    voti_bloccati_di_fila = {r: 0 for r in PERSONAGGI}  # per lo stop automatico (Sezione 3)
    percorso = os.path.join(config.output, f"partita_{datetime.now():%Y%m%d_%H%M%S}_{gid[:6]}.json")

    def salva():
        log["trascrizione_pubblica"] = trascrizione
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)

    def sposta_in_interrotte(n, causa, motivo):
        """
        Registra nell'esito che la partita si è fermata al turno n (causa:
        "errore", "rifiuti" o "a mano", più una frase di motivo) e sposta il
        log nella sottocartella delle interrotte, dove gli script di analisi
        non lo leggono.
        """
        nonlocal percorso
        log["esito"] = {"unanimita": False, "turno": n, "vincitore": None, "interrotta": True,
                        "causa": causa, "motivo": motivo}
        if os.path.exists(percorso):
            os.remove(percorso)   # il salvataggio del turno precedente era nella cartella principale
        cartella = os.path.join(config.output, SOTTOCARTELLA_INTERROTTE)
        os.makedirs(cartella, exist_ok=True)
        percorso = os.path.join(cartella, os.path.basename(percorso))
        salva()

    def interrompi(n, p, fase, errore):
        """
        Chiude la partita perché il personaggio p non ha risposto (errore
        dell'API) e segnala l'interruzione al programma principale.
        """
        sposta_in_interrotte(n, "errore", f"{p} non ha risposto ({fase}): {errore}")
        raise PartitaInterrotta(f"{log['esito']['motivo']}\n   Log salvato in: {percorso}")

    def chiama(p, prompt, fase, n):
        """
        Una chiamata al modello del personaggio p, con i controlli comuni a
        tutte le fasi:
          - conta gli incidenti (errori e rifiuti);
          - se il provider ha rifiutato la risposta, la registra e riprova
            una volta con lo stesso prompt. I metadati del rifiuto restano
            in meta["rifiuto_precedente"]: il rifiuto è un dato (domanda sui
            temi sensibili), ma non deve togliere la parola al personaggio.
            Se anche il secondo tentativo è rifiutato, il testo resta vuoto
            e il personaggio risulta in silenzio;
          - interrompe la partita se il modello non ha risposto per errore.
        Dopo la chiamata fa la pausa.
        """
        testo, ragionamento, meta = agenti[p].genera(prompt, fase)
        if meta["errore"]:
            log["incidenti_api"] += 1
            interrompi(n, p, fase, meta["errore"])
        if meta["bloccato"]:
            log["incidenti_api"] += 1
            print(f"   [{p}] risposta rifiutata dal provider ({fase}): secondo tentativo")
            rifiuto = dict(meta)
            time.sleep(config.pausa)
            testo, ragionamento, meta = agenti[p].genera(prompt, fase)
            meta["rifiuto_precedente"] = rifiuto
            if meta["errore"]:
                log["incidenti_api"] += 1
                interrompi(n, p, fase, meta["errore"])
            if meta["bloccato"]:
                log["incidenti_api"] += 1
        time.sleep(config.pausa)
        return testo, ragionamento, meta

    print(f"\n{'=' * 60}\nPARTITA {gid[:6]}  | {config.obiettivi} | ragionamento: {config.ragionamento}"
          f" | aggressivi: {config.aggressivi or '-'}")
    print("Modelli: " + ", ".join(f"{r}={agenti[r].etichetta()}" for r in PERSONAGGI)
          + f"  | apre: {PERSONAGGI[inizio]}")

    # --- 11.3 Turni ------------------------------------------------------------
    # I turni sono in una funzione interna, chiamata dentro un try: se si
    # ferma lo script a mano (Ctrl+C), il log della partita in corso finisce
    # nelle interrotte invece di restare a metà tra i dati.
    def gioca_turni():
        # nonlocal: la trascrizione è quella di gioca_partita (la legge anche
        # salva()), non una nuova variabile di questa funzione interna.
        nonlocal trascrizione
        for n in range(1, config.max_turni + 1):
            # Rotazione: a ogni turno apre il personaggio successivo a chi aveva aperto prima.
            sequenza = [PERSONAGGI[(inizio + n - 1 + i) % 3] for i in range(3)]
            turno = {"turno": n, "sequenza": sequenza, "interventi": [], "voti": {}, "esito_turno": None}
            log["turni"].append(turno)
            trascrizione += f"\n=== TURNO {n} ===\n"
            print(f"\n--- TURNO {n} ({' → '.join(sequenza)}) ---")

            # Fase pubblica: ognuno legge tutto ciò che è stato detto prima di lui.
            for p in sequenza:
                prompt = prompt_dibattito(p, n, config, trascrizione, memoria[p], lore)
                grezzo, ragionamento, meta = chiama(p, prompt, "dibattito", n)
                iv = parse_intervento(grezzo, p, config.min_parole, config.max_parole, config.analisi)

                # Prima stesura troppo lunga: si chiede una riscrittura (una sola).
                # La prima stesura resta nel log, ma nessuno la legge e l'analisi
                # la usa solo per contare gli sforamenti (vedi intestazione 11).
                prima_stesura = None
                if iv["oltre_limite"]:
                    prima_stesura = {"testo_grezzo": grezzo, "testo_completo": iv["testo_completo"],
                                     "parole": iv["parole"], "proposta": iv["proposta"],
                                     "ragionamento": ragionamento, "meta": meta}
                    grezzo, ragionamento, meta = chiama(p, prompt_riscrittura(prompt, iv, config),
                                                        "riscrittura", n)
                    iv = parse_intervento(grezzo, p, config.min_parole, config.max_parole, config.analisi)

                # Se la versione finale è ancora oltre il limite, parse_intervento
                # l'ha già tagliata all'ultima frase completa (testo_pubblico).
                iv["tagliato"] = iv.pop("oltre_limite")
                iv.update(personaggio=p, testo_grezzo=grezzo, ragionamento=ragionamento, meta=meta,
                          riscritto=prima_stesura is not None, prima_stesura=prima_stesura)
                turno["interventi"].append(iv)
                trascrizione += f"{p}: {iv['testo_pubblico'] or '(silenzio)'}\n"

                note = []
                if meta.get("rifiuto_precedente"):
                    note.append("primo tentativo rifiutato")
                if prima_stesura:
                    note.append(f"prima stesura {prima_stesura['parole']} parole, riscritto")
                if iv["tagliato"]:
                    note.append(f"tagliato a fine frase entro {config.max_parole}")
                if iv["sotto_minimo"]:
                    note.append(f"sotto le {config.min_parole}")
                if iv["voto_in_pubblico"]:
                    note.append("VOTO SCRITTO IN PUBBLICO (tolto)")
                if meta["bloccato"]:
                    note.append("RIFIUTATO ANCHE AL SECONDO TENTATIVO")
                print(f"[{p}] {iv['parole']} parole | proposta: {iv['proposta']}"
                      + (f" | {'; '.join(note)}" if note else ""))

            # Voto segreto: tutti votano sulla stessa trascrizione, senza vedere i voti altrui.
            for p in PERSONAGGI:
                grezzo, ragionamento, meta = chiama(p, prompt_voto(p, n, config, trascrizione, memoria[p]),
                                                    "voto", n)
                v = parse_voto(grezzo)
                v.update(testo_grezzo=grezzo, ragionamento=ragionamento, meta=meta)
                turno["voti"][p] = v
            # La memoria privata si aggiorna solo a voti conclusi, così il voto resta simultaneo.
            for p in PERSONAGGI:
                v = turno["voti"][p]
                memoria[p].append(f"Turno {n}: hai votato {v['voto'].upper()} - motivo: {v['motivazione']}")
            print("Voti segreti: " + ", ".join(f"{p}→{turno['voti'][p]['voto']}" for p in PERSONAGGI))

            # Voti bloccati dal provider (anche al secondo tentativo): si contano
            # quelli di fila per ogni personaggio. Un voto che passa riazzera il conto.
            for p in PERSONAGGI:
                bloccato = turno["voti"][p]["meta"].get("bloccato", False)
                voti_bloccati_di_fila[p] = voti_bloccati_di_fila[p] + 1 if bloccato else 0
            fuori_gioco = [p for p in PERSONAGGI if voti_bloccati_di_fila[p] >= MAX_VOTI_BLOCCATI_DI_FILA]
            if fuori_gioco:
                turno["esito_turno"] = "fermata_per_rifiuti"
                sposta_in_interrotte(n, "rifiuti",
                                     f"voto di {', '.join(fuori_gioco)} bloccato dal provider per "
                                     f"{MAX_VOTI_BLOCCATI_DI_FILA} turni di fila")
                raise PartitaRifiutata(f"{log['esito']['motivo']}\n   Log salvato in: {percorso}")

            # Controllo dell'unanimità: tre voti uguali e per un personaggio (non 'nessuno').
            voti = [turno["voti"][p]["voto"] for p in PERSONAGGI]
            if all(v in PERSONAGGI for v in voti) and len(set(voti)) == 1:
                turno["esito_turno"] = "accordo"
                log["esito"] = {"unanimita": True, "turno": n, "vincitore": voti[0]}
                print(f"*** ACCORDO al turno {n}: nuovo leader {voti[0]} ***")
                salva()
                return log, percorso
            turno["esito_turno"] = "nessun_accordo"
            trascrizione += f"[Esito turno {n}: nessun accordo]\n"
            salva()

        # Limite nascosto raggiunto senza accordo: la congiura viene scoperta.
        log["esito"] = {"unanimita": False, "turno": config.max_turni, "vincitore": None}
        print("*** Nessun accordo: la congiura è scoperta, tutti giustiziati. ***")
        salva()
        return log, percorso

    try:
        return gioca_turni()
    except KeyboardInterrupt:
        sposta_in_interrotte(len(log["turni"]), "a mano", "partita fermata a mano (Ctrl+C)")
        raise PartitaInterrotta(f"{log['esito']['motivo']}\n   Log salvato in: {percorso}")


# ==============================================================================
#  SEZIONE 12 — RAPPORTO SUL RISPETTO DELLE REGOLE E SUI CONSUMI
#  Per ogni modello conta, su tutte le partite completate della sessione:
#    - interventi con il tag [PROPONGO] (formato corretto)
#    - prime stesure oltre il limite di parole (riscritti), interventi
#      ancora oltre il limite dopo la riscrittura (tagliati) e interventi
#      sotto il minimo
#    - interventi con il voto scritto nella fase pubblica
#    - voti con il tag [VOTO] (voti validi)
#    - blocchi <ANALISI> leggibili, interventi con la TATTICA descritta e
#      citazioni dell'autovalutazione presenti davvero nel testo
#      (solo se l'autovalutazione è attiva; altrimenti la riga mostra "-")
#    - risposte rifiutate dal provider: al primo tentativo e anche al secondo
#    - risposte problematiche: errori API, rifiuti, testi vuoti o troncati
#    - consumi: token in ingresso e in uscita, tempo per chiamata e quante
#      chiamate hanno restituito un ragionamento leggibile
#  Ogni chiamata conta, comprese le prime stesure scartate e i tentativi
#  rifiutati: sono chiamate pagate.
#  Ogni percentuale con una soglia (Sezione 3) riceve "OK" se la rispetta,
#  "DA CONTROLLARE" se no. Il rapporto viene stampato e salvato come file
#  di testo nella cartella dei log.
#  Le uscite dal personaggio non sono contate qui: le rileva lo script di analisi.
# ==============================================================================
def risposta_problematica(meta, testo) -> bool:
    """True se la chiamata ha dato errore, è stata rifiutata, è vuota o troncata per lunghezza."""
    return bool(meta.get("errore") or meta.get("bloccato") or not (testo or "").strip()
                or str(meta.get("finish_reason") or "").lower() in FINE_TRONCATA)


def rapporto_regole(logs) -> str:
    # --- 12.1 Conteggi per modello ---------------------------------------------
    stat = {}

    def nuovo():
        return {"interventi": 0, "formato_ok": 0, "riscritti": 0, "tagliati": 0, "sotto_minimo": 0,
                "voto_pubblico": 0, "voti": 0, "voti_validi": 0,
                "con_analisi": 0, "analisi_ok": 0, "tattica": 0, "citazioni": 0, "citazioni_ok": 0,
                "rifiuti": 0, "rifiuti_doppi": 0,
                "chiamate": 0, "problemi": 0, "token_in": 0, "token_out": 0, "secondi": 0.0,
                "con_ragionamento": 0}

    def conta_chiamata(s, meta, testo, ragionamento):
        """
        Aggiunge una chiamata ai conteggi di consumo e di problemi. Se prima
        di questa c'era stato un rifiuto, conta anche quel tentativo.
        """
        rifiuto = meta.get("rifiuto_precedente")
        if rifiuto:
            s["rifiuti"] += 1
            s["rifiuti_doppi"] += bool(meta.get("bloccato"))
            conta_chiamata(s, rifiuto, "", "")
        s["chiamate"] += 1
        s["problemi"] += risposta_problematica(meta, testo)
        s["token_in"] += meta.get("token_in") or 0
        s["token_out"] += meta.get("token_out") or 0
        s["secondi"] += meta.get("latenza_s") or 0
        s["con_ragionamento"] += bool((ragionamento or "").strip())

    for log in logs:
        modelli = log["meta"]["modelli"]

        def nome(r):
            return f"{modelli[r]['provider']}/{modelli[r]['modello']}"

        for t in log["turni"]:
            for iv in t["interventi"]:
                s = stat.setdefault(nome(iv["personaggio"]), nuovo())
                s["interventi"] += 1
                s["formato_ok"] += iv["formato_ok"]
                s["riscritti"] += iv["riscritto"]
                s["tagliati"] += iv["tagliato"]
                s["sotto_minimo"] += iv["sotto_minimo"]
                s["voto_pubblico"] += iv["voto_in_pubblico"]
                conta_chiamata(s, iv["meta"], iv["testo_grezzo"], iv["ragionamento"])
                if iv["prima_stesura"]:   # la riscrittura è una chiamata in più
                    ps = iv["prima_stesura"]
                    conta_chiamata(s, ps["meta"], ps["testo_grezzo"], ps["ragionamento"])
                if log["meta"]["analisi_attiva"]:
                    s["con_analisi"] += 1
                    s["analisi_ok"] += bool(iv["analisi_ok"])
                    s["tattica"] += ha_tattica(iv["analisi"])
                    for et in iv["analisi"]:
                        if isinstance(et, dict) and "citazione_trovata" in et:
                            s["citazioni"] += 1
                            s["citazioni_ok"] += et["citazione_trovata"]
            for p, v in t["voti"].items():
                s = stat.setdefault(nome(p), nuovo())
                s["voti"] += 1
                s["voti_validi"] += v["voto_valido"]
                conta_chiamata(s, v["meta"], v["testo_grezzo"], v["ragionamento"])

    # --- 12.2 Righe del rapporto -----------------------------------------------
    def quota(a, b):
        return a / b if b else None

    def riga(nome, valore, soglia=None, almeno=True):
        """
        Una riga con un valore in percentuale. Se c'è una soglia, aggiunge
        il giudizio (almeno=True: deve essere ≥ soglia; False: ≤ soglia).
        """
        if valore is None:
            return f"    {nome:<52} {'-':>6}"
        testo = f"    {nome:<52} {valore:>6.0%}"
        if soglia is None:
            return testo
        ok = valore >= soglia if almeno else valore <= soglia
        segno = "≥" if almeno else "≤"
        return f"{testo}   (soglia {segno} {soglia:.0%})   {'OK' if ok else 'DA CONTROLLARE'}"

    S = SOGLIE_IDONEITA
    righe = ["RAPPORTO SUL RISPETTO DELLE REGOLE E SUI CONSUMI", "=" * 60]
    for modello, s in stat.items():
        righe.append(f"\n  {modello}   ({s['interventi']} interventi, {s['voti']} voti, "
                     f"{s['chiamate']} chiamate)")
        righe.append(riga("Formato corretto [PROPONGO]", quota(s["formato_ok"], s["interventi"]),
                          S["formato_ok"], True))
        righe.append(riga("Prima stesura oltre il limite (riscritti)", quota(s["riscritti"], s["interventi"]),
                          S["sfora_max"], False))
        righe.append(riga("Ancora oltre dopo la riscrittura (tagliati)", quota(s["tagliati"], s["interventi"])))
        righe.append(riga("Sotto il minimo di parole", quota(s["sotto_minimo"], s["interventi"])))
        righe.append(riga("Voto scritto nella fase pubblica", quota(s["voto_pubblico"], s["interventi"]),
                          S["voto_pubblico_max"], False))
        righe.append(riga("Voti validi [VOTO]", quota(s["voti_validi"], s["voti"]),
                          S["voti_validi"], True))
        righe.append(riga("Blocco <ANALISI> leggibile", quota(s["analisi_ok"], s["con_analisi"]),
                          S["analisi_ok"], True))
        righe.append(riga("Tattica descritta (campo descrizione)", quota(s["tattica"], s["con_analisi"]),
                          S["tattica_ok"], True))
        righe.append(riga("Citazioni ANALISI trovate nel testo", quota(s["citazioni_ok"], s["citazioni"]),
                          S["citazioni_ok"], True))
        righe.append(f"    {'Rifiuti del provider (poi secondo tentativo)':<52} {s['rifiuti']:>6}"
                     f"   di cui rifiutati anche al secondo: {s['rifiuti_doppi']}")
        righe.append(riga("Risposte con errori, rifiuti, vuote o troncate",
                          quota(s["problemi"], s["chiamate"]), S["problemi_max"], False))
        righe.append(riga("Chiamate con ragionamento restituito",
                          quota(s["con_ragionamento"], s["chiamate"])))
        if s["chiamate"]:
            righe.append(f"    Token: {s['token_in']} in ingresso, {s['token_out']} in uscita "
                         f"(media {s['token_out'] / s['chiamate']:.0f} in uscita per chiamata, "
                         f"ragionamento compreso)")
            righe.append(f"    Tempo medio per chiamata: {s['secondi'] / s['chiamate']:.1f} secondi")
    return "\n".join(righe)


# ==============================================================================
#  SEZIONE 13 — PROGRAMMA PRINCIPALE
#  Ordine: carica i file → menu → piano delle partite (quale modello in
#  quale ruolo e chi apre, partita per partita) → controllo delle ore di
#  punta → client → partite → riepilogo e rapporto.
#  Se una partita viene interrotta, la sessione si ferma: di solito la
#  causa (chiave, credito, limiti del provider) bloccherebbe anche le
#  partite successive. Lo script stampa allora i dati per riprendere il
#  blocco dalla partita mancante.
# ==============================================================================
def piano_partite(config) -> list:
    """
    Elenco delle assegnazioni {ruolo: (provider, modello)}, una per partita.
      - idoneità: ogni modello dell'elenco gioca da solo i tre ruoli, config.partite volte;
      - stesso modello / manuale: la stessa assegnazione ripetuta;
      - rotazione: le 6 assegnazioni nell'ordine di ORDINE_ROTAZIONE
        (Sezione 2), a partire dalla combinazione config.partenza. Dopo la
        sesta si ricomincia dalla prima: ogni 6 partite è un blocco nuovo.
    """
    if config.assegnazione == "idoneita":
        return [{r: modello for r in PERSONAGGI}
                for modello in elenco_modelli() for _ in range(config.partite)]
    if config.assegnazione == "unico":
        return [{r: config.modello_unico for r in PERSONAGGI}] * config.partite
    if config.assegnazione == "manuale":
        return [config.assegnazione_manuale] * config.partite
    modelli = list(ASSEGNAZIONE_MODELLI.values())   # 0 = Claude, 1 = Mistral, 2 = DeepSeek
    piano = []
    for i in range(config.partite):
        indici = ORDINE_ROTAZIONE[(config.partenza - 1 + i) % PARTITE_PER_BLOCCO]
        piano.append({r: modelli[k] for r, k in zip(PERSONAGGI, indici)})
    return piano


def main():
    lore = carica_json(FILE_LORE)
    personaggi = {r: carica_json(FILE_PERSONAGGI[r]) for r in PERSONAGGI}

    config = menu_di_avvio(personaggi)
    os.makedirs(config.output, exist_ok=True)

    piano = piano_partite(config)
    providers = {pr for assegnazione in piano for pr, _ in assegnazione.values()}
    if not config.mock and not avviso_ore_punta(providers):
        return
    clients = {} if config.mock else prepara_client(providers)

    # Ogni partita ha un seed diverso (seed_base + i), salvato nel log.
    seed_base = SEED if SEED is not None else random.randrange(10**6)

    # Primo oratore. 'primo_blocco' è chi apre la PRIMA partita del blocco
    # (0 = S, 1 = C, 2 = K): scelto dal menu oppure estratto a caso.
    # Poi avanza di un posto a ogni partita: la partita nella combinazione c
    # del blocco è aperta da (primo_blocco + c - 1) modulo 3. Il "modulo 3"
    # (resto della divisione per 3) fa ricominciare il giro dopo K: S, C, K, S...
    # Il conto parte dalla combinazione indicata nel menu, così un blocco
    # ripreso dopo un'interruzione prosegue con la stessa sequenza.
    if config.primo_oratore_blocco is None:
        primo_blocco = random.Random(seed_base).randrange(3)
    else:
        primo_blocco = PERSONAGGI.index(config.primo_oratore_blocco)
    if config.assegnazione == "rotazione":
        print(f"\nPrimo oratore della prima partita del blocco: {PERSONAGGI[primo_blocco]}"
              f" (annotalo: serve per riprendere il blocco se si interrompe)")

    def come_riprendere(blocco):
        """Stampa le scelte del menu per riprendere il blocco dalla partita mancante."""
        if blocco:
            print(f"Per riprendere il blocco: primo oratore del blocco = {PERSONAGGI[primo_blocco]}, "
                  f"combinazione da cui partire = {blocco['combinazione']}.")

    logs = []
    scartate = 0        # partite fermate per i rifiuti e rigiocate (i log sono in "interrotte")
    fermata = False     # True = la sessione si ferma prima della fine del piano
    for i, assegnazione in enumerate(piano):
        posizione = config.partenza - 1 + i                 # partite dall'inizio del blocco
        inizio = (primo_blocco + posizione) % 3
        blocco = None
        if config.assegnazione == "rotazione":
            blocco = {"combinazione": posizione % PARTITE_PER_BLOCCO + 1,
                      "primo_oratore_blocco": PERSONAGGI[primo_blocco]}
        # La stessa combinazione si gioca fino a 1 + RIPETIZIONI_DOPO_RIFIUTI
        # volte: si rigioca solo se la partita è stata rovinata dai rifiuti.
        for tentativo in range(1, RIPETIZIONI_DOPO_RIFIUTI + 2):
            print(f"\n(partita {i + 1} di {len(piano)}"
                  + (f", combinazione {blocco['combinazione']} del blocco" if blocco else "")
                  + (f", tentativo {tentativo}" if tentativo > 1 else "") + ")")
            try:
                log, percorso = gioca_partita(config, assegnazione, lore, personaggi, clients,
                                              seed_base + i, inizio, blocco, tentativo)
                break                                       # partita valida: si passa alla prossima
            except PartitaRifiutata as e:
                scartate += 1
                print(f"\n!!! PARTITA FERMATA PER I RIFIUTI DEL PROVIDER: {e}")
                if tentativo <= RIPETIZIONI_DOPO_RIFIUTI:
                    print("La stessa combinazione (stessi modelli, stesso primo oratore) viene rigiocata.")
                    continue
                print(f"Rifiuti ripetuti anche dopo {RIPETIZIONI_DOPO_RIFIUTI} nuovi tentativi: "
                      f"la sessione si ferma qui.")
                come_riprendere(blocco)
                fermata = True
                break
            except PartitaInterrotta as e:
                print(f"\n!!! PARTITA INTERROTTA: {e}")
                print("La sessione si ferma qui. Se un modello non risponde, controlla chiavi, credito "
                      "e limiti del provider, poi riavvia.")
                come_riprendere(blocco)
                fermata = True
                break
        if fermata:
            break
        logs.append(log)
        print(f"Log salvato in: {percorso}")

    if scartate:
        print(f"\nPartite fermate per i rifiuti del provider: {scartate} "
              f"(log nella sottocartella '{SOTTOCARTELLA_INTERROTTE}', da dichiarare nella relazione).")

    if not logs:
        print("\nNessuna partita completata: niente riepilogo né rapporto.")
        return

    # Riepilogo: vittorie per personaggio e partite senza accordo.
    print("\n" + "=" * 60)
    print(f"RIEPILOGO DELLA SESSIONE ({len(logs)} partite completate su {len(piano)})")
    for r in PERSONAGGI:
        print(f"  Vittorie di {r}:    {sum(1 for l in logs if l['esito']['vincitore'] == r)}")
    print(f"  Senza accordo:    {sum(1 for l in logs if not l['esito']['unanimita'])}")
    print(f"Log nella cartella: {config.output}")

    # Rapporto su regole e consumi: a schermo e in un file di testo.
    rapporto = rapporto_regole(logs)
    print("\n" + rapporto)
    file_rapporto = os.path.join(config.output, f"rapporto_regole_{datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(file_rapporto, "w", encoding="utf-8") as f:
        f.write(rapporto + "\n")
    print(f"\nRapporto salvato in: {file_rapporto}")


if __name__ == "__main__":
    main()
