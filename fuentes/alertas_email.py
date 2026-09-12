"""Lee los emails de alerta de los portales y extrae los anuncios.
No depende de la forma de las URLs (los portales usan enlaces de redireccion):
busca bloques de texto que contengan un precio y coge el enlace mas cercano."""
import email
import hashlib
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header

from bs4 import BeautifulSoup

DIAS_ATRAS = int(os.getenv("DIAS_ATRAS", "5"))

PORTALES = {
    "idealista": "idealista",
    "fotocasa": "fotocasa",
    "habitaclia": "habitaclia",
    "pisos.com": "pisos.com",
    "yaencontre": "yaencontre",
}

TIPOS = r"(Piso|Bajo|Planta baja|Apartamento|\u00c1tico|Atico|D\u00faplex|Duplex|Estudio|Loft|Casa|Chalet|Adosad[oa]|Local|Nave|Oficina|Vivienda|Inmueble)"
RE_PRECIO = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{5,7})\s*\u20ac")
RE_SUP = re.compile(r"(\d{2,4})\s*m\s*[\u00b22]")
RE_HAB = re.compile(r"(\d)\s*(?:hab|dorm)")
RE_TIPO = re.compile(TIPOS, re.I)


def _asunto(msg):
    salida = ""
    for texto, cod in decode_header(msg.get("Subject", "")):
        salida += texto.decode(cod or "utf-8", errors="ignore") if isinstance(texto, bytes) else texto
    return salida


def _html_del_mensaje(msg):
    html = ""
    for parte in msg.walk():
        if parte.get_content_type() == "text/html":
            carga = parte.get_payload(decode=True)
            if carga:
                html += carga.decode(parte.get_content_charset() or "utf-8", errors="ignore")
    return html


def _municipio(texto):
    m = re.search(r"\ben ([A-Z\u00c0-\u00ff][\w\u00c0-\u00ff'\.\- ]{2,40}?)(?:,|\.|\d|$)", texto)
    if m:
        return m.group(1).strip()
    for barrio in ("Russafa", "Ruzafa", "El Carme", "El Pilar", "La Petxina", "Benimaclet",
                   "Patraix", "Campanar", "Extramurs", "Algiros", "Quatre Carreres"):
        if barrio.lower() in texto.lower():
            return barrio
    return "Valencia"


def _enlace_cercano(nodo):
    """Busca un enlace dentro del bloque o, si no, en sus hermanos anteriores."""
    a = nodo.find("a", href=True)
    if a:
        return a["href"]
    padre = nodo
    for _ in range(3):
        if not padre.parent:
            break
        padre = padre.parent
        a = padre.find("a", href=True)
        if a:
            return a["href"]
    return None


def _extraer_anuncios(html, portal, es_bajada=False):
    soup = BeautifulSoup(html, "html.parser")
    for etiqueta in soup(["style", "script"]):
        etiqueta.decompose()
    vistos = {}
    # candidatos: cualquier nodo cuyo texto tenga un precio y no sea demasiado largo
    for nodo in soup.find_all(["td", "div", "table", "tr", "p", "li"]):
        texto = nodo.get_text(" ", strip=True)
        if not texto or len(texto) > 400:
            continue
        mp = RE_PRECIO.search(texto)
        if not mp:
            continue
        precio = int(mp.group(1).replace(".", ""))
        if precio < 20000 or precio > 3000000:
            continue
        msup = RE_SUP.search(texto)
        mtipo = RE_TIPO.search(texto)
        titulo = texto[:120]
        clave = hashlib.md5(f"{portal}|{precio}|{msup.group(1) if msup else ''}|{_municipio(texto)}".encode()).hexdigest()[:16]
        if clave in vistos:
            continue
        mhab = RE_HAB.search(texto)
        tipo_txt = (mtipo.group(1).lower() if mtipo else "")
        vistos[clave] = {
            "id": f"{portal}-{clave}",
            "fuente": portal,
            "url": _enlace_cercano(nodo),
            "tipo": "local" if tipo_txt in ("local", "nave", "oficina") else "vivienda",
            "titulo": titulo,
            "municipio": _municipio(texto),
            "precio": precio,
            "superficie": int(msup.group(1)) if msup else None,
            "habitaciones": int(mhab.group(1)) if mhab else None,
            "texto": texto[:1500],
            "bajada_anunciada": es_bajada,
        }
    return list(vistos.values())


def obtener():
    correo = imaplib.IMAP4_SSL("imap.gmail.com")
    correo.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    correo.select("INBOX")
    desde = (datetime.utcnow() - timedelta(days=DIAS_ATRAS)).strftime("%d-%b-%Y")
    resultado = []
    for portal, remitente in PORTALES.items():
        try:
            _, datos = correo.search(None, f'(SINCE {desde} FROM "{remitente}")')
        except Exception as e:
            print(f"  {portal}: error al buscar: {e}")
            continue
        nums = datos[0].split()
        print(f"  {portal}: {len(nums)} correos")
        for num in nums:
            _, contenido = correo.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(contenido[0][1])
            es_bajada = bool(re.search(r"bajada de precio|baja de precio|ha bajado", _asunto(msg), re.I))
            encontrados = _extraer_anuncios(_html_del_mensaje(msg), portal, es_bajada)
            print(f"    '{_asunto(msg)[:60]}' -> {len(encontrados)} anuncios")
            resultado.extend(encontrados)
    correo.logout()
    return resultado
