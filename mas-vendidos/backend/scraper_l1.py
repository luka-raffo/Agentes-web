# -*- coding: utf-8 -*-
"""
Scrapper Meli L1 - motor PRINCIPAL (curl_cffi), modo lote
=========================================================
Extrae el ranking de productos mas vendidos de las 29 categorias L1 del CSV,
desde https://www.mercadolibre.com.ar/mas-vendidos/<CAT_ID>

El motor de descarga (curl_cffi + proof-of-work de DataDome) vive en
meli_fetch.py y lo comparte con el backend (api.py).

Si una categoria queda bloqueada por el captcha pesado, se marca como pendiente
y se puede resolver con el fallback de navegador real:  py scraper_browser.py

Salidas: resultados_l1.json  +  resultados_l1.xlsx  (incremental, reanudable).

Uso:
    py scraper_l1.py
"""

import random
import time

import meli_common as mc
import meli_fetch as mf


def main():
    categorias = mc.cargar_categorias_l1()
    print(f"Categorias L1 en CSV: {len(categorias)}")

    resultados, hechas = mc.cargar_progreso()
    pendientes = [(c, n) for c, n in categorias if c not in hechas]
    print(f"Ya scrapeadas: {len(hechas)} | Pendientes: {len(pendientes)}\n")
    if not pendientes:
        print("Todo listo. Nada pendiente.")
        return

    bloqueadas = []
    for idx, (cid, nombre) in enumerate(pendientes, 1):
        print(f"[{idx}/{len(pendientes)}] {cid} - {nombre}")
        print(f"  -> {mc.url_mas_vendidos(cid)}")
        estado, productos = mf.scrapear_categoria(cid)

        if estado == "bloqueado":
            print("  !!! BLOQUEADO por DataDome. Usa el fallback: py scraper_browser.py")
            bloqueadas.append((cid, nombre))
        else:
            data = mc.registro_categoria(cid, nombre, productos)
            resultados = mc.upsert(resultados, data)
            mc.guardar(resultados)
            if estado == "vacio":
                print(f"  (0 productos para {cid}).")
            print(f"  OK: {len(productos)} productos. Guardado.\n")
        time.sleep(random.uniform(5.0, 11.0))

    total = sum(len(r["productos"]) for r in resultados)
    print(f"\nFINALIZADO. {len(resultados)} categorias con datos, {total} productos.")
    print(f"  JSON : {mc.OUT_JSON}")
    print(f"  Excel: {mc.OUT_XLSX}")
    if bloqueadas:
        print(f"\n{len(bloqueadas)} categorias quedaron BLOQUEADAS:")
        for cid, nombre in bloqueadas:
            print(f"   - {cid} {nombre}")
        print("Reintenta con el navegador real:  py scraper_browser.py")


if __name__ == "__main__":
    main()
