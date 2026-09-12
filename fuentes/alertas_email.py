"""Lee los emails de alerta de los portales y extrae los anuncios.
Aprovecha que los propios correos ya traen euros/m2 y el barrio."""
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

BARRIOS = [
    "Russafa", "Ruzafa", "El Carme", "El Carmen", "El Pilar", "La Petxina", "Benimaclet",
    "Patraix", "Campanar", "Extramurs", "Algiros", "Quatre Carreres", "El Cabanyal",
    "El Canyamelar", "La Roqueta", "El Mercat", "La Xerea", "Arrancapins", "Sant Francesc",
    "La Seu", "Jesus", "Jesús", "Camins al Grau", "Ayora", "Albors", "La Creu del Grau",
    "Penya-roja", "Malilla", "Sant Marcelli", "Sant Marcel·li", "Tres Forques", "Safranar",
    "Vara de Quart", "Nou Moles", "Soternes", "Marxalenes", "Morvedre", "Trinitat",
    "Exposicio", "Exposició", "Mestalla", "Ciutat Universitaria", "Benicalap", "Torrefiel",
    "Orriols", "Sant Llorens", "Sant Antoni", "Natzaret", "La Punta", "Castellar",
    "Pla del Real", "Gran Via", "El Pla del Remei", "Ciutat Vella", "Poblats Maritims",
    "Benimamet", "Beteró", "Betero", "La Malva-rosa", "Els Orriols", "Sant Pau",
]

RE_PRECIO = re.compile("(\\d{1,3}(?:\\.\\d{3})+|\\d{5,7})\\s*€")
RE_M2_DIRECTO = re.compile("(\\d{1,2}\\.?\\d{3})\\s*€\\s*/\\s*m")
RE_SUP = re.compile("(\\d{2,4})\\s*m\\s*[²2]")
RE_HAB = re.compile("(\\d)\\s*hab")
RE_TIPO = re.compile("(Piso|Bajo|Planta baja|Apartamento|Ático|Atico|Dúplex|Duplex|Estudio|Loft|Casa|Chalet|Adosado|Adosada|Local|Nave|Oficina)", re.I)
# "calle X, Barrio en Valencia" -> Barrio
RE_BARRIO_EN = re.compile(",\\s*([A-ZÀ-ÿ][\\wÀ-ÿ'·\\-\\. ]{2,35}?)\\s+en\\s+Val[eè]ncia", re.I)
# frases que delatan que el bloque es parte del filtro, no un anuncio
RUIDO = re.compile("sin otros filtros|hasta \\d|ver todos|modificar|darse de baja|preferencias", re.I)


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


def _barrio(texto):
    m = RE_BARRIO_EN.search(texto)
    if m:
        nombre = m.group(1).strip()
        if 2 < len(nombre) < 36 and not nombre.lower().startswith(("calle", "avenida", "plaza", "camino")):
            return nombre
    bajo = texto.lower()
    for barrio in BARRIOS:
        if barrio.lower() in bajo:
            return barrio
    return "Valencia"


def _enlace_cercano(nodo):
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
    for nodo in soup.find_all(["td", "div", "table", "tr", "p", "li"]):
        texto = nodo.get_text(" ", strip=True)
        if not texto or len(texto) > 400 or RUIDO.search(texto):
            continue
        precios = RE_PRECIO.findall(texto)
        if not precios:
            continue
        msup = RE_SUP.search(texto)
        mm2 = RE_M2_DIRECTO.search(texto)
        mhab = RE_HAB.search(texto)
        mtipo = RE_TIPO.search(texto)
        # un anuncio de verdad trae, ademas del precio, metros o euros/m2 o habitaciones
        if not (msup or mm2 or mhab):
            continue
        # si hay varios precios (rebajado), el vigente es el mas bajo
        valores = [int(p.replace(".", "")) for p in precios]
        valores = [v for v in valores if 20000 <= v <= 3000000]
        if not valores:
            continue
        precio = min(valores)
        anterior = max(valores) if max(valores) > precio else None
        sup = int(msup.group(1)) if msup else None
        m2 = int(mm2.group(1).replace(".", "")) if mm2 else None
        if not sup and m2 and precio:
            sup = round(precio / m2)
        barrio = _barrio(texto)
        clave = hashlib.md5((portal + "|" + str(precio) + "|" + str(sup) + "|" + barrio).encode()).hexdigest()[:16]
        if clave in vistos:
            continue
        tipo_txt = mtipo.group(1).lower() if mtipo else ""
        vistos[clave] = {
            "id": portal + "-" + clave,
            "fuente": portal,
            "url": _enlace_cercano(nodo),
            "tipo": "local" if tipo_txt in ("local", "nave", "oficina") else "vivienda",
            "titulo": texto[:120],
            "municipio": barrio,
            "precio": precio,
            "precio_anterior": anterior,
            "superficie": sup,
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
            _, datos = correo.search(None, '(SINCE ' + desde + ' FROM "' + remitente + '")')
        except Exception as e:
            print("  " + portal + ": error al buscar: " + str(e))
            continue
        nums = datos[0].split()
        print("  " + portal + ": " + str(len(nums)) + " correos")
        for num in nums:
            _, contenido = correo.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(contenido[0][1])
            asunto = _asunto(msg)
            es_bajada = bool(re.search("bajada de precio|baja de precio|ha bajado", asunto, re.I))
            encontrados = _extraer_anuncios(_html_del_mensaje(msg), portal, es_bajada)
            print("    " + asunto[:55] + " -> " + str(len(encontrados)))
            resultado.extend(encontrados)
    correo.logout()
    return resultado
