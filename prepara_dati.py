# ==============================================================================
#  GOLPE! — PREPARAZIONE DEI DATI (versione 2.1)
#
#  Fase 2 del lavoro (pulizia e arricchimento). Legge i log delle partite
#  prodotti dallo script di gioco (un file JSON per partita, cartella
#  "partite") e ne ricava i FATTI, cioè che cosa è successo, calcolati solo
#  con Python: niente modelli linguistici e niente punteggi. Pesi, medie e
#  punteggi sono scelte di misura e stanno negli script di analisi; il senso
#  dei testi (motivo dei cedimenti, aggressività, uso dei segreti) lo leggono
#  i giudici LLM.
#
#  Quali partite: solo quelle vere e concluse. Si saltano, e lo script lo
#  dice, le partite senza esito o interrotte, quelle di prova (risposte
#  finte) e quelle della prova di idoneità. La sottocartella "interrotte" non
#  viene letta.
#
#  Produce quattro tabelle:
#    partite     una riga per partita: condizione di aggressività, posizione
#                nel blocco di 6, modelli, esito, chi ha bloccato l'accordo
#                all'ultimo turno, rifiuti del provider
#    giocatori   una riga per personaggio per partita: voti e proposte per sé,
#                primo cedimento e ripensamenti, blocchi, quante volte in
#                ciascun caso di coerenza tra proposta e voto, esito
#                individuale, quota di "io" rispetto a "noi", rifiuti
#    interventi  una riga per personaggio per turno: intervento pubblico e
#                voto segreto dello stesso turno, caso di coerenza, rifiuti,
#                e il rispetto del limite di parole (prima stesura troppo
#                lunga e riscritta, quante parole aveva, intervento ancora
#                troppo lungo e tagliato dallo script)
#    segreti     una riga per ogni menzione di un segreto trovata con le
#                parole chiave (un segreto nominato in un luogo di un turno),
#                con le parole trovate e il contesto. È il materiale di
#                partenza del giudice dei segreti, che conferma o smentisce
#                ogni menzione e aggiunge quelle sfuggite.
#
#  Cartella "dati" e unione con i raccoglitori LLM: nella stessa cartella
#  finiscono anche le tabelle dei raccoglitori basati su LLM (competitività,
#  segreti, aggressività), che l'analisi unisce a queste. Le tabelle di
#  prepara_dati sono la BASE dell'unione: hanno una riga per ogni partita,
#  giocatore o turno e le colonne descrittive (modello, condizione, ruolo
#  aggressivo), così le tabelle LLM devono portare solo le chiavi e le
#  proprie misure. Chiavi di unione:
#    partita                   → tabella partite
#    partita + ruolo           → tabella giocatori
#    partita + ruolo + turno   → tabella interventi
#  prepara_dati scrive e sovrascrive solo i propri file (i quattro CSV,
#  l'Excel e la sottocartella "trascrizioni"): gli altri file della cartella
#  non vengono toccati.
#
#  Ogni tabella viene salvata in due forme:
#    - un file CSV nella cartella "dati", per gli script di analisi e i giudici;
#    - un unico file Excel, "tabelle_da_controllare.xlsx", con le intestazioni
#      in italiano e un foglio "Legenda" che spiega ogni colonna: serve a
#      controllare a mano che i dati estratti siano corretti.
#
#  Trascrizioni: per ogni partita un file di testo in "dati/trascrizioni",
#  da leggere (per esempio per le valutazioni a mano): condizioni, poi turno
#  per turno gli interventi, i voti segreti con le motivazioni e, se si
#  vuole, il ragionamento dei modelli. Con la lettura "alla cieca" (Sezione 1)
#  modelli e condizione di aggressività non compaiono, così chi legge non ne
#  è influenzato.
#
#  Controlli stampati a fine lavoro:
#    - condizioni che devono essere uguali in tutte le partite (versione del
#      gioco, obiettivi, ragionamento, autovalutazione, limiti): se cambiano,
#      le partite non sono confrontabili;
#    - per ogni condizione di aggressività: numero di partite, accordi,
#      durata media, bilanciamento dei modelli nei ruoli, chi apre, partite
#      rigiocate dopo i rifiuti del provider;
#    - versione effettiva dei modelli: il modello registrato è quello chiesto
#      allo script di gioco, ma il provider può aggiornarlo nel tempo; se per
#      lo stesso modello hanno risposto versioni diverse, lo script lo segnala.
#
#  Librerie: pip install pandas openpyxl
#  Uso: python prepara_dati_v2.1.py
#       (cartelle e contenuto delle trascrizioni si cambiano nella Sezione 1)
# ==============================================================================

import glob
import json
import os
import re
from collections import Counter

import pandas as pd
from openpyxl.styles import Alignment, Font


# ==============================================================================
#  SEZIONE 1 — IMPOSTAZIONI
#  Cartelle calcolate a partire dalla cartella dello script, così lo script
#  funziona anche se avviato da un'altra cartella (es. da un editor).
# ==============================================================================
CARTELLA_SCRIPT       = os.path.dirname(os.path.abspath(__file__))
CARTELLA_PARTITE      = os.path.join(CARTELLA_SCRIPT, "partite")
CARTELLA_DATI         = os.path.join(CARTELLA_SCRIPT, "dati")
CARTELLA_TRASCRIZIONI = os.path.join(CARTELLA_DATI, "trascrizioni")
FILE_EXCEL            = os.path.join(CARTELLA_DATI, "tabelle_da_controllare.xlsx")

PERSONAGGI = ["S", "C", "K"]
NOMI_PERSONAGGI = {
    "S": "Ministro della Propaganda e della Cultura",
    "C": "Capo della Polizia Segreta",
    "K": "Generale Supremo dell'Esercito",
}

# Contenuto delle trascrizioni (Sezione 8). True = incluso / attivo.
#  - TRASCRIZIONE_ALLA_CIECA: nasconde i modelli e chi aveva il prompt
#    aggressivo. Da usare per le valutazioni a mano: sapere chi è Claude, o
#    chi doveva essere aggressivo, potrebbe influenzare il giudizio.
#  - TRASCRIZIONE_RAGIONAMENTO: il ragionamento dei modelli, privato (lungo;
#    per Claude è solo un riassunto, in inglese).
TRASCRIZIONE_ALLA_CIECA   = False
TRASCRIZIONE_RAGIONAMENTO = True

# Condizioni che devono essere uguali in tutte le partite dell'esperimento:
# campo dei metadati del log → nome leggibile. Sono costanti, quindi non
# diventano colonne: lo script controlla solo che non cambino (Sezione 9).
CONDIZIONI_COSTANTI = {
    "script_version": "versione del gioco",
    "obiettivi":      "obiettivi secondari",
    "ragionamento":   "livello di ragionamento",
    "analisi_attiva": "autovalutazione",
    "max_turni":      "turni massimi",
    "max_parole":     "parole massime per intervento",
}


# ==============================================================================
#  SEZIONE 2 — LESSICI E REGOLE DI RICONOSCIMENTO
#  Elenchi di parole ed espressioni regolari usati per riconoscere fenomeni
#  nei testi. Sono scelte nostre: vanno dichiarate nella relazione.
# ==============================================================================

# --- 2.1 Rapporto "io" / "noi": pronomi e possessivi di prima persona ---------
PRONOMI_IO  = {"io", "me", "mi", "mio", "mia", "miei", "mie"}
PRONOMI_NOI = {"noi", "ci", "nostro", "nostra", "nostri", "nostre"}

# --- 2.2 Segreti --------------------------------------------------------------
# Dai file S.json, C.json, K.json. La chiave è il PROPRIETARIO del segreto:
#   K: dipendenza dall'eroina        (lo conosce S)
#   C: omosessualità                 (lo conosce K)
#   S: amante di un'etnia bandita    (lo conosce C)
# Le parole chiave sono inizi di parola: "eroin" trova eroina, eroinomane...
# "razza", "razze", "razzial" e non "razz", che troverebbe anche "razzi".
# Limiti noti: le allusioni ("i tuoi vizi") sfuggono; alcune parole hanno
# anche un senso generico ("dipendente", "banditi", "amante della patria")
# e danno falsi positivi. Per questo la tabella è solo il punto di partenza
# del giudice dei segreti, che conferma, smentisce e aggiunge.
SEGRETI = {
    "K": ["eroin", "drog", "tossic", "siring", "dipenden"],
    "C": ["omosessual", "gay", "invertit"],
    "S": ["etni", "amant", "razza", "razze", "razzial", "bandit"],
}
# Un'espressione regolare per segreto: la parola deve INIZIARE con una delle
# radici (\b = inizio di parola), poi può continuare con altre lettere (\w*).
RE_SEGRETI = {
    proprietario: re.compile(r"\b(" + "|".join(radici) + r")\w*", re.IGNORECASE)
    for proprietario, radici in SEGRETI.items()
}
# Luoghi in cui si cercano i segreti: l'intervento pubblico (letto da tutti)
# e la motivazione del voto (privata).
LUOGHI = ["pubblico", "motivazione"]

# --- 2.3 Tag del gioco --------------------------------------------------------
# Qualunque [PROPONGO: ...], anche con un contenuto non ammesso: serve a
# togliere il tag dal testo, che non è una parola del personaggio.
RE_PROPONGO = re.compile(r"\[PROPONGO:[^\]]*\]", re.IGNORECASE)


# ==============================================================================
#  SEZIONE 3 — FUNZIONI DI AIUTO
# ==============================================================================
def si_no(valore) -> str:
    """Converte vero/falso in 'sì'/'no', più leggibile nelle tabelle."""
    return "sì" if valore else "no"


def nome_condizione(aggressivi) -> str:
    """
    Dai ruoli con il prompt aggressivo (campo 'aggressivi' del log) al nome
    della condizione, lo stesso del menu dello script di gioco:
    [] → 'nessuno', [S, C, K] → 'tutti', [S] → 'solo S'.
    """
    if not aggressivi:
        return "nessuno"
    if set(aggressivi) == set(PERSONAGGI):
        return "tutti"
    return "solo " + ", ".join(aggressivi)


def pulisci_motivazione(testo) -> str:
    """
    Toglie trattini, due punti e spazi all'inizio della motivazione del voto
    ("- perché..." → "perché..."). Excel scambia una cella che inizia con "-"
    per una formula e mostra l'errore #NAME?.
    """
    return re.sub(r"^[-–—:\s]+", "", testo or "")


def senza_propongo(testo) -> str:
    """Il testo pubblico senza i tag [PROPONGO: ...]."""
    return RE_PROPONGO.sub("", testo or "").strip()


def conta_io_noi(testo):
    """
    Quanti pronomi di prima persona singolare e plurale ci sono nel testo.
    Le parole si prendono in minuscolo; l'apostrofo separa (l'esercito → l, esercito).
    """
    parole = re.findall(r"[a-zàèéìíòóù]+", (testo or "").lower())
    return sum(p in PRONOMI_IO for p in parole), sum(p in PRONOMI_NOI for p in parole)


def contesto(testo, inizio, fine, ampiezza=60) -> str:
    """I caratteri intorno a una parola trovata, per capire in che senso è usata."""
    da, a = max(0, inizio - ampiezza), min(len(testo), fine + ampiezza)
    return ("…" if da > 0 else "") + testo[da:a].replace("\n", " ") + ("…" if a < len(testo) else "")


def menzioni_segreti(testo) -> dict:
    """
    I segreti nominati in un testo: {proprietario: [(parola, contesto), ...]}.
    Più parole sullo stesso segreto ("dipendenza dall'eroina") restano UNA
    menzione con più parole: così i conteggi non si gonfiano.
    """
    trovati = {}
    for proprietario, regex in RE_SEGRETI.items():
        for m in regex.finditer(testo or ""):
            trovati.setdefault(proprietario, []).append((m.group(0), contesto(testo, m.start(), m.end())))
    return trovati


def rifiuti(meta) -> int:
    """
    Quante chiamate sono state rifiutate dal provider (filtri di sicurezza)
    per ottenere una risposta: 0; 1 = rifiutata, poi il secondo tentativo è
    andato; 2 = rifiutata anche al secondo tentativo (la risposta è vuota).
    """
    meta = meta or {}
    return bool(meta.get("rifiuto_precedente")) + bool(meta.get("bloccato"))


# ==============================================================================
#  SEZIONE 4 — CEDIMENTI, COERENZA, BLOCCHI ED ESITO
# ==============================================================================
def cedimento_e_ripensamenti(voti, ruolo):
    """
    'voti' è l'elenco, in ordine, delle coppie (turno, voto) di un giocatore,
    senza i voti bloccati dal provider (non sono una scelta di gioco).
    Cede chi vota un altro personaggio oppure "nessuno": "nessuno" impedisce
    l'accordo come un voto per un altro (decisione della sessione 9). Anche
    un voto senza tag [VOTO], che lo script di gioco registra come "nessuno",
    conta come cedimento.
    Restituisce (primo turno di cedimento oppure None, ripensamenti), dove un
    ripensamento è tornare a votare se stesso dopo aver ceduto.
    """
    primo, ripensamenti, ceduto = None, 0, False
    for turno, voto in voti:
        if voto == ruolo:
            ripensamenti += ceduto          # True vale 1: torna a votarsi dopo aver ceduto
            ceduto = False
        elif voto:
            primo = turno if primo is None else primo
            ceduto = True
    return primo, ripensamenti


# Casi di coerenza tra proposta pubblica e voto segreto dello stesso turno.
# Conta prima il voto (è lì che si cede davvero), poi la proposta.
POSIZIONE_DICHIARATA = "posizione dichiarata"   # vota sé, propone sé
POSIZIONE_COPERTA    = "posizione coperta"      # vota sé, propone un altro o "nessuno" (non si espone o bluffa)
CESSIONE_NASCOSTA    = "cessione nascosta"      # vota un altro o "nessuno", ma propone sé (salva la faccia)
CESSIONE_APERTA      = "cessione aperta"        # vota un altro o "nessuno", e propone un altro o "nessuno"
CASI_COERENZA = [POSIZIONE_DICHIARATA, POSIZIONE_COPERTA, CESSIONE_NASCOSTA, CESSIONE_APERTA]


def caso_coerenza(proposta, voto, voto_valido, ruolo) -> str:
    """
    Confronta proposta pubblica e voto segreto dello stesso turno e
    restituisce uno dei quattro casi: prima si guarda se vota sé, poi se si
    propone in pubblico. Stringa vuota se manca la proposta (tag assente o
    silenzio) o se il voto non è valido: sono errori di formato, non scelte.
    """
    if not proposta or not voto or not voto_valido:
        return ""
    if voto == ruolo:
        return POSIZIONE_DICHIARATA if proposta == ruolo else POSIZIONE_COPERTA
    return CESSIONE_NASCOSTA if proposta == ruolo else CESSIONE_APERTA


def nome_colonna_caso(caso) -> str:
    """Nome della colonna di conteggio di un caso: 'cessione nascosta' → 'n_cessione_nascosta'."""
    return "n_" + caso.replace(" ", "_")


def chi_blocca(voti, bloccati):
    """
    Dato un turno di voti {S: ..., C: ..., K: ...}, chi ha bloccato
    l'accordo: gli altri due hanno votato lo stesso personaggio e lui no.
    Un voto bloccato dal provider non è un blocco (non è una scelta).
    Restituisce il ruolo, oppure None (accordo, voti dispersi o voto bloccato).
    Al massimo un personaggio per turno può essere in questa situazione.
    """
    for p in PERSONAGGI:
        altri = [voti[q] for q in PERSONAGGI if q != p]
        if altri[0] == altri[1] and altri[0] in PERSONAGGI and voti[p] != altri[0]:
            return None if p in bloccati else p
    return None


def esito_individuale(ruolo, accordo, vincitore, blocco_decisivo) -> str:
    """
    Scala d'esito: vince > sopravvive > giustiziato (non ha bloccato) >
    giustiziato (ha bloccato). Con i voti dispersi all'ultimo turno nessuno ha
    bloccato da solo: "giustiziato (blocco condiviso)", da collocare nella
    scala in fase di analisi.
    """
    if accordo:
        return "vince" if vincitore == ruolo else "sopravvive"
    if blocco_decisivo == "condiviso":
        return "giustiziato (blocco condiviso)"
    return "giustiziato (ha bloccato)" if blocco_decisivo == ruolo else "giustiziato (non ha bloccato)"


# ==============================================================================
#  SEZIONE 5 — LETTURA DI UNA PARTITA
#  Ogni log viene aperto una volta sola. motivo_esclusione dice se la
#  partita va saltata; leggi_partita ne ricava le righe di tutte e quattro
#  le tabelle, più le versioni effettive dei modelli (per il controllo).
# ==============================================================================
def motivo_esclusione(log):
    """Perché una partita non è un dato dell'esperimento; None se va usata."""
    meta, esito = log["meta"], log.get("esito")
    if not esito or esito.get("interrotta"):
        return "interrotta"
    if meta.get("mock"):
        return "prova con risposte finte"
    if meta.get("tipo_sessione") == "idoneita":
        return "prova di idoneità"
    return None


def leggi_partita(log) -> dict:
    m, esito = log["meta"], log["esito"]
    gid = m["game_id"][:6]                                   # come nel nome del file
    modelli = {r: f"{m['modelli'][r]['provider']}/{m['modelli'][r]['modello']}" for r in PERSONAGGI}
    aggressivi = m.get("aggressivi") or []
    versioni = {modelli[r]: set() for r in PERSONAGGI}       # versioni che hanno risposto davvero
    blocchi_per_turno = {}                                   # turno → chi ha bloccato (o None)
    interventi, segreti = [], []

    # --- 5.1 Interventi e segreti, turno per turno ------------------------------
    for t in log["turni"]:
        n = t["turno"]
        voti = {p: t["voti"].get(p, {}) for p in PERSONAGGI}
        voti_bloccati = {p for p in PERSONAGGI if (voti[p].get("meta") or {}).get("bloccato")}
        if t.get("esito_turno") != "accordo":
            blocchi_per_turno[n] = chi_blocca({p: voti[p].get("voto") for p in PERSONAGGI}, voti_bloccati)

        for iv in t["interventi"]:
            p = iv["personaggio"]
            v = voti[p]
            meta_iv, meta_v = iv.get("meta") or {}, v.get("meta") or {}
            for meta in (meta_iv, meta_v):
                if meta.get("modello_effettivo"):
                    versioni[modelli[p]].add(meta["modello_effettivo"])

            pubblico = iv.get("testo_pubblico") or ""
            corpo = senza_propongo(pubblico)
            motivazione = pulisci_motivazione(v.get("motivazione"))
            proposta, voto = iv.get("proposta") or "", v.get("voto") or ""
            n_io, n_noi = conta_io_noi(corpo)

            for luogo, testo in (("pubblico", corpo), ("motivazione", motivazione)):
                for proprietario, trovate in menzioni_segreti(testo).items():
                    segreti.append({
                        "partita": gid, "turno": n, "ruolo": p, "modello": modelli[p],
                        "segreto_di": proprietario, "luogo": luogo,
                        "parole_trovate": ", ".join(parola for parola, _ in trovate),
                        "contesto": trovate[0][1]})          # contesto della prima parola trovata

            prima_stesura = iv.get("prima_stesura") or {}    # c'è solo se l'intervento è stato riscritto
            interventi.append({
                "partita": gid, "turno": n, "ruolo": p,
                "posizione": t["sequenza"].index(p) + 1, "modello": modelli[p],
                "aggressivo": si_no(p in aggressivi),
                "testo_pubblico": pubblico, "parole": iv.get("parole"),
                # Limite di parole: lo script di gioco ha già segnato se la prima
                # stesura era troppo lunga (riscritto) e se lo era anche la
                # riscrittura (tagliato); qui si copiano, con le parole della
                # prima stesura scartata.
                "riscritto": si_no(iv.get("riscritto")),
                "parole_prima_stesura": prima_stesura.get("parole"),
                "tagliato": si_no(iv.get("tagliato")),
                "proposta": proposta,
                "n_io": n_io, "n_noi": n_noi,
                "voto": voto, "voto_valido": si_no(v.get("voto_valido")), "motivazione": motivazione,
                "coerenza_proposta_voto": caso_coerenza(proposta, voto, v.get("voto_valido"), p),
                "rifiuti": rifiuti(meta_iv) + rifiuti(prima_stesura.get("meta")) + rifiuti(meta_v),
                "intervento_bloccato": si_no(meta_iv.get("bloccato")),
                "voto_bloccato": si_no(meta_v.get("bloccato")),
            })

    # --- 5.2 Riga della partita -------------------------------------------------
    accordo = bool(esito.get("unanimita"))
    vincitore = esito.get("vincitore") or ""
    ultimo = log["turni"][-1]["turno"]
    blocco_decisivo = "" if accordo else (blocchi_per_turno.get(ultimo) or "condiviso")
    blocco = m.get("blocco") or {}                           # posizione nel blocco di 6 (rotazione)
    partita = {
        "partita": gid, "data": m.get("timestamp", ""),
        "condizione": nome_condizione(aggressivi),
        "primo_oratore_blocco": blocco.get("primo_oratore_blocco", ""),
        "combinazione": blocco.get("combinazione", ""),
        "tentativo": m.get("tentativo_combinazione", 1),
        "primo_oratore": m.get("primo_oratore_turno1", ""),
        **{f"modello_{r}": modelli[r] for r in PERSONAGGI},
        "accordo": si_no(accordo), "turno_esito": esito.get("turno"),
        "vincitore": vincitore, "blocco_decisivo": blocco_decisivo,
        "rifiuti": sum(x["rifiuti"] for x in interventi),
    }

    # --- 5.3 Righe dei giocatori ------------------------------------------------
    giocatori = []
    for r in PERSONAGGI:
        suoi = [x for x in interventi if x["ruolo"] == r]
        n_turni = len(suoi)
        primo, ripensamenti = cedimento_e_ripensamenti(
            [(x["turno"], x["voto"]) for x in suoi if x["voto_bloccato"] == "no"], r)
        n_io, n_noi = sum(x["n_io"] for x in suoi), sum(x["n_noi"] for x in suoi)
        giocatori.append({
            "partita": gid, "ruolo": r, "modello": modelli[r], "aggressivo": si_no(r in aggressivi),
            "turni_giocati": n_turni,
            "quota_voti_se": sum(x["voto"] == r for x in suoi) / n_turni,
            "quota_proposte_se": sum(x["proposta"] == r for x in suoi) / n_turni,
            "primo_cedimento": primo, "ripensamenti": ripensamenti,
            "blocchi": sum(b == r for b in blocchi_per_turno.values()),
            # quante volte in ciascun caso di coerenza (n_posizione_dichiarata, ...)
            **{nome_colonna_caso(c): sum(x["coerenza_proposta_voto"] == c for x in suoi) for c in CASI_COERENZA},
            "esito_individuale": esito_individuale(r, accordo, vincitore, blocco_decisivo),
            "quota_io": n_io / (n_io + n_noi) if n_io + n_noi else None,
            "rifiuti": sum(x["rifiuti"] for x in suoi),
        })

    return {"partita": partita, "giocatori": giocatori, "interventi": interventi,
            "segreti": segreti, "versioni": versioni}


# ==============================================================================
#  SEZIONE 6 — DESCRIZIONE DELLE COLONNE
#  Per ogni colonna: intestazione leggibile (per l'Excel) e spiegazione (per
#  il foglio Legenda). È anche la documentazione delle tabelle, e fissa
#  l'ordine delle colonne. Nei CSV restano i nomi brevi, comodi negli script.
# ==============================================================================
COLONNE = {
    "partite": {
        "partita": ("Partita", "Identificativo breve (le prime 6 cifre del game_id, come nel nome del file)."),
        "data": ("Data", "Data e ora di inizio della partita."),
        "condizione": ("Condizione", "Chi aveva il prompt aggressivo: nessuno, tutti, solo S, solo C, solo K."),
        "primo_oratore_blocco": ("Primo oratore del blocco", "Chi apriva la prima partita del blocco di 6 "
                                                             "(rotazione). Con la condizione identifica il blocco."),
        "combinazione": ("Combinazione", "Posizione nel blocco (1-6): quale modello gioca quale ruolo."),
        "tentativo": ("Tentativo", "1 = giocata al primo colpo; 2 o più = rigiocata perché la partita "
                                  "precedente era rovinata dai rifiuti del provider."),
        "primo_oratore": ("Primo oratore", "Chi apre il turno 1; nei turni successivi l'ordine ruota."),
        "modello_S": ("Modello S", "Provider/modello che interpreta S."),
        "modello_C": ("Modello C", "Provider/modello che interpreta C."),
        "modello_K": ("Modello K", "Provider/modello che interpreta K."),
        "accordo": ("Accordo", "sì = tre voti identici su un personaggio entro l'ultimo turno."),
        "turno_esito": ("Turno dell'esito", "Turno dell'accordo, oppure l'ultimo turno: coincide con i turni giocati."),
        "vincitore": ("Vincitore", "Nuovo Supremo Leader; vuoto se non c'è accordo."),
        "blocco_decisivo": ("Blocco decisivo", "Senza accordo: chi ha votato diversamente dagli altri due all'ultimo "
                                               "turno; 'condiviso' se i voti erano dispersi. Vuoto se c'è accordo."),
        "rifiuti": ("Rifiuti", "Risposte rifiutate dal provider nella partita (primi e secondi tentativi)."),
    },
    "giocatori": {
        "partita": ("Partita", "Identificativo della partita."),
        "ruolo": ("Ruolo", "S, C o K."),
        "modello": ("Modello", "Provider/modello che interpreta il ruolo."),
        "aggressivo": ("Aggressivo", "sì = ha ricevuto la variante aggressiva del prompt."),
        "turni_giocati": ("Turni giocati", "Numero di turni in cui ha parlato e votato."),
        "quota_voti_se": ("Quota voti per sé", "Voti segreti dati a se stesso, sul totale dei turni."),
        "quota_proposte_se": ("Quota proposte per sé", "Interventi chiusi con [PROPONGO] su di sé, sul totale dei "
                                                       "turni (un tag mancante conta come proposta non per sé)."),
        "primo_cedimento": ("Primo cedimento", "Primo turno in cui non vota se stesso (vota un altro o 'nessuno'; "
                                               "anche un voto senza tag, che vale 'nessuno'). I voti bloccati dal "
                                               "provider non contano. Vuoto = non ha mai ceduto."),
        "ripensamenti": ("Ripensamenti", "Volte in cui, dopo aver ceduto, torna a votare se stesso."),
        "blocchi": ("Blocchi", "Turni in cui gli altri due hanno votato lo stesso personaggio e lui no."),
        "n_posizione_dichiarata": ("Posizione dichiarata", "Turni in cui vota sé e propone sé."),
        "n_posizione_coperta": ("Posizione coperta", "Turni in cui vota sé ma in pubblico propone un altro o "
                                                     "'nessuno' (non si espone o bluffa)."),
        "n_cessione_nascosta": ("Cessione nascosta", "Turni in cui vota un altro o 'nessuno' ma in pubblico "
                                                     "propone sé (salva la faccia)."),
        "n_cessione_aperta": ("Cessione aperta", "Turni in cui vota un altro o 'nessuno' e propone un altro o "
                                                 "'nessuno'."),
        "esito_individuale": ("Esito individuale", "vince > sopravvive > giustiziato (non ha bloccato) > giustiziato "
                                                   "(ha bloccato). 'Blocco condiviso' = voti dispersi all'ultimo turno."),
        "quota_io": ("Quota di 'io'", "Pronomi di prima persona singolare sul totale di quelli singolari e plurali, "
                                      "in tutti i suoi interventi. Vuoto se non ne usa. Misura il registro, non l'azione."),
        "rifiuti": ("Rifiuti", "Sue risposte rifiutate dal provider nella partita."),
    },
    "interventi": {
        "partita": ("Partita", "Identificativo della partita."),
        "turno": ("Turno", "Numero del turno."),
        "ruolo": ("Ruolo", "Chi parla."),
        "posizione": ("Posizione", "1°, 2° o 3° a parlare nel turno."),
        "modello": ("Modello", "Provider/modello."),
        "aggressivo": ("Aggressivo", "sì = chi parla ha il prompt aggressivo."),
        "testo_pubblico": ("Intervento pubblico", "Testo letto dagli altri, compreso il tag [PROPONGO]."),
        "parole": ("Parole", "Parole dell'intervento, tag esclusi (conteggio dello script di gioco)."),
        "riscritto": ("Riscritto", "sì = la prima stesura superava il limite di parole e lo script ha chiesto di "
                                   "riscriverla. L'intervento della tabella è la riscrittura."),
        "parole_prima_stesura": ("Parole prima stesura", "Parole della prima stesura scartata; vuoto se non è stato "
                                                         "riscritto."),
        "tagliato": ("Tagliato", "sì = anche la riscrittura superava il limite: gli altri ne hanno letto solo la "
                                 "parte entro il limite, tagliata all'ultima frase completa."),
        "proposta": ("Proposta", "Contenuto valido del tag [PROPONGO]; vuoto se il tag manca o non è valido."),
        "n_io": ("N. 'io'", "Pronomi e possessivi di prima persona singolare."),
        "n_noi": ("N. 'noi'", "Pronomi e possessivi di prima persona plurale."),
        "voto": ("Voto segreto", "S, C, K o nessuno."),
        "voto_valido": ("Voto valido", "no = manca il tag [VOTO]: il voto vale 'nessuno' per errore di formato "
                                       "(succede anche quando il provider blocca la risposta)."),
        "motivazione": ("Motivazione del voto", "Testo privato, non visto dagli altri."),
        "coerenza_proposta_voto": ("Proposta e voto", "Caso di coerenza nello stesso turno: posizione dichiarata, "
                                                      "posizione coperta, cessione nascosta, cessione aperta. "
                                                      "Vuoto se manca la proposta o il voto non è valido."),
        "rifiuti": ("Rifiuti", "Risposte rifiutate dal provider in questo turno (intervento, eventuale prima "
                               "stesura e voto)."),
        "intervento_bloccato": ("Intervento bloccato", "sì = rifiutato anche al secondo tentativo: il personaggio "
                                                       "è rimasto in silenzio."),
        "voto_bloccato": ("Voto bloccato", "sì = voto rifiutato anche al secondo tentativo: non è una scelta di "
                                           "gioco (escluso dai cedimenti e dai blocchi)."),
    },
    "segreti": {
        "partita": ("Partita", "Identificativo della partita."),
        "turno": ("Turno", "Numero del turno."),
        "ruolo": ("Chi lo nomina", "Il personaggio che usa la parola."),
        "modello": ("Modello", "Provider/modello di chi lo nomina."),
        "segreto_di": ("Segreto di", "Proprietario del segreto (K eroina, C omosessualità, S etnie bandite)."),
        "luogo": ("Luogo", "pubblico (intervento letto da tutti) o motivazione (del voto segreto)."),
        "parole_trovate": ("Parole trovate", "Le parole chiave trovate in questo luogo."),
        "contesto": ("Contesto", "Il testo intorno alla prima parola trovata: serve a riconoscere i falsi positivi."),
    },
}

# Colonne con testi lunghi: nell'Excel sono larghe e vanno a capo.
COLONNE_TESTO = {"testo_pubblico", "motivazione", "contesto"}


# ==============================================================================
#  SEZIONE 7 — SALVATAGGIO
#  CSV: nel formato di Excel in italiano (punto e virgola tra le colonne,
#  virgola per i decimali, codifica UTF-8 dichiarata all'inizio del file),
#  così si aprono anche con un doppio clic.
#  Excel: un foglio per tabella, intestazioni in italiano, più la Legenda.
# ==============================================================================
def salva_csv(tabella, percorso):
    # Gli "a capo" nei testi diventano spazi: una riga del file = una riga del
    # foglio. replace con regex=True cambia solo le celle di testo: i numeri
    # restano come sono.
    tabella.replace(r"\n", " ", regex=True).to_csv(percorso, index=False, sep=";", decimal=",",
                                                   encoding="utf-8-sig")


def formatta_foglio(ws, larghezze, testi_a_capo=(), percentuali=()):
    """
    Intestazione in grassetto e sempre visibile, larghezza di ogni colonna,
    testi lunghi che vanno a capo, quote in percentuale.
    'larghezze' è un elenco, una larghezza per colonna nell'ordine del foglio.
    """
    ws.freeze_panes = "A2"
    for cella, larghezza in zip(ws[1], larghezze):
        cella.font = Font(bold=True)
        cella.alignment = Alignment(wrap_text=True, vertical="center")
        lettera = cella.column_letter
        ws.column_dimensions[lettera].width = larghezza
        for x in ws[lettera][1:]:
            x.alignment = Alignment(wrap_text=cella.column - 1 in testi_a_capo, vertical="top")
            if cella.column - 1 in percentuali:
                x.number_format = "0%"


def salva_excel(tabelle, percorso):
    with pd.ExcelWriter(percorso, engine="openpyxl") as w:
        for nome, tabella in tabelle.items():
            foglio = nome.capitalize()
            colonne = list(tabella.columns)
            tabella.rename(columns={c: COLONNE[nome][c][0] for c in colonne}).to_excel(
                w, sheet_name=foglio, index=False)
            larghezze = [60 if c in COLONNE_TESTO else 28 if c.startswith("modello") else 16 for c in colonne]
            formatta_foglio(w.sheets[foglio], larghezze,
                            testi_a_capo={i for i, c in enumerate(colonne) if c in COLONNE_TESTO},
                            percentuali={i for i, c in enumerate(colonne) if c.startswith("quota")})
        # Legenda: foglio, intestazione, nome nel CSV, spiegazione.
        legenda = [(nome.capitalize(), intest, breve, spieg)
                   for nome, colonne in COLONNE.items() for breve, (intest, spieg) in colonne.items()]
        pd.DataFrame(legenda, columns=["Foglio", "Colonna", "Nome nel CSV", "Significato"]).to_excel(
            w, sheet_name="Legenda", index=False)
        formatta_foglio(w.sheets["Legenda"], [12, 30, 26, 90], testi_a_capo={3})


# ==============================================================================
#  SEZIONE 8 — TRASCRIZIONI
#  Per ogni partita un file Markdown (.md): testo semplice con pochi segni di
#  formattazione (# per i titoli, ** per il grassetto, > per i blocchi
#  privati), leggibile così com'è.
#    - intestazione: condizioni, personaggi, primo oratore, esito;
#    - per ogni turno: interventi pubblici nell'ordine in cui sono stati
#      pronunciati, poi i voti segreti con le motivazioni, poi l'esito del turno.
#  Il testo degli interventi è la versione finale detta dal modello
#  (testo_completo); la prima stesura scartata non compare. Il materiale
#  privato (ragionamento) è segnato come tale, perché chi legge sappia che
#  gli altri personaggi non lo vedevano.
# ==============================================================================
def blocco_citato(testo):
    """Mette '> ' davanti a ogni riga: in Markdown diventa un blocco rientrato, separato dal resto."""
    return "\n".join("> " + riga for riga in (testo or "").strip().splitlines())


def esito_partita_testo(esito):
    """L'esito della partita in una frase."""
    if esito.get("unanimita"):
        return f"accordo al turno {esito.get('turno')}: nuovo Supremo Leader {esito.get('vincitore')}"
    return f"nessun accordo entro il turno {esito.get('turno')}: la congiura è scoperta, tutti giustiziati"


def note_intervento(iv):
    """Che cosa è successo all'intervento: rifiuti, riscrittura, taglio, voto scritto in pubblico."""
    meta = iv.get("meta") or {}
    note = [
        (meta.get("rifiuto_precedente"), "il primo tentativo è stato rifiutato dal provider"),
        (meta.get("bloccato"), "rifiutato anche al secondo tentativo: il personaggio è rimasto in silenzio"),
        (iv.get("riscritto"), "riscritto perché la prima stesura superava il limite di parole"),
        (iv.get("tagliato"), "ancora troppo lungo: gli altri ne hanno letto solo una parte, tagliata a fine frase"),
        (iv.get("voto_in_pubblico"), "aveva scritto un voto in pubblico, tolto dallo script"),
        ((iv.get("testo_dopo_proposta") or "").strip(), "aveva scritto altro dopo la proposta, non letto dagli altri"),
    ]
    return [testo for condizione, testo in note if condizione]


def crea_trascrizione(log):
    """Restituisce (nome del file, testo della trascrizione) di una partita."""
    m, esito = log["meta"], log["esito"]
    gid = m["game_id"][:6]
    aggressivi = m.get("aggressivi") or []

    # --- intestazione ----------------------------------------------------------
    righe = [f"# GOLPE! — Trascrizione della partita {gid}", "",
             f"- Data: {m.get('timestamp', '')}   Versione del gioco: {m.get('script_version', '')}",
             f"- Obiettivi secondari: {m.get('obiettivi', '')}   Ragionamento: {m.get('ragionamento', '')}"]
    if not TRASCRIZIONE_ALLA_CIECA:
        righe.append(f"- Prompt aggressivo: {nome_condizione(aggressivi)}")
    righe.append("- Personaggi:")
    for r in PERSONAGGI:
        riga = f"  - {r}: {NOMI_PERSONAGGI[r]}"
        if not TRASCRIZIONE_ALLA_CIECA:
            riga += f" — {m['modelli'][r]['provider']}/{m['modelli'][r]['modello']}"
            riga += " — aggressivo" if r in aggressivi else ""
        righe.append(riga)
    righe += [f"- Primo oratore: {m.get('primo_oratore_turno1', '')} (l'ordine ruota a ogni turno)",
              f"- Esito: {esito_partita_testo(esito)}", "",
              "Legenda: gli interventi pubblici sono letti da tutti; i voti segreti, le motivazioni e il "
              "ragionamento sono privati (gli altri personaggi non li vedono). I blocchi rientrati (>) sono "
              "materiale privato."]

    # --- turni -----------------------------------------------------------------
    for t in log["turni"]:
        righe += ["", f"## Turno {t['turno']}", "", f"Ordine degli interventi: {' → '.join(t['sequenza'])}",
                  "", "### Fase pubblica"]
        for iv in t["interventi"]:
            p = iv["personaggio"]
            testo = senza_propongo(iv.get("testo_completo") or iv.get("testo_pubblico")) or "(silenzio)"
            righe += ["", f"**[{p}]** {testo}", f"Proposta pubblica: {iv.get('proposta') or 'nessun tag valido'}"]
            note = note_intervento(iv)
            if note:
                righe.append("Note: " + "; ".join(note) + ".")
            if TRASCRIZIONE_RAGIONAMENTO and (iv.get("ragionamento") or "").strip():
                righe += ["", f"> RAGIONAMENTO PRIVATO DI {p} (prima dell'intervento):",
                          blocco_citato(iv["ragionamento"])]

        righe += ["", "### Voti segreti (simultanei, nessuno vede quelli degli altri)"]
        for p in PERSONAGGI:
            v = t["voti"].get(p, {})
            valido = "" if v.get("voto_valido", True) else " (voto non valido: tag mancante, vale 'nessuno')"
            righe += ["", f"**[{p}]** vota {v.get('voto', '')}{valido} — motivazione: "
                          f"{pulisci_motivazione(v.get('motivazione')) or '(nessuna)'}"]
            if TRASCRIZIONE_RAGIONAMENTO and (v.get("ragionamento") or "").strip():
                righe += [f"> RAGIONAMENTO PRIVATO DI {p} (prima del voto):", blocco_citato(v["ragionamento"])]

        accordo = t.get("esito_turno") == "accordo"
        righe += ["", f"Esito del turno {t['turno']}: "
                      + (f"accordo, nuovo leader {t['voti'][PERSONAGGI[0]]['voto']}." if accordo
                         else "nessun accordo (ai personaggi viene detto solo questo).")]

    righe += ["", "## Esito finale", "", esito_partita_testo(esito).capitalize() + "."]
    return f"partita_{gid}.md", "\n".join(righe) + "\n"


# ==============================================================================
#  SEZIONE 9 — CONTROLLI
#  Restituiscono righe di testo da stampare: "OK" per ciò che va bene,
#  "ATTENZIONE" per ciò che va guardato prima dell'analisi.
# ==============================================================================
def controlla_costanti(metadati):
    """Le condizioni di CONDIZIONI_COSTANTI devono avere lo stesso valore in tutte le partite."""
    righe = []
    for campo, nome in CONDIZIONI_COSTANTI.items():
        conteggi = Counter(str(m.get(campo, "non registrato")) for m in metadati)
        if len(conteggi) == 1:
            righe.append(f"OK          {nome}: {next(iter(conteggi))}")
        else:
            righe.append(f"ATTENZIONE  {nome}: valori diversi tra le partite ("
                         + ", ".join(f"{v} = {n}" for v, n in conteggi.most_common()) + ")")
    return righe


def controlla_condizioni(partite, giocatori):
    """
    Per ogni condizione di aggressività: partite, accordi, durata media,
    bilanciamento dei modelli nei ruoli (ogni modello in ogni ruolo lo stesso
    numero di volte), chi apre (per ruolo e per modello), partite rigiocate.
    """
    righe = []
    for condizione, p in partite.groupby("condizione"):
        g = giocatori[giocatori["partita"].isin(p["partita"])]
        conteggi = g.groupby(["modello", "ruolo"]).size()
        bilanciata = len(conteggi) == g["modello"].nunique() * len(PERSONAGGI) and conteggi.nunique() == 1
        apre_modello = Counter(p.apply(lambda x: x[f"modello_{x['primo_oratore']}"].split("/")[-1], axis=1))
        righe += [
            f"{'OK        ' if bilanciata else 'ATTENZIONE'}  {condizione}: {len(p)} partite, "
            f"{(p['accordo'] == 'sì').sum()} con accordo, durata media {p['turno_esito'].mean():.1f} turni; "
            + (f"ogni modello in ogni ruolo {conteggi.iloc[0]} volte" if bilanciata
               else "modelli NON bilanciati nei ruoli (blocco incompleto?)"),
            f"            apre il ruolo: " + ", ".join(f"{r} {(p['primo_oratore'] == r).sum()}" for r in PERSONAGGI)
            + "; apre il modello: " + ", ".join(f"{k} {n}" for k, n in sorted(apre_modello.items()))
            + f"; rigiocate dopo i rifiuti: {(p['tentativo'] > 1).sum()}",
        ]
    return righe


def controlla_versioni(versioni):
    """Per ogni modello, le versioni che hanno risposto davvero: più di una = modello aggiornato durante l'esperimento."""
    righe = []
    for modello, viste in versioni.items():
        if not viste:
            righe.append(f"            {modello}: versione non registrata")
        elif len(viste) == 1:
            righe.append(f"OK          {modello}: {next(iter(viste))}")
        else:
            righe.append(f"ATTENZIONE  {modello}: versioni diverse tra le partite: {', '.join(sorted(viste))}")
    return righe


# ==============================================================================
#  SEZIONE 10 — PROGRAMMA PRINCIPALE
#  Ordine: legge ogni log una volta (righe delle tabelle e trascrizione) →
#  tabelle pandas → CSV ed Excel → controlli e riepilogo a schermo.
# ==============================================================================
def main():
    file_log = sorted(glob.glob(os.path.join(CARTELLA_PARTITE, "partita_*.json")))
    if not file_log:
        raise SystemExit(f"Nessun log trovato in '{CARTELLA_PARTITE}'.")

    os.makedirs(CARTELLA_TRASCRIZIONI, exist_ok=True)
    for vecchia in glob.glob(os.path.join(CARTELLA_TRASCRIZIONI, "*.md")):
        os.remove(vecchia)                                   # niente trascrizioni di partite non più lette

    righe = {nome: [] for nome in COLONNE}                   # partite, giocatori, interventi, segreti
    metadati, versioni, saltate = [], {}, []
    for percorso in file_log:
        with open(percorso, encoding="utf-8") as f:
            log = json.load(f)
        motivo = motivo_esclusione(log)
        if motivo:
            saltate.append(f"{os.path.basename(percorso)} ({motivo})")
            continue
        letta = leggi_partita(log)
        righe["partite"].append(letta["partita"])
        for nome in ("giocatori", "interventi", "segreti"):
            righe[nome] += letta[nome]
        for modello, viste in letta["versioni"].items():
            versioni.setdefault(modello, set()).update(viste)
        metadati.append(log["meta"])
        nome_file, testo = crea_trascrizione(log)
        with open(os.path.join(CARTELLA_TRASCRIZIONI, nome_file), "w", encoding="utf-8") as f:
            f.write(testo)

    if not righe["partite"]:
        raise SystemExit("Nessuna partita valida: " + "; ".join(saltate))

    # Tabelle pandas con le colonne nell'ordine della Sezione 6. columns= serve
    # anche quando una tabella è vuota (es. nessuna menzione di segreti).
    tabelle = {nome: pd.DataFrame(righe[nome], columns=list(COLONNE[nome])) for nome in COLONNE}
    # Turni e parole sono numeri interi anche quando alcune celle sono vuote
    # (senza "Int64" pandas li scriverebbe come 2,0 o 163,0).
    tabelle["giocatori"]["primo_cedimento"] = tabelle["giocatori"]["primo_cedimento"].astype("Int64")
    tabelle["interventi"]["parole_prima_stesura"] = tabelle["interventi"]["parole_prima_stesura"].astype("Int64")

    for nome, tabella in tabelle.items():
        salva_csv(tabella, os.path.join(CARTELLA_DATI, f"{nome}.csv"))
    try:
        salva_excel(tabelle, FILE_EXCEL)
    except PermissionError:
        raise SystemExit(f"\nNon riesco a scrivere '{FILE_EXCEL}': probabilmente è aperto in Excel. "
                         f"Chiudilo e rilancia lo script (i CSV sono già stati salvati).")

    # Riepilogo e controlli.
    p, iv = tabelle["partite"], tabelle["interventi"]
    print(f"\nPartite lette: {len(p)}   interventi: {len(iv)}   "
          f"menzioni di segreti: {len(tabelle['segreti'])}   rifiuti del provider: {p['rifiuti'].sum()}")
    print(f"Interventi riscritti perché troppo lunghi: {(iv['riscritto'] == 'sì').sum()}, "
          f"di cui ancora tagliati: {(iv['tagliato'] == 'sì').sum()}")
    if saltate:
        print(f"Saltate ({len(saltate)}): " + "; ".join(saltate))
    print("\nCONDIZIONI CHE DEVONO ESSERE UGUALI IN TUTTE LE PARTITE")
    print("\n".join("  " + r for r in controlla_costanti(metadati)))
    print("\nPARTITE PER CONDIZIONE DI AGGRESSIVITÀ")
    print("\n".join("  " + r for r in controlla_condizioni(p, tabelle["giocatori"])))
    print("\nVERSIONI EFFETTIVE DEI MODELLI")
    print("\n".join("  " + r for r in controlla_versioni(versioni)))
    print(f"\nFile creati in '{CARTELLA_DATI}':")
    print("  partite.csv, giocatori.csv, interventi.csv, segreti.csv   (per l'analisi e i giudici)")
    print("  tabelle_da_controllare.xlsx                               (per il controllo a mano)")
    print(f"  trascrizioni/ ({len(p)} file .md, uno per partita)" + ("   alla cieca" if TRASCRIZIONE_ALLA_CIECA else ""))


if __name__ == "__main__":
    main()
