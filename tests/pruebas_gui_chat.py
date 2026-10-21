"""Prueba de que el chat enseña lo que el asistente está haciendo.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_chat.py

- La app se crea con una configuración y una conversación temporales (no toca tus
  datos ni tus chats).
- Se usa el `mainloop` de verdad: los pasos llegan desde un hilo de fondo y se
  pintan con `after()`, igual que cuando SharePoint tarda un minuto.
- El cerebro y el ejecutor se sustituyen por funciones de mentira: aquí se prueba
  la ventana (qué se ve), no la IA ni las acciones.
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_chat.json")
CHAT = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_chat.md")
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

app = app_gui.AppGUI(config_path=CONFIG)
app.conversacion_actual = CHAT          # el historial de prueba no toca tus chats
app.brain.procesar_mensaje = lambda texto: ("", "ACCION_DE_PRUEBA|1")
app.system.ejecutar_comando = lambda comando: "Respuesta de prueba"

pasos = []
guardados = [0]   # cuántos pasos había cuando la tarea ya había terminado


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


def textos_pasos():
    """Lo que se está viendo ahora mismo dentro del indicador."""
    if app._marco_pasos is None:
        return []
    return [w.cget("text") for w in app._marco_pasos.winfo_children()
            if isinstance(w, app_gui.ctk.CTkLabel)]


def emitir_desde_hilo(*eventos):
    """Manda pasos como lo hace SharePoint: desde su propio hilo de trabajo."""
    def tarea():
        for tipo, texto in eventos:
            getattr(app.system.progreso, tipo)(texto)
            time.sleep(0.05)
    threading.Thread(target=tarea, daemon=True).start()


def paso_1_indicador():
    print("== El indicador dice qué está haciendo ==")
    app._mostrar_pensando(True)
    comprobar(app._procesando and app._ind_pensando is not None,
              "al empezar a procesar aparece el indicador")
    comprobar("trabajando" in app._lbl_pensando.cget("text"),
              "el rótulo ya no es solo 'escribiendo': dice que está trabajando")
    comprobar(textos_pasos() == [], "sin pasos todavía no hay lista que enseñar")
    avanzar()


def paso_2_pasos_en_vivo():
    print("\n== Los pasos llegan del hilo de trabajo ==")
    emitir_desde_hilo(
        ("paso", "Leyendo la carpeta pedida (1ª carpeta · 0 documento(s))"),
        ("hecho", "Revisadas 3 carpeta(s) y 6 documento(s)"),
        ("aviso", "No pude entrar en 2026; sigo con el resto"))
    avanzar(800)


def paso_3_pasos_pintados():
    lineas = textos_pasos()
    comprobar(any(l.startswith(app_gui.MARCAS_PASOS["hecho"]) and "Revisadas 3" in l
                  for l in lineas),
              "el paso terminado se ve con su ✓")
    comprobar(any(l.startswith(app_gui.MARCAS_PASOS["aviso"]) and "No pude entrar" in l
                  for l in lineas),
              "el aviso se ve con su '!'")
    comprobar(any(l.startswith(app_gui.MARCAS_PASOS["paso"]) for l in lineas),
              "y lo que está haciendo ahora con su '→'")
    comprobar(len(app._pasos) == 3, "los tres pasos quedan apuntados")
    avanzar()


def paso_4_muchos_pasos():
    print("\n== Muchos pasos: se ven los últimos y la lista no crece sin fin ==")
    emitir_desde_hilo(*[("paso", f"Archivo {i} de 20") for i in range(1, 21)])
    avanzar(1700)


def paso_5_limite():
    lineas = textos_pasos()
    comprobar(len(lineas) == 6, "el indicador enseña los últimos 6 (no se llena)")
    comprobar(lineas[-1].endswith("Archivo 20 de 20"), "y el último es el más reciente")
    comprobar(len(app._pasos) <= 12, "por dentro no se acumulan sin límite")
    avanzar()


def paso_6_reloj():
    print("\n== El reloj deja claro que sigue trabajando ==")
    app._tarea_inicio = time.monotonic() - 65      # como si llevara un minuto
    app._animar_pensando(0)
    comprobar("(1:05)" in app._lbl_pensando.cget("text"),
              "el rótulo lleva el tiempo transcurrido (1:05)")
    avanzar()


def paso_7_fuera_de_tarea():
    print("\n== Fuera de una tarea no se pinta nada ==")
    app._mostrar_pensando(False)
    comprobar(not app._ind_pensando.winfo_ismapped(),
              "al terminar, el indicador desaparece")
    guardados[0] = len(app._pasos)
    emitir_desde_hilo(("paso", "Esto es de una tarea que ya terminó"))
    avanzar(500)   # el paso llega en el paso siguiente, cuando el hilo ya mandó


def paso_8_fuera_de_tarea_comprobacion():
    comprobar(len(app._pasos) == guardados[0],
              "un paso de una tarea terminada no se cuela en el chat")
    comprobar(not app._ind_pensando.winfo_ismapped(),
              "ni vuelve a abrir el indicador por su cuenta")
    app.system.progreso.paso("y tampoco revienta")
    comprobar(len(app._pasos) == guardados[0], "ni se guarda ni da error")
    avanzar()


def paso_9_mensaje_completo():
    print("\n== Un mensaje de principio a fin ==")
    # La caja arranca con su aviso dentro (el «placeholder» del CTkTextbox): lo que
    # se escribe a mano lo retira, y eso es lo que se envía.
    app._limpiar_input()
    app.entry_chat.insert("1.0", "haz la prueba")
    app._tecla_soltada()
    comprobar(app._texto_input() == "haz la prueba",
              "en la caja queda lo escrito (sin el aviso de ayuda)")
    app._enviar_chat()
    avanzar(1000)


def paso_10_mensaje_resultado():
    comprobar(not app._procesando, "al responder, el indicador se apaga solo")
    comprobar(any("Pensando con la IA qué hacer" in texto
                  for _tipo, texto in app._pasos),
              "el primer paso que se ve es que le está preguntando a la IA")
    comprobar(any(b["autor"] == "Jarvis" and b["texto"] == "Respuesta de prueba"
                  for b in app._burbujas),
              "la respuesta se añade al chat")
    comprobar(app._texto_input() == "" and app.entry_chat.get("1.0", "end-1c") == app_gui.AVISO_INPUT,
              "y la caja queda vacía, con su aviso, lista para el siguiente mensaje")
    guardado = ""
    if os.path.exists(CHAT):
        with open(CHAT, encoding="utf-8") as f:
            guardado = f.read()
    comprobar("Respuesta de prueba" in guardado and "haz la prueba" in guardado,
              "y la conversación queda guardada")
    comprobar(not app._ind_pensando.winfo_ismapped(),
              "sin indicador colgado al terminar")
    avanzar()


pasos.extend([paso_1_indicador, paso_2_pasos_en_vivo, paso_3_pasos_pintados,
              paso_4_muchos_pasos, paso_5_limite, paso_6_reloj,
              paso_7_fuera_de_tarea, paso_8_fuera_de_tarea_comprobacion,
              paso_9_mensaje_completo, paso_10_mensaje_resultado])
app.after(500, avanzar)
app.mainloop()
app.destroy()

for ruta in (CONFIG, CHAT):
    if os.path.exists(ruta):
        os.remove(ruta)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)

