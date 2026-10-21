"""Prueba de los atajos de edición de las cajas de escribir (Ctrl+Supr y compañía).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_atajos.py

- La app se crea con una configuración y una carpeta de conversaciones temporales:
  la prueba no toca tus chats ni tu configuración.
- Tk trae en las cajas de texto pocos atajos (los de Emacs: Ctrl+K, Ctrl+D...) y le
  faltan los que se dan por hechos en Windows: borrar la línea entera con Ctrl+Supr,
  la palabra anterior con Ctrl+Retroceso, seleccionar todo con Ctrl+A, deshacer y
  rehacer, y saltar de palabra con Ctrl+←/→. Aquí se comprueba que la ventana los
  pone (en el chat, en «Tu inglés», en las reglas y en los campos de una línea) y
  que hacen lo que se espera, pulsando la tecla de verdad.
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

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_atajos")
CONFIG = BASE + ".json"
CARPETA_CHATS = BASE + "_conversaciones"
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


if os.path.exists(CONFIG):
    os.remove(CONFIG)
shutil.rmtree(CARPETA_CHATS, ignore_errors=True)
os.makedirs(CARPETA_CHATS, exist_ok=True)
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui

app_gui.rutas.CONVERSACIONES = CARPETA_CHATS    # el historial de prueba no es el tuyo
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


def pulsar(caja, secuencia):
    """Pulsa una tecla de verdad en la caja (como si la escribieras tú)."""
    caja.focus_force()
    caja.event_generate(secuencia)
    app.update()


def caja_chat(texto=""):
    """Deja la caja del chat con ese texto y el cursor al final, y sin el aviso."""
    app._despertar_input()                  # fuera el aviso: se va a escribir
    app.entry_chat.delete("1.0", "end")
    if texto:
        app.entry_chat.insert("1.0", texto)
    app.entry_chat._textbox.mark_set("insert", "end-1c")
    app.entry_chat._textbox.edit_reset()    # lo escrito es el punto de partida
    return app.entry_chat._textbox


def escrito():
    """Lo que hay ahora mismo en la caja del chat."""
    return app.entry_chat.get("1.0", "end-1c")


def paso_1_atajos_puestos():
    print("== La ventana pone los atajos en las cajas de escribir ==")
    for nombre, caja in (("el chat", app.entry_chat._textbox),
                         ("«Tu inglés»", app.txt_ingles_texto._textbox),
                         ("las reglas permanentes", app.txt_reglas._textbox)):
        puestos = [s for s, _ in app_gui.ATAJOS_CAJA if caja.bind(s)]
        comprobar(len(puestos) == len(app_gui.ATAJOS_CAJA),
                  f"{nombre} lleva los {len(app_gui.ATAJOS_CAJA)} atajos (Ctrl+Supr, "
                  "Ctrl+Retroceso, Ctrl+A, Ctrl+Z/Ctrl+Y, Ctrl+←/→)")
    comprobar(bool(app.entry_chat._textbox.cget("undo")),
              "y la caja del chat sabe deshacer (undo=True, que Tk no pone solo)")
    comprobar(app._chat_vacio and app._texto_input() == "",
              "de entrada solo está el aviso de la caja: no hay mensaje escrito")
    avanzar()


def paso_2_ctrl_supr_borra_linea():
    print("\n== Ctrl+Supr borra la línea entera donde está el cursor ==")
    caja = caja_chat("primera\nsegunda con más cosas\ntercera")
    caja.mark_set("insert", "2.4")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "primera\ntercera",
              "la línea del medio desaparece entera, con su salto")
    comprobar(caja.index("insert") == "2.0",
              "y el cursor se queda al principio de la línea que baja")
    caja = caja_chat("primera\nultima")
    caja.mark_set("insert", "2.2")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "primera",
              "en la última línea no queda un renglón en blanco detrás")
    caja = caja_chat("solo esto")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "" and app._texto_input() == "",
              "y con una sola línea la caja queda vacía de verdad")
    caja = caja_chat("uno\ndos tres\ncuatro")
    caja.tag_add("sel", "2.0", "2.3")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "uno\ncuatro",
              "con algo seleccionado, se lleva las líneas que toca la selección")
    caja = caja_chat("uno\ndos tres\ncuatro")
    caja.mark_set("insert", "2.0 lineend")
    pulsar(caja, "<Control-Shift-Delete>")
    comprobar(escrito() == "uno\ndos trescuatro",
              "Ctrl+Mayús+Supr al final de la línea solo junta con la siguiente")
    caja = caja_chat("uno\ndos tres\ncuatro")
    caja.mark_set("insert", "2.4")
    pulsar(caja, "<Control-Shift-Delete>")
    comprobar(escrito() == "uno\ndos \ncuatro",
              "y desde el medio, borra hasta el final de la línea")
    avanzar()


def paso_3_ctrl_retroceso_palabra():
    print("\n== Ctrl+Retroceso borra la palabra de la izquierda ==")
    caja = caja_chat("hola mundo entero")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == "hola mundo ", "se lleva la última palabra")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == "hola mundo",
              "el hueco que quedaba se va en la siguiente pulsación")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == "hola ", "y después ya la palabra anterior")
    caja = caja_chat("uno\ndos")
    caja.mark_set("insert", "2.0")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == "unodos",
              "al principio de una línea junta las dos, sin comerse la de arriba")
    caja = caja_chat("uno\n   dos")
    caja.mark_set("insert", "2.3")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == "uno\n  dos", "y con huecos delante no se sale de la línea")
    caja = caja_chat("hola mundo")
    caja.tag_add("sel", "1.0", "1.4")
    pulsar(caja, "<Control-BackSpace>")
    comprobar(escrito() == " mundo", "con algo seleccionado, borra la selección")
    avanzar()


def paso_4_ctrl_a_deshacer_rehacer():
    print("\n== Ctrl+A selecciona todo y Ctrl+Z/Ctrl+Y deshacen y rehacen ==")
    caja = caja_chat("primera línea\nsegunda línea")
    pulsar(caja, "<Control-a>")
    comprobar(bool(caja.tag_ranges("sel"))
              and caja.get("sel.first", "sel.last") == "primera línea\nsegunda línea",
              "Ctrl+A selecciona todo el mensaje")
    caja = caja_chat()
    app.entry_chat.insert("1.0", "hola")
    pulsar(caja, "<Control-z>")
    comprobar(escrito() == "", "Ctrl+Z deshace lo escrito")
    pulsar(caja, "<Control-y>")
    comprobar(escrito() == "hola", "y Ctrl+Y lo vuelve a poner")
    caja = caja_chat("borrador")
    pulsar(caja, "<Control-z>")
    comprobar(escrito() == "borrador",
              "Ctrl+Z sin nada que deshacer no cambia lo que hay (ni da error)")
    caja = caja_chat()
    pulsar(caja, "<Control-z>")
    pulsar(caja, "<Control-z>")
    comprobar(escrito() == "",
              "e insistir con la caja vacía la deja vacía, sin quejarse")
    avanzar()


def paso_5_mover_de_palabra():
    print("\n== Ctrl+←/→ mueven de palabra (y con Mayús, seleccionando) ==")
    caja = caja_chat("uno dos tres")
    pulsar(caja, "<Control-Left>")
    comprobar(caja.index("insert") == "1.8", "Ctrl+← salta al principio de la palabra")
    pulsar(caja, "<Control-Shift-Left>")
    comprobar(bool(caja.tag_ranges("sel"))
              and caja.get("sel.first", "sel.last").strip() == "dos",
              "y con Mayús se va seleccionando de palabra en palabra")
    pulsar(caja, "<Control-Right>")
    comprobar(caja.index("insert") == "1.8",
              "Ctrl+→ vuelve al principio de la palabra que sigue")
    avanzar()


def paso_6_aviso_del_chat():
    print("\n== El aviso de la caja del chat («Escribe un mensaje…») no ensucia ==")
    app._chat_vacio = False
    app.entry_chat.delete("1.0", "end")
    app._poner_fantasma()
    comprobar(app._chat_vacio and escrito() == app_gui.AVISO_INPUT,
              "la caja vacía vuelve a enseñar su aviso")
    caja = app.entry_chat._textbox
    pulsar(caja, "<Control-a>")
    comprobar(escrito() == "" and not app._chat_vacio,
              "Ctrl+A se lleva el aviso: a partir de ahí se escribe de verdad")
    comprobar(not caja.tag_ranges("sel"),
              "y no deja nada seleccionado que se pueda borrar sin querer")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "", "y Ctrl+Supr sobre la caja vacía no rompe nada")
    app.entry_chat.insert("1.0", "un mensaje largo\nque ocupa dos líneas")
    app._tecla_soltada()          # como al soltar la última tecla al escribir
    comprobar(app._alto_input_actual > app_gui.ALTO_INPUT_MIN,
              "al escribir en varias líneas la caja crece, como siempre")
    caja.mark_set("insert", "2.0")
    pulsar(caja, "<Control-Delete>")
    comprobar(escrito() == "un mensaje largo"
              and app._alto_input_actual == app_gui.ALTO_INPUT_MIN,
              "y al quitar una línea con Ctrl+Supr vuelve a su alto de una línea")
    avanzar()


def paso_7_campos_de_una_linea():
    print("\n== Los campos de una línea (Tu nombre, la API Key...) también ==")
    # Las teclas solo llegan a lo que se ve: se abre Ajustes, que es donde están.
    app._mostrar_vista("ajustes")
    app.update()
    campo = app.entry_usuario._entry
    comprobar(bool(campo.bind("<Control-a>")) and bool(campo.bind("<Control-BackSpace>")),
              "el campo «Tu nombre» lleva sus atajos")
    campo.delete(0, "end")
    campo.insert(0, "Ana María López")
    campo.icursor("end")
    pulsar(campo, "<Control-BackSpace>")
    comprobar(campo.get() == "Ana María ",
              "Ctrl+Retroceso borra la palabra anterior del campo")
    pulsar(campo, "<Control-a>")
    comprobar(campo.selection_present()
              and campo.get()[campo.index("sel.first"):campo.index("sel.last")] == "Ana María ",
              "Ctrl+A selecciona todo el campo")
    campo.selection_clear()
    campo.icursor("4")
    pulsar(campo, "<Control-Delete>")
    comprobar(campo.get() == "Ana ",
              "y Ctrl+Supr borra del cursor al final del campo")
    campo.delete(0, "end")
    avanzar()


pasos.extend([paso_1_atajos_puestos, paso_2_ctrl_supr_borra_linea,
              paso_3_ctrl_retroceso_palabra, paso_4_ctrl_a_deshacer_rehacer,
              paso_5_mover_de_palabra, paso_6_aviso_del_chat,
              paso_7_campos_de_una_linea])
app.after(500, avanzar)
app.mainloop()
app.destroy()

shutil.rmtree(CARPETA_CHATS, ignore_errors=True)
if os.path.exists(CONFIG):
    os.remove(CONFIG)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
