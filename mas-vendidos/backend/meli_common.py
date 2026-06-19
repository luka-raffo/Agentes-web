# -*- coding: utf-8 -*-
"""
Modulo comun de Scrapper Meli L1.
Contiene: carga de categorias, parseo de productos, guardado JSON/Excel y resume.
NO importa playwright (roto en Python 3.14): solo bs4/pandas.
"""

import csv
import json
import os
import re
from datetime import datetime

from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "NN AI - Verticales MELI.csv")
OUT_JSON = os.path.join(BASE_DIR, "resultados_l1.json")
OUT_XLSX = os.path.join(BASE_DIR, "resultados_l1.xlsx")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")

URL_TPL = "https://www.mercadolibre.com.ar/mas-vendidos/{cat_id}"  # compat
BLOCK_MARKERS = ("suspicious-traffic", "verifyChallenge", "account-verification",
                 "micro-landing-container")

# Base de "mas vendidos" por prefijo de ID.
# OJO Brasil: dominio mercadoLIVRE (no libre) y ruta MAIS-vendidos (no mas-).
SITIOS = {
    "MLA": "https://www.mercadolibre.com.ar/mas-vendidos/",
    "MLM": "https://www.mercadolibre.com.mx/mas-vendidos/",
    "MLU": "https://www.mercadolibre.com.uy/mas-vendidos/",
    "MLB": "https://www.mercadolivre.com.br/mais-vendidos/",
}
PAIS_DE_PREFIJO = {"MLA": "AR", "MLM": "MX", "MLU": "UY", "MLB": "BR"}


def url_mas_vendidos(cat_id):
    return SITIOS.get(cat_id[:3], SITIOS["MLA"]) + cat_id


# ----------------------- Categorias -----------------------
def cargar_categorias_l1():
    """Lista [(id, nombre)] de categorias L1 unicas, en orden de aparicion."""
    vistas = {}
    with open(CSV_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = (row.get("L1 ID") or "").strip()
            if cid and cid not in vistas:
                vistas[cid] = (row.get("L1 Nombre") or "").strip()
    return list(vistas.items())


def cargar_categorias_todas():
    """Todas las categorias unicas del CSV (L1+L2+L3), con nivel, vertical y ruta.

    Devuelve lista de dicts: {id, nombre, nivel, vertical, ruta}.
    Dedup por ID (primera aparicion gana).
    """
    vistas = {}
    with open(CSV_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vert = (row.get("Vertical") or "").strip()
            l1n = (row.get("L1 Nombre") or "").strip()
            l2n = (row.get("L2 Nombre") or "").strip()
            l3n = (row.get("L3 Nombre") or "").strip()
            niveles = (
                ("L1", row.get("L1 ID"), l1n, l1n),
                ("L2", row.get("L2 ID"), l2n, " > ".join(filter(None, [l1n, l2n]))),
                ("L3", row.get("L3 ID"), l3n, " > ".join(filter(None, [l1n, l2n, l3n]))),
            )
            for nivel, idc, nombre, ruta in niveles:
                cid = (idc or "").strip()
                if cid and cid not in vistas:
                    vistas[cid] = {"id": cid, "nombre": nombre, "nivel": nivel,
                                   "vertical": vert, "ruta": ruta, "pais": "AR"}
    return list(vistas.values())


def cargar_catalogo(pais="AR"):
    """Catalogo de categorias por pais. Lee categorias_<pais>.json (arbol completo
    de la API de ML, hasta 7 niveles). Para AR, si no existe el JSON, cae al CSV."""
    pais = (pais or "AR").upper()
    path = os.path.join(BASE_DIR, f"categorias_{pais.lower()}.json")
    if not os.path.exists(path):
        return cargar_categorias_todas() if pais == "AR" else []
    with open(path, encoding="utf-8") as f:
        cats = json.load(f)
    for c in cats:
        c.setdefault("pais", pais)
    return cats


# ----------------------- Progreso -----------------------
def cargar_progreso():
    if os.path.exists(OUT_JSON):
        try:
            with open(OUT_JSON, encoding="utf-8") as f:
                data = json.load(f)
            hechas = {d["categoria_id"] for d in data if d.get("productos")}
            return data, hechas
        except (json.JSONDecodeError, KeyError):
            pass
    return [], set()


def guardar(resultados):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    exportar_excel(resultados)


def upsert(resultados, data):
    """Reemplaza la categoria si existia; agrega si no. Devuelve lista nueva."""
    out = [r for r in resultados if r["categoria_id"] != data["categoria_id"]]
    out.append(data)
    return out


def exportar_excel(resultados):
    try:
        import pandas as pd
    except ImportError:
        return
    filas = []
    for cat in resultados:
        for p in cat["productos"]:
            filas.append({
                "Categoria_ID": cat["categoria_id"],
                "Categoria": cat["categoria"],
                "Pais": cat.get("pais", ""),
                "Ranking": p["ranking"],
                "Mas_vendido": p.get("highlight", ""),
                "Titulo": p["titulo"],
                "Moneda": p.get("moneda", ""),
                "Precio": p["precio"],
                "Precio_original": p.get("precio_original", ""),
                "Descuento": p.get("descuento", ""),
                "Cuotas": p.get("cuotas", ""),
                "Cantidad_vendida": p.get("vendidos", ""),
                "Rating": p.get("rating", ""),
                "Reviews": p.get("reviews", ""),
                "Envio": p.get("envio", ""),
                "Vendedor_Marca": p.get("vendedor", ""),
                "MLA_ID": p.get("mla_id", ""),
                "Catalogo_ID": p.get("catalogo_id", ""),
                "Link": p["link"],
                "Imagen": p.get("imagen", ""),
                "Fecha": cat["fecha_extraccion"],
            })
    if filas:
        pd.DataFrame(filas).to_excel(OUT_XLSX, index=False)


# ----------------------- Parseo -----------------------
def _txt(node):
    return node.get_text(strip=True) if node else ""


def esta_bloqueado(html):
    return any(m in html for m in BLOCK_MARKERS)


def parsear_productos(html):
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.poly-card") or soup.select("li.ui-search-layout__item")

    productos = []
    for i, card in enumerate(cards, 1):
        a = (card.select_one("a.poly-component__title")
             or card.select_one("h2.poly-component__title a")
             or card.select_one("a.ui-search-link"))
        if not a:
            a = card.find("a", href=re.compile(r"mercadoli[bv]re|ML[ABMU]\d"))
        if not a:
            continue
        titulo = _txt(a) or a.get("title", "")
        link = (a.get("href") or "").split("#")[0].split("?")[0]
        if not titulo or not link:
            continue

        mla = re.search(r"ML[ABMU]-?\d+", link)
        mla_id = mla.group(0).replace("-", "") if mla else ""
        catm = re.search(r"/p/(ML[ABMU]\d+)", link)
        catalogo_id = catm.group(1) if catm else ""

        texto_card = card.get_text(" ", strip=True)

        # Posicion / badge "N° MÁS VENDIDO"
        highlight = _txt(card.select_one(".poly-component__highlight"))

        # Precio actual + moneda
        cur = card.select_one(".poly-price__current") or card
        precio = _txt(cur.select_one(".andes-money-amount__fraction"))
        moneda = _txt(cur.select_one(".andes-money-amount__currency-symbol"))
        # Precio anterior (tachado) y descuento
        prev = card.select_one("s.andes-money-amount .andes-money-amount__fraction")
        precio_orig = _txt(prev)
        desc = _txt(card.select_one(".andes-money-amount__discount, .poly-price__disc"))
        # Cuotas
        cuotas = _txt(card.select_one(".poly-price__installments"))

        # Rating, cantidad de opiniones y cantidad vendida
        rc = _txt(card.select_one(".poly-component__review-compacted")) \
            or _txt(card.select_one(".poly-reviews, .poly-component__reviews"))
        mr = re.search(r"\d[.,]\d", rc) if rc else None
        rating = mr.group(0) if mr else _txt(card.select_one(".poly-reviews__rating"))
        mp = re.search(r"\(([\d.,]+)\)", rc) if rc else None
        reviews = mp.group(1) if mp else ""
        mv = re.search(r"\+?\s?[\d.,]+\s*(?:mil|millones)?\s*vendidos", texto_card, re.I)
        vendidos = mv.group(0).strip() if mv else ""

        # Envio y vendedor/marca
        env_el = card.select_one(".poly-component__shipping")
        envio = env_el.get_text(" ", strip=True) if env_el else ""
        vendedor = _txt(card.select_one(".poly-component__seller, .poly-component__brand"))

        img_el = card.find("img")
        imagen = (img_el.get("data-src") or img_el.get("src") or "") if img_el else ""

        productos.append({
            "ranking": i,
            "highlight": highlight,
            "titulo": titulo,
            "moneda": moneda,
            "precio": precio,
            "precio_original": precio_orig,
            "descuento": desc,
            "cuotas": cuotas,
            "vendidos": vendidos,
            "rating": rating,
            "reviews": reviews,
            "envio": envio,
            "vendedor": vendedor,
            "mla_id": mla_id,
            "catalogo_id": catalogo_id,
            "link": link,
            "imagen": imagen,
        })
    return productos


def guardar_debug(cat_id, html):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    with open(os.path.join(DEBUG_DIR, f"{cat_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def registro_categoria(cat_id, cat_name, productos):
    return {
        "categoria_id": cat_id,
        "categoria": cat_name,
        "pais": PAIS_DE_PREFIJO.get(cat_id[:3], ""),
        "url": url_mas_vendidos(cat_id),
        "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "productos": productos,
    }
