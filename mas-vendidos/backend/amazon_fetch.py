# -*- coding: utf-8 -*-
"""
Motor de descarga de Amazon (curl_cffi impersonate chrome).
Amazon NO usa DataDome (no hay proof-of-work); su anti-bot es un captcha.
Si aparece, reintenta con sesion nueva. Espejo de meli_fetch.
"""
import random
import time

from curl_cffi import requests

import amazon_common as az

MAX_RETRIES = 3
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _headers(pais):
    lang = "pt-BR,pt;q=0.9,en;q=0.8" if (pais or "").upper() == "BR" \
        else "es-MX,es;q=0.9,en;q=0.8"
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": lang,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def obtener_html(url, pais="MX", log=print, max_retries=MAX_RETRIES,
                 backoff_base=4, backoff_max=12):
    """Devuelve (status, html). Reintenta con sesion nueva si Amazon muestra captcha."""
    for intento in range(1, max_retries + 1):
        try:
            session = requests.Session(impersonate="chrome")
            session.headers.update(_headers(pais))
            res = session.get(url, timeout=30, allow_redirects=True)
            html = res.text
            if not az.esta_bloqueado(html):
                return res.status_code, html
            espera = min(backoff_base * intento, backoff_max)
            log(f"      [{intento}/{max_retries}] Amazon pidio captcha; "
                f"espero {espera}s y reintento...")
            time.sleep(espera)
        except Exception as e:
            log(f"      error de red ({e}); reintento...")
            time.sleep(4)
    return 0, ""


def buscar(pais, query, log=print, vacio_reintentos=2, **kw):
    """Busca una categoria (por nombre) en Amazon.

    Retorna (estado, productos): estado = "ok" | "bloqueado" | "vacio".
    Una busqueda por categoria casi siempre tiene resultados; si vuelve vacia
    suele ser throttle blando -> reintenta con sesion nueva.
    kw extra (max_retries, backoff_base, backoff_max) van a obtener_html.
    """
    url = az.url_busqueda(pais, query)
    for intento in range(vacio_reintentos + 1):
        status, html = obtener_html(url, pais=pais, log=log, **kw)
        if not html or az.esta_bloqueado(html):
            return "bloqueado", []
        productos = az.parsear_productos(html, pais=pais)
        if productos:
            return "ok", productos
        if intento < vacio_reintentos:
            log(f"      busqueda vacia; reintento {intento + 1}/{vacio_reintentos}...")
            time.sleep(random.uniform(2.0, 4.0))
    return "vacio", []
