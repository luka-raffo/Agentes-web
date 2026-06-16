# -*- coding: utf-8 -*-
"""
Genera el catalogo de categorias de un sitio de MercadoLibre (L1+L2+L3)
usando la API OFICIAL de categorias (no bloqueada por DataDome).

Salida: categorias_<pais>.json  ->  lista de {id, nombre, nivel, ruta}

Credenciales: toma MELI_CLIENT_ID / MELI_CLIENT_SECRET del entorno; si no estan,
intenta leerlas de ../API_Scraper_Test/.env. No se hardcodean en el repo.

Uso:
    py fetch_categorias.py MLM      # Mexico  -> categorias_mx.json
    py fetch_categorias.py MLA      # Argentina (arbol completo) -> categorias_ar_full.json
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

PAIS_OF = {"MLA": "AR", "MLM": "MX", "MLU": "UY", "MLB": "BR"}
API = "https://api.mercadolibre.com"


def _leer_env_credenciales():
    cid = os.environ.get("MELI_CLIENT_ID")
    csec = os.environ.get("MELI_CLIENT_SECRET")
    if cid and csec:
        return cid, csec
    # fallback: ../API_Scraper_Test/.env (formato: lineas "App ID"\n<valor>, etc.)
    env_path = os.path.join(os.path.dirname(__file__), "..", "API_Scraper_Test", ".env")
    if os.path.exists(env_path):
        lines = [l.strip() for l in open(env_path, encoding="utf-8")]
        try:
            cid = cid or lines[lines.index("App ID") + 1]
            csec = csec or lines[lines.index("Client Secret") + 1]
        except (ValueError, IndexError):
            pass
    return cid, csec


def get_token():
    cid, csec = _leer_env_credenciales()
    if not cid or not csec:
        sys.exit("Faltan credenciales: define MELI_CLIENT_ID y MELI_CLIENT_SECRET.")
    r = requests.post(f"{API}/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": cid, "client_secret": csec,
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def hijos(cat_id, headers):
    """Devuelve la lista de children_categories [{id,name}] de una categoria."""
    for intento in range(3):
        try:
            r = requests.get(f"{API}/categories/{cat_id}", headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json().get("children_categories", []) or []
            time.sleep(1)
        except Exception:
            time.sleep(2)
    return []


def main():
    site = sys.argv[1].upper() if len(sys.argv) > 1 else "MLM"
    pais = PAIS_OF.get(site, site)
    headers = {"Authorization": f"Bearer {get_token()}"}
    print(f"Generando arbol de {site} ({pais})...")

    # L1
    r = requests.get(f"{API}/sites/{site}/categories", headers=headers, timeout=30)
    r.raise_for_status()
    l1 = r.json()
    print(f"  L1: {len(l1)} categorias")

    catalogo = {}  # id -> dict (dedup por id)

    def add(cid, nombre, nivel, ruta):
        if cid and cid not in catalogo:
            catalogo[cid] = {"id": cid, "nombre": nombre, "nivel": nivel,
                             "vertical": "", "ruta": ruta}

    for c in l1:
        add(c["id"], c["name"], "L1", c["name"])

    # L2: hijos de cada L1 (en paralelo)
    def trae_l2(c):
        return c, hijos(c["id"], headers)
    l2_all = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for c1, l2 in ex.map(trae_l2, l1):
            for c2 in l2:
                add(c2["id"], c2["name"], "L2", f"{c1['name']} > {c2['name']}")
                l2_all.append((c1, c2))
    print(f"  L2: {sum(1 for v in catalogo.values() if v['nivel']=='L2')} categorias")

    # L3: hijos de cada L2 (en paralelo)
    def trae_l3(pair):
        c1, c2 = pair
        return c1, c2, hijos(c2["id"], headers)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for c1, c2, l3 in ex.map(trae_l3, l2_all):
            for c3 in l3:
                add(c3["id"], c3["name"], "L3",
                    f"{c1['name']} > {c2['name']} > {c3['name']}")
    print(f"  L3: {sum(1 for v in catalogo.values() if v['nivel']=='L3')} categorias")

    out = os.path.join(os.path.dirname(__file__), f"categorias_{pais.lower()}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(list(catalogo.values()), f, ensure_ascii=False, indent=1)
    print(f"OK: {len(catalogo)} categorias -> {out}")


if __name__ == "__main__":
    main()
