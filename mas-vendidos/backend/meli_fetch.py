# -*- coding: utf-8 -*-
"""
Motor de descarga de MercadoLibre (curl_cffi + proof-of-work de DataDome).
Compartido por el scraper CLI (scraper_l1.py) y el backend (api.py).
"""

import hashlib
import random
import time
from urllib.parse import quote, unquote

from curl_cffi import requests

import meli_common as mc

MAX_RETRIES = 4
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def solve_pow(n_str, diff):
    """Resuelve el proof-of-work SHA256 de BotManager: hash que empieza con N ceros."""
    target = "0" * int(diff)
    r = 0
    while True:
        h = hashlib.sha256((n_str + str(r)).encode("utf-8")).hexdigest()
        if h.startswith(target):
            return r
        r += 1


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def obtener_html(url, log=print, max_retries=MAX_RETRIES, backoff_base=8, backoff_max=24):
    """Devuelve (status, html) resolviendo el PoW de BotManager si aparece.

    max_retries / backoff_*: la API usa valores chicos (falla rapido); el modo
    lote usa los grandes por defecto (mas insistente).
    """
    session = requests.Session(impersonate="chrome")
    session.headers.update(_headers())

    for intento in range(1, max_retries + 1):
        try:
            res = session.get(url, timeout=30, allow_redirects=True)
            html = res.text

            if mc.esta_bloqueado(html):
                bmstate = session.cookies.get("_bmstate")
                if bmstate:
                    dec = unquote(bmstate).split(";")
                    if len(dec) >= 2:
                        n_str, diff = dec[0], dec[1]
                        log(f"      resolviendo PoW (dificultad {diff})...")
                        r = solve_pow(n_str, diff)
                        session.cookies.set("_bmc", quote(f"{n_str};{r}"))
                        session.cookies.set("_bm_skipml", "true")
                        time.sleep(random.uniform(1.0, 2.5))
                        res = session.get(url, timeout=30, allow_redirects=True)
                        html = res.text

                if mc.esta_bloqueado(html):
                    espera = min(backoff_base * intento, backoff_max)
                    log(f"      [{intento}/{max_retries}] sigue bloqueado; "
                        f"espero {espera}s y reintento...")
                    time.sleep(espera)
                    session = requests.Session(impersonate="chrome")
                    session.headers.update(_headers())
                    continue

            return res.status_code, html
        except Exception as e:
            log(f"      error de red ({e}); reintento...")
            time.sleep(5)

    return 0, ""


def scrapear_categoria(cat_id, log=print, **kw):
    """Descarga y parsea una categoria.

    Retorna (estado, productos):
      estado = "ok" | "bloqueado" | "vacio"
    kw extra (max_retries, backoff_base, backoff_max) se pasan a obtener_html.
    """
    url = mc.url_mas_vendidos(cat_id)
    status, html = obtener_html(url, log=log, **kw)

    if not html or mc.esta_bloqueado(html):
        return "bloqueado", []

    productos = mc.parsear_productos(html)
    if not productos:
        return "vacio", []
    return "ok", productos
