"""Lee los emails de alerta de los portales y extrae los anuncios.
Busca por fecha (ultimos dias), no por "no leido", asi que puedes abrir los correos sin problema."""
import email
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header

from bs4 import BeautifulSoup

DIAS_ATRAS = int(os.getenv("DIAS_ATRAS", "3"))

PORTALES = {
    "idealista": {"remitente": "idealista", "dominio": "idealista.com"},
    "fotocasa": {"remitente": "fotocasa", "dominio": "fotocasa.es"},
    "habitaclia": {"remitente": "habitaclia", "dominio": "habitaclia.com"},
    "pisos.com": {"remitente": "pisos.com", "dominio": "pisos.com"},
    "yaencontre": {"remitente": "yaencontre", "dominio": "yaencontre.com"},
}


def _asunto(msg):
    salida = ""
    for texto, cod in decode_header(msg.get("Subject", "")):
        salida += texto.decode(cod or "utf-8", errors="ignore") if isinstance(texto, bytes) else texto
    return salida


def _html_del_mensaje(msg):
    for parte in msg.walk():
        if parte.get_content_type() == "text/html":
            carga = parte.get_payload(decode=True)
            return carga.decode(parte.get_content_charset() or "utf-8", errors="ignore")
    return ""


def _extraer_anuncios(html, portal, dominio, es_bajada=False):
    soup = BeautifulSoup(html, "html.parser")
    anuncios = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if dominio not in href or not re.search(r"/inmueble/\d+|/vivienda/|/\d{6,}", href):
            continue
        m = re.search(r"(\d{6,})", href)
        if not m:
            continue
        aid = f"{portal}-{m.group(1)}"
        bloque = a
        for _ in range(4):
            if bloque.parent and len(bloque.parent.get_text(" ", strip=True)) < 600:
                bloque = bloque.parent
        texto = bloque.get_text(" ", strip=True)
        precio = re.search(r"(\d{2,3}(?:\.\d{3})+|\d{5,7})\s*€", texto)
        sup = re.search(r"(\d{2,4})\s*m[²2]", texto)
        hab = re.search(r"(\d)\s*hab", texto)
        titulo = re.search(r"(Piso|Bajo|Planta baja|Apartamento|Ático|Dúplex|Estudio|Loft|Casa|Chalet|Adosad[oa]|Local|Nave|Oficina)[^€]{0,80}", texto)
        tipo = "local" if titulo and titulo.group(1) in ("Local", "Nave", "Oficina") else "vivienda"
        anuncio = anuncios.setdefault(aid, {"id": aid, "fuente": portal, "url": href.split("?")[0], "tipo": tipo, "bajada_anunciada": es_bajada})
        if precio and not anuncio.get("precio"):
            anuncio["precio"] = int(precio.group(1).replace(".", ""))
        if sup and not anuncio.get("superficie"):
            anuncio["superficie"] = int(sup.group(1))
        if hab and not anuncio.get("habitaciones"):
            anuncio["habitaciones"] = int(hab.group(1))
        if titulo and not anuncio.get("titulo"):
            anuncio["titulo"] = titulo.group(0).strip()[:120]
            anuncio["municipio"] = _municipio(titulo.group(0))
        anuncio["texto"] = (anuncio.get("texto", "") + " " + texto)[:1500]
        if es_bajada:
            anuncio["bajada_anunciada"] = True
    return [a for a in anuncios.values() if a.get("precio")]


def _municipio(titulo):
    m = re.search(r" en ([A-ZÀ-ÿ][\wÀ-ÿ' -]+?)(?:,|$| \d)", titulo)
    return m.group(1).strip() if m else "Valencia"


def obtener():
    correo = imaplib.IMAP4_SSL("imap.gmail.com")
    correo.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    correo.select("INBOX")
    desde = (datetime.utcnow() - timedelta(days=DIAS_ATRAS)).strftime("%d-%b-%Y")
    resultado = []
    for portal, cfg in PORTALES.items():
        _, datos = correo.search(None, f'(SINCE {desde} FROM "{cfg["remitente"]}")')
        for num in datos[0].split():
            _, contenido = correo.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(contenido[0][1])
            es_bajada = bool(re.search(r"bajada de precio|baja de precio|ha bajado", _asunto(msg), re.I))
            resultado.extend(_extraer_anuncios(_html_del_mensaje(msg), portal, cfg["dominio"], es_bajada))
    correo.logout()
    return resultado
