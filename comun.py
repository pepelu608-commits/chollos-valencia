"""Funciones compartidas: configuracion, Supabase, Telegram y calculo de chollos."""
import os
import re
import statistics
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

from puntuacion import puntuar, dias_desde

load_dotenv()

PRECIO_MAX = int(os.getenv("PRECIO_MAX", "350000"))
UMBRAL_BAJADA = float(os.getenv("UMBRAL_BAJADA", "10"))
UMBRAL_PUNTOS = int(os.getenv("UMBRAL_PUNTOS", "70"))
MUNICIPIOS = [m.strip().lower() for m in os.getenv("MUNICIPIOS", "valencia").split(",")]

# Rangos plausibles de euros por metro cuadrado. Fuera de esto es un error de lectura.
RANGOS_M2 = {"vivienda": (800, 8000), "local": (300, 6000)}
MIN_MUESTRA = 8          # anuncios necesarios en una zona para fiarse de su media
DESCUENTO_MAX = 60.0     # tope al descuento mostrado

_db = None


def db():
    global _db
    if _db is None:
        _db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _db


def es_municipio_ok(texto):
    t = (texto or "").lower()
    return any(m in t for m in MUNICIPIOS)


def m2_plausible(valor, tipo):
    bajo, alto = RANGOS_M2.get(tipo or "vivienda", RANGOS_M2["vivienda"])
    return valor is not None and bajo <= valor <= alto


def media_zona(municipio, tipo):
    """Mediana de euros/m2 de la zona, descartando valores imposibles y los extremos."""
    if not municipio:
        return None
    r = (
        db().table("anuncios")
        .select("precio_m2")
        .eq("municipio", municipio)
        .eq("tipo", tipo)
        .not_.is_("precio_m2", "null")
        .limit(500)
        .execute()
    )
    valores = sorted(v["precio_m2"] for v in r.data if m2_plausible(v["precio_m2"], tipo))
    if len(valores) < MIN_MUESTRA:
        return None
    # se queda con el tramo central (quita el 10% mas barato y el 10% mas caro)
    recorte = max(1, len(valores) // 10)
    centro = valores[recorte:-recorte] or valores
    return int(statistics.median(centro))


def _grupo(anuncio):
    if not anuncio.get("superficie") or not anuncio.get("precio"):
        return None
    muni = re.sub(r"\W", "", (anuncio.get("municipio") or "").lower())[:12]
    return muni + "-" + str(anuncio["superficie"]) + "-" + str(round(anuncio["precio"] / 5000))


def guardar(anuncio):
    ahora = datetime.now(timezone.utc).isoformat()
    tipo = anuncio.get("tipo") or "vivienda"
    if anuncio.get("precio") and anuncio.get("superficie"):
        anuncio["precio_m2"] = round(anuncio["precio"] / anuncio["superficie"])
    media = media_zona(anuncio.get("municipio"), tipo)
    anuncio["media_zona_m2"] = media
    # solo comparamos si el propio anuncio tiene un euros/m2 creible
    if media and m2_plausible(anuncio.get("precio_m2"), tipo):
        dto = round(100 * (1 - anuncio["precio_m2"] / media), 1)
        anuncio["descuento_pct"] = max(-DESCUENTO_MAX, min(DESCUENTO_MAX, dto))
    else:
        anuncio["descuento_pct"] = None
    anuncio["grupo"] = _grupo(anuncio)
    texto = anuncio.pop("texto", None)
    bajada_anunciada = anuncio.pop("bajada_anunciada", False)

    existente = db().table("anuncios").select("*").eq("id", anuncio["id"]).execute().data
    bajada, dias = 0.0, 0
    if existente:
        viejo = existente[0]
        if viejo["descartado"]:
            return viejo, None
        dias = dias_desde(viejo.get("fecha_alta"))
        if viejo["precio"] and anuncio.get("precio") and anuncio["precio"] < viejo["precio"]:
            bajada = 100 * (1 - anuncio["precio"] / viejo["precio"])
            anuncio["precio_anterior"] = viejo["precio"]
    puntos, motivos = puntuar({**anuncio, "texto": texto}, dias, bajada)
    anuncio["puntos"] = puntos
    anuncio["motivos"] = "; ".join(motivos) or None
    anuncio["fecha_actualizacion"] = ahora

    motivo_aviso = None
    ya_avisado = existente and existente[0].get("avisado")
    if puntos >= UMBRAL_PUNTOS and not ya_avisado:
        motivo_aviso = "Puntuacion " + str(puntos) + "/100 - " + "; ".join(motivos)
    elif bajada >= UMBRAL_BAJADA:
        motivo_aviso = "Bajada del " + format(bajada, ".0f") + "%"
    elif bajada_anunciada and not ya_avisado:
        motivo_aviso = "El portal anuncia bajada de precio"

    if existente:
        db().table("anuncios").update(anuncio).eq("id", anuncio["id"]).execute()
    else:
        db().table("anuncios").insert(anuncio).execute()
    if anuncio["grupo"]:
        otros = db().table("anuncios").select("fuente,precio").eq("grupo", anuncio["grupo"]).neq("id", anuncio["id"]).execute().data
        if otros:
            anuncio["tambien_en"] = ", ".join(o["fuente"] for o in otros)
    return anuncio, motivo_aviso


def marcar_antiguos(dias=30):
    """Oculta los anuncios que llevan mucho sin aparecer en ninguna alerta."""
    from datetime import timedelta
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    r = (
        db().table("anuncios")
        .update({"descartado": True})
        .lt("fecha_actualizacion", limite)
        .eq("descartado", False)
        .execute()
    )
    return len(r.data or [])


def avisar_telegram(anuncio, motivo):
    token = os.environ["TELEGRAM_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    precio = format(anuncio["precio"], ",").replace(",", ".") + " EUR" if anuncio.get("precio") else "sin precio"
    sup = " - " + str(anuncio["superficie"]) + " m2" if anuncio.get("superficie") else ""
    m2 = " - " + format(anuncio["precio_m2"], ",").replace(",", ".") + " EUR/m2" if anuncio.get("precio_m2") else ""
    texto = (
        "CHOLLO (" + anuncio["fuente"] + ")\n"
        + (anuncio.get("titulo") or "Vivienda") + "\n"
        + "Zona: " + (anuncio.get("municipio") or "") + "\n"
        + "Precio: " + precio + sup + m2 + "\n"
        + "Motivo: " + motivo + "\n"
        + (("Tambien en: " + anuncio["tambien_en"] + "\n") if anuncio.get("tambien_en") else "")
        + (anuncio.get("url") or "")
    )
    requests.post(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        json={"chat_id": chat, "text": texto, "disable_web_page_preview": False},
        timeout=20,
    )
    db().table("anuncios").update({"avisado": True}).eq("id", anuncio["id"]).execute()
