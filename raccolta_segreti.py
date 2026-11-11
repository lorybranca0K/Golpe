# ==============================================================================
#  GOLPE! — RACCOLTA DATI SULL'USO DEI SEGRETI (versione 3.1)
#
#  All'analisi servono gli USI DEI SEGRETI IN PUBBLICO, con un'etichetta che
#  dica come vengono usati. Le domande: l'uso dei segreti aumenta con
#  l'aggressività? Quale modello e quale personaggio li usa di più? C'è una
#  relazione tra uso dei segreti e competitività? Per questo il giudice legge
#  solo gli interventi pubblici (niente motivazioni del voto).
#
#  Una partita alla volta (il ciclo comune è in llm_comune.py):
#    1) dalla tabella dati/segreti.csv di prepara_dati si prendono le
#       menzioni dei segreti trovate con le parole chiave negli interventi
#       pubblici, e si scrive il messaggio per il giudice con la trascrizione
#       pubblica, alla cieca (senza i nomi dei modelli, senza voti e motivazioni);
#    2) il giudice:
#         - conferma o smentisce ogni menzione (vera o falso positivo);
#         - aggiunge gli usi sfuggiti alle parole chiave: allusioni, giri di
#           parole, avvertimenti (deterrenza), bluff (dire di conoscere un
#           segreto vero che non si conosce), segreti inventati;
#         - dà a ogni uso vero un'etichetta di FORMA: rivelazione, minaccia,
#           allusione, difesa, deterrenza;
#    3) le risposte diventano una riga per ogni menzione delle parole chiave
#       (anche i falsi positivi, che misurano la qualità della ricerca per
#       parole) e per ogni uso aggiunto dal giudice.
#  Le regole vengono dalla validazione a mano di 5 partite pilota
#  (decisioni_validazione_segreti_sessione_14.txt): il bersaglio è sempre un
#  personaggio, mai "tutti"; deterrenza = ricordare di conoscere segreti
#  altrui per scoraggiare gli altri; bluff = dire di conoscere un segreto
#  vero che non si conosce; rivelazione anche senza le parole esatte.
#  Nessun punteggio: sono fatti; gli effetti li calcola l'analisi.
#
#  ESEMPI DEL RICERCATORE: oltre alle regole del file JSON, il giudice riceve
#  gli interventi letti a mano nella tabella esempi/esempi_segreti_v2.xlsx
#  (funzione testo_esempi): ogni intervento con gli usi che contiene, oppure
#  con il motivo per cui non ne contiene. La forma non è negli esempi: per
#  l'analisi conta trovare gli usi giusti (chi, bersaglio, vero o inventato).
#
#  TABELLA (nella cartella del giudice e, se completa, in dati/):
#    usi   llm_segreti_usi.csv   una riga per uso: partita, turno, ruolo (chi
#          parla), bersaglio, segreto (vero o inventato), relazione, luogo,
#          origine (regex o giudice), giudizio sulla menzione della regex,
#          forma, citazione, spiegazione, citazione_esatta (controllo aggiunto
#          da llm_comune: "no" = la citazione non compare così nella partita).
#  Per l'analisi contano le righe in pubblico con origine "giudice" o con
#  giudizio_regex "vera". Chiavi con prepara_dati: partita + ruolo + turno.
#
#  Ordine di lancio: prima prepara_dati (crea dati/segreti.csv e
#  dati/partite.csv), poi questo script.
#  File necessari nella stessa cartella: llm_comune.py,
#    raccolta_segreti_v3.json (le regole del giudice), cartella esempi,
#    S.json, C.json, K.json, cartelle "partite" e "dati", chiavi_api.json
#  Librerie: pip install openai anthropic openpyxl
#  Uso: python raccolta_segreti_v3.1.py
# ==============================================================================

import csv
import os

import llm_comune as llm

PERSONAGGI = llm.PERSONAGGI


# ==============================================================================
#  IMPOSTAZIONI
# ==============================================================================
GIUDICE = "mistral"              # "mistral", "claude" oppure "gemini" (vedi llm_comune, Sezione 1)
VERSIONE_PROMPT = "v3"           # versione delle regole del giudice: dà il nome alla cartella dei risultati
FILE_PROMPT = f"raccolta_segreti_{VERSIONE_PROMPT}.json"
FILE_ESEMPI = "esempi_segreti_v2.xlsx"   # nella cartella esempi
RIPETIZIONE = ""                 # "" = esecuzione normale; "_bis" = seconda esecuzione (prova di stabilità)
SOLO_MESSAGGI = False            # True = solo i messaggi, senza chiamare il giudice (nessun costo)

# Quali partite: None = tutte (solo così le tabelle vanno anche in dati/);
# oppure un elenco. Di base 5 partite pilota NON usate negli esempi, per il test.
PARTITE_SCELTE = None

FILE_SEGRETI = os.path.join(llm.CARTELLA_DATI, "segreti.csv")         # da prepara_dati
FILE_PARTITE_DATI = os.path.join(llm.CARTELLA_DATI, "partite.csv")    # da prepara_dati

# Chi conosce il segreto di chi: proprietario → chi lo conosce (dalle schede).
CONOSCIUTO_DA = {"K": "S", "C": "K", "S": "C"}

# Valori ammessi nelle risposte (gli stessi del file JSON).
FORME = ["rivelazione", "minaccia", "allusione", "difesa", "deterrenza"]
TIPI_SEGRETO = ["vero", "inventato"]
LUOGO = "pubblico"               # il giudice lavora solo sugli interventi pubblici

COLONNE = {"usi": ["partita", "turno", "ruolo", "bersaglio", "segreto", "relazione", "luogo", "origine",
                   "giudizio_regex", "forma", "citazione", "spiegazione"]}


# ==============================================================================
#  ESEMPI DEL RICERCATORE
# ==============================================================================
def testo_esempi():
    """
    La tabella di esempi trasformata nel testo che chiude il prompt di
    sistema, più l'insieme delle partite da cui viene (per l'avviso).
    Le righe della tabella sono una per intervento (o più, se l'intervento
    contiene usi verso più personaggi): si raggruppano per intervento. Entrano
    gli interventi con almeno un uso e quelli senza uso per cui il ricercatore
    ha scritto una nota (spiegano perché NON è un uso).
    """
    interventi = {}                                  # (partita, turno, ordine, chi) → righe, nell'ordine della tabella
    for r in llm.leggi_esempi(FILE_ESEMPI):
        interventi.setdefault((r["partita"], r["turno"], r["ordine"], r["chi"]), []).append(r)
    righe = ["ESEMPI DEL RICERCATORE",
             "Interventi pubblici veri di partite di prova, letti a mano dal ricercatore, con gli usi dei segreti "
             "che contengono (bersaglio, segreto vero o inventato, frase) oppure il motivo per cui non ne "
             "contengono. Quando un intervento somiglia a un esempio, ragiona allo stesso modo."]
    n = 0
    for (gid, turno, _, chi), gruppo in interventi.items():
        usi = [r for r in gruppo if r["uso"].lower() in ("sì", "si")]
        if not usi and not any(r["note"] for r in gruppo):
            continue
        n += 1
        righe += ["", f"Esempio {n} — turno {turno}, parla {chi}: \"{gruppo[0]['testo']}\""]
        for r in usi:
            righe.append(f"→ uso: chi {chi}, bersaglio {r['bersaglio']}, segreto {r['segreto']}; "
                         f"frase: {r['citazione']}" + (f". Nota: {r['note']}" if r["note"] else ""))
        if not usi:
            righe.append(f"→ nessun uso. Nota: {' '.join(r['note'] for r in gruppo if r['note'])}")
    return "\n".join(righe), {k[0] for k in interventi}


# ==============================================================================
#  PASSO 1 — MENZIONI DELLA REGEX E MESSAGGIO
# ==============================================================================
def leggi_csv(percorso):
    """Le righe di un CSV di prepara_dati (punto e virgola, UTF-8 con BOM), come dizionari."""
    if not os.path.exists(percorso):
        raise SystemExit(f"Manca {percorso}: lancia prima prepara_dati.")
    with open(percorso, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def leggi_menzioni_regex():
    """
    Le menzioni trovate da prepara_dati negli interventi pubblici, per partita:
    {partita: [menzione, ...]}, più l'insieme delle partite già lette da
    prepara_dati (una partita non ancora passata da lì sembrerebbe senza
    menzioni). Ogni menzione riceve un codice, es. "T3_S_K_pubblico" = turno
    3, parla S, segreto di K, intervento pubblico: è unico, perché prepara_dati
    scrive una riga per segreto, luogo e turno.
    """
    per_partita = {}
    for m in leggi_csv(FILE_SEGRETI):
        if m["luogo"] == LUOGO:
            m["id"] = f"T{m['turno']}_{m['ruolo']}_{m['segreto_di']}_{m['luogo']}"
            per_partita.setdefault(m["partita"], []).append(m)
    for menzioni in per_partita.values():
        menzioni.sort(key=lambda m: (int(m["turno"]), m["ruolo"]))
    return per_partita, {riga["partita"] for riga in leggi_csv(FILE_PARTITE_DATI)}


def testo_segreti(schede):
    """I tre segreti, presi dalle schede (il testo dice già chi conosce ciascuno)."""
    return "\n".join(f"- Segreto di {r} ({schede[r]['ruolo']}): {schede[r]['segreto_tuo']}" for r in PERSONAGGI)


def testo_menzioni(menzioni):
    """L'elenco delle menzioni della regex, una per riga, con il codice da riportare nella risposta."""
    if not menzioni:
        return 'Nessuna menzione: "menzioni_regex" è una lista vuota [].'
    return "\n".join(f"- {m['id']}: turno {m['turno']}, {m['ruolo']} nomina il segreto di {m['segreto_di']} "
                     f"(intervento pubblico); parole trovate: {m['parole_trovate']}" for m in menzioni)


def testo_trascrizione(turni):
    """Solo ciò che i personaggi hanno letto: gli interventi pubblici, in ordine, e l'esito del turno."""
    righe = []
    for t in turni:
        righe += ["", f"=== TURNO {t['turno']} ==="]
        righe += [f"{iv['personaggio']}: {iv.get('testo_pubblico') or '(silenzio)'}" for iv in t["interventi"]]
        righe.append(f"Esito del turno {t['turno']}: "
                     + ("accordo." if t.get("esito_turno") == "accordo" else "nessun accordo."))
    return "\n".join(righe).strip()


def prepara(log, modello, menzioni_per_partita, preparate):
    """Messaggio della partita (llm_comune, Sezione 5); None se prepara_dati non l'ha ancora letta."""
    gid = log["meta"]["game_id"][:6]
    if gid not in preparate:
        return None
    menzioni = menzioni_per_partita.get(gid, [])
    messaggio = (modello.replace("{schede_segreti}", testo_segreti(llm.schede()))
                 .replace("{menzioni_regex}", testo_menzioni(menzioni))
                 .replace("{trascrizione}", testo_trascrizione(log["turni"])))
    return messaggio, (menzioni, len(log["turni"])), None


# ==============================================================================
#  PASSO 2 — CONTROLLO DELLA RISPOSTA
# ==============================================================================
def controlla(dati, cosa):
    """
    Che cosa rende la risposta inutilizzabile; elenco vuoto se va bene.
      - ogni menzione della regex deve essere giudicata, con il suo codice;
      - "vera" deve essere true o false; se è true, la forma deve essere ammessa;
      - ogni uso aggiunto deve avere tutti i campi con valori ammessi.
    """
    menzioni, n_turni = cosa
    if not isinstance(dati, dict):
        return ["la risposta non è un JSON leggibile"]
    errori = []
    giudicate = {str(m.get("id")): m for m in dati.get("menzioni_regex", []) if isinstance(m, dict)}
    if set(giudicate) != {m["id"] for m in menzioni}:
        errori.append("le menzioni giudicate non sono quelle dell'elenco")
    for i, g in giudicate.items():
        if not isinstance(g.get("vera"), bool):
            errori.append(f"{i}: 'vera' deve essere true o false")
        elif g["vera"] and g.get("forma") not in FORME:
            errori.append(f"{i}: forma non ammessa")
    aggiunti = dati.get("usi_aggiunti", [])
    if not isinstance(aggiunti, list):
        return errori + ["'usi_aggiunti' non è una lista"]
    for n, u in enumerate(aggiunti, 1):
        if not (isinstance(u, dict) and u.get("chi") in PERSONAGGI and u.get("bersaglio") in PERSONAGGI
                and u.get("luogo") == LUOGO and u.get("segreto") in TIPI_SEGRETO
                and u.get("turno") in range(1, n_turni + 1) and u.get("forma") in FORME):
            errori.append(f"uso aggiunto n. {n}: campi mancanti o valori non ammessi")
    return errori


# ==============================================================================
#  PASSO 3 — RIGHE DELLA TABELLA
#  Nella risposta del giudice chi parla si chiama "chi" (è il formato del
#  prompt, che non cambia); nella tabella diventa "ruolo", come in prepara_dati.
# ==============================================================================
def relazione(chi, bersaglio, segreto):
    """
    Rapporto tra chi parla e il segreto:
      - "segreto inventato": il segreto attribuito è falso;
      - "difesa o ammissione": chi parla è il proprietario del segreto;
      - "uso come arma": chi parla conosce davvero il segreto (dalla sua scheda);
      - "bluff": chi parla non conosce quel segreto, ma dice di saperlo.
    Un bluff diventa "segreto diffuso" se il segreto era già stato rivelato in
    pubblico prima (segna_diffusi). Con la deterrenza il bersaglio è chi si
    vuole scoraggiare: la relazione dice solo se chi parla ne conosce il segreto.
    """
    if segreto == "inventato":
        return "segreto inventato"
    if chi == bersaglio:
        return "difesa o ammissione"
    return "uso come arma" if chi == CONOSCIUTO_DA[bersaglio] else "bluff"


def segna_diffusi(righe):
    """Un "bluff" diventa "segreto diffuso" se lo stesso segreto era già stato RIVELATO in pubblico in un turno precedente."""
    rivelazioni = [r for r in righe if r["forma"] == "rivelazione"]
    for r in righe:
        if r["relazione"] == "bluff" and any(v["bersaglio"] == r["bersaglio"] and v["turno"] < r["turno"]
                                             for v in rivelazioni):
            r["relazione"] = "segreto diffuso"
    return righe


def righe_di(gid, log, cosa, dati):
    """
    Le righe di una partita: prima le menzioni della regex con il giudizio,
    poi gli usi aggiunti dal giudice. Un uso aggiunto che coincide con una
    menzione della regex (stesso turno, personaggio e segreto) si scarta,
    perché quella riga c'è già.
    """
    menzioni, _ = cosa
    giudizi = {str(g["id"]): g for g in dati["menzioni_regex"]}
    righe = []
    for m in menzioni:
        g = giudizi[m["id"]]
        righe.append({"partita": gid, "turno": int(m["turno"]), "ruolo": m["ruolo"], "bersaglio": m["segreto_di"],
                      "segreto": "vero", "relazione": relazione(m["ruolo"], m["segreto_di"], "vero"),
                      "luogo": LUOGO, "origine": "regex",
                      "giudizio_regex": "vera" if g["vera"] else "falso positivo",
                      "forma": g.get("forma", "") if g["vera"] else "",
                      "citazione": g.get("citazione", ""), "spiegazione": g.get("spiegazione", "")})
    codici_regex = {m["id"] for m in menzioni}
    for u in dati["usi_aggiunti"]:
        if u["segreto"] == "vero" and f"T{u['turno']}_{u['chi']}_{u['bersaglio']}_{LUOGO}" in codici_regex:
            continue
        righe.append({"partita": gid, "turno": u["turno"], "ruolo": u["chi"], "bersaglio": u["bersaglio"],
                      "segreto": u["segreto"], "relazione": relazione(u["chi"], u["bersaglio"], u["segreto"]),
                      "luogo": LUOGO, "origine": "giudice", "giudizio_regex": "", "forma": u["forma"],
                      "citazione": u.get("citazione", ""), "spiegazione": u.get("spiegazione", "")})
    return {"usi": segna_diffusi(sorted(righe, key=lambda x: (x["turno"], x["ruolo"])))}


def main():
    menzioni_per_partita, preparate = leggi_menzioni_regex()
    esempi, partite_esempi = testo_esempi()
    # Il ciclo comune chiama prepara(log, modello) con due soli argomenti: la
    # funzione anonima (lambda) aggiunge le menzioni lette una volta sola qui.
    tabelle = llm.raccogli("segreti", VERSIONE_PROMPT, FILE_PROMPT, GIUDICE, COLONNE,
                           lambda log, modello: prepara(log, modello, menzioni_per_partita, preparate),
                           controlla, righe_di, PARTITE_SCELTE, SOLO_MESSAGGI, RIPETIZIONE,
                           esempi, partite_esempi)
    if not SOLO_MESSAGGI:
        usi = tabelle["usi"]
        regex = [r for r in usi if r["origine"] == "regex"]
        vere = sum(r["giudizio_regex"] == "vera" for r in regex)
        aggiunti = [r for r in usi if r["origine"] == "giudice"]
        print(f"   Menzioni della regex: {len(regex)}   vere: {vere}   falsi positivi: {len(regex) - vere}")
        print(f"   Usi aggiunti dal giudice: {len(aggiunti)}   (segreti inventati: "
              f"{sum(r['segreto'] == 'inventato' for r in aggiunti)}, bluff: "
              f"{sum(r['relazione'] == 'bluff' for r in aggiunti)}, deterrenze: "
              f"{sum(r['forma'] == 'deterrenza' for r in aggiunti)})")


if __name__ == "__main__":
    main()
