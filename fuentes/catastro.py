"""Enriquecimiento con el Catastro (servicio público, sin clave): superficie construida y año."""
import re
import requests

URL = "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPRC"


def consultar(referencia):
    rc = re.sub(r"\s", "", referencia or "")
    if len(rc) < 14:
        return {}
    try:
        r = requests.get(URL, params={"Provincia": "", "Municipio": "", "RC": rc}, timeout=20)
        xml = r.text
    except Exception:
        return {}
    datos = {}
    m = re.search(r"<sfc>(\d+)</sfc>", xml)
    if m:
        datos["superficie"] = int(m.group(1))
    m = re.search(r"<ant>(\d{4})</ant>", xml)
    if m:
        datos["anyo"] = int(m.group(1))
    m = re.search(r"<luso>([^<]+)</luso>", xml)
    if m:
        datos["uso_catastro"] = m.group(1)
    return datos
