"""Prueba de las zonas independientes del taller de programación.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_zonas_programacion.py

Comprueba lo nuevo: que cada botón de «Qué quieres hacer» abre **su propia zona**
(su pestaña) sin pisar lo de las demás tareas, y que la misma zona se puede abrir
en una **ventana aparte** que se actualiza sola cuando el taller vuelve a escribir
en ella. La IA y el tutor se sustituyen por respuestas fijas: aquí se prueba la
ventana, no el contenido del temario.
"""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_zonas_programacion")
CONFIG = BASE + ".json"
CHAT = BASE + ".md"
CARPETA_PROG = BASE + "_avance"
CARPETA_DOCS = BASE + "_documentos"
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


for ruta in (CONFIG, CHAT):
    if os.path.exists(ruta):
        os.remove(ruta)
shutil.rmtree(CARPETA_PROG, ignore_errors=True)
shutil.rmtree(CARPETA_DOCS, ignore_errors=True)
os.makedirs(CARPETA_PROG, exist_ok=True)
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui
from modules.programming_tutor import MARCA_PROFE
from views.zona_programacion import VentanaZonaProgramacion

app_gui.rutas.DOCUMENTOS = CARPETA_DOCS     # «Guardar» no escribe en tus documentos
app = app_gui.AppGUI(config_path=CONFIG)
app.conversacion_actual = CHAT              # el historial de prueba no toca tus chats

# El tutor de verdad, pero con respuestas fijas: aquí se prueba la ventana, no la IA.
tutor = app.system.programacion
tutor.bases = lambda: "## \U0001F4D6 Bases de prueba\n\nContenido de bases.\n"
tutor.leccion = lambda tema: (f"## \U0001F4D8 Lección de {tema or 'bucles'}\n\n"
                              f"Contenido de lección de {tema or 'bucles'}.\n")
tutor.ejercicios = lambda tema, cuantos: (
    f"## \u270F Ejercicios de {tema or 'bucles'}\n\nContenido de ejercicios ({cuantos}).\n")
tutor.documentacion = lambda tema: "## \U0001F4D1 Documentación de prueba\n\nContenido de doc.\n"
tutor.comparar = lambda tema: "## \u2696 Comparación de prueba\n\nContenido de comparación.\n"
tutor.progreso = lambda accion=None: "## \U0001F4CA Mi avance de prueba\n\nContenido de avance.\n"

pasos = []


def ejecutar(paso):
    """Corre un paso y sigue con el siguiente aunque falle (sin colgar la ventana)."""
    print(f"\n== {paso.__name__} ==")
    try:
        paso()
    except Exception as e:
        comprobar(False, f"el paso {paso.__name__} no debe fallar ({e!r})")
    app.update_idletasks()
    avanzar(140)


def avanzar(retardo=300):
    if pasos:
        app.after(retardo, lambda: ejecutar(pasos.pop(0)))
    else:
        app.after(retardo, app.quit)


def paso_1_cada_boton_su_zona():
    app.btn_programar.invoke()
    app.update_idletasks()
    comprobar({"clase", "chat"} <= set(app.zonas_programacion()),
              "el taller arranca con la zona de la clase y la del chat")
    app.botones_prog["bases"].invoke()
    app.update_idletasks()
    zonas = app.zonas_programacion()
    comprobar("bases" in zonas and zonas["bases"]["marco"].winfo_manager() == "grid",
              "«Bases» abre su propia zona (su pestaña) en el centro")
    comprobar(zonas["clase"]["marco"].winfo_manager() == "",
              "y la zona de la clase se aparta (no se pisan)")
    comprobar("Contenido de bases" in app.texto_programacion_visible(),
              "lo que se ve es lo de «Bases», en tarjetas")
    comprobar(app._panel_prog == "bases" and "bases" in app.botones_prog_panel,
              "su pestaña queda marcada como la zona abierta")


def paso_2_una_zona_no_pisa_otra():
    app.entry_prog_tema.delete(0, "end")
    app.entry_prog_tema.insert(0, "bucles")
    app.botones_prog["leccion"].invoke()
    app.update_idletasks()
    zonas = app.zonas_programacion()
    comprobar("leccion" in zonas and zonas["leccion"]["marco"].winfo_manager() == "grid",
              "«Lección» abre otra zona distinta")
    comprobar(zonas["bases"]["marco"].winfo_manager() == "",
              "y «Bases» se guarda (no se borra): su pestaña sigue ahí")
    comprobar("Contenido de bases" in (zonas["bases"].get("texto") or ""),
              "lo que había en «Bases» se conserva intacto")
    comprobar("Contenido de lección de bucles" in app.texto_programacion_visible(),
              "y lo que se ve ahora es la lección del tema pedido")
    comprobar(len(app.botones_prog_panel) >= 4,
              "cada zona abierta tiene su pestaña (clase, chat, bases, lección)")


pasos.extend([paso_1_cada_boton_su_zona, paso_2_una_zona_no_pisa_otra])



def paso_3_ventana_propia():
    ventana = app.abrir_zona_en_ventana("leccion")
    app.update_idletasks()
    comprobar(isinstance(ventana, VentanaZonaProgramacion),
              "la zona se abre en una ventana aparte (zona independiente)")
    comprobar(ventana.titulo == "Lección del tema" and ventana.winfo_exists(),
              "con el título de su tarea en la cabecera")
    comprobar(bool(ventana.tarjetas) and "Contenido de lección" in ventana.texto,
              "y dentro, las mismas tarjetas que su pestaña")
    app._escribir_en_zona("leccion", "## \U0001F4D8 Lección nueva\n\n"
                                     "Contenido nuevo en la ventana.\n")
    app.update_idletasks()
    comprobar("Contenido nuevo en la ventana" in ventana.texto,
              "si el taller vuelve a escribir en la zona, la ventana se actualiza sola")
    otra = app.abrir_zona_en_ventana("leccion")
    comprobar(otra is ventana,
              "volver a pedir la ventana trae al frente la misma (no abre otra)")


def paso_4_copiar_y_guardar():
    comprobar(app.copiar_zona_programacion("bases"),
              "«Copiar» de una zona funciona aunque no sea la que se está viendo")
    comprobar("Contenido de bases" in app.clipboard_get(),
              "y deja en el portapapeles lo de esa zona, no lo de la pestaña abierta")
    ruta = app.guardar_zona_programacion("bases")
    guardado = os.path.isfile(ruta)
    comprobar(guardado and os.path.basename(ruta).startswith("Bases del curso"),
              "«Guardar» deja la zona como .md en documentos, con su título")
    if guardado:
        with open(ruta, encoding="utf-8") as archivo:
            comprobar(archivo.read() == app.zonas_programacion()["bases"]["texto"],
                      "con el texto entero de esa zona")
    comprobar(app.copiar_zona_programacion("progreso") is False,
              "una zona que aún no tiene contenido no copia nada (y lo avisa)")


def paso_5_revision_y_chat():
    app.botones_prog["corregir"].invoke()
    app.update_idletasks()
    zonas = app.zonas_programacion()
    comprobar("revision" in zonas and zonas["revision"]["marco"].winfo_manager() == "grid",
              "«Corregir» tiene también su propia zona de revisión")
    comprobar(bool((zonas["revision"].get("texto") or "").strip()),
              "con el resultado del compilador dentro")
    comprobar("Contenido nuevo en la ventana" in (zonas["leccion"].get("texto") or ""),
              "y sin tocar lo que ya había en la lección")
    app.mostrar_panel_programacion("chat")
    app.update_idletasks()
    comprobar(app.marco_chat_prog.winfo_manager() == "grid"
              and zonas["revision"]["marco"].winfo_manager() == "",
              "el chat del taller sigue siendo una zona aparte (y se abre sola)")
    comprobar(app.abrir_zona_en_ventana("chat") is None,
              "el chat no abre ventana: ya tiene su sitio en su pestaña")


def paso_6_cerrar_la_ventana():
    ventana = app.zonas_programacion()["leccion"]["ventana"]
    if ventana is not None and ventana.winfo_exists():
        ventana._cerrar()
        app.update_idletasks()
    comprobar(app.zonas_programacion()["leccion"]["ventana"] is None,
              "cerrar la ventana no se lleva por delante la zona del taller")
    comprobar("Contenido nuevo en la ventana"
              in app.zonas_programacion()["leccion"]["texto"],
              "la zona conserva su contenido después de cerrar su ventana")
    nueva = app.abrir_zona_en_ventana("leccion")
    comprobar(isinstance(nueva, VentanaZonaProgramacion) and nueva.winfo_exists(),
              "y se puede volver a abrir cuando haga falta")


def paso_7_la_ia_escribe_en_su_zona():
    tutor.ejercicios = lambda tema, cuantos: MARCA_PROFE + "Prepara ejercicios de bucles."
    app.brain.analizar_documento = lambda texto, sistema=None: (
        "## \u270F Ejercicios con IA\n\nContenido de la IA en su zona.\n")
    app.botones_prog["ejercicios"].invoke()
    # La respuesta llega de un hilo: se espera sin bloquear el bucle de la ventana.
    import time
    limite = time.time() + 3
    while time.time() < limite:
        if "Contenido de la IA en su zona" in (
                app.zonas_programacion().get("ejercicios", {}).get("texto") or ""):
            break
        app.update()
        time.sleep(0.02)
    zona = app.zonas_programacion().get("ejercicios") or {}
    comprobar("Contenido de la IA en su zona" in (zona.get("texto") or ""),
              "la respuesta de la IA se queda en la zona de esa tarea")
    comprobar("Listo" in zona["lbl_estado"].cget("text"),
              "y su zona avisa de que ya está lista")
    comprobar("Contenido nuevo en la ventana"
              in (app.zonas_programacion()["leccion"].get("texto") or ""),
              "sin pisar lo que había en las demás zonas")


pasos.extend([paso_3_ventana_propia, paso_4_copiar_y_guardar,
              paso_5_revision_y_chat, paso_6_cerrar_la_ventana,
              paso_7_la_ia_escribe_en_su_zona])

app.after(200, lambda: ejecutar(pasos.pop(0)))
app.mainloop()

print(f"\n{total[0] - len(fallos)}/{total[0]} comprobaciones bien")
if fallos:
    print("\nFallos:")
    for fallo in fallos:
        print(f"  · {fallo}")
    sys.exit(1)
print("Todo bien: cada botón abre su zona, y su zona se abre en su ventana.")
