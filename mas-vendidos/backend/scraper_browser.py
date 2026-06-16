# -*- coding: utf-8 -*-
"""
Scrapper Meli L1 - FALLBACK con navegador real (Selenium + Chrome)
==================================================================
Usar SOLO si scraper_l1.py dejo categorias bloqueadas por el captcha pesado.

Abre un Chrome real con perfil persistente (carpeta chrome_profile/). Si aparece
el captcha de "trafico sospechoso", lo resolves UNA vez en la ventana: la cookie
de validacion queda en el perfil y el resto de las categorias salen solas.

Procesa las categorias L1 que en resultados_l1.json esten vacias o "flacas"
(menos de MIN_PRODUCTS productos). El navegador hace scroll y dispara el
lazy-load por JS, por lo que completa las listas que curl_cffi dejo truncadas.

Uso:
    py scraper_browser.py            # completa vacias y flacas (<20)
    py scraper_browser.py 0          # solo las vacias (0 productos)
"""

import os
import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

import meli_common as mc

import sys

PROFILE_DIR = os.path.join(mc.BASE_DIR, "chrome_profile")
PRODUCT_SELECTOR = "div.poly-card, li.ui-search-layout__item"
CAPTCHA_WAIT_S = 240
MIN_PRODUCTS = 20  # categorias con menos que esto se re-scrapean (por defecto)


def init_driver():
    options = Options()
    options.add_argument("start-maximized")
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--lang=es-AR")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    stealth(driver,
            languages=["es-AR", "es", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True)
    return driver


def scrapear(driver, cat_id, cat_name):
    url = mc.url_mas_vendidos(cat_id)
    print(f"  -> {url}")
    driver.get(url)
    time.sleep(random.uniform(2.5, 4.0))

    html = driver.page_source
    if mc.esta_bloqueado(html):
        print(f"  !!! CAPTCHA. Resolvelo en Chrome. Espero hasta {CAPTCHA_WAIT_S}s...")
        try:
            WebDriverWait(driver, CAPTCHA_WAIT_S).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, PRODUCT_SELECTOR)))
            print("  OK, resuelto.")
            time.sleep(2)
        except Exception:
            print("  No se cargaron productos. Salteo.")
            mc.guardar_debug(cat_id, driver.page_source)
            return None

    # scroll para lazy-load
    for _ in range(4):
        driver.execute_script("window.scrollBy(0, 4000);")
        time.sleep(random.uniform(0.4, 0.9))

    html = driver.page_source
    productos = mc.parsear_productos(html)
    if not productos:
        mc.guardar_debug(cat_id, html)
        print(f"  (0 productos; ver debug/{cat_id}.html)")
    return mc.registro_categoria(cat_id, cat_name, productos)


def main():
    umbral = int(sys.argv[1]) if len(sys.argv) > 1 else MIN_PRODUCTS
    categorias = mc.cargar_categorias_l1()
    resultados, _ = mc.cargar_progreso()
    # cuenta de productos por categoria ya guardada
    conteo = {r["categoria_id"]: len(r["productos"]) for r in resultados}
    # pendiente = nunca scrapeada, o con menos productos que el umbral
    pendientes = [(c, n) for c, n in categorias if conteo.get(c, 0) < umbral]
    print(f"Categorias L1: {len(categorias)} | "
          f"A completar (<{umbral} productos): {len(pendientes)}\n")
    if not pendientes:
        print("Todo listo. Nada pendiente.")
        return

    driver = init_driver()
    try:
        for idx, (cid, nombre) in enumerate(pendientes, 1):
            print(f"[{idx}/{len(pendientes)}] {cid} - {nombre}")
            data = scrapear(driver, cid, nombre)
            if data is not None and len(data["productos"]) >= conteo.get(cid, 0):
                resultados = mc.upsert(resultados, data)
                conteo[cid] = len(data["productos"])
                mc.guardar(resultados)
                print(f"  OK: {len(data['productos'])} productos.\n")
            elif data is not None:
                print(f"  ({len(data['productos'])} productos; conservo los "
                      f"{conteo.get(cid, 0)} previos)\n")
            time.sleep(random.uniform(4.0, 8.0))
    finally:
        driver.quit()

    total = sum(len(r["productos"]) for r in resultados)
    print(f"\nFINALIZADO. {len(resultados)} categorias con datos, {total} productos.")


if __name__ == "__main__":
    main()
