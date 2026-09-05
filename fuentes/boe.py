"""Subastas de inmuebles del Portal de Subastas del BOE (provincia de Valencia = código 46).
Datos públicos. Se consulta una vez al día, con pausas entre peticiones."""
import re
import time

import requests
from bs4 import BeautifulSoup

from fuentes import catastro

BASE = "https://subastas.boe.es"
CABECERAS = {"User-Agent": "chollos-valencia-bot/1.0 (uso personal, 1 consulta diaria)"}

BUSQUEDA = (
    BASE + "/subastas_ava.php?campo[0]=SUBASTA.ORIGEN&dato[0]=&campo[1]=SUBASTA.ESTADO&dato[1]=EJ"
    "&campo[2]=BIEN.TIPO&dato[2]=I&dato[3]=&campo[4]=BIEN.DIRECCION&dato[4]=&campo[5]=BIEN.CODPOSTAL"
    "&dato[5]=&campo[6]=BIEN.LOCALIDAD&dato[6]=&campo[7]=BIEN.COD_PROVINCIA&dato[7]=46"
    "&campo[8]=SUBASTA.POSTURA_MINIMA_MINIMA_LOTES&dato[8]=&campo[9]=SUBASTA.NUM_CUENTA_EXPEDIENTE_1"
    "&dato[9]=&campo[10]=SUBASTA.NUM_CUENTA_EXPEDIENTE_2&dato[10]=&campo[11]=SUBASTA.NUM_CUENTA_EXPEDIENTE_3"
    "&dato[11]=&campo[12]=SUBASTA.NUM_CUENTA_EXPEDIENTE_4&dato[12]=&campo[13]=SUBASTA.NUM_CUENTA_EXPEDIENTE_5"
    "&dato[13]=&campo[14]=SUBASTA.ID_SUBASTA_BUSCAR&dato[14]=&campo[15]=SUBASTA.FECHA_FIN_YMD&dato[15][0]=&dato[15][1]="
    "&campo[16]=SUBASTA.FECHA_INICIO_YMD&dato[16][0]=&dato[16][1]=&page_hits=50"
    "&sort_field[0]=SUBASTA.FECHA_INICIO_YMD&sort_order[0]=desc&accion=Buscar"
)


def _num(txt):
    s = re.sub(r"[^\d,]", "", txt or "").replace(",", ".")
    try:
        return int(float(s)) if s else None
    except ValueError:
        return None


def _valor_tabla(soup, etiqueta):
    th = soup.find(lambda t: t.name in ("th", "td") and etiqueta.lower() in t.get_text().lower())
    if th and th.find_next_sibling("td"):
        return th.find_next_sibling("td").get_text(" ", strip=True)
    return None


def obtener(max_subastas=40):
    r = requests.get(BUSQUEDA, headers=CABECERAS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ids = []
    for a in soup.select("a[href*='detalleSubasta.php?idSub=']"):
        m = re.search(r"idSub=([A-Z0-9-]+)", a["href"])
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    resultado = []
    for id_sub in ids[:max_subastas]:
        time.sleep(1.5)
        try:
            resultado.extend(_detalle(id_sub))
        except Exception as e:  # una subasta rara no debe parar el resto
            print("BOE: no se pudo leer", id_sub, e)
    return resultado


def _detalle(id_sub):
    url_general = f"{BASE}/detalleSubasta.php?idSub={id_sub}"
    g = BeautifulSoup(requests.get(url_general, headers=CABECERAS, timeout=30).text, "html.parser")
    valor = _num(_valor_tabla(g, "Valor subasta"))
    puja_min = _num(_valor_tabla(g, "Puja mínima")) or (int(valor * 0.5) if valor else None)
    tramos = _valor_tabla(g, "Tramos")
    time.sleep(1.0)
    url_bienes = f"{BASE}/detalleSubasta.php?idSub={id_sub}&ver=3"
    b = BeautifulSoup(requests.get(url_bienes, headers=CABECERAS, timeout=30).text, "html.parser")
    descripcion = _valor_tabla(b, "Descripción") or ""
    localidad = _valor_tabla(b, "Localidad") or ""
    direccion = _valor_tabla(b, "Dirección") or ""
    ref_cat = _valor_tabla(b, "Referencia catastral")
    situacion = _valor_tabla(b, "Situación posesoria") or ""
    cargas = _valor_tabla(b, "Cargas") or ""
    sup = re.search(r"(\d{2,4})(?:[,.]\d+)?\s*(?:m2|m²|metros)", descripcion, re.I)
    tipo = "vivienda" if re.search(r"vivienda|piso|casa|chalet|apartamento|dúplex|ático", descripcion, re.I) else "otro"
    if tipo != "vivienda" or not puja_min or puja_min > 10**7:
        return []
    cat = catastro.consultar(ref_cat) if ref_cat else {}
    avisos = []
    if "ocupad" in situacion.lower() or "sin posesi" in situacion.lower():
        avisos.append("ocupado / sin posesión")
    if cargas and not re.search(r"no constan|sin cargas|libre de cargas", cargas, re.I):
        avisos.append("con cargas")
    return [{
        "id": f"boe-{id_sub}",
        "fuente": "BOE subasta",
        "titulo": descripcion[:110] or "Inmueble en subasta",
        "alertas": ", ".join(avisos) or None,
        "referencia_catastral": ref_cat,
        "anyo": cat.get("anyo"),
        "url": url_general,
        "municipio": localidad or "Valencia",
        "zona": direccion[:80],
        "precio": puja_min,
        "precio_anterior": valor,
        "superficie": cat.get("superficie") or (int(sup.group(1)) if sup else None),
        "tipo": tipo,
        "descuento_boe": round(100 * (1 - puja_min / valor), 1) if valor else None,
    }]
