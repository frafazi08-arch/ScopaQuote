"""Quote bet365 (tiri, tiri in porta, falli commessi, falli subiti) tramite il
servizio Apify "bet365-real-time-odds". Si paga a consumo dal credito Apify
(piano gratuito: $5 al mese). Il programma tiene il conto della spesa."""
import datetime as dt
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://zen-studio--bet365-real-time-odds.apify.actor"
COSTO_PARTITA = 0.01      # /match/{id}
COSTO_ELENCO = 0.003      # /competition/{slug}
MERCATI = {
    "Shots": "tiri",
    "Shots On Target": "tiri_in_porta",
    "Fouls Committed": "falli_commessi",
    "To Be Fouled": "falli_subiti",
}
GENERICI = {"calcio", "fc", "ac", "as", "ssc", "us", "cf", "acf", "bc", "afc", "sc", "ss",
            "1907", "1909", "1913", "rome", "turin", "milano", "milan", "di", "de", "the"}


class ErroreApify(Exception):
    pass


def _get(percorso, token, **params):
    params["token"] = token
    url = f"{BASE}/{percorso}?{urllib.parse.urlencode(params)}"
    for tentativo in range(3):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErroreApify("Token Apify non valido o credito esaurito "
                                  f"(HTTP {e.code}).")
            if e.code == 429 or e.code >= 500:
                time.sleep(5 * (tentativo + 1))
                continue
            raise ErroreApify(f"Apify HTTP {e.code} su /{percorso}")
        except urllib.error.URLError as e:
            if tentativo == 2:
                raise ErroreApify(f"Apify non raggiungibile: {e.reason}")
            time.sleep(3)
    raise ErroreApify(f"Apify: troppi tentativi su /{percorso}")


def _token_squadra(nome):
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return {t for t in s.split() if t not in GENERICI and len(t) > 1}


def elenco_partite(token, slug="italy-serie-a"):
    d = _get(f"competition/{slug}", token)
    return d.get("matches") or []


def abbina(partite_bet365, partita):
    """Trova la partita bet365 corrispondente a una partita OddsPapi
    (stesso orario d'inizio e almeno una squadra in comune)."""
    try:
        t0 = dt.datetime.fromisoformat(partita["inizio"].replace("Z", "+00:00"))
    except ValueError:
        return None
    casa, ospite = (partita["nome"].split(" - ", 1) + [""])[:2]
    tc, to = _token_squadra(casa), _token_squadra(ospite)
    migliore, punti_max = None, 0
    for m in partite_bet365:
        try:
            t1 = dt.datetime.fromisoformat(str(m.get("kickoff", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if abs((t1 - t0).total_seconds()) > 3600:
            continue
        punti = len(tc & _token_squadra(m.get("home"))) + len(to & _token_squadra(m.get("away")))
        if punti > punti_max:
            migliore, punti_max = m, punti
    return migliore


def righe_partita(token, match_id, fixture_id):
    """Scarica una partita e restituisce le righe nel formato del motore di analisi."""
    d = _get(f"match/{match_id}", token)
    righe = []
    for mercato in d.get("markets") or []:
        categoria = MERCATI.get(mercato.get("name"))
        if not categoria or mercato.get("suspended"):
            continue
        for s in mercato.get("selections") or []:
            if not s.get("odds") or s.get("suspended") or not s.get("row"):
                continue
            m = re.fullmatch(r"(\d+)\+", str(s.get("rung", "")).strip())
            if not m:
                continue
            try:
                quota = float(s["odds"])
            except (TypeError, ValueError):
                continue
            if quota <= 1.0:
                continue
            righe.append({
                "fixture": str(fixture_id),
                "giocatore_raw": s["row"],
                "mercato": categoria,
                "linea": int(m.group(1)) - 0.5,
                "lato": "over",
                "book": "bet365.it",
                "quota": quota,
                "link": None,
                "aggiornata": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "inattiva": False,
            })
    return righe
