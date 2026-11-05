"""Prueba del aspecto visual de la ventana (paleta, tarjetas, acento y micrófono).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_estilo.py

- La app se crea con una configuración y una carpeta de conversaciones temporales:
  la prueba no toca tus chats ni tu configuración.
- Se usa el `mainloop` de verdad: los widgets se crean y se pintan como al arrancar.
- No se prueba ni la IA ni las acciones, sino la capa visual: que la paleta vaya en
  capas, que el acento se use para lo importante (y siempre con texto oscuro encima,
  que se lea), que cada apartado de la clase sea una tarjeta con su icono, que los
  ejemplos salgan en monoespaciada y que el micrófono de la barra de entrada exista
  y lata mientras escucha.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import tkinter.font as tkfont

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

BASE = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_estilo")
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
FUENTES = set(tkfont.families())

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


def luminancia(color):
    """Luminancia relativa de un color #rrggbb (0 = negro, 1 = blanco)."""
    canales = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    canales = [(c / 12.92) if c <= 0.03928 else (((c + 0.055) / 1.055) ** 2.4)
               for c in canales]
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def contraste(color_a, color_b):
    """Relación de contraste entre dos colores (lo que pide la accesibilidad)."""
    alto, bajo = sorted((luminancia(color_a), luminancia(color_b)), reverse=True)
    return (alto + 0.05) / (bajo + 0.05)


def saturacion(color):
    """Cuánto de vivo es un color (0 = gris, 1 = color puro)."""
    rojo, verde, azul = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    maximo, minimo = max(rojo, verde, azul), min(rojo, verde, azul)
    return 0 if not maximo else (maximo - minimo) / maximo


def widgets(raiz):
    """Todos los widgets que hay dentro de `raiz` (customtkinter incluido)."""
    dentro = []
    pila = list(raiz.winfo_children())
    while pila:
        widget = pila.pop()
        dentro.append(widget)
        pila.extend(widget.winfo_children())
    return dentro


def textos(widget):
    """Los textos de las etiquetas que haya dentro de un widget."""
    return [w.cget("text") for w in widgets(widget)
            if isinstance(w, app_gui.ctk.CTkLabel)]


def paso_1_paleta():
    print("== La paleta va en capas y con el acento de la casa ==")
    capas = [app_gui.COLOR_FONDO, app_gui.COLOR_PANEL, app_gui.COLOR_TARJETA,
             app_gui.COLOR_TARJETA_ALTA]
    comprobar(all(luminancia(abajo) < luminancia(arriba)
                  for abajo, arriba in zip(capas, capas[1:])),
              "cada superficie es más clara que la de debajo (fondo < panel < tarjeta)")
    comprobar(luminancia(app_gui.COLOR_ACENTO) > 0.45
              and saturacion(app_gui.COLOR_ACENTO) > 0.5,
              "el acento es un color vivo y claro (el turquesa de la casa)")
    comprobar(app_gui.COLOR_ACENTO_2 != app_gui.COLOR_ACENTO
              and luminancia(app_gui.COLOR_ACENTO_2) > 0.3,
              "y hay un segundo color (azul eléctrico) para el degradado superior")
    comprobar(contraste(app_gui.COLOR_ACENTO, app_gui.COLOR_ACENTO_TEXTO) >= 4.5,
              "el texto que va encima del acento se lee de sobra (4.5:1 o más)")
    comprobar(contraste(app_gui.COLOR_TEXTO, app_gui.COLOR_TARJETA) >= 7
              and contraste(app_gui.COLOR_TEXTO_SUAVE, app_gui.COLOR_TARJETA) >= 4.5,
              "y el texto normal y el suave también, sobre las tarjetas")
    # La paleta vive en `ui/tema.py`; el resto de la interfaz (la ventana y cada
    # apartado) no puede llevar colores ni fuentes escritos a mano.
    archivos = [os.path.join(RAIZ, "app_gui.py"),
                os.path.join(RAIZ, "views", "base.py"),
                os.path.join(RAIZ, "views", "chat.py"),
                os.path.join(RAIZ, "views", "ingles.py"),
                os.path.join(RAIZ, "views", "programacion.py"),
                os.path.join(RAIZ, "views", "editor_codigo.py"),
                os.path.join(RAIZ, "views", "ajustes.py")]
    fuente = ""
    for ruta in archivos:
        with open(ruta, encoding="utf-8") as archivo:
            fuente += archivo.read()
    comprobar(not re.search(r'"#[0-9a-fA-F]{6}"', fuente),
              "no quedan colores sueltos por la ventana: todos salen de la paleta")
    comprobar(not re.search(r'font=\("Segoe', fuente),
              "ni fuentes escritas a mano: todas salen de FUENTE_UI y FUENTE_MONO")
    avanzar()


def paso_2_fuentes_y_barra():
    print("\n== Tipografía elegida y barra superior con degradado ==")
    comprobar(app_gui.FUENTE_UI in FUENTES and app_gui.FUENTE_MONO in FUENTES,
              f"se usan fuentes instaladas ({app_gui.FUENTE_UI} / {app_gui.FUENTE_MONO})")
    comprobar("Inter" in app_gui.FUENTE_UI or "Poppins" in app_gui.FUENTE_UI
              or "Variable" in app_gui.FUENTE_UI,
              "una sans-serif moderna (Inter, Poppins o Segoe UI Variable) para el texto")
    comprobar("Mono" in app_gui.FUENTE_MONO or "Consolas" in app_gui.FUENTE_MONO,
              "y una monoespaciada para el código (Cascadia Mono, Consolas...)")
    comprobar(int(app.barra_superior.cget("height")) == 3
              and isinstance(app._brillo_superior, app_gui.ctk.CTkImage),
              "la barra superior es una línea de degradado (turquesa → azul → fondo)")
    barras = [getattr(marco, "_scrollbar", None)
              for marco in (app.chat_scroll, app.lista_conv, app.scroll_ingles)]
    comprobar(all(barra is not None
                  and barra.cget("button_color") == app_gui.COLOR_TARJETA_ALTA
                  and barra.cget("button_hover_color") == app_gui.COLOR_ACENTO
                  for barra in barras),
              "y las barras de desplazamiento van en el tono de las tarjetas")
    avanzar()


def paso_3_burbujas():
    print("\n== El chat, con icono y nombre en cada mensaje ==")
    app._insertar_burbuja("Tú", "hazme un resumen del correo")
    app._insertar_burbuja("Jarvis", "Aquí tienes el resumen.")
    mia = app._burbujas[-2]["burbuja"]
    suya = app._burbujas[-1]["burbuja"]
    comprobar(suya.pack_info()["side"] == "left" and mia.pack_info()["side"] == "right",
              "el asistente escribe a la izquierda y tú a la derecha")
    comprobar("\u2726" in textos(suya.master) and "\U0001F464" in textos(mia.master),
              "cada mensaje lleva su icono (la estrella del asistente y tu avatar)")
    comprobar("Jarvis" in textos(suya) and "Tú" in textos(mia),
              "y quien habla va escrito encima del texto")
    comprobar(int(suya.cget("border_width")) == 1
              and int(suya.cget("corner_radius")) >= 16,
              "las burbujas son tarjetas redondeadas con borde suave")
    comprobar(mia.cget("fg_color") == app_gui.COLOR_USUARIO
              and suya.cget("fg_color") == app_gui.COLOR_TARJETA,
              "y cada una con su fondo (el tuyo, algo más azulado)")
    avanzar()


def paso_4_indicador():
    print("\n== El indicador de trabajo, con su punto que late ==")
    app._mostrar_pensando(True)
    comprobar(app._lbl_pulso is not None and app._ind_pensando is not None,
              "aparece la tarjeta de trabajo, con su punto y su reloj")
    comprobar(app._ind_pensando.cget("border_color") != app_gui.COLOR_BORDE,
              "y su borde lleva un toque de acento (está trabajando)")
    app._lbl_pulso.configure(text="\u25cf")
    app._animar_pensando(0)
    comprobar(app._lbl_pulso.cget("text") == "\u25cb"
              and app._lbl_pulso.cget("text_color") == app_gui.COLOR_ACENTO_2,
              "el punto cambia al ritmo del reloj (late, no está muerto)")
    app._mostrar_pensando(False)
    comprobar(not app._ind_pensando.winfo_ismapped(),
              "al terminar, la tarjeta de trabajo desaparece")
    avanzar()


def paso_5_microfono():
    print("\n== El micrófono de la barra de entrada ==")
    comprobar(app.btn_mic.master is app.marco_mic
              and int(app.marco_mic.cget("corner_radius")) >= 24
              and int(app.marco_mic.cget("border_width")) >= 2,
              "el micrófono es un círculo metido en un anillo (la onda de sonido)")
    comprobar(int(app.btn_mic.cget("corner_radius")) * 2
              == int(app.btn_mic.cget("height")) == int(app.btn_mic.cget("width")),
              "bien redondo: el radio es la mitad del lado")
    comando = getattr(app.btn_mic, "_command", None)
    comprobar(getattr(comando, "__func__", None) is app_gui.AppGUI.toggle_escucha,
              "y es el botón que arranca la escucha por voz (toggle_escucha)")
    comprobar(app.marco_mic.cget("border_color") == app_gui.COLOR_BORDE
              and app.btn_mic.cget("text_color") == app_gui.COLOR_ACENTO,
              "en reposo, el anillo está apagado y el icono lleva el acento")
    app.escuchando = True
    app._actualizar_mic()
    comprobar(app.marco_mic.cget("border_color") == app_gui.COLOR_ACENTO
              and app.btn_mic.cget("fg_color") == app_gui.COLOR_ACENTO
              and app.btn_mic.cget("text_color") == app_gui.COLOR_ACENTO_TEXTO,
              "al escuchar se enciende (icono oscuro sobre el acento, para leerlo)")
    comprobar(app._onda_mic is not None, "y empieza a latir")
    avanzar(500)


def paso_6_microfono_late():
    print("\n== El anillo del micrófono late mientras escucha ==")
    tonos = (app_gui.COLOR_ACENTO, app_gui.COLOR_ACENTO_2,
             app_gui._mezclar(app_gui.COLOR_ACENTO, app_gui.COLOR_PANEL, 0.55))
    comprobar(app._onda_mic is not None
              and app.marco_mic.cget("border_color") in tonos,
              "el anillo va cambiando de tono, como una onda de sonido")
    app.escuchando = False
    app._actualizar_mic()
    comprobar(app.marco_mic.cget("border_color") == app_gui.COLOR_BORDE
              and app._onda_mic is None,
              "al parar, el anillo se apaga y deja de latir")
    avanzar()


def paso_7_glow():
    print("\n== Los bordes que se encienden (glow) ==")
    app._glow_input(True)
    comprobar(app.caja_input.cget("border_color") == app_gui.COLOR_ACENTO,
              "la caja de escritura se enciende con el acento al escribir en ella")
    app._glow_input(False)
    comprobar(app.caja_input.cget("border_color") == app_gui.COLOR_BORDE,
              "y vuelve a su borde suave al salir")
    # El enlace de verdad: el evento de foco se genera en el campo de Tk que hay
    # dentro (customtkinter envuelve el widget que recibe el foco).
    app.entry_chat._textbox.event_generate("<FocusIn>")
    comprobar(app.caja_input.cget("border_color") == app_gui.COLOR_ACENTO,
              "al entrar en la caja, su propio enlace la enciende")
    app.entry_chat._textbox.event_generate("<FocusOut>")
    comprobar(app.caja_input.cget("border_color") == app_gui.COLOR_BORDE,
              "y al salir, se apaga sola")
    comprobar(bool(app.txt_ingles_texto._textbox.bind("<FocusIn>"))
              and bool(app.txt_ingles_texto._textbox.bind("<FocusOut>")),
              "el cuadro de «Tu inglés» del apartado lleva los mismos enlaces")
    app.btn_ingles.invoke()
    comprobar(app.btn_ingles.cget("border_color") == app_gui.COLOR_ACENTO
              and app.btn_ingles.cget("text_color") == app_gui.COLOR_ACENTO,
              "el apartado abierto queda con el borde de acento en la barra lateral")
    app._mostrar_vista("chat")
    comprobar(app.btn_ingles.cget("border_color") == app_gui.COLOR_BORDE,
              "y al volver al chat deja de estar encendido")
    avanzar()


def paso_8_clase_en_tarjetas():
    print("\n== La clase, en tarjetas con icono y código monoespaciado ==")
    app._escribir_clase(
        "## ✅ Versión corregida\n\nI am 30 years old.\n\n"
        "## 🔍 Punto por punto\n\n1. **I have 30 years** → *I am 30 years old*\n"
        "   - la edad se dice con *to be*.\n\n"
        "## 📚 Para entenderlo\n\n```\nI am from Madrid.\n```\n"
        "| Inglés | Español |\n|---|---|\n| hello | hola |\n\n"
        "## ✍️ Practica\n\n1. Completa: I ___ (be) from Madrid.")
    titulos = [tarjeta["titulo"] for tarjeta in app._marcos_clase]
    iconos = [tarjeta["icono"] for tarjeta in app._marcos_clase]
    comprobar(titulos == ["Versión corregida", "Punto por punto", "Para entenderlo",
                          "Practica"],
              "cada apartado de la clase es una tarjeta (una por sección del Markdown)")
    comprobar(iconos == ["✅", "🔍", "📚", "✍️"],
              "con su icono delante, tal y como lo manda la respuesta del tutor")
    comprobar(app._marcos_clase[0]["marco"].cget("border_color") == app_gui.COLOR_ACENTO
              and app._marcos_clase[3]["marco"].cget("border_color") == app_gui.COLOR_BORDE,
              "la de la versión corregida lleva el borde encendido (destaca del resto)")
    visible = app.texto_clase_visible()
    comprobar("**" not in visible and "*I have 30 years*" not in visible
              and "I have 30 years" in visible and "to be" in visible,
              "el texto sale limpio: sin asteriscos, con las cursivas ya puestas")
    areas = [area for _titulo, area in app._tarjetas_clase]
    codigo = [area for area in areas if "I am from Madrid." in area.get("1.0", "end")]
    comprobar(bool(codigo)
              and app_gui.FUENTE_MONO in str(codigo[0].tag_cget("codigo", "font"))
              and codigo[0].tag_cget("codigo", "background") == app_gui.COLOR_CODIGO,
              "los ejemplos y la tabla van en monoespaciada sobre fondo oscuro")
    comprobar(any(area.tag_cget("fuerte", "foreground") == app_gui.COLOR_ACENTO
                  for area in areas)
              and "1. Completa: I ___ (be) from Madrid." in visible,
              "las negritas en acento y los ejercicios numerados, listos para copiar")
    avanzar()


def paso_8b_markdown_en_el_chat():
    print("\n== Los mensajes del asistente, en Markdown de verdad ==")
    app._insertar_burbuja(
        "Jarvis",
        "Esto va en **negrita** y aquí un `codigo`.\n\n- uno\n- dos\n\n"
        "## Un apartado\n\n> una cita\n\n```\nI am from Madrid.\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    burbuja = app._burbujas[-1]["burbuja"]
    areas = [w for w in burbuja.winfo_children() if isinstance(w, app_gui.tk.Text)]
    comprobar(len(areas) == 1, "el mensaje se pinta en un área de texto dentro de su burbuja")
    area = areas[0]
    pintado = area.get("1.0", "end-1c")
    comprobar("**" not in pintado and "`" not in pintado and "*" not in pintado
              and "negrita" in pintado and "codigo" in pintado,
              "sin asteriscos ni acentos graves a la vista: el formato se aplica, no se lee")
    comprobar(area.tag_cget("fuerte", "foreground") == app_gui.COLOR_ACENTO
              and app_gui.FUENTE_MONO in str(area.tag_cget("codigo", "font"))
              and area.tag_cget("codigo", "background") == app_gui.COLOR_CODIGO,
              "negritas en el acento, títulos con su formato y código en monoespaciada")
    comprobar("\u2022 uno" in pintado and "una cita" in pintado,
              "las listas llevan su viñeta y las citas también se pintan")
    comprobar(area.cget("wrap") == "word" and int(area.cget("width")) >= 24
              and area.master is burbuja,
              "el texto se envuelve al ancho de la burbuja (no se estira hacia el lado)")
    comprobar(int(area.cget("height")) > 1,
              "y el área crece hacia abajo con lo que ocupa el mensaje")
    comprobar(app._burbujas[-1]["texto"].startswith("Esto va en **negrita**"),
              "lo que se guarda y se copia sigue siendo el Markdown original")
    avanzar()


def paso_8c_caja_expansible():
    print("\n== La caja de escritura crece hacia abajo ==")
    comprobar(isinstance(app.entry_chat, app_gui.ctk.CTkTextbox)
              and app.entry_chat.cget("wrap") == "word",
              "la caja de escribir es multilínea y envuelve las palabras")
    app._limpiar_input()
    comprobar(app._texto_input() == ""
              and app.entry_chat.get("1.0", "end-1c") == app_gui.AVISO_INPUT,
              "vacía, dentro está su aviso (no un mensaje)")
    alto_inicial = int(app.entry_chat.cget("height"))
    app._foco_input(True)
    comprobar(app.entry_chat.get("1.0", "end-1c") == ""
              and app.caja_input.cget("border_color") == app_gui.COLOR_ACENTO,
              "al entrar en ella el aviso se va y el borde se enciende")
    app.entry_chat.insert("1.0", "una linea\n" * 4)
    app._tecla_soltada()
    alto_crecido = int(app.entry_chat.cget("height"))
    comprobar(alto_crecido > alto_inicial
              and app._texto_input().startswith("una linea"),
              f"con varias líneas la caja crece hacia abajo ({alto_inicial} → {alto_crecido} px)")
    # La IA se sustituye: aquí se prueba la caja, no el cerebro (y así no se llama a la API).
    app.brain.procesar_mensaje = lambda texto: ("Respuesta de prueba", None)
    comprobar(app._enviar_con_enter() == "break",
              "y Enter envía el mensaje (sin dejar un salto de línea suelto)")
    comprobar(app._texto_input() == "" and int(app.entry_chat.cget("height")) == alto_inicial,
              "al enviarlo se vacía y vuelve a su alto de una línea")
    comprobar(app._enviar_con_enter() is None,
              "con la caja vacía, Enter no envía nada")
    app._foco_input(False)
    avanzar()


def paso_9_acento_en_botones():
    print("\n== El acento, para lo importante ==")
    principal = app.botones_ingles[app_gui.TAREA_INGLES_PRINCIPAL]
    otras = [boton for tarea, boton in app.botones_ingles.items()
             if tarea not in (app_gui.TAREA_INGLES_PRINCIPAL, app_gui.TAREA_INGLES_PELIGRO)]
    comprobar(principal.cget("fg_color") == app_gui.COLOR_ACENTO
              and all(boton.cget("fg_color") == app_gui.COLOR_TARJETA_ALTA
                      for boton in otras),
              "la tarea principal va rellena de acento y las demás como tarjetas")
    comprobar(app.botones_ingles[app_gui.TAREA_INGLES_PELIGRO].cget("text_color")
              == app_gui.COLOR_PELIGRO,
              "y la de borrar, en rojo suave (no se pulsa por descuido)")
    comprobar(app.menu_ingles_nivel.cget("button_color") == app_gui.COLOR_ACENTO,
              "el desplegable del nivel lleva el acento en su botón")
    rellenos = [w for w in widgets(app)
                if isinstance(w, app_gui.ctk.CTkButton)
                and w.cget("fg_color") == app_gui.COLOR_ACENTO]
    comprobar(len(rellenos) >= 4
              and all(w.cget("text_color") == app_gui.COLOR_ACENTO_TEXTO for w in rellenos),
              f"los {len(rellenos)} botones rellenos de acento llevan el texto oscuro")
    avanzar()


def paso_10_barra_lateral():
    print("\n== Las conversaciones y el resto de la barra lateral ==")
    ruta = os.path.join(CARPETA_CHATS, "historial_chat_2026-02-03_091011.md")
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write("**[09:10] Tú:** prepara el informe\n\n")
    app._cargar_conversaciones_sidebar()
    tarjetas = [w for w in widgets(app.lista_conv)
                if isinstance(w, app_gui.ctk.CTkFrame)
                and w.cget("fg_color") == app_gui.COLOR_TARJETA
                and "3 feb 2026" in textos(w)]
    comprobar(len(tarjetas) == 1 and int(tarjetas[0].cget("border_width")) == 1
              and int(tarjetas[0].cget("corner_radius")) >= 10,
              "cada conversación es una tarjeta redondeada, no una línea de texto")
    comprobar(bool(tarjetas) and "\U0001F4AC" in textos(tarjetas[0])
              and any("informe" in texto for texto in textos(tarjetas[0])),
              "con su icono, la fecha y el primer mensaje como resumen")
    enlaces = [w.bind("<Enter>") for w in app._widgets_clickeables(tarjetas[0])]
    comprobar(any(enlaces), "y se eleva al pasar el ratón por encima")
    clics = [w.bind("<Button-1>") for w in app._widgets_clickeables(tarjetas[0])]
    comprobar(any(clics), "el clic sigue abriendo la conversación, como siempre")
    comprobar(app.btn_nuevo.cget("fg_color") == app_gui.COLOR_TARJETA
              and int(app.btn_nuevo.cget("border_width")) == 1,
              "«Nuevo chat» es una tarjeta con borde suave (acción secundaria)")
    comprobar(app.avatar.cget("fg_color") == app_gui.COLOR_ACENTO
              and app.avatar.cget("text_color") == app_gui.COLOR_ACENTO_TEXTO,
              "el avatar lleva el acento con texto oscuro (se lee)")
    comprobar(app.lbl_usuario.cget("text") == app_gui.USUARIO_SIN_NOMBRE
              and app.entry_usuario.get() == "",
              "y sin nombre en Ajustes invita a ponerlo (no enseña el usuario de Windows)")
    avanzar()


pasos.extend([paso_1_paleta, paso_2_fuentes_y_barra, paso_3_burbujas, paso_4_indicador,
              paso_5_microfono, paso_6_microfono_late, paso_7_glow,
              paso_8_clase_en_tarjetas, paso_8b_markdown_en_el_chat,
              paso_8c_caja_expansible, paso_9_acento_en_botones, paso_10_barra_lateral])
app.after(500, avanzar)
app.mainloop()
app.destroy()

if os.path.exists(CONFIG):
    os.remove(CONFIG)
shutil.rmtree(CARPETA_CHATS, ignore_errors=True)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
