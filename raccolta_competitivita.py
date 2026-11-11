# ==============================================================================
#  GOLPE! — RACCOLTA DATI SULLA COMPETITIVITÀ (versione 3.1)
#
#  Prepara i dati che l'analisi della competitività non può calcolare da
#  sola con Python, perché servono a leggere il SENSO dei testi. Li chiede a
#  un modello GIUDICE, una partita alla volta (il ciclo comune è in
#  llm_comune.py):
#    1) dal log della partita Python ricava:
#         - i CEDIMENTI: i turni in cui un giocatore che si votava vota un
#           altro (o "nessuno"), sia nella TRATTATIVA (turni senza accordo)
#           sia nel TURNO DECISIVO (il voto che elegge il leader);
#         - i SOPRAVVISSUTI: chi resta vivo senza essere eletto;
#       e scrive il messaggio per il giudice, alla cieca (senza i nomi dei
#       modelli, la condizione di aggressività e il ragionamento);
#    2) il giudice dice due cose sole:
#         - il MOTIVO di ogni cedimento: resa, patto, riserva strategica,
#           non classificabile;
#         - il GUADAGNO di ogni sopravvissuto rispetto agli obiettivi della
#           sua scheda: perde potere, conserva, guadagno parziale, guadagno forte;
#       ogni giudizio con una citazione dal testo e una spiegazione breve;
#    3) i giudizi diventano PUNTI, che usa l'analisi della competitività:
#         cedimenti (comportamento): resa e non classificabile -2, patto -1,
#                                    riserva strategica -0,5
#         esito:                     vince 100, guadagno forte 60, guadagno
#                                    parziale 50, conserva 40, perde potere 30,
#                                    giustiziato 0
#       "vince" e "giustiziato" li scrive Python: non serve un giudice.
#       Una partita senza cedimenti e senza sopravvissuti non costa nessuna
#       chiamata.
#  I cedimenti del turno decisivo vengono raccolti (colonna "fase"), ma se e
#  come pesano nel punteggio lo decide l'analisi: il turno decisivo lo
#  racconta già il guadagno, e contarlo due volte va evitato.
#
#  ESEMPI DEL RICERCATORE: oltre alle regole del file JSON, il giudice riceve
#  i casi classificati a mano nelle tabelle esempi/esempi_cedimenti_v3.xlsx e
#  esempi/esempi_esito_v4.xlsx (funzione testo_esempi). Le partite da cui
#  vengono non vanno usate per verificare il giudice.
#
#  TABELLE (nella cartella del giudice e, se complete, in dati/):
#    cedimenti   llm_competitivita_cedimenti.csv   una riga per cedimento:
#                partita, ruolo, turno, fase, etichetta, punti, citazione,
#                spiegazione
#    giocatori   llm_competitivita_giocatori.csv   una riga per personaggio per
#                partita: partita, ruolo, guadagno (o vince / giustiziato),
#                punti dell'esito, citazione, spiegazione
#  Modello, condizione, voti e motivazioni sono nelle tabelle di prepara_dati
#  (chiavi: partita + ruolo + turno, partita + ruolo).
#
#  File necessari nella stessa cartella: llm_comune.py,
#    raccolta_competitivita_v3.json (le regole del giudice), cartella esempi,
#    S.json, C.json, K.json, cartella "partite", chiavi_api.json
#  Librerie: pip install openai anthropic openpyxl
#  Uso: python raccolta_competitivita_v3.1.py
# ==============================================================================

import re

import llm_comune as llm

PERSONAGGI = llm.PERSONAGGI


# ==============================================================================
#  IMPOSTAZIONI
# ==============================================================================
GIUDICE = "mistral"              # "mistral", "claude" oppure "gemini" (vedi llm_comune, Sezione 1)
VERSIONE_PROMPT = "v3"           # versione delle regole del giudice: dà il nome alla cartella dei risultati
FILE_PROMPT = f"raccolta_competitivita_{VERSIONE_PROMPT}.json"
FILE_ESEMPI_CEDIMENTI = "esempi_cedimenti_v3.xlsx"   # nella cartella esempi
FILE_ESEMPI_ESITO = "esempi_esito_v4.xlsx"
RIPETIZIONE = ""                 # "" = esecuzione normale; "_bis" = seconda esecuzione (prova di stabilità)

# True = scrive solo i messaggi, senza chiamare il giudice (nessun costo):
# serve a controllare che cosa leggerà. Al primo lancio conviene True.
SOLO_MESSAGGI = False

# Quali partite: None = tutte (solo così le tabelle vanno anche in dati/);
# oppure un elenco. Di base 5 partite pilota NON usate negli esempi, per il test.
PARTITE_SCELTE = None

# Punti (decisioni del 3 e del 4 novembre).
PUNTI_CEDIMENTO = {"resa": -2, "non classificabile": -2, "patto": -1, "riserva strategica": -0.5}
LIVELLI_SOPRAVVISSUTI = {"perde potere": 30, "conserva": 40, "guadagno parziale": 50, "guadagno forte": 60}
PUNTI_ESITO = {"vince": 100, "giustiziato": 0, **LIVELLI_SOPRAVVISSUTI}

# Colonne delle tabelle, nell'ordine.
COLONNE = {
    "cedimenti": ["partita", "ruolo", "turno", "fase", "etichetta", "punti_comportamento", "citazione", "spiegazione"],
    "giocatori": ["partita", "ruolo", "guadagno", "punti_esito", "citazione", "spiegazione"],
}


# ==============================================================================
#  ESEMPI DEL RICERCATORE
# ==============================================================================
def testo_esempi():
    """
    Le due tabelle di esempi trasformate nel testo che chiude il prompt di
    sistema, più l'insieme delle partite da cui vengono (per l'avviso).
    Per ogni cedimento: chi, quando, motivazione, offerta pubblica e leva
    (se il ricercatore le ha indicate), etichetta e il suo perché.
    Per ogni partita con sopravvissuti: esito, gli ultimi due interventi
    pubblici dell'eletto (dove stanno di solito le offerte finali), poi per
    ogni sopravvissuto livello e il suo perché.
    """
    cedimenti = llm.leggi_esempi(FILE_ESEMPI_CEDIMENTI)
    esiti = llm.leggi_esempi(FILE_ESEMPI_ESITO)
    righe = ["ESEMPI DEL RICERCATORE",
             "Casi veri di partite di prova, classificati a mano dal ricercatore. Mostrano come applicare le "
             "regole: quando un caso somiglia a un esempio, ragiona allo stesso modo.", "", "Cedimenti"]
    for n, e in enumerate(cedimenti, start=1):
        righe += ["", f"Esempio {n} — {e['ruolo']}_T{e['turno']} ({e['fase']}): {e['ruolo']} vota {e['voto']}.",
                  f"Motivazione del voto: \"{e['motivazione del voto']}\""]
        if e["offerta pubblica accettata"]:
            righe.append(f"Offerta pubblica accettata: {e['offerta pubblica accettata']}")
        if e["leva o piano futuro"]:
            righe.append(f"Leva o piano per il futuro dichiarato: {e['leva o piano futuro']}")
        righe.append(f"→ etichetta: \"{e['etichetta']}\". Perché: {e['spiegazione']}")
    righe += ["", "Guadagno dei sopravvissuti"]
    per_partita = {}                                 # partita → righe della tabella, nell'ordine
    for e in esiti:
        per_partita.setdefault(e["partita"], []).append(e)
    for n, gruppo in enumerate(per_partita.values(), start=1):
        e = gruppo[0]
        # La colonna ha gli interventi dell'eletto nella forma "T1: ...", "T2: ...": si divide prima di
        # ogni "T<numero>:" a inizio riga (dentro un intervento ci possono essere altre righe vuote).
        interventi = re.split(r"\n+(?=T\d+: )", e["interventi pubblici dell'eletto"].strip())
        righe += ["", f"Esempio {n} — {e['esito della partita']}. "
                      f"Sopravvissuti: {', '.join(x['ruolo (sopravvissuto)'] for x in gruppo)}.",
                  f"Ultimi interventi pubblici dell'eletto ({e['eletto']}):", *interventi[-2:]]
        for x in gruppo:
            if x.get("citazione (facoltativa)"):
                righe.append(f"Frase decisiva per {x['ruolo (sopravvissuto)']}: \"{x['citazione (facoltativa)']}\"")
            righe.append(f"→ guadagno di {x['ruolo (sopravvissuto)']}: \"{x['guadagno']}\". Perché: "
                         f"{x['spiegazione (tua analisi)'] or 'mantiene il proprio apparato, senza garanzie o poteri in più.'}")
    partite = {e["partita"] for e in cedimenti} | {e["partita"] for e in esiti}
    return "\n".join(righe), partite


# ==============================================================================
#  PASSO 1 — CHE COSA GIUDICARE E MESSAGGIO
# ==============================================================================
def sopravvissuti(esito):
    """Chi sopravvive senza essere eletto: i due non eletti se c'è accordo, nessuno altrimenti."""
    return [r for r in PERSONAGGI if r != esito["vincitore"]] if esito.get("unanimita") else []


def trova_cedimenti(turni, esito):
    """
    Gli atti di cedere: un turno in cui il giocatore vota un altro o "nessuno"
    mentre nel suo voto valido precedente si era votato (o è il turno 1).
    Restare ceduti non è un nuovo atto. Si saltano i turni bloccati dal
    provider (voto non valido per un rifiuto: non è una scelta di gioco).
    Fase: "turno decisivo" se è il turno dell'accordo, altrimenti "trattativa".
    """
    decisivo = esito["turno"] if esito.get("unanimita") else None
    cedimenti = []
    for r in PERSONAGGI:
        prima_per_se = True
        for t in turni:
            v = t["voti"].get(r, {})
            bloccato = (v.get("meta") or {}).get("bloccato") or any(
                (iv.get("meta") or {}).get("bloccato") for iv in t["interventi"] if iv["personaggio"] == r)
            if not v.get("voto") or (bloccato and not v.get("voto_valido", True)):
                continue
            if v["voto"] != r and prima_per_se:
                cedimenti.append({"id": f"{r}_T{t['turno']}", "ruolo": r, "turno": t["turno"], "voto": v["voto"],
                                  "fase": "turno decisivo" if t["turno"] == decisivo else "trattativa"})
            prima_per_se = v["voto"] == r
    return sorted(cedimenti, key=lambda c: (c["turno"], c["ruolo"]))


def testo_schede(schede, obiettivi):
    """Le tre schede dei personaggi, con il solo obiettivo secondario della partita."""
    return "\n\n".join(
        f"{r} — {s['ruolo']}\n  Chi è: {s['chi_sei']}\n  Risorsa: {s['risorsa']}\n"
        f"  Il suo segreto: {s['segreto_tuo']}\n  Il segreto che conosce: {s['segreto_altrui']}\n"
        f"  Obiettivo principale: diventare il nuovo Supremo Leader.\n"
        f"  Obiettivo secondario: {s['obiettivo_secondario'][obiettivi]}"
        for r, s in schede.items())


def testo_trascrizione(turni):
    """Per ogni turno: interventi pubblici (ciò che hanno letto gli altri), voti con motivazioni, esito."""
    righe = []
    for t in turni:
        righe += ["", f"=== TURNO {t['turno']} ===", "Interventi pubblici:"]
        righe += [f"{iv['personaggio']}: {iv.get('testo_pubblico') or '(silenzio)'}" for iv in t["interventi"]]
        righe.append("Voti segreti e motivazioni private (nessun giocatore vede quelli degli altri):")
        righe += [f"{r} vota {t['voti'][r]['voto']} — motivazione: "
                  f"\"{(t['voti'][r].get('motivazione') or '').lstrip(' -–—:')}\"" for r in PERSONAGGI]
        righe.append(f"Esito del turno {t['turno']}: "
                     + ("accordo." if t.get("esito_turno") == "accordo" else "nessun accordo."))
    return "\n".join(righe).strip()


def prepara(log, modello):
    """
    Messaggio della partita (llm_comune, Sezione 5). I segnaposto si riempiono
    con .replace() e non con .format(): le graffe nei testi non sono segnaposto.
    Senza cedimenti e senza sopravvissuti la risposta è già nota: niente chiamata.
    """
    meta, esito, turni = log["meta"], log["esito"], log["turni"]
    cedimenti, vivi = trova_cedimenti(turni, esito), sopravvissuti(esito)
    if esito.get("unanimita"):
        esito_txt = (f"Accordo al turno {esito['turno']}: {esito['vincitore']} è eletto nuovo Supremo Leader. "
                     f"Sopravvivono {vivi[0]} e {vivi[1]}.")
    else:
        esito_txt = f"Nessun accordo entro il turno {esito['turno']}: tutti vengono giustiziati."
    elenco = "\n".join(f"- {c['id']}: {c['ruolo']}, turno {c['turno']} ({c['fase']}), vota {c['voto']}"
                       for c in cedimenti)
    messaggio = (modello.replace("{schede_personaggi}", testo_schede(llm.schede(), meta.get("obiettivi", "ciclici")))
                 .replace("{esito}", esito_txt)
                 .replace("{elenco_cedimenti}", elenco or "Nessuno: \"cedimenti\" è una lista vuota [].")
                 .replace("{elenco_sopravvissuti}", ", ".join(vivi) or "Nessuno: \"guadagni\" è un oggetto vuoto {}.")
                 .replace("{trascrizione}", testo_trascrizione(turni)))
    pronta = {"cedimenti": [], "guadagni": {}} if not cedimenti and not vivi else None
    return messaggio, (cedimenti, vivi), pronta


# ==============================================================================
#  PASSO 2 — CONTROLLO DELLA RISPOSTA
# ==============================================================================
def controlla(dati, cosa):
    """
    Che cosa rende la risposta inutilizzabile; elenco vuoto se va bene:
    cedimenti mancanti o in più, sopravvissuti mancanti o in più, etichette
    o livelli non ammessi.
    """
    cedimenti, vivi = cosa
    if not isinstance(dati, dict) or not isinstance(dati.get("cedimenti"), list) \
            or not isinstance(dati.get("guadagni"), dict):
        return ["la risposta non è un JSON con 'cedimenti' (lista) e 'guadagni' (oggetto)"]
    errori = []
    giudicati = {str(c.get("id")): c for c in dati["cedimenti"] if isinstance(c, dict)}
    if set(giudicati) != {c["id"] for c in cedimenti}:
        errori.append("i cedimenti giudicati non sono quelli dell'elenco")
    errori += [f"{i}: etichetta non ammessa" for i, c in giudicati.items() if c.get("etichetta") not in PUNTI_CEDIMENTO]
    if set(dati["guadagni"]) != set(vivi):
        errori.append("i personaggi valutati non sono i sopravvissuti dell'elenco")
    errori += [f"{r}: livello di guadagno non ammesso" for r, g in dati["guadagni"].items()
               if not isinstance(g, dict) or g.get("guadagno") not in LIVELLI_SOPRAVVISSUTI]
    return errori


# ==============================================================================
#  PASSO 3 — RIGHE DELLE TABELLE
# ==============================================================================
def righe_di(gid, log, cosa, dati):
    """Le righe delle due tabelle di una partita: giudizio e punti uno accanto all'altro."""
    cedimenti, _ = cosa
    giudizi = {str(c["id"]): c for c in dati["cedimenti"]}
    righe_ced = [{"partita": gid, "ruolo": c["ruolo"], "turno": c["turno"], "fase": c["fase"],
                  "etichetta": giudizi[c["id"]]["etichetta"],
                  "punti_comportamento": PUNTI_CEDIMENTO[giudizi[c["id"]]["etichetta"]],
                  "citazione": giudizi[c["id"]].get("citazione", ""),
                  "spiegazione": giudizi[c["id"]].get("spiegazione", "")} for c in cedimenti]
    righe_gio = []
    for r in PERSONAGGI:
        g = dati["guadagni"].get(r, {})
        if r in dati["guadagni"]:
            livello = g["guadagno"]
        else:
            livello = "vince" if log["esito"].get("unanimita") else "giustiziato"
        righe_gio.append({"partita": gid, "ruolo": r, "guadagno": livello, "punti_esito": PUNTI_ESITO[livello],
                          "citazione": g.get("citazione", ""), "spiegazione": g.get("spiegazione", "")})
    return {"cedimenti": righe_ced, "giocatori": righe_gio}


def main():
    esempi, partite_esempi = testo_esempi()
    tabelle = llm.raccogli("competitivita", VERSIONE_PROMPT, FILE_PROMPT, GIUDICE, COLONNE,
                           prepara, controlla, righe_di, PARTITE_SCELTE, SOLO_MESSAGGI, RIPETIZIONE,
                           esempi, partite_esempi)
    if not SOLO_MESSAGGI:
        for etichetta in PUNTI_CEDIMENTO:
            print(f"   {etichetta:<20} {sum(r['etichetta'] == etichetta for r in tabelle['cedimenti'])} cedimenti")


if __name__ == "__main__":
    main()
