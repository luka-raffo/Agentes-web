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
import amazon_common as az
import amazon_fetch as azf

CACHE_TTL_S = 600          # 10 min: respuestas cacheadas para no re-scrapear de mas
CAT_ID_RE = re.compile(r"^ML[ABMU]\d+$")  # A=Argentina B=Brasil M=Mexico U=Uruguay

app = FastAPI(title="Scrapper Meli - Más vendidos a demanda", version="1.0")

# CORS abierto para que la web pueda consumirlo desde el navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ----------------------- Catalogo de nombres (AR + MX) -----------------------
def _cargar_nombres():
    nombres = {}
    for p in ("AR", "MX", "UY", "BR"):
        for c in mc.cargar_catalogo(p):
            nombres.setdefault(c["id"], c.get("nombre", ""))
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
    ecommerce: str = "meli"


def _scrapear(cat_id, ecommerce, pais, nombre):
    """Ejecuta el scrape segun la tienda. Devuelve (estado, productos, url)."""
    if ecommerce == "amazon":
        # Amazon: se busca por NOMBRE de categoria (las mismas de MeLi).
        if not nombre:
            raise HTTPException(status_code=404,
                                detail=f"No conozco el nombre de la categoria {cat_id} "
                                       "para buscarla en Amazon.")
        estado, productos = azf.buscar(
            pais, nombre, max_retries=2, backoff_base=3, backoff_max=6)
        return estado, productos, az.url_busqueda(pais, nombre)
    # MeLi (default)
    estado, productos = mf.scrapear_categoria(
        cat_id, max_retries=2, backoff_base=4, backoff_max=6)
    return estado, productos, mc.url_mas_vendidos(cat_id)


def _resolver(cat_id: str, nocache: bool, ecommerce: str = "meli"):
    cat_id = cat_id.strip().upper()
    ecommerce = (ecommerce or "meli").strip().lower()
    if ecommerce not in ("meli", "amazon"):
        ecommerce = "meli"
    if not CAT_ID_RE.match(cat_id):
        raise HTTPException(status_code=400,
                            detail=f"ID de categoria invalido: '{cat_id}'. "
                                   "Debe tener formato MLA seguido de numeros, ej. MLA1000.")

    clave = f"{ecommerce}:{cat_id}"   # la tienda forma parte de la clave de cache

    # cache hit
    if not nocache:
        hit = _cache.get(clave)
        if hit and (time.time() - hit[0]) < CACHE_TTL_S:
            payload = dict(hit[1])
            payload["cacheado"] = True
            return payload

    # Un solo scrape simultaneo por categoria+tienda
    with _lock_de(clave):
        # revisar de nuevo por si otro hilo ya lo trajo mientras esperabamos el lock
        if not nocache:
            hit = _cache.get(clave)
            if hit and (time.time() - hit[0]) < CACHE_TTL_S:
                payload = dict(hit[1])
                payload["cacheado"] = True
                return payload

        pais = mc.PAIS_DE_PREFIJO.get(cat_id[:3], "")
        nombre = NOMBRES.get(cat_id, "")
        # Reintentos cortos: una API no debe colgar 80s. Si bloquea, 503 rapido.
        estado, productos, url = _scrapear(cat_id, ecommerce, pais, nombre)
        if estado == "bloqueado":
            tienda = "Amazon" if ecommerce == "amazon" else "MercadoLibre"
            raise HTTPException(status_code=503,
                                detail=f"{tienda} bloqueo la peticion. "
                                       "Reintenta en unos segundos.")

        payload = {
            "categoria_id": cat_id,
            "categoria": nombre,
            "ecommerce": ecommerce,
            "pais": pais,
            "url": url,
            "cantidad": len(productos),
            "cacheado": False,
            "productos": productos,
        }
        _cache[clave] = (time.time(), payload)
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
def categorias(pais: str = Query("AR"), nivel: str = Query("todas")):
    """Categorias por pais y nivel.

    pais: AR (Argentina, del CSV) | MX (Mexico, del arbol API).
    nivel: todas (default) | l1 | l2 | l3.
    Devuelve {id, nombre, nivel, vertical, ruta, pais}.
    """
    nivel = (nivel or "todas").lower()
    todas = mc.cargar_catalogo(pais)
    if re.fullmatch(r"l\d", nivel):     # l1..l7 (AR llega a L7)
        todas = [c for c in todas if c["nivel"].lower() == nivel]
    return todas


@app.get("/paises")
def paises():
    """Paises disponibles."""
    return [{"codigo": "AR", "nombre": "Argentina"},
            {"codigo": "MX", "nombre": "México"},
            {"codigo": "UY", "nombre": "Uruguay"},
            {"codigo": "BR", "nombre": "Brasil"}]


@app.get("/tiendas")
def tiendas():
    """Ecommerces disponibles."""
    return [{"codigo": "meli", "nombre": "MercadoLibre"},
            {"codigo": "amazon", "nombre": "Amazon"}]


@app.get("/mas-vendidos/{cat_id}")
def mas_vendidos(cat_id: str, nocache: int = Query(0),
                 ecommerce: str = Query("meli")):
    return _resolver(cat_id, nocache=bool(nocache), ecommerce=ecommerce)


@app.post("/mas-vendidos")
def mas_vendidos_post(body: CategoriaIn):
    return _resolver(body.categoria, nocache=False, ecommerce=body.ecommerce)
