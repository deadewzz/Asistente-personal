"""Prueba del nombre del usuario (Ajustes → «Tu nombre») y de su memoria.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_perfil.py

- La app se crea con una configuración temporal: la prueba no toca la tuya.
- Se usa el `mainloop` de verdad y se guarda como lo haría el usuario (el botón de
  Ajustes llama a `guardar_config()`), con la ventana pintándose de verdad.
- Se comprueba lo que promete el apartado: que el nombre queda guardado en
  `config_usuario.json`, que el pie de la barra lateral lo enseña —y **no** el
  usuario de la sesión de Windows, que era lo que ponía «coutt»— y que el cerebro
  lo lleva en su mensaje de sistema, que es lo que hace que lo recuerde en cada
  conversación.
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_perfil.json")
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


if os.path.exists(CONFIG):
    os.remove(CONFIG)
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui

app = app_gui.AppGUI(config_path=CONFIG)
pasos = []


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


def guardado():
    """Lo que hay ahora mismo en config_usuario.json."""
    with open(CONFIG, encoding="utf-8") as archivo:
        return json.load(archivo)


def paso_1_sin_nombre():
    print("== Sin nombre puesto, Jarvis no se lo inventa ==")
    comprobar(hasattr(app, "entry_usuario") and app.entry_usuario.get() == "",
              "Ajustes tiene su campo «Tu nombre», vacío de entrada")
    comprobar(app.lbl_usuario.cget("text") == app_gui.USUARIO_SIN_NOMBRE
              and app.avatar.cget("text") == "\u2726",
              "y el pie de la barra lateral invita a ponerlo")
    de_windows = (os.environ.get("USERNAME") or "").lower()
    comprobar(not de_windows
              or de_windows not in app.lbl_usuario.cget("text").lower(),
              "no se cuela el usuario de la sesión de Windows (antes ponía «coutt»)")
    comprobar(app.brain.nombre_usuario() == ""
              and "EL USUARIO SE LLAMA" not in app.brain.historial[0]["content"],
              "y el cerebro no da por sabido ningún nombre")
    avanzar()


def paso_2_guardar_nombre():
    print("\n== Al escribir tu nombre y guardar, se queda ==")
    app.entry_usuario.delete(0, "end")
    app.entry_usuario.insert(0, "  Ana  ")
    app.guardar_config()                    # el botón «Guardar» de Ajustes
    comprobar(guardado().get("usuario") == "Ana",
              "el nombre se guarda sin espacios de más en config_usuario.json")
    comprobar(guardado().get("nombre_asistente") == "jarvis",
              "y el resto de la configuración se conserva")
    comprobar(app.lbl_usuario.cget("text") == "Ana"
              and app.avatar.cget("text") == "A"
              and app.lbl_usuario.cget("text_color") == app_gui.COLOR_TEXTO,
              "el pie de la barra lateral lo enseña al momento, con su inicial")
    comprobar("Jarvis te llamará Ana" in app.lbl_estado.cget("text"),
              "y la ventana confirma que lo ha aprendido")
    avanzar()


def paso_3_lo_recuerda():
    print("\n== Y lo recuerda: viaja en el mensaje de sistema ==")
    prompt = app.brain.historial[0]["content"]
    comprobar("EL USUARIO SE LLAMA Ana" in prompt,
              "el cerebro lleva tu nombre en el mensaje de sistema")
    comprobar("llámalo por su nombre" in prompt and "Ajustes" in prompt,
              "con la orden de dirigirse a ti así y de dónde sale el nombre")
    cerebro = app_gui.APIBrain(CONFIG)      # como al reabrir la app
    comprobar(cerebro.nombre_usuario() == "Ana"
              and "EL USUARIO SE LLAMA Ana" in cerebro.historial[0]["content"],
              "y un cerebro nuevo (app reabierta) también lo tiene")
    comprobar(guardado().get("api_key", "") == "",
              "el nombre no arrastra una API Key que no había")
    avanzar()


def paso_4_atajo_al_ajustes():
    print("\n== El nombre del pie lleva a Ajustes ==")
    app._mostrar_vista("chat")
    comando = [w.bind("<Button-1>") for w in app._widgets_clickeables(app.avatar)]
    comprobar(any(comando) and any(w.bind("<Button-1>")
                                   for w in app._widgets_clickeables(app.lbl_usuario)),
              "tanto el avatar como el nombre son clicables")
    app.avatar._canvas.event_generate("<Button-1>", x=4, y=4)
    comprobar(app.vista_ajustes.winfo_manager() == "pack",
              "y el clic abre Ajustes, que es donde se cambia")
    avanzar()


def paso_5_volver_a_abrir():
    print("\n== Al volver a abrir la ventana, el nombre sigue ahí ==")
    datos = guardado()
    datos["usuario"] = "Bea"
    with open(CONFIG, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4)
    app._cargar_config_en_inputs()
    comprobar(app.entry_usuario.get() == "Bea"
              and app.lbl_usuario.cget("text") == "Bea"
              and app.avatar.cget("text") == "B",
              "el nombre guardado vuelve al campo de Ajustes y al pie")
    comprobar(app_gui.APIBrain(CONFIG).nombre_usuario() == "Bea",
              "y el cerebro de la nueva sesión lo lee igual")

    app.entry_usuario.delete(0, "end")
    app.guardar_config()
    comprobar(guardado().get("usuario") == ""
              and app.lbl_usuario.cget("text") == app_gui.USUARIO_SIN_NOMBRE
              and app.avatar.cget("text") == "\u2726",
              "si se borra el nombre, vuelve el aviso y el cerebro deja de usarlo")
    comprobar(app_gui.APIBrain(CONFIG).nombre_usuario() == ""
              and "EL USUARIO SE LLAMA" not in app_gui.APIBrain(CONFIG).historial[0]["content"],
              "y sin nombre no se inventa ninguno")
    avanzar()


pasos.extend([paso_1_sin_nombre, paso_2_guardar_nombre, paso_3_lo_recuerda,
              paso_4_atajo_al_ajustes, paso_5_volver_a_abrir])
app.after(500, avanzar)
app.mainloop()
app.destroy()

if os.path.exists(CONFIG):
    os.remove(CONFIG)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)