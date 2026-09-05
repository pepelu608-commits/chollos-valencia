"""Punto de entrada: recoge anuncios de todas las fuentes, los guarda y avisa de los chollos."""
import sys
import traceback

from comun import PRECIO_MAX, es_municipio_ok, guardar, avisar_telegram
from fuentes import alertas_email

FUENTES = [("Alertas portales (Idealista, Fotocasa, habitaclia, pisos.com, yaencontre)", alertas_email.obtener)]

if __name__ == "__main__":
    solo_prueba = "--prueba" in sys.argv
    total, nuevos, chollos = 0, 0, 0
    for nombre, fn in FUENTES:
        try:
            anuncios = fn()
        except Exception:
            print(f"[{nombre}] ERROR:"); traceback.print_exc(); continue
        print(f"[{nombre}] {len(anuncios)} anuncios leidos")
        for a in anuncios:
            if not a.get("precio") or a["precio"] > PRECIO_MAX:
                continue
            if not es_municipio_ok(a.get("municipio")) and not es_municipio_ok(a.get("titulo")):
                continue
            total += 1
            if solo_prueba:
                print("  ", a.get("titulo"), a.get("precio"), "EUR", a.get("url")); continue
            guardado, motivo = guardar(a)
            nuevos += 1
            if motivo:
                chollos += 1
                avisar_telegram(guardado, motivo)
    print(f"Hecho: {total} anuncios en zona y precio, {nuevos} guardados, {chollos} chollos avisados.")
