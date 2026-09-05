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
UMBRAL_DESCUENTO = float(os.getenv("UMBRAL_DESCUENTO", "20"))
UMBRAL_BAJADA = float(os.getenv("UMBRAL_BAJADA", "10"))
UMBRAL_PUNTOS = int(os.getenv("UMBRAL_PUNTOS", "70"))
MUNICIPIOS = [m.strip().lower() for m in os.getenv("MUNICIPIOS", "valencia").split(",")]

_db = None


def db():
    global _db
    if _db is None:
        _db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _db


def es_municipio_ok(texto):
    t = (texto or "").lower()
    return any(m in t for m in MUNICIPIOS)


def numero(txt):
    if txt is None:
        return None
    s = re.sub(r"[^\d]", "", str(txt))
    return int(s) if s else None


def media_zona(municipio, tipo):
    """Mediana de EUR/m2 de los anuncios que ya tenemos en esa zona (minimo 5)."""
    r = (
        db().table("anuncios")
        .select("precio_m2")
        .ilike("municipio", f"%{municipio}%")
        .eq("tipo", tipo)
        .not_.is_("precio_m2", "null")
        .limit(500)
        .execute()
    )
    valores = [x["precio_m2"] for x in r.data if x["precio_m2"]]
    return int(statistics.median(valores)) if len(valores) >= 5 else None


def _grupo(anuncio):
    """Clave para detectar el mismo piso en varios portales: municipio + superficie + precio parecido."""
    if not anuncio.get("superficie") or not anuncio.get("precio"):
        return None
    muni = re.sub(r"\W", "", (anuncio.get("municipio") or "").lower())[:12]
    return f"{muni}-{anuncio['superficie']}-{round(anuncio['precio'] / 5000)}"


def guardar(anuncio):
    """Inserta o actualiza. Devuelve (anuncio_guardado, motivo_aviso o None)."""
    ahora = datetime.now(timezone.utc).isoformat()
    if anuncio.get("precio") and anuncio.get("superficie"):
        anuncio["precio_m2"] = round(anuncio["precio"] / anuncio["superficie"])
    media = media_zona(anuncio.get("municipio") or "", anuncio.get("tipo") or "vivienda")
    anuncio["media_zona_m2"] = media
    if media and anuncio.get("precio_m2"):
        anuncio["descuento_pct"] = round(100 * (1 - anuncio["precio_m2"] / media), 1)
    anuncio["grupo"] = _grupo(anuncio)
    texto = anuncio.pop("texto", None)

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
        motivo_aviso = f"Puntuacion {puntos}/100 - " + "; ".join(motivos)
    elif bajada >= UMBRAL_BAJADA:
        motivo_aviso = f"Bajada del {bajada:.0f}% ({existente[0]['precio']:,} EUR -> {anuncio['precio']:,} EUR)".replace(",", ".")

    if existente:
        db().table("anuncios").update(anuncio).eq("id", anuncio["id"]).execute()
    else:
        db().table("anuncios").insert(anuncio).execute()
    if anuncio["grupo"]:
        otros = db().table("anuncios").select("fuente,precio").eq("grupo", anuncio["grupo"]).neq("id", anuncio["id"]).execute().data
        if otros:
            anuncio["tambien_en"] = ", ".join(f"{o['fuente']} ({o['precio']:,} EUR)".replace(",", ".") for o in otros)
    return anuncio, motivo_aviso


def avisar_telegram(anuncio, motivo):
    token = os.environ["TELEGRAM_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    precio = f"{anuncio['precio']:,} EUR".replace(",", ".") if anuncio.get("precio") else "sin precio"
    sup = f" - {anuncio['superficie']} m2" if anuncio.get("superficie") else ""
    m2 = f" - {anuncio['precio_m2']:,} EUR/m2".replace(",", ".") if anuncio.get("precio_m2") else ""
    texto = (
        f"CHOLLO ({anuncio['fuente']})\n"
        f"{anuncio.get('titulo') or 'Vivienda'}\n"
        f"Zona: {anuncio.get('municipio') or ''} {anuncio.get('zona') or ''}\n"
        f"Precio: {precio}{sup}{m2}\n"
        f"Motivo: {motivo}\n"
        + (f"Tambien en: {anuncio['tambien_en']}\n" if anuncio.get("tambien_en") else "")
        + (f"Aviso: {anuncio['alertas']}\n" if anuncio.get("alertas") else "")
        + f"{anuncio.get('url') or ''}"
    )
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": texto, "disable_web_page_preview": False},
        timeout=20,
    )
    db().table("anuncios").update({"avisado": True}).eq("id", anuncio["id"]).execute()
