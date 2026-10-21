"""Pruebas del aviso de reuniones: acta guardada, avisos de escritorio y cortes.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_reunion.py

No graba audio ni llama a la IA: la transcripción y el acta se sustituyen por
texto fijo, y el aviso de Windows se captura con un PowerShell simulado, así que
las pruebas no muestran ningún toast ni escriben en el registro.
"""
import base64
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from modules import notificaciones
from modules.meeting_assistant import MeetingAssistant

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


def _reunion_de_prueba(notas_dir, con_audio=True):
    """Reunión ya 'grabada': solo falta transcribir y redactar el acta."""
    reunion = MeetingAssistant(config_path=os.path.join(notas_dir, "config.json"),
                               notas_dir=notas_dir)
    reunion.grabando = True
    reunion._hilos = []
    reunion._chunks_loop = ([np.zeros(16000 * 3, dtype=np.float32)]
                            if con_audio else [])
    reunion._chunks_mic = []
    reunion._meta = {"inicio": datetime.now() - timedelta(minutes=4),
                     "titulo": "Comité de seguimiento",
                     "asistentes": ["ana.gomez@acme.com"]}
    # Sin Whisper ni IA: la prueba comprueba el flujo y los avisos, no el modelo.
    reunion._transcribir = lambda audio: "Hola, probando la reunión."
    reunion._resumir = lambda transcripcion, meta=None: ("## Resumen ejecutivo\n"
                                                         "- Se probó el acta.")
    return reunion


def pruebas_acta_y_avisos():
    print("\n== Acta terminada: se guarda y se avisa ==")
    with tempfile.TemporaryDirectory() as tmp:
        reunion = _reunion_de_prueba(tmp)
        avisos, alertas = [], []
        reunion.on_notificar = lambda titulo, texto="": avisos.append((titulo, texto))
        reunion.on_alerta = alertas.append

        ruta = reunion.finalizar()

        comprobar(bool(ruta) and os.path.exists(ruta), "el acta se guarda en disco")
        contenido = ""
        if ruta:
            with open(ruta, "r", encoding="utf-8") as archivo:
                contenido = archivo.read()
        comprobar("## Transcripción" in contenido
                  and "Hola, probando la reunión." in contenido,
                  "el acta lleva la transcripción")
        comprobar("Comité de seguimiento" in contenido, "el acta lleva el título")

        titulos = [titulo for titulo, _ in avisos]
        comprobar(titulos == ["Reunión terminada", "Acta lista"],
                  "avisa al empezar a transcribir y al terminar el acta")
        comprobar(any("Procesando la reunión" in a for a in alertas),
                  "la voz sigue avisando igual")
        if len(avisos) == 2:
            comprobar("Comité de seguimiento" in avisos[1][1],
                      "el aviso final dice de qué reunión es el acta")
            comprobar("envía el acta" in avisos[1][1],
                      "el aviso final dice cómo mandarla")


def pruebas_sin_audio():
    print("\n== Sin audio suficiente ==")
    with tempfile.TemporaryDirectory() as tmp:
        reunion = _reunion_de_prueba(tmp, con_audio=False)
        avisos = []
        reunion.on_notificar = lambda titulo, texto="": avisos.append((titulo, texto))
        comprobar(reunion.finalizar() is None, "no devuelve acta")
        comprobar([t for t, _ in avisos] == ["Reunión sin audio"],
                  "avisa de que no hay audio para el acta")


def pruebas_error_al_guardar():
    print("\n== No se puede escribir el acta ==")
    with tempfile.TemporaryDirectory() as tmp:
        reunion = _reunion_de_prueba(tmp)

        def sin_disco(*args, **kwargs):
            raise OSError("disco lleno")

        reunion.guardar_acta = sin_disco
        avisos = []
        reunion.on_notificar = lambda titulo, texto="": avisos.append((titulo, texto))
        comprobar(reunion.finalizar() is None, "no devuelve acta")
        comprobar([t for t, _ in avisos] == ["Reunión terminada", "No pude guardar el acta"],
                  "avisa de que el acta no se pudo guardar")


def pruebas_buffer_de_grabacion():
    print("\n== Búfer del audio del sistema ==")
    # Con el búfer mínimo de soundcard (~10 ms) WASAPI pierde bloques y llena la
    # consola de «data discontinuity»: el búfer tiene que dar varios segundos.
    comprobar(MeetingAssistant.BUFFER_LOOPBACK >= 16000 * 2,
              "el búfer de WASAPI es de varios segundos")


def pruebas_aviso_de_windows():
    print("\n== Aviso de Windows ==")
    orden = notificaciones._comando()
    comprobar(isinstance(orden, list) and "-EncodedCommand" in orden,
              "hay orden para mostrar el aviso")
    if not orden:
        return
    script = base64.b64decode(orden[-1]).decode("utf-16-le")
    comprobar("ToastNotificationManager" in script
              and "JARVIS_AVISO_TEXTO" in script,
              "el aviso sale por la API de Windows y el texto va por entorno")

    # El aviso no puede romper la tarea: con un PowerShell simulado se comprueba
    # qué recibe, sin abrir procesos ni tocar el registro.
    llamadas = {}
    original_run = notificaciones.subprocess.run
    original_registro = notificaciones._registrar_nombre
    notificaciones.subprocess.run = lambda orden, **kw: llamadas.update(
        orden=orden, env=kw.get("env"), flags=kw.get("creationflags"))
    notificaciones._registrar_nombre = lambda: None
    try:
        notificaciones._mostrar("Acta lista", "El acta de «Reunión» ya está.\n"
                                              "Pídeme «envía el acta».")
    finally:
        notificaciones.subprocess.run = original_run
        notificaciones._registrar_nombre = original_registro

    comprobar(llamadas.get("env", {}).get("JARVIS_AVISO_TITULO") == "Acta lista",
              "el título llega al aviso")
    comprobar(llamadas.get("env", {}).get("JARVIS_AVISO_TEXTO")
              == "El acta de «Reunión» ya está. Pídeme «envía el acta».",
              "el texto llega en una línea (los saltos no rompen el toast)")
    comprobar(llamadas.get("env", {}).get("JARVIS_AVISO_APPID") == notificaciones.APP_ID,
              "el aviso va firmado con el identificador de Jarvis")

    # Si PowerShell falla, el aviso lo cuenta y no lanza la excepción.
    notificaciones.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
        OSError("sin powershell"))
    notificaciones._registrar_nombre = lambda: None
    try:
        notificaciones._mostrar("Prueba", "sin PowerShell")
        comprobar(True, "un fallo del aviso no interrumpe la tarea")
    except Exception:
        comprobar(False, "un fallo del aviso no interrumpe la tarea")
    finally:
        notificaciones.subprocess.run = original_run
        notificaciones._registrar_nombre = original_registro


def main_pruebas():
    pruebas_acta_y_avisos()
    pruebas_sin_audio()
    pruebas_error_al_guardar()
    pruebas_buffer_de_grabacion()
    pruebas_aviso_de_windows()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
