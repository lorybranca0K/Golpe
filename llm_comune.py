# ==============================================================================
#  GOLPE! — PARTI COMUNI DEI RACCOGLITORI DI DATI LLM (llm_comune, versione 3.1)
#
#  È un MODULO: un file di funzioni che gli altri script importano
#  ("import llm_comune as llm"), non uno script da lanciare. Il nome del file
#  non porta la versione perché gli altri script lo importano con questo nome:
#  la versione è scritta qui sopra. Lo usano:
#    raccolta_competitivita_v3.1.py motivo dei cedimenti e guadagno dei sopravvissuti
#    raccolta_segreti_v3.1.py       usi dei segreti negli interventi pubblici
#    raccolta_aggressivita_v3.1.py  aggressività e apertura di ogni intervento
#    e gli script di confronto (validazione a mano, stabilità, confronto tra giudici).
#  Qui c'è tutto ciò che i raccoglitori fanno nello stesso modo; ogni
#  raccoglitore contiene solo ciò che è suo: che cosa chiedere al giudice,
#  come controllare la risposta, quali tabelle scrivere.
#
#  ESEMPI DEL RICERCATORE: le regole di ogni giudice (file JSON) sono
#  accompagnate da esempi veri, classificati a mano dal ricercatore su partite
#  pilota, nella cartella "esempi" (una tabella Excel per misura). Ogni
#  raccoglitore li trasforma in testo e li aggiunge in fondo al prompt di
#  sistema: così il giudice impara la visione del ricercatore dai casi
#  concreti, non solo dalle definizioni. Le partite usate come esempi non
#  vanno usate per verificare il giudice.
#
#  Ogni raccoglitore lavora una partita alla volta, in tre passi (funzione
#  raccogli, Sezione 5):
#    1) PREPARA il messaggio per il giudice a partire dal log della partita,
#       alla cieca: il giudice non vede mai i nomi dei modelli né la
#       condizione di aggressività;
#    2) CHIEDE il giudizio al modello giudice, oppure riusa la risposta già
#       salvata: rilanciare uno script non costa niente per le partite già
#       giudicate. Una risposta che non rispetta il formato viene chiesta una
#       seconda volta;
#    3) TRASFORMA la risposta in righe di tabella.
#
#  CONTROLLO DELLE CITAZIONI: ogni tabella con una colonna "citazione" riceve
#  anche la colonna "citazione_esatta" (sì / no / vuota se la citazione manca):
#  "no" vuol dire che la frase non compare parola per parola nella partita,
#  per esempio perché il giudice l'ha tradotta in parte ("threats" al posto
#  di "minaccia"). Alla fine lo script dice quante sono.
#
#  Quali partite: le stesse di prepara_dati, cioè quelle vere e concluse, in
#  tutte le condizioni di aggressività (nessuno, tutti, un solo aggressivo).
#
#  Cartelle:
#    partite/                        i log delle partite (solo letti)
#    giudice_<giudice>/<misura>_<versione del prompt>/
#        messaggi/                   che cosa ha letto il giudice, uno per partita
#        risposte/                   le risposte del giudice, una per partita
#        <tabella>.csv               le tabelle di questa esecuzione
#    dati/llm_<misura>_<tabella>.csv le tabelle da unire a quelle di prepara_dati
#  Le risposte date con un prompt di un'altra versione stanno nella cartella
#  di quella versione e non vengono mai riusate per sbaglio.
#
#  Quando le tabelle vanno anche in "dati": solo se il giudice ha letto TUTTE
#  le partite (PARTITE_SCELTE = None), senza risposte mancanti, e non è una
#  ripetizione per la prova di stabilità. Così le prove su poche partite
#  (validazione, confronto tra giudici) non sostituiscono mai le tabelle
#  complete che l'analisi unisce.
#
#  Chiavi di unione con prepara_dati: partita, ruolo, turno. Le tabelle LLM
#  portano solo le chiavi e le proprie misure: modello, condizione e testi
#  stanno già nelle tabelle di prepara_dati.
#
#  Librerie: pip install openai anthropic (solo per chiamare il giudice)
# ==============================================================================

import csv
import glob
import json
import os
import re
import time


# ==============================================================================
#  SEZIONE 1 — CARTELLE E GIUDICI
# ==============================================================================
CARTELLA         = os.path.dirname(os.path.abspath(__file__))
CARTELLA_PARTITE = os.path.join(CARTELLA, "partite")
CARTELLA_DATI    = os.path.join(CARTELLA, "dati")
CARTELLA_ESEMPI  = os.path.join(CARTELLA, "esempi")
FILE_CHIAVI      = os.path.join(CARTELLA, "chiavi_api.json")
PERSONAGGI       = ["S", "C", "K"]

# I giudici disponibili (si sceglie con GIUDICE in ogni raccoglitore).
#  - mistral: Mistral Large 4, temperatura 1.0 (consigliata), ragionamento high;
#  - claude:  Sonnet 5.5 (più capace di Haiku, il modello che gioca);
#             ragionamento adattivo high; nessuna temperatura (i modelli 5.5
#             non la accettano);
#  - gemini:  esterno alle famiglie in gioco, ma nelle prove dava spesso
#             errori 503 (server sovraccarichi).
# ATTENZIONE: Mistral Large 4 e Claude sono anche giocatori. Un giudice della
# stessa famiglia potrebbe leggere meglio i testi del proprio modello
# (self-preference): gli script di confronto dividono l'accordo per modello.
# "pausa" = secondi di attesa dopo ogni chiamata riuscita.
GIUDICI = {
    "mistral": {"modello": "mistral-large-4", "libreria": "openai", "indirizzo": "https://api.mistral.ai/v1",
                "chiave": "mistral", "temperatura": 0.5, "ragionamento": "high", "pausa": 2},
    "claude":  {"modello": "claude-sonnet-5-5", "libreria": "anthropic", "indirizzo": None,
                "chiave": "claude", "temperatura": None, "ragionamento": "high", "pausa": 2},
    "gemini":  {"modello": "gemini-3.8-flash", "libreria": "openai",
                "indirizzo": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "chiave": "gemini", "temperatura": None, "ragionamento": "high", "pausa": 15},
}

# Attese (secondi) prima del secondo e del terzo tentativo di una chiamata
# fallita: 503 = server sovraccarichi, 429 = limite di richieste o credito.
ATTESE_ERRORE = [60, 120]


# ==============================================================================
#  SEZIONE 2 — FILE E PARTITE
# ==============================================================================
def leggi_json(percorso):
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def leggi_prompt(nome_file):
    """
    Dal file JSON delle regole del giudice: (prompt di sistema, modello del
    messaggio). Ogni sezione del prompt di sistema è una lista di righe: si
    uniscono nell'ordine in cui sono scritte, con una riga vuota tra le sezioni.
    """
    prompt = leggi_json(os.path.join(CARTELLA, nome_file))
    sistema = "\n\n".join("\n".join(righe) for righe in prompt["system_prompt"].values())
    return sistema, "\n".join(prompt["messaggio_partita"])


def leggi_esempi(nome_file, foglio="Esempi"):
    """
    Le righe di una tabella di esempi (cartella "esempi"), come dizionari
    {intestazione in minuscolo: valore}. Le righe vuote si saltano; i numeri
    interi salvati da Excel come 3.0 tornano 3; le celle vuote diventano "".
    """
    from openpyxl import load_workbook      # serve solo qui: chi non usa esempi non ha bisogno di openpyxl
    percorso = os.path.join(CARTELLA_ESEMPI, nome_file)
    if not os.path.exists(percorso):
        raise SystemExit(f"Manca la tabella di esempi {percorso}.")
    righe = list(load_workbook(percorso, data_only=True)[foglio].iter_rows(values_only=True))

    def pulito(v):
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).strip()

    intestazione = [pulito(c).lower() for c in righe[0]]
    return [dict(zip(intestazione, map(pulito, r))) for r in righe[1:] if any(pulito(c) for c in r)]


def schede():
    """Le schede dei tre personaggi (S.json, C.json, K.json): {ruolo: scheda}."""
    return {r: leggi_json(os.path.join(CARTELLA, f"{r}.json")) for r in PERSONAGGI}


def partita_da_usare(log):
    """
    Partite vere e concluse: niente partite senza esito o interrotte, niente
    prove con risposte finte (mock), niente prova di idoneità. Tutte le
    condizioni di aggressività sono comprese. Stessa regola di prepara_dati.
    """
    meta, esito = log["meta"], log.get("esito")
    return bool(esito) and not esito.get("interrotta") and not meta.get("mock") \
        and meta.get("tipo_sessione") != "idoneita"


def partite_da_leggere():
    """[(identificativo, log), ...] delle partite da usare, nell'ordine dei nomi dei file."""
    elenco = []
    for percorso in sorted(glob.glob(os.path.join(CARTELLA_PARTITE, "partita_*.json"))):
        log = leggi_json(percorso)
        if partita_da_usare(log):
            elenco.append((log["meta"]["game_id"][:6], log))
    return elenco


def modelli_dai_log():
    """{(partita, ruolo): nome del modello}, dai log: serve agli script di confronto (accordo per modello)."""
    return {(gid, r): log["meta"]["modelli"][r]["modello"] for gid, log in partite_da_leggere() for r in PERSONAGGI}


def normalizza(testo):
    """
    Il testo in minuscolo, con apostrofi e virgolette tutti dello stesso tipo
    (') e con gli spazi singoli: così le piccole differenze di battitura tra
    la citazione e il testo originale non contano (il giudice scrive spesso
    'parola' dove il testo ha "parola").
    """
    for vecchio, nuovo in (("’", "'"), ("‘", "'"), ("“", "'"), ("”", "'"), ("«", "'"), ("»", "'"), ('"', "'")):
        testo = testo.replace(vecchio, nuovo)
    return " ".join(testo.lower().split())


def testo_della_partita(log):
    """Tutto ciò che il giudice può citare: interventi pubblici e motivazioni dei voti, normalizzati, in un'unica stringa."""
    pezzi = []
    for t in log["turni"]:
        pezzi += [iv.get("testo_pubblico") or "" for iv in t["interventi"]]
        pezzi += [(v or {}).get("motivazione") or "" for v in t["voti"].values()]
    return normalizza(" ".join(pezzi))


def citazione_esatta(citazione, testo_partita):
    """
    "sì" se la citazione compare parola per parola nella partita, "no" se non
    compare, "" se la citazione è vuota. Se il giudice ha tagliato la frase
    con i puntini (... o …), ogni pezzo deve comparire. Virgolette e
    punteggiatura all'inizio e alla fine di ogni pezzo non contano.
    """
    pezzi = [p.strip(" \"'.,;:!?") for p in re.split(r"\.\.\.|…", normalizza(citazione or ""))]
    pezzi = [p for p in pezzi if p]
    if not pezzi:
        return ""
    return "sì" if all(p in testo_partita for p in pezzi) else "no"


def salva_csv(righe, colonne, percorso):
    """
    CSV nel formato di Excel in italiano, come quelli di prepara_dati: punto e
    virgola tra le colonne, virgola per i decimali, "a capo" sostituiti da
    spazi. Le colonne sono passate a parte: così anche una tabella vuota ha
    la sua intestazione.
    """
    with open(percorso, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonne, delimiter=";")
        w.writeheader()
        for riga in righe:
            w.writerow({k: (str(v).replace(".", ",") if isinstance(v, float) else str(v).replace("\n", " "))
                        for k, v in riga.items()})


# ==============================================================================
#  SEZIONE 3 — CHIAMARE IL GIUDICE
#  Due librerie: "openai" per Mistral e Gemini (stesso formato di richiesta,
#  cambia solo l'indirizzo), "anthropic" per Claude. Si importano solo quando
#  servono: per scrivere i soli messaggi non servono.
# ==============================================================================
def crea_client(scelto):
    """Il client del giudice scelto, con la chiave presa da chiavi_api.json."""
    nome = scelto["chiave"]
    chiave = str(leggi_json(FILE_CHIAVI).get(nome) or "").strip() if os.path.exists(FILE_CHIAVI) else ""
    if not chiave:
        raise SystemExit(f'Manca la chiave: aggiungi "{nome}": "la-chiave" in chiavi_api.json.')
    if scelto["libreria"] == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=chiave)
    from openai import OpenAI
    return OpenAI(api_key=chiave, base_url=scelto["indirizzo"])


def solo_testo(contenuto):
    """Il testo della risposta senza il ragionamento (Mistral restituisce pezzi "text" e "thinking")."""
    if isinstance(contenuto, str) or contenuto is None:
        return contenuto or ""
    pezzi = []
    for pezzo in contenuto:
        tipo = pezzo.get("type") if isinstance(pezzo, dict) else getattr(pezzo, "type", None)
        testo = pezzo.get("text") if isinstance(pezzo, dict) else getattr(pezzo, "text", None)
        if tipo == "text" and testo:
            pezzi.append(testo)
    return "".join(pezzi)


def una_chiamata(client, scelto, sistema, messaggio):
    """
    Una sola chiamata al giudice; restituisce il testo della risposta.
    Claude: ragionamento adattivo; un rifiuto del provider (stop_reason
    "refusal") diventa un errore, così la chiamata viene ripetuta. 16.000
    token: sotto la soglia oltre cui la libreria di Anthropic vuole la
    risposta "a flusso". I parametri del ragionamento passano con extra_body,
    inseriti nella richiesta così come sono.
    """
    if scelto["libreria"] == "anthropic":
        r = client.messages.create(
            model=scelto["modello"], system=sistema, max_tokens=16000,
            messages=[{"role": "user", "content": messaggio}],
            extra_body={"thinking": {"type": "adaptive"}, "output_config": {"effort": scelto["ragionamento"]}})
        if r.stop_reason == "refusal":
            raise RuntimeError("risposta rifiutata dal provider")
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    parametri = {"model": scelto["modello"], "max_tokens": 32000,
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": messaggio}],
                 "extra_body": {"reasoning_effort": scelto["ragionamento"]}}
    if scelto["temperatura"] is not None:
        parametri["temperature"] = scelto["temperatura"]
    r = client.chat.completions.create(**parametri)
    return solo_testo(r.choices[0].message.content)


def chiedi_al_giudice(client, scelto, sistema, messaggio):
    """Una chiamata, con due nuovi tentativi (ATTESE_ERRORE) se fallisce. None se il giudice non risponde."""
    for tentativo in range(len(ATTESE_ERRORE) + 1):
        try:
            return una_chiamata(client, scelto, sistema, messaggio)
        except Exception as e:
            print(f"   errore: {e}")
            if tentativo < len(ATTESE_ERRORE):
                print(f"   riprovo tra {ATTESE_ERRORE[tentativo]} secondi")
                time.sleep(ATTESE_ERRORE[tentativo])
    return None


def leggi_risposta(testo):
    """Il JSON della risposta (anche se racchiuso tra ``` o con testo intorno); None se non c'è."""
    inizio, fine = testo.find("{"), testo.rfind("}")
    try:
        return json.loads(testo[inizio:fine + 1]) if inizio != -1 else None
    except json.JSONDecodeError:
        return None


def giudizio_valido(client, scelto, sistema, messaggio, controlla, cosa):
    """
    Chiede il giudizio e lo controlla; se la risposta non rispetta il formato
    la chiede una seconda volta. Restituisce (dati, stato), con stato:
      "ok"               risposta valida;
      "non valida"       due risposte fuori formato;
      "nessuna risposta" il giudice non risponde (errori anche dopo i nuovi tentativi).
    """
    for _ in range(2):
        testo = chiedi_al_giudice(client, scelto, sistema, messaggio)
        if testo is None:
            return None, "nessuna risposta"
        dati = leggi_risposta(testo)
        errori = controlla(dati, cosa)
        if not errori:
            return dati, "ok"
        print(f"   risposta non valida: {'; '.join(errori[:3])}")
    return None, "non valida"


# ==============================================================================
#  SEZIONE 4 — CARTELLE DEI RISULTATI
# ==============================================================================
def cartella_risultati(giudice, misura, versione_prompt, ripetizione=""):
    """giudice_<giudice>/<misura>_<versione><ripetizione>, es. giudice_mistral/segreti_v1.4."""
    return os.path.join(CARTELLA, f"giudice_{giudice}", f"{misura}_{versione_prompt}{ripetizione}")


def file_in_dati(misura, tabella):
    """Il file di una tabella nella cartella dati, es. dati/llm_segreti_usi.csv."""
    return os.path.join(CARTELLA_DATI, f"llm_{misura}_{tabella}.csv")


# ==============================================================================
#  SEZIONE 5 — IL CICLO DI RACCOLTA
#  Ogni raccoglitore passa tre funzioni sue:
#    prepara(log, modello_messaggio) → (messaggio, cosa, risposta_pronta)
#        'cosa' è ciò che il giudice deve giudicare (es. l'elenco dei
#        cedimenti): serve a controllare la risposta e a scrivere le righe.
#        'risposta_pronta' è una risposta già nota senza chiedere nulla (es.
#        una partita senza niente da giudicare), altrimenti None.
#        Restituisce None per saltare la partita (es. dati di partenza mancanti).
#    controlla(dati, cosa) → elenco degli errori della risposta (vuoto = valida)
#    righe_di(gid, log, cosa, dati) → {tabella: [righe]} di quella partita
# ==============================================================================
def raccogli(misura, versione_prompt, file_prompt, giudice, colonne, prepara, controlla, righe_di,
             partite_scelte=None, solo_messaggi=True, ripetizione="", esempi="", partite_esempi=()):
    """
    Il ciclo comune dei raccoglitori. 'colonne' è {tabella: [colonne]}.
    'esempi' è il testo degli esempi del ricercatore: si aggiunge in fondo al
    prompt di sistema (che viene anche salvato in prompt_di_sistema.txt nella
    cartella dei risultati, per poterlo rileggere). 'partite_esempi' sono le
    partite da cui vengono gli esempi: se se ne giudica una, lo script avvisa
    (il giudice ne conosce già la risposta, quindi non serve a verificarlo).
    Se il giudice smette di rispondere, le partite rimaste si saltano: basta
    rilanciare più tardi (quelle già giudicate non costano niente).
    Restituisce le righe raccolte, {tabella: [righe]}.
    """
    scelto = GIUDICI[giudice]
    # Le tabelle con una citazione ricevono anche la colonna del controllo (vedi citazione_esatta).
    colonne = {nome: c + ["citazione_esatta"] if "citazione" in c else c for nome, c in colonne.items()}
    sistema, modello_messaggio = leggi_prompt(file_prompt)
    if esempi:
        sistema += "\n\n" + esempi
    cartella = cartella_risultati(giudice, misura, versione_prompt, ripetizione)
    for sottocartella in ("messaggi", "risposte"):
        os.makedirs(os.path.join(cartella, sottocartella), exist_ok=True)
    with open(os.path.join(cartella, "prompt_di_sistema.txt"), "w", encoding="utf-8") as f:
        f.write(sistema)
    client = None if solo_messaggi else crea_client(scelto)
    print(f"Raccolta: {misura}   giudice: {giudice} ({scelto['modello']})   prompt {versione_prompt}{ripetizione}   "
          f"partite: {'tutte' if not partite_scelte else ', '.join(partite_scelte)}")
    print(f"Prompt di sistema: circa {len(sistema.split())} parole (esempi compresi)")

    tabelle = {nome: [] for nome in colonne}
    trovate, saltate, scartate = set(), [], []
    giudice_fermo = False                      # diventa True se il giudice smette di rispondere
    for gid, log in partite_da_leggere():
        if partite_scelte and gid not in partite_scelte:
            continue
        trovate.add(gid)
        if gid in partite_esempi:
            print(f"{gid}: ATTENZIONE, partita usata negli esempi del prompt: non vale per verificare il giudice")

        # Passo 1: messaggio (alla cieca), salvato per poterlo rileggere.
        preparata = prepara(log, modello_messaggio)
        if preparata is None:
            saltate.append(gid)
            continue
        messaggio, cosa, pronta = preparata
        with open(os.path.join(cartella, "messaggi", f"{gid}.txt"), "w", encoding="utf-8") as f:
            f.write(messaggio)
        if solo_messaggi:
            print(f"{gid}: messaggio scritto")
            continue

        # Passo 2: giudizio, riusato se già salvato e valido.
        file_risposta = os.path.join(cartella, "risposte", f"{gid}.json")
        if pronta is not None:
            dati = pronta
        else:
            dati = leggi_json(file_risposta) if os.path.exists(file_risposta) else None
        if controlla(dati, cosa):
            if giudice_fermo:
                scartate.append(gid)
                continue
            print(f"{gid}: chiedo il giudizio")
            dati, stato = giudizio_valido(client, scelto, sistema, messaggio, controlla, cosa)
            if stato == "nessuna risposta":
                print("   Il giudice non risponde: le partite già giudicate sono salvate, rilancia più tardi.")
                giudice_fermo = True
            if stato != "ok":
                scartate.append(gid)
                continue
            with open(file_risposta, "w", encoding="utf-8") as f:
                json.dump(dati, f, ensure_ascii=False, indent=2)
            time.sleep(scelto["pausa"])

        # Passo 3: righe delle tabelle, con il controllo delle citazioni.
        testo_partita = testo_della_partita(log)
        for nome, righe in righe_di(gid, log, cosa, dati).items():
            if "citazione_esatta" in colonne[nome]:
                for riga in righe:
                    riga["citazione_esatta"] = citazione_esatta(riga.get("citazione", ""), testo_partita)
            tabelle[nome] += righe

    # --- riepilogo e salvataggio ------------------------------------------------
    if partite_scelte and set(partite_scelte) - trovate:
        print(f"\nPartite scelte ma non trovate (o non concluse): {', '.join(sorted(set(partite_scelte) - trovate))}")
    if saltate:
        print(f"Partite saltate (dati di partenza mancanti): {', '.join(saltate)}")
    if solo_messaggi:
        print(f"\nMessaggi in {os.path.join(cartella, 'messaggi')}. Per chiamare il giudice metti SOLO_MESSAGGI = False.")
        return tabelle
    for nome, righe in tabelle.items():
        salva_csv(righe, colonne[nome], os.path.join(cartella, f"{nome}.csv"))
    print(f"\nTabelle in {cartella}: " + ", ".join(f"{nome}.csv ({len(r)} righe)" for nome, r in tabelle.items()))
    for nome, righe in tabelle.items():
        sbagliate = [r for r in righe if r.get("citazione_esatta") == "no"]
        if sbagliate:
            print(f"Citazioni che non compaiono nel testo ({nome}.csv, colonna citazione_esatta = no): "
                  f"{len(sbagliate)} su {sum(bool(r.get('citazione_esatta')) for r in righe)}")
    if scartate:
        print(f"Risposte non valide o mancanti (rilancia lo script per riprovare): {', '.join(scartate)}")

    completa = not partite_scelte and not ripetizione and not scartate and not saltate
    if completa:
        os.makedirs(CARTELLA_DATI, exist_ok=True)
        for nome, righe in tabelle.items():
            salva_csv(righe, colonne[nome], file_in_dati(misura, nome))
        print(f"Tabelle anche in dati/: " + ", ".join(os.path.basename(file_in_dati(misura, n)) for n in tabelle)
              + f"   (giudice {giudice}, prompt {versione_prompt})")
    else:
        print("Tabelle NON copiate in dati/: servono tutte le partite (PARTITE_SCELTE = None), nessuna risposta "
              "mancante e nessuna ripetizione.")
    return tabelle
