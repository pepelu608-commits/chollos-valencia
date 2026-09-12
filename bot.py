"""Punto de entrada: recoge anuncios, los guarda y avisa de los chollos."""
import sys
import traceback

from comun import PRECIO_MAX, es_municipio_ok, guardar, avisar_telegram, marcar_antiguos
from fuentes import alertas_email

FUENTES = [("Alertas portales", alertas_email.obtener)]

# superficies plausibles para no meter basura en la base
SUP_MIN, SUP_MAX = 20, 600

if __name__ == "__main__":
    solo_prueba = "--prueba" in sys.argv
    total, nuevos, chollos, descartados = 0, 0, 0, 0
    for nombre, fn in FUENTES:
        try:
            anuncios = fn()
        except Exception:
            print("[" + nombre + "] ERROR:")
            traceback.print_exc()
            continue
        print("[" + nombre + "] " + str(len(anuncios)) + " anuncios leidos")
        for a in anuncios:
            if not a.get("precio") or a["precio"] > PRECIO_MAX:
                continue
            sup = a.get("superficie")
            if sup is not None and not (SUP_MIN <= sup <= SUP_MAX):
                a["superficie"] = None
                descartados += 1
            if not es_municipio_ok(a.get("municipio")) and not es_municipio_ok(a.get("titulo")):
                continue
            total += 1
            if solo_prueba:
                print("  ", a.get("municipio"), a.get("precio"), a.get("superficie"))
                continue
            guardado, motivo = guardar(a)
            nuevos += 1
            if motivo:
                chollos += 1
                avisar_telegram(guardado, motivo)
    if not solo_prueba:
        try:
            ocultados = marcar_antiguos(30)
            print("Ocultados por antiguos (mas de 30 dias sin aparecer): " + str(ocultados))
        except Exception:
            traceback.print_exc()
    print("Hecho: " + str(total) + " en zona y precio, " + str(nuevos) + " guardados, "
          + str(chollos) + " avisados, " + str(descartados) + " con superficie no fiable.")
