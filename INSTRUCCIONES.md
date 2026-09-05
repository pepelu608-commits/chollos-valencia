# Chollos Valencia — instrucciones (Mac)

Todo se hace en la app **Terminal**. Copia y pega cada comando y pulsa Intro.

## A. Preparar el proyecto en tu Mac (una sola vez)

1. Descarga la carpeta `chollos-valencia` y muévela a tu carpeta personal (la que tiene tu nombre).
2. Abre Terminal y entra en la carpeta:
   ```
   cd ~/chollos-valencia
   ```
3. Comprueba que tienes Python 3 (si te pide instalar las herramientas de Xcode, acepta):
   ```
   python3 --version
   ```
4. Crea el entorno e instala lo necesario:
   ```
   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
   ```
5. Crea tu fichero de claves a partir del ejemplo:
   ```
   cp .env.ejemplo .env && open -e .env
   ```
   Se abre un editor: sustituye cada valor por los de tus Notas (token de Telegram, tu Id, URL y clave de Supabase, Gmail y contraseña de aplicación). Guarda y cierra.

## B. Supabase

Ya está hecho: proyecto `chollos-valencia` creado y tabla `anuncios` lista (v2 con puntuación).
Solo necesitas copiar en `.env`: `SUPABASE_URL=https://gclytaqegexluuwyrniw.supabase.co` y en `SUPABASE_KEY` la clave de **Settings → API Keys → Secret keys → default**.

## C. Probar a mano

Sin guardar nada ni avisar, solo para ver qué encuentra:
```
source venv/bin/activate && python bot.py --prueba
```
Ejecución real (guarda en Supabase y avisa por Telegram):
```
source venv/bin/activate && python bot.py
```

## D. Que corra solo cada día (GitHub Actions)

1. En github.com → **New repository** → nombre `chollos-valencia` → **Private** → Create.
2. En Terminal, dentro de la carpeta (sustituye TU_USUARIO por tu usuario de GitHub):
   ```
   git init && git add . && git commit -m "bot chollos" && git branch -M main && git remote add origin https://github.com/TU_USUARIO/chollos-valencia.git && git push -u origin main
   ```
   (El fichero `.env` con tus claves NO se sube: está protegido por `.gitignore`.)
3. En el repositorio → **Settings → Secrets and variables → Actions → New repository secret**. Crea uno por cada línea de tu `.env`: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `SUPABASE_URL`, `SUPABASE_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`.
4. Pestaña **Actions** → "Chollos - portales cada hora" → **Run workflow** para probarlo. A partir de ahí los portales se revisan cada hora y las subastas del BOE cada mañana.

## Ajustes

Cambia en `.env` (y en los secretos de GitHub si quieres) `PRECIO_MAX`, `UMBRAL_PUNTOS` (puntuación mínima 0-100 para avisar; 70 por defecto), `UMBRAL_BAJADA` (% de bajada de precio) y la lista `MUNICIPIOS`.

## Cómo se puntúa un chollo (0-100)
- Precio/m² por debajo de la media de su municipio: 10% → 20 pts · 20% → 40 · 30% → 55
- Subasta con puja mínima ≥30% bajo tasación: 45
- Bajada de precio: 8% → 15 pts · 15% → 25
- Lleva más de 90 días publicado: 10
- Palabras clave: "urge" +10, herencia +8, a reformar +6, negociable/rebajado +6, banco +5
- Penaliza: ocupado/inquilino −25, con cargas −15, no se puede visitar −10
