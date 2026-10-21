"""Prueba del apartado «Clase de inglés» de la ventana (su botón y su panel).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_ingles.py

- La app se crea con una configuración, un avance de inglés y una carpeta de
  documentos temporales: la prueba no toca tus chats, tu avance ni tus documentos.
- Se usa el `mainloop` de verdad y se pulsa el botón de la barra lateral igual que
  lo haría el usuario.
- La IA se sustituye por una función de mentira: aquí se prueba la ventana (que el
  apartado pida la clase con el mensaje de profesor, que la enseñe entera en las
  tarjetas de su panel —una por apartado, con su icono— y que nada de esto se cuele
  en el chat), no la IA.
"""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_ingles")
CONFIG = BASE + ".json"
CHAT = BASE + ".md"
CARPETA_INGLES = BASE + "_avance"
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
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui
from modules.api_brain import APIBrain
from modules.english_tutor import EnglishTutor

app_gui.rutas.DOCUMENTOS = CARPETA_DOCS     # «Guardar» no escribe en tus documentos
app = app_gui.AppGUI(config_path=CONFIG)
app.conversacion_actual = CHAT              # el historial de prueba no toca tus chats
# El tutor de verdad, pero con su nivel y su historial en una carpeta temporal
app.system.ingles = EnglishTutor(config_path=CONFIG, carpeta=CARPETA_INGLES)

pasos = []
encargos = []          # (encargo, mensaje de sistema) de cada clase pedida a la IA
dichos = []            # (texto, idioma) de cada frase dicha en voz alta
clase = ("## ✅ Versión corregida\n\nI am 30 years old.\n\n"
         "## 🔍 Punto por punto\n\n- *I have 30 years* → *I am 30 years old*\n\n"
         "## ✍️ Ejercicios\n\n1. Completa: I ___ (be) from Madrid.")
fin_clase = "1. Completa: I ___ (be) from Madrid."
#: Lo que devuelve la IA en el modo hablado: la réplica va en inglés (es lo que se
#: lee en voz alta) y la corrección y la pronunciación, por escrito.
clase_speaking = (
    "## \U0001F4AC Lo que digo yo\n\nThat sounds great! What did you do yesterday?\n\n"
    "## \U0001F50D Cómo lo has dicho\n\n**I went to the office yesterday.**\n\n"
    "## \U0001F50A Pronunciación\n\n*office*, con la fuerza en la primera sílaba.\n")


def ejecutar(paso):
    """Corre un paso y sigue con el siguiente aunque falle (sin colgar la ventana)."""
    try:
        paso()
    except Exception as e:
        comprobar(False, f"el paso {paso.__name__} no debe fallar ({e!r})")
        avanzar(100)


def avanzar(retardo=300):
    """Ejecuta el siguiente paso (o cierra la ventana si ya no hay más)."""
    if pasos:
        app.after(retardo, lambda: ejecutar(pasos.pop(0)))
    else:
        app.after(retardo, app.quit)


def panel():
    """Lo que se está viendo ahora mismo en las tarjetas del panel de la clase."""
    return app.texto_clase_visible()


def paso_1_entrar():
    print("== El botón «Inglés» lleva a su apartado ==")
    comprobar(app.vista_chat.winfo_manager() == "pack"
              and app.vista_ingles.winfo_manager() == "",
              "la ventana arranca en el chat, con el apartado sin montar")
    comprobar(app.btn_ingles.master is app.sidebar
              and "Inglés" in app.btn_ingles.cget("text"),
              "el botón del apartado está en la barra lateral")
    app.btn_ingles.invoke()                 # como si se pulsara con el ratón
    comprobar(app.vista_ingles.winfo_manager() == "pack"
              and app.vista_chat.winfo_manager() == "",
              "al pulsarlo se abre el apartado (y el chat se aparta)")
    comprobar(app.btn_ingles.cget("fg_color") == app_gui.COLOR_TARJETA,
              "y queda marcado en la barra lateral mientras está abierto")
    comprobar("Nivel B1" in app.lbl_ingles_resumen.cget("text")
              and "0 prácticas" in app.lbl_ingles_resumen.cget("text")
              and "sin fallos apuntados" in app.lbl_ingles_resumen.cget("text"),
              "la cabecera cuenta cómo va el alumno: nivel, prácticas y fallos")
    comprobar("Cómo se usa" in [titulo for titulo, _area in app._tarjetas_clase]
              and "Corregir" in panel(),
              "y el panel arranca con la ayuda de uso, en tarjetas con su título")
    comprobar(app.menu_ingles_nivel.get() == "B1",
              "el nivel del alumno está puesto en el desplegable del apartado")
    avanzar()


def paso_2_avance_sin_ia():
    print("\n== «Mi avance» se resuelve sin IA y sin tocar el chat ==")
    comprobar(app.vista_ingles.winfo_ismapped(),
              "el apartado ya está a la vista (no solo montado)")
    app.brain.analizar_documento = lambda texto, sistema=None: (
        comprobar(False, "«Mi avance» no debe llamar a la IA") or "")
    app._accion_ingles("progreso")
    comprobar("Tutor de inglés" in panel() and "Prácticas: 0" in panel(),
              "el panel enseña el avance que el tutor arma en local")
    comprobar("IA" in app.lbl_ingles_estado.cget("text"),
              "y su línea de estado avisa de que no hay nada que pedirle a la IA")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "nada de esto se cuela en el chat ni en tu historial")
    avanzar()


def paso_3_corregir_con_ia():
    print("\n== Corregir: la clase se pide a la IA y llega al panel ==")
    app.brain.analizar_documento = lambda texto, sistema=None: (
        encargos.append((texto, sistema)) or clase)
    app.txt_ingles_texto.insert("1.0", "yesterday i go to the office and my boss say me hello")
    app._accion_ingles("corregir")
    comprobar(app.lbl_ingles_estado.cget("text").startswith("Escribiendo"),
              "mientras la IA escribe, el apartado lo dice")
    avanzar(600)


def paso_4_clase_en_el_panel():
    print("\n== La clase entera en el panel, y el chat limpio ==")
    comprobar(bool(encargos) and encargos[0][1] == APIBrain.SISTEMA_TUTOR,
              "la clase se le pide a la IA con el mensaje de profesor (SISTEMA_TUTOR)")
    comprobar(bool(encargos) and "hispanohablante" in encargos[0][0]
              and "nivel" in encargos[0][0],
              "y con el encargo del tutor, que lleva el nivel del alumno delante")
    comprobar(bool(encargos) and "yesterday i go to the office" in encargos[0][0],
              "con el texto del alumno tal cual lo escribió")
    comprobar("I am 30 years old." in panel() and fin_clase in panel(),
              "el panel enseña la clase entera, hasta el último ejercicio")
    comprobar([titulo for titulo, _area in app._tarjetas_clase]
              == ["Versión corregida", "Punto por punto", "Ejercicios"],
              "cada apartado de la clase es una tarjeta con su título (sin el ###)")
    comprobar([tarjeta["icono"] for tarjeta in app._marcos_clase] == ["✅", "🔍", "✍️"],
              "y cada tarjeta lleva delante el icono que manda la IA en el título")
    comprobar(app._marcos_clase[0]["marco"].cget("border_color") == app_gui.COLOR_ACENTO
              and app._marcos_clase[1]["marco"].cget("border_color") == app_gui.COLOR_BORDE,
              "la tarjeta de la versión corregida sobresale con el borde de acento")
    comprobar(app.lbl_ingles_estado.cget("text").startswith("Clase lista"),
              "la línea de estado avisa de que ya está lista")
    comprobar(app.btn_ingles_copiar.cget("state") == "normal"
              and app.btn_ingles_guardar.cget("state") == "normal",
              "y la clase se puede copiar o guardar")
    avance = app.system.ingles.resumen()
    comprobar(avance["practicas"] == 1 and bool(avance["repetidos"])
              and "1 prácticas" in app.lbl_ingles_resumen.cget("text"),
              "el tutor apunta la práctica y los fallos, y la cabecera lo cuenta")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "en el chat no ha aparecido nada de esto")
    avanzar()


def paso_5_guardar_y_copiar():
    print("\n== Guardar la clase en documentos y copiarla ==")
    app.btn_ingles_guardar.invoke()
    archivos = os.listdir(CARPETA_DOCS) if os.path.isdir(CARPETA_DOCS) else []
    guardadas = [nombre for nombre in archivos if nombre.endswith(".md")]
    contenido = ""
    if guardadas:
        with open(os.path.join(CARPETA_DOCS, guardadas[0]), encoding="utf-8") as f:
            contenido = f.read()
    comprobar(bool(guardadas) and "Clase de inglés" in guardadas[0] and clase in contenido,
              "«Guardar en documentos» deja la clase en un .md de la carpeta")
    comprobar("Clase guardada en" in app.lbl_ingles_estado.cget("text"),
              "y el apartado dice dónde la ha dejado")
    app.btn_ingles_copiar.invoke()
    try:
        copiado = app.clipboard_get()
    except Exception as e:
        copiado = f"no pude leer el portapapeles: {e}"
    comprobar(copiado == clase, "«Copiar» manda la clase al portapapeles")
    avanzar()


def paso_6_nivel():
    print("\n== El nivel se cambia desde el apartado ==")
    app.menu_ingles_nivel.set("C1")
    app.menu_ingles_nivel.cget("command")("C1")     # lo que dispara el desplegable
    comprobar(app.system.ingles.nivel() == "C1" and app.menu_ingles_nivel.get() == "C1",
              "elegir otro nivel lo fija en el tutor")
    comprobar("Nivel C1" in app.lbl_ingles_resumen.cget("text")
              and "Nivel C1" in app.lbl_ingles_estado.cget("text"),
              "y se ve en la cabecera y en la línea de estado")
    avanzar()


def paso_7_borrar_historial():
    print("\n== Borrar el historial pide confirmación ==")
    app._accion_ingles("borrar")
    comprobar("Pulsa otra vez" in app.lbl_ingles_estado.cget("text")
              and bool(app.system.ingles.resumen()["repetidos"]),
              "la primera pulsación avisa y no borra nada")
    app._accion_ingles("borrar")
    comprobar(not app.system.ingles.resumen()["repetidos"]
              and "He borrado el historial" in panel(),
              "la segunda borra los fallos y lo cuenta en el panel")
    comprobar("sin fallos apuntados" in app.lbl_ingles_resumen.cget("text"),
              "y la cabecera se queda sin fallos que enseñar")
    avanzar()


def paso_7b_speaking():
    print("\n== Speaking: hablar en inglés con el micrófono ==")
    comprobar("speaking" in app.botones_ingles
              and "\U0001F5E3" in app.botones_ingles["speaking"].cget("text"),
              "el apartado tiene su tarea «Speaking» en la rejilla")
    comprobar(app.btn_ingles_mic.master is app.marco_ingles_mic
              and int(app.btn_ingles_mic.cget("corner_radius")) * 2
              == int(app.btn_ingles_mic.cget("height")),
              "y un micrófono redondo en su anillo, junto a la clase")
    comprobar(getattr(getattr(app.btn_ingles_mic, "_command", None), "__func__", None)
              is app_gui.AppGUI._toggle_speaking,
              "que es el botón que enciende y apaga el speaking")
    comprobar("Micrófono apagado" in app.lbl_speaking.cget("text"),
              "de entrada avisa de que el micrófono está apagado")

    # El micrófono, la IA y la voz se sustituyen: aquí se prueba la ventana, no el audio.
    del dichos[:]
    frases = ["i am go to the office yesterday"]
    app.voice.escuchar_ingles = lambda: frases.pop() if frases else None
    app.brain.analizar_documento = lambda texto, sistema=None: (
        encargos.append((texto, sistema)) or clase_speaking)
    app.reproducir_voz = lambda texto, modelo_rvc=None, idioma="es": dichos.append(
        (texto, idioma))
    app.entry_ingles_tema.delete(0, "end")
    app._accion_ingles("speaking")
    comprobar(app._speaking_activo
              and app.btn_ingles_mic.cget("fg_color") == app_gui.COLOR_ACENTO
              and app.btn_ingles_mic.cget("text_color") == app_gui.COLOR_ACENTO_TEXTO,
              "al pulsar «Speaking» el micrófono se enciende (icono oscuro sobre el acento)")
    comprobar(app.marco_ingles_mic.cget("border_color") in
              (app_gui.COLOR_ACENTO, app_gui.COLOR_ACENTO_2,
               app_gui._mezclar(app_gui.COLOR_ACENTO, app_gui.COLOR_PANEL, 0.55)),
              "y su anillo empieza a latir, como el del chat")
    comprobar("Te escucho" in app.lbl_speaking.cget("text"),
              "mientras que la tarjeta dice que te está escuchando")
    avanzar(1200)


def paso_7c_speaking_turno():
    print("\n== El turno hablado: lo que dices, la clase y la voz inglesa ==")
    comprobar(bool(encargos) and encargos[-1][1] == APIBrain.SISTEMA_TUTOR,
              "la charla se le pide a la IA con el mensaje de sistema del profesor")
    comprobar(bool(encargos) and "HABLADA" in encargos[-1][0]
              and "i am go to the office yesterday" in encargos[-1][0],
              "y con lo que se ha oído por el micrófono, como charla hablada")
    visible = panel()
    comprobar("Tú has dicho" in visible and "i am go to the office" in visible,
              "el panel enseña tu turno (lo que ha oído el micrófono)")
    comprobar("I went to the office" in visible and "Pronunciación" in visible,
              "y la clase del tutor: la corrección y la pronunciación por escrito")
    comprobar([tarjeta["icono"] for tarjeta in app._marcos_clase]
              == ["\U0001F5E3", "\U0001F4AC", "\U0001F50D", "\U0001F50A"],
              "con el turno del alumno y los apartados del speaking, cada uno con su icono")
    comprobar(bool(dichos) and dichos[-1][1] == "en"
              and dichos[-1][0] == "That sounds great! What did you do yesterday?",
              "la réplica (y solo la réplica) se lee en voz alta con voz inglesa")
    comprobar(app.btn_speaking_repetir.cget("state") == "normal",
              "y el botón «Repetir» queda listo para volver a oírla")
    app._toggle_speaking()
    comprobar(not app._speaking_activo
              and app.marco_ingles_mic.cget("border_color") == app_gui.COLOR_BORDE
              and app.btn_ingles_mic.cget("fg_color") == app_gui.COLOR_TARJETA,
              "al volver a pulsarlo se para y el anillo se apaga")
    comprobar("Micrófono apagado" in app.lbl_speaking.cget("text"),
              "y la tarjeta lo dice")
    avanzar()


def paso_8_volver_al_chat():
    print("\n== «Volver al chat» deja el apartado como estaba ==")
    app._mostrar_vista("chat")
    comprobar(app.vista_chat.winfo_manager() == "pack"
              and app.vista_ingles.winfo_manager() == "",
              "el chat vuelve a ocupar su sitio")
    comprobar(app.btn_ingles.cget("fg_color") == "transparent",
              "y el botón del apartado deja de estar marcado")
    comprobar(all(clase not in burbuja["texto"] for burbuja in app._burbujas),
              "la clase no se ha copiado al chat al salir")
    avanzar()


pasos.extend([paso_1_entrar, paso_2_avance_sin_ia, paso_3_corregir_con_ia,
              paso_4_clase_en_el_panel, paso_5_guardar_y_copiar, paso_6_nivel,
              paso_7_borrar_historial, paso_7b_speaking, paso_7c_speaking_turno,
              paso_8_volver_al_chat])
app.after(500, avanzar)
app.mainloop()
app.destroy()

for ruta in (CONFIG, CHAT):
    if os.path.exists(ruta):
        os.remove(ruta)
for carpeta in (CARPETA_INGLES, CARPETA_DOCS):
    shutil.rmtree(carpeta, ignore_errors=True)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
