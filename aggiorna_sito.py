#!/usr/bin/env python3
"""Usato da GitHub ogni 15 minuti: aggiorna le quote e scrive docs/dati.json,
che la pagina del sito legge. Senza chiave genera dati di prova."""
import json
import os
import shutil
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)

from scova import aggiorna, demo  # noqa: E402


def main():
    with open(os.path.join(QUI, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    chiave = os.environ.get("ODDSPAPI_KEY", "").strip()
    if chiave:
        cfg["api_key"] = chiave
    if os.environ.get("APIFY_TOKEN", "").strip():
        cfg["apify_token"] = os.environ["APIFY_TOKEN"].strip()

    if aggiorna.chiave_valida(cfg):
        risultato = aggiorna.esegui(cfg)
    else:
        print("Nessuna chiave ODDSPAPI_KEY: genero dati di prova.")
        risultato = demo.genera(cfg)

    os.makedirs(os.path.join(QUI, "docs"), exist_ok=True)
    shutil.copyfile(aggiorna.FILE_ULTIMO, os.path.join(QUI, "docs", "dati.json"))
    print("Sito aggiornato:", risultato["aggiornato"])


if __name__ == "__main__":
    main()
