"""Un ciclo completo: scarica partite e quote, analizza, salva dati/ultimo.json."""
import datetime as dt
import json
import os
import time

from . import analisi
from .oddspapi import OddsPapi, ErroreAPI, trova_tornei

CARTELLA_DATI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dati")
FILE_ULTIMO = os.path.join(CARTELLA_DATI, "ultimo.json")
FILE_CATALOGO = os.path.join(CARTELLA_DATI, "catalogo_mercati.json")
FILE_SCONOSCIUTI = os.path.join(CARTELLA_DATI, "mercati_non_riconosciuti.txt")


def chiave_valida(cfg):
    k = (cfg.get("api_key") or "").strip()
    return bool(k) and not k.startswith("INCOLLA")


def _salva(percorso, dati):
    os.makedirs(CARTELLA_DATI, exist_ok=True)
    tmp = percorso + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, percorso)


def leggi_ultimo():
    try:
        with open(FILE_ULTIMO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def catalogo_mercati(api, log):
    """Catalogo dei mercati, tenuto in cache per 30 giorni (cambia raramente)."""
    if os.path.exists(FILE_CATALOGO) and time.time() - os.path.getmtime(FILE_CATALOGO) < 30 * 86400:
        with open(FILE_CATALOGO, encoding="utf-8") as f:
            return json.load(f)
    log("Scarico il catalogo dei mercati...")
    catalogo = {}
    for m in api.mercati():
        esiti = {}
        for o in m.get("outcomes") or []:
            esiti[str(o.get("outcomeId"))] = o.get("outcomeName")
        catalogo[str(m.get("marketId"))] = {
            "nome": m.get("marketName") or "",
            "handicap": m.get("handicap"),
            "tipo": m.get("marketType"),
            "periodo": m.get("period"),
            "giocatore": bool(m.get("playerProp")),
            "esiti": esiti,
        }
    _salva(FILE_CATALOGO, catalogo)
    return catalogo


def esegui(cfg, log=print):
    inizio = time.time()
    api = OddsPapi(cfg["api_key"], cfg.get("pausa_tra_richieste_secondi", 1.0), log)
    precedente = leggi_ultimo()

    # contatore richieste del mese (per restare nel piano gratuito)
    mese = dt.date.today().strftime("%Y-%m")
    usate = (precedente or {}).get("richieste_mese", 0) if (precedente or {}).get("mese") == mese else 0
    limite = int(cfg.get("limite_richieste_mese", 240))

    def budget_ok(servono=1):
        return usate + api.richieste + servono <= limite

    catalogo = catalogo_mercati(api, log)
    utili = sum(1 for v in catalogo.values() if analisi.classifica_info(v))
    log(f"Mercati tiri/falli riconosciuti nel catalogo: {utili}")

    ora_utc = dt.datetime.now(dt.timezone.utc)
    adesso = ora_utc.strftime("%Y-%m-%dT%H:%M:%S")
    entro_lista = (ora_utc + dt.timedelta(hours=cfg.get("finestra_ore", 48))).strftime("%Y-%m-%dT%H:%M:%S")
    entro_quote = (ora_utc + dt.timedelta(hours=cfg.get("aggiorna_quote_entro_ore", 12))).strftime("%Y-%m-%dT%H:%M:%S")

    # calendario: riscaricato al massimo una volta ogni 20 ore (risparmia richieste)
    cal = (precedente or {}).get("calendario") or {}
    cal_eta = None
    try:
        cal_eta = (ora_utc - dt.datetime.fromisoformat(cal.get("aggiornato", "").replace("Z", "+00:00"))).total_seconds() / 3600
    except ValueError:
        pass
    elenco_partite = cal.get("partite", [])
    errori = []
    if cal_eta is None or cal_eta > 20 or not elenco_partite:
        tornei = trova_tornei(api, cfg["competizioni"], log)
        oggi = dt.date.today()
        da, a = oggi.isoformat(), (oggi + dt.timedelta(days=cfg.get("giorni_avanti", 4))).isoformat()
        elenco_partite = []
        for tid, nome_torneo in tornei.items():
            if not budget_ok():
                continue
            try:
                for f in api.partite(tid, da, a):
                    if f.get("hasOdds", True):
                        elenco_partite.append({
                            "id": str(f.get("fixtureId")),
                            "nome": f"{f.get('participant1Name', '?')} - {f.get('participant2Name', '?')}",
                            "competizione": nome_torneo,
                            "inizio": f.get("startTime", ""),
                        })
            except ErroreAPI as e:
                errori.append(f"{nome_torneo}: {e}")
        cal = {"aggiornato": ora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "partite": elenco_partite}
        log(f"Calendario aggiornato: {len(elenco_partite)} partite")

    future = [f for f in elenco_partite if adesso < str(f["inizio"]) <= entro_lista]
    da_aggiornare = [f for f in future if str(f["inizio"]) <= entro_quote]
    log(f"{len(future)} partite nelle prossime {cfg.get('finestra_ore', 48)} ore, "
        f"{len(da_aggiornare)} da aggiornare ora (entro {cfg.get('aggiorna_quote_entro_ore', 12)} ore)")

    partite, righe, sconosciuti = {}, [], set()
    saltate = 0
    for f in sorted(da_aggiornare, key=lambda x: x["inizio"]):
        if not budget_ok():
            saltate += 1
            continue
        partite[f["id"]] = dict(f)
        try:
            quote = api.quote(f["id"], cfg["bookmaker"])
        except ErroreAPI as e:
            errori.append(f"{f['nome']}: {e}")
            continue
        righe.extend(analisi.estrai_righe(partite[f["id"]], quote, catalogo, sconosciuti))
    if saltate:
        errori.insert(0, f"Limite di {limite} richieste al mese quasi raggiunto: {saltate} partite/competizioni "
                         "non aggiornate. Riparte da solo il mese prossimo (o alza limite_richieste_mese).")

    if sconosciuti:
        with open(FILE_SCONOSCIUTI, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(sconosciuti)))

    opp, arb = analisi.analizza(righe, partite, cfg, precedente)
    rif = getattr(analisi.analizza, "riferimento", [])
    # partite ancora future ma non riscaricate ora: tengo le quote dell'ultimo giro
    ids_future = {f["id"] for f in future}
    tenute = set()
    if precedente:
        for chiave, lista in (("opportunita", opp), ("riferimento", rif)):
            for o in precedente.get(chiave, []):
                fx = o["id"].split("|")[0]
                if fx in ids_future and fx not in partite:
                    lista.append(o)
                    tenute.add(fx)
    rango = {"alta": 0, "media": 1, "bassa": 2}
    opp.sort(key=lambda o: (rango.get(o.get("affidabilita"), 2) == 2, -o["valore_pct"], -o["differenza_pct"]))
    rif.sort(key=lambda r: -r["sopra_pct"])
    analisi.analizza.riferimento = rif
    if tenute:
        log(f"{len(tenute)} partite mostrate con le quote dell'ultimo aggiornamento")
    copertura = {}
    for r in righe:
        c = copertura.setdefault(r["book"], {m: 0 for m in analisi.NOMI_MERCATO})
        c[r["mercato"]] += 1

    risultato = {
        "demo": False,
        "aggiornato": dt.datetime.now().isoformat(timespec="seconds"),
        "aggiornato_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prossimo_tra_minuti": cfg.get("intervallo_minuti", 15),
        "durata_secondi": round(time.time() - inizio, 1),
        "richieste_api": api.richieste,
        "mese": mese,
        "richieste_mese": usate + api.richieste,
        "limite_richieste_mese": limite,
        "partite_analizzate": len(partite) + len(tenute),
        "calendario": cal,
        "quote_lette": len(righe),
        "copertura_bookmaker": copertura,
        "riferimento": getattr(analisi.analizza, "riferimento", []),
        "opportunita": opp,
        "arbitraggi": arb,
        "errori": errori[:20],
    }
    _salva(FILE_ULTIMO, risultato)
    log(f"Fatto: {len(partite)} partite, {len(righe)} quote, "
        f"{sum(o['segnale'] for o in opp)} segnalazioni, {len(arb)} arbitraggi, "
        f"{api.richieste} richieste API.")
    return risultato
