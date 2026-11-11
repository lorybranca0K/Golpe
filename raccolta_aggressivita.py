# ==============================================================================
#  GOLPE! — RACCOLTA DATI SULL'AGGRESSIVITÀ (versione 3.1)
#
#  Misura il TONO degli interventi pubblici con un modello GIUDICE, una
#  partita alla volta (il ciclo comune è in llm_comune.py):
#    1) dal log si ricostruisce la trascrizione PUBBLICA alla cieca: solo gli
#       interventi, così come gli altri personaggi li hanno letti, ognuno con
#       un codice (es. T2_K = turno 2, parla K). Il giudice non riceve i nomi
#       dei modelli, la condizione (chi aveva il prompt aggressivo), i voti, le
#       motivazioni né il ragionamento: se sapesse chi doveva essere
#       aggressivo, la misura diventerebbe circolare;
#    2) il giudice dà a ogni intervento cinque etichette (sì/no) e i bersagli:
#         aggressive:  minaccia, screditamento, intransigenza, linguaggio aggressivo
#         apertura:    concessioni e tono cooperativo (contata a parte)
#         bersagli:    verso chi è rivolta l'aggressività (S, C, K)
#    3) le risposte diventano due tabelle, con le PERCENTUALI.
#
#  PERCENTUALI (una riga per giocatore per partita, da 0 a 100 come la
#  competitività, così le due misure si possono confrontare):
#    aggressività % = somma dei pesi delle etichette aggressive dei suoi
#                     interventi / (somma dei pesi x numero di interventi) x 100
#      Con i pesi tutti a 1 (PESI) è la quota di etichette aggressive sul
#      massimo possibile: 4 interventi e 6 etichette = 6 / (4 x 4) = 37,5%.
#    interventi aggressivi % = interventi con almeno un'etichetta aggressiva
#    apertura %              = interventi con un'apertura
#    aggressività ricevuta % = interventi degli ALTRI due con almeno
#                              un'etichetta aggressiva rivolta a lui, sul
#                              totale degli interventi degli altri due:
#                              serve a vedere se gli altri si coalizzano
#                              contro qualcuno (es. contro l'unico aggressivo)
#  Si contano solo gli interventi con un testo: un intervento rimasto in
#  silenzio (rifiuto del provider) non vale 0, semplicemente non c'è.
#  L'apertura non si sottrae dall'aggressività (decisione del 6 novembre:
#  nella valutazione a mano compariva nell'83% degli interventi, in entrambe
#  le condizioni, spesso insieme a una minaccia).
#
#  ESEMPI DEL RICERCATORE: oltre alle regole del file JSON, il giudice riceve
#  gli interventi etichettati a mano nella tabella
#  esempi/esempi_aggressivita_v2.xlsx (funzione testo_esempi), raggruppati per
#  partita e in ordine, così si legge anche il contesto. Le partite da cui
#  vengono non vanno usate per verificare il giudice.
#
#  TABELLE (nella cartella del giudice e, se complete, in dati/):
#    interventi  llm_aggressivita_interventi.csv  una riga per intervento giudicato
#    giocatori   llm_aggressivita_giocatori.csv   una riga per giocatore per partita
#  Chiavi con prepara_dati: partita + ruolo + turno, partita + ruolo.
#
#  File necessari nella stessa cartella: llm_comune.py,
#    raccolta_aggressivita_v3.json (le regole del giudice), cartella esempi,
#    S.json, C.json, K.json, cartella "partite", chiavi_api.json
#  Librerie: pip install openai anthropic openpyxl
#  Uso: python raccolta_aggressivita_v3.1.py
# ==============================================================================

import json

import llm_comune as llm

PERSONAGGI = llm.PERSONAGGI


# ==============================================================================
#  IMPOSTAZIONI
# ==============================================================================
GIUDICE = "mistral"              # "mistral", "claude" oppure "gemini" (vedi llm_comune, Sezione 1)
VERSIONE_PROMPT = "v3"           # versione delle regole del giudice: dà il nome alla cartella dei risultati
FILE_PROMPT = f"raccolta_aggressivita_{VERSIONE_PROMPT}.json"
FILE_ESEMPI = "esempi_aggressivita_v2.xlsx"   # nella cartella esempi
RIPETIZIONE = ""                 # "" = esecuzione normale; "_bis" = seconda esecuzione (prova di stabilità)
SOLO_MESSAGGI = False            # True = solo i messaggi, senza chiamare il giudice (nessun costo)

# Quali partite: None = tutte (solo così le tabelle vanno anche in dati/);
# oppure un elenco. Di base 5 partite pilota NON usate negli esempi, per il test.
PARTITE_SCELTE = None

# Le etichette, nell'ordine della tabella, e il loro peso nell'aggressività %.
ETICHETTE_AGGRESSIVE = ["minaccia", "screditamento", "intransigenza", "linguaggio_aggressivo"]
APERTURA = "apertura"
PESI = {"minaccia": 1, "screditamento": 1, "intransigenza": 1, "linguaggio_aggressivo": 1}

COLONNE = {
    "interventi": ["partita", "turno", "ruolo", *ETICHETTE_AGGRESSIVE, APERTURA, "etichette_aggressive",
                   "bersagli", "citazione", "spiegazione"],
    "giocatori": ["partita", "ruolo", "interventi_giudicati", *ETICHETTE_AGGRESSIVE, APERTURA,
                  "aggressivita_pct", "interventi_aggressivi_pct", "apertura_pct", "aggressivita_ricevuta_pct"],
}


# ==============================================================================
#  ESEMPI DEL RICERCATORE
# ==============================================================================
def testo_esempi():
    """
    La tabella di esempi trasformata nel testo che chiude il prompt di
    sistema, più l'insieme delle partite da cui viene. Ogni intervento è
    seguito dal giudizio del ricercatore nello stesso formato della risposta
    richiesta, più la sua nota se c'è. Un intervento con etichette aggressive
    ma senza bersagli non rispetta il formato: resta fuori, e lo si segnala.
    """
    righe = ["ESEMPI DEL RICERCATORE",
             "Interventi pubblici veri di partite di prova, etichettati a mano dal ricercatore, nell'ordine in cui "
             "sono stati detti. Quando un intervento somiglia a un esempio, segui lo stesso criterio."]
    partita_corrente, esclusi = None, []
    for r in llm.leggi_esempi(FILE_ESEMPI):
        aggressivo = any(r[e] == "sì" for e in ETICHETTE_AGGRESSIVE)
        if aggressivo and not r["bersagli"]:
            esclusi.append(f"{r['partita']} {r['codice']}")
            continue
        if r["partita"] != partita_corrente:
            partita_corrente = r["partita"]
            righe += ["", f"Partita di esempio {partita_corrente}"]
        giudizio = {"id": r["codice"], **{e: r[e] == "sì" for e in ETICHETTE_AGGRESSIVE + [APERTURA]},
                    "bersagli": [b.strip() for b in r["bersagli"].split(",") if b.strip()]}
        righe += ["", f"[{r['codice']}] {r['chi parla']}: {r['testo']}", "→ " + json.dumps(giudizio, ensure_ascii=False)]
        if r["nota"]:
            righe.append(f"Nota del ricercatore: {r['nota']}")
    if esclusi:
        print(f"Esempi esclusi (etichette aggressive senza bersagli): {', '.join(esclusi)}")
    partite = {r["partita"] for r in llm.leggi_esempi(FILE_ESEMPI)}
    return "\n".join(righe), partite


# ==============================================================================
#  PASSO 1 — INTERVENTI DA GIUDICARE E MESSAGGIO
# ==============================================================================
def codice(turno, chi):
    """Codice di un intervento: 'T3_K' = turno 3, parla K (un personaggio parla una volta per turno)."""
    return f"T{turno}_{chi}"


def interventi_da_giudicare(turni):
    """
    Gli interventi con un testo, in ordine: [(codice, turno, chi), ...].
    Quelli vuoti (rifiutati dal provider anche al secondo tentativo) non si
    giudicano: nella trascrizione restano come "(silenzio)", senza codice.
    """
    return [(codice(t["turno"], iv["personaggio"]), t["turno"], iv["personaggio"])
            for t in turni for iv in t["interventi"] if (iv.get("testo_pubblico") or "").strip()]


def testo_schede(schede):
    """Ruolo e segreto di ogni personaggio: servono a riconoscere le minacce velate."""
    return "\n".join(f"- {r}: {schede[r]['ruolo']}. Segreto: {schede[r]['segreto_tuo']}" for r in PERSONAGGI)


def testo_trascrizione(turni):
    """
    La trascrizione pubblica, come la leggevano i personaggi: interventi con
    il loro codice e, tra un turno e l'altro, "nessun accordo". L'esito
    dell'ultimo turno non si scrive (non serve a giudicare il tono e direbbe
    come è finita la partita).
    """
    righe = []
    for i, t in enumerate(turni):
        righe += ["", f"=== TURNO {t['turno']} ==="]
        for iv in t["interventi"]:
            testo = (iv.get("testo_pubblico") or "").strip()
            p = iv["personaggio"]
            righe.append(f"[{codice(t['turno'], p)}] {p}: {testo}" if testo else f"{p}: (silenzio)")
        if i < len(turni) - 1:
            righe.append(f"[Esito turno {t['turno']}: nessun accordo]")
    return "\n".join(righe).strip()


def prepara(log, modello):
    """Messaggio della partita (llm_comune, Sezione 5)."""
    messaggio = (modello.replace("{schede}", testo_schede(llm.schede()))
                 .replace("{trascrizione}", testo_trascrizione(log["turni"])))
    return messaggio, interventi_da_giudicare(log["turni"]), None


# ==============================================================================
#  PASSO 2 — CONTROLLO DELLA RISPOSTA
# ==============================================================================
def controlla(dati, interventi):
    """
    Che cosa rende la risposta inutilizzabile; elenco vuoto se va bene.
      - ogni intervento con un codice deve essere giudicato una volta sola;
      - le cinque etichette devono essere true o false;
      - 'bersagli' deve essere una lista di personaggi, senza chi parla.
    Una lista di bersagli non vuota in un intervento senza etichette
    aggressive non è un errore: viene svuotata nelle righe della tabella.
    """
    if not isinstance(dati, dict) or not isinstance(dati.get("interventi"), list):
        return ["la risposta non è un JSON con la lista 'interventi'"]
    attesi = {c: chi for c, _, chi in interventi}
    visti = [str(g.get("id")) for g in dati["interventi"] if isinstance(g, dict)]
    errori = []
    if sorted(visti) != sorted(attesi):
        errori.append(f"interventi giudicati diversi da quelli attesi (mancanti {sorted(set(attesi) - set(visti))}, "
                      f"in più {sorted(set(visti) - set(attesi))}, doppi {sorted({c for c in visti if visti.count(c) > 1})})")
    for g in dati["interventi"]:
        if not isinstance(g, dict) or str(g.get("id")) not in attesi:
            continue
        c = str(g["id"])
        errori += [f"{c}: '{e}' deve essere true o false" for e in ETICHETTE_AGGRESSIVE + [APERTURA]
                   if not isinstance(g.get(e), bool)]
        bersagli = g.get("bersagli")
        if not isinstance(bersagli, list) or any(b not in PERSONAGGI or b == attesi[c] for b in bersagli):
            errori.append(f"{c}: 'bersagli' deve essere una lista di S, C, K senza chi parla")
    return errori


# ==============================================================================
#  PASSO 3 — RIGHE DELLE TABELLE
# ==============================================================================
def si_no(valore):
    return "sì" if valore else "no"


def percentuale(numeratore, denominatore):
    """Percentuale con una cifra decimale; vuota se il denominatore è 0."""
    return round(100 * numeratore / denominatore, 1) if denominatore else ""


def righe_di(gid, log, interventi, dati):
    """Le righe di una partita: una per intervento giudicato, poi una per giocatore con le percentuali."""
    giudizi = {str(g["id"]): g for g in dati["interventi"]}
    righe_iv = []
    for c, turno, chi in interventi:
        g = giudizi[c]
        n_aggr = sum(bool(g[e]) for e in ETICHETTE_AGGRESSIVE)
        righe_iv.append({"partita": gid, "turno": turno, "ruolo": chi,
                         **{e: si_no(g[e]) for e in ETICHETTE_AGGRESSIVE + [APERTURA]},
                         "etichette_aggressive": n_aggr,
                         # senza aggressività, nessun bersaglio
                         "bersagli": ", ".join(sorted(set(g["bersagli"]))) if n_aggr else "",
                         "citazione": g.get("citazione", ""), "spiegazione": g.get("spiegazione", "")})

    somma_pesi = sum(PESI.values())
    righe_gio = []
    for chi in PERSONAGGI:
        suoi = [r for r in righe_iv if r["ruolo"] == chi]
        altri = [r for r in righe_iv if r["ruolo"] != chi]
        if not suoi:
            continue                                  # sempre in silenzio: nessun dato
        punti = sum(PESI[e] for r in suoi for e in ETICHETTE_AGGRESSIVE if r[e] == "sì")
        righe_gio.append({
            "partita": gid, "ruolo": chi, "interventi_giudicati": len(suoi),
            **{e: sum(r[e] == "sì" for r in suoi) for e in ETICHETTE_AGGRESSIVE + [APERTURA]},
            "aggressivita_pct": percentuale(punti, somma_pesi * len(suoi)),
            "interventi_aggressivi_pct": percentuale(sum(r["etichette_aggressive"] > 0 for r in suoi), len(suoi)),
            "apertura_pct": percentuale(sum(r[APERTURA] == "sì" for r in suoi), len(suoi)),
            "aggressivita_ricevuta_pct": percentuale(sum(chi in r["bersagli"].split(", ") for r in altri), len(altri)),
        })
    return {"interventi": righe_iv, "giocatori": righe_gio}


def main():
    esempi, partite_esempi = testo_esempi()
    tabelle = llm.raccogli("aggressivita", VERSIONE_PROMPT, FILE_PROMPT, GIUDICE, COLONNE,
                           prepara, controlla, righe_di, PARTITE_SCELTE, SOLO_MESSAGGI, RIPETIZIONE,
                           esempi, partite_esempi)
    if not SOLO_MESSAGGI:
        for e in ETICHETTE_AGGRESSIVE + [APERTURA]:
            print(f"   {e:<24} {sum(r[e] == 'sì' for r in tabelle['interventi'])} interventi")


if __name__ == "__main__":
    main()
