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

URL_TPL = "https://www.mercadolibre.com.ar/mas-vendidos/{cat_id}"
BLOCK_MARKERS = ("suspicious-traffic", "verifyChallenge", "account-verification",
                 "micro-landing-container")


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
                "Ranking": p["ranking"],
                "Titulo": p["titulo"],
                "Precio": p["precio"],
                "Precio_original": p.get("precio_original", ""),
                "Descuento": p.get("descuento", ""),
                "Vendedor_Marca": p.get("vendedor", ""),
                "Rating": p.get("rating", ""),
                "Reviews": p.get("reviews", ""),
                "MLA_ID": p.get("mla_id", ""),
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
            a = card.find("a", href=re.compile(r"mercadolibre|MLA"))
        if not a:
            continue
        titulo = _txt(a) or a.get("title", "")
        link = (a.get("href") or "").split("#")[0].split("?")[0]
        if not titulo or not link:
            continue

        mla = re.search(r"MLA-?\d+", link)
        mla_id = mla.group(0).replace("-", "") if mla else ""

        precios = card.select("span.andes-money-amount__fraction")
        precio = _txt(precios[0]) if precios else ""
        precio_orig = _txt(precios[1]) if len(precios) > 1 else ""

        desc = _txt(card.select_one(
            "span.andes-money-amount__discount, .poly-price__disc"))
        vendedor = _txt(card.select_one(
            ".poly-component__seller, .poly-component__brand"))
        rating = _txt(card.select_one(".poly-reviews__rating"))
        reviews = _txt(card.select_one(".poly-reviews__total")).strip("()")

        img_el = card.find("img")
        imagen = (img_el.get("data-src") or img_el.get("src") or "") if img_el else ""

        productos.append({
            "ranking": i,
            "titulo": titulo,
            "precio": precio,
            "precio_original": precio_orig,
            "descuento": desc,
            "vendedor": vendedor,
            "rating": rating,
            "reviews": reviews,
            "mla_id": mla_id,
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
        "url": URL_TPL.format(cat_id=cat_id),
        "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "productos": productos,
    }
