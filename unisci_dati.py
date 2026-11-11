# ==============================================================================
#  GOLPE! — TABELLA UNIFICATA DEGLI INTERVENTI (versione 2.1)
#
#  Mette in una sola tabella tutto ciò che sappiamo di ogni intervento, così
#  si può leggere una partita turno per turno con accanto i dati raccolti, ed
#  è la base dell'analisi finale (analisi_finale_v1.2.py).
#  La BASE è la tabella interventi di prepara_dati (versione 2.1): una riga
#  per personaggio per turno (intervento pubblico + voto segreto dello stesso
#  turno), con il rispetto delle regole già calcolato da Python: parole,
#  prima stesura troppo lunga e riscritta (con le sue parole), intervento
#  ancora troppo lungo e tagliato, proposta e voto validi, rifiuti del
#  provider. A ogni riga si aggiungono, se ci sono:
#
#    AGGRESSIVITÀ   (llm_aggressivita_interventi.csv, giudice LLM alla cieca)
#                   le cinque etichette (minaccia, screditamento,
#                   intransigenza, linguaggio aggressivo, apertura), quante
#                   etichette aggressive, verso chi, la frase citata e la
#                   spiegazione del giudice
#    SEGRETI        (llm_segreti_usi.csv, giudice LLM + parole chiave)
#                   gli usi dei segreti in quell'intervento. Un intervento può
#                   contenerne più di uno (fino a 4), quindi diventano:
#                     usi_segreti_contati  usi che l'analisi conta: segreto
#                                          vero contro un altro (uso come
#                                          arma, bluff, segreto diffuso)
#                     usi_come_arma, bluff quanti di questi per tipo
#                     difese               il proprietario parla del suo segreto
#                     segreti_dettaglio    ogni uso per esteso, con la forma,
#                                          separati da " | ":
#                                          "su K (tossicodipendenza): uso come arma, minaccia"
#                     segreti_spiegazione  le spiegazioni del giudice, nello
#                                          stesso ordine, separate da " | "
#                   Le menzioni trovate dalle parole chiave e smentite dal
#                   giudice (falsi positivi) non sono usi: si tolgono.
#    CEDIMENTO      (llm_competitivita_cedimenti.csv, giudice LLM)
#                   se in quel turno il personaggio cede: il motivo (resa,
#                   patto, riserva strategica), la fase (trattativa / turno
#                   decisivo), la frase citata e la spiegazione del giudice
#    ESITO          (giocatori.csv + llm_competitivita_giocatori.csv)
#                   SOLO nell'ULTIMO intervento di ogni giocatore (l'esito è
#                   della partita, non di un turno): esito individuale, livello
#                   di guadagno del sopravvissuto, citazione e spiegazione del
#                   giudice, e l'esito finale in sei livelli:
#                     vince > guadagno forte > guadagno parziale > conserva >
#                     perde potere > giustiziato
#
#  Si aggiungono anche:
#    condizione        chi aveva il prompt aggressivo: nessuno, tutti, solo S/C/K
#                      (ricavata dalla colonna "aggressivo")
#    tipo_giocatore    il contesto di chi parla:
#                        neutro (partita neutra)
#                        neutro davanti a un aggressivo   (partita mista)
#                        aggressivo solo                  (partita mista)
#                        aggressivo (partita aggressiva)
#
#  Unione: tutte le tabelle hanno la chiave partita + turno + ruolo (l'esito
#  partita + ruolo). Si usa un'unione "a sinistra" (how="left"): restano TUTTE
#  le righe di interventi, e dove una tabella non ha nulla le colonne restano
#  vuote. Lo script controlla che nessuna riga delle altre tabelle resti fuori.
#
#  Produce, nella cartella "dati":
#    interventi_unificati.csv    per l'analisi (formato Excel italiano)
#    interventi_unificati.xlsx   per leggere: intestazioni bloccate, testi a
#                                capo, un foglio "Legenda" con le colonne
#
#  File necessari nella cartella "dati": interventi.csv, giocatori.csv,
#  llm_aggressivita_interventi.csv, llm_segreti_usi.csv,
#  llm_competitivita_cedimenti.csv, llm_competitivita_giocatori.csv
#  (le tabelle mancanti si saltano, con un avviso; interventi è obbligatoria)
#  Librerie: pip install pandas openpyxl
#  Uso: python unisci_dati_v2.1.py
# ==============================================================================

import os

import pandas as pd
from openpyxl.styles import Alignment, Font

CARTELLA_DATI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati")
CHIAVE = ["partita", "turno", "ruolo"]
PERSONAGGI = ["S", "C", "K"]
# Il segreto di ogni personaggio (dalle schede S.json, C.json, K.json).
SEGRETI = {"K": "tossicodipendenza", "C": "omosessualità", "S": "amante di un'etnia bandita"}
USI_CONTATI = ["uso come arma", "bluff", "segreto diffuso"]
TIPI = ["neutro (partita neutra)", "neutro davanti a un aggressivo",
        "aggressivo solo", "aggressivo (partita aggressiva)"]
LIVELLI_GUADAGNO = ["perde potere", "conserva", "guadagno parziale", "guadagno forte"]


# ==============================================================================
#  LETTURA E CONTROLLO
# ==============================================================================
def leggi(nome, obbligatoria=False):
    """Legge dati/<nome>.csv; None (con un avviso) se manca. Celle vuote = testo vuoto."""
    percorso = os.path.join(CARTELLA_DATI, f"{nome}.csv")
    if not os.path.exists(percorso):
        if obbligatoria:
            raise SystemExit(f"Manca {percorso}: lancia prima prepara_dati.")
        print(f"ATTENZIONE: manca {nome}.csv, le sue colonne restano vuote.")
        return None
    t = pd.read_csv(percorso, sep=";", encoding="utf-8-sig", keep_default_na=False, dtype={"partita": str})
    if "turno" in t:
        t["turno"] = pd.to_numeric(t["turno"]).astype(int)   # stessa forma della chiave in tutte le tabelle
    return t


def controlla_chiavi(tabella, nome, base, chiave):
    """Quante righe di una tabella non trovano la loro riga nella base (dovrebbero essere 0)."""
    unite = tabella[chiave].merge(base[chiave].drop_duplicates(), on=chiave, how="left", indicator=True)
    fuori = (unite["_merge"] == "left_only").sum()
    print(f"   {nome}: {len(tabella)} righe" + (f", ATTENZIONE {fuori} senza corrispondenza" if fuori else ", tutte unite"))


# ==============================================================================
#  PREPARAZIONE DELLE TABELLE (al massimo una riga per intervento)
# ==============================================================================
def colonne_aggressivita(ag):
    """Le etichette del giudice, con la frase citata e la spiegazione (rinominate per non confonderle)."""
    colonne = ["minaccia", "screditamento", "intransigenza", "linguaggio_aggressivo", "apertura",
               "etichette_aggressive", "bersagli", "citazione", "spiegazione"]
    return ag[CHIAVE + colonne].rename(columns={"bersagli": "aggressivita_bersagli",
                                                "citazione": "aggressivita_citazione",
                                                "spiegazione": "aggressivita_spiegazione"})


def colonne_segreti(se):
    """
    Più usi nello stesso intervento → una riga per intervento con i conteggi
    e, per esteso, dettaglio (con la forma) e spiegazioni del giudice.
    """
    se = se[se["giudizio_regex"] != "falso positivo"].copy()        # parole chiave smentite: non sono usi
    se["contato"] = se["relazione"].isin(USI_CONTATI) & (se["segreto"] == "vero")
    se["arma"] = se["relazione"] == "uso come arma"
    se["bluff"] = se["contato"] & ~se["arma"]
    se["difesa"] = se["relazione"] == "difesa o ammissione"
    se["dettaglio"] = [f"su {b} ({SEGRETI.get(b, '?')}): {r}" + (f", {f}" if f else "")
                       for b, r, f in zip(se["bersaglio"], se["relazione"], se["forma"])]
    return se.groupby(CHIAVE, as_index=False).agg(
        usi_segreti_contati=("contato", "sum"), usi_come_arma=("arma", "sum"), bluff=("bluff", "sum"),
        difese=("difesa", "sum"), segreti_dettaglio=("dettaglio", " | ".join),
        segreti_spiegazione=("spiegazione", " | ".join))


def colonne_cedimento(ce):
    """Al massimo un cedimento per personaggio per turno: basta rinominare le colonne."""
    return ce[CHIAVE + ["etichetta", "fase", "citazione", "spiegazione"]].rename(
        columns={"etichetta": "cedimento", "fase": "cedimento_fase", "citazione": "cedimento_citazione",
                 "spiegazione": "cedimento_spiegazione"})


def esito_finale(esito_individuale, guadagno):
    """I sei livelli: vince, i quattro livelli di guadagno dei sopravvissuti, giustiziato."""
    if esito_individuale.startswith("giustiziato"):
        return "giustiziato"
    if esito_individuale == "vince":
        return "vince"
    return guadagno if guadagno in LIVELLI_GUADAGNO else "sopravvive (non giudicato)"


def colonne_esito(gi, gu, iv):
    """
    Una riga per giocatore, con il turno del suo ULTIMO intervento: è lì che
    l'esito verrà attaccato. gu (il guadagno del giudice) può mancare.
    """
    e = gi[["partita", "ruolo", "esito_individuale"]].rename(columns={"esito_individuale": "esito"})
    if gu is not None:
        controlla_chiavi(gu, "guadagno dei sopravvissuti", gi, ["partita", "ruolo"])
        e = e.merge(gu[["partita", "ruolo", "guadagno", "citazione", "spiegazione"]].rename(
            columns={"citazione": "guadagno_citazione", "spiegazione": "guadagno_spiegazione"}),
            on=["partita", "ruolo"], how="left").fillna("")
    else:
        e["guadagno"] = e["guadagno_citazione"] = e["guadagno_spiegazione"] = ""
    e["esito_finale"] = [esito_finale(x, g) for x, g in zip(e["esito"], e["guadagno"])]
    ultimo = iv.groupby(["partita", "ruolo"], as_index=False)["turno"].max()   # turno dell'ultimo intervento
    return e.merge(ultimo, on=["partita", "ruolo"], how="left")


# ==============================================================================
#  CONDIZIONE E TIPO DI GIOCATORE
# ==============================================================================
def condizione_per_partita(iv):
    """Dalla colonna 'aggressivo': nessuno, tutti, oppure 'solo X'."""
    condizioni = {}
    for partita, g in iv.groupby("partita"):
        aggressivi = sorted(set(g.loc[g["aggressivo"] == "sì", "ruolo"]), key=PERSONAGGI.index)
        condizioni[partita] = ("nessuno" if not aggressivi else "tutti" if len(aggressivi) == 3
                               else "solo " + ", ".join(aggressivi))
    return condizioni


def tipo_giocatore(condizione, aggressivo):
    """Il contesto di chi parla (TIPI)."""
    if condizione == "nessuno":
        return TIPI[0]
    if condizione == "tutti":
        return TIPI[3]
    return TIPI[2] if aggressivo == "sì" else TIPI[1]


# ==============================================================================
#  ORDINE E DESCRIZIONE DELLE COLONNE (per l'Excel e la legenda)
# ==============================================================================
COLONNE = {
    "partita": "Identificativo della partita.",
    "condizione": "Chi aveva il prompt aggressivo: nessuno, tutti, solo S/C/K.",
    "turno": "Numero del turno.",
    "posizione": "1°, 2° o 3° a parlare nel turno.",
    "ruolo": "Chi parla: S, C o K.",
    "modello": "Provider/modello.",
    "aggressivo": "sì = chi parla ha il prompt aggressivo.",
    "tipo_giocatore": "Neutro in partita neutra / neutro davanti a un aggressivo / aggressivo solo / aggressivo in partita aggressiva.",
    "testo_pubblico": "Intervento letto dagli altri.",
    "proposta": "Contenuto del tag [PROPONGO].",
    "voto": "Voto segreto dello stesso turno.",
    "motivazione": "Motivazione privata del voto.",
    "coerenza_proposta_voto": "Proposta pubblica e voto segreto: posizione dichiarata / coperta, cessione nascosta / aperta.",
    "minaccia": "Giudice dell'aggressività: c'è una minaccia (sì/no).",
    "screditamento": "Giudice dell'aggressività: c'è uno screditamento.",
    "intransigenza": "Giudice dell'aggressività: c'è intransigenza.",
    "linguaggio_aggressivo": "Giudice dell'aggressività: linguaggio aggressivo.",
    "apertura": "Giudice dell'aggressività: concessioni o tono cooperativo (non sottratta all'aggressività).",
    "etichette_aggressive": "Quante delle 4 etichette aggressive (0-4). Vuota = intervento non giudicato (silenzio).",
    "aggressivita_bersagli": "Verso chi è rivolta l'aggressività.",
    "aggressivita_citazione": "La frase che il giudice cita.",
    "aggressivita_spiegazione": "La spiegazione del giudice.",
    "usi_segreti_contati": "Usi di segreti veri contro un altro (uso come arma, bluff, segreto diffuso).",
    "usi_come_arma": "Di cui: chi parla conosce davvero il segreto.",
    "bluff": "Di cui: chi parla non conosce il segreto (bluff o segreto diffuso).",
    "difese": "Il proprietario parla del proprio segreto (non contato tra gli usi).",
    "segreti_dettaglio": "Ogni uso per esteso: su chi (quale segreto), relazione, forma.",
    "segreti_spiegazione": "Le spiegazioni del giudice, nello stesso ordine del dettaglio.",
    "cedimento": "Se in questo turno cede: motivo del giudice (resa, patto, riserva strategica, non classificabile).",
    "cedimento_fase": "trattativa o turno decisivo.",
    "cedimento_citazione": "La frase su cui il giudice basa il motivo.",
    "cedimento_spiegazione": "La spiegazione del giudice.",
    "esito": "Solo nell'ultimo intervento del giocatore: esito individuale (vince, sopravvive, giustiziato...).",
    "guadagno": "Solo per i sopravvissuti: perde potere, conserva, guadagno parziale, guadagno forte (giudice).",
    "guadagno_citazione": "La frase pubblica che decide il livello di guadagno.",
    "guadagno_spiegazione": "La spiegazione del giudice, rispetto agli obiettivi del personaggio.",
    "esito_finale": "Sei livelli: vince, guadagno forte, guadagno parziale, conserva, perde potere, giustiziato.",
    "parole": "Parole dell'intervento (limite delle regole: 100-150).",
    "riscritto": "sì = la prima stesura superava 150 parole e lo script ha chiesto di riscriverla.",
    "parole_prima_stesura": "Parole della prima stesura scartata; vuoto se non è stato riscritto.",
    "tagliato": "sì = anche la riscrittura superava 150 parole: gli altri ne hanno letto solo una parte.",
    "n_io": "Pronomi di prima persona singolare.",
    "n_noi": "Pronomi di prima persona plurale.",
    "voto_valido": "no = tag [VOTO] mancante.",
    "rifiuti": "Risposte rifiutate dal provider in questo turno.",
    "intervento_bloccato": "sì = rimasto in silenzio per i rifiuti del provider.",
    "voto_bloccato": "sì = voto rifiutato dal provider.",
}
TESTI_LUNGHI = {"testo_pubblico", "motivazione", "aggressivita_spiegazione", "segreti_dettaglio",
                "segreti_spiegazione", "cedimento_spiegazione", "guadagno_spiegazione"}


def salva_excel(t, percorso):
    """Un foglio con la tabella (intestazione bloccata, testi a capo) e un foglio Legenda."""
    with pd.ExcelWriter(percorso, engine="openpyxl") as w:
        t.to_excel(w, sheet_name="Interventi", index=False)
        ws = w.sheets["Interventi"]
        ws.freeze_panes = "A2"
        for cella, nome in zip(ws[1], t.columns):
            cella.font = Font(bold=True)
            ws.column_dimensions[cella.column_letter].width = 60 if nome in TESTI_LUNGHI else 14
            if nome in TESTI_LUNGHI:
                for x in ws[cella.column_letter][1:]:
                    x.alignment = Alignment(wrap_text=True, vertical="top")
        pd.DataFrame(list(COLONNE.items()), columns=["Colonna", "Significato"]).to_excel(
            w, sheet_name="Legenda", index=False)
        w.sheets["Legenda"].column_dimensions["A"].width = 26
        w.sheets["Legenda"].column_dimensions["B"].width = 100


# ==============================================================================
#  PROGRAMMA PRINCIPALE
# ==============================================================================
def main():
    iv = leggi("interventi", obbligatoria=True)
    gi, gu = leggi("giocatori"), leggi("llm_competitivita_giocatori")
    ag, se, ce = leggi("llm_aggressivita_interventi"), leggi("llm_segreti_usi"), leggi("llm_competitivita_cedimenti")

    print(f"Interventi: {len(iv)} righe, {iv['partita'].nunique()} partite. Controllo delle chiavi:")
    t = iv.copy()
    for tabella, nome, prepara in ((ag, "aggressività", colonne_aggressivita), (se, "segreti", colonne_segreti),
                                   (ce, "cedimenti", colonne_cedimento)):
        if tabella is not None:
            controlla_chiavi(tabella, nome, iv, CHIAVE)
            t = t.merge(prepara(tabella), on=CHIAVE, how="left")     # unione a sinistra: restano tutti gli interventi
    if gi is not None:
        controlla_chiavi(gi, "giocatori", iv, ["partita", "ruolo"])
        t = t.merge(colonne_esito(gi, gu, iv), on=CHIAVE, how="left")  # solo sull'ultimo turno di ognuno

    # interventi senza usi di segreti: 0 e non "vuoto" (il giudice li ha letti e non ha trovato nulla)
    for c in ("usi_segreti_contati", "usi_come_arma", "bluff", "difese"):
        if c in t:
            t[c] = t[c].fillna(0).astype(int)
    t["condizione"] = t["partita"].map(condizione_per_partita(iv))
    t["tipo_giocatore"] = [tipo_giocatore(c, a) for c, a in zip(t["condizione"], t["aggressivo"])]
    # partite nell'ordine del file, poi turno e ordine di parola: si legge come una trascrizione
    ordine = {p: i for i, p in enumerate(iv["partita"].unique())}
    t = t.sort_values(["partita", "turno", "posizione"], key=lambda c: c.map(ordine) if c.name == "partita" else c)
    t = t[[c for c in COLONNE if c in t.columns]].fillna("")

    t.to_csv(os.path.join(CARTELLA_DATI, "interventi_unificati.csv"), index=False, sep=";", decimal=",",
             encoding="utf-8-sig")
    salva_excel(t, os.path.join(CARTELLA_DATI, "interventi_unificati.xlsx"))

    print(f"\nTabella unificata: {len(t)} righe (come interventi), {len(t.columns)} colonne.")
    for colonna, testo in (("etichette_aggressive", "con giudizio di aggressività"), ("cedimento", "con un cedimento"),
                           ("esito_finale", "con l'esito (ultimo intervento di ogni giocatore)")):
        if colonna in t:
            print(f"   {testo}: {(t[colonna] != '').sum()}")
    if "usi_segreti_contati" in t:
        print(f"   con almeno un uso contato dei segreti: {(t['usi_segreti_contati'] > 0).sum()}")
    print(f"File creati in '{CARTELLA_DATI}': interventi_unificati.csv e interventi_unificati.xlsx")


if __name__ == "__main__":
    main()
