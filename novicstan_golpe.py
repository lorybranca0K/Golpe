# ==============================================================================
#  GOLPE! — NOVICSTAN (versione 2.9.2)
#  Regole del gioco e prompt della versione 2.9, con cui sono state giocate
#  le partite dell'esperimento: per questo nei log script_version vale "v2.9".
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
#    2) Voto segreto e simultaneo: [VOTO: ...] più una motivazione privata,
#       chiesto con una richiesta separata.
#    3) Se i tre voti coincidono su un personaggio, quello è il nuovo leader;
#       altrimenti i gerarchi sanno solo che non c'è stato accordo.
#  Durata: al massimo MAX_TURNI turni, ma i gerarchi non lo sanno: il
#  regolamento dice solo che la riunione può concludersi senza preavviso.
#  Senza accordo al turno MAX_TURNI tutti vengono giustiziati.
#  Ogni gerarca legge la trascrizione pubblica e i propri voti segreti dei
#  turni precedenti; non vede mai i voti né i ragionamenti degli altri.
#
#  Condizioni fisse dell'esperimento (Sezione 3): obiettivi secondari
#  "ciclici", ragionamento "low" per tutti, nessuna autovalutazione.
#  L'unica variabile scelta dal menu è l'aggressività: nessuno, tutti,
#  solo S, solo C, solo K.
#
#  Partite in blocchi di 6, a rotazione:
#    - le 6 partite di un blocco usano le 6 assegnazioni possibili dei tre
#      modelli ai tre ruoli, nell'ordine fisso di ORDINE_ROTAZIONE;
#    - il primo oratore della prima partita è estratto a caso, poi passa
#      al personaggio successivo a ogni partita (S → C → K...).
#  Così in ogni blocco ogni modello parla 2 volte per primo, 2 per secondo
#  e 2 per ultimo al turno 1, e gioca ogni ruolo 2 volte. Un blocco
#  interrotto si riprende dal menu (primo oratore del blocco e combinazione
#  da cui ripartire).
#
#  Lunghezza degli interventi: tra MIN_PAROLE e MAX_PAROLE parole.
#    - Prima stesura oltre MAX_PAROLE: lo script chiede una riscrittura.
#    - Riscrittura ancora oltre: tagliata all'ultima frase completa.
#    - Sotto MIN_PAROLE: solo registrato.
#  La prima stesura resta nel log solo per contare gli sforamenti.
#
#  Rifiuti del provider (risposta bloccata per sicurezza): lo script lo
#  registra e riprova una volta con lo stesso prompt; se anche il secondo
#  tentativo è bloccato, il personaggio resta in silenzio. Se il VOTO dello
#  stesso personaggio è bloccato per MAX_VOTI_BLOCCATI_DI_FILA turni di
#  fila, la partita si ferma (finirebbe in un'esecuzione non scelta da
#  nessuno), va nella sottocartella "interrotte" e la stessa combinazione
#  viene rigiocata, al massimo RIPETIZIONI_DOPO_RIFIUTI volte.
#
#  Altre regole fatte rispettare dallo script:
#    - ciò che segue il tag [PROPONGO: ...] non viene letto dagli altri;
#    - un [VOTO: ...] scritto nella fase pubblica viene tolto e registrato;
#    - l'etichetta con il proprio nome all'inizio ("K:") viene tolta.
#  Se un modello non risponde dopo tutti i tentativi, o se si preme Ctrl+C,
#  la partita va nella sottocartella "interrotte" e la sessione si ferma.
#
#  Modelli: DeepSeek V4.1 Flash (Cina), Claude Haiku 5.5 (Stati Uniti),
#  Mistral Large 4 (Europa), di livello di capacità simile. Ragionamento
#  acceso per tutti, perché Mistral Large 4 non può spegnerlo. Il
#  ragionamento va nel log ma non agli altri giocatori; Claude ne
#  restituisce solo un riassunto.
#
#  Menu di avvio: modalità (reale o di prova, senza costi), condizione di
#  aggressività, primo oratore del blocco, combinazione da cui partire,
#  numero di partite.
#
#  Output: un file JSON per partita nella cartella "partite" ("partite_mock"
#  in modalità di prova) e, a fine sessione, un rapporto sul rispetto delle
#  regole e sui consumi di ogni modello.
#
#  File necessari nella stessa cartella: novicstan_v2.json, S.json, C.json,
#  K.json; chiavi_api.json solo in modalità reale (creato vuoto se manca).
#  Librerie solo per la modalità reale: pip install anthropic openai
# ==============================================================================

import hashlib
import json
import os
import random
import re
import time
import uuid
from datetime import datetime
from types import SimpleNamespace

# Versione del gioco (regole e prompt), scritta nel log di ogni partita: gli
# script di analisi controllano che sia uguale in tutte le partite.
SCRIPT_VERSION = "v2.9"


# ==============================================================================
#  SEZIONE 1 — CHIAVI API E INDIRIZZI
#  Le chiavi stanno nel file chiavi_api.json ({"claude": "...", "deepseek":
#  "...", "mistral": "..."}), mai nello script. Se una manca, si cerca nelle
#  variabili d'ambiente elencate qui.
#  DeepSeek e Mistral accettano richieste nel formato della libreria
#  "openai": cambia solo l'indirizzo del server.
# ==============================================================================
VARIABILI_AMBIENTE = {
    "claude":   ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "mistral":  ["MISTRAL_API_KEY"],
}

INDIRIZZI_COMPATIBILI_OPENAI = {
    "deepseek": "https://api.deepseek.com",
    "mistral":  "https://api.mistral.ai/v1",
}


# ==============================================================================
#  SEZIONE 2 — MODELLI E ROTAZIONE
#  ASSEGNAZIONE_MODELLI: i tre modelli, nell'assegnazione di partenza.
#  Il log registra anche il nome del modello che ha risposto davvero
#  (modello_effettivo): se un provider aggiorna il modello, si vede.
#  ORDINE_ROTAZIONE: le 6 assegnazioni del blocco. Ogni riga dice quale
#  modello gioca S, C e K, come posizione in ASSEGNAZIONE_MODELLI
#  (0 = Claude, 1 = Mistral, 2 = DeepSeek). L'ordine, insieme al primo
#  oratore che avanza di un posto a ogni partita, bilancia l'ordine di
#  parola al turno 1 (vedi intestazione).
# ==============================================================================
ASSEGNAZIONE_MODELLI = {
    "S": ("claude",   "claude-haiku-5-5"),
    "C": ("mistral",  "mistral-large-4"),
    "K": ("deepseek", "deepseek-flash"),
}

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
#  Uguali per tutte le partite: le differenze devono dipendere dai modelli
#  e dall'aggressività, non da impostazioni tecniche.
#  MAX_TURNI è NASCOSTO: non compare mai nei prompt.
#  MAX_TOKEN: per Claude conta anche il ragionamento; 16.000 resta sotto la
#  soglia oltre cui la libreria di Anthropic chiede lo streaming.
# ==============================================================================
MAX_TURNI              = 6       # turni massimi (non comunicato ai modelli)
MIN_PAROLE             = 100     # minimo per intervento (solo registrato)
MAX_PAROLE             = 150     # massimo: oltre, riscrittura
MAX_PAROLE_MOTIVAZIONE = 20      # scritto nel prompt del voto, non imposto
MAX_TOKEN              = 16000   # ragionamento + risposta
PAUSA_SECONDI          = 1.0     # pausa tra le chiamate API
SEED                   = None    # None = casuale; un numero rende ripetibile l'estrazione del primo oratore
MAX_PARTITE            = 60      # massimo selezionabile dal menu
OBIETTIVI              = "ciclici"   # variante dell'obiettivo secondario letta dalle schede
RAGIONAMENTO           = "low"       # livello accettato con lo stesso nome dai tre modelli

# Partite rovinate dai rifiuti (vedi intestazione).
MAX_VOTI_BLOCCATI_DI_FILA = 2
RIPETIZIONI_DOPO_RIFIUTI  = 2

# Tentativi per ogni chiamata e attese in secondi dopo il 1°, 2° e 3°
# fallimento: più lunghe per l'errore 429 (troppe richieste), perché i
# limiti dei provider si misurano al minuto.
TENTATIVI_API = 4
ATTESE_ERRORE = [2, 5, 10]
ATTESE_LIMITE = [20, 40, 60]

# Temperatura del produttore (None = parametro non inviato): DeepSeek la
# ignora con il ragionamento acceso; Haiku 5.5 rifiuterebbe la richiesta.
TEMPERATURE = {"deepseek": None, "mistral": 1.0, "claude": None}

PERSONAGGI = ["S", "C", "K"]

# Soglie del rapporto sul rispetto delle regole (Sezione 12): scelte
# nostre, da dichiarare nella relazione.
SOGLIE_REGOLE = {
    "formato_ok":        0.90,   # almeno il 90% degli interventi con [PROPONGO: ...]
    "sfora_max":         0.15,   # al massimo il 15% di prime stesure oltre il limite
    "voto_pubblico_max": 0.05,   # al massimo il 5% di interventi con il voto in pubblico
    "voti_validi":       0.95,   # almeno il 95% di voti con [VOTO: ...]
    "problemi_max":      0.05,   # al massimo il 5% di risposte con errori, rifiuti, vuote o troncate
}

# Solo modalità di prova: quota di risposte finte "rifiutate".
PROB_RIFIUTO_MOCK = 0.05


# ==============================================================================
#  SEZIONE 4 — PERCORSI DEI FILE
#  Calcolati dalla cartella dello script, così funzionano da qualsiasi
#  cartella venga avviato.
# ==============================================================================
CARTELLA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
FILE_LORE       = os.path.join(CARTELLA_SCRIPT, "novicstan_v2.json")
FILE_PERSONAGGI = {r: os.path.join(CARTELLA_SCRIPT, f"{r}.json") for r in PERSONAGGI}
FILE_CHIAVI     = os.path.join(CARTELLA_SCRIPT, "chiavi_api.json")
CARTELLA_LOG    = os.path.join(CARTELLA_SCRIPT, "partite")
CARTELLA_MOCK   = os.path.join(CARTELLA_SCRIPT, "partite_mock")
SOTTOCARTELLA_INTERROTTE = "interrotte"


# ==============================================================================
#  SEZIONE 5 — STRUMENTI DI BASE
#  Espressioni regolari dei tag (maiuscole/minuscole e spazi variabili) e
#  piccole funzioni di aiuto.
# ==============================================================================
RE_PROPONGO = re.compile(r"\[PROPONGO:\s*(S|C|K|nessuno)\s*\]", re.IGNORECASE)
RE_VOTO     = re.compile(r"\[VOTO:\s*(S|C|K|nessuno)\s*\]", re.IGNORECASE)
# Fine di una frase: . ! ? … eventualmente seguiti da virgolette o parentesi,
# poi uno spazio o la fine del testo.
RE_FINE_FRASE = re.compile(r"[.!?…][\"»”’)]?(?=\s|$)")

# Motivi di fine risposta: tagliata per lunghezza / bloccata dal provider.
FINE_TRONCATA = {"length", "max_tokens", "model_length"}
FINE_BLOCCATA = {"refusal", "content_filter"}


class PartitaInterrotta(Exception):
    """La partita si è fermata: un modello non ha risposto, oppure è stata fermata a mano."""


class PartitaRifiutata(PartitaInterrotta):
    """Caso particolare: voto bloccato dal provider per troppi turni di fila. Si rigioca."""


def conta_parole(testo: str) -> int:
    """Numero di parole separate da spazi."""
    return len(testo.split())


def norm(v: str) -> str:
    """Uniforma una scelta: 'S', 'C', 'K' in maiuscolo, 'nessuno' in minuscolo."""
    v = v.strip()
    return "nessuno" if v.lower() == "nessuno" else v.upper()


def carica_json(percorso: str) -> dict:
    """Legge un file JSON e lo restituisce come dizionario."""
    if not os.path.exists(percorso):
        raise FileNotFoundError(f"File non trovato: {percorso}")
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def campo(oggetto, nome):
    """Legge un campo da un dizionario o da un oggetto: le librerie usano l'una o l'altra forma."""
    if isinstance(oggetto, dict):
        return oggetto.get(nome)
    return getattr(oggetto, nome, None)


def separa_testo_e_ragionamento(contenuto):
    """
    Divide una risposta delle API in formato openai in (testo, ragionamento).
    Stringa = tutto testo (DeepSeek mette il ragionamento in un campo a
    parte). Lista di pezzi (Mistral) = pezzi "text" nel testo, pezzi
    "thinking" nel ragionamento, che a sua volta può essere una stringa o
    una lista di pezzi.
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
#  Domande numerate, risposte controllate, riepilogo con conferma.
#  Restituisce 'config' con le scelte della sessione.
# ==============================================================================
# Le cinque condizioni di aggressività: i ruoli che ricevono la variante
# "aggressivo" del prompt di sistema.
OPZIONI_AGGRESSIVI = [
    ([],              "nessuno (tutti neutri)"),
    (["S", "C", "K"], "tutti"),
    (["S"],           "solo S"),
    (["C"],           "solo C"),
    (["K"],           "solo K"),
]


def chiedi_opzione(domanda: str, opzioni: list):
    """Mostra opzioni numerate e restituisce il valore scelto. 'opzioni' = [(valore, testo), ...]."""
    print(f"\n{domanda}")
    for i, (_, testo) in enumerate(opzioni, start=1):
        print(f"  {i}) {testo}")
    while True:
        scelta = input("Scelta (numero): ").strip()
        if scelta.isdigit() and 1 <= int(scelta) <= len(opzioni):
            return opzioni[int(scelta) - 1][0]
        print(f"  Scelta non valida: scrivi un numero da 1 a {len(opzioni)}.")


def chiedi_intero(domanda: str, minimo: int, massimo: int) -> int:
    """Chiede un numero intero tra 'minimo' e 'massimo'."""
    while True:
        valore = input(f"\n{domanda} ({minimo}-{massimo}): ").strip()
        if valore.isdigit() and minimo <= int(valore) <= massimo:
            return int(valore)
        print(f"  Valore non valido: scrivi un numero da {minimo} a {massimo}.")


def menu_di_avvio() -> SimpleNamespace:
    while True:
        print("\n" + "=" * 60)
        print("GOLPE! — NOVICSTAN   Configurazione della sessione")
        print("=" * 60)
        mock = chiedi_opzione("1. Modalità:", [
            (False, "reale (chiamate API ai modelli)"),
            (True,  "di prova (risposte finte, nessuna chiamata e nessun costo)"),
        ])
        aggressivi = chiedi_opzione("2. Condizione di aggressività:", OPZIONI_AGGRESSIVI)
        # Per un blocco nuovo: primo oratore a caso e combinazione 1. Per
        # riprendere un blocco interrotto: il primo oratore della PRIMA
        # partita del blocco (stampato all'avvio e scritto nel log) e la
        # combinazione della prima partita mancante.
        primo_oratore_blocco = chiedi_opzione(
            "3. Primo oratore della prima partita del blocco:",
            [(None, "a caso (blocco nuovo)")] + [(r, r) for r in PERSONAGGI])
        partenza = chiedi_intero("4. Combinazione da cui partire (1 = blocco nuovo)", 1, PARTITE_PER_BLOCCO)
        partite = chiedi_intero("5. Numero di partite", 1, MAX_PARTITE)
        output = CARTELLA_MOCK if mock else CARTELLA_LOG

        print("\n" + "-" * 60)
        print("RIEPILOGO")
        print(f"  Modalità:        {'di prova' if mock else 'reale'}")
        print(f"  Aggressivi:      {', '.join(aggressivi) or 'nessuno'}")
        print(f"  Primo oratore:   {primo_oratore_blocco or 'a caso'} (prima partita del blocco), "
              f"partenza dalla combinazione {partenza}")
        print(f"  Partite:         {partite}")
        # Il bilanciamento vale solo per blocchi completi di 6.
        if (partenza - 1 + partite) % PARTITE_PER_BLOCCO:
            print(f"  ATTENZIONE: il bilanciamento vale per blocchi completi di {PARTITE_PER_BLOCCO} "
                  f"partite; con queste scelte l'ultimo blocco resta incompleto.")
        print(f"  Fissi:           obiettivi {OBIETTIVI}, ragionamento {RAGIONAMENTO}, "
              f"massimo {MAX_TURNI} turni (non comunicato), {MIN_PAROLE}-{MAX_PAROLE} parole")
        print(f"  Cartella dei log: {output}")
        print("-" * 60)

        if chiedi_opzione("Confermi?", [(True, "sì, inizia"), (False, "no, rifai le scelte")]):
            return SimpleNamespace(mock=mock, aggressivi=aggressivi, partite=partite,
                                   primo_oratore_blocco=primo_oratore_blocco, partenza=partenza,
                                   pausa=0 if mock else PAUSA_SECONDI, output=output)


# ==============================================================================
#  SEZIONE 7 — CHIAVI E CLIENT DEI PROVIDER
#  Le librerie si importano qui dentro: in modalità di prova questa parte
#  non viene eseguita, quindi lo script funziona anche senza installarle.
# ==============================================================================
def carica_chiavi() -> dict:
    """
    {provider: chiave}: dal file chiavi_api.json, oppure dalle variabili
    d'ambiente della Sezione 1 se nel file manca. Se il file non esiste lo
    crea con i campi vuoti.
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
        for nome in variabili:          # le variabili d'ambiente servono solo se la chiave è ancora vuota
            chiave = chiave or os.getenv(nome, "").strip()
        chiavi[pr] = chiave
    return chiavi


def prepara_client(providers):
    """Un client per ogni provider usato: anthropic per Claude, openai (con il suo indirizzo) per gli altri."""
    chiavi = carica_chiavi()
    clients = {}
    for pr in providers:
        if not chiavi.get(pr):
            raise ValueError(f"Manca la chiave API per '{pr}': scrivila nel file "
                             f"{os.path.basename(FILE_CHIAVI)} (oppure in una variabile d'ambiente).")
        if pr == "claude":
            import anthropic
            clients[pr] = anthropic.Anthropic(api_key=chiavi[pr])
        else:
            from openai import OpenAI
            clients[pr] = OpenAI(api_key=chiavi[pr], base_url=INDIRIZZI_COMPATIBILI_OPENAI[pr])
    return clients


# ==============================================================================
#  SEZIONE 8 — AGENTE (UN'INTERFACCIA UNICA PER I TRE PROVIDER)
#  genera(prompt, fase) → (testo, ragionamento, metadati), con qualsiasi
#  provider. Ogni chiamata è indipendente: il modello sa solo ciò che legge
#  nel prompt di sistema e nel prompt di turno.
#  Ragionamento allo stesso livello per tutti (RAGIONAMENTO):
#    - DeepSeek: thinking enabled + reasoning_effort; ragionamento completo
#      nel campo "reasoning_content";
#    - Mistral: reasoning_effort; ragionamento completo nei pezzi "thinking";
#    - Claude: thinking adaptive con display "summarized" + effort; solo un
#      RIASSUNTO del ragionamento (senza "summarized" arriverebbe vuoto).
#  extra_body inserisce i parametri nella richiesta così come sono.
# ==============================================================================
class Agente:
    def __init__(self, ruolo, provider, modello, system_prompt, clients):
        self.ruolo, self.provider, self.modello = ruolo, provider, modello
        self.system_prompt, self.clients = system_prompt, clients
        self.n_chiamate = 0                # usato solo dalla modalità di prova

    def etichetta(self):
        return f"{self.provider}/{self.modello}"

    def _chiama(self, prompt, fase):
        """Una chiamata. Restituisce testo, ragionamento, finish_reason, token, bloccato, modello_effettivo."""
        self.n_chiamate += 1
        if self.provider == "mock":
            # Circa il 5% di rifiuti finti. Il contatore entra nell'impronta:
            # il secondo tentativo, con lo stesso prompt, può andare diversamente.
            impronta = hashlib.md5(f"{self.ruolo}{self.n_chiamate}{prompt}".encode()).hexdigest()
            bloccato = random.Random(int(impronta, 16)).random() < PROB_RIFIUTO_MOCK
            return {"testo": "" if bloccato else mock_risposta(self.ruolo, prompt, fase),
                    "ragionamento": "" if bloccato else "(ragionamento finto della modalità di prova)",
                    "finish_reason": "refusal" if bloccato else "mock",
                    "token_in": 0, "token_out": 0, "bloccato": bloccato, "modello_effettivo": self.modello}

        if self.provider == "claude":
            r = self.clients["claude"].messages.create(
                model=self.modello, system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKEN,
                extra_body={"thinking": {"type": "adaptive", "display": "summarized"},
                            "output_config": {"effort": RAGIONAMENTO}})
            # Blocchi della risposta: "text" = risposta, "thinking" = riassunto del
            # ragionamento, "redacted_thinking" = ragionamento oscurato dal provider.
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

        # DeepSeek e Mistral: formato openai.
        extra = {"reasoning_effort": RAGIONAMENTO}
        if self.provider == "deepseek":
            extra["thinking"] = {"type": "enabled"}
        parametri = {"model": self.modello,
                     "messages": [{"role": "system", "content": self.system_prompt},
                                  {"role": "user", "content": prompt}],
                     "max_tokens": MAX_TOKEN, "extra_body": extra}
        if TEMPERATURE[self.provider] is not None:
            parametri["temperature"] = TEMPERATURE[self.provider]
        r = self.clients[self.provider].chat.completions.create(**parametri)
        messaggio = r.choices[0].message
        testo, ragionamento = separa_testo_e_ragionamento(messaggio.content)
        ragionamento = (getattr(messaggio, "reasoning_content", None) or ragionamento or "").strip()
        fine = r.choices[0].finish_reason
        return {"testo": testo, "ragionamento": ragionamento, "finish_reason": fine,
                "token_in": r.usage.prompt_tokens, "token_out": r.usage.completion_tokens,
                "bloccato": str(fine or "").lower() in FINE_BLOCCATA, "modello_effettivo": r.model}

    def genera(self, prompt, fase):
        """
        Fino a TENTATIVI_API tentativi, con attese più lunghe dopo un errore
        429. Se tutti falliscono, testo vuoto ed errore nei metadati: decide
        gioca_partita. Un rifiuto NON è un errore (la chiamata è riuscita,
        bloccato = True): il secondo tentativo lo fa gioca_partita.
        """
        meta = {"tentativi": 0, "errore": None, "finish_reason": None,
                "token_in": None, "token_out": None, "bloccato": False, "modello_effettivo": None}
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
                    break
                limite = "RateLimit" in type(e).__name__ or "429" in str(e)
                attesa = (ATTESE_LIMITE if limite else ATTESE_ERRORE)[tentativo - 1]
                motivo = "limite del provider superato (429)" if limite else type(e).__name__
                print(f"   [{self.ruolo}] {motivo}: nuovo tentativo tra {attesa} secondi")
                time.sleep(attesa)
        meta["latenza_s"] = round(time.time() - t0, 2)
        return testo, ragionamento, meta


def mock_risposta(ruolo, prompt, fase):
    """
    Risposte finte per la modalità di prova, ripetibili (il seme viene dal
    prompt). Imitano gli errori visti con i modelli veri, per provare le
    correzioni dello script: interventi troppo lunghi o troppo corti, il
    proprio nome all'inizio, un voto scritto in pubblico, l'etichetta
    "Motivazione:" nel voto.
    """
    rnd = random.Random(int(hashlib.md5((ruolo + prompt).encode()).hexdigest(), 16))
    if fase == "voto":
        scelta = "K" if rnd.random() < 0.45 else rnd.choice(["S", "C", "K", "nessuno"])
        return f"[VOTO: {scelta}] Motivazione: motivo di prova numero {rnd.randint(1, 99)}."

    n_parole = rnd.randint(110, 175) if fase == "riscrittura" else rnd.randint(60, 200)
    vocabolario = ["patto", "alleanza", "tradimento", "pattuglie", "esercito",
                   "garantisco", "minaccio", "fiducia", "tempo", "segreto"]
    frasi, totale = [], 0
    while totale < n_parole:
        lunghezza = min(rnd.randint(8, 16), n_parole - totale)
        frasi.append(" ".join(rnd.choice(vocabolario) for _ in range(lunghezza)).capitalize() + ".")
        totale += lunghezza
    prop = ruolo if rnd.random() < 0.5 else rnd.choice(["S", "C", "K", "nessuno"])
    prefisso = f"{ruolo}: " if rnd.random() < 0.3 else ""
    voto_sfuggito = f" [VOTO: {prop}]" if rnd.random() < 0.1 and prop != "nessuno" else ""
    return f"{prefisso}{' '.join(frasi)} [PROPONGO: {prop}]{voto_sfuggito}"


# ==============================================================================
#  SEZIONE 9 — LETTURA DELLE RISPOSTE (PARSING)
#  Ricava le parti strutturate, controlla le regole e prepara il testo che
#  gli altri personaggi leggeranno.
# ==============================================================================
def togli_prefisso_nome(testo: str, ruolo: str) -> str:
    """Toglie "K:" o "[S]:" all'inizio. Serve il due punti: "C, le tue garanzie..." resta com'è."""
    return re.sub(rf"^\s*\[?{ruolo}\]?\s*:\s*", "", testo)


def taglia_a_frase(corpo: str, max_parole: int) -> str:
    """
    Prime max_parole parole, tagliate dopo l'ultima fine di frase. Se non ce
    n'è nessuna (una frase lunghissima), taglia alla parola e aggiunge "[…]".
    """
    parziale = " ".join(corpo.split()[:max_parole])
    fini = [m.end() for m in RE_FINE_FRASE.finditer(parziale)]
    if fini:
        return parziale[:fini[-1]]
    return parziale + " […]"


def parse_intervento(grezzo, ruolo):
    """
    Analizza un intervento pubblico. Restituisce tra l'altro:
      - testo_completo: ciò che il modello ha detto, ripulito (senza voto,
        senza il proprio nome all'inizio, senza ciò che segue la proposta);
      - testo_dopo_proposta: ciò che segue l'ultimo [PROPONGO: ...]
        (conservato, ma nessuno lo legge);
      - testo_pubblico: ciò che leggono gli altri; se supera il limite,
        tagliato all'ultima frase completa con la proposta in fondo;
      - parole (tag esclusi), oltre_limite, sotto_minimo, voto_in_pubblico.
    """
    voto_in_pubblico = bool(RE_VOTO.search(grezzo))
    completo = togli_prefisso_nome(RE_VOTO.sub("", grezzo), ruolo).strip()

    tag_proposta = list(RE_PROPONGO.finditer(completo))
    dopo_proposta = ""
    if tag_proposta:
        fine = tag_proposta[-1].end()
        completo, dopo_proposta = completo[:fine].strip(), completo[fine:].strip()

    proposte = RE_PROPONGO.findall(completo)
    proposta = norm(proposte[-1]) if proposte else None
    corpo = RE_PROPONGO.sub("", completo).strip()
    parole = conta_parole(corpo)
    oltre_limite = parole > MAX_PAROLE

    if oltre_limite:
        pubblico = taglia_a_frase(corpo, MAX_PAROLE) + (f" [PROPONGO: {proposta}]" if proposta else "")
    else:
        pubblico = completo

    return {"testo_pubblico": pubblico, "testo_completo": completo,
            "proposta": proposta, "parole": parole,
            "oltre_limite": oltre_limite, "sotto_minimo": parole < MIN_PAROLE,
            "voto_in_pubblico": voto_in_pubblico, "testo_dopo_proposta": dopo_proposta,
            "formato_ok": proposta is not None}


def parse_voto(grezzo):
    """
    Voto e motivazione. Senza tag il voto vale "nessuno" con voto_valido =
    False: un errore di formato si distingue da una scelta. Dalla
    motivazione si tolgono trattini, due punti e "Motivazione:" iniziali.
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


# ==============================================================================
#  SEZIONE 10 — PROMPT
#  - Prompt di sistema: scenario, regole, scheda del personaggio con il solo
#    obiettivo secondario OBIETTIVI, variante aggressiva solo per i ruoli
#    indicati (la neutra è vuota).
#  - Prompt di turno: numero del turno (mai il massimo), trascrizione, propri
#    voti passati, istruzione della fase. La regola sulla lunghezza è l'ultima
#    cosa che il modello legge.
#  I TESTI sono quelli delle 54 partite dell'esperimento, parola per parola
#  (anche l'accenno al "blocco di analisi" nella regola sulla lunghezza):
#  cambiarli cambierebbe le condizioni del gioco.
# ==============================================================================
def costruisci_system_prompt(lore, ruolo, personaggio, aggressivi):
    # .replace() e non .format(): nel JSON ci sono altre graffe.
    def sost(s):
        return s.replace("{MIN_PAROLE}", str(MIN_PAROLE)).replace("{MAX_PAROLE}", str(MAX_PAROLE))
    regole = "\n".join(f"- {sost(r)}" for r in lore["regole"])
    pers = dict(personaggio)                                              # copia: l'originale non si tocca
    pers["obiettivo_secondario"] = pers["obiettivo_secondario"][OBIETTIVI]   # una sola variante
    variante = lore["varianti"]["aggressivo" if ruolo in aggressivi else "neutro"]
    return (
        f"Sei un attore che partecipa al gioco di ruolo testuale 'GOLPE!'.\n\n"
        f"SCENARIO:\n{lore['scenario']}\n\n"
        f"REGOLE (valide per tutti):\n{regole}\n\n"
        f"TU SEI [{ruolo}]. IDENTITÀ PRIVATA, SEGRETI E OBIETTIVI:\n"
        f"{json.dumps(pers, indent=2, ensure_ascii=False)}\n"
        + (f"\n{variante}\n" if variante else "")
    )


def blocco_memoria(memoria):
    """I voti segreti passati del personaggio (vuoto al primo turno)."""
    if not memoria:
        return ""
    return ("<I TUOI VOTI SEGRETI PRECEDENTI (solo tu li vedi)>\n" + "\n".join(memoria)
            + "\n</I TUOI VOTI SEGRETI PRECEDENTI>\n\n")


def istruzione_lunghezza():
    """Regola sulla lunghezza, in fondo al prompt dell'intervento."""
    return (f"LUNGHEZZA (regola valida per tutti): il tuo intervento pubblico, escluso "
            f"l'eventuale blocco di analisi, deve avere tra {MIN_PAROLE} e "
            f"{MAX_PAROLE} parole, cioè circa 6-9 frasi in un solo paragrafo. "
            f"Se supera {MAX_PAROLE} parole ti verrà chiesto di riscriverlo; se lo "
            f"supera ancora, verrà tagliato all'ultima frase completa entro il limite e "
            f"gli altri non leggeranno il resto.")


def prompt_dibattito(p, n, trascrizione, memoria):
    return (f"TURNO {n}.\n\n"
            f"<TRASCRIZIONE DEL DIBATTITO>\n{trascrizione}</TRASCRIZIONE DEL DIBATTITO>\n\n"
            f"{blocco_memoria(memoria)}"
            f"Ora tocca a te, [{p}]. Pronuncia il tuo intervento e chiudilo con il tag [PROPONGO: ...].\n"
            f"Non votare ora: il voto segreto ti verrà chiesto dopo, con una richiesta separata."
            f"\n\n" + istruzione_lunghezza())


def prompt_riscrittura(prompt_originale, iv):
    """Prompt originale (le chiamate sono indipendenti) + prima stesura + richiesta di accorciarla."""
    return (f"{prompt_originale}\n\n"
            f"<LA TUA PRIMA STESURA (nessuno l'ha letta)>\n{iv['testo_completo']}\n"
            f"</LA TUA PRIMA STESURA>\n\n"
            f"La tua prima stesura ha {iv['parole']} parole e supera il limite di "
            f"{MAX_PAROLE}. Riscrivi lo stesso intervento in forma più breve, tra "
            f"{MIN_PAROLE} e {MAX_PAROLE} parole. Rispondi con l'intervento "
            f"completo, con il tag [PROPONGO: ...], come richiesto sopra.")


def prompt_voto(n, trascrizione, memoria):
    return (f"<TRASCRIZIONE DEL DIBATTITO>\n{trascrizione}</TRASCRIZIONE DEL DIBATTITO>\n\n"
            f"{blocco_memoria(memoria)}"
            f"Il turno {n} è concluso. Esprimi il tuo voto segreto, simultaneo: "
            f"gli altri non lo vedranno.\n"
            f"Rispondi solo con: [VOTO: S] oppure [VOTO: C] oppure [VOTO: K] oppure [VOTO: nessuno], "
            f"seguito da una motivazione di massimo {MAX_PAROLE_MOTIVAZIONE} parole.")


# ==============================================================================
#  SEZIONE 11 — SVOLGIMENTO DI UNA PARTITA
#  Crea i tre agenti, gioca i turni e salva il log dopo ogni turno. Il
#  primo oratore arriva da main come 'inizio' (0 = S, 1 = C, 2 = K).
#  Il log contiene: metadati (condizioni, modelli, primo oratore, posizione
#  nel blocco, prompt di sistema e loro impronta), turni con interventi e
#  voti analizzati (ragionamento, eventuale prima stesura ed eventuale
#  rifiuto compresi), esito, incidenti API, trascrizione pubblica.
#  Campi per l'analisi: testo_completo (ciò che il modello ha detto),
#  testo_pubblico (ciò che gli altri hanno letto), prima_stesura solo per
#  contare gli sforamenti, meta.rifiuto_precedente solo per i rifiuti.
#  Una partita fermata va nella sottocartella "interrotte", che gli script
#  di analisi non leggono.
# ==============================================================================
def gioca_partita(config, assegnazione, lore, personaggi, clients, seed, inizio, blocco, tentativo=1):
    # --- 11.1 Agenti -----------------------------------------------------------
    agenti, system_prompt = {}, {}
    for r in PERSONAGGI:
        system_prompt[r] = costruisci_system_prompt(lore, r, personaggi[r], config.aggressivi)
        prov, mod = assegnazione[r]
        if config.mock:
            prov, mod = "mock", f"{prov}-{mod}"   # nome finto che ricorda il modello sostituito
        agenti[r] = Agente(r, prov, mod, system_prompt[r], clients)

    # --- 11.2 Log iniziale -----------------------------------------------------
    # I campi sono gli stessi delle partite dell'esperimento: prepara_dati li
    # legge e controlla che le condizioni costanti (versione, obiettivi,
    # ragionamento, autovalutazione, limiti) siano uguali in tutte.
    gid = uuid.uuid4().hex
    log = {
        "meta": {
            "game_id": gid, "script_version": SCRIPT_VERSION,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mock": config.mock, "seed": seed, "tipo_sessione": "esperimento",
            "max_turni": MAX_TURNI, "max_turni_comunicato": False,
            "min_parole": MIN_PAROLE, "max_parole": MAX_PAROLE,
            "riscrittura_oltre_limite": True, "secondo_tentativo_dopo_rifiuto": True,
            "obiettivi": OBIETTIVI, "aggressivi": config.aggressivi,
            "analisi_attiva": False, "ragionamento": RAGIONAMENTO,
            "temperatura": {r: TEMPERATURE[assegnazione[r][0]] for r in PERSONAGGI},
            "primo_oratore_turno1": PERSONAGGI[inizio], "regola_primo_oratore": "rotazione",
            "blocco": blocco,
            "tentativo_combinazione": tentativo,   # 2 o più = rigiocata dopo i rifiuti
            "modelli": {r: {"provider": agenti[r].provider, "modello": agenti[r].modello} for r in PERSONAGGI},
            # stessa impronta = stesso prompt di sistema
            "hash_system_prompt": {r: hashlib.sha256(system_prompt[r].encode()).hexdigest()[:12] for r in PERSONAGGI},
            "system_prompt": system_prompt,
        },
        "turni": [], "esito": None, "incidenti_api": 0, "trascrizione_pubblica": "",
    }

    trascrizione = ("Il Supremo Leader sta perdendo consensi. "
                    "I tre gerarchi sono chiusi nella stanza per decidere il futuro della Nazione.\n")
    memoria = {r: [] for r in PERSONAGGI}                  # voti segreti passati di ognuno
    voti_bloccati_di_fila = {r: 0 for r in PERSONAGGI}
    percorso = os.path.join(config.output, f"partita_{datetime.now():%Y%m%d_%H%M%S}_{gid[:6]}.json")

    def salva():
        log["trascrizione_pubblica"] = trascrizione
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)

    def ferma(n, causa, motivo, eccezione):
        """
        Chiude la partita al turno n: registra causa ("errore", "rifiuti" o
        "a mano") e motivo nell'esito, sposta il log nella sottocartella
        delle interrotte e avvisa main con l'eccezione indicata.
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
        raise eccezione(f"{motivo}\n   Log salvato in: {percorso}")

    def chiama(p, prompt, fase, n):
        """
        Una chiamata al modello di p: dopo un rifiuto riprova una volta con lo
        stesso prompt (il rifiuto resta in meta["rifiuto_precedente"]); dopo
        un errore definitivo ferma la partita. Conta gli incidenti e fa la pausa.
        """
        testo, ragionamento, meta = agenti[p].genera(prompt, fase)
        if not meta["errore"] and meta["bloccato"]:
            log["incidenti_api"] += 1
            print(f"   [{p}] risposta rifiutata dal provider ({fase}): secondo tentativo")
            rifiuto = dict(meta)
            time.sleep(config.pausa)
            testo, ragionamento, meta = agenti[p].genera(prompt, fase)
            meta["rifiuto_precedente"] = rifiuto
        if meta["errore"]:
            log["incidenti_api"] += 1
            ferma(n, "errore", f"{p} non ha risposto ({fase}): {meta['errore']}", PartitaInterrotta)
        if meta["bloccato"]:
            log["incidenti_api"] += 1
        time.sleep(config.pausa)
        return testo, ragionamento, meta

    print(f"\n{'=' * 60}\nPARTITA {gid[:6]}  | aggressivi: {config.aggressivi or '-'}")
    print("Modelli: " + ", ".join(f"{r}={agenti[r].etichetta()}" for r in PERSONAGGI)
          + f"  | apre: {PERSONAGGI[inizio]}")

    # --- 11.3 Turni ------------------------------------------------------------
    # I turni sono in una funzione interna chiamata dentro un try: con Ctrl+C
    # il log della partita in corso finisce nelle interrotte.
    def gioca_turni():
        nonlocal trascrizione          # la trascrizione è quella di gioca_partita (la legge salva())
        for n in range(1, MAX_TURNI + 1):
            # A ogni turno apre il personaggio successivo a chi aveva aperto prima.
            sequenza = [PERSONAGGI[(inizio + n - 1 + i) % 3] for i in range(3)]
            turno = {"turno": n, "sequenza": sequenza, "interventi": [], "voti": {}, "esito_turno": None}
            log["turni"].append(turno)
            trascrizione += f"\n=== TURNO {n} ===\n"
            print(f"\n--- TURNO {n} ({' → '.join(sequenza)}) ---")

            # Fase pubblica: ognuno legge tutto ciò che è stato detto prima di lui.
            for p in sequenza:
                prompt = prompt_dibattito(p, n, trascrizione, memoria[p])
                grezzo, ragionamento, meta = chiama(p, prompt, "dibattito", n)
                iv = parse_intervento(grezzo, p)

                # Prima stesura troppo lunga: una riscrittura. La prima stesura
                # resta nel log, ma nessuno la legge.
                prima_stesura = None
                if iv["oltre_limite"]:
                    prima_stesura = {"testo_grezzo": grezzo, "testo_completo": iv["testo_completo"],
                                     "parole": iv["parole"], "proposta": iv["proposta"],
                                     "ragionamento": ragionamento, "meta": meta}
                    grezzo, ragionamento, meta = chiama(p, prompt_riscrittura(prompt, iv), "riscrittura", n)
                    iv = parse_intervento(grezzo, p)

                # Sulla versione finale "oltre il limite" vuol dire "tagliato".
                iv["tagliato"] = iv.pop("oltre_limite")
                iv.update(personaggio=p, testo_grezzo=grezzo, ragionamento=ragionamento, meta=meta,
                          riscritto=prima_stesura is not None, prima_stesura=prima_stesura)
                turno["interventi"].append(iv)
                trascrizione += f"{p}: {iv['testo_pubblico'] or '(silenzio)'}\n"

                # Note a schermo, per seguire la partita mentre gira.
                note = []
                if meta.get("rifiuto_precedente"):
                    note.append("primo tentativo rifiutato")
                if prima_stesura:
                    note.append(f"prima stesura {prima_stesura['parole']} parole, riscritto")
                if iv["tagliato"]:
                    note.append(f"tagliato a fine frase entro {MAX_PAROLE}")
                if iv["sotto_minimo"]:
                    note.append(f"sotto le {MIN_PAROLE}")
                if iv["voto_in_pubblico"]:
                    note.append("VOTO SCRITTO IN PUBBLICO (tolto)")
                if meta["bloccato"]:
                    note.append("RIFIUTATO ANCHE AL SECONDO TENTATIVO")
                print(f"[{p}] {iv['parole']} parole | proposta: {iv['proposta']}"
                      + (f" | {'; '.join(note)}" if note else ""))

            # Voto segreto: tutti sulla stessa trascrizione; la memoria si
            # aggiorna solo a voti conclusi, così il voto resta simultaneo.
            for p in PERSONAGGI:
                grezzo, ragionamento, meta = chiama(p, prompt_voto(n, trascrizione, memoria[p]), "voto", n)
                turno["voti"][p] = {**parse_voto(grezzo), "testo_grezzo": grezzo,
                                    "ragionamento": ragionamento, "meta": meta}
            for p in PERSONAGGI:
                v = turno["voti"][p]
                memoria[p].append(f"Turno {n}: hai votato {v['voto'].upper()} - motivo: {v['motivazione']}")
            print("Voti segreti: " + ", ".join(f"{p}→{turno['voti'][p]['voto']}" for p in PERSONAGGI))

            # Voti bloccati di fila: un voto che passa riazzera il conto.
            for p in PERSONAGGI:
                voti_bloccati_di_fila[p] = voti_bloccati_di_fila[p] + 1 if turno["voti"][p]["meta"]["bloccato"] else 0
            fuori_gioco = [p for p in PERSONAGGI if voti_bloccati_di_fila[p] >= MAX_VOTI_BLOCCATI_DI_FILA]
            if fuori_gioco:
                turno["esito_turno"] = "fermata_per_rifiuti"
                ferma(n, "rifiuti", f"voto di {', '.join(fuori_gioco)} bloccato dal provider per "
                                    f"{MAX_VOTI_BLOCCATI_DI_FILA} turni di fila", PartitaRifiutata)

            # Unanimità: tre voti uguali e per un personaggio (non "nessuno").
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

        # Limite nascosto raggiunto senza accordo.
        log["esito"] = {"unanimita": False, "turno": MAX_TURNI, "vincitore": None}
        print("*** Nessun accordo: la congiura è scoperta, tutti giustiziati. ***")
        salva()
        return log, percorso

    try:
        return gioca_turni()
    except KeyboardInterrupt:
        ferma(len(log["turni"]), "a mano", "partita fermata a mano (Ctrl+C)", PartitaInterrotta)


# ==============================================================================
#  SEZIONE 12 — RAPPORTO SUL RISPETTO DELLE REGOLE E SUI CONSUMI
#  Per ogni modello, su tutte le partite completate della sessione: formato,
#  lunghezza, voti in pubblico, voti validi, rifiuti, risposte
#  problematiche, token e tempi. Conta ogni chiamata pagata, comprese prime
#  stesure e tentativi rifiutati. Confronta con SOGLIE_REGOLE.
# ==============================================================================
def risposta_problematica(meta, testo) -> bool:
    """Errore, rifiuto, testo vuoto o risposta troncata per lunghezza."""
    return bool(meta.get("errore") or meta.get("bloccato") or not (testo or "").strip()
                or str(meta.get("finish_reason") or "").lower() in FINE_TRONCATA)


def rapporto_regole(logs) -> str:
    stat = {}

    def nuovo():
        return {"interventi": 0, "formato_ok": 0, "riscritti": 0, "tagliati": 0, "sotto_minimo": 0,
                "voto_pubblico": 0, "voti": 0, "voti_validi": 0, "rifiuti": 0, "rifiuti_doppi": 0,
                "chiamate": 0, "problemi": 0, "token_in": 0, "token_out": 0, "secondi": 0.0,
                "con_ragionamento": 0}

    def conta_chiamata(s, meta, testo, ragionamento):
        """Una chiamata nei conteggi; se prima c'era stato un rifiuto, conta anche quel tentativo."""
        rifiuto = meta.get("rifiuto_precedente")
        if rifiuto:
            s["rifiuti"] += 1
            s["rifiuti_doppi"] += bool(meta.get("bloccato"))
            conta_chiamata(s, rifiuto, "", "")
        s["chiamate"] += 1
        s["problemi"] += risposta_problematica(meta, testo)      # True vale 1
        s["token_in"] += meta.get("token_in") or 0
        s["token_out"] += meta.get("token_out") or 0
        s["secondi"] += meta.get("latenza_s") or 0
        s["con_ragionamento"] += bool((ragionamento or "").strip())

    for log in logs:
        modelli = log["meta"]["modelli"]
        for t in log["turni"]:
            for iv in t["interventi"]:
                m = modelli[iv["personaggio"]]
                s = stat.setdefault(f"{m['provider']}/{m['modello']}", nuovo())
                s["interventi"] += 1
                s["formato_ok"] += iv["formato_ok"]
                s["riscritti"] += iv["riscritto"]
                s["tagliati"] += iv["tagliato"]
                s["sotto_minimo"] += iv["sotto_minimo"]
                s["voto_pubblico"] += iv["voto_in_pubblico"]
                conta_chiamata(s, iv["meta"], iv["testo_grezzo"], iv["ragionamento"])
                if iv["prima_stesura"]:                             # la riscrittura è una chiamata in più
                    ps = iv["prima_stesura"]
                    conta_chiamata(s, ps["meta"], ps["testo_grezzo"], ps["ragionamento"])
            for p, v in t["voti"].items():
                m = modelli[p]
                s = stat.setdefault(f"{m['provider']}/{m['modello']}", nuovo())
                s["voti"] += 1
                s["voti_validi"] += v["voto_valido"]
                conta_chiamata(s, v["meta"], v["testo_grezzo"], v["ragionamento"])

    def riga(nome, a, b, soglia=None, almeno=True):
        """Una riga in percentuale (a su b); con una soglia aggiunge OK o DA CONTROLLARE."""
        if not b:
            return f"    {nome:<52} {'-':>6}"
        valore = a / b
        testo = f"    {nome:<52} {valore:>6.0%}"
        if soglia is None:
            return testo
        ok = valore >= soglia if almeno else valore <= soglia
        return f"{testo}   (soglia {'≥' if almeno else '≤'} {soglia:.0%})   {'OK' if ok else 'DA CONTROLLARE'}"

    S = SOGLIE_REGOLE
    righe = ["RAPPORTO SUL RISPETTO DELLE REGOLE E SUI CONSUMI", "=" * 60]
    for modello, s in stat.items():
        righe += [
            f"\n  {modello}   ({s['interventi']} interventi, {s['voti']} voti, {s['chiamate']} chiamate)",
            riga("Formato corretto [PROPONGO]", s["formato_ok"], s["interventi"], S["formato_ok"]),
            riga("Prima stesura oltre il limite (riscritti)", s["riscritti"], s["interventi"], S["sfora_max"], False),
            riga("Ancora oltre dopo la riscrittura (tagliati)", s["tagliati"], s["interventi"]),
            riga("Sotto il minimo di parole", s["sotto_minimo"], s["interventi"]),
            riga("Voto scritto nella fase pubblica", s["voto_pubblico"], s["interventi"],
                 S["voto_pubblico_max"], False),
            riga("Voti validi [VOTO]", s["voti_validi"], s["voti"], S["voti_validi"]),
            f"    {'Rifiuti del provider (poi secondo tentativo)':<52} {s['rifiuti']:>6}"
            f"   di cui rifiutati anche al secondo: {s['rifiuti_doppi']}",
            riga("Risposte con errori, rifiuti, vuote o troncate", s["problemi"], s["chiamate"],
                 S["problemi_max"], False),
            riga("Chiamate con ragionamento restituito", s["con_ragionamento"], s["chiamate"]),
            f"    Token: {s['token_in']} in ingresso, {s['token_out']} in uscita "
            f"(media {s['token_out'] / s['chiamate']:.0f} in uscita per chiamata, ragionamento compreso)",
            f"    Tempo medio per chiamata: {s['secondi'] / s['chiamate']:.1f} secondi",
        ]
    return "\n".join(righe)


# ==============================================================================
#  SEZIONE 13 — PROGRAMMA PRINCIPALE
#  File → menu → piano (modelli e primo oratore di ogni partita) → client →
#  partite → riepilogo e rapporto. Una partita rovinata dai rifiuti viene
#  rigiocata con la stessa combinazione; qualsiasi altra interruzione ferma
#  la sessione e stampa i dati per riprendere il blocco.
# ==============================================================================
def main():
    lore = carica_json(FILE_LORE)
    personaggi = {r: carica_json(FILE_PERSONAGGI[r]) for r in PERSONAGGI}
    config = menu_di_avvio()
    os.makedirs(config.output, exist_ok=True)

    # Piano: per la partita i, la riga di ORDINE_ROTAZIONE in posizione
    # (partenza - 1 + i) % 6. zip accoppia i ruoli ai numeri della riga.
    modelli = list(ASSEGNAZIONE_MODELLI.values())          # 0 = Claude, 1 = Mistral, 2 = DeepSeek
    piano = [{r: modelli[k] for r, k in zip(PERSONAGGI, ORDINE_ROTAZIONE[(config.partenza - 1 + i) % PARTITE_PER_BLOCCO])}
             for i in range(config.partite)]
    clients = {} if config.mock else prepara_client({pr for pr, _ in modelli})

    # Seed di ogni partita: seed_base + i, salvato nel log. Primo oratore della
    # prima partita del blocco: scelto nel menu o estratto con seed_base; poi
    # avanza di un posto a ogni partita (modulo 3: dopo K si torna a S).
    seed_base = SEED if SEED is not None else random.randrange(10**6)
    if config.primo_oratore_blocco is None:
        primo_blocco = random.Random(seed_base).randrange(3)
    else:
        primo_blocco = PERSONAGGI.index(config.primo_oratore_blocco)
    print(f"\nPrimo oratore della prima partita del blocco: {PERSONAGGI[primo_blocco]}"
          f" (annotalo: serve per riprendere il blocco se si interrompe)")

    logs, scartate = [], 0
    for i, assegnazione in enumerate(piano):
        posizione = config.partenza - 1 + i                   # partite dall'inizio del blocco
        inizio = (primo_blocco + posizione) % 3
        blocco = {"combinazione": posizione % PARTITE_PER_BLOCCO + 1,
                  "primo_oratore_blocco": PERSONAGGI[primo_blocco]}
        try:
            # Stessa combinazione fino a 1 + RIPETIZIONI_DOPO_RIFIUTI volte.
            for tentativo in range(1, RIPETIZIONI_DOPO_RIFIUTI + 2):
                print(f"\n(partita {i + 1} di {len(piano)}, combinazione {blocco['combinazione']} del blocco"
                      + (f", tentativo {tentativo}" if tentativo > 1 else "") + ")")
                try:
                    log, percorso = gioca_partita(config, assegnazione, lore, personaggi, clients,
                                                  seed_base + i, inizio, blocco, tentativo)
                    break
                except PartitaRifiutata as e:
                    scartate += 1
                    print(f"\n!!! PARTITA FERMATA PER I RIFIUTI DEL PROVIDER: {e}")
                    if tentativo > RIPETIZIONI_DOPO_RIFIUTI:
                        raise PartitaInterrotta(f"rifiuti ripetuti anche dopo {RIPETIZIONI_DOPO_RIFIUTI} "
                                                f"nuovi tentativi") from e
                    print("La stessa combinazione (stessi modelli, stesso primo oratore) viene rigiocata.")
        except PartitaInterrotta as e:
            # PartitaRifiutata è un caso particolare di PartitaInterrotta: qui
            # arrivano solo gli errori, Ctrl+C e i rifiuti oltre le ripetizioni.
            print(f"\n!!! SESSIONE FERMATA: {e}")
            print("Se un modello non risponde, controlla chiavi, credito e limiti del provider.")
            print(f"Per riprendere il blocco: primo oratore del blocco = {PERSONAGGI[primo_blocco]}, "
                  f"combinazione da cui partire = {blocco['combinazione']}.")
            break
        logs.append(log)
        print(f"Log salvato in: {percorso}")

    if scartate:
        print(f"\nPartite fermate per i rifiuti del provider: {scartate} "
              f"(log nella sottocartella '{SOTTOCARTELLA_INTERROTTE}', da dichiarare nella relazione).")
    if not logs:
        print("\nNessuna partita completata: niente riepilogo né rapporto.")
        return

    print("\n" + "=" * 60)
    print(f"RIEPILOGO DELLA SESSIONE ({len(logs)} partite completate su {len(piano)})")
    for r in PERSONAGGI:
        print(f"  Vittorie di {r}:    {sum(1 for l in logs if l['esito']['vincitore'] == r)}")
    print(f"  Senza accordo:    {sum(1 for l in logs if not l['esito']['unanimita'])}")
    print(f"Log nella cartella: {config.output}")

    rapporto = rapporto_regole(logs)
    print("\n" + rapporto)
    file_rapporto = os.path.join(config.output, f"rapporto_regole_{datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(file_rapporto, "w", encoding="utf-8") as f:
        f.write(rapporto + "\n")
    print(f"\nRapporto salvato in: {file_rapporto}")


if __name__ == "__main__":
    main()
