"""Client minimale per l'API OddsPapi v4 (solo libreria standard)."""
import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.oddspapi.io/v4"
SPORT_CALCIO = 10


class ErroreAPI(Exception):
    pass


class OddsPapi:
    def __init__(self, api_key, pausa=1.0, log=print):
        self.api_key = api_key
        self.pausa = pausa
        self.log = log
        self.richieste = 0

    def get(self, percorso, **params):
        params["apiKey"] = self.api_key
        url = f"{BASE_URL}/{percorso}?{urllib.parse.urlencode(params)}"
        for tentativo in range(4):
            self.richieste += 1
            try:
                with urllib.request.urlopen(url, timeout=180) as r:
                    dati = json.loads(r.read().decode("utf-8"))
                time.sleep(self.pausa)
                return dati
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    attesa = 5 * (tentativo + 1)
                    self.log(f"  limite richieste raggiunto, aspetto {attesa}s...")
                    time.sleep(attesa)
                    continue
                if e.code == 404:
                    return None
                if e.code in (401, 403):
                    raise ErroreAPI("Chiave API non valida o piano non abilitato "
                                    f"(HTTP {e.code}). Controlla config.json.")
                corpo = e.read().decode("utf-8", "ignore")[:300]
                raise ErroreAPI(f"HTTP {e.code} su /{percorso}: {corpo}")
            except urllib.error.URLError as e:
                if tentativo == 3:
                    raise ErroreAPI(f"Connessione fallita: {e.reason}")
                time.sleep(3)
        raise ErroreAPI(f"Troppe richieste rifiutate su /{percorso}")

    # ---- endpoint -------------------------------------------------------
    def mercati(self):
        """Catalogo mercati: lista di {marketId, marketName, handicap, outcomes...}."""
        dati = self.get("markets", sportId=SPORT_CALCIO) or []
        return dati if isinstance(dati, list) else dati.get("data", [])

    def tornei(self):
        dati = self.get("tournaments", sportId=SPORT_CALCIO) or []
        return dati if isinstance(dati, list) else dati.get("data", [])

    def partite(self, torneo_id, da, a):
        dati = self.get("fixtures", tournamentId=torneo_id, **{"from": da, "to": a}) or []
        return dati if isinstance(dati, list) else dati.get("data", [])

    def quote(self, fixture_id, bookmakers):
        return self.get("odds", fixtureId=fixture_id, bookmakers=",".join(bookmakers)) or {}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


def trova_tornei(api, competizioni, log=print):
    """Restituisce {id: nome} risolvendo per nome+paese quelle senza id."""
    risultato = {}
    competizioni = [c for c in competizioni if c.get("attiva", True)]
    da_cercare = [c for c in competizioni if not c.get("id")]
    for c in competizioni:
        if c.get("id"):
            risultato[int(c["id"])] = c["nome"]
    if not da_cercare:
        return risultato
    try:
        elenco = api.tornei()
    except ErroreAPI as e:
        log(f"  impossibile leggere l'elenco tornei: {e}")
        return risultato
    for c in da_cercare:
        nome, paese = _norm(c["nome"]), _norm(c.get("paese"))
        candidati = []
        for t in elenco:
            tnome = _norm(t.get("tournamentName") or t.get("name"))
            tpaese = _norm(t.get("categoryName") or t.get("category") or t.get("country"))
            if tnome == nome and (not paese or paese in tpaese or tpaese in paese):
                candidati.append(t)
        if candidati:
            tid = candidati[0].get("tournamentId") or candidati[0].get("id")
            risultato[int(tid)] = c["nome"]
        else:
            log(f"  competizione non trovata: {c['nome']} ({c.get('paese')}) "
                "- metti l'id a mano in config.json")
    return risultato
