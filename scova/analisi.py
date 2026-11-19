"""Trasforma le quote grezze in una classifica delle differenze più grandi
sui mercati giocatore: tiri, tiri in porta, falli commessi, falli subiti."""
import re
import statistics
import unicodedata
from collections import defaultdict

NOMI_MERCATO = {
    "tiri": "Tiri totali",
    "tiri_in_porta": "Tiri in porta",
    "falli_commessi": "Falli commessi",
    "falli_subiti": "Falli subiti",
}

# Margine medio ipotizzato quando un bookmaker quota un solo lato (es. solo "Over")
MARGINE_STIMATO_UN_LATO = 1.08


# --------------------------------------------------------------------------
# Riconoscimento mercati
# --------------------------------------------------------------------------
def classifica_mercato(nome):
    """Dal nome del mercato (in inglese, come lo dà l'API) alla nostra categoria.
    Restituisce None se non è un mercato che ci interessa."""
    n = (nome or "").lower()
    if "team" in n or "total match" in n or "both teams" in n:
        return None
    if any(k in n for k in ("half", "1st", "2nd", "first 10", "minute")):
        return None  # solo mercati sull'intera partita
    if "shot" in n:
        if any(k in n for k in ("on target", "on goal", "ontarget", "sot")):
            if "outside" in n or "header" in n or "headed" in n:
                return None
            return "tiri_in_porta"
        if "assist" in n or "blocked" in n or "outside" in n or "header" in n:
            return None
        return "tiri"
    if "foul" in n:
        if any(k in n for k in ("fouled", "drawn", "won", "suffered", "to be")):
            return "falli_subiti"
        return "falli_commessi"
    return None


def lato_esito(nome_esito):
    n = (nome_esito or "").strip().lower()
    if n.startswith("over") or n in ("yes", "si", "sì") or n.endswith("+"):
        return "over"
    if n.startswith("under") or n == "no":
        return "under"
    return None


def linea_da_nome(nome, handicap):
    """Linea del mercato: dall'handicap del catalogo, oppure da '2+' nel nome."""
    try:
        h = float(handicap)
        if h > 0:
            return h
    except (TypeError, ValueError):
        pass
    m = re.search(r"(\d+)\s*\+", nome or "")
    if m:
        return int(m.group(1)) - 0.5
    m = re.search(r"(\d+\.5)", nome or "")
    if m:
        return float(m.group(1))
    return 0.5  # "almeno un tiro" e simili


# --------------------------------------------------------------------------
# Nomi giocatori
# --------------------------------------------------------------------------
def _ascii(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def nome_leggibile(nome):
    """'Malen, Donyell' -> 'Donyell Malen'."""
    nome = (nome or "").strip()
    if "," in nome:
        cognome, nome_proprio = [p.strip() for p in nome.split(",", 1)]
        return f"{nome_proprio} {cognome}".strip()
    return nome


def token_nome(nome):
    s = _ascii(nome_leggibile(nome))
    s = re.sub(r"[^a-z ]", " ", s)
    return [t for t in s.split() if len(t) > 1 or True]


def stesso_giocatore(a, b):
    """Confronto tollerante: 'D. Malen' = 'Donyell Malen' = 'Malen, Donyell'."""
    ta, tb = token_nome(a), token_nome(b)
    lunghi_a = {t for t in ta if len(t) > 2}
    lunghi_b = {t for t in tb if len(t) > 2}
    if not lunghi_a or not lunghi_b or not (lunghi_a & lunghi_b):
        return False
    if not (lunghi_a <= lunghi_b or lunghi_b <= lunghi_a):
        return False
    # se uno dei due ha iniziali (es. 'D. Malen'), devono combaciare
    iniz_a = {t[0] for t in ta if len(t) <= 2}
    iniz_b = {t[0] for t in tb if len(t) <= 2}
    prime_a = {t[0] for t in ta}
    prime_b = {t[0] for t in tb}
    return iniz_a <= prime_b and iniz_b <= prime_a


def raggruppa_giocatori(nomi):
    """Restituisce {nome_originale: nome_canonico} unendo le varianti."""
    gruppi = []  # liste di nomi
    for nome in sorted(set(nomi), key=lambda x: -len(nome_leggibile(x))):
        for g in gruppi:
            if stesso_giocatore(nome, g[0]):
                g.append(nome)
                break
        else:
            gruppi.append([nome])
    mappa = {}
    for g in gruppi:
        canonico = nome_leggibile(g[0])  # il nome più lungo/completo
        for n in g:
            mappa[n] = canonico
    return mappa


# --------------------------------------------------------------------------
# Estrazione righe dalle risposte API
# --------------------------------------------------------------------------
def classifica_info(info):
    """Usa il marketType dell'API quando c'è (es. 'playertotals-shotsongoal'),
    altrimenti il nome del mercato."""
    tipo = (info.get("tipo") or "").lower()
    if tipo:
        if info.get("periodo") not in (None, "", "result", "fulltime"):
            return None
        if "shotsongoal" in tipo or "shotsontarget" in tipo:
            return "tiri_in_porta"
        if tipo.endswith("-shots"):
            return "tiri"
        if "foulscommitted" in tipo:
            return "falli_commessi"
        if "fouled" in tipo or "foulsdrawn" in tipo or "foulssuffered" in tipo:
            return "falli_subiti"
        return None
    return classifica_mercato(info.get("nome"))


def linea_lato(nome_esito, info):
    """Restituisce (linea, lato) per un esito.
    'Over'/'Under' -> linea del mercato; '2+' -> over 1.5; '0' -> under 0.5;
    'Yes' su 'commette un fallo' -> over 0.5."""
    n = (nome_esito or "").strip().lower()
    m = re.fullmatch(r"(\d+)\s*\+", n)
    if m:
        return int(m.group(1)) - 0.5, "over"
    if n == "0":
        return 0.5, "under"
    lato = lato_esito(n)
    if lato is None:
        return None, None
    return linea_da_nome(info["nome"], info.get("handicap")), lato


def _ore_fa(iso):
    import datetime as _dt
    try:
        t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return None


def estrai_righe(partita, risposta_quote, catalogo, sconosciuti, inattivi_ok=(), ore_max=72):
    """partita: dict fixture. risposta_quote: JSON di /odds.
    catalogo: {marketId(str): {nome, handicap, tipo, periodo, giocatore, esiti:{id:nome}}}"""
    righe = []
    boards = (risposta_quote or {}).get("bookmakerOdds") or {}
    for book, board in boards.items():
        for mid, mercato in (board.get("markets") or {}).items():
            info = catalogo.get(str(mid))
            if not info:
                continue
            categoria = classifica_info(info)
            if categoria is None:
                if info.get("giocatore") or "player" in info["nome"].lower():
                    sconosciuti.add(info["nome"])
                continue
            for oid, esito in (mercato.get("outcomes") or {}).items():
                nome_esito = info["esiti"].get(str(oid)) or esito.get("outcomeName")
                linea, lato = linea_lato(nome_esito, info)
                if lato is None:
                    continue
                for pid, p in (esito.get("players") or {}).items():
                    if pid == "0" or not p.get("playerName"):
                        continue
                    inattiva = not p.get("active", True)
                    if inattiva:
                        eta = _ore_fa(p.get("changedAt"))
                        if book not in inattivi_ok or eta is None or eta > ore_max:
                            continue
                    try:
                        prezzo = float(p.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if prezzo <= 1.0:
                        continue
                    righe.append({
                        "fixture": str(partita["id"]),
                        "giocatore_raw": p["playerName"],
                        "mercato": categoria,
                        "linea": linea,
                        "lato": lato,
                        "book": book,
                        "quota": prezzo,
                        "link": p.get("betslip"),
                        "aggiornata": p.get("changedAt"),
                        "inattiva": inattiva,
                    })
    return righe


# --------------------------------------------------------------------------
# Analisi
# --------------------------------------------------------------------------
def _prob_equa(over, under):
    """Toglie il margine dalla coppia over/under -> probabilità 'vera' dell'over."""
    po, pu = 1 / over, 1 / under
    return po / (po + pu)


def analizza(righe, partite, cfg, precedente=None):
    cloni = cfg.get("cloni", {})
    precisi = set(cfg.get("bookmaker_precisi", []))
    soglia_valore = cfg.get("soglia_valore_percento", 5)
    soglia_diff = cfg.get("soglia_differenza_percento", 20)
    quota_max = cfg.get("quota_massima", 10)
    min_book = cfg.get("minimo_bookmaker", 3)

    # 1) unifica i nomi dei giocatori per partita
    per_partita = defaultdict(list)
    for r in righe:
        per_partita[r["fixture"]].append(r["giocatore_raw"])
    mappe = {fx: raggruppa_giocatori(nomi) for fx, nomi in per_partita.items()}
    for r in righe:
        r["giocatore"] = mappe[r["fixture"]][r["giocatore_raw"]]

    # 2) indice: (partita, giocatore, mercato, linea) -> lato -> book -> quota
    idx = defaultdict(lambda: {"over": {}, "under": {}})
    link = {}
    da_verificare = {}  # (chiave, lato, book) -> ora ultimo aggiornamento
    for r in righe:
        if r.get("inattiva"):
            k = (r["fixture"], r["giocatore"], r["mercato"], r["linea"])
            da_verificare[(k, r["lato"], r["book"])] = (r["quota"], r.get("aggiornata"))
            continue
        k = (r["fixture"], r["giocatore"], r["mercato"], r["linea"])
        attuale = idx[k][r["lato"]].get(r["book"])
        if attuale is None or r["quota"] > attuale:
            idx[k][r["lato"]][r["book"]] = r["quota"]
            link[(k, r["lato"], r["book"])] = r.get("link")

    prec = {}
    for o in (precedente or {}).get("opportunita", []):
        prec[o["id"]] = o["miglior_quota"]

    riferimento_book = cfg.get("riferimento", "sisal.it")
    copie_rif = {b for b, padre in cloni.items() if padre == riferimento_book}
    riferimento = []
    for k, lati in idx.items():
        fx, giocatore, mercato, linea = k
        p = partite.get(fx, {})
        for lato in ("over", "under"):
            quote = dict(lati[lato])
            verificare = {}
            for (kk, ll, b), (q, quando) in da_verificare.items():
                if kk == k and ll == lato and b not in quote:
                    quote[b] = q
                    verificare[b] = quando
            q_rif = quote.get(riferimento_book)
            if not q_rif:
                continue
            altri = sorted(([b, q] for b, q in quote.items()
                            if b != riferimento_book and not (b in copie_rif and q == q_rif)),
                           key=lambda x: -x[1])
            sopra = [[b, q] for b, q in altri if q > q_rif]
            top_b, top_q = (sopra[0] if sopra else (None, None))
            riferimento.append({
                "id": f"{fx}|{giocatore}|{mercato}|{linea}|{lato}",
                "partita": p.get("nome", fx), "competizione": p.get("competizione", ""),
                "inizio": p.get("inizio", ""), "giocatore": giocatore,
                "mercato": mercato, "mercato_nome": NOMI_MERCATO[mercato],
                "linea": linea, "lato": lato, "descrizione": descrivi(mercato, linea, lato),
                "quota_rif": q_rif,
                "altri": altri,
                "sopra": sopra,
                "miglior_book": top_b, "miglior_quota": top_q,
                "sopra_pct": round((top_q / q_rif - 1) * 100, 1) if top_q else 0.0,
                "da_verificare": verificare,
            })
    riferimento.sort(key=lambda r: -r["sopra_pct"])

    opportunita, arbitraggi = [], []
    for k, lati in idx.items():
        fx, giocatore, mercato, linea = k
        p = partite.get(fx, {})

        # probabilità equa dell'over per ogni bookmaker che quota entrambi i lati
        equa = {}
        for b in set(lati["over"]) & set(lati["under"]):
            equa[b] = _prob_equa(lati["over"][b], lati["under"][b])

        for lato in ("over", "under"):
            quote = lati[lato]
            # raggruppa i cloni con quota identica al "padre"
            indipendenti = {}
            for b, q in quote.items():
                padre = cloni.get(b)
                if padre and quote.get(padre) == q:
                    continue
                indipendenti[b] = q
            if len(indipendenti) < 2:
                continue

            ordinate = sorted(indipendenti.items(), key=lambda x: -x[1])
            best_b, best_q = ordinate[0]
            if best_q > quota_max:
                continue  # quote altissime: margini enormi, confronto inaffidabile
            worst_b, worst_q = ordinate[-1]
            diff = (best_q - worst_q) / worst_q * 100

            # probabilità equa stimata SENZA il bookmaker migliore
            fonte = ""
            prob = None
            altri = []
            pr = [equa[b] for b in precisi if b in equa and b != best_b]
            if pr:
                prob = statistics.median(pr)
                fonte = "bookmaker preciso (Pinnacle)"
            else:
                altri = [v for b, v in equa.items() if b != best_b and not
                         (cloni.get(b) and cloni.get(b) in equa)]
                if altri:
                    prob = statistics.median(altri)
                    fonte = f"media di {len(altri)} bookmaker (margine tolto)"
                else:
                    stime = [1 / q / MARGINE_STIMATO_UN_LATO
                             for b, q in indipendenti.items() if b != best_b]
                    prob = statistics.median(stime)
                    fonte = "stima (solo un lato quotato)"
            if lato == "under" and fonte != "stima (solo un lato quotato)":
                prob = 1 - prob
            valore = (best_q * prob - 1) * 100

            if fonte.startswith("bookmaker preciso"):
                affidabilita = "alta"
            elif (fonte.startswith("media") and len(altri) >= 2) or len(indipendenti) >= 4:
                affidabilita = "media"
            else:
                affidabilita = "bassa"
            # segnalazione = c'è valore vero, confermato da abbastanza bookmaker.
            # (una differenza grande da sola spesso vuol dire solo che un bookmaker è basso)
            segnale = (len(indipendenti) >= min_book and affidabilita != "bassa"
                       and valore >= soglia_valore and diff >= soglia_diff)

            oid = f"{fx}|{giocatore}|{mercato}|{linea}|{lato}"
            prima = prec.get(oid)
            opportunita.append({
                "id": oid,
                "fixture": fx,
                "partita": p.get("nome", fx),
                "competizione": p.get("competizione", ""),
                "inizio": p.get("inizio", ""),
                "giocatore": giocatore,
                "mercato": mercato,
                "mercato_nome": NOMI_MERCATO[mercato],
                "linea": linea,
                "lato": lato,
                "descrizione": descrivi(mercato, linea, lato),
                "miglior_book": best_b,
                "miglior_quota": best_q,
                "peggior_book": worst_b,
                "peggior_quota": worst_q,
                "differenza_pct": round(diff, 1),
                "prob_equa_pct": round(prob * 100, 1),
                "quota_equa": round(1 / prob, 2) if prob > 0 else None,
                "quota_minima": round((1 + soglia_valore / 100) / prob, 2) if prob > 0 else None,
                "valore_pct": round(valore, 1),
                "fonte_prob": fonte,
                "affidabilita": affidabilita,
                "n_book": len(indipendenti),
                "tutte": sorted(([b, q] for b, q in quote.items()), key=lambda x: -x[1]),
                "link": link.get((k, lato, best_b)),
                "quota_precedente": prima,
                "segnale": segnale,
            })

        # arbitraggio: miglior over + miglior under < 100%
        if lati["over"] and lati["under"]:
            bo, qo = max(lati["over"].items(), key=lambda x: x[1])
            bu, qu = max(lati["under"].items(), key=lambda x: x[1])
            somma = 1 / qo + 1 / qu
            if somma < 1 and bo != bu:
                arbitraggi.append({
                    "partita": p.get("nome", fx),
                    "competizione": p.get("competizione", ""),
                    "inizio": p.get("inizio", ""),
                    "giocatore": giocatore,
                    "mercato_nome": NOMI_MERCATO[mercato],
                    "linea": linea,
                    "over": [bo, qo], "under": [bu, qu],
                    "profitto_pct": round((1 / somma - 1) * 100, 2),
                    "puntata_over_su_100": round(100 * (1 / qo) / somma, 2),
                    "puntata_under_su_100": round(100 * (1 / qu) / somma, 2),
                })

    rango = {"alta": 0, "media": 1, "bassa": 2}
    opportunita.sort(key=lambda o: (rango[o["affidabilita"]] == 2, -o["valore_pct"], -o["differenza_pct"]))
    arbitraggi.sort(key=lambda a: -a["profitto_pct"])
    # aggiungi al riferimento la stima della quota giusta, quando c'è
    equa = {o["id"]: o for o in opportunita}
    for r in riferimento:
        o = equa.get(r["id"])
        if o:
            r["quota_equa"], r["prob_equa_pct"], r["affidabilita"] = o["quota_equa"], o["prob_equa_pct"], o["affidabilita"]
    analizza.riferimento = riferimento
    return opportunita, arbitraggi


_PLURALE = {"tiri": "tiri", "tiri_in_porta": "tiri in porta",
            "falli_commessi": "falli commessi", "falli_subiti": "falli subiti"}
_SINGOLARE = {"tiri": "tiro", "tiri_in_porta": "tiro in porta",
              "falli_commessi": "fallo commesso", "falli_subiti": "fallo subito"}


def descrivi(mercato, linea, lato):
    n = int(linea + 0.5)  # over 1.5 -> almeno 2
    if lato == "over":
        return f"Almeno {n} {_PLURALE[mercato] if n > 1 else _SINGOLARE[mercato]}"
    if n == 1:
        return f"Nessun {_SINGOLARE[mercato]}"
    return f"Al massimo {n - 1} {_PLURALE[mercato] if n - 1 > 1 else _SINGOLARE[mercato]}"
