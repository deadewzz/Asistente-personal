"""El tema de Jarvis: paleta, tipografía, medidas y utilidades de color.

Aquí vive lo que hace que la ventana se vea como una sola app: las capas de
color (fondo < panel < tarjeta < tarjeta alta), el acento turquesa, las fuentes
que se eligen según lo que haya instalado y los atajos de teclado que Tk no
trae. Los apartados (`views/`) y la propia ventana (`app_gui.py`) leen de aquí:
un cambio de estilo se hace en un sitio y se ve en todos.

`FUENTE_UI` y `FUENTE_MONO` se resuelven al montar la ventana (hace falta un
root de Tk para preguntar qué fuentes hay), así que se leen como
`tema.FUENTE_UI`, no con `from ui.tema import FUENTE_UI` (que se quedaría con
la de reserva).
"""
import customtkinter as ctk
import tkinter.font as tkfont

from PIL import Image

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ---------------- Paleta: oscuro en capas con acento turquesa ----------------
# El fondo es muy oscuro y las superficies van en capas (panel < tarjeta <
# tarjeta alta), de modo que los paneles parecen flotar unos sobre otros con
# bordes redondeados y sombra sutil. Un único color de acento (turquesa neón)
# marca lo importante: los botones de acción, el nivel del alumno, los iconos
# y los bordes que «brillan» cuando algo está activo.
COLOR_FONDO = "#070a10"
COLOR_SIDEBAR = "#0a0e15"
COLOR_PANEL = "#0f151d"          # superficie de trabajo (la más baja)
COLOR_TARJETA = "#151d28"        # tarjetas y paneles elevados
COLOR_TARJETA_ALTA = "#1b2532"   # tarjeta sobre tarjeta (chips, cabeceras)
COLOR_HOVER = "#222e3d"
COLOR_BORDE = "#22303f"          # borde suave de las tarjetas
COLOR_TEXTO = "#e9f0f8"
COLOR_TEXTO_SUAVE = "#8ea2b9"
COLOR_ACENTO = "#2ee6c5"         # turquesa neón: el color de la casa
COLOR_ACENTO_HOVER = "#26ccb0"
COLOR_ACENTO_2 = "#3aa0ff"       # azul eléctrico: segundo color del degradado
COLOR_ACENTO_TEXTO = "#05231e"   # texto sobre el acento (contraste alto)
COLOR_USUARIO = "#16283a"        # burbuja del usuario
COLOR_OK = "#4ade80"             # pasos ya hechos (✓)
COLOR_AVISO = "#f8b26a"          # avisos y confirmaciones
COLOR_PELIGRO = "#f27272"        # acciones que borran
COLOR_PELIGRO_HOVER = "#d95757"
COLOR_CODIGO = "#0a0f16"         # fondo de los bloques de código
COLOR_CODIGO_TEXTO = "#7ff0da"   # texto monoespaciado

# La caja de escritura del chat crece hacia abajo con el mensaje: empieza en una
# línea (ALTO_INPUT_MIN) y va subiendo de ALTO_INPUT_LINEA en ALTO_INPUT_LINEA
# hasta ALTO_INPUT_LINEAS_MAX; a partir de ahí el texto se desplaza por dentro.
ALTO_INPUT_MIN = 44
ALTO_INPUT_LINEA = 22
ALTO_INPUT_LINEAS_MAX = 7

#: Lo que se ve en la caja de escritura cuando está vacía (un `CTkTextbox` no
#: trae placeholder propio: se escribe este texto en gris y se borra al escribir).
AVISO_INPUT = "Escribe un mensaje a Jarvis\u2026"

#: Pie de la barra lateral cuando el usuario todavía no ha escrito su nombre en
#: Ajustes: Jarvis no usa el nombre de la sesión de Windows (eso enseñaba
#: «coutt»), solo el que el usuario pone en el campo «Tu nombre».
USUARIO_SIN_NOMBRE = "Pon tu nombre"

# Atajos de edición para las cajas de escribir. Tk trae muy pocos puestos (los de
# Emacs: Ctrl+K, Ctrl+D...) y le faltan justo los que se dan por hechos en
# Windows: seleccionar todo, deshacer, borrar la línea entera con Ctrl+Supr o la
# palabra anterior con Ctrl+Retroceso. Cuando la acción empieza por «<<» se le
# pasa el evento virtual al propio Tk (que ya sabe resolverlo: mover de palabra,
# seleccionar todo, deshacer); si no, es el nombre de un método de la ventana.
ATAJOS_CAJA = (
    ("<Control-a>", "seleccionar_todo"),
    ("<Control-z>", "<<Undo>>"),
    ("<Control-y>", "<<Redo>>"),
    ("<Control-Shift-Z>", "<<Redo>>"),
    ("<Control-Left>", "<<PrevWord>>"),
    ("<Control-Right>", "<<NextWord>>"),
    ("<Control-Shift-Left>", "<<SelectPrevWord>>"),
    ("<Control-Shift-Right>", "<<SelectNextWord>>"),
    ("<Control-Delete>", "borrar_linea"),
    ("<Control-Shift-Delete>", "borrar_hasta_final"),
    ("<Control-BackSpace>", "borrar_palabra"),
)

#: Lo mismo para los campos de una línea (`CTkEntry`), donde el «wordstart» de Tk
#: no existe: se calcula mirando el texto (ver `_borrar_palabra_campo`).
ATAJOS_CAMPO = (
    ("<Control-a>", "seleccionar_todo"),
    ("<Control-Delete>", "borrar_hasta_final"),
    ("<Control-BackSpace>", "borrar_palabra"),
)

# Radios: las tarjetas son redondeadas, los chips algo menos, los iconos círculos.
RADIO_TARJETA = 16
RADIO_CHIP = 12

#: Estilo de las barras de desplazamiento de los paneles: en el tono de las
#: tarjetas (para que no canten sobre el fondo) y encendidas con el acento al
#: pasar el ratón por encima.
BARRA_SCROLL = {"scrollbar_button_color": COLOR_TARJETA_ALTA,
                "scrollbar_button_hover_color": COLOR_ACENTO}

# Tipografía: se usa la mejor fuente instalada (Inter/Poppins si están) en lugar
# de la genérica del sistema, con pesos distintos para títulos y contenido. Se
# resuelve al montar la ventana, porque hace falta un root de Tk para preguntar.
FUENTE_UI = "Segoe UI Variable Text"
FUENTE_MONO = "Cascadia Mono"
FUENTES_UI = ("Inter", "Poppins", "Segoe UI Variable Text", "Segoe UI", "Arial")
FUENTES_MONO = ("JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New")


def _fuente_instalada(preferidas, familias):
    """Primera fuente de la lista que esté instalada en el sistema."""
    for fuente in preferidas:
        if fuente in familias:
            return fuente
    return preferidas[-1]


def _resolver_fuentes():
    """Fija FUENTE_UI y FUENTE_MONO con lo que haya instalado (una vez por sesión)."""
    global FUENTE_UI, FUENTE_MONO
    try:
        familias = set(tkfont.families())
    except Exception:
        return          # sin root todavía: se siguen usando las de reserva
    FUENTE_UI = _fuente_instalada(FUENTES_UI, familias)
    FUENTE_MONO = _fuente_instalada(FUENTES_MONO, familias)


def _mezclar(color_a, color_b, cantidad):
    """Mezcla dos colores hex (#rrggbb): cantidad 0 devuelve `a`, 1 devuelve `b`."""
    cantidad = max(0.0, min(1.0, cantidad))
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * cantidad) for x, y in zip(a, b))


def imagen_degradado(ancho, alto, paradas):
    """Crea un degradado horizontal con PIL para el brillo de la barra superior.

    `paradas` son pares (posición 0-1, color): se interpola entre ellas, así que
    el halo del acento se va apagando hasta el fondo del panel.
    """
    paradas = sorted(paradas)
    imagen = Image.new("RGB", (max(1, int(ancho)), max(1, int(alto))))
    pixeles = imagen.load()
    for x in range(imagen.width):
        posicion = x / max(1, imagen.width - 1)
        izquierda, derecha = paradas[0], paradas[-1]
        for i in range(len(paradas) - 1):
            if paradas[i][0] <= posicion <= paradas[i + 1][0]:
                izquierda, derecha = paradas[i], paradas[i + 1]
                break
        trecho = (derecha[0] - izquierda[0]) or 1
        color = _mezclar(izquierda[1], derecha[1], (posicion - izquierda[0]) / trecho)
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        for y in range(imagen.height):
            pixeles[x, y] = rgb
    return imagen
