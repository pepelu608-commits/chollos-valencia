"""Puntuación de chollo 0-100. Combina descuento frente a la zona, bajadas de precio,
días publicado y palabras clave. Devuelve (puntos, lista_de_motivos)."""
import re
from datetime import datetime, timezone

POSITIVAS = {
    r"\burge\b|urgente|venta r[aá]pida": ("vendedor con urgencia", 10),
    r"herencia|herederos|proindiviso": ("herencia / proindiviso", 8),
    r"a reformar|para reformar|reforma integral": ("a reformar (margen de reforma)", 6),
    r"nuda propiedad": ("nuda propiedad (precio muy bajo, sin uso inmediato)", 5),
    r"negociable|oferta|rebajad|bajada de precio": ("precio negociable / rebajado", 6),
    r"procedente de banco|entidad bancaria|adjudicad": ("procedente de banco", 5),
}
NEGATIVAS = {
    r"ocupad[oa]|sin posesi[oó]n|inquilino|alquilad[oa]": ("ocupado / con inquilino", -25),
    r"no se puede visitar|sin visita": ("no se puede visitar", -10),
    r"sin ascensor": ("sin ascensor", -3),
    r"con cargas|embargo": ("con cargas", -15),
}


def puntuar(a, dias_publicado=0, bajada_pct=0.0):
    puntos, motivos = 0, []
    d = a.get("descuento_pct") or 0
    if d >= 30:
        puntos += 55; motivos.append(f"{d:.0f}% por debajo de la media de la zona")
    elif d >= 20:
        puntos += 40; motivos.append(f"{d:.0f}% por debajo de la media de la zona")
    elif d >= 10:
        puntos += 20; motivos.append(f"{d:.0f}% por debajo de la media de la zona")
    db = a.get("descuento_boe") or 0
    if db >= 30:
        puntos += 45; motivos.append(f"puja mínima un {db:.0f}% bajo tasación")
    if bajada_pct >= 15:
        puntos += 25; motivos.append(f"bajada de precio del {bajada_pct:.0f}%")
    elif bajada_pct >= 8:
        puntos += 15; motivos.append(f"bajada de precio del {bajada_pct:.0f}%")
    if dias_publicado >= 90:
        puntos += 10; motivos.append(f"{dias_publicado} días publicado")
    elif dias_publicado >= 45:
        puntos += 5
    texto = " ".join(str(a.get(k) or "") for k in ("titulo", "texto", "alertas")).lower()
    for patron, (etiqueta, pts) in {**POSITIVAS, **NEGATIVAS}.items():
        if re.search(patron, texto):
            puntos += pts; motivos.append(etiqueta)
    return max(0, min(100, puntos)), motivos


def dias_desde(fecha_iso):
    if not fecha_iso:
        return 0
    try:
        f = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - f).days
    except ValueError:
        return 0
