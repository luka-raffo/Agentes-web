# Scrapper Meli L1 — Productos más vendidos por categoría

Extrae el ranking de **productos más vendidos** de las **29 categorías raíz (L1)**
del archivo `NN AI - Verticales MELI.csv`, desde las páginas
`https://www.mercadolibre.com.ar/mas-vendidos/<CAT_ID>`.

## Cómo evita el bloqueo de DataDome

MercadoLibre protege estas páginas con DataDome ("tráfico sospechoso"). Además,
la API oficial de ML ya **no permite** búsqueda por categoría ni el endpoint de
*highlights* con esta app (devuelven 403). Por eso se scrapea la página pública:

- **`scraper_l1.py` (principal):** usa `curl_cffi` con `impersonate="chrome"`
  (replica el fingerprint TLS de un Chrome real) y resuelve automáticamente el
  *proof-of-work* del BotManager de ML. Es rápido y no abre navegador.
- **`scraper_browser.py` (fallback):** Chrome real vía Selenium. Hace scroll para
  disparar el *lazy-load* y completa las categorías que `curl_cffi` dejó truncadas.
  Si aparece un captcha, lo resolvés una vez y el resto sale solo.

> La clave es correrlo desde una **IP residencial** (tu PC). Para miles de
> categorías (L2/L3) haría falta rotación de IPs / un servicio anti-bot.

## Uso

```powershell
# 1) Motor principal: trae el top de las 29 categorías (rápido)
py scraper_l1.py

# 2) (Opcional) Completar las categorías con menos de 20 productos
#    Abre Chrome, scrollea y rellena las listas truncadas
py scraper_browser.py

# Solo reintentar las que quedaron en 0 productos:
py scraper_browser.py 0
```

Ambos scripts son **reanudables** y guardan **incrementalmente**: si se cortan,
volvés a ejecutarlos y siguen donde quedaron. `scraper_browser.py` solo reemplaza
un resultado si obtiene **más** productos que el guardado.

## Backend a demanda (API web)

Para consultar **una categoría desde la web** y traer sus más vendidos al
instante, hay un backend FastAPI que reutiliza el mismo motor:

```powershell
# Levantar el servidor (queda escuchando)
py -m uvicorn api:app --host 0.0.0.0 --port 8000

# (recarga automática mientras desarrollás)
py -m uvicorn api:app --reload
```

Endpoints:

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/health` | Chequeo de estado |
| `GET` | `/categorias` | Lista las 29 categorías L1 con su ID |
| `GET` | `/mas-vendidos/{cat_id}` | **Más vendidos de esa categoría** (ej. `/mas-vendidos/MLA1000`) |
| `GET` | `/mas-vendidos/{cat_id}?nocache=1` | Igual, pero ignora la caché y vuelve a scrapear |
| `POST` | `/mas-vendidos` | Body `{"categoria": "MLA1000"}` |

Respuesta:

```json
{
  "categoria_id": "MLA1000",
  "categoria": "Electrónica, Audio y Video",
  "url": "https://www.mercadolibre.com.ar/mas-vendidos/MLA1000",
  "cantidad": 20,
  "cacheado": false,
  "productos": [ { "ranking": 1, "titulo": "...", "precio": "538.288", "...": "..." } ]
}
```

Detalles:
- **Caché en memoria de 10 min**: si piden la misma categoría dos veces seguidas,
  la segunda es instantánea y no vuelve a pegarle a ML (menos riesgo de bloqueo).
- **CORS abierto**: se puede consumir desde el navegador / cualquier front.
- Si ML bloquea, responde **HTTP 503** rápido (reintentos cortos, ~10 s máx).
- Docs interactivas automáticas en **http://localhost:8000/docs**.

**Demo web:** abrí `demo.html` en el navegador (con el server corriendo). Trae el
combo de categorías desde el backend y muestra los más vendidos en tarjetas.

> Acepta cualquier ID del CSV (L1/L2/L3), no solo L1. Igual, para uso intensivo
> de niveles bajos aplica la misma advertencia de bloqueo/IP.

## Despliegue (GitHub + tu PC + túnel) — el que funciona

> **Por qué así:** MercadoLibre bloquea (DataDome) las IPs de datacenter. Render,
> Railway, Heroku, una VPS, etc. corren en esas IPs → se bloquean al instante.
> Tu PC tiene **IP residencial**, que ML no bloquea. Por eso el backend corre en
> tu PC y solo lo **exponés** a internet con un túnel. GitHub guarda el código.

### 1) Subir el código a GitHub (una vez)

```powershell
cd "Scrapper Meli L1"
git init
git add .
git commit -m "Backend mas vendidos MercadoLibre"
git branch -M main
git remote add origin <URL_DE_TU_REPO>
git push -u origin main
```

`cloudflared.exe`, los perfiles de navegador y la carpeta `debug/` están en
`.gitignore` (no se suben). El proyecto **no usa secretos**.

### 2) Correrlo (cada vez que lo quieras online)

```text
1. Doble clic en  start.bat     -> levanta el backend en http://localhost:8000
2. Doble clic en  tunnel.bat    -> imprime una URL https://XXXX.trycloudflare.com
```

Esa URL pública es la que pones en tu web:
`https://XXXX.trycloudflare.com/mas-vendidos/MLA1000`

Mientras tu PC esté encendida con esas dos ventanas abiertas, la API funciona
desde cualquier lado. Si cerrás y volvés a abrir el túnel, la URL cambia (es la
versión gratis sin cuenta).

### URL fija (opcional)

Para una URL estable (ej. `api.tudominio.com`) necesitás una cuenta Cloudflare
gratis + un dominio, y crear un *named tunnel*:
`cloudflared tunnel login` → `cloudflared tunnel create meli` → asociar DNS.
Te lo dejo armado si lo necesitás.

### Alternativa 24/7 sin tu PC

Hosting cloud (desde este mismo repo) **+ un servicio de proxies residenciales**
(ScraperAPI / ZenRows / Bright Data). Hay que enchufar el proxy en
`meli_fetch.py` (`requests.Session(..., proxies=...)`). Es pago pero corre solo.

## Salidas

- **`resultados_l1.json`** — estructura completa por categoría:
  ```json
  {
    "categoria_id": "MLA1000",
    "categoria": "Electrónica, Audio y Video",
    "url": "https://www.mercadolibre.com.ar/mas-vendidos/MLA1000",
    "fecha_extraccion": "2026-06-11 17:30",
    "productos": [
      {"ranking": 1, "titulo": "...", "precio": "538.288",
       "precio_original": "", "descuento": "", "vendedor": "Mercado Libre",
       "rating": "", "reviews": "", "mla_id": "MLA49197748",
       "link": "https://...", "imagen": "https://..."}
    ]
  }
  ```
- **`resultados_l1.xlsx`** — una fila por producto (ideal para Excel / análisis).

## Dependencias (ya instaladas en este equipo)

`curl_cffi`, `beautifulsoup4`, `lxml`, `pandas`, `openpyxl` (principal) ·
`selenium`, `selenium-stealth` + Google Chrome (fallback).

> Nota: Playwright **no** funciona en este equipo (Python 3.14 / greenlet), por
> eso el fallback usa Selenium.

## Cambiar el nivel de categorías

Hoy procesa nivel **L1** (columna `L1 ID` del CSV). Para L2/L3, en
`meli_common.py` la función `cargar_categorias_l1()` lee esa columna; cambiar a
`L2 ID`/`L3 ID` permitiría otros niveles, pero el volumen (382 / 2751 categorías)
casi seguro requiere proxies o un servicio anti-bot para no ser bloqueado.
