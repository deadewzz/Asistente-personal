"""Prueba del apartado «Aprender programación» de la ventana (taller de Java).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_programacion.py

- La app se crea con una configuración, un avance de programación y una carpeta de
  documentos temporales: la prueba no toca tus chats, tu avance ni tus documentos.
- Se usa el `mainloop` de verdad y se pulsan los botones del taller igual que lo
  haría el usuario.
- La IA se sustituye por una función de mentira: aquí se prueba la ventana (que la
  revisión en vivo enseñe la línea y la columna sin gastar IA, que «Corregir»
  compile, que «Probar» ejecute y que lo que necesita IA se pida con el mensaje del
  profesor de programación), no la IA.
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

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_programacion")
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
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui
from modules.api_brain import APIBrain
from modules.programming_tutor import MARCA_PROFE, ProgrammingTutor

app_gui.rutas.DOCUMENTOS = CARPETA_DOCS     # «Guardar» no escribe en tus documentos
app = app_gui.AppGUI(config_path=CONFIG)
app.conversacion_actual = CHAT              # el historial de prueba no toca tus chats
# El taller de verdad, pero con su nivel y su avance en una carpeta temporal
app.system.programacion = ProgrammingTutor(config_path=CONFIG, carpeta=CARPETA_PROG)
app._actualizar_programacion()

pasos = []
encargos = []          # (encargo, mensaje de sistema) de cada explicación pedida a la IA
clase = ("## \U0001F4DD Cuatro ejercicios de bucles\n\n"
         "1. Suma los números del 1 al 10 con un `for`.\n\n"
         "## \u2705 Soluciones\n\n```java\nint suma = 0;\n```\n")
#: Programa que no compila: el analizador propio lo ve sin llamar a `javac`.
ROTO = ('public class Roto {\n  public static void main(String[] args) {\n'
        '    string nombre = "Ana"\n    System.out.println(nombre);\n  }\n}')
#: Programa completo con `Scanner`, para el paso de «Probar».
SUMA = ('import java.util.Scanner;\n\npublic class Suma {\n'
        '    public static void main(String[] args) {\n'
        '        Scanner lector = new Scanner(System.in);\n'
        '        int a = lector.nextInt();\n'
        '        int b = lector.nextInt();\n'
        '        System.out.println("Suma: " + (a + b));\n'
        '    }\n}\n')
#: Programa sin lecturas, para ejecutarlo desde la ventana del editor.
HOLA = ('public class HolaEditor {\n'
        '    public static void main(String[] args) {\n'
        '        System.out.println("Hola desde el editor");\n'
        '    }\n}\n')


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


def esperar(condicion, luego, intentos=40, retardo=150):
    """Espera a que se cumpla algo (sin bloquear) y sigue; si no, sigue igual.

    Compilar y ejecutar tarda lo que tarde el `javac` del equipo: en vez de dormir
    un rato fijo —y que la prueba falle en un ordenador lento—, se pregunta hasta
    que el programa ha terminado (o se agotan los intentos, unos seis segundos).
    """
    if condicion() or intentos <= 0:
        luego()
        return
    app.after(retardo, lambda: esperar(condicion, luego, intentos - 1, retardo))


def panel():
    """Lo que se está viendo ahora mismo en las tarjetas del taller."""
    return app.texto_programacion_visible()


def avisos():
    """Lo que dice el panel de la revisión (línea, columna y pista de cada fallo)."""
    return app.txt_prog_avisos.get("1.0", "end-1c")


def poner_codigo(codigo):
    """Deja el programa escrito en el taller (como si se hubiera escrito a mano).

    El código se escribe en la ventana del editor, que guarda el programa en el
    taller: aquí se usa su misma puerta, sin abrir ventanas.
    """
    app.fijar_codigo_programacion(codigo)


def paso_1_entrar():
    print("== El botón «Programar» lleva a su apartado ==")
    comprobar(app.vista_chat.winfo_manager() == "pack"
              and app.vista_programacion.winfo_manager() == "",
              "la ventana arranca en el chat, con el taller sin montar")
    comprobar(app.btn_programar.master is app.sidebar
              and "Programar" in app.btn_programar.cget("text"),
              "el botón del taller está en la barra lateral")
    app.btn_programar.invoke()              # como si se pulsara con el ratón
    comprobar(app.vista_programacion.winfo_manager() == "pack"
              and app.vista_chat.winfo_manager() == "",
              "al pulsarlo se abre el taller (y el chat se aparta)")
    comprobar(app.btn_programar.cget("fg_color") == app_gui.COLOR_TARJETA,
              "y queda marcado en la barra lateral mientras está abierto")
    resumen = app.lbl_prog_resumen.cget("text")
    comprobar("Nivel Principiante" in resumen and "0 prácticas" in resumen
              and "sin fallos apuntados" in resumen,
              "la cabecera cuenta cómo va el alumno: nivel, prácticas y fallos")
    comprobar("JDK instalado" in app.lbl_prog_jdk.cget("text")
              or "sin JDK" in app.lbl_prog_jdk.cget("text"),
              "y dice si hay compilador de verdad o solo revisión básica")
    comprobar(app.menu_prog_nivel.get() == "Principiante",
              "el nivel del alumno está puesto en el desplegable")
    comprobar("Hola" in app.txt_prog_codigo.get("1.0", "end-1c")
              and "Scanner" in app.txt_prog_codigo.get("1.0", "end-1c"),
              "el editor arranca con el programa de ejemplo (compila tal cual)")
    comprobar("Cómo se usa" in [titulo for titulo, _area in app._tarjetas_prog],
              "y el panel arranca con la ayuda de uso, en tarjetas con su título")
    comprobar("Nada que corregir" in avisos(),
              "al entrar ya se revisa el ejemplo, sin gastar IA")
    avanzar()


def paso_2_revision_al_escribir():
    print("\n== La revisión en vivo: línea y columna, sin IA ==")
    comprobar(app.vista_programacion.winfo_ismapped(),
              "el taller ya está a la vista (no solo montado)")
    app.brain.analizar_documento = lambda texto, sistema=None: (
        comprobar(False, "la revisión no debe llamar a la IA") or "")
    poner_codigo(ROTO)
    app._revision_diferida()                # lo que dispara cada tecla
    comprobar(app._revision_prog is not None,
              "al teclear se programa una revisión (no se revisa en cada tecla)")
    app.after_cancel(app._revision_prog)
    app._revision_al_escribir()             # y al parar, se revisa de una vez
    texto = avisos()
    comprobar("línea 3" in texto,
              "el aviso dice en qué línea está el fallo (`string` en la 3)")
    comprobar("columna" in texto,
              "y en qué columna, para poder ir derecho a él")
    comprobar("punto y coma" in texto.lower() or "`;`" in texto,
              "con la pista de qué falta (`;`), no solo un «error» a secas")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "nada de esto se cuela en el chat ni en tu historial")
    # La revisión rápida es la misma que se lanza sola, pero a mano.
    datos = app._revisar_programacion(compilar=False)
    comprobar(datos["errores"] and not datos["compilado"],
              "la revisión rápida devuelve los fallos sin compilar")
    comprobar(app.lbl_prog_estado.cget("text").startswith(f"{len(datos['errores'])} aviso"),
              f"y la línea de estado cuenta los {len(datos['errores'])} avisos")
    poner_codigo(SUMA)                      # un programa que sí está bien
    limpio = app._revisar_programacion(compilar=False)
    comprobar(not limpio["errores"]
              and "Revisión rápida" in app.lbl_prog_estado.cget("text"),
              "con un programa limpio lo dice: revisión rápida, y «Corregir» para compilar")
    poner_codigo(ROTO)                      # se vuelve al roto para el paso siguiente
    comprobar(app._revisar_programacion(compilar=False)["errores"]
              and "línea 3" in avisos() and not app._burbujas,
              "y al volver al programa roto los avisos siguen donde estaban")
    avanzar()


def paso_3_corregir():
    print("\n== «Corregir»: el compilador de verdad y el avance apuntado ==")
    app.botones_prog["corregir"].invoke()       # el botón principal, como el usuario
    datos = app.system.programacion.resumen()
    comprobar(datos["practicas"] == 1,
              "la corrección apunta una práctica en el avance del alumno")
    comprobar(bool(datos["repetidos"]),
              "y guarda los fallos para saber qué se le repite")
    comprobar("1 prácticas" in app.lbl_prog_resumen.cget("text"),
              "la cabecera del taller se refresca sola con la práctica nueva")
    comprobar("lo que más se te repite" in app.lbl_prog_resumen.cget("text"),
              "y nombra el fallo que más se le repite")
    comprobar("fallo(s)" in avisos() or "aviso(s)" in avisos(),
              "el panel de la revisión cuenta los fallos (y los avisos aparte)")
    comprobar(bool(panel()) and "Cómo se usa" not in panel(),
              "la corrección sustituye la ayuda de uso en las tarjetas")
    comprobar(bool(app._clase_prog) and "línea" in app._clase_prog,
              "y dice, en el texto, en qué línea está cada fallo")
    comprobar(app.btn_prog_copiar.cget("state") == "normal"
              and app.btn_prog_guardar.cget("state") == "normal",
              "el resultado se puede copiar o guardar")
    if app.system.programacion.hay_jdk():
        comprobar("compilador" in app.lbl_prog_estado.cget("text").lower()
                  or "aviso" in app.lbl_prog_estado.cget("text"),
                  "y el estado cuenta lo que ha pasado al compilar")
    # Ahora un programa correcto: nada que corregir y con el visto bueno.
    poner_codigo(SUMA)
    app.botones_prog["corregir"].invoke()
    comprobar("Nada que corregir" in avisos(),
              "un programa que compila se queda sin avisos")
    if app.system.programacion.hay_jdk():
        comprobar("compilador" in app.lbl_prog_estado.cget("text"),
                  "y el estado dice que lo ha revisado el compilador")
    avanzar()


def paso_4_probar():
    print("\n== «Probar»: compilar y ejecutar el programa ==")
    app.txt_prog_entrada.delete("1.0", "end")
    app.txt_prog_entrada.insert("1.0", "2\n3\n")
    app.botones_prog["probar"].invoke()
    comprobar(app.lbl_prog_estado.cget("text").startswith("Compilando y ejecutando"),
              "mientras compila, el taller lo dice (y la ventana sigue viva)")
    # Se espera a que el programa acabe de verdad (mejor que dormir un rato fijo).
    esperar(lambda: not app.lbl_prog_estado.cget("text").startswith("Compilando"),
            paso_4b_resultado)


def paso_4b_resultado():
    print("\n== Lo que ha impreso el programa ==")
    visible = panel()
    if app.system.programacion.hay_jdk():
        comprobar("Salida del programa" in visible,
                  "el panel enseña la salida en su apartado")
        comprobar("Suma: 5" in visible,
                  "con lo que imprimió de verdad (le ha leído el 2 y el 3)")
        comprobar("El programa funcionó" in app.lbl_prog_estado.cget("text"),
                  "y el estado confirma que funcionó")
    else:
        comprobar("JDK" in visible or "JDK" in app.lbl_prog_estado.cget("text"),
                  "sin JDK lo explica en vez de fallar")
    avanzar()


def paso_4c_ventana_del_editor():
    print("\n== La ventana del editor: se escribe ahí y se ejecuta ahí ==")
    comprobar(app.btn_prog_abrir_editor.cget("text").endswith("Abrir el editor"),
              "el taller tiene su botón para abrir el editor aparte")
    editor = app.abrir_editor()
    comprobar(bool(editor.winfo_exists()) and editor is app._editor,
              "«Abrir el editor» abre una ventana aparte (y se recuerda)")
    comprobar(editor.txt_codigo.get("1.0", "end-1c") == app.codigo_programacion(),
              "que arranca con el programa que hay en el taller")
    editor.txt_codigo.delete("1.0", "end")
    editor.txt_codigo.insert("1.0", HOLA)
    editor._al_escribir()                   # lo que dispara cada tecla
    comprobar(app.codigo_programacion() == HOLA,
              "lo que se escribe en el editor queda en el taller")
    comprobar("HolaEditor" in app.txt_prog_codigo.get("1.0", "end-1c"),
              "y se ve en la vista previa (que aquí solo se lee)")
    editor._ejecutar()                      # el mismo botón ▶ Ejecutar
    comprobar(editor.lbl_consola.cget("text").startswith("Ejecutando"),
              "al ejecutar lo dice en la ventana (y la ventana sigue viva)")
    esperar(lambda: not editor.lbl_consola.cget("text").startswith("Ejecutando"),
            paso_4d_salida_en_la_consola)


def paso_4d_salida_en_la_consola():
    print("\n== ▶ Ejecutar: lo que imprime el programa sale en la consola ==")
    editor = app._editor
    consola = editor.consola.get("1.0", "end-1c") if editor else ""
    if app.system.programacion.hay_jdk():
        comprobar("javac HolaEditor.java" in consola,
                  "la consola enseña la orden que se ha lanzado")
        comprobar("Hola desde el editor" in consola,
                  "y lo que imprime el programa (su System.out.println)")
        comprobar("código 0" in consola,
                  "con el visto bueno de que terminó bien")
        comprobar("Hola desde el editor" in panel(),
                  "y el taller también cuenta la salida en sus tarjetas")
    else:
        comprobar("JDK" in consola, "sin JDK lo explica en la consola")
    editor._cerrar()
    comprobar(app._editor is None and app.codigo_programacion() == HOLA,
              "al cerrar la ventana el programa se queda en el taller")
    avanzar()


def paso_5_tablas_sin_ia():
    print("\n== Temario, lección, documentación, comparaciones y avance: sin IA ==")
    app.brain.analizar_documento = lambda texto, sistema=None: (
        comprobar(False, "esto no debe llamar a la IA") or "")
    app.botones_prog["bases"].invoke()
    comprobar("Las bases de Java" in panel(),
              "«Bases» trae el temario entero del curso")
    comprobar("IA" in app.lbl_prog_estado.cget("text"),
              "y el estado avisa de que no ha hecho falta la IA")
    app.entry_prog_tema.delete(0, "end")
    app.entry_prog_tema.insert(0, "bucles")
    app.botones_prog["leccion"].invoke()
    comprobar("Bucles" in panel() and "###" not in panel(),
              "«Lección» trae el tema pedido, en tarjetas por apartado")
    app.entry_prog_tema.delete(0, "end")
    app.entry_prog_tema.insert(0, "String")
    app.botones_prog["documentacion"].invoke()
    comprobar("String" in panel() and "inmutable" in panel(),
              "«Documentación» cuenta qué hace la clase y sus trampas")
    app.entry_prog_tema.delete(0, "end")
    app.entry_prog_tema.insert(0, "equals")
    app.botones_prog["comparar"].invoke()
    comprobar("equals" in panel() and "==" in panel(),
              "«¿Por qué…?» compara las dos opciones y se queda con una regla")
    app.botones_prog["progreso"].invoke()
    comprobar("Tu avance" in panel() and "Prácticas corregidas" in panel(),
              "«Mi avance» cuenta el nivel, las prácticas y los fallos")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "y nada de esto se ha colado en el chat")
    avanzar()


def paso_6_ejercicios_con_ia():
    print("\n== «Ejercicios»: el encargo se le pide a la IA con el profesor de Java ==")
    del encargos[:]
    app.brain.analizar_documento = lambda texto, sistema=None: (
        encargos.append((texto, sistema)) or clase)
    app.entry_prog_tema.delete(0, "end")
    app.entry_prog_tema.insert(0, "bucles")
    app.menu_prog_cantidad.set("4")
    app.botones_prog["ejercicios"].invoke()
    comprobar(app.lbl_prog_estado.cget("text").startswith("Escribiendo con la IA"),
              "mientras la IA escribe, el taller lo dice")
    avanzar(600)


def paso_6b_ejercicios_en_el_panel():
    print("\n== Los ejercicios llegan al panel, en tarjetas ==")
    comprobar(bool(encargos) and encargos[0][1] == APIBrain.SISTEMA_PROGRAMADOR,
              "se le piden a la IA con el mensaje del profesor (SISTEMA_PROGRAMADOR)")
    comprobar(bool(encargos) and not encargos[0][0].startswith(MARCA_PROFE)
              and "4 ejercicios" in encargos[0][0] and "bucles" in encargos[0][0],
              "con el encargo del tutor: cuántos ejercicios y de qué tema")
    comprobar(bool(encargos) and "Nivel del alumno" in encargos[0][0],
              "y con el nivel del alumno delante, para ajustar la dificultad")
    comprobar("Suma los números del 1 al 10" in panel(),
              "el panel enseña la respuesta entera")
    comprobar([titulo for titulo, _area in app._tarjetas_prog]
              == ["Cuatro ejercicios de bucles", "Soluciones"],
              "cada apartado es una tarjeta con su título (sin el ##)")
    comprobar([tarjeta["icono"] for tarjeta in app._marcos_prog]
              == ["\U0001F4DD", "\u2705"],
              "y con el icono que manda la IA en cada título")
    comprobar(app.lbl_prog_estado.cget("text").startswith("Listo"),
              "la línea de estado avisa de que ya está")
    avanzar()


def paso_7_preguntar_sin_duda():
    print("\n== «Preguntar» lleva al chat del taller (sin duda, sin gastar IA) ==")
    del encargos[:]
    app.entry_prog_tema.delete(0, "end")
    app.botones_prog["preguntar"].invoke()
    comprobar(not encargos,
              "sin duda escrita no se le pide nada a la IA")
    comprobar(app._panel_prog == "chat" and app.marco_chat_prog.winfo_manager() == "grid"
              and app.marco_panel_prog.winfo_manager() == "",
              "el taller se pasa a su chat (la clase se aparta, no se pierde)")
    comprobar(app.botones_prog_panel["chat"].cget("fg_color") == app_gui.COLOR_ACENTO
              and app.botones_prog_panel["clase"].cget("fg_color") == app_gui.COLOR_TARJETA,
              "y la pestaña del chat queda marcada en el centro (la clase, como tarjeta)")
    comprobar("Escríbeme la duda" in app.texto_chat_programacion(),
              "el chat pide que le escribas la duda, en su propia tarjeta")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "y nada de esto se cuela en el chat de Jarvis ni en tu historial")
    avanzar()


def paso_7b_chat_del_taller():
    print("\n== El chat del taller: se pregunta ahí y contesta el profe de Java ==")
    del encargos[:]
    respuesta = ("## \U0001F4AC Por qué falla\n\n"
                 "`String` es **inmutable**: por eso `string` (en minúscula) no existe.\n")
    app.brain.analizar_documento = lambda texto, sistema=None: (
        encargos.append((texto, sistema)) or respuesta)
    # Mayús+Enter hace un salto de línea dentro del mensaje (no lo manda).
    app.txt_chat_prog.delete("1.0", "end")
    app.txt_chat_prog.insert("1.0", "primera línea")
    comprobar(app._salto_chat_prog() == "break"
              and "primera línea\n" in app.txt_chat_prog.get("1.0", "end-1c"),
              "Mayús+Enter mete un salto de línea sin mandar el mensaje")
    # Y Enter lo manda (aquí se usa la misma puerta que el teclado).
    app.txt_chat_prog.delete("1.0", "end")
    app.txt_chat_prog.insert("1.0", "¿por qué falla mi línea 3?")
    comprobar(app._enviar_chat_prog_con_enter() == "break",
              "Enter manda el mensaje del chat del taller")
    comprobar(app.txt_chat_prog.get("1.0", "end-1c").strip() == "",
              "y la caja se queda limpia para la siguiente pregunta")
    comprobar(app.lbl_prog_estado.cget("text").startswith("Pensando"),
              "mientras la IA escribe, el taller lo dice (y la ventana sigue viva)")
    esperar(lambda: len(app.conversacion_programacion()) >= 2, avanzar)


def paso_7c_chat_contestado():
    print("\n== Quién habla en el chat del taller (y qué se le manda a la IA) ==")
    comprobar(len(encargos) == 1 and encargos[0][1] == APIBrain.SISTEMA_PROGRAMADOR,
              "la duda se le pide a la IA con el mensaje del profesor de programación")
    comprobar(bool(encargos) and "¿por qué falla mi línea 3?" in encargos[0][0],
              "con la duda dentro del encargo")
    comprobar(bool(encargos) and "Su código" in encargos[0][0]
              and "HolaEditor" in encargos[0][0],
              "y con el programa que hay ahora en el taller, delante")
    conversacion = app.conversacion_programacion()
    comprobar([autor for autor, _texto in conversacion] == ["Tú", "Profe"],
              "el chat guarda tu pregunta y la respuesta del profe, en orden")
    comprobar("inmutable" in app.texto_chat_programacion(),
              "la respuesta se lee en el chat (con su Markdown puesto)")
    comprobar(not app._burbujas and not os.path.exists(CHAT),
              "y el chat de Jarvis sigue sin enterarse de nada")
    avanzar()


def paso_7d_chat_con_memoria():
    print("\n== La segunda pregunta se contesta con lo ya hablado ==")
    del encargos[:]
    app.txt_chat_prog.insert("1.0", "¿y entonces cómo lo comparo?")
    app.btn_chat_prog_enviar.invoke()       # el botón de enviar, como el usuario
    esperar(lambda: len(app.conversacion_programacion()) >= 4, avanzar)


def paso_7e_chat_nuevo():
    print("\n== El hilo viaja en el encargo, y «Nuevo» empieza otro chat ==")
    comprobar(bool(encargos) and "Lo que ya se han dicho" in encargos[0][0],
              "la segunda pregunta le llega a la IA con lo que ya se habló")
    comprobar(bool(encargos) and "¿por qué falla mi línea 3?" in encargos[0][0],
              "con la pregunta anterior dentro del hilo")
    comprobar("Lo que ya se han dicho" not in (encargos[0][0] if encargos else "")
              or "Duda del alumno: ¿y entonces" in encargos[0][0],
              "y la duda nueva va aparte, sin repetirse como si fuera del hilo")
    guardados = ([nombre for nombre in os.listdir(CARPETA_PROG)
                  if nombre.startswith("chat_taller_")]
                 if os.path.isdir(CARPETA_PROG) else [])
    comprobar(bool(guardados) and guardados[0].endswith(".md"),
              "la conversación queda guardada en la carpeta del taller (no en tus chats)")
    if guardados:
        with open(os.path.join(CARPETA_PROG, guardados[0]), encoding="utf-8") as archivo:
            hilo = archivo.read()
        comprobar("¿por qué falla mi línea 3?" in hilo and "inmutable" in hilo,
                  "con las dos voces apuntadas (tú y el profe)")
    comprobar(app.btn_chat_prog_nuevo.cget("text").endswith("Nuevo"),
              "el chat tiene su botón de empezar otra conversación")
    app.btn_chat_prog_nuevo.invoke()
    comprobar(app.conversacion_programacion() == [] and app._hilo_prog == [],
              "«Nuevo» limpia el chat (la conversación anterior se queda en su archivo)")
    comprobar("Escríbeme la duda" in app.texto_chat_programacion(),
              "y vuelve a estar la ayuda del principio")
    avanzar()


def paso_8_nivel():
    print("\n== El nivel del alumno, desde el desplegable ==")
    app._cambiar_nivel_programacion("Avanzado")
    comprobar(app.system.programacion.nivel() == "Avanzado",
              "cambiar el desplegable cambia el nivel del taller")
    comprobar("Nivel Avanzado" in app.lbl_prog_resumen.cget("text"),
              "y la cabecera lo enseña al momento")
    app._cambiar_nivel_programacion("Intermedio")
    comprobar(app.system.programacion.nivel() == "Intermedio",
              "y se puede volver a otro nivel sin reiniciar")
    avanzar()


def paso_9_guardar_y_copiar():
    print("\n== Guardar lo que se ve y copiarlo ==")
    app.mostrar_panel_programacion("clase")   # Guardar y Copiar son de la clase
    app.btn_prog_guardar.invoke()
    guardados = ([nombre for nombre in os.listdir(CARPETA_DOCS)
                  if nombre.startswith("Programación")]
                 if os.path.isdir(CARPETA_DOCS) else [])
    comprobar(bool(guardados) and guardados[0].endswith(".md"),
              "«Guardar» deja lo que se ve como .md en documentos")
    if guardados:
        with open(os.path.join(CARPETA_DOCS, guardados[0]), encoding="utf-8") as archivo:
            comprobar(archivo.read() == app._clase_prog,
                      "con el texto entero (lo mismo que se ve en el panel)")
    comprobar("Guardado en" in app.lbl_prog_estado.cget("text"),
              "y el estado dice dónde ha quedado")
    app.btn_prog_copiar.invoke()
    comprobar(app.clipboard_get() == app._clase_prog,
              "«Copiar» deja el texto en el portapapeles")
    comprobar("Copiado" in app.lbl_prog_estado.cget("text"),
              "y lo avisa en la línea de estado")
    avanzar()


def paso_10_borrar():
    print("\n== «Borrar» el avance pide confirmación ==")
    app.botones_prog["borrar"].invoke()
    comprobar("Pulsa otra vez" in app.lbl_prog_estado.cget("text"),
              "la primera vez solo avisa (no borra nada a la ligera)")
    comprobar(app.system.programacion.resumen()["practicas"] >= 1,
              "y el avance sigue donde estaba")
    app.botones_prog["borrar"].invoke()
    datos = app.system.programacion.resumen()
    comprobar(datos["practicas"] == 0 and not datos["repetidos"],
              "la segunda vez sí borra las prácticas y los fallos")
    comprobar(datos["nivel"] == "Intermedio",
              "pero respeta el nivel que había elegido")
    comprobar("0 prácticas" in app.lbl_prog_resumen.cget("text"),
              "y la cabecera vuelve a cero")
    comprobar("He borrado el avance" in panel(),
              "el panel lo cuenta")
    avanzar()


def paso_11_volver_al_chat():
    print("\n== «Volver al chat» deja el taller como estaba ==")
    app._mostrar_vista("chat")
    comprobar(app.vista_chat.winfo_manager() == "pack"
              and app.vista_programacion.winfo_manager() == "",
              "el chat vuelve a ocupar su sitio")
    comprobar(app.btn_programar.cget("fg_color") == "transparent",
              "y el botón del taller deja de estar marcado")
    comprobar(not app._burbujas,
              "el taller no ha escrito nada en la conversación")
    avanzar()


pasos.extend([paso_1_entrar, paso_2_revision_al_escribir, paso_3_corregir,
              paso_4_probar, paso_4c_ventana_del_editor,
              paso_5_tablas_sin_ia, paso_6_ejercicios_con_ia,
              paso_6b_ejercicios_en_el_panel,
              paso_7_preguntar_sin_duda, paso_7b_chat_del_taller,
              paso_7c_chat_contestado, paso_7d_chat_con_memoria,
              paso_7e_chat_nuevo, paso_8_nivel, paso_9_guardar_y_copiar,
              paso_10_borrar, paso_11_volver_al_chat])
app.after(500, avanzar)
app.mainloop()
app.destroy()

for ruta in (CONFIG, CHAT):
    if os.path.exists(ruta):
        os.remove(ruta)
for carpeta in (CARPETA_PROG, CARPETA_DOCS):
    shutil.rmtree(carpeta, ignore_errors=True)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
