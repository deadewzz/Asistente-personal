"""Prueba de que el chat va diciendo lo que se está haciendo.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_progreso.py

- La app se crea con una configuración temporal (no toca la tuya).
- Se usa el camino DE VERDAD del aviso: `SystemActions._aviso` ->
  `AppGUI._aviso_progreso` -> etiqueta del indicador del chat. Lo único
  simulado es que el aviso se dispara desde un hilo de fondo, como lo hace el
  trabajo real (listar una biblioteca por clientes tarda minutos).
- Se usa el `mainloop` de verdad, porque la etiqueta se actualiza con `after()`
  desde el hilo que trabaja.
"""
import json
import os
import sys
import tempfile
import threading

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_progreso.json")
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

UNO = "Buscando archivos dentro de 180 carpeta(s) (nivel 1 de 2)..."
DOS = "Moviendo 12 de 350: AXA/acta.pdf → Actas"


def texto_indicador():
    """Lo que enseña el indicador del chat ('Jarvis está escribiendo...')."""
    return str(app._lbl_pensando.cget("text"))


def en_hilo(funcion, *args):
    """Dispara lo que pasa en el trabajo real: avisos desde un hilo de fondo."""
    threading.Thread(target=funcion, args=args, daemon=True).start()


def ejecutar(paso):
    """Corre un paso y sigue con el siguiente aunque falle (sin colgar la ventana)."""
    try:
        paso()
    except Exception as e:
        comprobar(False, f"el paso {paso.__name__} no debe fallar ({e!r})")
        avanzar(100)


def avanzar(retardo=400):
    """Ejecuta el siguiente paso (o cierra la ventana si ya no hay más)."""
    if pasos:
        app.after(retardo, lambda: ejecutar(pasos.pop(0)))
    else:
        app.after(retardo, app.quit)


def paso_1_enlace():
    print("== La ventana escucha lo que hacen la IA y las acciones ==")
    app._insertar_burbuja("Tú", "clasifica los archivos de SharePoint de Colombia")
    comprobar(app.chat_activo is True, "con un mensaje, la conversación está activa")
    comprobar(app.system.on_aviso == app._aviso_progreso,
              "las acciones avisan a la ventana (system.on_aviso)")
    comprobar(app.brain.on_aviso == app._aviso_progreso,
              "y la clasificación con la IA también (brain.on_aviso)")
    comprobar(app._aviso_chat == "", "al empezar no hay ningún paso apuntado")
    avanzar()


def paso_2_pensando():
    print("\n== Mientras trabaja, el chat lo dice (en vez de quedarse mudo) ==")
    app._mostrar_pensando(True)
    app.update_idletasks()
    comprobar(bool(app._ind_pensando.winfo_ismapped()),
              "el indicador de 'escribiendo' está a la vista")
    comprobar(texto_indicador().startswith("Jarvis está escribiendo"),
              "de momento dice que Jarvis está escribiendo")
    # El aviso llega del hilo que trabaja (como en la clasificación de verdad).
    en_hilo(app.system._aviso, UNO)
    avanzar(700)


def paso_3_el_paso_en_curso():
    comprobar(UNO in texto_indicador(),
              "el aviso real de la acción llega a la etiqueta del chat")
    comprobar(app._aviso_chat == UNO, "y queda apuntado como paso en curso")
    en_hilo(app.system._aviso, DOS)
    avanzar(900)


def paso_4_animacion():
    # La animación de los puntos sigue corriendo cada 400 ms: el paso tiene que
    # seguir viéndose (con sus puntos) y no volver al texto genérico.
    comprobar(DOS in texto_indicador(),
              "el paso en curso se mantiene aunque pase la animación de puntos")
    comprobar(not texto_indicador().startswith("Jarvis está escribiendo"),
              "y no se vuelve al 'está escribiendo' genérico")
    comprobar(app._procesando is True, "mientras trabaja, la ventana lo sabe")
    avanzar()


def paso_5_sin_mover_la_vista():
    print("\n== Si el usuario está leyendo arriba, no se le mueve la vista ==")
    # Se apaga el aviso de posición del lienzo para que el resultado no dependa
    # de la geometría de la ventana (es lo que aquí no se está probando).
    app._scroll_actualizado_real = app._scroll_actualizado
    app._scroll_final_real = app._scroll_final
    app._scroll_actualizado = lambda first, last: None
    llamadas = []
    app._scroll_final = lambda: llamadas.append(1)
    app._scroll_final_llamadas = llamadas
    app._pegado_abajo = False       # está mirando hacia arriba en la conversación
    en_hilo(app.system._aviso, UNO)
    avanzar(700)


def paso_6_al_terminar():
    print("\n== Al terminar, el aviso desaparece (no deja burbujas colgadas) ==")
    comprobar(UNO in texto_indicador(), "el cambio de paso llega igual")
    comprobar(app._scroll_final_llamadas == [],
              "no baja la conversación al final si el usuario está leyendo arriba")
    app._scroll_final = app._scroll_final_real
    app._scroll_actualizado = app._scroll_actualizado_real
    app._mostrar_pensando(False)
    app.update_idletasks()
    comprobar(not bool(app._ind_pensando.winfo_ismapped()),
              "al terminar, el indicador se esconde")
    comprobar(app._aviso_chat == "", "y se olvida el paso que estaba en curso")
    # Un aviso que llegue tarde (el trabajo ya acabó) no debe reabrir la burbuja.
    en_hilo(app.system._aviso, DOS)
    avanzar(700)


def paso_7_aviso_tardio():
    comprobar(not bool(app._ind_pensando.winfo_ismapped()),
              "un aviso tardío no reabre el indicador")
    comprobar(app._aviso_chat == DOS and bool(app.winfo_exists()),
              "el texto queda apuntado y la ventana sigue viva")
    avanzar()


pasos.extend([paso_1_enlace, paso_2_pensando, paso_3_el_paso_en_curso,
              paso_4_animacion, paso_5_sin_mover_la_vista, paso_6_al_terminar,
              paso_7_aviso_tardio])
app.after(500, avanzar)
app.mainloop()
app.destroy()

print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print(f"  - {fallo}")
raise SystemExit(1 if fallos else 0)
