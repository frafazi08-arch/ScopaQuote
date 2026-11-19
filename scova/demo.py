"""Genera dati DI PROVA nello stesso formato dell'API OddsPapi e li fa passare
per lo stesso identico motore di analisi. Serve a vedere la dashboard senza chiave."""
import datetime as dt
import math
import random

from . import analisi
from .aggiorna import _salva, FILE_ULTIMO

# catalogo finto: (id, nome inglese, linea)
MERCATI = []
_mid = 9000
for nome, linee in [("Player Shots Over/Under", [0.5, 1.5, 2.5, 3.5]),
                    ("Player Shots On Target Over/Under", [0.5, 1.5, 2.5]),
                    ("Player Fouls Committed Over/Under", [0.5, 1.5, 2.5]),
                    ("Player To Be Fouled Over/Under", [0.5, 1.5, 2.5])]:
    for l in linee:
        MERCATI.append((str(_mid), nome, l))
        _mid += 1

# medie per partita (tiri, tiri in porta, falli commessi, falli subiti)
PARTITE = [
    ("Serie A", "Roma", "Napoli", [("Malen, Donyell", 3.6, 1.9, 0.8, 1.4), ("Dybala, Paulo", 2.4, 0.9, 0.5, 1.9),
                                   ("Hojlund, Rasmus", 2.6, 1.1, 1.3, 1.5), ("Politano, Matteo", 1.8, 0.6, 0.9, 1.6)]),
    ("Serie A", "Inter", "Juventus", [("Martinez, Lautaro", 3.3, 1.4, 0.9, 1.6), ("Thuram, Marcus", 2.4, 1.0, 1.0, 1.3),
                                      ("Vlahovic, Dusan", 2.7, 1.2, 1.4, 1.2), ("Yildiz, Kenan", 2.5, 0.9, 0.7, 2.3)]),
    ("Serie A", "Milan", "Atalanta", [("Leao, Rafael", 2.6, 1.0, 0.6, 2.0), ("Pulisic, Christian", 2.3, 0.9, 0.5, 1.7),
                                      ("De Ketelaere, Charles", 2.1, 0.8, 1.1, 1.8)]),
    ("Serie A", "Como", "Fiorentina", [("Paz, Nico", 2.8, 1.0, 1.0, 1.9), ("Kean, Moise", 2.7, 1.2, 1.2, 1.4)]),
    ("Premier League", "Arsenal", "Chelsea", [("Saka, Bukayo", 2.7, 1.1, 0.6, 2.2), ("Palmer, Cole", 2.9, 1.1, 0.6, 1.5)]),
    ("Champions League", "Real Madrid", "Bayern", [("Mbappe, Kylian", 4.0, 1.9, 0.5, 1.4), ("Kane, Harry", 3.4, 1.6, 0.9, 1.3)]),
]

BOOK = {  # margine medio sui mercati giocatore, rumore, "generosità" casuale
    "bet365.it": (1.045, 0.05, 0.08), "sisal.it": (1.08, 0.05, 0.0), "eurobet.it": (1.065, 0.06, 0.0),
    "goldbet.it": (1.07, 0.05, 0.0), "admiralbet.it": (1.075, 0.07, 0.0), "pinnacle": (1.03, 0.03, 0.0),
}
CLONI = {"snai.it": "sisal.it", "pokerstars.it": "sisal.it", "lottomatica.it": "goldbet.it",
         "betflag.it": "goldbet.it", "planetwin365.it": "goldbet.it"}


def _poisson_over(media, linea):
    k = int(linea + 0.5)
    return 1 - sum(math.exp(-media) * media ** i / math.factorial(i) for i in range(k))


def genera(cfg, seme=None):
    rnd = random.Random(seme)
    catalogo = {mid: {"nome": nome, "handicap": l, "esiti": {"1": "Over", "2": "Under"}}
                for mid, nome, l in MERCATI}
    partite, righe, sconosciuti = {}, [], set()
    adesso = dt.datetime.now()
    pid_giocatore = 100000

    for i, (comp, casa, ospite, giocatori) in enumerate(PARTITE):
        fid = f"demo{i}"
        inizio = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=20 + 23 * (i // 2) + 3 * i)).replace(minute=45 if i % 2 else 0, second=0)
        partite[fid] = {"id": fid, "nome": f"{casa} - {ospite}", "competizione": comp,
                        "inizio": inizio.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        boards = {}
        for book, (margine, rumore, gener) in BOOK.items():
            boards[book] = {"markets": {}}
        for g in giocatori:
            nome, medie = g[0], g[1:]
            pid_giocatore += 1
            for mid, nome_m, linea in MERCATI:
                cat = analisi.classifica_mercato(nome_m)
                media = medie[["tiri", "tiri_in_porta", "falli_commessi", "falli_subiti"].index(cat)]
                p_vera = min(max(_poisson_over(media, linea), 0.03), 0.97)
                for book, (margine, rumore, gener) in BOOK.items():
                    if book == "pinnacle" and cat.startswith("falli"):
                        continue  # Pinnacle spesso non quota i falli
                    if rnd.random() < 0.12:
                        continue  # non tutti i book quotano tutto
                    lg = math.log(p_vera / (1 - p_vera)) + rnd.gauss(0, rumore)
                    if gener and rnd.random() < gener:
                        lg -= rnd.uniform(0.18, 0.35)  # bet365 a volte più generoso sull'over
                    if book == "sisal.it" and rnd.random() < 0.04:
                        lg += 0.6  # Sisal ogni tanto molto basso sull'over
                    p_book = 1 / (1 + math.exp(-lg))
                    over = round(max(1.01, 1 / (p_book * margine)), 2)
                    under = round(max(1.01, 1 / ((1 - p_book) * margine)), 2)
                    if over > 15 or under > 15:
                        continue
                    nome_book = nome
                    if book == "eurobet.it":  # nomi scritti diversamente
                        cogn, pr = nome.split(", ")
                        nome_book = f"{pr[0]}. {cogn}"
                    elif book == "bet365.it":
                        cogn, pr = nome.split(", ")
                        nome_book = f"{pr} {cogn}"
                    boards[book]["markets"][mid] = boards[book]["markets"].get(mid, {"outcomes": {"1": {"players": {}}, "2": {"players": {}}}})
                    for oid, prezzo in (("1", over), ("2", under)):
                        boards[book]["markets"][mid]["outcomes"][oid]["players"][str(pid_giocatore)] = {
                            "playerName": nome_book, "price": prezzo, "active": True,
                            "betslip": None, "changedAt": adesso.isoformat()}
        # cloni identici al padre
        for clone, padre in CLONI.items():
            if padre in boards:
                boards[clone] = boards[padre]
        righe.extend(analisi.estrai_righe(partite[fid], {"bookmakerOdds": boards}, catalogo, sconosciuti))

    # un caso "Malen" come quello visto dall'utente: Sisal 1.25, bet365 1.75
    for r in righe:
        if "Malen" in r["giocatore_raw"] and r["mercato"] == "tiri_in_porta" and r["linea"] == 1.5 and r["lato"] == "over":
            if r["book"] == "bet365.it":
                r["quota"] = 1.75
            elif r["book"] in ("sisal.it", "snai.it", "pokerstars.it"):
                r["quota"] = 1.25

    cfg_demo = dict(cfg, cloni=CLONI)
    opp, arb = analisi.analizza(righe, partite, cfg_demo)
    copertura = {}
    for r in righe:
        c = copertura.setdefault(r["book"], {m: 0 for m in analisi.NOMI_MERCATO})
        c[r["mercato"]] += 1
    risultato = {
        "demo": True,
        "aggiornato": adesso.isoformat(timespec="seconds"),
        "aggiornato_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prossimo_tra_minuti": cfg.get("intervallo_minuti", 15),
        "durata_secondi": 0.1, "richieste_api": 0,
        "partite_analizzate": len(partite), "quote_lette": len(righe),
        "copertura_bookmaker": copertura,
        "riferimento": getattr(analisi.analizza, "riferimento", []),
        "opportunita": opp, "arbitraggi": arb, "errori": [],
    }
    _salva(FILE_ULTIMO, risultato)
    return risultato
