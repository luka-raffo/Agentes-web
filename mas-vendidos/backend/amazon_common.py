# -*- coding: utf-8 -*-
"""
Modulo comun de Amazon (espejo de meli_common para el parser/URLs).
Estrategia: buscar por NOMBRE de categoria (las mismas de MeLi) en Amazon y
ordenar por volumen de compra ("X comprados el mes pasado") para aproximar
"mas vendidos". Amazon no expone sort por unidades vendidas.

OJO paises: Amazon solo tiene marketplace local en Mexico (com.mx) y Brasil
(com.br). NO existe Amazon Argentina ni Uruguay -> se mapean a com.mx (espanol).
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

# pais (de MeLi) -> dominio Amazon
DOMINIOS = {"AR": "com.mx", "MX": "com.mx", "UY": "com.mx", "BR": "com.br"}
MONEDA_DE_PAIS = {"AR": "$", "MX": "$", "UY": "$", "BR": "R$"}

# La pagina real de captcha de Amazon trae este form; no aparece con resultados.
BLOCK_MARKERS = ("/errors/validateCaptcha", 'id="captchacharacters"',
                 "Enter the characters you see below",
                 "Escribe los caracteres que ves a continuaci")


def dominio(pais):
    return DOMINIOS.get((pais or "MX").upper(), "com.mx")


def moneda_de(pais):
    return MONEDA_DE_PAIS.get((pais or "MX").upper(), "$")


def url_busqueda(pais, query):
    """URL de busqueda de Amazon para una categoria (por nombre)."""
    return f"https://www.amazon.{dominio(pais)}/s?k={quote(query)}"


def esta_bloqueado(html):
    if not html:
        return True
    # Si hay resultados de busqueda, no esta bloqueado (evita falsos positivos).
    if "s-search-result" in html:
        return False
    return any(m in html for m in BLOCK_MARKERS)


def _txt(node):
    return node.get_text(strip=True) if node else ""


def _volumen(texto):
    """'2 k+ comprados el mes pasado' -> 2000 ; '900+' -> 900 ; '' -> 0."""
    if not texto:
        return 0
    t = texto.lower().replace(",", ".")
    m = re.search(r"([\d.]+)\s*(k|mil|m)?\+?", t)
    if not m:
        return 0
    try:
        n = float(m.group(1))
    except ValueError:
        return 0
    suf = m.group(2)
    if suf in ("k", "mil"):
        n *= 1000
    elif suf == "m":
        n *= 1_000_000
    return int(n)


def _precio_moneda(texto, pais):
    """'$345.00' -> ('$', '345.00') ; 'R$ 1.299,90' -> ('R$', '1.299,90')."""
    if not texto:
        return moneda_de(pais), ""
    m = re.match(r"\s*([^\d]*)\s*([\d.,]+)", texto)
    if not m:
        return moneda_de(pais), ""
    sim = (m.group(1) or "").strip() or moneda_de(pais)
    return sim, m.group(2)


def parsear_productos(html, pais="MX", limite=30):
    """Parsea resultados de busqueda de Amazon -> lista de dicts (mismo shape que
    MeLi). Descarta patrocinados y ordena por volumen de compra descendente."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div[data-component-type='s-search-result']")
    moneda_def = moneda_de(pais)
    dom = dominio(pais)

    items = []
    for card in cards:
        texto_card = card.get_text(" ", strip=True)
        # Saltear anuncios (no son "mas vendidos" organicos)
        if "Patrocinado" in texto_card or "Sponsored" in texto_card:
            continue

        h2 = card.select_one("h2")
        titulo = _txt(h2.select_one("span")) if h2 else ""
        a = (card.select_one("h2 a")
             or card.select_one("a.a-link-normal.s-no-outline")
             or card.select_one("a.a-link-normal[href*='/dp/']"))
        href = (a.get("href") if a else "") or ""
        if not titulo or not href:
            continue
        link = href.split("?")[0]
        if link.startswith("/"):
            link = f"https://www.amazon.{dom}{link}"
        asin = card.get("data-asin", "")

        sim, precio = _precio_moneda(_txt(card.select_one("span.a-price span.a-offscreen")), pais)

        rating_raw = _txt(card.select_one("span.a-icon-alt"))
        mr = re.search(r"\d[.,]\d", rating_raw)
        rating = mr.group(0) if mr else ""

        # Conteo de resenas: link de calificaciones (aria-label numerico)
        reviews = ""
        rlink = card.select_one("a[href*='#customerReviews'] span.a-size-base") \
            or card.select_one("span.a-size-base.s-underline-text")
        if rlink:
            reviews = _txt(rlink)

        # "X comprados el mes pasado" -> volumen + texto
        comprados = ""
        for sp in card.select("span"):
            tx = sp.get_text(strip=True)
            if ("comprad" in tx.lower() or "bought" in tx.lower()) and len(tx) < 60:
                comprados = tx
                break
        vol = _volumen(comprados)

        badge = _txt(card.select_one("span.a-badge-text"))

        img_el = card.select_one("img.s-image")
        imagen = img_el.get("src", "") if img_el else ""

        items.append({
            "highlight": badge,                 # "Mas vendido" / "Opcion" / ""
            "titulo": titulo,
            "moneda": sim or moneda_def,
            "precio": precio,
            "precio_original": "",
            "descuento": "",
            "cuotas": "",
            "vendidos": comprados,              # texto "X comprados el mes pasado"
            "_vol": vol,                        # numerico, para ordenar
            "rating": rating,
            "reviews": reviews,
            "envio": "",
            "vendedor": "",
            "mla_id": asin,                     # ASIN (reutiliza el campo)
            "catalogo_id": "",
            "link": link,
            "imagen": imagen,
        })

    # Ordenar por volumen de compra desc (los "mas vendidos" arriba), luego rating.
    items.sort(key=lambda p: (p["_vol"], _volumen(p["rating"])), reverse=True)
    out = []
    for i, p in enumerate(items[:limite], 1):
        p["ranking"] = i
        p.pop("_vol", None)
        out.append(p)
    return out
