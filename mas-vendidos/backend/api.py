# -*- coding: utf-8 -*-
"""
Backend a demanda - Scrapper Meli
=================================
API HTTP que recibe UNA categoria y devuelve sus productos mas vendidos.

Reutiliza el mismo motor que el scraper CLI (curl_cffi + proof-of-work DataDome).

Levantar el servidor:
    py -m uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /                         -> info
    GET  /health                   -> {"status":"ok"}
    GET  /categorias               -> lista de categorias conocidas del CSV
    GET  /mas-vendidos/{cat_id}    -> productos mas vendidos de esa categoria
         ?nocache=1                -> ignora cache y vuelve a scrapear
    POST /mas-vendidos             -> body {"categoria": "MLA1000"}

Ejemplo:
    GET http://localhost:8000/mas-vendidos/MLA1000

Respuesta:
    {
      "categoria_id": "MLA1000",
      "categoria": "Electrónica, Audio y Video",
      "url": "https://www.mercadolibre.com.ar/mas-vendidos/MLA1000",
      "cantidad": 20,
      "cacheado": false,
      "productos": [ {ranking, titulo, precio, ...}, ... ]
    }
"""

import csv
import os
import re
import threading
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import meli_common as mc
import meli_fetch as mf

CACHE_TTL_S = 600          # 10 min: respuestas cacheadas para no re-scrapear de mas
CAT_ID_RE = re.compile(r"^MLA\d+$")

app = FastAPI(title="Scrapper Meli - Más vendidos a demanda", version="1.0")

# CORS abierto para que la web pueda consumirlo desde el navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ----------------------- Catalogo de categorias (todos los niveles del CSV) ---
def _cargar_nombres():
    nombres = {}
    try:
        with open(mc.CSV_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for idc, namec in (("L1 ID", "L1 Nombre"),
                                   ("L2 ID", "L2 Nombre"),
                                   ("L3 ID", "L3 Nombre")):
                    cid = (row.get(idc) or "").strip()
                    if cid and cid not in nombres:
                        nombres[cid] = (row.get(namec) or "").strip()
    except FileNotFoundError:
        pass
    return nombres

NOMBRES = _cargar_nombres()

# ----------------------- Cache simple en memoria con TTL -----------------------
_cache = {}            # cat_id -> (timestamp, payload)
_locks = {}            # cat_id -> Lock (evita scrapear la misma cat en paralelo)
_locks_guard = threading.Lock()


def _lock_de(cat_id):
    with _locks_guard:
        if cat_id not in _locks:
            _locks[cat_id] = threading.Lock()
        return _locks[cat_id]


class CategoriaIn(BaseModel):
    categoria: str


def _resolver(cat_id: str, nocache: bool):
    cat_id = cat_id.strip().upper()
    if not CAT_ID_RE.match(cat_id):
        raise HTTPException(status_code=400,
                            detail=f"ID de categoria invalido: '{cat_id}'. "
                                   "Debe tener formato MLA seguido de numeros, ej. MLA1000.")

    # cache hit
    if not nocache:
        hit = _cache.get(cat_id)
        if hit and (time.time() - hit[0]) < CACHE_TTL_S:
            payload = dict(hit[1])
            payload["cacheado"] = True
            return payload

    # Un solo scrape simultaneo por categoria
    with _lock_de(cat_id):
        # revisar de nuevo por si otro hilo ya lo trajo mientras esperabamos el lock
        if not nocache:
            hit = _cache.get(cat_id)
            if hit and (time.time() - hit[0]) < CACHE_TTL_S:
                payload = dict(hit[1])
                payload["cacheado"] = True
                return payload

        # Reintentos cortos: una API no debe colgar 80s. Si bloquea, 503 rapido.
        estado, productos = mf.scrapear_categoria(
            cat_id, max_retries=2, backoff_base=4, backoff_max=6)
        if estado == "bloqueado":
            raise HTTPException(status_code=503,
                                detail="MercadoLibre bloqueo la peticion (DataDome). "
                                       "Reintenta en unos segundos.")

        payload = {
            "categoria_id": cat_id,
            "categoria": NOMBRES.get(cat_id, ""),
            "url": mc.URL_TPL.format(cat_id=cat_id),
            "cantidad": len(productos),
            "cacheado": False,
            "productos": productos,
        }
        _cache[cat_id] = (time.time(), payload)
        return payload


# ----------------------- Endpoints -----------------------
@app.get("/")
def root():
    return {
        "servicio": "Scrapper Meli - mas vendidos a demanda",
        "uso": "GET /mas-vendidos/MLA1000",
        "endpoints": ["/health", "/categorias", "/mas-vendidos/{cat_id}",
                      "POST /mas-vendidos"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/categorias")
def categorias():
    """Categorias L1 (raiz) del CSV, las recomendadas para consultar."""
    return [{"id": cid, "nombre": nom} for cid, nom in mc.cargar_categorias_l1()]


@app.get("/mas-vendidos/{cat_id}")
def mas_vendidos(cat_id: str, nocache: int = Query(0)):
    return _resolver(cat_id, nocache=bool(nocache))


@app.post("/mas-vendidos")
def mas_vendidos_post(body: CategoriaIn):
    return _resolver(body.categoria, nocache=False)
