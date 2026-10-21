import customtkinter as ctk
import glob
import json
import os
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from tkinter import filedialog

from PIL import Image

from modules.api_brain import APIBrain
from modules.english_tutor import MARCA_TUTOR, NIVELES
from modules.system_actions import SystemActions
from modules.voice_engine import VoiceEngine
from modules.voice_output import VoiceOutput
from modules.ocr_engine import ocr_imagen, motor as ocr_motor
from modules.cloud_matrix import CloudMatrix, COLUMNAS_DEFECTO
from modules import rutas
from modules import notificaciones

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

# ---------------- Apartado de inglés (tutor) ----------------
# El tutor de inglés tiene su propio apartado en la ventana (no pasa por el chat):
# aquí, los botones que ofrece cada tarea del tutor, con (texto, tarea). Cada uno
# lleva su icono delante: en la rejilla se reconocen de un vistazo.
TAREAS_INGLES = (
    ("\u2705  Corregir", "corregir"),
    ("\U0001F4AC  Conversar", "conversar"),
    ("\U0001F5E3  Speaking", "speaking"),
    ("\u270F  Ejercicios", "practicar"),
    ("\U0001F9E9  Explicar", "explicar"),
    ("\U0001F4D6  Vocabulario", "vocabulario"),
    ("\U0001F501  Repaso", "repaso"),
    ("\U0001F4CA  Mi avance", "progreso"),
    ("\U0001F5D1  Borrar", "borrar"),
)
#: La tarea principal se pinta con el color de acento (es la que más se usa);
#: la que borra, en rojo suave, para que no se pulse por descuido.
TAREA_INGLES_PRINCIPAL = "corregir"
TAREA_INGLES_PELIGRO = "borrar"

#: Lo que se ve en el panel de la clase al abrir el apartado por primera vez. Va
#: en Markdown con títulos «## icono título», que es lo que convierte el panel en
#: tarjetas: la primera explica el apartado y la segunda, el nivel.
AYUDA_INGLES = (
    "## \U0001F44B Cómo se usa\n"
    "1. Escribe (o dicta) tu frase o tu texto en inglés en el cuadro «Tu inglés». "
    "Al corregirlo se apuntan tus fallos para el repaso.\n"
    "2. Pulsa lo que quieras que te prepare:\n"
    "   · **\u2705 Corregir**: versión corregida, punto por punto, reglas de fondo y ejercicios.\n"
    "   · **\U0001F4AC Conversar**: te contesta en inglés y te corrige al final.\n"
    "   · **\U0001F5E3 Speaking**: hablas tú: el micrófono te escucha en inglés, te corrige por "
    "escrito y te contesta en voz alta.\n"
    "   · **\u270F Ejercicios**: práctica del tema que escribas o, si lo dejas vacío, de lo que "
    "más te falla.\n"
    "   · **\U0001F9E9 Explicar** y **\U0001F4D6 Vocabulario**: usan el tema del campo «Tema».\n"
    "   · **\U0001F501 Repaso**: vuelve sobre los errores que más se te repiten.\n"
    "   · **\U0001F4CA Mi avance**: nivel, prácticas y lo que más te cuesta (no gasta IA).\n"
    "3. Cuando la clase esté lista, puedes copiarla o guardarla en documentos.\n"
    "\n"
    "## \U0001F39A Tu nivel\n"
    "Se cambia arriba a la derecha (**Nivel**) y queda guardado en Jarvis/ingles: "
    "la clase se prepara con esa dificultad."
)

# Color de cada paso del indicador "qué está haciendo": lo que hace ahora en
# claro, lo terminado en verde y los avisos en el color de aviso.
COLOR_PASOS = {"paso": COLOR_TEXTO, "hecho": COLOR_OK, "aviso": COLOR_AVISO}
MARCAS_PASOS = {"paso": "→", "hecho": "✓", "aviso": "!"}

# ---------------- Adjuntos ----------------
CARPETA_ADJUNTOS = rutas.ADJUNTOS
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"}
EXT_TEXTO = {".txt", ".md", ".markdown", ".py", ".json", ".csv", ".log", ".html", ".htm",
             ".xml", ".js", ".ts", ".css", ".c", ".cpp", ".h", ".hpp", ".java", ".cs",
             ".sql", ".yaml", ".yml", ".ini", ".cfg", ".bat", ".ps1", ".sh", ".env",
             ".toml", ".rst", ".pyw", ".tsx", ".jsx", ".php", ".rb", ".go", ".rs"}
MAX_TEXTO_ADJUNTO = 12000  # caracteres máximos que se envían por archivo a la IA

# El Entry de Tk se vuelve extremadamente lento (O(n²)) al insertar cadenas
# enormes: 20.000 car. ~0,5 s y 100.000 car. ~13 s, lo que congela la interfaz.
# Por encima de este umbral, el texto pegado se guarda como documento adjunto.
UMBRAL_PEGADO_TEXTO = 8000

# ---------------- Documentos de texto ----------------
CARPETA_DOCUMENTOS = rutas.DOCUMENTOS

# ---------------- Ubicaciones (rutas/URLs) citadas en los mensajes ----------------
# Se detectan para ofrecer un botón que las abra con un solo clic.
RE_UBICACION = re.compile(
    r'"([A-Za-z]:[\\/][^"\r\n]+)"'        # "C:\ruta con espacios\archivo.txt"
    r'|`([A-Za-z]:[\\/][^`\r\n]+)`'       # `C:\ruta\archivo.txt`
    r'|(\\\\[^\s<>"\'`)\]]+)'             # \\servidor\recurso\archivo.txt (UNC)
    r'|([A-Za-z]:[\\/][^\s<>"\'`)\]]*)'   # C:\ruta\archivo.txt (sin espacios)
    r'|(https?://[^\s<>"\'`)\]]+)'        # https://ejemplo.com
)


class AppGUI(ctk.CTk):
    def __init__(self, config_path=rutas.CONFIG_USUARIO, voice_output=None):
        super().__init__()

        self.config_path = config_path
        self.escuchando = False
        self.chat_activo = None      # None = sin definir, False = bienvenida, True = conversación
        self._procesando = False
        self._ind_pensando = None
        self._lbl_pensando = None    # rótulo "Jarvis está trabajando (0:12)"
        self._lbl_pulso = None       # punto que late a su lado
        self._marco_pasos = None     # caja donde van cayendo los pasos
        self._pasos = []             # [(tipo, texto)] de la tarea en curso
        self._tarea_inicio = None    # cuándo empezó (para el reloj del indicador)
        self._pegado_abajo = True    # True si el usuario está viendo el final del chat
        self.adjuntos = []          # lista de dicts con los archivos adjuntos pendientes
        self._burbujas = []         # registros de las burbujas visibles (para selección)
        self._seleccion = []        # registros de las burbujas seleccionadas
        self.conversacion_actual = None  # ruta del archivo de la conversación activa
        # Apartado de inglés: la clase vive en su propio panel (no en el chat) y
        # `_ingles_borrar_pendiente` recuerda si ya se pidió confirmación para
        # borrar el historial de fallos del alumno.
        self._clase_ingles = ""
        self._tarjetas_clase = []   # tarjetas pintadas en el panel de la clase
        self._marcos_clase = []     # marcos de esas tarjetas (título e icono)
        self._ingles_borrar_pendiente = False
        os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)

        # Instanciar módulos
        self.brain = APIBrain(config_path)
        self.system = SystemActions(config_path)
        self.voice = VoiceEngine(config_path)

        # Estado del OCR (lectura de texto dentro de imágenes adjuntas)
        self.ocr_motor = ocr_motor()
        print(f"OCR activo: {self.ocr_motor}" if self.ocr_motor
              else "OCR no disponible: no se leerá el texto de las imágenes.")

        # Salida de voz (si se recibe desde main.py o se crea por defecto)
        self.voice_output = voice_output if voice_output else VoiceOutput()

        # Alertas por voz (pomodoro) apuntan al reproductor
        self.system.productivity.on_alerta = self.reproducir_voz

        # Asistente de reuniones: alertas por voz + resumen con la IA + monitoreo
        self.system.meeting.on_alerta = self.reproducir_voz
        self.system.meeting.on_resumen = self._resumir_reunion
        self.system.meeting.on_metadatos = self._metadatos_reunion
        # El aviso de escritorio es lo que se ve cuando la transcripción acaba
        # con Jarvis detrás (o cerrado): la voz sola no se escucha.
        self.system.meeting.on_notificar = self._notificar_reunion
        self.system.meeting.iniciar_monitoreo()

        # Herramientas de preventa: generación de documentos con la IA
        self.system.preventa.on_generar = self._generar_preventa

        # SharePoint/OneDrive sin Graph: clasificación de archivos con la IA
        self.system.sharepoint.on_clasificar = self._clasificar_archivos_ia

        # Lo que va haciendo el asistente se ve en el chat: la ventana escucha el
        # canal de progreso de las acciones (SharePoint, IA, correo...) y lo pinta
        # en el indicador, en vez de dejar un "escribiendo..." sin explicación.
        self.system.progreso.conectar(self._progreso_gui)

        # Configuración de la ventana principal
        self.title("Jarvis")
        self.geometry("1120x760")
        self.resizable(True, True)
        self.minsize(900, 600)
        self.configure(fg_color=COLOR_FONDO)

        self._crear_interfaz()
        self._cargar_config_en_inputs()
        self._cargar_conversaciones_sidebar()

    # ---------------- Construcción de la interfaz ----------------
    def _crear_interfaz(self):
        # Las fuentes se eligen al montar la ventana: hasta que no hay un root de
        # Tk no se pueden consultar las familias instaladas del sistema.
        _resolver_fuentes()
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True)

        self._crear_sidebar(contenedor)

        # Área principal (derecha)
        self.area_principal = ctk.CTkFrame(contenedor, fg_color=COLOR_PANEL, corner_radius=0)
        self.area_principal.pack(side="left", fill="both", expand=True)

        # Barra superior con degradado: da el toque de color de la casa (turquesa
        # → azul → fondo) sin ensuciar el resto de la ventana.
        self._crear_barra_superior(self.area_principal)

        # Tres vistas dentro del área principal: chat, ajustes y el apartado del
        # tutor de inglés (el tutor no se usa desde el chat: tiene la suya).
        self.vista_chat = ctk.CTkFrame(self.area_principal, fg_color="transparent")
        self.vista_ajustes = ctk.CTkFrame(self.area_principal, fg_color="transparent")
        self.vista_ingles = ctk.CTkFrame(self.area_principal, fg_color="transparent")

        self._crear_vista_chat(self.vista_chat)
        self._crear_vista_ajustes(self.vista_ajustes)
        self._crear_vista_ingles(self.vista_ingles)

        self._mostrar_vista("chat")
        self._mostrar_estado_chat(False)

        # Los campos de una línea (tu nombre, la API Key, el tema de inglés...) van
        # con los mismos atajos: se recorren ahora, que ya están todos creados.
        self._atajos_en_campos()

    def _crear_barra_superior(self, parent):
        """Pinta la línea de degradado que corona el área de trabajo.

        El degradado acaba justo en el color del panel: así encaja con cualquier
        ancho de ventana (lo que sobra sigue siendo del mismo color que el fondo).
        """
        ancho = 900
        imagen = imagen_degradado(ancho, 3, ((0.0, COLOR_ACENTO), (0.32, COLOR_ACENTO_2),
                                             (1.0, COLOR_PANEL)))
        self._brillo_superior = ctk.CTkImage(light_image=imagen, dark_image=imagen,
                                             size=(ancho, 3))
        self.barra_superior = ctk.CTkLabel(parent, text="", image=self._brillo_superior,
                                           fg_color=COLOR_PANEL, height=3)
        self.barra_superior.pack(side="top", fill="x")

    def _crear_sidebar(self, parent):
        self.sidebar = ctk.CTkFrame(parent, width=276, fg_color=COLOR_SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Cabecera: el logo en su pastilla de acento y el nombre del asistente
        cabecera = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        cabecera.pack(fill="x", padx=16, pady=(18, 14))
        ctk.CTkLabel(cabecera, text="\u2726", width=38, height=38, corner_radius=12,
                     fg_color=_mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(FUENTE_UI, 18)).pack(side="left")
        titulos = ctk.CTkFrame(cabecera, fg_color="transparent")
        titulos.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(titulos, text="Jarvis", font=(FUENTE_UI, 17, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w")
        ctk.CTkLabel(titulos, text="Tu asistente personal", font=(FUENTE_UI, 10),
                     text_color=COLOR_TEXTO_SUAVE).pack(anchor="w")

        # Botón "Nuevo chat" (tarjeta con borde suave: la acción de la casa es
        # escribir en el chat, pero no compite con el acento del apartado)
        self.btn_nuevo = ctk.CTkButton(
            self.sidebar, text="\uff0b   Nuevo chat", anchor="w",
            font=(FUENTE_UI, 13), height=40, corner_radius=RADIO_CHIP,
            fg_color=COLOR_TARJETA, hover_color=COLOR_TARJETA_ALTA, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE,
            command=self._nueva_conversacion,
        )
        self.btn_nuevo.pack(fill="x", padx=14, pady=(0, 16))

        # Apartado del tutor de inglés: botón propio con su vista, porque el tutor
        # no se usa desde el chat (se escribe en su caja, no en el mensaje).
        ctk.CTkLabel(self.sidebar, text="APARTADOS", font=(FUENTE_UI, 10, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(anchor="w", padx=20, pady=(0, 6))
        self.btn_ingles = ctk.CTkButton(
            self.sidebar, text="\U0001F393   Inglés", anchor="w",
            font=(FUENTE_UI, 13), height=40, corner_radius=RADIO_CHIP,
            fg_color="transparent", hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE,
            command=lambda: self._mostrar_vista("ingles"),
        )
        self.btn_ingles.pack(fill="x", padx=14, pady=(0, 18))

        # Encabezado de sección
        ctk.CTkLabel(self.sidebar, text="CONVERSACIONES", font=(FUENTE_UI, 10, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(anchor="w", padx=20, pady=(0, 4))

        # Lista scrollable de conversaciones
        self.lista_conv = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent",
                                                 **BARRA_SCROLL)
        self.lista_conv.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Pie: tu nombre (el que pones en Ajustes → «Tu nombre», que es el que
        # Jarvis recuerda y usa para dirigirse a ti) + el botón de ajustes.
        pie = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        pie.pack(side="bottom", fill="x", padx=14, pady=12)
        self.avatar = ctk.CTkLabel(pie, text="\u2726", width=32, height=32, corner_radius=16,
                                   fg_color=COLOR_ACENTO, text_color=COLOR_ACENTO_TEXTO,
                                   font=(FUENTE_UI, 13, "bold"), cursor="hand2")
        self.avatar.pack(side="left")
        self.lbl_usuario = ctk.CTkLabel(pie, text=USUARIO_SIN_NOMBRE,
                                        font=(FUENTE_UI, 13), text_color=COLOR_TEXTO_SUAVE,
                                        cursor="hand2")
        self.lbl_usuario.pack(side="left", padx=(10, 0))
        # Pulsar tu nombre lleva a Ajustes, que es donde se cambia.
        for widget in (self.avatar, self.lbl_usuario):
            widget.bind("<Button-1>", lambda e: self._mostrar_vista("ajustes"))
        ctk.CTkButton(pie, text="\u2699", width=32, height=32, corner_radius=RADIO_CHIP,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 16),
                      command=self._toggle_ajustes).pack(side="right")

    def _mostrar_vista(self, vista):
        # Al salir del apartado de inglés se apaga su micrófono: si no, seguiría
        # escuchando (y gastando IA) desde una vista que ya no se ve.
        if vista != "ingles" and getattr(self, "_speaking_activo", False):
            self._parar_speaking("Micrófono apagado.")
        self.vista_chat.pack_forget()
        self.vista_ajustes.pack_forget()
        self.vista_ingles.pack_forget()
        self._resaltar_apartado(vista)
        if vista == "ajustes":
            self.vista_ajustes.pack(fill="both", expand=True)
            self._cargar_reglas_ui()
        elif vista == "ingles":
            self.vista_ingles.pack(fill="both", expand=True)
            self._actualizar_ingles()
        else:
            self.vista_chat.pack(fill="both", expand=True)

    def _resaltar_apartado(self, vista):
        """Deja marcado en la barra lateral en qué apartado estás.

        El apartado abierto se ve como una tarjeta con el borde encendido en el
        color de acento (un «glow» sutil); al salir vuelve a su sitio.
        """
        abierto = vista == "ingles"
        try:
            self.btn_ingles.configure(
                fg_color=COLOR_TARJETA if vista == "ingles" else "transparent",
                border_color=COLOR_ACENTO if abierto else COLOR_BORDE,
                text_color=COLOR_ACENTO if abierto else COLOR_TEXTO)
        except Exception:
            pass

    def _toggle_ajustes(self):
        if self.vista_ajustes.winfo_ismapped():
            self._mostrar_vista("chat")
        else:
            self._mostrar_vista("ajustes")

    def _crear_vista_chat(self, parent):
        # Espaciadores para centrar la bienvenida verticalmente. Se les da un alto
        # mínimo (por defecto un CTkFrame pide 200 px): así el reparto del espacio
        # sobrante es igual para los dos y el hero queda realmente centrado.
        self.spacer_top = ctk.CTkFrame(parent, fg_color="transparent", height=1)
        self.spacer_bottom = ctk.CTkFrame(parent, fg_color="transparent", height=1)

        # Hero (pantalla de bienvenida): el icono de la casa en una pastilla con el
        # borde encendido, para que la primera pantalla hable el mismo idioma visual
        # que el resto (tarjetas redondeadas y acento).
        self.hero = ctk.CTkFrame(parent, fg_color="transparent")
        pastilla = ctk.CTkFrame(self.hero, fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.10),
                                corner_radius=24, border_width=1, border_color=COLOR_ACENTO,
                                width=78, height=78)
        pastilla.pack()
        pastilla.pack_propagate(False)
        ctk.CTkLabel(pastilla, text="\u2726", font=(FUENTE_UI, 34),
                     text_color=COLOR_ACENTO).pack(expand=True)
        ctk.CTkLabel(self.hero, text="\u00bfEn qué puedo ayudarte hoy?",
                     font=(FUENTE_UI, 26, "bold"), text_color=COLOR_TEXTO).pack(pady=(14, 0))
        ctk.CTkLabel(self.hero, text="Escribe tu mensaje o usa el micrófono para dictarlo.",
                     font=(FUENTE_UI, 13), text_color=COLOR_TEXTO_SUAVE).pack(pady=(6, 0))

        # Historial de conversación (burbujas)
        self.chat_scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent",
                                                  **BARRA_SCROLL)
        # Al cambiar el tamaño de la vista (ventana, barra de selección, maximizar...)
        # se reancla el final: el <Configure> del lienzo es la señal fiable del cambio
        # de alto disponible. add="+" conserva el manejador interno de
        # CTkScrollableFrame (que ajusta el ancho del contenido).
        self.chat_scroll._parent_canvas.bind("<Configure>", self._chat_redimensionado, add="+")
        # El lienzo avisa (yscrollcommand) cada vez que se desplaza: así sabemos si
        # el usuario está viendo el final y podemos reanclarlo al redimensionar.
        self.chat_scroll._parent_canvas.configure(yscrollcommand=self._scroll_actualizado)

        # Barra de entrada (compartida por ambos estados)
        self._crear_barra_input(parent)

    def _crear_barra_input(self, parent):
        self.barra_input = ctk.CTkFrame(parent, fg_color="transparent")

        # Fila de chips con los adjuntos pendientes (se rellena dinámicamente).
        # No se empaqueta aquí a propósito: un CTkFrame sin hijos conserva su alto
        # por defecto (200 px) y dejaría una banda muerta entre el chat y la caja
        # de escritura, cortando los mensajes por encima del cuadro de texto.
        # _actualizar_adjuntos_ui() la muestra solo cuando hay adjuntos.
        self.adjuntos_frame = ctk.CTkFrame(self.barra_input, fg_color="transparent")

        # La caja de escritura es una tarjeta muy redondeada que se enciende (borde
        # de acento) mientras se escribe: es el «glow» del panel activo.
        caja = ctk.CTkFrame(self.barra_input, fg_color=COLOR_TARJETA, corner_radius=22,
                            border_width=1, border_color=COLOR_BORDE)
        caja.pack(fill="x")
        self.caja_input = caja  # referencia para recolocar la fila de chips encima

        # Botón para adjuntar archivos (📎) y explorador (📁): círculos suaves.
        self.btn_adjuntar = ctk.CTkButton(
            caja, text="\U0001F4CE", width=36, height=36, corner_radius=18,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 15),
            command=self._adjuntar_archivos)
        self.btn_adjuntar.pack(side="left", padx=(10, 0), pady=8)

        self.btn_explorador = ctk.CTkButton(
            caja, text="\U0001F4C1", width=36, height=36, corner_radius=18,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 15),
            command=self._abrir_explorador)
        self.btn_explorador.pack(side="left", padx=(6, 0), pady=8)

        # La caja de escritura crece hacia abajo: el mensaje largo se lee entero en
        # varias líneas (antes se iba hacia el lado dentro de una sola línea). Enter
        # envía el mensaje y Shift+Enter hace un salto de línea.
        self.entry_chat = ctk.CTkTextbox(
            caja, height=ALTO_INPUT_MIN, wrap="word", fg_color="transparent",
            border_width=0, corner_radius=0, text_color=COLOR_TEXTO,
            scrollbar_button_color=COLOR_TARJETA_ALTA,
            scrollbar_button_hover_color=COLOR_ACENTO,
            undo=True, maxundo=200, autoseparators=True,
            font=(FUENTE_UI, 14))
        self.entry_chat.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=8)
        self.entry_chat._textbox.configure(spacing1=2, spacing3=2, padx=0, pady=2)
        self._alto_input_actual = ALTO_INPUT_MIN
        self._chat_vacio = True          # dentro está el aviso, no un mensaje
        self._poner_fantasma()

        self.btn_enviar = ctk.CTkButton(
            caja, text="\u2191", width=38, height=38, corner_radius=19,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO,
            font=(FUENTE_UI, 18, "bold"), command=self._enviar_chat)
        self.btn_enviar.pack(side="right", padx=(0, 8), pady=5)

        # El micrófono: el gesto de hablarle a Jarvis, con el círculo bien visible y
        # un anillo alrededor que late (onda de sonido) mientras está escuchando.
        self._onda_mic = None
        self.marco_mic = ctk.CTkFrame(caja, fg_color="transparent", width=50, height=50,
                                      corner_radius=25, border_width=2,
                                      border_color=COLOR_BORDE)
        self.marco_mic.pack(side="right", padx=(0, 4), pady=1)
        self.marco_mic.pack_propagate(False)
        self.btn_mic = ctk.CTkButton(
            self.marco_mic, text="\U0001F3A4", width=42, height=42, corner_radius=21,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            text_color=COLOR_ACENTO, font=(FUENTE_UI, 17),
            command=self.toggle_escucha)
        self.btn_mic.pack(expand=True)
        self._actualizar_mic()

        self.entry_chat.bind("<Return>", self._enviar_con_enter)
        self.entry_chat.bind("<Control-v>", self._pegar_portapapeles)
        self.entry_chat.bind("<<Paste>>", self._pegar_portapapeles)
        self.entry_chat.bind("<KeyRelease>", self._tecla_soltada)
        # Los atajos de edición (Ctrl+Supr para la línea entera, Ctrl+A, Ctrl+Z,
        # Ctrl+←/→ para mover de palabra...): Tk no los trae puestos en las cajas
        # de texto, se los pone la ventana (ver `_atajos_caja`).
        self._atajos_caja(self.entry_chat)
        # Al cambiar el ancho de la caja (ventana más pequeña) el texto se reparte en
        # más líneas: se recalcula el alto para que no se quede ningún renglón fuera.
        self.entry_chat.bind("<Configure>", self._ajustar_alto_input)
        # Al entrar en la caja, su borde se enciende con el acento (panel activo) y
        # se va el texto de ayuda; al salir, se apaga y el aviso vuelve si está vacía.
        self.entry_chat.bind("<FocusIn>", lambda e: self._foco_input(True))
        self.entry_chat.bind("<FocusOut>", lambda e: self._foco_input(False))
        self.caja_input.bind("<Button-1>", lambda e: self.entry_chat.focus_set())

        ctk.CTkLabel(self.barra_input,
                     text="Jarvis puede cometer errores. Verifica la información importante.",
                     font=(FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE).pack(pady=(6, 0))

        # Barra de acciones de la selección de mensajes (oculta por defecto)
        self._crear_barra_seleccion(parent)

    def _glow_input(self, activo):
        """Enciende el borde de la caja de escritura mientras está activa."""
        try:
            self.caja_input.configure(
                border_color=COLOR_ACENTO if activo else COLOR_BORDE,
                fg_color=_mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.06) if activo
                else COLOR_TARJETA)
        except Exception:
            pass

    # ---------------- La caja de escritura (crece hacia abajo) ----------------
    def _poner_fantasma(self):
        """Deja el aviso en la caja vacía: en gris y se borra al empezar a escribir.

        El `CTkTextbox` no trae placeholder propio, así que el aviso es texto de
        verdad dentro de la caja; `_chat_vacio` recuerda que eso no es un mensaje.
        """
        try:
            if self.entry_chat.get("1.0", "end-1c"):
                return
            self.entry_chat.insert("1.0", AVISO_INPUT)
            self.entry_chat.configure(text_color=COLOR_TEXTO_SUAVE)
            self._chat_vacio = True
            # El historial de deshacer empieza en la caja vacía: así Ctrl+Z no
            # devuelve el aviso ni el mensaje que se acaba de enviar.
            self.entry_chat._textbox.edit_reset()
        except Exception:
            pass

    def _texto_input(self):
        """Lo que hay escrito de verdad en la caja (el aviso no cuenta)."""
        try:
            texto = self.entry_chat.get("1.0", "end-1c")
        except Exception:
            return ""
        if getattr(self, "_chat_vacio", False):
            if texto.strip() == AVISO_INPUT:
                return ""
            # El aviso seguía dentro y se ha escrito detrás: no forma parte del mensaje.
            texto = texto.replace(AVISO_INPUT, "", 1)
        return texto.strip()

    def _revisar_fantasma(self):
        """Retira el aviso en cuanto se escribe algo, sin llevarse lo escrito.

        El aviso es texto de verdad dentro de la caja (un `CTkTextbox` no trae
        placeholder propio): si se escribía encima, el aviso acababa dentro del
        mensaje y el texto se quedaba en gris. Aquí se quita justo al empezar,
        esté donde esté (delante o detrás de lo escrito).
        """
        if not getattr(self, "_chat_vacio", False):
            return
        try:
            actual = self.entry_chat.get("1.0", "end-1c")
        except Exception:
            return
        if actual == AVISO_INPUT:
            return                      # todavía no se ha escrito nada
        if AVISO_INPUT in actual:
            self.entry_chat.delete("1.0", "end")
            self.entry_chat.insert("1.0", actual.replace(AVISO_INPUT, "", 1))
            self.entry_chat.mark_set("insert", "end")
        self._chat_vacio = False
        try:
            self.entry_chat.configure(text_color=COLOR_TEXTO)
        except Exception:
            pass

    def _tecla_soltada(self, evento=None):
        """Tras cada tecla: fuera el aviso si ya hay texto y ajuste del alto."""
        self._revisar_fantasma()
        self._ajustar_alto_input()

    def _limpiar_input(self):
        """Vacía la caja (dejando su aviso) y la devuelve a una línea de alto."""
        self._chat_vacio = False
        try:
            self.entry_chat.delete("1.0", "end")
        except Exception:
            return
        self._poner_fantasma()
        self._ajustar_alto_input()

    def _foco_input(self, activo):
        """Entrar en la caja la enciende y se lleva el aviso; salir lo devuelve."""
        self._glow_input(activo)
        if activo:
            self._despertar_input()
        elif not self._texto_input():
            self._chat_vacio = False
            try:
                self.entry_chat.delete("1.0", "end")
            except Exception:
                return
            self._poner_fantasma()

    def _ajustar_alto_input(self, evento=None):
        """Sube el alto de la caja con el texto escrito (hacia abajo, no a lo ancho).

        Se cuentan las líneas que ocupa el texto *con el ancho actual* (por eso se
        recalcula al escribir y al redimensionar), y la caja crece de una a siete
        líneas; a partir de ahí el texto se desplaza por dentro.
        """
        try:
            cuenta = self.entry_chat._textbox.count("1.0", "end", "displaylines")
            lineas = int(cuenta[0]) if cuenta else 1
        except Exception:
            return
        lineas = max(1, min(ALTO_INPUT_LINEAS_MAX, lineas))
        alto = ALTO_INPUT_MIN + (lineas - 1) * ALTO_INPUT_LINEA
        if getattr(self, "_alto_input_actual", None) == alto:
            return
        try:
            self.entry_chat.configure(height=alto)
            self._alto_input_actual = alto
        except Exception:
            pass

    # ---------------- Atajos de edición de las cajas de texto ----------------
    # Tk trae pocos atajos en las cajas de escribir (los de Emacs: Ctrl+K, Ctrl+D)
    # y le faltan los que se dan por hechos en Windows. Ver ATAJOS_CAJA/ATAJOS_CAMPO.
    def _atajos_caja(self, caja):
        """Pone en una caja de escribir los atajos que Tk no trae de serie.

        Se enlaza en el widget de dentro (el `tk.Text`), que es quien recibe las
        teclas; los manejadores devuelven «break» para que Tk no haga además lo
        suyo (su Ctrl+K, por ejemplo).
        """
        for secuencia, accion in ATAJOS_CAJA:
            if accion.startswith("<<"):
                caja.bind(secuencia, lambda e, cual=accion: self._virtual_caja(e, cual))
            else:
                caja.bind(secuencia, getattr(self, "_%s_caja" % accion))
        return caja

    def _atajos_en_campos(self):
        """Los atajos de una línea en todos los campos (`CTkEntry`) de la ventana.

        Los campos se crean por todas las vistas (Ajustes, inglés, correo...), así
        que se recorren una vez montada la interfaz en lugar de ir uno a uno.
        """
        pendientes = list(self.winfo_children())
        while pendientes:
            widget = pendientes.pop()
            pendientes.extend(widget.winfo_children())
            if isinstance(widget, tk.Entry):
                for secuencia, accion in ATAJOS_CAMPO:
                    widget.bind(secuencia, getattr(self, "_%s_campo" % accion))

    def _caja_de(self, evento, caja):
        """El widget que hay que editar: el que se pasa o el que disparó la tecla."""
        if caja is not None:
            return caja
        return getattr(evento, "widget", None)

    def _es_caja_chat(self, caja):
        """¿Ese widget (el de dentro) es la caja de escribir del chat?"""
        caja_chat = getattr(self, "entry_chat", None)
        return caja is caja_chat or caja is getattr(caja_chat, "_textbox", None)

    def _despertar_input(self):
        """Se lleva el aviso de la caja del chat: es texto dentro, no un placeholder."""
        if not getattr(self, "_chat_vacio", False):
            return
        self._chat_vacio = False
        try:
            self.entry_chat.delete("1.0", "end")
            self.entry_chat.configure(text_color=COLOR_TEXTO)
        except Exception:
            pass

    def _despertar_caja(self, caja):
        """Antes de editar con un atajo, en el chat se quita el aviso si está."""
        if self._es_caja_chat(caja):
            self._despertar_input()

    def _tras_editar_caja(self, caja):
        """Tras editar con un atajo, la caja del chat repasa el aviso y su alto."""
        if self._es_caja_chat(caja):
            self._revisar_fantasma()
            self._ajustar_alto_input()

    def _virtual_caja(self, evento, cual):
        """Los atajos que Tk ya sabe resolver se le mandan como evento virtual."""
        caja = self._caja_de(evento, None)
        self._despertar_caja(caja)
        if caja is None:
            return "break"
        caja.event_generate(cual)
        self._tras_editar_caja(caja)
        return "break"

    def _seleccionar_todo_caja(self, evento=None, caja=None):
        """Ctrl+A: selecciona el mensaje entero.

        El `<<SelectAll>>` de Tk se lleva también el salto de línea del final (el
        que Tk guarda siempre detrás del texto); aquí se selecciona solo lo escrito.
        """
        caja = self._caja_de(evento, caja)
        if caja is None:
            return "break"
        self._despertar_caja(caja)
        caja.tag_remove("sel", "1.0", "end")
        caja.tag_add("sel", "1.0", "end-1c")
        caja.mark_set("insert", "end-1c")
        self._tras_editar_caja(caja)
        return "break"

    def _quitar_lineas(self, caja, desde, hasta):
        """Borra las líneas de «desde» a «hasta», con su salto, sin dejar hueco.

        Si es la última línea (no lleva salto detrás) se quita también el salto de
        la anterior: la línea desaparece de verdad en vez de quedarse en blanco.
        """
        ultima = caja.compare(hasta, "==", "end-1c")
        caja.delete(desde, hasta if ultima else "%s +1c" % hasta)
        if ultima and caja.compare(desde, ">", "1.0"):
            caja.delete("%s -1c" % desde)

    def _borrar_linea_caja(self, evento=None, caja=None):
        """Ctrl+Supr: borra la línea entera donde está el cursor (y su salto)."""
        caja = self._caja_de(evento, caja)
        if caja is None:
            return "break"
        self._despertar_caja(caja)
        if caja.tag_ranges("sel"):
            self._quitar_lineas(caja, "sel.first linestart", "sel.last lineend")
        else:
            self._quitar_lineas(caja, "insert linestart", "insert lineend")
        self._tras_editar_caja(caja)
        return "break"

    def _borrar_hasta_final_caja(self, evento=None, caja=None):
        """Ctrl+Mayús+Supr: del cursor al final de la línea.

        Si el cursor ya está al final, se lleva el salto de línea (junta con la
        siguiente), que es lo que se espera al ir pulsando repetido.
        """
        caja = self._caja_de(evento, caja)
        if caja is None:
            return "break"
        self._despertar_caja(caja)
        if caja.tag_ranges("sel"):
            caja.delete("sel.first", "sel.last")
        elif caja.compare("insert", "==", "insert lineend"):
            if caja.compare("insert", "<", "end-1c"):
                caja.delete("insert", "insert +1c")
        else:
            caja.delete("insert", "insert lineend")
        self._tras_editar_caja(caja)
        return "break"

    def _borrar_palabra_caja(self, evento=None, caja=None):
        """Ctrl+Retroceso: borra la palabra de la izquierda (o lo seleccionado)."""
        caja = self._caja_de(evento, caja)
        if caja is None:
            return "break"
        self._despertar_caja(caja)
        if caja.tag_ranges("sel"):
            caja.delete("sel.first", "sel.last")
        elif caja.compare("insert", ">", "1.0"):
            if caja.get("insert -1c", "insert") == "\n":
                caja.delete("insert -1c")       # en el principio: junta las líneas
            else:
                inicio = caja.index("insert -1c wordstart")
                principio = caja.index("insert linestart")
                if caja.compare(inicio, "<", principio):
                    inicio = principio          # de la línea no se sale
                caja.delete(inicio, "insert")
        self._tras_editar_caja(caja)
        return "break"

    # Los campos de una línea (`CTkEntry`) no entienden «wordstart» ni «insert -1c»:
    # la palabra anterior se busca mirando el texto, que en una línea es directo.
    def _seleccionar_todo_campo(self, evento=None, caja=None):
        """Ctrl+A en un campo: se selecciona todo lo escrito."""
        campo = self._caja_de(evento, caja)
        if campo is None:
            return "break"
        campo.selection_range(0, "end")
        campo.icursor("end")
        return "break"

    def _borrar_hasta_final_campo(self, evento=None, caja=None):
        """Ctrl+Supr en un campo: del cursor al final (o lo seleccionado)."""
        campo = self._caja_de(evento, caja)
        if campo is None:
            return "break"
        if campo.selection_present():
            campo.delete("sel.first", "sel.last")
        elif int(campo.index("insert")) < len(campo.get()):
            campo.delete("insert", "end")
        return "break"

    def _borrar_palabra_campo(self, evento=None, caja=None):
        """Ctrl+Retroceso en un campo: borra la palabra de la izquierda."""
        campo = self._caja_de(evento, caja)
        if campo is None:
            return "break"
        if campo.selection_present():
            campo.delete("sel.first", "sel.last")
            return "break"
        posicion = int(campo.index("insert"))
        texto = campo.get()
        inicio = posicion
        while inicio > 0 and texto[inicio - 1].isspace():       # los huecos de delante
            inicio -= 1
        while inicio > 0 and not texto[inicio - 1].isspace():   # y después la palabra
            inicio -= 1
        if inicio < posicion:
            campo.delete(inicio, posicion)
        return "break"

    def _enviar_con_enter(self, evento=None):
        """Enter envía el mensaje (Shift+Enter, que no pasa por aquí, salta de línea)."""
        if not self._texto_input() and not self.adjuntos:
            return None      # caja vacía: Enter solo baja de línea
        self._enviar_chat()
        return "break"       # sin esto, además de enviar se escribiría un salto

    def _actualizar_mic(self):
        """Pinta el botón del micrófono según el estado de la escucha."""
        escuchando = bool(getattr(self, "escuchando", False))
        try:
            self.btn_mic.configure(fg_color=COLOR_ACENTO if escuchando else COLOR_TARJETA_ALTA,
                                   text_color=COLOR_ACENTO_TEXTO if escuchando else COLOR_ACENTO)
            self.marco_mic.configure(border_color=COLOR_ACENTO if escuchando else COLOR_BORDE)
        except Exception:
            return          # la ventana aún no tiene barra de entrada montada
        if escuchando and self._onda_mic is None:
            self._onda_mic = 0
            self.after(150, self._pulso_mic)
        if not escuchando:
            self._onda_mic = None

    def _pulso_mic(self, paso=0):
        """Late el anillo del micrófono mientras se está escuchando (onda de sonido)."""
        if not getattr(self, "escuchando", False) or self._onda_mic is None:
            self._onda_mic = None
            try:
                self.marco_mic.configure(border_color=COLOR_BORDE)
            except Exception:
                pass
            return
        tonos = (COLOR_ACENTO, _mezclar(COLOR_ACENTO, COLOR_PANEL, 0.55), COLOR_ACENTO_2)
        try:
            self.marco_mic.configure(border_color=tonos[paso % len(tonos)])
        except Exception:
            return
        self.after(170, lambda: self._pulso_mic(paso + 1))

    def _mostrar_estado_chat(self, activo):
        """Alterna entre la pantalla de bienvenida (False) y la conversación (True)."""
        if activo == self.chat_activo:
            return
        self.chat_activo = activo
        for w in (self.spacer_top, self.spacer_bottom, self.hero,
                  self.chat_scroll, self.barra_input, self.barra_seleccion):
            w.pack_forget()
        if activo:
            self.chat_scroll.pack(fill="both", expand=True, padx=6, pady=(12, 0))
            self.barra_input.pack(fill="x", padx=110, pady=(4, 16))
            # Fuerza el cálculo de geometría del área scrollable ANTES de añadir
            # burbujas. Sin esto, al re-empaquetar el CTkScrollableFrame el canvas
            # mantiene un ancho inicial erróneo (p. ej. 1 px), las etiquetas se
            # envuelven a una altura enorme y la vista acaba mostrando un área
            # vacía (chat "en blanco").
            try:
                self.chat_scroll.update_idletasks()
            except Exception:
                pass
        else:
            self.spacer_top.pack(fill="both", expand=True)
            self.hero.pack(fill="x", padx=30, pady=(0, 20))
            self.barra_input.pack(fill="x", padx=110, pady=(0, 8))
            self.spacer_bottom.pack(fill="both", expand=True)
        # Refresca la barra de selección (visible solo si hay mensajes marcados)
        self._actualizar_barra_seleccion()

    # ---------------- Render de mensajes ----------------
    def _ruta_nueva_conversacion(self):
        """Ruta de un archivo nuevo: una conversación independiente por sesión."""
        base = os.path.join(rutas.CONVERSACIONES,
                            "historial_chat_" + datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        ruta = base + ".md"
        i = 2
        while os.path.exists(ruta):
            ruta = f"{base}_{i}.md"
            i += 1
        return ruta

    def _agregar_chat(self, autor, texto, adjuntos=None):
        """Persiste el mensaje en la conversación activa y lo muestra como burbuja.

        Cada conversación se guarda en su propio archivo
        (historial_chat_AAAA-MM-DD_HHMMSS.md). Si no hay conversación activa se
        crea una nueva, de modo que "Nuevo chat" siempre abre un hilo aparte.
        """
        adjuntos = adjuntos or []
        linea_adj = "".join(f" 📎 {a['nombre']}" for a in adjuntos)
        nueva = False
        try:
            os.makedirs(rutas.CONVERSACIONES, exist_ok=True)
            if not self.conversacion_actual:
                self.conversacion_actual = self._ruta_nueva_conversacion()
                nueva = True
            hora = datetime.now().strftime("%H:%M")
            with open(self.conversacion_actual, "a", encoding="utf-8") as f:
                f.write(f"**[{hora}] {autor}:** {texto}{linea_adj}\n\n")
        except Exception as e:
            print(f"Error guardando historial: {e}")

        self.after(0, lambda: self._insertar_burbuja(autor, texto, adjuntos))
        if nueva:
            # Refresca la lista lateral para mostrar el hilo recién creado
            self.after(0, self._cargar_conversaciones_sidebar)

    def _insertar_burbuja(self, autor, texto, adjuntos=None):
        """Añade un mensaje al chat como una burbuja con su icono.

        El asistente lleva su pastilla con la estrella de la casa y el usuario la
        suya, al otro lado: el historial deja de ser una lista de texto seguido.
        """
        adjuntos = adjuntos or []
        self._mostrar_estado_chat(True)

        es_usuario = str(autor).strip().lower() in ("tú", "tu", "usuario", "yo")
        fila = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        fila.pack(fill="x", padx=18, pady=6)

        # El icono va FUERA de la burbuja: el clic sigue seleccionando el mensaje
        # (y no se pierde por pulsar el icono).
        avatar = ctk.CTkLabel(
            fila, text="\U0001F464" if es_usuario else "\u2726",
            width=32, height=32, corner_radius=16, font=(FUENTE_UI, 15),
            fg_color=COLOR_TARJETA_ALTA if es_usuario
            else _mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.18),
            text_color=COLOR_TEXTO_SUAVE if es_usuario else COLOR_ACENTO)
        avatar.pack(side="right" if es_usuario else "left",
                    padx=(8, 0) if es_usuario else (0, 8), anchor="n")

        # Tarjeta de la burbuja: borde suave (y algo de acento en la del usuario)
        burbuja = ctk.CTkFrame(
            fila, corner_radius=RADIO_TARJETA, border_width=1,
            fg_color=COLOR_USUARIO if es_usuario else COLOR_TARJETA,
            border_color=(_mezclar(COLOR_USUARIO, COLOR_ACENTO, 0.4) if es_usuario
                          else COLOR_BORDE))
        burbuja.pack(side="right" if es_usuario else "left")

        ancho_panel = self.area_principal.winfo_width()
        if ancho_panel <= 1:
            ancho_panel = 820
        ancho_texto = max(320, int(ancho_panel * 0.6))

        # Quién habla: con su nombre sobre el texto se sigue el hilo de un vistazo.
        ctk.CTkLabel(burbuja, text="Tú" if es_usuario else "Jarvis",
                     font=(FUENTE_UI, 10, "bold"), anchor="w",
                     text_color=COLOR_TEXTO_SUAVE if es_usuario else COLOR_ACENTO).pack(
                         anchor="w", padx=16, pady=(10, 0))

        # Imágenes adjuntas: vista previa dentro de la burbuja
        for adj in adjuntos:
            if adj.get("tipo") == "imagen":
                img = self._crear_ctkimage(adj["ruta"], max_lado=240)
                if img is not None:
                    lbl_img = ctk.CTkLabel(burbuja, text="", image=img)
                    lbl_img._ctk_image = img  # evita recolección de basura
                    lbl_img.pack(padx=12, pady=(10, 2), anchor="w")

        # Chips de los archivos que no son imágenes
        for adj in adjuntos:
            if adj.get("tipo") != "imagen":
                ctk.CTkLabel(burbuja, text=f"\U0001F4C4 {adj['nombre']}",
                             font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                             fg_color=COLOR_HOVER, corner_radius=8).pack(
                                 padx=12, pady=(6, 0), anchor="w")

        area_texto = None
        if texto:
            if es_usuario:
                # Tu mensaje se enseña tal cual lo escribiste.
                ctk.CTkLabel(burbuja, text=texto, wraplength=ancho_texto, justify="left",
                             anchor="w", font=(FUENTE_UI, 13),
                             text_color=COLOR_TEXTO).pack(padx=16, pady=(4, 12))
            else:
                # Lo del asistente llega en Markdown: se pinta con su formato (negritas,
                # listas, código...) en un área que envuelve al ancho de la burbuja y
                # crece hacia abajo con el texto. Antes se leían los asteriscos.
                area_texto = self._area_markdown_burbuja(burbuja, texto, ancho_texto)

        # Registra la burbuja y permite seleccionarla con un clic. El área del
        # mensaje del asistente se deja fuera: ahí el clic selecciona texto.
        registro = {"autor": autor, "texto": texto, "burbuja": burbuja, "seleccionada": False}
        self._burbujas.append(registro)
        self._vincular_clic(burbuja, lambda e, r=registro: self._toggle_seleccion(r),
                            excepto=(area_texto, ) if area_texto is not None else ())

        # Enlaces clicables a rutas/URLs del mensaje (se añaden DESPUÉS de
        # vincular el clic para no pisar el manejador de selección de burbuja).
        if texto:
            self._agregar_ubicaciones_burbuja(burbuja, texto)

        self.after(30, self._scroll_final)

    # ---------------- Selección de mensajes ----------------
    def _crear_barra_seleccion(self, parent):
        """Construye la barra de acciones que aparece al seleccionar mensajes."""
        self.barra_seleccion = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA_ALTA,
                                            corner_radius=RADIO_TARJETA, border_width=1,
                                            border_color=_mezclar(COLOR_TARJETA_ALTA, COLOR_ACENTO, 0.5))
        ctk.CTkButton(self.barra_seleccion, text="\u2715", width=28, height=28,
                      corner_radius=RADIO_CHIP, fg_color="transparent",
                      hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_TEXTO_SUAVE,
                      font=(FUENTE_UI, 12),
                      command=self._limpiar_seleccion).pack(side="left", padx=(10, 6), pady=6)
        self.lbl_sel = ctk.CTkLabel(self.barra_seleccion, text="0 mensajes seleccionados",
                                    font=(FUENTE_UI, 12), text_color=COLOR_TEXTO)
        self.lbl_sel.pack(side="left", pady=8)
        ctk.CTkButton(self.barra_seleccion, text="Guardar .txt", width=110, height=28,
                      corner_radius=8, fg_color=COLOR_ACENTO,
                      hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      font=(FUENTE_UI, 12, "bold"),
                      command=self._guardar_seleccion_txt).pack(side="right", padx=(4, 10), pady=6)
        ctk.CTkButton(self.barra_seleccion, text="Copiar", width=80, height=28,
                      corner_radius=8, fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, font=(FUENTE_UI, 12),
                      command=self._copiar_seleccion).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(self.barra_seleccion, text="Todo", width=60, height=28,
                      corner_radius=8, fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 12),
                      command=self._seleccionar_todos).pack(side="right", padx=4, pady=6)

    def _vincular_clic(self, widget, callback, excepto=()):
        """Vincula el clic izquierdo a los widgets que reciben clics en la burbuja.

        customtkinter dibuja sobre un Canvas interno y expone los textos en un
        Label interno; se recorren esos componentes reales (sin duplicar) para
        que el clic funcione tanto sobre el texto como sobre el fondo. Lo que
        venga en `excepto` (el área de texto del asistente, donde el clic elige
        texto) se deja sin tocar.
        """
        excluidos = {id(w) for w in excepto}
        for w in self._widgets_clickeables(widget):
            if id(w) in excluidos:
                continue
            try:
                w.bind("<Button-1>", callback)
            except Exception:
                pass
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass

    def _widgets_clickeables(self, raiz):
        """Devuelve los widgets tk (hojas) de un árbol customtkinter sin duplicados."""
        hojas = []
        vistos = set()
        pila = [raiz]
        while pila:
            w = pila.pop()
            if id(w) in vistos:
                continue
            vistos.add(id(w))
            es_customtk = any(hasattr(w, a) for a in ("_canvas", "_label", "_text_label"))
            if es_customtk:
                # Los widgets customtkinter no reciben el clic: lo reciben sus
                # componentes internos (_canvas para el fondo, _label para el texto).
                for attr in ("_canvas", "_label", "_text_label"):
                    hijo = getattr(w, attr, None)
                    if hijo is not None and id(hijo) not in vistos:
                        pila.append(hijo)
            else:
                hojas.append(w)
            try:
                hijos = w.winfo_children()
            except Exception:
                hijos = []
            for hijo in hijos:
                if id(hijo) not in vistos:
                    pila.append(hijo)
        return hojas

    # ---------------- Ubicaciones clicables (rutas/URLs) ----------------
    def _detectar_ubicaciones(self, texto):
        """Devuelve las rutas de archivo y URLs únicas presentes en el texto."""
        if not texto:
            return []
        encontradas = []
        vistos = set()
        for m in RE_UBICACION.finditer(texto):
            valor = next((g for g in m.groups() if g), None)
            if not valor:
                continue
            valor = valor.rstrip(".,;:")
            clave = valor.lower()
            if valor and clave not in vistos:
                vistos.add(clave)
                encontradas.append(valor)
        return encontradas

    def _es_url(self, destino):
        """True si el texto es un enlace con esquema (http://, https://, etc.)."""
        return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", destino or ""))

    def _agregar_ubicaciones_burbuja(self, parent, texto):
        """Añade botones para abrir con un clic las rutas/URLs citadas."""
        ubicaciones = self._detectar_ubicaciones(texto)
        for i, destino in enumerate(ubicaciones):
            icono = "\U0001F310" if self._es_url(destino) else "\U0001F4C1"
            etiqueta = destino if len(destino) <= 80 else "..." + destino[-77:]
            ultimo = i == len(ubicaciones) - 1
            btn = ctk.CTkButton(
                parent, text=f"{icono}  {etiqueta}", anchor="w",
                height=26, corner_radius=8, fg_color=COLOR_HOVER,
                hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO,
                font=(FUENTE_UI, 11),
                command=lambda d=destino: self._abrir_ubicacion(d))
            btn.pack(padx=14, pady=(4, 10 if ultimo else 0), anchor="w")

    def _abrir_ubicacion(self, destino):
        """Abre en el Explorador la ubicación indicada (o la URL en el navegador).

        Si es un archivo, abre su carpeta con el archivo seleccionado; si es una
        carpeta, la abre directamente. Si no existe, intenta abrir la carpeta
        contenedora más cercana y avisa al usuario.
        """
        destino = (destino or "").strip().strip('"').strip("'").strip("`")
        if not destino:
            return
        if self._es_url(destino):
            import webbrowser
            try:
                webbrowser.open(destino)
            except Exception as e:
                self._aviso_input(f"No pude abrir el enlace: {e}")
            return
        import subprocess
        try:
            ruta = os.path.normpath(
                os.path.expandvars(os.path.expanduser(destino)))
            if not os.path.isabs(ruta):
                ruta = os.path.abspath(ruta)
        except Exception:
            ruta = destino
        try:
            if os.path.isfile(ruta):
                subprocess.Popen(f'explorer /select,"{ruta}"')
                return
            if os.path.isdir(ruta):
                os.startfile(ruta)
                return
            # No existe: abro la carpeta contenedora más cercana que sí exista
            carpeta = os.path.dirname(ruta)
            while carpeta and not os.path.isdir(carpeta):
                padre = os.path.dirname(carpeta)
                if padre == carpeta:
                    break
                carpeta = padre
            if carpeta and os.path.isdir(carpeta):
                os.startfile(carpeta)
                self._aviso_input(
                    f"No encontré «{os.path.basename(ruta)}»; abrí {carpeta}")
            else:
                self._aviso_input(f"No encontré la ubicación: {destino}")
        except Exception as e:
            self._aviso_input(f"No pude abrir la ubicación: {e}")

    # ---------------- Mini-explorador de archivos ----------------
    def _abrir_explorador(self):
        """Abre la ventana del mini-explorador (o la trae al frente si ya existe)."""
        ventana = getattr(self, "_ventana_explorador", None)
        if ventana is not None and ventana.winfo_exists():
            ventana.lift()
            ventana.focus_force()
            return
        self._ventana_explorador = ctk.CTkToplevel(self)
        dlg = self._ventana_explorador
        dlg.title("Explorador de archivos")
        dlg.geometry("760x560")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)

        self._expl_dir = None       # carpeta actual
        self._expl_sel = set()      # rutas de archivos seleccionados
        self._expl_todos = []       # rutas de archivos visibles (para 'seleccionar todo')
        self._expl_botones = {}     # ruta -> (botón, texto base) de los archivos

        # Cabecera: ruta actual + navegación
        cabecera = ctk.CTkFrame(dlg, fg_color="transparent")
        cabecera.pack(fill="x", padx=16, pady=(16, 6))
        ctk.CTkButton(cabecera, text="⬆", width=38, height=34, font=(FUENTE_UI, 14),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, command=self._expl_subir).pack(side="left")
        ctk.CTkButton(cabecera, text="⌂", width=38, height=34, font=(FUENTE_UI, 14),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO,
                      command=self._expl_raiz).pack(side="left", padx=(6, 6))
        self._expl_entry_ruta = ctk.CTkEntry(
            cabecera, placeholder_text="Ruta de la carpeta...", fg_color=COLOR_TARJETA,
            border_color=COLOR_BORDE, text_color=COLOR_TEXTO, font=(FUENTE_UI, 12))
        self._expl_entry_ruta.pack(side="left", fill="x", expand=True)
        self._expl_entry_ruta.bind("<Return>", lambda e: self._expl_ir())
        ctk.CTkButton(cabecera, text="Ir", width=44, height=34, font=(FUENTE_UI, 12),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, command=self._expl_ir).pack(side="left", padx=(6, 0))

        # Búsqueda dentro de la carpeta
        busqueda = ctk.CTkFrame(dlg, fg_color="transparent")
        busqueda.pack(fill="x", padx=16, pady=(4, 6))
        self._expl_entry_buscar = ctk.CTkEntry(
            busqueda, placeholder_text="Buscar dentro de esta carpeta...",
            fg_color=COLOR_TARJETA, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO, font=(FUENTE_UI, 12))
        self._expl_entry_buscar.pack(side="left", fill="x", expand=True)
        self._expl_entry_buscar.bind("<Return>", lambda e: self._expl_buscar())
        ctk.CTkButton(busqueda, text="Buscar", width=72, height=34, font=(FUENTE_UI, 12),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=self._expl_buscar).pack(side="left", padx=(6, 0))
        ctk.CTkButton(busqueda, text="Carpeta", width=72, height=34, font=(FUENTE_UI, 12),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO,
                      command=self._expl_actualizar).pack(side="left", padx=(6, 0))

        # Lista de contenidos
        self._expl_lista = ctk.CTkScrollableFrame(dlg, fg_color=COLOR_PANEL,
                                                  corner_radius=10, **BARRA_SCROLL)
        self._expl_lista.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # Pie: estado + botones
        pie = ctk.CTkFrame(dlg, fg_color="transparent")
        pie.pack(fill="x", padx=16, pady=(0, 16))
        self._expl_lbl_estado = ctk.CTkLabel(pie, text="", font=(FUENTE_UI, 11),
                                             text_color=COLOR_TEXTO_SUAVE, anchor="w",
                                             justify="left")
        self._expl_lbl_estado.pack(fill="x", pady=(0, 6))
        botones = ctk.CTkFrame(pie, fg_color="transparent")
        botones.pack(fill="x")
        self._expl_lbl_sel = ctk.CTkLabel(botones, text="0 seleccionados",
                                          font=(FUENTE_UI, 11),
                                          text_color=COLOR_TEXTO_SUAVE)
        self._expl_lbl_sel.pack(side="left", pady=6)
        ctk.CTkButton(botones, text="Seleccionar todo", width=120, height=30,
                      font=(FUENTE_UI, 11), fg_color=COLOR_TARJETA,
                      hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
                      command=self._expl_todo).pack(side="left", padx=(10, 0))
        ctk.CTkButton(botones, text="Abrir", width=70, height=30, font=(FUENTE_UI, 11),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO,
                      command=self._expl_abrir).pack(side="left", padx=(6, 0))
        ctk.CTkButton(botones, text="Mover a…", width=90, height=30, font=(FUENTE_UI, 11),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=lambda: self._expl_mover_copiar("mover")).pack(side="right")
        ctk.CTkButton(botones, text="Copiar a…", width=90, height=30, font=(FUENTE_UI, 11),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=lambda: self._expl_mover_copiar("copiar")).pack(
                          side="right", padx=(0, 6))

        # Punto de partida: primera raíz disponible (OneDrive si existe)
        raices = self.system.archivos.raices()
        self._expl_ir(raices[0] if raices else os.path.expanduser("~"))

    def _expl_ir(self, ruta=None):
        ruta = ruta or self._expl_entry_ruta.get().strip()
        ruta = self.system.archivos.normalizar(ruta)
        entradas = self.system.archivos.listar(ruta)
        if entradas is None:
            self._expl_estado(f"No pude abrir: {ruta}")
            return
        self._expl_dir = ruta
        self._expl_entry_ruta.delete(0, "end")
        self._expl_entry_ruta.insert(0, ruta)
        self._expl_sel.clear()
        self._expl_todos = []
        self._expl_botones = {}
        for widget in self._expl_lista.winfo_children():
            widget.destroy()
        self._expl_fila(None, "📁  ..", es_subir=True)
        for entrada in entradas:
            icono = "📁" if entrada["es_carpeta"] else "📄"
            self._expl_fila(entrada, f"{icono}  {entrada['nombre']}")
        self._expl_estado_sel()
        self._expl_estado(f"{len(entradas)} elemento(s) en {ruta}")

    def _expl_fila(self, entrada, texto, es_subir=False):
        """Crea una fila: '..' para subir, carpeta para entrar o archivo para marcar."""
        if es_subir:
            ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                          fg_color="transparent", hover_color=COLOR_HOVER,
                          text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 12),
                          command=self._expl_subir).pack(fill="x", padx=6, pady=2)
            return
        es_carpeta = bool(entrada.get("es_carpeta"))
        ruta = entrada["ruta"]
        if es_carpeta:
            ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                          fg_color="transparent", hover_color=COLOR_HOVER,
                          text_color=COLOR_TEXTO, font=(FUENTE_UI, 12),
                          command=lambda r=ruta: self._expl_ir(r)).pack(fill="x", padx=6, pady=2)
        else:
            self._expl_todos.append(ruta)
            boton = ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                                  fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                                  text_color=COLOR_TEXTO, font=(FUENTE_UI, 12))
            boton.pack(fill="x", padx=6, pady=2)
            self._expl_botones[ruta] = (boton, texto)
            boton.configure(command=lambda r=ruta, b=boton, t=texto:
                            self._expl_toggle(r, b, t))

    def _expl_subir(self):
        actual = self.system.archivos.normalizar(self._expl_dir or "")
        if actual:
            self._expl_ir(os.path.dirname(actual))

    def _expl_raiz(self):
        raices = self.system.archivos.raices()
        if raices:
            self._expl_ir(raices[0])

    def _expl_actualizar(self):
        self._expl_ir(self._expl_dir)

    def _expl_buscar(self):
        carpeta = self._expl_dir or self._expl_entry_ruta.get().strip()
        nombre = self._expl_entry_buscar.get().strip()
        if not nombre:
            self._expl_actualizar()
            return
        resultados = self.system.archivos.buscar(carpeta, nombre)
        for widget in self._expl_lista.winfo_children():
            widget.destroy()
        self._expl_todos = list(resultados)
        self._expl_sel.clear()
        self._expl_botones = {}
        if not resultados:
            ctk.CTkLabel(self._expl_lista, text=f"Sin resultados para «{nombre}»",
                         font=(FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                         anchor="w").pack(fill="x", padx=10, pady=8)
        for ruta in resultados:
            texto = f"📄  {ruta}"
            boton = ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                                  fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                                  text_color=COLOR_TEXTO, font=(FUENTE_UI, 12))
            boton.pack(fill="x", padx=6, pady=2)
            self._expl_botones[ruta] = (boton, texto)
            boton.configure(command=lambda r=ruta, b=boton, t=texto:
                            self._expl_toggle(r, b, t))
        self._expl_estado_sel()
        self._expl_estado(f"{len(resultados)} archivo(s) encontrados")

    def _expl_toggle(self, ruta, boton, texto):
        if ruta in self._expl_sel:
            self._expl_sel.discard(ruta)
            boton.configure(fg_color=COLOR_TARJETA, text=texto)
        else:
            self._expl_sel.add(ruta)
            boton.configure(fg_color=COLOR_ACENTO_HOVER, text="✓ " + texto)
        self._expl_estado_sel()

    def _expl_todo(self):
        if len(self._expl_sel) == len(self._expl_todos):
            self._expl_sel.clear()
        else:
            self._expl_sel = set(self._expl_todos)
        for ruta, (boton, texto) in self._expl_botones.items():
            if ruta in self._expl_sel:
                boton.configure(fg_color=COLOR_ACENTO_HOVER, text="✓ " + texto)
            else:
                boton.configure(fg_color=COLOR_TARJETA, text=texto)
        self._expl_estado_sel()

    def _expl_abrir(self):
        seleccion = sorted(self._expl_sel)
        if seleccion:
            for ruta in seleccion:
                self._abrir_ubicacion(ruta)
        elif self._expl_dir:
            self._abrir_ubicacion(self._expl_dir)
        else:
            self._expl_estado("Selecciona algo para abrirlo.")

    def _expl_mover_copiar(self, accion):
        seleccion = sorted(self._expl_sel)
        if not seleccion:
            self._expl_estado("Selecciona primero uno o varios archivos.")
            return
        destino = filedialog.askdirectory(title=f"Carpeta de destino ({accion})",
                                          initialdir=self._expl_dir or None)
        if not destino:
            return
        operacion = (self.system.archivos.mover if accion == "mover"
                     else self.system.archivos.copiar)
        resultado = operacion(seleccion, destino, confirmado=True)
        self._expl_estado(self.system.archivos.resumen(resultado))
        self._expl_sel.clear()
        self._expl_actualizar()

    def _expl_estado(self, texto):
        self._expl_lbl_estado.configure(text=texto)

    def _expl_estado_sel(self):
        self._expl_lbl_sel.configure(text=f"{len(self._expl_sel)} seleccionados")

    def _toggle_seleccion(self, registro):
        """Marca o desmarca una burbuja como seleccionada."""
        if registro in self._seleccion:
            self._seleccion.remove(registro)
            registro["seleccionada"] = False
            try:
                registro["burbuja"].configure(border_width=0)
            except Exception:
                pass
        else:
            self._seleccion.append(registro)
            registro["seleccionada"] = True
            try:
                registro["burbuja"].configure(border_width=2,
                                              border_color=COLOR_ACENTO)
            except Exception:
                pass
        self._actualizar_barra_seleccion()

    def _actualizar_barra_seleccion(self):
        """Muestra u oculta la barra de selección según los mensajes marcados."""
        if not hasattr(self, "barra_seleccion"):
            return
        n = len(self._seleccion)
        if n and self.chat_activo:
            plural = "s" if n != 1 else ""
            self.lbl_sel.configure(
                text=f"{n} mensaje{plural} seleccionado{plural}")
            try:
                self.barra_seleccion.pack(fill="x", padx=110, pady=(0, 6),
                                          before=self.barra_input)
            except Exception:
                self.barra_seleccion.pack(fill="x", padx=110, pady=(0, 6))
        else:
            self.barra_seleccion.pack_forget()

    def _seleccionar_todos(self):
        self._seleccion = list(self._burbujas)
        for registro in self._burbujas:
            registro["seleccionada"] = True
            try:
                registro["burbuja"].configure(border_width=2,
                                              border_color=COLOR_ACENTO)
            except Exception:
                pass
        self._actualizar_barra_seleccion()

    def _limpiar_seleccion(self):
        for registro in self._seleccion:
            registro["seleccionada"] = False
            try:
                registro["burbuja"].configure(border_width=0)
            except Exception:
                pass
        self._seleccion = []
        self._actualizar_barra_seleccion()

    def _formatear_seleccion(self):
        """Devuelve el texto de los mensajes seleccionados listo para exportar."""
        lineas = []
        for registro in self._seleccion:
            texto = (registro.get("texto") or "").strip()
            if texto:
                lineas.append(f"{registro.get('autor', '')}: {texto}")
        return "\n\n".join(lineas)

    def _feedback_seleccion(self, mensaje):
        """Muestra un mensaje temporal en la barra de selección."""
        if not hasattr(self, "lbl_sel"):
            return
        self.lbl_sel.configure(text=mensaje)
        self.after(1600, self._actualizar_barra_seleccion)

    def _copiar_seleccion(self):
        texto = self._formatear_seleccion()
        if not texto:
            self._feedback_seleccion("No hay texto que copiar")
            return
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._feedback_seleccion("Copiado al portapapeles")

    def _guardar_seleccion_txt(self):
        contenido = self._formatear_seleccion()
        if not contenido:
            self._feedback_seleccion("No hay texto que guardar")
            return
        encabezado = ("Conversación de Jarvis\n"
                      f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                      + "-" * 40 + "\n\n")
        ruta = self.crear_documento_txt(encabezado + contenido + "\n")
        if ruta:
            self._feedback_seleccion("Documento guardado")
            self._agregar_chat("Jarvis", f"Documento .txt creado en:\n{ruta}")
        else:
            self._feedback_seleccion("Guardado cancelado")

    # ---------------- Documentos de texto ----------------
    def crear_documento_txt(self, contenido, ruta=None):
        """Crea un documento .txt con el contenido indicado.

        Si no se indica 'ruta', pide al usuario dónde guardarlo (por defecto en
        la carpeta de documentos de Jarvis con un nombre basado en la fecha y
        hora). Devuelve la ruta del archivo creado, o None si cancela o falla.
        """
        contenido = (contenido or "").strip()
        if not contenido:
            return None
        if not ruta:
            try:
                os.makedirs(CARPETA_DOCUMENTOS, exist_ok=True)
            except Exception:
                pass
            nombre_def = f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            ruta = filedialog.asksaveasfilename(
                title="Guardar documento de texto",
                initialdir=os.path.abspath(CARPETA_DOCUMENTOS),
                initialfile=nombre_def,
                defaultextension=".txt",
                filetypes=[("Documento de texto", "*.txt"),
                           ("Todos los archivos", "*.*")],
            )
            if not ruta:
                return None
        if not ruta.lower().endswith(".txt"):
            ruta += ".txt"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido + "\n")
            return ruta
        except Exception as e:
            print(f"Error creando documento .txt: {e}")
            return None

    # ---------------- Gestión de adjuntos ----------------
    def _crear_ctkimage(self, ruta, max_lado=220):
        """Devuelve un CTkImage escalado conservando la proporción, o None si falla."""
        try:
            with Image.open(ruta) as im:
                im = im.convert("RGBA")
                im.thumbnail((max_lado, max_lado))
                return ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        except Exception as e:
            print(f"No se pudo cargar la imagen {ruta}: {e}")
            return None

    def _adjuntar_archivos(self):
        rutas = filedialog.askopenfilenames(
            title="Adjuntar archivos",
            filetypes=[
                ("Todos los archivos", "*.*"),
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff"),
                ("Documentos", "*.pdf *.docx *.txt *.md *.csv"),
                ("Hojas de cálculo", "*.xlsx *.xlsm"),
            ])
        for ruta in rutas:
            self._agregar_adjunto(ruta)

    def _agregar_adjunto(self, ruta):
        ruta = os.path.abspath(ruta)
        if not os.path.isfile(ruta):
            return
        if any(a["ruta"] == ruta for a in self.adjuntos):
            return
        ext = os.path.splitext(ruta)[1].lower()
        tipo = "imagen" if ext in EXT_IMAGEN else "archivo"
        self.adjuntos.append({"ruta": ruta, "nombre": os.path.basename(ruta), "tipo": tipo})
        self._actualizar_adjuntos_ui()

    def _quitar_adjunto(self, ruta):
        ruta = os.path.abspath(ruta)
        self.adjuntos = [a for a in self.adjuntos if a["ruta"] != ruta]
        self._actualizar_adjuntos_ui()

    def _limpiar_adjuntos(self):
        self.adjuntos = []
        self._actualizar_adjuntos_ui()

    def _actualizar_adjuntos_ui(self):
        for w in self.adjuntos_frame.winfo_children():
            w.destroy()
        # La fila de chips solo reserva espacio si hay adjuntos: un CTkFrame vacío
        # mantiene 200 px de alto y cortaría el área visible del chat.
        if not self.adjuntos:
            self.adjuntos_frame.pack_forget()
            return
        try:
            self.adjuntos_frame.pack(fill="x", before=self.caja_input)
        except Exception:
            self.adjuntos_frame.pack(fill="x")
        for adj in self.adjuntos:
            chip = ctk.CTkFrame(self.adjuntos_frame, fg_color=COLOR_TARJETA,
                                corner_radius=12, border_width=1, border_color=COLOR_BORDE)
            chip.pack(side="left", padx=(0, 8), pady=(0, 8))

            if adj["tipo"] == "imagen":
                img = self._crear_ctkimage(adj["ruta"], max_lado=26)
                if img is not None:
                    lbl_mini = ctk.CTkLabel(chip, text="", image=img)
                    lbl_mini._ctk_image = img
                    lbl_mini.pack(side="left", padx=(6, 4), pady=5)

            icono = "" if adj["tipo"] == "imagen" else "\U0001F4C4 "
            nombre = adj["nombre"]
            if len(nombre) > 22:
                nombre = nombre[:19] + "..."
            ctk.CTkLabel(chip, text=f"{icono}{nombre}", font=(FUENTE_UI, 11),
                         text_color=COLOR_TEXTO).pack(side="left", padx=(6, 4), pady=5)

            ctk.CTkButton(chip, text="\u2715", width=20, height=20, corner_radius=10,
                          fg_color="transparent", hover_color=COLOR_ACENTO_HOVER,
                          text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 11),
                          command=lambda r=adj["ruta"]: self._quitar_adjunto(r)).pack(
                              side="left", padx=(0, 6), pady=5)

    def _pegar_portapapeles(self, event=None):
        """Procesa el pegado (Ctrl+V).

        - Imágenes y archivos copiados se adjuntan a la conversación.
        - El texto corto se pega con normalidad en el campo de entrada.
        - El texto muy largo se guarda como documento adjunto (.txt): insertar
          miles de caracteres en el Entry de Tk es O(n²) y congelaba la interfaz.
        """
        # 1) Archivos o imágenes del portapapeles (vía Pillow)
        datos = None
        try:
            from PIL import ImageGrab
            datos = ImageGrab.grabclipboard()
        except Exception:
            datos = None

        # Lista de rutas de archivos copiados desde el Explorador
        if isinstance(datos, list):
            agregado = False
            for ruta in datos:
                if os.path.isfile(ruta):
                    self._agregar_adjunto(ruta)
                    agregado = True
            if agregado:
                return "break"
            datos = None

        # Imagen (captura de pantalla o copiada al portapapeles)
        if datos is not None and not isinstance(datos, str):
            try:
                os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)
                nombre = f"pegado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                ruta = os.path.join(CARPETA_ADJUNTOS, nombre)
                datos.save(ruta, "PNG")
                self._agregar_adjunto(ruta)
                return "break"
            except Exception as e:
                print(f"No se pudo guardar la imagen del portapapeles: {e}")
                datos = None

        # 2) Texto del portapapeles
        texto = datos if isinstance(datos, str) else None
        if texto is None:
            try:
                texto = self.clipboard_get()
            except Exception:
                texto = None  # no hay texto: el pegado normal decide

        if texto and len(texto) > UMBRAL_PEGADO_TEXTO:
            ruta = self._guardar_texto_pegado(texto)
            if ruta:
                self._agregar_adjunto(ruta)
                self._aviso_input(
                    f"Texto largo ({len(texto):,} caracteres) adjuntado como "
                    f"{os.path.basename(ruta)}")
                print(f"Texto pegado adjuntado como documento: {ruta}")
                return "break"
        return None  # texto corto: continúa el pegado normal del campo

    def _guardar_texto_pegado(self, texto):
        """Guarda un texto pegado como archivo .txt dentro de la carpeta de adjuntos."""
        try:
            os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)
            nombre = f"texto_pegado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            ruta = os.path.join(CARPETA_ADJUNTOS, nombre)
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(texto)
            return ruta
        except Exception as e:
            print(f"No se pudo guardar el texto pegado: {e}")
            return None

    def _aviso_input(self, mensaje):
        """Muestra un aviso temporal bajo el campo de entrada (se oculta solo)."""
        self._ocultar_aviso()
        try:
            self._lbl_aviso = ctk.CTkLabel(self.barra_input, text=mensaje,
                                           font=(FUENTE_UI, 11),
                                           text_color=COLOR_ACENTO)
            self._lbl_aviso.pack(pady=(6, 0))
            lbl = self._lbl_aviso
            self.after(3500, lambda: self._ocultar_aviso(lbl))
        except Exception:
            self._lbl_aviso = None

    def _ocultar_aviso(self, lbl=None):
        """Elimina el aviso temporal; si se indica 'lbl' solo si sigue siendo el actual."""
        actual = getattr(self, "_lbl_aviso", None)
        if actual is None:
            return
        if lbl is not None and lbl is not actual:
            return
        try:
            actual.destroy()
        except Exception:
            pass
        self._lbl_aviso = None

    # ---------------- Extracción de contenido de los adjuntos ----------------
    def _extraer_contenido(self, ruta):
        """Devuelve el texto/contenido extraído de un archivo para enviarlo a la IA."""
        ext = os.path.splitext(ruta)[1].lower()
        nombre = os.path.basename(ruta)
        try:
            if ext in EXT_IMAGEN:
                return self._extraer_imagen(ruta)
            if ext in EXT_TEXTO:
                with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()[:MAX_TEXTO_ADJUNTO]
            if ext == ".pdf":
                return self._extraer_pdf(ruta)
            if ext == ".docx":
                return self._extraer_docx(ruta)
            if ext in (".xlsx", ".xlsm"):
                return self._extraer_xlsx(ruta)
            if ext in (".pptx", ".pptm", ".potx"):
                return self._extraer_pptx(ruta)
            if ext in (".ppt", ".doc", ".xls"):
                return (f"[Archivo de Office en formato antiguo ({ext}); no se puede "
                        f"extraer su texto. Indica al usuario que lo guarde como "
                        f".pptx/.docx/.xlsx o en PDF.]")
            # Intento final: leerlo como texto plano
            with open(ruta, "r", encoding="utf-8", errors="strict") as f:
                return f.read()[:MAX_TEXTO_ADJUNTO]
        except Exception:
            pass
        try:
            tam = os.path.getsize(ruta)
        except Exception:
            tam = 0
        return f"[Archivo binario no legible como texto: {nombre} ({tam} bytes)]"

    def _extraer_imagen(self, ruta):
        nombre = os.path.basename(ruta)
        info = f"[Imagen: {nombre}]"
        try:
            with Image.open(ruta) as im:
                info = f"[Imagen: {nombre}, formato {im.format}, {im.width}x{im.height}px]"
        except Exception:
            pass
        try:
            texto_ocr = ocr_imagen(ruta) if ocr_motor() else ""
        except Exception as e:
            print(f"No se pudo aplicar OCR a {nombre}: {e}")
            texto_ocr = ""
        if texto_ocr:
            return f"{info}\nTexto detectado en la imagen (OCR):\n{texto_ocr[:MAX_TEXTO_ADJUNTO]}"
        return (f"{info}\n(No se pudo extraer texto de esta imagen. "
                f"El archivo está en: {ruta})")

    def _extraer_pdf(self, ruta):
        try:
            from pypdf import PdfReader
        except Exception:
            try:
                from PyPDF2 import PdfReader
            except Exception:
                return (f"[PDF adjunto: {os.path.basename(ruta)}. "
                        "Instala 'pypdf' para extraer su texto.]")
        try:
            lector = PdfReader(ruta)
            partes = [(pag.extract_text() or "") for pag in lector.pages[:30]]
            return "\n".join(partes)[:MAX_TEXTO_ADJUNTO] or "[PDF sin texto extraíble]"
        except Exception as e:
            return f"[No se pudo leer el PDF: {e}]"

    def _extraer_docx(self, ruta):
        try:
            import docx
        except Exception:
            return (f"[Documento Word: {os.path.basename(ruta)}. "
                    "Instala 'python-docx' para extraer su texto.]")
        try:
            doc = docx.Document(ruta)
            return "\n".join(p.text for p in doc.paragraphs)[:MAX_TEXTO_ADJUNTO]
        except Exception as e:
            return f"[No se pudo leer el documento Word: {e}]"

    def _extraer_xlsx(self, ruta):
        try:
            import openpyxl
        except Exception:
            return (f"[Hoja de cálculo: {os.path.basename(ruta)}. "
                    "Instala 'openpyxl' para extraer su contenido.]")
        try:
            wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
            partes = []
            for hoja in wb.worksheets:
                partes.append(f"# Hoja: {hoja.title}")
                for i, fila in enumerate(hoja.iter_rows(values_only=True)):
                    if i > 300:
                        partes.append("... (truncado)")
                        break
                    partes.append(" | ".join("" if c is None else str(c) for c in fila))
            return "\n".join(partes)[:MAX_TEXTO_ADJUNTO]
        except Exception as e:
            return f"[No se pudo leer la hoja de cálculo: {e}]"

    def _extraer_pptx(self, ruta):
        try:
            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE
        except Exception:
            return (f"[Presentación: {os.path.basename(ruta)}. "
                    "Instala 'python-pptx' para extraer su contenido.]")
        try:
            prs = Presentation(ruta)
        except Exception as e:
            return f"[No se pudo leer la presentación: {e}]"

        def _texto_formas(formas):
            """Recorre las formas (incluidas las agrupadas) y devuelve sus textos."""
            lineas = []
            for forma in formas:
                try:
                    if forma.shape_type == MSO_SHAPE_TYPE.GROUP:
                        lineas.extend(_texto_formas(forma.shapes))
                        continue
                except Exception:
                    pass
                if getattr(forma, "has_table", False) and forma.has_table:
                    for fila in forma.table.rows:
                        celdas = [c.text.strip() for c in fila.cells]
                        if any(celdas):
                            lineas.append(" | ".join(celdas))
                    continue
                try:
                    if forma.has_text_frame:
                        txt = forma.text_frame.text.strip()
                        if txt:
                            lineas.append(txt)
                except Exception:
                    pass
            return lineas

        partes = []
        for i, slide in enumerate(prs.slides, start=1):
            if i > 60:
                partes.append("... (se omitieron las diapositivas restantes)")
                break
            lineas = _texto_formas(slide.shapes)
            try:
                notas = slide.notes_slide.notes_text_frame.text.strip()
            except Exception:
                notas = ""
            bloque = f"# Diapositiva {i}"
            if lineas:
                bloque += "\n" + "\n".join(lineas)
            if notas:
                bloque += f"\n[Notas: {notas}]"
            partes.append(bloque)
        contenido = "\n\n".join(partes).strip()
        return contenido[:MAX_TEXTO_ADJUNTO] or "[Presentación sin texto extraíble]"

    def _construir_prompt(self, texto, adjuntos):
        """Combina el texto del usuario con el contenido extraído de los adjuntos."""
        if not adjuntos:
            return texto
        bloques = [f"--- Archivo adjunto: {a['nombre']} ---\n{self._extraer_contenido(a['ruta'])}"
                   for a in adjuntos]
        encabezado = texto.strip() or "Analiza el/los archivo(s) adjunto(s)."
        return (f"{encabezado}\n\nEl usuario adjuntó los siguientes archivos; "
                "ten en cuenta su contenido al responder:\n\n" + "\n\n".join(bloques))

    def _guardar_regla_si_aplica(self, texto):
        """Guarda una regla permanente si el mensaje la declara de forma explícita.

        Se reconocen los prefijos 'regla:' y '/regla' (p. ej. 'regla: las tareas
        van al padre 174080'). Devuelve True si se guardó una regla.
        """
        t = (texto or "").strip()
        bajo = t.lower()
        if bajo.startswith("/regla"):
            regla = t[len("/regla"):].lstrip(": ").strip()
        elif bajo.startswith("regla:"):
            regla = t[len("regla:"):].strip()
        else:
            return False
        if not regla:
            return False
        self.system.productivity.agregar_regla(regla)
        print(f"Regla permanente guardada: {regla}")
        return True

    def _scroll_final(self):
        """Desplaza la conversación al final recalculando antes la región de scroll.

        Recalcular la región evita que, tras insertar muchas burbujas de forma
        síncrona (p. ej. al abrir una conversación), el scroll use una geometría
        obsoleta y deje los mensajes fuera de la vista (chat en blanco)."""
        try:
            canvas = self.chat_scroll._parent_canvas
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(1.0)
            self._pegado_abajo = True
        except Exception:
            pass

    def _scroll_actualizado(self, first, last):
        """Registra si el final del chat está a la vista (lo llama el lienzo).

        Sustituye al yscrollcommand de CTkScrollableFrame conservando su trabajo
        (mover la barra lateral) y recuerda la posición para reanclar el final
        cuando cambia el tamaño de la vista."""
        try:
            self._pegado_abajo = float(last) >= 0.999
        except Exception:
            self._pegado_abajo = True
        try:
            self.chat_scroll._scrollbar.set(first, last)
        except Exception:
            pass

    def _chat_redimensionado(self, event=None):
        """Reancla el final de la conversación cuando cambia el tamaño de la vista.

        Sin esto, al encoger o maximizar la ventana el lienzo cambia de alto y los
        últimos mensajes quedan por debajo del borde visible (el chat parece
        cortado). Solo se reancla si el usuario estaba viendo el final, para no
        arrastrar la vista mientras lee mensajes anteriores."""
        if not self.chat_activo or not self._pegado_abajo:
            return
        # En diferido: no conviene reconfigurar el lienzo dentro de su <Configure>
        # (llegan varios eventos seguidos hasta que la ventana tiene su tamaño final).
        self.after_idle(self._scroll_final)

    def _mostrar_pensando(self, activo):
        self._procesando = activo
        if activo:
            # Tarea nueva: pasos y reloj desde cero.
            self._pasos = []
            self._tarea_inicio = time.monotonic()
            if self._ind_pensando is None:
                # La tarjeta de trabajo: punto que late + reloj + los pasos que van
                # cayendo. Su borde lleva un toque de acento (está activa).
                self._ind_pensando = ctk.CTkFrame(
                    self.chat_scroll, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                    border_width=1,
                    border_color=_mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.45))
                cabecera = ctk.CTkFrame(self._ind_pensando, fg_color="transparent")
                cabecera.pack(fill="x")
                self._lbl_pulso = ctk.CTkLabel(cabecera, text="\u25cf",
                                               font=(FUENTE_UI, 13), text_color=COLOR_ACENTO)
                self._lbl_pulso.pack(side="left", padx=(16, 6), pady=(10, 4))
                self._lbl_pensando = ctk.CTkLabel(cabecera,
                                                  text="Jarvis está trabajando",
                                                  font=(FUENTE_UI, 12, "italic"),
                                                  text_color=COLOR_TEXTO_SUAVE)
                self._lbl_pensando.pack(side="left", pady=(10, 4))
                # Aquí van cayendo los pasos: es la respuesta a "¿y ahora qué
                # está haciendo?".
                self._marco_pasos = ctk.CTkFrame(self._ind_pensando,
                                                 fg_color="transparent")
            self._ind_pensando.pack(anchor="w", padx=18, pady=5)
            self._pintar_pasos()
            self.after(30, self._scroll_final)
            self._animar_pensando(0)
        else:
            if self._ind_pensando is not None:
                self._ind_pensando.pack_forget()

    def _animar_pensando(self, i):
        if not self._procesando or self._ind_pensando is None:
            return
        # El reloj importa: ver que el tiempo corre tranquiliza cuando un paso
        # tarda de verdad (una biblioteca grande, un archivo pesado...).
        segundos = int(time.monotonic() - (self._tarea_inicio or time.monotonic()))
        self._lbl_pensando.configure(
            text=f"Jarvis está trabajando{'.' * (i % 4)}  "
                 f"({segundos // 60}:{segundos % 60:02d})")
        # El punto late para que se vea que sigue vivo aunque un paso tarde.
        if self._lbl_pulso is not None:
            try:
                self._lbl_pulso.configure(
                    text="\u25cf" if i % 2 else "\u25cb",
                    text_color=COLOR_ACENTO if i % 2 else COLOR_ACENTO_2)
            except Exception:
                pass
        self.after(400, lambda: self._animar_pensando(i + 1))

    def _progreso_gui(self, texto, tipo):
        """Recibe un paso del canal de progreso y lo lleva al hilo de la ventana.

        Lo llaman los hilos de trabajo (SharePoint, la IA, el correo...), así que
        aquí solo se encola: los widgets se tocan en `_anotar_paso`.
        """
        self.after(0, lambda: self._anotar_paso(texto, tipo))

    def _anotar_paso(self, texto, tipo):
        """Apunta un paso de la tarea en curso y repinta el indicador."""
        if not self._procesando:
            return  # pasos de una tarea ya terminada: no hay dónde enseñarlos
        self._pasos.append((tipo, texto))
        del self._pasos[:-12]   # el indicador enseña los últimos: con 12 sobra
        self._pintar_pasos()

    def _pintar_pasos(self):
        """Redibuja los últimos pasos dentro del indicador (hilo de la ventana)."""
        if self._marco_pasos is None:
            return
        for widget in self._marco_pasos.winfo_children():
            widget.destroy()
        visibles = self._pasos[-6:]
        if not visibles:
            self._marco_pasos.pack_forget()
            return
        ancho = self.chat_scroll.winfo_width()
        if ancho <= 1:
            ancho = 700
        for tipo, texto in visibles:
            ctk.CTkLabel(self._marco_pasos,
                         text=f"{MARCAS_PASOS.get(tipo, '·')} {texto}",
                         font=(FUENTE_UI, 11), justify="left", anchor="w",
                         text_color=COLOR_PASOS.get(tipo, COLOR_TEXTO_SUAVE),
                         wraplength=max(280, int(ancho * 0.6))).pack(anchor="w")
        self._marco_pasos.pack(fill="x", padx=16, pady=(0, 10))
        self.after(30, self._scroll_final)

    def _nueva_conversacion(self):
        """Inicia un hilo nuevo: el próximo mensaje creará su propio archivo."""
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        self._ind_pensando = None
        self._lbl_pensando = None
        self._lbl_pulso = None
        self._marco_pasos = None
        self._pasos = []
        self._pegado_abajo = True    # un hilo nuevo se ve desde el final
        self._procesando = False
        self.chat_activo = None
        self._burbujas = []
        self._seleccion = []
        self.conversacion_actual = None
        self._limpiar_adjuntos()
        self._limpiar_input()       # el hilo nuevo empieza con la caja en blanco
        self._mostrar_vista("chat")
        self._mostrar_estado_chat(False)

    # ---------------- Envío y procesamiento ----------------
    def _enviar_chat(self):
        texto = self._texto_input()
        adjuntos = list(self.adjuntos)
        if not texto and not adjuntos:
            return
        self._limpiar_input()
        self._limpiar_adjuntos()
        self._agregar_chat("Tú", texto, adjuntos)
        self.after(0, lambda: self._mostrar_pensando(True))
        threading.Thread(target=self._procesar_chat, args=(texto, adjuntos),
                         daemon=True).start()

    def _procesar_chat(self, texto, adjuntos=None):
        adjuntos = adjuntos or []
        try:
            self._guardar_regla_si_aplica(texto)
            if adjuntos:
                # Leer un PDF o pasar OCR a una imagen tarda: sin decirlo, el rato
                # hasta que la IA contesta parece que se colgó.
                self.system.progreso.paso("Leyendo el contenido de los adjuntos"
                                          + " (con OCR si son imágenes)")
            prompt = self._construir_prompt(texto, adjuntos)
            respuesta = self._procesar_mensaje(prompt)
        except Exception as e:
            respuesta = f"Ocurrió un error al procesar tu mensaje: {e}"
        finally:
            self.after(0, lambda: self._mostrar_pensando(False))
        if respuesta:
            self._agregar_chat("Jarvis", respuesta)

    def _procesar_mensaje(self, texto):
        """Procesa un mensaje de usuario (voz o texto) y devuelve la respuesta final."""
        # El primer paso de cualquier mensaje: la IA decide qué hacer (es lo que
        # se ve mientras el indicador no tiene nada más que contar).
        self.system.progreso.paso("Pensando con la IA qué hacer…")
        respuesta_texto, comando_accion = self.brain.procesar_mensaje(texto)
        resultado = None
        if comando_accion:
            resultado = self.system.ejecutar_comando(comando_accion)
            if comando_accion.strip().upper() == "SISTEMA|APAGAR":
                self.reproducir_voz("Entendido, cerrando el programa. Hasta luego.")
                self.after(0, self.destroy)
                return "Cerrando el programa..."
        if resultado:
            if str(resultado).startswith("__CONTEXTO__"):
                contexto = str(resultado)[len("__CONTEXTO__"):]
                self.system.progreso.paso("Redactando la respuesta con la IA…")
                return self.brain.analizar(contexto) or "No pude procesar la solicitud."
            return str(resultado)
        if respuesta_texto:
            return respuesta_texto
        if comando_accion:
            return ""  # se ejecutó una acción sin texto de respuesta
        return "No entendí eso."

    # ---------------- Apartado de inglés (tutor) ----------------
    def _crear_vista_ingles(self, parent):
        """Monta el apartado del tutor de inglés (se entra con el botón «Inglés»).

        Todo pasa aquí, nunca en el chat: se escribe (o se dicta) el texto en su
        propia caja, se elige qué se quiere que se prepare —lo arma `EnglishTutor`
        con el nivel del alumno y los errores que detecta en local— y la clase se
        pinta en su panel. Las clases las redacta la IA con el mensaje de sistema de
        profesor (`APIBrain.SISTEMA_TUTOR`), que responde largo y en Markdown: cada
        apartado de esa respuesta (✅ Versión corregida, 🔍 Punto por punto, 📚 Para
        entenderlo, ✍️ Practica...) se convierte en una tarjeta con su icono, y los
        ejemplos y ejercicios se ven en monoespaciada.
        """
        cabecera = ctk.CTkFrame(parent, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(16, 4))
        ctk.CTkButton(cabecera, text="\u2039  Volver al chat", width=150, height=34,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, anchor="w", font=(FUENTE_UI, 13),
                      command=lambda: self._mostrar_vista("chat")).pack(side="left")
        # El icono del apartado en su pastilla de acento, como en la barra lateral
        ctk.CTkLabel(cabecera, text="\U0001F393", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(FUENTE_UI, 16)).pack(side="left", padx=(16, 8))
        ctk.CTkLabel(cabecera, text="Clase de inglés",
                     font=(FUENTE_UI, 20, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")
        # El nivel es lo que más se cambia: desplegable con el botón en acento
        ctk.CTkLabel(cabecera, text="\U0001F39A  Nivel", font=(FUENTE_UI, 12),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="right", padx=(0, 8))
        self.menu_ingles_nivel = ctk.CTkOptionMenu(
            cabecera, values=list(NIVELES), width=92, height=34,
            font=(FUENTE_UI, 13, "bold"),
            fg_color=COLOR_TARJETA, button_color=COLOR_ACENTO,
            button_hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_TEXTO,
            dropdown_fg_color=COLOR_TARJETA_ALTA, dropdown_text_color=COLOR_TEXTO,
            dropdown_hover_color=COLOR_HOVER,
            command=self._cambiar_nivel_ingles)
        self.menu_ingles_nivel.pack(side="right")

        # Cómo va el alumno (nivel, prácticas y lo que más se le repite): tarjeta
        # de estado, porque es información de un vistazo y no un párrafo.
        self.marco_ingles_resumen = ctk.CTkFrame(
            parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA, border_width=1,
            border_color=COLOR_BORDE)
        self.marco_ingles_resumen.pack(fill="x", padx=30, pady=(8, 10))
        ctk.CTkLabel(self.marco_ingles_resumen, text="\U0001F4CA", font=(FUENTE_UI, 13),
                     text_color=COLOR_ACENTO).pack(side="left", padx=(14, 8), pady=8)
        self.lbl_ingles_resumen = ctk.CTkLabel(self.marco_ingles_resumen, text="", anchor="w",
                                               justify="left", font=(FUENTE_UI, 12),
                                               text_color=COLOR_TEXTO_SUAVE, wraplength=820)
        self.lbl_ingles_resumen.pack(side="left", padx=(0, 14), pady=8)

        cuerpo = ctk.CTkFrame(parent, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # --- Izquierda: lo que escribes y lo que quieres que te prepare
        izquierda = ctk.CTkFrame(cuerpo, width=336, fg_color="transparent")
        izquierda.pack(side="left", fill="y")
        izquierda.pack_propagate(False)

        caja_texto = self._tarjeta(izquierda, "\u270D", "Tu inglés",
                                   "Escribe (o dicta) aquí tu frase; al corregirla se "
                                   "apuntan tus fallos para el repaso.")
        self.txt_ingles_texto = ctk.CTkTextbox(caja_texto, height=150, fg_color=COLOR_CODIGO,
                                               border_width=1, border_color=COLOR_BORDE,
                                               corner_radius=RADIO_CHIP,
                                               text_color=COLOR_TEXTO, font=(FUENTE_UI, 12),
                                               undo=True, maxundo=200, wrap="word")
        self.txt_ingles_texto.pack(fill="x")
        # Este cuadro también se enciende al escribir en él (es donde se escribe).
        self.txt_ingles_texto.bind(
            "<FocusIn>", lambda e: self.txt_ingles_texto.configure(border_color=COLOR_ACENTO))
        self.txt_ingles_texto.bind(
            "<FocusOut>", lambda e: self.txt_ingles_texto.configure(border_color=COLOR_BORDE))
        # Aquí también se escribe a gusto: los mismos atajos que en el chat.
        self._atajos_caja(self.txt_ingles_texto)

        caja_tareas = self._tarjeta(
            izquierda, "\U0001F3AF", "Qué practicar",
            "El tema solo se usa para explicar, ejercicios y vocabulario.")
        self.entry_ingles_tema = ctk.CTkEntry(caja_tareas, height=34, fg_color=COLOR_CODIGO,
                                              border_color=COLOR_BORDE,
                                              corner_radius=RADIO_CHIP,
                                              text_color=COLOR_TEXTO, font=(FUENTE_UI, 12),
                                              placeholder_text="Tema: p. ej. for y since")
        self.entry_ingles_tema.pack(fill="x")

        cantidades = ctk.CTkFrame(caja_tareas, fg_color="transparent")
        cantidades.pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(cantidades, text="Cuántos (ejercicios o palabras)",
                     font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE).pack(side="left")
        self.menu_ingles_cantidad = ctk.CTkOptionMenu(
            cantidades, values=[str(numero) for numero in range(3, 11)], width=76, height=30,
            font=(FUENTE_UI, 12), fg_color=COLOR_CODIGO, button_color=COLOR_TARJETA_ALTA,
            button_hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            dropdown_fg_color=COLOR_TARJETA_ALTA, dropdown_text_color=COLOR_TEXTO)
        self.menu_ingles_cantidad.set("5")
        self.menu_ingles_cantidad.pack(side="right")

        # Una tarea por botón (en dos columnas), con su icono y su color: la
        # principal en acento (es la que más se usa) y la de borrar en rojo suave.
        rejilla = ctk.CTkFrame(caja_tareas, fg_color="transparent")
        rejilla.pack(fill="x")
        self.botones_ingles = {}
        for indice, (etiqueta, tarea) in enumerate(TAREAS_INGLES):
            principal = tarea == TAREA_INGLES_PRINCIPAL
            peligro = tarea == TAREA_INGLES_PELIGRO
            boton = ctk.CTkButton(
                rejilla, text=etiqueta, font=(FUENTE_UI, 12), height=36,
                corner_radius=RADIO_CHIP, anchor="w",
                fg_color=COLOR_ACENTO if principal else COLOR_TARJETA_ALTA,
                hover_color=COLOR_ACENTO_HOVER if principal else COLOR_HOVER,
                border_width=0 if principal else 1, border_color=COLOR_BORDE,
                text_color=(COLOR_ACENTO_TEXTO if principal
                            else COLOR_PELIGRO if peligro else COLOR_TEXTO),
                command=lambda tarea=tarea: self._accion_ingles(tarea))
            boton.grid(row=indice // 2, column=indice % 2, sticky="ew", padx=2, pady=3)
            self.botones_ingles[tarea] = boton
        rejilla.grid_columnconfigure(0, weight=1)
        rejilla.grid_columnconfigure(1, weight=1)

        # --- Derecha: la clase, en tarjetas (una por apartado de la respuesta)
        derecha = ctk.CTkFrame(cuerpo, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                               border_width=1, border_color=COLOR_BORDE)
        derecha.pack(side="left", fill="both", expand=True, padx=(14, 0))

        fila = ctk.CTkFrame(derecha, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkLabel(fila, text="\U0001F393", font=(FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text="Tu clase", font=(FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.btn_ingles_copiar = ctk.CTkButton(
            fila, text="\U0001F4CB  Copiar", width=96, height=32, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(FUENTE_UI, 12), command=self._copiar_clase_ingles)
        self.btn_ingles_copiar.pack(side="right")
        self.btn_ingles_guardar = ctk.CTkButton(
            fila, text="\U0001F4BE  Guardar en documentos", width=242, height=32,
            corner_radius=RADIO_CHIP, state="disabled", fg_color=COLOR_ACENTO,
            hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
            font=(FUENTE_UI, 12, "bold"), command=self._guardar_clase_ingles)
        self.btn_ingles_guardar.pack(side="right", padx=(0, 8))

        # Qué está pasando, en su propia línea bajo el título: así el nombre de la
        # clase y los botones tienen su sitio y no se recorta ningún texto.
        self.lbl_ingles_estado = ctk.CTkLabel(derecha, text="Listo cuando quieras.",
                                              font=(FUENTE_UI, 11), anchor="w",
                                              text_color=COLOR_TEXTO_SUAVE)
        self.lbl_ingles_estado.pack(fill="x", padx=18, pady=(0, 8))

        # --- Speaking: hablar en inglés (el micrófono y su estado, junto a la clase)
        # Las demás tareas se escriben; esta se dice. El micrófono escucha en inglés,
        # el panel enseña el turno y la réplica se lee en voz alta con voz inglesa.
        self._onda_ingles = None
        self._speaking_activo = False
        self._speaking_tema = ""
        self._ultimo_en_voz = ""
        caja_speaking = ctk.CTkFrame(derecha, fg_color=COLOR_TARJETA_ALTA,
                                     corner_radius=RADIO_TARJETA, border_width=1,
                                     border_color=COLOR_BORDE)
        caja_speaking.pack(fill="x", padx=14, pady=(0, 10))
        self.marco_ingles_mic = ctk.CTkFrame(caja_speaking, fg_color="transparent", width=54,
                                             height=54, corner_radius=27, border_width=2,
                                             border_color=COLOR_BORDE)
        self.marco_ingles_mic.pack(side="left", padx=(12, 10), pady=10)
        self.marco_ingles_mic.pack_propagate(False)
        self.btn_ingles_mic = ctk.CTkButton(
            self.marco_ingles_mic, text="\U0001F3A4", width=44, height=44, corner_radius=22,
            fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
            text_color=COLOR_ACENTO, font=(FUENTE_UI, 17),
            command=self._toggle_speaking)
        self.btn_ingles_mic.pack(expand=True)
        texto_speaking = ctk.CTkFrame(caja_speaking, fg_color="transparent")
        texto_speaking.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(texto_speaking, text="\U0001F5E3  Speaking: habla en inglés",
                     font=(FUENTE_UI, 12, "bold"), text_color=COLOR_TEXTO).pack(anchor="w")
        self.lbl_speaking = ctk.CTkLabel(
            texto_speaking, text="Micrófono apagado: pulsa el micro y contéstame en voz alta.",
            font=(FUENTE_UI, 11), anchor="w", justify="left", wraplength=380,
            text_color=COLOR_TEXTO_SUAVE)
        self.lbl_speaking.pack(anchor="w")
        self.btn_speaking_repetir = ctk.CTkButton(
            caja_speaking, text="\U0001F50A  Repetir", width=104, height=30,
            corner_radius=RADIO_CHIP, state="disabled", fg_color=COLOR_TARJETA,
            hover_color=COLOR_HOVER, border_width=1, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO, font=(FUENTE_UI, 11),
            command=self._repetir_speaking)
        self.btn_speaking_repetir.pack(side="right", padx=(0, 12), pady=10)

        # El panel de la clase: tarjetas apiladas (una por apartado) con su scroll.
        self.scroll_ingles = ctk.CTkScrollableFrame(derecha, fg_color="transparent",
                                                    **BARRA_SCROLL)
        self.scroll_ingles.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self._escribir_clase(AYUDA_INGLES)

    def _escribir_clase(self, texto):
        """Enseña un texto en el panel de la clase (y lo deja listo para copiar).

        El Markdown se trocea por sus títulos: cada apartado se pinta como una
        tarjeta con su icono, y los ejemplos y los ejercicios en monoespaciada.
        """
        self._clase_ingles = str(texto or "")
        self._pintar_clase(self._clase_ingles)
        listos = "normal" if self._clase_ingles else "disabled"
        self.btn_ingles_copiar.configure(state=listos)
        self.btn_ingles_guardar.configure(state=listos)

    def texto_clase_visible(self):
        """Lo que se está viendo en el panel de la clase, en texto plano.

        El Markdown original (lo que se copia y se guarda) vive en `_clase_ingles`;
        esto es lo que hay pintado en las tarjetas, que es lo que comprueban las
        pruebas del apartado.
        """
        trozos = [f"{titulo}\n{area.get('1.0', 'end-1c').strip()}"
                  for titulo, area in getattr(self, "_tarjetas_clase", [])]
        return "\n\n".join(trozos).strip()

    # ---------------- La clase, en tarjetas ----------------
    def _pintar_clase(self, texto):
        """Redibuja el panel de la clase: una tarjeta por apartado del Markdown."""
        for widget in self.scroll_ingles.winfo_children():
            widget.destroy()
        self._tarjetas_clase = []       # [(título, área de texto)] de lo que se ve
        self._marcos_clase = []        # marcos de las tarjetas (para las pruebas)
        for seccion in self._secciones_de_clase(texto):
            self._tarjeta_clase(seccion)
        try:
            self.scroll_ingles._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    @staticmethod
    def _secciones_de_clase(texto):
        """Trocea la clase en apartados: [{'icono', 'titulo', 'lineas'}].

        Los títulos llegan en Markdown («## ✅ Versión corregida»). Lo que venga
        antes del primer título (por ejemplo un aviso del tutor) se enseña igual,
        en su tarjeta de «Tu clase».
        """
        secciones = []
        sueltas = []
        actual = None
        for linea in str(texto or "").splitlines():
            titulo = re.match(r"^\s*#{1,4}\s+(\S.*?)\s*$", linea)
            if titulo:
                icono, nombre = AppGUI._separar_icono(titulo.group(1))
                actual = {"icono": icono, "titulo": nombre, "lineas": []}
                secciones.append(actual)
            elif actual is None:
                sueltas.append(linea)
            else:
                actual["lineas"].append(linea)
        if any(linea.strip() for linea in sueltas):
            secciones.insert(0, {"icono": "\U0001F4DD", "titulo": "Tu clase",
                                 "lineas": sueltas})
        return secciones

    @staticmethod
    def _separar_icono(titulo):
        """Separa el icono del título: «✅ Versión corregida» → («✅», «Versión…»)."""
        partes = str(titulo).strip().split(" ", 1)
        if len(partes) == 2 and partes[0] and not any(c.isalnum() for c in partes[0]):
            return partes[0], partes[1].strip()
        return "\U0001F4CC", str(titulo).strip()

    def _tarjeta_clase(self, seccion):
        """Pinta un apartado de la clase como tarjeta con su icono y su texto.

        La tarjeta de la versión corregida (lo que el alumno se lleva) lleva el
        borde encendido en el color de acento: es la que destaca entre las demás.
        """
        titulo = seccion["titulo"]
        es_correccion = bool(re.search(r"corregid|versi[oó]n", titulo, re.I))
        marco = ctk.CTkFrame(
            self.scroll_ingles, fg_color=COLOR_TARJETA_ALTA, corner_radius=RADIO_TARJETA,
            border_width=1, border_color=COLOR_ACENTO if es_correccion else COLOR_BORDE)
        marco.pack(fill="x", padx=6, pady=(0, 10))
        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(cabecera, text=seccion["icono"], font=(FUENTE_UI, 15),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(cabecera, text=titulo, font=(FUENTE_UI, 13, "bold"),
                     text_color=COLOR_ACENTO if es_correccion else COLOR_TEXTO).pack(
                         side="left", padx=(8, 0))
        if es_correccion:
            ctk.CTkLabel(cabecera, text="listo para copiar", font=(FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE).pack(side="right")
        area = self._area_de_tarjeta(marco, seccion["lineas"])
        if area is not None:
            self._tarjetas_clase.append((titulo, area))
            self._marcos_clase.append({"marco": marco, "icono": seccion["icono"],
                                       "titulo": titulo})

    def _area_de_tarjeta(self, marco, lineas):
        """Pinta las líneas de un apartado de la clase y devuelve su área de texto.

        Se usa un `tk.Text` (y no el de customtkinter) porque permite cambiar la
        tipografía por línea: hace falta para el monoespaciado de los ejemplos y los
        ejercicios, y para las negritas dentro del propio texto.
        """
        if not any(linea.strip() for linea in lineas):
            return None
        area = self._crear_area_markdown(marco, COLOR_TARJETA_ALTA,
                                         alto=min(18, max(2, len(lineas))))
        self._insertar_lineas(area, lineas)
        area.configure(state="disabled")
        area.pack(fill="x", padx=14, pady=(6, 12))
        # El alto se queda con lo que ocupa el texto de verdad, y se recalcula si la
        # ventana cambia de ancho (entonces cambia lo que ocupa cada línea).
        self._ajustar_alto_tarjeta(area)
        area.bind("<Configure>", lambda e, a=area: self._ajustar_alto_tarjeta(a))
        self._permitir_rueda(area, self.scroll_ingles)
        return area

    def _area_markdown_burbuja(self, burbuja, texto, ancho_px):
        """Pinta el mensaje del asistente dentro de su burbuja, con el Markdown puesto.

        Las respuestas llegan en Markdown («**negrita**», listas, bloques de código):
        sin esto se leían los asteriscos tal cual. Se usa el mismo `tk.Text` sin marco
        que el de la clase, pero con un ancho fijo en caracteres (el de la burbuja),
        de modo que el texto se envuelve donde debe y la burbuja crece hacia abajo.
        """
        area = self._crear_area_markdown(burbuja, COLOR_TARJETA, alto=1,
                                         columnas=self._columnas_markdown(ancho_px))
        area.pack(fill="x", padx=14, pady=(4, 12))
        self._insertar_lineas(area, str(texto or "").splitlines())
        area.configure(state="disabled")
        self._ajustar_alto_tarjeta(area, minimo=1, maximo=200)
        area.bind("<Configure>", lambda e, a=area: self._ajustar_alto_tarjeta(a, 1, 200))
        self._permitir_rueda(area, self.chat_scroll)
        return area

    def _crear_area_markdown(self, parent, fondo, alto=2, columnas=None, tam=12):
        """Crea el área de texto donde se pinta el Markdown, con sus etiquetas.

        Es el ladrillo común de las tarjetas de la clase y de las burbujas del chat:
        un `tk.Text` sin marco ni fondo propio (el del contenedor) con las etiquetas
        ya puestas —negrita en el acento, cursiva, título, cita, viñeta y el
        monoespaciado del código y las tablas sobre su propio fondo—.
        """
        ancho = {"width": columnas} if columnas else {}
        area = tk.Text(parent, height=alto, wrap="word", borderwidth=0,
                       highlightthickness=0, bg=fondo, fg=COLOR_TEXTO,
                       font=(FUENTE_UI, tam), padx=0, pady=0, cursor="arrow",
                       spacing1=2, spacing3=2, takefocus=0,
                       selectbackground=_mezclar(fondo, COLOR_ACENTO, 0.35),
                       selectforeground=COLOR_TEXTO, **ancho)
        area.tag_config("fuerte", font=(FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        area.tag_config("cursiva", font=(FUENTE_UI, tam, "italic"))
        area.tag_config("titulo", font=(FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        area.tag_config("cita", font=(FUENTE_UI, tam, "italic"), foreground=COLOR_TEXTO_SUAVE)
        area.tag_config("codigo", font=(FUENTE_MONO, max(9, tam - 1)),
                        foreground=COLOR_CODIGO_TEXTO, background=COLOR_CODIGO,
                        lmargin1=10, lmargin2=10, rmargin=10)
        area.tag_config("vineta", font=(FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        return area

    @staticmethod
    def _columnas_markdown(ancho_px, tam=13):
        """Cuántos caracteres caben en el ancho de la burbuja (para el `tk.Text`).

        El ancho de un `tk.Text` se pide en caracteres, así que se mide el ancho
        real que ocupa una letra con la tipografía de la ventana: así el texto se
        envuelve donde toca y la burbuja queda del ancho justo.
        """
        try:
            medida = tkfont.Font(family=FUENTE_UI, size=tam).measure("n")
        except Exception:
            medida = 8
        return max(24, int(ancho_px / max(4, medida)))

    @staticmethod
    def _ajustar_alto_tarjeta(area, minimo=2, maximo=60):
        """Ajusta el alto del área al texto que ocupa de verdad, según su ancho.

        Se cuentan las líneas *de pantalla* (lo que ocupa el texto ya envuelto) hasta
        «end»: midiendo hasta «end-1c» Tk no cuenta el último renglón partido y el
        final del mensaje quedaba recortado.
        """
        try:
            lineas = area.count("1.0", "end", "displaylines")
            alto = int(lineas[0]) if lineas else 1
        except Exception:
            return
        alto = max(minimo, min(maximo, alto))
        try:
            if int(area.cget("height")) != alto:
                area.configure(height=alto)
        except Exception:
            pass

    @staticmethod
    def _permitir_rueda(widget, marco_scroll):
        """Deja que la rueda siga desplazando el panel aunque el ratón esté encima.

        Un `tk.Text` se queda la rueda para sí mismo; como estas áreas crecen con su
        contenido y no tienen barra propia, el desplazamiento se reenvía al panel.
        """
        def mover(evento):
            try:
                marco_scroll._parent_canvas.yview_scroll(
                    int(-1 * (evento.delta / 40)), "units")
            except Exception:
                pass
            return "break"

        widget.bind("<MouseWheel>", mover)

    def _estado_ingles(self, texto, color=None):
        """Escribe en la línea de estado del apartado qué está pasando."""
        self.lbl_ingles_estado.configure(text=texto, text_color=color or COLOR_TEXTO_SUAVE)

    def _insertar_lineas(self, area, lineas):
        """Escribe las líneas de un apartado aplicando el formato del Markdown.

        - Los bloques entre ``` y las tablas van en monoespaciado sobre fondo oscuro
          (es el inglés que se copia: se tiene que ver como código).
        - Las listas llevan su viñeta y el **texto entre asteriscos** va en negrita
          con el color de acento.
        """
        en_codigo = False
        primera = True
        for linea in lineas:
            if re.match(r"^\s*```", linea):
                en_codigo = not en_codigo
                continue            # las vallas del bloque no se enseñan
            if not primera:
                area.insert("end", "\n")
            primera = False
            if not linea.strip():
                continue
            if (en_codigo or linea.lstrip().startswith("|")
                    or re.match(r"^\s*[-*_]{3,}\s*$", linea)):
                area.insert("end", linea.rstrip(), "codigo")
                continue
            self._insertar_linea(area, linea)

    def _insertar_linea(self, area, linea):
        """Una línea normal: título, cita, viñeta si es lista y formato dentro del texto."""
        titulo = re.match(r"^\s*#{1,6}\s+(\S.*?)\s*$", linea)
        if titulo:
            # Un título que no se troceó en tarjeta (le pasa a los mensajes del chat)
            # se enseña como tal: en negrita y con el color de acento.
            area.insert("end", titulo.group(1), "titulo")
            return
        cita = re.match(r"^\s*>\s?(.*)$", linea)
        if cita:
            self._insertar_texto(area, cita.group(1), "cita")
            return
        sangria = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", linea)
        if sangria:
            numero = sangria.group(2)
            vineta = numero if numero[0].isdigit() else "\u2022"
            area.insert("end", " " * min(len(sangria.group(1)), 4) + f"{vineta} ", "vineta")
            cuerpo = sangria.group(3)
        else:
            area.insert("end", " " * min(len(linea) - len(linea.lstrip()), 4))
            cuerpo = linea.strip()
        self._insertar_texto(area, cuerpo)

    def _insertar_texto(self, area, texto, etiqueta=""):
        """Trocea el texto y lo inserta con su formato (negrita, cursiva, código)."""
        for trozo in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)", texto):
            if not trozo:
                continue
            if trozo.startswith("**") and trozo.endswith("**") and len(trozo) > 4:
                area.insert("end", trozo[2:-2], "fuerte")
            elif trozo.startswith("`") and trozo.endswith("`") and len(trozo) > 2:
                area.insert("end", trozo[1:-1], "codigo")
            elif trozo.startswith("*") and trozo.endswith("*") and len(trozo) > 2:
                area.insert("end", trozo[1:-1], "cursiva")
            elif etiqueta:
                area.insert("end", trozo, etiqueta)
            else:
                area.insert("end", trozo)

    # ---------------- Piezas de interfaz compartidas ----------------
    def _tarjeta(self, parent, icono, titulo, ayuda=None, color_borde=None):
        """Crea una tarjeta con su cabecera (icono + título) y devuelve su interior.

        Es el ladrillo visual de la ventana: fondo elevado, esquinas redondeadas y
        borde suave —o del color de acento si la tarjeta es la protagonista—. Lo que
        se devuelve es el interior, que es donde se meten los controles.
        """
        marco = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=color_borde or COLOR_BORDE)
        marco.pack(fill="x", pady=(0, 12))
        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(cabecera, text=icono, font=(FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(cabecera, text=titulo, font=(FUENTE_UI, 13, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        interior = ctk.CTkFrame(marco, fg_color="transparent")
        interior.pack(fill="x", padx=14, pady=(0, 12))
        if ayuda:
            ctk.CTkLabel(interior, text=ayuda, font=(FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE, anchor="w", justify="left",
                         wraplength=286).pack(anchor="w", pady=(0, 8))
        return interior

    def _actualizar_ingles(self):
        """Refresca la cabecera del apartado con cómo va el alumno."""
        resumen = self.system.ingles.resumen()
        self.menu_ingles_nivel.set(resumen["nivel"])
        partes = [f"Nivel {resumen['nivel']}", f"{resumen['practicas']} prácticas"]
        if resumen["desde"]:
            partes[-1] += f" desde {resumen['desde']}"
        repetidos = resumen["repetidos"]
        if repetidos:
            nombres = ", ".join((datos.get("titulo") or clave) for clave, datos in repetidos[:3])
            partes.append(f"lo que más se te repite: {nombres}")
        else:
            partes.append("todavía sin fallos apuntados")
        self.lbl_ingles_resumen.configure(text=" \u00b7 ".join(partes))

    def _cambiar_nivel_ingles(self, nivel):
        """Fija el nivel del alumno desde el desplegable del apartado."""
        if nivel != self.system.ingles.nivel():
            self.system.ingles.fijar_nivel(nivel)
            self._estado_ingles(f"Nivel {nivel}: corrijo y explico con esa dificultad.")
        self._actualizar_ingles()

    def _accion_ingles(self, tarea):
        """Prepara una tarea del tutor y la trae al apartado (sin tocar el chat).

        `EnglishTutor` devuelve siempre texto: o el *encargo* para la IA (marcado
        con `MARCA_TUTOR`) o un aviso para el alumno («escríbeme algo y te lo
        corrijo»). Los avisos se enseñan tal cual —no gastan IA— y los encargos se
        piden al cerebro con el mensaje de sistema del profesor en un hilo aparte,
        para que la ventana no se quede congelada mientras se escribe la clase.
        """
        tutor = self.system.ingles
        texto = self.txt_ingles_texto.get("1.0", "end").strip()
        tema = self.entry_ingles_tema.get().strip()
        cuantos = self.menu_ingles_cantidad.get()
        if tarea == "speaking":
            # El «speaking» no es una clase escrita: enciende el micrófono del
            # apartado y la charla va turno a turno, hablando (por voz).
            self._toggle_speaking()
            return
        if tarea != "borrar":
            self._ingles_borrar_pendiente = False
        if tarea == "corregir":
            resultado = tutor.corregir(texto)
        elif tarea == "conversar":
            resultado = tutor.conversar(texto)
        elif tarea == "practicar":
            resultado = tutor.practicar(tema, cuantos)
        elif tarea == "explicar":
            resultado = tutor.explicar(tema)
        elif tarea == "vocabulario":
            resultado = tutor.vocabulario(tema, cuantos)
        elif tarea == "repaso":
            resultado = tutor.repaso(cuantos)
        elif tarea == "progreso":
            resultado = tutor.progreso()
        else:                       # borrar el historial: se confirma la segunda vez
            if not self._ingles_borrar_pendiente:
                self._ingles_borrar_pendiente = True
                self._estado_ingles("Pulsa otra vez «Borrar» si de verdad quieres empezar "
                                    "de cero.", COLOR_ACENTO)
                return
            self._ingles_borrar_pendiente = False
            resultado = tutor.progreso("borrar")

        self._actualizar_ingles()
        resultado = str(resultado or "")
        if not resultado.startswith(MARCA_TUTOR):
            self._escribir_clase(resultado)     # aviso del tutor: no hace falta la IA
            self._estado_ingles("Sin nada que pedirle a la IA todavía.")
            return
        self._estado_ingles("Escribiendo tu clase con la IA…")
        threading.Thread(target=self._pedir_clase,
                         args=(resultado[len(MARCA_TUTOR):], ), daemon=True).start()

    def _pedir_clase(self, encargo):
        """Pide la clase a la IA (hilo de trabajo) y la lleva al apartado."""
        try:
            clase = self.brain.analizar_documento(encargo, sistema=APIBrain.SISTEMA_TUTOR)
        except Exception as e:
            clase = ""
            print(f"No pude preparar la clase de inglés: {e}")
        self.after(0, lambda: self._mostrar_clase(clase))

    def _mostrar_clase(self, clase):
        """Pinta en el apartado la clase que acaba de escribir la IA (hilo de Tk)."""
        if not clase:
            self._escribir_clase(
                "No pude preparar la clase de inglés: revisa tu API Key (DeepSeek) en "
                "Ajustes y vuelve a pedírmela.\n\n"
                "La clase es lo único que necesita la IA: tus fallos, el nivel y «Mi "
                "avance» siguen funcionando sin conexión.")
            self._estado_ingles("No hubo respuesta de la IA.", COLOR_ACENTO)
            return
        self._escribir_clase(clase)
        self._estado_ingles(f"Clase lista ({datetime.now().strftime('%H:%M')}).")

    # ---------------- Speaking: hablar en inglés ----------------
    def _toggle_speaking(self):
        """Enciende o apaga el «speaking»: hablar en inglés con el micrófono.

        Mientras está encendido, el apartado escucha en inglés (sin palabra de
        activación: aquí lo que diga el alumno *es* la práctica), pide la charla a
        la IA con lo que se ha oído y lee la réplica en voz alta con voz inglesa.
        """
        if getattr(self, "_speaking_activo", False):
            self._parar_speaking("Micrófono apagado.")
            return
        # Hablar y escuchar a la vez no tiene sentido: la escucha del chat se para.
        if getattr(self, "escuchando", False):
            self.toggle_escucha()
        # El tema se lee aquí, en el hilo de la interfaz: desde el hilo de trabajo no
        # se puede tocar un widget de Tk.
        self._speaking_tema = self.entry_ingles_tema.get().strip()
        self._speaking_activo = True
        self._onda_ingles = 0
        self._pintar_mic_ingles()
        self.after(150, self._pulso_ingles)
        self._estado_speaking("Te escucho… habla en inglés (pulsa otra vez para parar).",
                              COLOR_ACENTO)
        threading.Thread(target=self._bucle_speaking, daemon=True).start()

    def _parar_speaking(self, mensaje=""):
        """Deja de escuchar y apaga el micrófono del apartado."""
        self._speaking_activo = False
        self._onda_ingles = None
        self._pintar_mic_ingles()
        if mensaje:
            self._estado_speaking(mensaje)

    def _pintar_mic_ingles(self):
        """Pinta el micrófono del apartado según esté escuchando o parado."""
        activo = bool(getattr(self, "_speaking_activo", False))
        try:
            self.btn_ingles_mic.configure(
                fg_color=COLOR_ACENTO if activo else COLOR_TARJETA,
                text_color=COLOR_ACENTO_TEXTO if activo else COLOR_ACENTO)
            self.marco_ingles_mic.configure(
                border_color=COLOR_ACENTO if activo else COLOR_BORDE)
        except Exception:
            pass            # la ventana aún no tiene el apartado montado

    def _pulso_ingles(self, paso=0):
        """Late el anillo del micrófono del apartado mientras se está escuchando."""
        if not getattr(self, "_speaking_activo", False) or self._onda_ingles is None:
            self._onda_ingles = None
            return
        tonos = (COLOR_ACENTO, _mezclar(COLOR_ACENTO, COLOR_PANEL, 0.55), COLOR_ACENTO_2)
        try:
            self.marco_ingles_mic.configure(border_color=tonos[paso % len(tonos)])
        except Exception:
            return
        self.after(170, lambda: self._pulso_ingles(paso + 1))

    def _estado_speaking(self, texto, color=None):
        """Escribe en la tarjeta del speaking qué está pasando."""
        try:
            self.lbl_speaking.configure(text=texto, text_color=color or COLOR_TEXTO_SUAVE)
        except Exception:
            pass

    def _bucle_speaking(self):
        """Escucha, corrige y contesta en voz alta (hilo de trabajo).

        Corre hasta que se apaga el micrófono: oye una frase, pide la charla a la IA
        con lo oído, la pinta en el panel y lee en voz alta la réplica en inglés.
        Mientras habla no escucha: si no, se oiría a sí mismo.
        """
        while getattr(self, "_speaking_activo", False):
            frase = self.voice.escuchar_ingles()
            if not getattr(self, "_speaking_activo", False):
                break
            if not frase:
                time.sleep(0.2)   # no se oyó nada: se sigue escuchando, sin girar en vacío
                continue
            self.after(0, lambda f=frase: self._estado_speaking(f"He oído: «{f}»"))
            clase = self._clase_speaking(frase)
            if not clase or not getattr(self, "_speaking_activo", False):
                continue
            en_voz = self._resumir_en_voz(clase)
            self.after(0, lambda f=frase, c=clase, e=en_voz:
                       self._mostrar_speaking(f, c, e))
            if en_voz:
                self.after(0, lambda: self._estado_speaking("Te contesto…", COLOR_ACENTO_2))
                self.reproducir_voz(en_voz, idioma="en")   # se oye por los altavoces
            if getattr(self, "_speaking_activo", False):
                self.after(0, lambda: self._estado_speaking(
                    "Te escucho… habla en inglés.", COLOR_ACENTO))

    def _clase_speaking(self, frase):
        """Pide la charla a la IA con lo que se ha oído (hilo de trabajo)."""
        try:
            encargo = self.system.ingles.speaking(frase, getattr(self, "_speaking_tema", ""))
            if not str(encargo).startswith(MARCA_TUTOR):
                # Aviso del tutor (no hay nada que pedir a la IA): se enseña tal cual.
                self.after(0, lambda t=str(encargo): self._mostrar_speaking(frase, t, ""))
                return ""
            return self.brain.analizar_documento(str(encargo)[len(MARCA_TUTOR):],
                                                 sistema=APIBrain.SISTEMA_TUTOR)
        except Exception as e:
            print(f"No pude preparar la charla de inglés: {e}")
            return ""

    def _mostrar_speaking(self, frase, clase, en_voz=""):
        """Pinta el turno hablado en el panel y deja listo el botón de repetir."""
        self._ultimo_en_voz = str(en_voz or "")
        self._escribir_clase(f"## \U0001F5E3 Tú has dicho\n\n{frase}\n\n{clase}")
        try:
            self.btn_speaking_repetir.configure(
                state="normal" if self._ultimo_en_voz else "disabled")
        except Exception:
            pass
        self._estado_ingles(f"Turno hablado ({datetime.now().strftime('%H:%M')}).")

    def _repetir_speaking(self):
        """Vuelve a decir en voz alta la última réplica en inglés."""
        if not getattr(self, "_ultimo_en_voz", ""):
            return
        self._estado_speaking("Repitiéndolo en voz alta…", COLOR_ACENTO_2)
        threading.Thread(
            target=lambda: self.reproducir_voz(self._ultimo_en_voz, idioma="en"),
            daemon=True).start()

    @staticmethod
    def _resumir_en_voz(clase, titulos=("digo", "r\u00e9plica", "replica", "respuesta",
                                        "reply", "charla", "conversation", "pregunta",
                                        "question", "speaking")):
        """Saca de la clase lo que se dice en voz alta: su réplica en inglés.

        Se lee solo el apartado de la respuesta («💬 Lo que digo yo» y sus sinónimos):
        lo demás es corrección por escrito, y leerlo en voz alta convertiría la charla
        en un examen. Si el tutor no trae ese apartado se lee el primero, y en todos
        los casos se limpia el Markdown (asteriscos, backticks, almohadillas...).
        """
        secciones = AppGUI._secciones_de_clase(clase)
        elegida = None
        for seccion in secciones:
            nombre = seccion["titulo"].lower()
            if any(palabra in nombre for palabra in titulos):
                elegida = seccion
                break
        if elegida is None and secciones:
            elegida = secciones[0]
        lineas = elegida["lineas"] if elegida else str(clase or "").splitlines()
        limpio = re.sub(r"[*`_#>|]", "", " ".join(lineas))
        return " ".join(limpio.split())[:600]

    def _copiar_clase_ingles(self):
        """Copia la clase al portapapeles (para pegarla donde quieras)."""
        if not self._clase_ingles:
            return
        self.clipboard_clear()
        self.clipboard_append(self._clase_ingles)
        self._estado_ingles("Clase copiada al portapapeles.")

    def _guardar_clase_ingles(self):
        """Guarda la clase como .md en la carpeta de documentos de Jarvis."""
        if not self._clase_ingles:
            return
        try:
            os.makedirs(rutas.DOCUMENTOS, exist_ok=True)
            nombre = f"Clase de inglés {datetime.now().strftime('%Y-%m-%d %H-%M')}.md"
            ruta = os.path.join(rutas.DOCUMENTOS, nombre)
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(self._clase_ingles)
        except OSError as e:
            self._estado_ingles(f"No pude guardar la clase: {e}", COLOR_ACENTO)
            return
        self._estado_ingles(f"Clase guardada en {ruta}")

    # ---------------- Vista de ajustes ----------------
    def _crear_vista_ajustes(self, parent):
        cabecera = ctk.CTkFrame(parent, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(16, 10))
        ctk.CTkButton(cabecera, text="\u2039  Volver al chat", width=150, height=34,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, anchor="w", font=(FUENTE_UI, 13),
                      command=lambda: self._mostrar_vista("chat")).pack(side="left")
        ctk.CTkLabel(cabecera, text="\u2699", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(FUENTE_UI, 16)).pack(side="left", padx=(16, 8))
        ctk.CTkLabel(cabecera, text="Voz y Ajustes", font=(FUENTE_UI, 20, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")

        # La voz, en su tarjeta: a la izquierda cómo está y a la derecha el botón,
        # que es lo único que se pulsa aquí.
        marco_voz = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                                 border_width=1, border_color=COLOR_BORDE)
        marco_voz.pack(fill="x", padx=30, pady=(0, 14))
        ctk.CTkLabel(marco_voz, text="\U0001F3A4  Escucha por voz",
                     font=(FUENTE_UI, 13, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(16, 10), pady=16)
        self.lbl_estado = ctk.CTkLabel(marco_voz, text="Estado: Inactivo",
                                       text_color=COLOR_TEXTO_SUAVE, font=(FUENTE_UI, 13))
        self.lbl_estado.pack(side="left", pady=16)
        self.btn_toggle = ctk.CTkButton(marco_voz, text="\U0001F3A4  Iniciar Escucha",
                                        command=self.toggle_escucha, fg_color=COLOR_ACENTO,
                                        hover_color=COLOR_ACENTO_HOVER,
                                        text_color=COLOR_ACENTO_TEXTO, corner_radius=RADIO_CHIP,
                                        height=40, width=236, font=(FUENTE_UI, 13, "bold"))
        self.btn_toggle.pack(side="right", padx=16, pady=10)

        # Marco de ajustes: una tarjeta con sus apartados, cada uno con su icono.
        self.frame_config = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA,
                                         corner_radius=RADIO_TARJETA,
                                         border_width=1, border_color=COLOR_BORDE)
        self.frame_config.pack(fill="both", expand=True, padx=30, pady=(0, 26))

        # Lo primero: cómo te llamas. Jarvis no lo adivina de la sesión de Windows
        # (eso ponía «coutt»): lo aprende aquí y lo lleva en el mensaje de sistema,
        # así que lo recuerda en todas las conversaciones.
        self._titulo_config("\U0001F464", "Tu nombre")
        self._campo_config(self.frame_config,
                           "Tu nombre (el asistente te llama así):",
                           "entry_usuario", pady_top=(4, 4))
        ctk.CTkLabel(
            self.frame_config,
            text="Se guarda en Jarvis y viaja en cada consulta, para que el asistente lo "
                 "recuerde y se dirija a ti por tu nombre. El nombre de la sesión de "
                 "Windows no se usa.",
            font=(FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE, anchor="w",
            justify="left", wraplength=700).pack(anchor="w", padx=18, pady=(0, 6))

        self._titulo_config("\U0001F511", "La IA que escribe las clases y tu voz")
        self._campo_config(self.frame_config, "DeepSeek API Key:",
                           "entry_api", show="*", pady_top=(4, 4))
        self._campo_config(self.frame_config, "Nombre del Asistente (Wake Word):",
                           "entry_nombre")
        self._campo_config(self.frame_config, "Ruta Modelo RVC (.pth):", "entry_rvc")

        # Matriz en la nube: botones, cada uno con su propio diálogo de configuración
        self._titulo_config("\u2601", "Matriz en la nube (Excel + Azure DevOps)")
        frame_nube = ctk.CTkFrame(self.frame_config, fg_color="transparent")
        frame_nube.pack(fill="x", padx=18, pady=(0, 6))
        self.btn_cfg_ado = ctk.CTkButton(
            frame_nube, text="Configurar Azure DevOps", corner_radius=RADIO_CHIP,
            command=self._abrir_config_azure, fg_color=COLOR_TARJETA_ALTA,
            hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, height=38,
            font=(FUENTE_UI, 12))
        self.btn_cfg_ado.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_cfg_excel = ctk.CTkButton(
            frame_nube, text="Excel (archivo o URL)",
            command=self._abrir_config_excel, fg_color=COLOR_ACENTO,
            hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO, height=36,
            font=(FUENTE_UI, 12, "bold"))
        self.btn_cfg_excel.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.lbl_nube_excel = ctk.CTkLabel(self.frame_config,
                                           text="Excel: sin configurar",
                                           text_color=COLOR_TEXTO_SUAVE,
                                           font=(FUENTE_UI, 11), anchor="w",
                                           justify="left", wraplength=620)
        self.lbl_nube_excel.pack(anchor="w", padx=18, pady=(4, 2))
        self.lbl_nube_ado = ctk.CTkLabel(self.frame_config,
                                         text="Azure DevOps: sin configurar",
                                         text_color=COLOR_TEXTO_SUAVE,
                                         font=(FUENTE_UI, 11), anchor="w",
                                         justify="left", wraplength=620)
        self.lbl_nube_ado.pack(anchor="w", padx=18, pady=(0, 10))

        # Correo (Outlook nuevo / Microsoft 365): se conecta una sola vez con un
        # código de Microsoft; no hace falta contraseña ni Outlook clásico.
        self._titulo_config("\u2709", "Correo (Outlook nuevo / Microsoft 365)")
        frame_correo = ctk.CTkFrame(self.frame_config, fg_color="transparent")
        frame_correo.pack(fill="x", padx=18, pady=(0, 6))
        self.btn_conectar_correo = ctk.CTkButton(
            frame_correo, text="Conectar correo", command=self._conectar_correo,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER, corner_radius=RADIO_CHIP,
            text_color=COLOR_ACENTO_TEXTO, height=38, font=(FUENTE_UI, 12, "bold"))
        self.btn_conectar_correo.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_desconectar_correo = ctk.CTkButton(
            frame_correo, text="Desconectar", command=self._desconectar_correo,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, height=36,
            font=(FUENTE_UI, 12, "bold"))
        self.btn_desconectar_correo.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.lbl_correo = ctk.CTkLabel(self.frame_config, text="Correo: sin conectar",
                                       text_color=COLOR_TEXTO_SUAVE,
                                       font=(FUENTE_UI, 11), anchor="w",
                                       justify="left", wraplength=620)
        self.lbl_correo.pack(anchor="w", padx=18, pady=(4, 10))

        # Música (Spotify): se conecta una sola vez y, a partir de ahí, el asistente
        # pone las canciones por la API oficial: sin abrir ventanas ni tocar el teclado,
        # así que se puede pedir una canción con un juego en primer plano.
        self._titulo_config("\U0001F3B5", "Música (Spotify, sin tocar el teclado)")
        frame_spotify = ctk.CTkFrame(self.frame_config, fg_color="transparent")
        frame_spotify.pack(fill="x", padx=18, pady=(0, 6))
        self.btn_conectar_spotify = ctk.CTkButton(
            frame_spotify, text="Conectar Spotify", command=self._conectar_spotify,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            corner_radius=RADIO_CHIP, text_color=COLOR_ACENTO_TEXTO, height=38,
            font=(FUENTE_UI, 12, "bold"))
        self.btn_conectar_spotify.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_cfg_spotify = ctk.CTkButton(
            frame_spotify, text="Client ID", command=self._abrir_config_spotify,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            height=36, font=(FUENTE_UI, 12))
        self.btn_cfg_spotify.pack(side="left", expand=True, fill="x", padx=6)
        self.btn_desconectar_spotify = ctk.CTkButton(
            frame_spotify, text="Desconectar", command=self._desconectar_spotify,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            height=36, font=(FUENTE_UI, 12))
        self.btn_desconectar_spotify.pack(side="left", expand=True, fill="x",
                                          padx=(6, 0))

        self.lbl_spotify = ctk.CTkLabel(self.frame_config, text="Spotify: sin conectar",
                                        text_color=COLOR_TEXTO_SUAVE,
                                        font=(FUENTE_UI, 11), anchor="w",
                                        justify="left", wraplength=620)
        self.lbl_spotify.pack(anchor="w", padx=18, pady=(4, 10))

        self.btn_guardar = ctk.CTkButton(self.frame_config,
                                         text="\U0001F4BE  Guardar configuración",
                                         command=self.guardar_config, fg_color=COLOR_ACENTO,
                                         hover_color=COLOR_ACENTO_HOVER, corner_radius=RADIO_CHIP,
                                         text_color=COLOR_ACENTO_TEXTO,
                                         height=40, width=250, font=(FUENTE_UI, 13, "bold"))
        self.btn_guardar.pack(pady=(10, 14))

        # Reglas permanentes (memoria del asistente: se añaden a cada consulta)
        self._titulo_config("\U0001F4CC", "Reglas permanentes (Jarvis las recuerda siempre)")
        self.txt_reglas = ctk.CTkTextbox(self.frame_config, height=110,
                                         fg_color=COLOR_CODIGO, border_width=1,
                                         border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
                                         text_color=COLOR_TEXTO, undo=True, maxundo=200,
                                         font=(FUENTE_UI, 12), wrap="word")
        self.txt_reglas.pack(padx=18, fill="x")
        # Las reglas también se escriben a mano: los mismos atajos que en el chat.
        self._atajos_caja(self.txt_reglas)
        self.btn_guardar_reglas = ctk.CTkButton(
            self.frame_config, text="Guardar reglas", command=self._guardar_reglas_ui,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_TEXTO, height=36, font=(FUENTE_UI, 12))
        self.btn_guardar_reglas.pack(pady=(10, 18))

    def _titulo_config(self, icono, texto):
        """Cabecera de un apartado dentro de la tarjeta de ajustes (icono + título)."""
        ctk.CTkLabel(self.frame_config, text=f"{icono}  {texto}",
                     text_color=COLOR_ACENTO, font=(FUENTE_UI, 12, "bold")).pack(
                         anchor="w", padx=18, pady=(16, 4))

    def _campo_config(self, parent, etiqueta, nombre_attr, show=None, pady_top=(14, 4)):
        ctk.CTkLabel(parent, text=etiqueta, text_color=COLOR_TEXTO,
                     font=(FUENTE_UI, 12)).pack(anchor="w", padx=18, pady=pady_top)
        entrada = ctk.CTkEntry(parent, show=show, fg_color=COLOR_CODIGO,
                               border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
                               text_color=COLOR_TEXTO, height=36, font=(FUENTE_UI, 12))
        entrada.pack(padx=18, pady=(0, 10), fill="x")
        setattr(self, nombre_attr, entrada)

    # ---------------- Matriz en la nube: configuración con botones ----------------
    def _leer_config_json(self):
        """Devuelve el diccionario completo de config_usuario.json."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"Error leyendo configuración: {e}")
        return {}

    def _escribir_config_json(self, data):
        """Escribe config_usuario.json (creando la carpeta si hace falta)."""
        carpeta = os.path.dirname(self.config_path)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _actualizar_estado_nube(self):
        """Refresca las etiquetas que resumen la configuración de la matriz en la nube."""
        cfg = self._leer_config_json()
        matriz = cfg.get("matriz") if isinstance(cfg.get("matriz"), dict) else {}
        azure = cfg.get("azure_devops") if isinstance(cfg.get("azure_devops"), dict) else {}

        archivo = (matriz.get("excel_path") or "").strip()
        url = (matriz.get("excel_url") or "").strip()
        sincronizada = (matriz.get("excel_sync_dir") or "").strip()
        if archivo:
            texto_excel = f"Excel: {os.path.basename(archivo)}\n{archivo}"
        elif url:
            texto_excel = f"Excel (URL): {url}"
            if sincronizada:
                texto_excel += (f"\ncopia en la carpeta sincronizada (se sube a "
                                f"SharePoint): {sincronizada}")
            else:
                texto_excel += ("\ncopia local: los cambios NO se suben a SharePoint "
                                "(indica la carpeta sincronizada en el botón del Excel)")
        else:
            texto_excel = ("Excel: sin configurar\n"
                           f"(se usará {os.path.join(rutas.MATRICES, 'Matriz.xlsx')})")

        org = (azure.get("org") or "").strip()
        proyecto = (azure.get("project") or "").strip()
        if org or proyecto:
            token = ((azure.get("pat") or "").strip()
                     or os.environ.get("AZURE_DEVOPS_PAT", "").strip())
            texto_ado = (f"Azure DevOps: {org or '(sin organización)'} · "
                         f"{proyecto or '(sin proyecto)'} · "
                         f"{'token OK' if token else 'falta el token (PAT)'}")
        else:
            texto_ado = "Azure DevOps: sin configurar"

        if hasattr(self, "lbl_nube_excel"):
            self.lbl_nube_excel.configure(text=texto_excel)
        if hasattr(self, "lbl_nube_ado"):
            self.lbl_nube_ado.configure(text=texto_ado)

    def _actualizar_estado_correo(self):
        """Refresca la etiqueta que resume la conexión del correo."""
        cfg = self._leer_config_json()
        correo = cfg.get("correo") if isinstance(cfg.get("correo"), dict) else {}
        cuenta = (correo.get("cuenta") or "").strip()
        conectando = getattr(self, "_conectando_correo", False)
        if correo.get("token"):
            texto = f"Correo conectado: {cuenta}" if cuenta else "Correo conectado."
            if not cuenta:
                texto += " (pulsa 'Conectar correo' para comprobar la cuenta)"
            texto += ("\nJarvis puede leerlo, resumirlo y dejar los borradores "
                      "preparados; nunca envía nada por su cuenta.")
            color = COLOR_OK
        elif conectando:
            return                      # hay una conexión en curso: no pisamos el código
        else:
            texto = ("Correo: sin conectar\nSe conecta una sola vez con un código de "
                     "Microsoft (el navegador se abre solo); no hace falta contraseña.")
            color = COLOR_TEXTO_SUAVE
        if hasattr(self, "lbl_correo"):
            self.lbl_correo.configure(text=texto, text_color=color)

    def _conectar_correo(self):
        """Conecta el correo con el código de dispositivo, sin bloquear la ventana."""
        if getattr(self, "_conectando_correo", False):
            return
        self._conectando_correo = True
        self.btn_conectar_correo.configure(text="Esperando el código...", state="disabled")
        self.lbl_correo.configure(text="Preparando la conexión con Microsoft...",
                                  text_color=COLOR_TEXTO)
        estado = {"abierto": False}

        def avisar(texto):
            """Enseña el código (acumulando líneas) y abre el navegador una vez."""
            if not estado["abierto"] and re.search(r"código\s+[A-Z0-9][A-Z0-9-]{4,}",
                                                   texto, re.IGNORECASE):
                estado["abierto"] = True
                try:
                    webbrowser.open("https://microsoft.com/devicelogin")
                except Exception as e:
                    print(f"No pude abrir el navegador: {e}")

            def pintar():
                # El código y el tiempo llegan en dos avisos seguidos: se acumulan
                # para que el código no desaparezca de la ventana.
                previo = (self.lbl_correo.cget("text") or "").strip()
                if previo.startswith("Preparando"):
                    previo = ""
                self.lbl_correo.configure(text=(f"{previo}\n{texto}" if previo else texto),
                                          text_color=COLOR_TEXTO)

            self.after(0, pintar)

        def tarea():
            from modules.correo_nube import CorreoNube
            try:
                ok, mensaje = CorreoNube(self.config_path).entrar(avisar=avisar)
            except Exception as e:
                ok, mensaje = False, f"No pude conectar tu correo: {e}"
            self.after(0, lambda: self._correo_resuelto(ok, mensaje))

        threading.Thread(target=tarea, daemon=True).start()

    def _correo_resuelto(self, ok, mensaje):
        """Termina la conexión del correo: pinta el resultado y rearma el botón."""
        self._conectando_correo = False
        self.btn_conectar_correo.configure(text="Conectar correo", state="normal")
        self.lbl_correo.configure(text=mensaje,
                                  text_color=COLOR_OK if ok else COLOR_PELIGRO)

    def _desconectar_correo(self):
        """Olvida la sesión de correo guardada, pidiendo confirmación."""
        cfg = self._leer_config_json()
        correo = cfg.get("correo") if isinstance(cfg.get("correo"), dict) else {}
        if not correo.get("token"):
            self.lbl_correo.configure(text="El correo todavía no está conectado.",
                                      text_color=COLOR_TEXTO_SUAVE)
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Desconectar correo")
        dlg.geometry("470x230")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)
        dlg.after(150, dlg.grab_set)
        ctk.CTkLabel(dlg, text="¿Olvidar la sesión de tu correo?",
                     font=(FUENTE_UI, 15, "bold"), text_color=COLOR_TEXTO).pack(
                         anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(dlg,
                     text=("Jarvis borrará el token guardado y dejará de leer tu correo.\n"
                           "Podrás volver a conectarlo cuando quieras."),
                     font=(FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                     justify="left").pack(anchor="w", padx=24)

        def confirmar():
            from modules.correo_nube import CorreoNube
            correo_nube = CorreoNube(self.config_path)
            correo_nube.salir()
            dlg.destroy()
            self.lbl_correo.configure(
                text="Correo desconectado. Jarvis ya no accede a tu buzón.",
                text_color=COLOR_TEXTO_SUAVE)

        botones = ctk.CTkFrame(dlg, fg_color="transparent")
        botones.pack(pady=(20, 12))
        ctk.CTkButton(botones, text="Desconectar", command=confirmar,
                      fg_color=COLOR_PELIGRO, hover_color=COLOR_PELIGRO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      height=34, font=(FUENTE_UI, 12, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, border_width=1, border_color=COLOR_BORDE,
                      height=34, font=(FUENTE_UI, 12)).pack(side="left", padx=6)

    def _actualizar_estado_spotify(self):
        """Refresca la etiqueta que resume cómo está la conexión de Spotify."""
        cfg = self._leer_config_json()
        spotify = cfg.get("spotify") if isinstance(cfg.get("spotify"), dict) else {}
        cuenta = str(spotify.get("cuenta") or "").strip()
        conectado = bool(spotify.get("token"))
        if conectado:
            quien = f": {cuenta}" if cuenta else ""
            if spotify.get("premium"):
                texto = (f"Spotify conectado{quien} (Premium).\nPuedo poner canciones, "
                         "pausar y saltar sin abrir ventanas ni tocar el teclado.")
                color = COLOR_OK
            else:
                texto = (f"Spotify conectado{quien}, pero la cuenta no es Premium.\n"
                         "Spotify no deja controlar la reproducción desde fuera sin "
                         "Premium, así que te dejaré la canción cargada para que le "
                         "des al play.")
                color = COLOR_TEXTO
        else:
            texto = ("Spotify: sin conectar\nSe conecta una sola vez (Client ID "
                     "gratuito y «Aceptar» en el navegador); después las canciones se "
                     "ponen solas, sin abrir ventanas.")
            color = COLOR_TEXTO_SUAVE
        if hasattr(self, "lbl_spotify"):
            self.lbl_spotify.configure(text=texto, text_color=color)

    def _conectar_spotify(self):
        """Conecta Spotify (Client ID + autorizar) sin bloquear la ventana."""
        if getattr(self, "_conectando_spotify", False):
            return
        cliente_id = ""
        try:
            from modules.spotify import Spotify
            cliente_id = Spotify(self.config_path).cliente_id()
        except Exception as e:
            print(f"No pude leer la configuración de Spotify: {e}")
        if not cliente_id:
            # Sin Client ID no hay nada que autorizar: se pide primero.
            self.lbl_spotify.configure(
                text="Falta el Client ID de tu aplicación de Spotify: pégalo aquí y "
                     "vuelvo a intentarlo.", text_color=COLOR_PELIGRO)
            self._abrir_config_spotify(despues=self._conectar_spotify)
            return
        self._conectando_spotify = True
        self.btn_conectar_spotify.configure(text="Esperando a Spotify...",
                                           state="disabled")
        self.lbl_spotify.configure(text="Abriendo el navegador para autorizar...",
                                   text_color=COLOR_TEXTO)

        def avisar(texto):
            """Los avisos del módulo llegan desde otro hilo: se pintan en el suyo."""
            self.after(0, lambda: self.lbl_spotify.configure(
                text=texto, text_color=COLOR_TEXTO))

        def tarea():
            from modules.spotify import Spotify
            try:
                ok, mensaje = Spotify(self.config_path).entrar(avisar=avisar)
            except Exception as e:
                ok, mensaje = False, f"No pude conectar Spotify: {e}"
            self.after(0, lambda: self._spotify_resuelto(ok, mensaje))

        threading.Thread(target=tarea, daemon=True).start()

    def _spotify_resuelto(self, ok, mensaje):
        """Termina la conexión: pinta el resultado y rearma el botón."""
        self._conectando_spotify = False
        self.btn_conectar_spotify.configure(text="Conectar Spotify", state="normal")
        if not ok:
            self.lbl_spotify.configure(text=mensaje, text_color=COLOR_PELIGRO)
            return
        self._actualizar_estado_spotify()
        resumen = self.lbl_spotify.cget("text")
        self.lbl_spotify.configure(text=f"{mensaje}\n{resumen}", text_color=COLOR_OK)

    def _abrir_config_azure(self):
        """Diálogo para configurar Azure DevOps (organización, proyecto, PAT...)."""
        cfg = self._leer_config_json()
        azure = cfg.get("azure_devops") if isinstance(cfg.get("azure_devops"), dict) else {}

        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar Azure DevOps")
        dlg.geometry("640x640")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Azure DevOps (work items)",
                     font=(FUENTE_UI, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(dlg,
                     text=("Genera un PAT en dev.azure.com → icono de usuario → "
                           "Tokens de acceso personal\n(permiso \"Work Items: Read & "
                           "Write\"). No necesitas una API key de administrador."),
                     font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=590).pack(anchor="w", padx=24,
                                                          pady=(0, 10))

        campos = [
            ("Organización (URL)", "org", "https://dev.azure.com/MiOrganizacion"),
            ("Proyecto", "project", "MiProyecto"),
            ("Token de acceso personal (PAT)", "pat", ""),
            ("Tipo de work item", "tipo_item", "Requirement"),
            ("Area Path (opcional)", "area_path", ""),
            ("Iteration Path (opcional)", "iteration_path", ""),
        ]
        entradas = {}
        for etiqueta, clave, pista in campos:
            ctk.CTkLabel(dlg, text=etiqueta, text_color=COLOR_TEXTO,
                         font=(FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(8, 2))
            entrada = ctk.CTkEntry(dlg, fg_color=COLOR_PANEL,
                                   border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
                                   height=34, show="*" if clave == "pat" else None)
            entrada.pack(padx=24, fill="x")
            valor = str(azure.get(clave, "") or "")
            if valor:
                entrada.insert(0, valor)
            elif clave == "tipo_item":
                entrada.insert(0, "Requirement")
            elif pista:
                entrada.configure(placeholder_text=pista)
            entradas[clave] = entrada

        lbl_estado = ctk.CTkLabel(dlg, text="", text_color=COLOR_TEXTO_SUAVE,
                                  font=(FUENTE_UI, 11), justify="left",
                                  wraplength=590)
        lbl_estado.pack(anchor="w", padx=24, pady=(10, 0))

        def _probar():
            datos = {k: e.get().strip() for k, e in entradas.items()}
            lbl_estado.configure(text="Probando conexión...",
                                 text_color=COLOR_TEXTO_SUAVE)
            resultado = {}

            def _worker():
                try:
                    resultado["texto"] = self.system.cloud.probar_azure(
                        datos["org"], datos["project"], datos["pat"])
                except Exception as e:
                    resultado["texto"] = f"No pude conectar: {e}"

            def _revisar():
                """Se ejecuta en el hilo de la interfaz: la prueba va en un hilo aparte."""
                try:
                    if "texto" not in resultado:
                        dlg.after(250, _revisar)
                        return
                    texto = resultado["texto"]
                    color = COLOR_OK if texto.startswith("Conexión") else COLOR_PELIGRO
                    lbl_estado.configure(text=texto, text_color=color)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
            dlg.after(250, _revisar)

        def _guardar():
            datos = {k: e.get().strip() for k, e in entradas.items()}
            if not datos["org"] or not datos["project"]:
                lbl_estado.configure(text="Indica al menos la organización y el proyecto.",
                                     text_color=COLOR_PELIGRO)
                return
            cfg_actual = self._leer_config_json()
            azure_cfg = cfg_actual.get("azure_devops")
            if not isinstance(azure_cfg, dict):
                azure_cfg = {}
            azure_cfg.update(datos)
            cfg_actual["azure_devops"] = azure_cfg
            try:
                self._escribir_config_json(cfg_actual)
            except Exception as e:
                lbl_estado.configure(text=f"No pude guardar: {e}", text_color=COLOR_PELIGRO)
                return
            self._actualizar_estado_nube()
            dlg.destroy()

        frame_botones = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_botones.pack(fill="x", padx=24, pady=16)
        ctk.CTkButton(frame_botones, text="Guardar", command=_guardar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      height=36, font=(FUENTE_UI, 12, "bold")).pack(side="right",
                                                                     padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Probar conexión", command=_probar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=36,
                      font=(FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=36).pack(side="right")

    def _desconectar_spotify(self):
        """Olvida la sesión de Spotify guardada, pidiendo confirmación."""
        cfg = self._leer_config_json()
        spotify = cfg.get("spotify") if isinstance(cfg.get("spotify"), dict) else {}
        if not spotify.get("token"):
            self.lbl_spotify.configure(text="Spotify todavía no está conectado.",
                                       text_color=COLOR_TEXTO_SUAVE)
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Desconectar Spotify")
        dlg.geometry("480x230")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)
        dlg.after(150, dlg.grab_set)
        ctk.CTkLabel(dlg, text="¿Olvidar la sesión de Spotify?",
                     font=(FUENTE_UI, 15, "bold"), text_color=COLOR_TEXTO).pack(
                         anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(dlg,
                     text=("Jarvis borrará el token guardado y volverá a pedir permiso "
                           "la próxima vez.\nLa música seguirá funcionando con el "
                           "reproductor de siempre."),
                     font=(FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                     justify="left").pack(anchor="w", padx=24)

        def confirmar():
            from modules.spotify import Spotify
            try:
                Spotify(self.config_path).salir()
            except Exception as e:
                print(f"No pude olvidar la sesión de Spotify: {e}")
            dlg.destroy()
            self._actualizar_estado_spotify()
            self.lbl_spotify.configure(
                text="Spotify desconectado. Si quieres, puedo volver a conectarlo.",
                text_color=COLOR_TEXTO_SUAVE)

        botones = ctk.CTkFrame(dlg, fg_color="transparent")
        botones.pack(pady=(20, 12))
        ctk.CTkButton(botones, text="Desconectar", command=confirmar,
                      fg_color=COLOR_PELIGRO, hover_color=COLOR_PELIGRO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=34,
                      font=(FUENTE_UI, 12, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, border_width=1, border_color=COLOR_BORDE,
                      height=34, font=(FUENTE_UI, 12)).pack(side="left", padx=6)

    def _abrir_config_spotify(self, despues=None):
        """Diálogo para pegar el Client ID de la aplicación de Spotify.

        Con ``despues`` se encadena la autorización: al guardar se llama a esa función,
        así «Conectar Spotify» sin Client ID pide el dato y sigue solo.
        """
        cfg = self._leer_config_json()
        spotify = cfg.get("spotify") if isinstance(cfg.get("spotify"), dict) else {}
        try:
            from modules.spotify import Spotify
            redireccion = str(spotify.get("redireccion") or Spotify.REDIRECCION)
        except Exception:
            redireccion = "http://127.0.0.1:8888/callback"

        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar Spotify")
        dlg.geometry("700x600")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Música con Spotify (API oficial)",
                     font=(FUENTE_UI, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(dlg,
                     text=("1) Entra en developer.spotify.com/dashboard, pulsa «Create "
                           "app» y marca Web API.\n"
                           f"2) En «Redirect URIs» pega exactamente: {redireccion}\n"
                           "3) Guarda, abre la app que has creado, copia el «Client ID» "
                           "y pégalo aquí.\n"
                           "Luego pulsa «Conectar Spotify» y acepta en el navegador. "
                           "Las canciones necesitan cuenta Premium; con una cuenta "
                           "gratuita Jarvis dejará la canción cargada."),
                     font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24)

        entradas = {}
        for clave, etiqueta, ayuda in (
                ("cliente_id", "Client ID:",
                 "Se copia de tu app de Spotify (no es la contraseña de tu cuenta)."),
                ("dispositivo", "Dispositivo preferido (opcional):",
                 "Parte del nombre del aparato donde quieres que suene (por ejemplo "
                 "«PC-escritorio»). Vacío = el que esté activo.")):
            ctk.CTkLabel(dlg, text=etiqueta, font=(FUENTE_UI, 12),
                         text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(14, 2))
            entrada = ctk.CTkEntry(dlg, height=34, width=620)
            entrada.insert(0, str(spotify.get(clave) or ""))
            entrada.pack(anchor="w", padx=24)
            ctk.CTkLabel(dlg, text=ayuda, font=(FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE, justify="left",
                         wraplength=620).pack(anchor="w", padx=24, pady=(2, 0))
            entradas[clave] = entrada

        lbl_estado = ctk.CTkLabel(dlg, text="", font=(FUENTE_UI, 11),
                                  text_color=COLOR_TEXTO_SUAVE, anchor="w",
                                  justify="left", wraplength=640)
        lbl_estado.pack(anchor="w", padx=24, pady=(10, 0))

        def _guardar():
            datos = {k: e.get().strip() for k, e in entradas.items()}
            if not datos["cliente_id"]:
                lbl_estado.configure(text="Pega el Client ID de tu app de Spotify.",
                                     text_color=COLOR_PELIGRO)
                return
            cfg_actual = self._leer_config_json()
            spotify_cfg = cfg_actual.get("spotify")
            if not isinstance(spotify_cfg, dict):
                spotify_cfg = {}
            spotify_cfg["cliente_id"] = datos["cliente_id"]
            spotify_cfg["dispositivo"] = datos["dispositivo"]
            spotify_cfg["redireccion"] = redireccion
            cfg_actual["spotify"] = spotify_cfg
            try:
                self._escribir_config_json(cfg_actual)
            except Exception as e:
                lbl_estado.configure(text=f"No pude guardar: {e}",
                                     text_color=COLOR_PELIGRO)
                return
            dlg.destroy()
            self._actualizar_estado_spotify()
            if callable(despues):
                despues()

        frame_botones = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_botones.pack(fill="x", padx=24, pady=16)
        ctk.CTkButton(frame_botones, text="Guardar", command=_guardar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=36,
                      font=(FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=36).pack(side="right")

    def _cargar_reglas_ui(self):
        """Vuelca las reglas permanentes guardadas en el editor de la interfaz."""
        if not hasattr(self, "txt_reglas"):
            return
        try:
            reglas = self.system.productivity.leer_reglas()
        except Exception:
            reglas = ""
        self.txt_reglas.delete("1.0", "end")
        if reglas:
            self.txt_reglas.insert("1.0", reglas)
        # Lo cargado es el punto de partida: Ctrl+Z no debe borrar las reglas.
        self.txt_reglas._textbox.edit_reset()

    def _guardar_reglas_ui(self):
        """Guarda el contenido del editor de reglas permanentes."""
        if not hasattr(self, "txt_reglas"):
            return
        contenido = self.txt_reglas.get("1.0", "end").strip()
        ok = self.system.productivity.guardar_reglas(contenido)
        self.btn_guardar_reglas.configure(
            text="Reglas guardadas \u2713" if ok else "Error al guardar")
        self.after(1600, lambda: self.btn_guardar_reglas.configure(
            text="Guardar reglas"))

    # ---------------- Lista de conversaciones (sidebar) ----------------
    def _cargar_conversaciones_sidebar(self):
        if not hasattr(self, "lista_conv"):
            return
        for w in self.lista_conv.winfo_children():
            w.destroy()

        archivos = sorted(glob.glob(os.path.join(rutas.CONVERSACIONES, "historial_chat_*.md")),
                          reverse=True)
        if not archivos:
            ctk.CTkLabel(self.lista_conv, text="Sin conversaciones todavía",
                         font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                         wraplength=210, justify="left").pack(anchor="w", padx=10, pady=6)
            return

        for ruta in archivos:
            fecha = self._fecha_desde_archivo(ruta)
            titulo = self._primer_mensaje(ruta) or "Conversación"
            # Cada conversación es una tarjeta con su icono: la fecha de un vistazo y
            # el primer mensaje como resumen (se lee mucho mejor que una línea larga).
            tarjeta = ctk.CTkFrame(self.lista_conv, fg_color=COLOR_TARJETA,
                                   corner_radius=RADIO_CHIP, border_width=1,
                                   border_color=COLOR_BORDE)
            tarjeta.pack(fill="x", padx=2, pady=3)
            cabecera = ctk.CTkFrame(tarjeta, fg_color="transparent")
            cabecera.pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(cabecera, text="\U0001F4AC", font=(FUENTE_UI, 12),
                         text_color=COLOR_ACENTO).pack(side="left")
            ctk.CTkLabel(cabecera, text=fecha, font=(FUENTE_UI, 10, "bold"),
                         text_color=COLOR_TEXTO_SUAVE).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(tarjeta, text=titulo, font=(FUENTE_UI, 11), anchor="w",
                         justify="left", wraplength=196, text_color=COLOR_TEXTO).pack(
                             anchor="w", padx=10, pady=(2, 9))
            self._vincular_clic(tarjeta, lambda e, r=ruta: self._abrir_conversacion(r))
            # Al pasar el ratón, la tarjeta se eleva y el borde se enciende un poco.
            for widget in self._widgets_clickeables(tarjeta):
                widget.bind("<Enter>", lambda e, t=tarjeta: t.configure(
                    fg_color=COLOR_TARJETA_ALTA,
                    border_color=_mezclar(COLOR_BORDE, COLOR_ACENTO, 0.5)))
                widget.bind("<Leave>", lambda e, t=tarjeta: t.configure(
                    fg_color=COLOR_TARJETA, border_color=COLOR_BORDE))

    def _fecha_desde_archivo(self, ruta):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(ruta))
        if m:
            try:
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                meses = ["ene", "feb", "mar", "abr", "may", "jun",
                         "jul", "ago", "sep", "oct", "nov", "dic"]
                return f"{dt.day} {meses[dt.month - 1]} {dt.year}"
            except Exception:
                pass
        return os.path.basename(ruta)

    def _primer_mensaje(self, ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    m = re.match(r"\*\*\[\d{2}:\d{2}\]\s*(.+?):\*\*\s*(.*)", linea.strip())
                    if m and m.group(2).strip():
                        texto = m.group(2).strip()
                        return (texto[:34] + "…") if len(texto) > 34 else texto
        except Exception:
            pass
        return ""

    def _abrir_conversacion(self, ruta):
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        self._ind_pensando = None
        self._pegado_abajo = True    # al abrir un hilo se muestra el final
        self._procesando = False
        self._burbujas = []
        self._seleccion = []
        self.conversacion_actual = ruta  # los mensajes nuevos siguen este hilo
        self._mostrar_vista("chat")

        pares = self._leer_conversacion(ruta)
        self.chat_activo = None
        if not pares:
            self._mostrar_estado_chat(False)
            return
        self._mostrar_estado_chat(True)
        for autor, texto in pares:
            self._insertar_burbuja(autor, texto)
        self.after(60, self._scroll_final)

    def _leer_conversacion(self, ruta):
        pares = []
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    m = re.match(r"\*\*\[\d{2}:\d{2}\]\s*(.+?):\*\*\s*(.*)", linea.strip())
                    if m:
                        pares.append((m.group(1).strip(), m.group(2).strip()))
        except Exception as e:
            print(f"Error leyendo conversación: {e}")
        return pares

    def _abrir_config_excel(self):
        """Diálogo para elegir el Excel de la matriz: archivo local o URL."""
        cfg = self._leer_config_json()
        matriz = cfg.get("matriz") if isinstance(cfg.get("matriz"), dict) else {}

        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar Excel de la matriz")
        dlg.geometry("700x580")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Excel de la matriz", font=(FUENTE_UI, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(dlg,
                     text=("Elige el archivo .xlsx o pega el enlace (URL) del Excel.\n"
                           "· Archivo dentro de una carpeta sincronizada de "
                           "OneDrive/SharePoint: se sube solo.\n"
                           "· URL + \"Carpeta sincronizada\": la copia se edita ahí y "
                           "OneDrive sube los cambios a SharePoint solo.\n"
                           "· URL sola: se edita una copia local y los cambios NO llegan a "
                           "SharePoint."),
                     font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24,
                                                          pady=(0, 10))

        ctk.CTkLabel(dlg, text="Archivo (.xlsx) o URL:", text_color=COLOR_TEXTO,
                     font=(FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(6, 2))
        frame_ruta = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_ruta.pack(fill="x", padx=24)
        entrada_ruta = ctk.CTkEntry(frame_ruta, fg_color=COLOR_PANEL,
                                    border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
                                    height=34)
        entrada_ruta.pack(side="left", expand=True, fill="x", padx=(0, 8))
        valor = (matriz.get("excel_path") or matriz.get("excel_url") or "")
        if valor:
            entrada_ruta.insert(0, str(valor))

        def _examinar():
            actual = entrada_ruta.get().strip().strip('"')
            if not actual.lower().startswith(("http://", "https://")) \
                    and os.path.dirname(actual):
                inicial = os.path.dirname(actual)
            else:
                inicial = rutas.MATRICES
            elegido = filedialog.askopenfilename(
                title="Elegir Excel de la matriz", initialdir=inicial,
                filetypes=[("Hojas de cálculo", "*.xlsx *.xlsm"), ("Todos", "*.*")])
            if elegido:
                entrada_ruta.delete(0, "end")
                entrada_ruta.insert(0, elegido)

        ctk.CTkButton(frame_ruta, text="Examinar...", command=_examinar,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=34).pack(side="left")

        def _descargar():
            """Baja de nuevo el Excel publicado en la URL (copia local actualizada)."""
            valor = entrada_ruta.get().strip().strip('"')
            if not valor.lower().startswith(("http://", "https://")):
                lbl_estado.configure(text="Escribe primero la URL del Excel.",
                                     text_color=COLOR_PELIGRO)
                return
            # Se usa la carpeta sincronizada escrita aquí, aunque no se haya guardado aún.
            carpeta = os.path.expanduser(
                os.path.expandvars(entrada_sync.get().strip().strip('"')))
            if carpeta and not os.path.isdir(carpeta):
                lbl_estado.configure(
                    text=("La carpeta sincronizada no existe. Corrígela o déjala vacía para "
                          "bajar solo una copia local."),
                    text_color=COLOR_PELIGRO)
                return
            lbl_estado.configure(text="Descargando...", text_color=COLOR_TEXTO_SUAVE)
            resultado = {}

            def _worker():
                try:
                    resultado["ruta"] = self.system.cloud.descargar_excel(
                        valor, forzar=True, carpeta_sincronizada=carpeta or "")
                except Exception as e:
                    self.system.cloud.error_ruta = f"No pude descargar el Excel: {e}"
                    resultado["ruta"] = None

            def _revisar():
                """Se ejecuta en el hilo de la interfaz: la descarga va en un hilo aparte."""
                try:
                    if "ruta" not in resultado:
                        dlg.after(250, _revisar)
                        return
                    bajada = resultado["ruta"]
                    if bajada:
                        prefijo = ("Copia actualizada en la carpeta sincronizada "
                                   "(OneDrive la subirá): ") if carpeta else \
                                  "Copia local actualizada: "
                        lbl_estado.configure(text=f"{prefijo}{bajada}",
                                             text_color=COLOR_OK)
                    else:
                        lbl_estado.configure(
                            text=self.system.cloud.error_ruta or
                                 "No pude descargar el Excel.",
                            text_color=COLOR_PELIGRO)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
            dlg.after(250, _revisar)

        ctk.CTkLabel(dlg, text="Hoja:", text_color=COLOR_TEXTO,
                     font=(FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(12, 2))
        entrada_hoja = ctk.CTkEntry(dlg, fg_color=COLOR_PANEL,
                                    border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
                                    height=34)
        entrada_hoja.pack(padx=24, fill="x")
        entrada_hoja.insert(0, str(matriz.get("hoja") or "Matriz"))

        # Carpeta sincronizada (solo con URL): así los cambios se suben solos a SharePoint
        ctk.CTkLabel(dlg, text="Carpeta sincronizada de OneDrive/SharePoint (opcional):",
                     text_color=COLOR_TEXTO, font=(FUENTE_UI, 12)).pack(
                         anchor="w", padx=24, pady=(12, 2))
        frame_sync = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_sync.pack(fill="x", padx=24)
        entrada_sync = ctk.CTkEntry(
            frame_sync, fg_color=COLOR_PANEL, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO, height=34,
            placeholder_text="C:\\Users\\tu_usuario\\OneDrive - Empresa\\Shared Documents")
        entrada_sync.pack(side="left", expand=True, fill="x", padx=(0, 8))
        valor_sync = str(matriz.get("excel_sync_dir") or "")
        if valor_sync:
            entrada_sync.insert(0, valor_sync)

        def _elegir_carpeta():
            actual = entrada_sync.get().strip().strip('"')
            inicial = actual if os.path.isdir(actual) else rutas.MATRICES
            carpeta = filedialog.askdirectory(
                title="Carpeta sincronizada de OneDrive/SharePoint", initialdir=inicial)
            if carpeta:
                entrada_sync.delete(0, "end")
                entrada_sync.insert(0, os.path.normpath(carpeta))

        ctk.CTkButton(frame_sync, text="Elegir carpeta...", command=_elegir_carpeta,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=34).pack(side="left")
        ctk.CTkLabel(dlg,
                     text=("En SharePoint abre el Excel → \"Sincronizar\" y pon aquí esa "
                           "carpeta local.\nLa copia descargada se guarda en ella con el "
                           "mismo nombre, así OneDrive actualiza el archivo de SharePoint."),
                     font=(FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24, pady=(2, 0))

        lbl_estado = ctk.CTkLabel(dlg, text="", text_color=COLOR_TEXTO_SUAVE,
                                  font=(FUENTE_UI, 11), justify="left",
                                  wraplength=640)
        lbl_estado.pack(anchor="w", padx=24, pady=(10, 0))

        def _guardar():
            ruta_o_url = entrada_ruta.get().strip().strip('"')
            if not ruta_o_url:
                lbl_estado.configure(text="Indica un archivo o una URL.",
                                     text_color=COLOR_PELIGRO)
                return
            cfg_actual = self._leer_config_json()
            matriz_cfg = cfg_actual.get("matriz")
            if not isinstance(matriz_cfg, dict):
                matriz_cfg = {}
            if ruta_o_url.lower().startswith(("http://", "https://")):
                matriz_cfg["excel_url"] = ruta_o_url
                matriz_cfg.pop("excel_path", None)
            else:
                if not os.path.isabs(ruta_o_url):
                    lbl_estado.configure(
                        text="Para archivos usa la ruta completa (C:\\...\\Matriz.xlsx).",
                        text_color=COLOR_PELIGRO)
                    return
                if not os.path.exists(ruta_o_url):
                    lbl_estado.configure(text="El archivo no existe. Revisa la ruta.",
                                         text_color=COLOR_PELIGRO)
                    return
                matriz_cfg["excel_path"] = ruta_o_url
                matriz_cfg.pop("excel_url", None)
            sincronizada = os.path.expanduser(
                os.path.expandvars(entrada_sync.get().strip().strip('"')))
            if sincronizada:
                if not os.path.isdir(sincronizada):
                    lbl_estado.configure(
                        text=("La carpeta sincronizada no existe. Elige una carpeta real "
                              "(usa \"Elegir carpeta...\")."),
                        text_color=COLOR_PELIGRO)
                    return
                matriz_cfg["excel_sync_dir"] = sincronizada
            else:
                matriz_cfg.pop("excel_sync_dir", None)
            matriz_cfg["hoja"] = entrada_hoja.get().strip() or "Matriz"
            matriz_cfg.setdefault("columnas", list(COLUMNAS_DEFECTO))
            cfg_actual["matriz"] = matriz_cfg
            try:
                self._escribir_config_json(cfg_actual)
            except Exception as e:
                lbl_estado.configure(text=f"No pude guardar: {e}", text_color=COLOR_PELIGRO)
                return
            self._actualizar_estado_nube()
            dlg.destroy()

        frame_botones = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_botones.pack(fill="x", padx=24, pady=16)
        ctk.CTkButton(frame_botones, text="Guardar", command=_guardar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      height=36, font=(FUENTE_UI, 12, "bold")).pack(side="right",
                                                                     padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Descargar URL ahora", command=_descargar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=36,
                      font=(FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=36).pack(side="right")

    # ---------------- Configuración ----------------
    def _pintar_usuario(self, nombre=None):
        """Deja el pie de la barra lateral con tu nombre (o el aviso de ponerlo).

        El nombre sale del campo «Tu nombre» de Ajustes: el de la sesión de Windows
        no se usa, que era lo que enseñaba «coutt · Free» sin que nadie lo pidiera.
        """
        if nombre is None:
            nombre = self.entry_usuario.get().strip() if hasattr(self, "entry_usuario") else ""
        nombre = str(nombre or "").strip()
        try:
            self.avatar.configure(text=(nombre[:1].upper() if nombre else "\u2726"))
            self.lbl_usuario.configure(
                text=nombre or USUARIO_SIN_NOMBRE,
                text_color=COLOR_TEXTO if nombre else COLOR_TEXTO_SUAVE)
        except Exception:
            pass            # la ventana aún no tiene la barra lateral montada

    def _cargar_config_en_inputs(self):
        """Carga los valores guardados en config_usuario.json (o .env para la API key)."""
        api_key = ""
        nombre = "jarvis"
        rvc = ""
        usuario = ""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    api_key = config.get("api_key", "")
                    nombre = config.get("nombre_asistente", "jarvis")
                    rvc = config.get("modelo_rvc_path", "")
                    usuario = config.get("usuario", "")
            except Exception as e:
                print(f"Error al cargar configuración: {e}")

        # La API key puede venir de la variable de entorno (más segura)
        api_key_env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key_env:
            api_key = api_key_env

        usuario = (usuario or "").strip()
        self._pintar_usuario(usuario)

        self.entry_api.delete(0, "end")
        self.entry_nombre.delete(0, "end")
        self.entry_rvc.delete(0, "end")
        self.entry_usuario.delete(0, "end")
        self.entry_api.insert(0, api_key)
        self.entry_nombre.insert(0, nombre)
        self.entry_rvc.insert(0, rvc)
        self.entry_usuario.insert(0, usuario)

        # Matriz en la nube: se configura con sus propios botones/diálogos
        self._actualizar_estado_nube()
        # Correo: idem (se conecta con 'Conectar correo')
        self._actualizar_estado_correo()
        # Música: idem (se conecta con 'Conectar Spotify')
        self._actualizar_estado_spotify()

    def guardar_config(self):
        """Guarda los datos de la interfaz en el JSON preservando claves existentes."""
        existente = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    existente = json.load(f)
                if not isinstance(existente, dict):
                    existente = {}
            except Exception as e:
                print(f"Error leyendo configuración previa: {e}")

        # Si la API key viene de la variable de entorno, no la persistimos en el JSON
        api_key = self.entry_api.get().strip()
        api_key_env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key and api_key_env and api_key == api_key_env:
            api_key = ""

        existente["api_key"] = api_key
        existente["nombre_asistente"] = self.entry_nombre.get().strip().lower()
        existente["usuario"] = self.entry_usuario.get().strip()
        existente["modelo_rvc_path"] = self.entry_rvc.get().strip()

        # La matriz en la nube (Excel + Azure DevOps) se configura con sus propios
        # botones y diálogos: aquí se conserva tal cual, sin modificarla.

        existente.setdefault("programas", {
            "discord": "discord://",
            "spotify": "spotify:",
            "vscode": "code"
        })

        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(existente, f, indent=4)

        # Re-inicializar módulos con la nueva configuración
        self.brain = APIBrain(self.config_path)
        self.voice.nombre_activacion = existente["nombre_asistente"]
        # El nombre nuevo se ve en la barra lateral al momento, y el cerebro ya lo
        # lleva en su mensaje de sistema (así lo recuerda en cada conversación).
        self._pintar_usuario(existente["usuario"])
        self.lbl_estado.configure(
            text=("Configuración guardada · Jarvis te llamará " + existente["usuario"]
                  if existente["usuario"] else "Configuración guardada"),
            text_color=COLOR_OK)

    # ---------------- Control por voz ----------------
    def toggle_escucha(self):
        if not self.escuchando:
            # El micrófono del chat y el del apartado de inglés no pueden estar
            # escuchando a la vez: se apaga el del speaking si estaba encendido.
            if getattr(self, "_speaking_activo", False):
                self._parar_speaking("Micrófono apagado.")
            self.escuchando = True
            self.lbl_estado.configure(text="Estado: Escuchando...", text_color=COLOR_OK)
            self.btn_toggle.configure(text="\u23F9  Detener Escucha", fg_color=COLOR_PELIGRO,
                                      hover_color=COLOR_PELIGRO_HOVER)
            threading.Thread(target=self._bucle_escucha, daemon=True).start()
        else:
            self.escuchando = False
            self.lbl_estado.configure(text="Estado: Inactivo", text_color=COLOR_TEXTO_SUAVE)
            self.btn_toggle.configure(text="\U0001F3A4  Iniciar Escucha", fg_color=COLOR_ACENTO,
                                      hover_color=COLOR_ACENTO_HOVER)
        # El micrófono de la barra de entrada refleja el mismo estado (y su anillo
        # late mientras escucha), tanto si se pulsó aquí como si vino por voz.
        self._actualizar_mic()

    def _bucle_escucha(self):
        """Bucle principal de procesamiento de voz en hilo daemon."""
        while self.escuchando:
            comando_usuario = self.voice.escuchar_microfono()

            if comando_usuario and self.escuchando:
                # 1. Manejo de comandos de cierre
                if comando_usuario == "COMANDO_CERRAR":
                    self.reproducir_voz("Entendido, cerrando el programa. Hasta luego.")
                    self.after(0, self.destroy)
                    break
                if comando_usuario == "COMANDO_APAGAR":
                    self.reproducir_voz("Entendido, desactivando la escucha.")
                    self.after(0, self.toggle_escucha)
                    break

                # 1.5 Modo dictado continuo: escribir el texto en lugar de procesarlo
                if self.system.productivity.dictado_activo:
                    if self._es_fin_dictado(comando_usuario):
                        self.system.productivity.dictado_activo = False
                        self.reproducir_voz("Dictado desactivado.")
                    else:
                        self.system.productivity.dictar(comando_usuario)
                    continue

                print(f"Instrucción a procesar: {comando_usuario}")
                self._guardar_regla_si_aplica(comando_usuario)
                self._agregar_chat("Tú", comando_usuario)

                # 2-3-4. Procesar y responder por voz (con el indicador del chat:
                # por voz pasa lo mismo y sin él no se sabía qué estaba haciendo).
                modelo_rvc = self.entry_rvc.get().strip()
                self.after(0, lambda: self._mostrar_pensando(True))
                try:
                    respuesta = self._procesar_mensaje(comando_usuario)
                finally:
                    self.after(0, lambda: self._mostrar_pensando(False))
                if respuesta:
                    self._agregar_chat("Jarvis", respuesta)
                    self.reproducir_voz(respuesta, modelo_rvc or None)

    def _es_fin_dictado(self, texto):
        t = texto.lower()
        return any(p in t for p in ["detener dictado", "detén dictado", "fin del dictado",
                                    "salir del dictado", "terminar dictado"])

    def _notificar_reunion(self, titulo, texto):
        """Aviso de Windows y burbuja en el chat de lo que pasa con la reunión.

        `MeetingAssistant.finalizar` trabaja en su propio hilo (transcribir y
        redactar el acta tarda minutos), así que para cuando acaba la ventana
        puede estar detrás de la reunión. El aviso de escritorio se ve igual; la
        burbuja deja el mismo mensaje en el hilo, que es donde se pregunta «¿ya?».
        """
        notificaciones.avisar(titulo, texto)
        try:
            self.after(0, lambda: self._agregar_chat("Jarvis", texto))
        except Exception as e:
            print(f"No pude dejar el aviso de la reunión en el chat: {e}")

    def _metadatos_reunion(self):
        """Título e invitados de la reunión en curso, leídos del calendario.

        La grabación los guarda en el acta, y con ellos se puede enviar el acta a
        los asistentes sin tener que dictar los correos. Si no hay calendario
        disponible se devuelve un dict vacío y la grabación sigue igual.
        """
        datos = {}
        try:
            evento, _mensaje = self.system.calendario.evento_en_curso()
        except Exception as e:
            print(f"No pude leer el calendario para la reunión: {e}")
            return datos
        if evento:
            datos["titulo"] = evento.get("asunto", "")
            datos["asistentes"] = list(evento.get("correos") or [])
        return datos

    def _resumir_reunion(self, transcripcion, metadatos=None):
        """Analiza la grabación y devuelve el acta con la información rescatada.

        El trabajo fino (ficha de la reunión, troceado de las grabaciones largas y
        plantilla del acta) está en `MeetingAssistant.analizar_transcripcion`, que usa
        `APIBrain.analizar_documento` como motor: una salida larga, sin el límite de
        tres frases del chat y sin interpretar comandos de acción dentro del acta.
        """
        datos = dict(metadatos or {})
        if not datos:
            datos = self.system.meeting.reunion_actual() or {}
        self.system.progreso.paso("Analizando la grabación con la IA para redactar el acta")
        acta = self.system.meeting.analizar_transcripcion(
            transcripcion, datos, self.brain.analizar_documento)
        self.system.progreso.hecho("Acta redactada")
        return acta

    def _generar_preventa(self, tipo, contenido):
        prompts = {
            "propuesta": "Genera una propuesta técnica profesional para un proyecto de software con: alcance, objetivos, solución propuesta, arquitectura, plan de trabajo y entregables. Usa Markdown.",
            "requisitos": "Genera una matriz de cumplimiento de requisitos (tabla) con columnas: ID, Requisito, Prioridad, Tipo (funcional/no funcional) y Observaciones. Usa Markdown.",
            "historias": "Genera historias de usuario en formato 'Como [rol], quiero [funcionalidad], para [beneficio]', cada una con criterios de aceptación. Usa Markdown.",
            "glosario": "Genera un glosario de términos técnicos del contenido, con definiciones claras y concisas. Usa Markdown.",
            "resumen": "Genera un resumen ejecutivo con: objetivo, alcance, riesgos y recomendaciones. Usa Markdown.",
            "estimacion": "Genera una estimación de esfuerzo por fases (análisis, diseño, desarrollo, pruebas, despliegue) con horas y supuestos. Usa Markdown.",
        }
        prompt = prompts.get(tipo, "Procesa este contenido y genera un documento estructurado en Markdown.") + "\n\nContenido:\n" + contenido
        self.system.progreso.paso(f"Generando el documento ({tipo}) con la IA")
        documento = self.brain.analizar_documento(prompt)
        self.system.progreso.hecho("Documento generado")
        return documento

    def _clasificar_archivos_ia(self, nombres, regla, carpetas=None, extractos=None):
        """Clasifica archivos con la IA: devuelve [(nombre, subcarpeta)].

        Con 'carpetas' (las que ya existen en el destino) la IA elige entre las
        de verdad en vez de inventarse nombres; con 'extractos' ({nombre: texto de
        dentro del documento}) decide además por lo que pone dentro, y no solo por
        el nombre del archivo.
        """
        # La IA tarda unos segundos por tanda: se dice cuántos van, con qué regla
        # y si lleva el texto de dentro (que es lo que la hace acertar).
        self.system.progreso.paso(
            f"Pidiendo a la IA que reparta {len(nombres)} documento(s) por subcarpetas"
            + (", con el texto de dentro" if extractos else ""))
        plan = self.brain.clasificar_archivos(nombres, regla, carpetas, extractos)
        if plan is None:
            # Sin IA (sin API Key o sin respuesta) se sigue con la clasificación de
            # respaldo: mejor decirlo que callar y dejar todo en la raíz sin más.
            self.system.progreso.aviso("Sin IA disponible: los dejo en la raíz de la "
                                       "carpeta de destino")
        elif not plan:
            self.system.progreso.aviso("La IA no devolvió un reparto usable")
        else:
            # los que la regla deja quietos ('dejar') no son una subcarpeta: se
            # cuentan aparte para que el aviso diga el reparto de verdad.
            quietos = sum(1 for _nombre, sub in plan
                          if self.system.sharepoint.es_dejar(sub))
            subcarpetas = {sub for _nombre, sub in plan
                           if sub and not self.system.sharepoint.es_dejar(sub)}
            self.system.progreso.hecho(
                f"La IA repartió {len(plan) - quietos} documento(s) en "
                f"{len(subcarpetas) or 1} subcarpeta(s)"
                + (f"; {quietos} se quedan donde están" if quietos else "")
                + ("; son copias (los originales no se tocan)"
                   if self.system.sharepoint.quiere_copiar(regla) else ""))
        return plan

    def reproducir_voz(self, texto, modelo_rvc=None, idioma="es"):
        """Reproduce texto con edge-tts (voz española) y cae a pyttsx3 offline si falla.

        Con `idioma="en"` se usa la voz inglesa: es lo que lee en voz alta la réplica
        del «speaking» (también en el respaldo offline, que lleva voz del sistema).
        """
        if not texto:
            return
        try:
            self.voice.hablar(texto, rvc_model_path=modelo_rvc, idioma=idioma)
        except Exception as e:
            print(f"Error en edge-tts, usando pyttsx3 offline: {e}")
            if hasattr(self.voice_output, "hablar"):
                self.voice_output.hablar(texto)
