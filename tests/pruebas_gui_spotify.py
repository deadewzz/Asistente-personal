"""Prueba del apartado de música de Ajustes (Spotify).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_spotify.py

- La app se crea con una configuración y una carpeta de conversaciones temporales:
  la prueba no toca tus chats, tu configuración ni tu sesión de Spotify.
- Se comprueba que la sección de música se monta dentro de Ajustes (los tres botones
  y su título), que la etiqueta de estado cuenta bien cómo está la conexión —sin
  sesión, con sesión Premium y con una cuenta gratuita— y que el botón «Conectar
  Spotify» vuelve a su sitio cuando la conexión termina (no se queda «Conectando…»).
- No se prueba aquí la API de Spotify (eso está en `tests/pruebas_musica.py`, con el
  cliente de la API simulado): aquí solo la ventana.
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

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_spotify")
CONFIG = BASE + ".json"
CARPETA_CHATS = BASE + "_conversaciones"
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


def escribir_config(datos):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4)


shutil.rmtree(CARPETA_CHATS, ignore_errors=True)
os.makedirs(CARPETA_CHATS, exist_ok=True)
escribir_config({"nombre_asistente": "jarvis"})

import app_gui

app_gui.rutas.CONVERSACIONES = CARPETA_CHATS    # el historial de prueba no es el tuyo
app = app_gui.AppGUI(config_path=CONFIG)
app.update_idletasks()


def widgets(raiz):
    """Todos los widgets que hay dentro de `raiz` (customtkinter incluido)."""
    dentro = []
    pila = list(raiz.winfo_children())
    while pila:
        widget = pila.pop()
        dentro.append(widget)
        pila.extend(widget.winfo_children())
    return dentro


def textos(raiz):
    """Los textos de las etiquetas que haya dentro de `raiz`."""
    return " ".join(str(w.cget("text")) for w in widgets(raiz)
                    if isinstance(w, app_gui.ctk.CTkLabel))


# == La sección de música, dentro de Ajustes ==
app._mostrar_vista("ajustes")
dentro_de_ajustes = widgets(app.vista_ajustes)
comprobar(all(boton in dentro_de_ajustes for boton in
              (app.btn_conectar_spotify, app.btn_cfg_spotify,
               app.btn_desconectar_spotify)),
          "los tres botones de la música están dentro de Ajustes")
comprobar("música" in textos(app.vista_ajustes).lower()
          and "spotify" in textos(app.vista_ajustes).lower(),
          "la sección lleva su título (música y Spotify, sin rodeos)")
comprobar(str(app.btn_conectar_spotify.cget("text")) == "Conectar Spotify"
          and bool(app.btn_conectar_spotify.cget("command")),
          "«Conectar Spotify» es un botón de verdad, con su orden detrás")
comprobar(str(app.btn_cfg_spotify.cget("text")) == "Client ID"
          and str(app.btn_desconectar_spotify.cget("text")) == "Desconectar",
          "y al lado están «Client ID» (para pegarlo una vez) y «Desconectar»")

# == La etiqueta de estado cuenta cómo está la conexión ==
app._actualizar_estado_spotify()
comprobar("sin conectar" in str(app.lbl_spotify.cget("text")).lower()
          and app_gui.COLOR_TEXTO_SUAVE in str(app.lbl_spotify.cget("text_color")),
          "sin sesión, la etiqueta pide conectarla una vez (en tono suave)")

with open(CONFIG, "r", encoding="utf-8") as f:
    cfg = json.load(f)
cfg["spotify"] = {"cliente_id": "abc", "token": "<cifrado>", "cifrado": True,
                  "cuenta": "coutt", "premium": True}
escribir_config(cfg)
app._actualizar_estado_spotify()
texto = str(app.lbl_spotify.cget("text"))
comprobar("coutt" in texto and "Premium" in texto,
          "con sesión, la etiqueta enseña tu cuenta y que es Premium")
comprobar("sin abrir ventanas" in texto and
          app_gui.COLOR_OK in str(app.lbl_spotify.cget("text_color")),
          "y promete lo que de verdad puede hacer (poner sin abrir ventanas), en verde")

cfg["spotify"]["premium"] = False
escribir_config(cfg)
app._actualizar_estado_spotify()
comprobar("no es Premium" in str(app.lbl_spotify.cget("text")),
          "con una cuenta gratuita avisa de que dejará la canción cargada "
          "(Spotify no deja controlarla desde fuera)")

# == El botón vuelve a su sitio al terminar ==
app._conectando_spotify = True
app.btn_conectar_spotify.configure(text="Conectando…", state="disabled")
app._spotify_resuelto(False, "prueba")
comprobar(str(app.btn_conectar_spotify.cget("text")) == "Conectar Spotify"
          and str(app.btn_conectar_spotify.cget("state")) == "normal"
          and app._conectando_spotify is False,
          "al responder, el botón vuelve a su sitio (no se queda «Conectando…»)")

app.destroy()
if os.path.exists(CONFIG):
    os.remove(CONFIG)
shutil.rmtree(CARPETA_CHATS, ignore_errors=True)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
