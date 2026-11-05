"""Apartado del taller de Java: el programa, su revisión y las tarjetas del curso.

El programa se escribe en una ventana aparte (`views.editor_codigo`), con sitio y
números de línea; aquí queda siempre lo último escrito, se corrige y se ejecuta
**mientras se escribe**: el analizador propio —y `javac`, si hay JDK— devuelve los
fallos con su línea y su columna en el panel de la revisión, y lo que imprime el
programa sale en la consola, sin gastar IA. Los botones arman la tarea
(`ProgrammingTutor`) y el contenido se pinta en tarjetas, igual que la clase de
inglés.

El centro tiene una zona (su pestaña) por tarea: **Clase**, el **Chat** del taller
—con su hilo, su memoria y su archivo en la carpeta del taller— y una más para
cada botón (Bases, Lección, Ejercicios, Documentación, comparaciones, avance,
revisión y salida del programa), de modo que lo de una tarea no pisa lo de otra.
Cada zona se puede abrir además en su propia ventana (`views.zona_programacion`).
"""
import os
import threading
from datetime import datetime

import customtkinter as ctk

from modules.api_brain import APIBrain
from modules.programming_tutor import MARCA_PROFE, NIVELES as NIVELES_JAVA
from modules import rutas
from ui import tema
from ui import scroll as rueda
from ui.tema import (
    BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_HOVER, COLOR_ACENTO_TEXTO,
    COLOR_AVISO, COLOR_BORDE, COLOR_CODIGO, COLOR_CODIGO_TEXTO, COLOR_HOVER,
    COLOR_OK, COLOR_PANEL, COLOR_PELIGRO, COLOR_TARJETA, COLOR_TARJETA_ALTA,
    COLOR_TEXTO, COLOR_TEXTO_SUAVE, COLOR_USUARIO, RADIO_CHIP, RADIO_TARJETA, _mezclar,
)

from views.base import Vista, caja_consola, escribir_consola, limpiar_consola
from views.editor_codigo import VentanaEditorCodigo, nombre_de_clase
from views.zona_programacion import VentanaZonaProgramacion

# ---------------- Apartado de programación (taller de Java) ----------------
# Mismo esquema que el de inglés: cada tarea del taller es un botón con su icono.
# La corrección es la tarea principal (acento) y la de borrar el avance va en rojo.
TAREAS_PROGRAMACION = (
    ("\U0001F50E  Corregir", "corregir"),
    ("\U0001F4D6  Bases", "bases"),
    ("\U0001F4D8  Lección", "leccion"),
    ("\u270F  Ejercicios", "ejercicios"),
    ("\U0001F4D1  Documentación", "documentacion"),
    ("\u2696  ¿Por qué…?", "comparar"),
    ("\u2753  Preguntar", "preguntar"),
    ("\u25B6  Probar", "probar"),
    ("\U0001F4CA  Mi avance", "progreso"),
    ("\U0001F5D1  Borrar", "borrar"),
)
TAREA_PROG_PRINCIPAL = "corregir"
TAREA_PROG_PELIGRO = "borrar"

#: Avisos que caben de una vez en el panel de la revisión (los demás se cuentan).
MAX_AVISOS_PANTALLA = 12

#: Las dos caras del centro del taller: las tarjetas de la clase y su chat propio.
#: El chat es una conversación del taller, aparte de la del chat de Jarvis.
PANEL_PROG_CLASE = "\U0001F4DA  Clase"
PANEL_PROG_CHAT = "\U0001F4AC  Chat"

#: Una zona por tarea: cada botón de «Qué quieres hacer» abre la suya, con su
#: pestaña en el centro y la opción de verla en una ventana aparte. Así lo de una
#: tarea no pisa lo de otra: la lección sigue ahí mientras miras los ejercicios.
#: clave -> (pestaña, icono, título, qué se lee en esa zona)
ZONAS_PROG = {
    "clase": (PANEL_PROG_CLASE, "\U0001F4D8", "Lo que te enseño",
              "La guía del taller y lo último que te he preparado."),
    "chat": (PANEL_PROG_CHAT, "\U0001F4AC", "Chat del taller",
             "Una conversación propia del taller, con tu programa delante."),
    "revision": ("\U0001F50E  Corregir", "\U0001F50E", "Revisión del compilador",
                 "Lo que ha visto el compilador de tu programa, con línea y columna."),
    "probar": ("\u25B6  Probar", "\u25B6", "Lo que hizo tu programa",
               "La salida y el desenlace de la última ejecución."),
    "bases": ("\U0001F4D6  Bases", "\U0001F4D6", "Bases del curso",
              "Por dónde empieza el temario: primer programa, variables y condicionales."),
    "leccion": ("\U0001F4D8  Lección", "\U0001F4D8", "Lección del tema",
                "La lección que me pidas en «Tema», paso a paso y con ejemplos."),
    "ejercicios": ("\u270F  Ejercicios", "\u270F", "Ejercicios para practicar",
                   "Ejercicios del tema (o de tus fallos) con sus soluciones comentadas."),
    "documentacion": ("\U0001F4D1  Docs", "\U0001F4D1", "Documentación",
                      "Qué hace una clase o un método, con ejemplos de uso."),
    "comparar": ("\u2696  ¿Por qué?", "\u2696", "Comparaciones razonadas",
                 "Dos formas de hacer lo mismo, y cuándo conviene cada una."),
    "progreso": ("\U0001F4CA  Avance", "\U0001F4CA", "Mi avance",
                 "Tu nivel, las prácticas corregidas y los fallos que más se repiten."),
}

#: Qué zona abre cada botón del taller (el de borrar deja el avance a la vista).
ZONA_DE_TAREA = {
    "corregir": "revision",
    "probar": "probar",
    "preguntar": "chat",
    "bases": "bases",
    "leccion": "leccion",
    "documentacion": "documentacion",
    "comparar": "comparar",
    "ejercicios": "ejercicios",
    "progreso": "progreso",
    "borrar": "progreso",
}

#: Lo que se lee en el chat del taller antes de preguntar nada.
AYUDA_CHAT_PROG = (
    "Aquí me tienes para indagar lo que quieras: `equals` contra `==`, por qué no "
    "compila una línea, qué hace un `ArrayList` por dentro\u2026\n\n"
    "Veo tu programa y lo que dice el compilador, y me acuerdo de lo que hablamos en "
    "este chat. Escríbeme la duda aquí abajo y te contesto."
)

#: Turnos del chat del taller que se recuerdan en la ventana (a la IA le llegan menos).
MAX_TURNOS_CHAT_PROG = 40

#: Lo que se contesta en el chat cuando la IA no devuelve nada (sin conexión o sin clave).
SIN_RESPUESTA_PROG = (
    "No pude preparar la respuesta: revisa tu API Key del asistente en **Ajustes** y "
    "vuelve a preguntarme.\n\n"
    "Lo demás sigue funcionando sin conexión: la revisión de tu código, el temario, las "
    "lecciones, la documentación, las comparaciones y tu avance."
)


def _hora_actual():
    """La hora `HH:MM` de ahora (para fechar lo que se dice en el chat)."""
    return datetime.now().strftime("%H:%M")


#: El programa de ejemplo que se encuentra el alumno al abrir el taller: compila,
#: imprime algo y sirve de plantilla para empezar a escribir.
CODIGO_EJEMPLO = (
    "import java.util.Scanner;\n"
    "\n"
    "public class Hola {\n"
    "    public static void main(String[] args) {\n"
    "        Scanner lector = new Scanner(System.in);\n"
    "        System.out.print(\"¿Cómo te llamas? \");\n"
    "        String nombre = lector.nextLine();\n"
    "        System.out.println(\"Hola, \" + nombre + \"!\");\n"
    "    }\n"
    "}\n"
)

#: Lo que se ve en el taller al abrirlo por primera vez (Markdown con títulos
#: «## icono título», que es lo que el panel convierte en tarjetas).
AYUDA_PROGRAMACION = (
    "## \U0001F44B Cómo se usa\n"
    "1. Pulsa **\u270F Abrir el editor**: el programa se escribe en una **ventana aparte**, "
    "con sitio de sobra y números de línea. Mientras escribes se revisa solo: cada "
    "aviso sale aquí con su **línea y su columna**, y no gasta IA.\n"
    "2. Desde esa ventana, pulsa **\u25B6 Ejecutar** (o F5): compila de verdad y lo que "
    "imprima tu programa (`System.out.println`) sale en la **consola**, justo debajo. "
    "Lo que lea por teclado se escribe en «Entrada».\n"
    "3. Aquí, en el taller, tienes el resto:\n"
    "   · **\U0001F50E Corregir**: pasa el compilador de verdad (`javac`), si lo tienes "
    "instalado, y apunta los fallos para tu avance.\n"
    "   · **\u25B6 Probar**: compila y ejecuta desde aquí mismo, con la salida en la "
    "consola del taller.\n"
    "   · **\U0001F4D6 Bases** y **\U0001F4D8 Lección**: el temario del curso y el tema que "
    "escribas en «Tema».\n"
    "   · **\U0001F4D1 Documentación**: qué hace una clase o un método, con ejemplos.\n"
    "   · **\u2696 ¿Por qué…?**: comparaciones razonadas («¿por qué `equals` y no `==`?»).\n"
    "   · **\u270F Ejercicios**: para practicar un tema o los fallos que más se te repiten.\n"
    "   · **\u2753 Preguntar**: tu duda suelta, que se contesta en el **chat del taller**.\n"
    "   Cada botón abre **su propia pestaña** en el centro y no pisa lo de las demás: "
    "puedes dejar la lección abierta y mirar los ejercicios en otra. Con **\u29C9 En "
    "ventana** esa misma zona se abre aparte, para verla a la vez que el taller.\n"
    "4. El **\U0001F4AC Chat** (la pestaña de arriba, a la derecha de «Clase») es una "
    "conversación propia del taller: ahí puedes indagar lo que quieras y se acuerda de lo "
    "que habéis hablado, sin mezclarlo con tu chat de siempre. Enter manda y Mayús+Enter "
    "hace un salto de línea; «\U0001F9F9 Nuevo» empieza otra conversación.\n"
    "## \U0001F9ED Por dónde empezar\n"
    "- Si es tu primer día: `primer_programa`, `variables` y `condicionales`.\n"
    "- Cuando algo no compile, mira la **línea** y la **columna** del aviso y lee la "
    "pista: casi siempre sobra o falta un `;`, una llave o una comilla.\n"
    "- El **JDK** (Java Development Kit) es lo que permite compilar y ejecutar de "
    "verdad. Sin él, el taller revisa llaves, paréntesis, comas y los errores típicos "
    "de empezar.\n"
)


class VistaProgramacion(Vista):
    """El taller de programación: tu programa, sus avisos y las clases del profe."""

    nombre = "programar"

    def _preparar(self):
        """Estado del taller: el programa, la última clase, la revisión y su chat."""
        self.codigo_prog = CODIGO_EJEMPLO   # el programa (se escribe en la ventana del editor)
        self._editor = None                 # la ventana del editor, si está abierta
        self._clase_prog = ""
        self._tarjetas_prog = []    # tarjetas pintadas en el panel de la clase
        self._marcos_prog = []      # marcos de esas tarjetas (título e icono)
        self._prog_borrar_pendiente = False
        self._revision_prog = None  # `after` de la revisión mientras se escribe
        # El chat del taller: una conversación propia, con su hilo y su archivo.
        self._panel_prog = "clase"  # qué zona del centro se está viendo
        # Una entrada por zona abierta (clave -> marco, tarjetas, texto, ventana…).
        # Cada botón de «Qué quieres hacer» abre la suya y conserva lo que tenía.
        self._zonas_prog = {}
        self._orden_zonas_prog = []     # en el orden en que se han abierto
        self._orden_pestanas = []       # el de las pestañas que se están viendo
        self._contenedor_prog = None    # donde viven las zonas (se monta al construir)
        self._zona_destino = None       # a qué zona escribe el turno en curso
        self._hilo_prog = []        # [(quién, texto)] de lo hablado en el chat
        self._burbujas_chat_prog = []   # lo mismo, pero tal cual se ha pintado
        self._chat_prog_ruta = None     # archivo del chat (uno nuevo por conversación)
        self._pista_chat_prog = None    # la ayuda que se lee antes de preguntar
        self._fila_pensando_prog = None  # «el profe está escribiendo…»
        self._latido_prog = None    # `after` de los puntos suspensivos


    # ---------------- Apartado de programación (taller de Java) ----------------
    def _construir(self):
        """Monta el taller de programación (se entra con el botón «Programar»).

        Se escribe el programa en el editor y se corrige **mientras se escribe**:
        el analizador propio —y `javac`, si hay JDK— devuelve los fallos con su
        línea y su columna en el panel de la revisión, sin gastar IA. Los botones
        arman la tarea (`ProgrammingTutor`) y el contenido se pinta en tarjetas,
        igual que la clase de inglés: lo que ya viene escrito en sus tablas se lee
        sin conexión y lo que necesita la IA se pide al cerebro con el mensaje de
        sistema del profesor de programación (`APIBrain.SISTEMA_PROGRAMADOR`).
        """
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(16, 4))
        ctk.CTkButton(cabecera, text="\u2039  Volver al chat", width=150, height=34,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, anchor="w", font=(tema.FUENTE_UI, 13),
                      command=lambda: self.app._mostrar_vista("chat")).pack(side="left")
        ctk.CTkLabel(cabecera, text="\U0001F4BB", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 16)).pack(side="left", padx=(16, 8))
        ctk.CTkLabel(cabecera, text="Aprender programación",
                     font=(tema.FUENTE_UI, 20, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")
        ctk.CTkLabel(cabecera, text="\U0001F39A  Nivel", font=(tema.FUENTE_UI, 12),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="right", padx=(0, 8))
        self.menu_prog_nivel = ctk.CTkOptionMenu(
            cabecera, values=list(NIVELES_JAVA), width=110, height=34,
            font=(tema.FUENTE_UI, 13, "bold"),
            fg_color=COLOR_TARJETA, button_color=COLOR_ACENTO,
            button_hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_TEXTO,
            dropdown_fg_color=COLOR_TARJETA_ALTA, dropdown_text_color=COLOR_TEXTO,
            dropdown_hover_color=COLOR_HOVER,
            command=self._cambiar_nivel_programacion)
        self.menu_prog_nivel.pack(side="right")

        # Cómo va el alumno (nivel, prácticas, fallos repetidos y JDK), de un vistazo.
        self.marco_prog_resumen = ctk.CTkFrame(
            self, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA, border_width=1,
            border_color=COLOR_BORDE)
        self.marco_prog_resumen.pack(fill="x", padx=30, pady=(8, 10))
        ctk.CTkLabel(self.marco_prog_resumen, text="\U0001F4CA", font=(tema.FUENTE_UI, 13),
                     text_color=COLOR_ACENTO).pack(side="left", padx=(14, 8), pady=8)
        self.lbl_prog_resumen = ctk.CTkLabel(self.marco_prog_resumen, text="", anchor="w",
                                             justify="left", font=(tema.FUENTE_UI, 12),
                                             text_color=COLOR_TEXTO_SUAVE, wraplength=820)
        self.lbl_prog_resumen.pack(side="left", padx=(0, 14), pady=8)

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=26, pady=(0, 16))
        cuerpo.grid_columnconfigure(0, minsize=300)
        cuerpo.grid_columnconfigure(1, weight=1)
        cuerpo.grid_columnconfigure(2, minsize=298)
        cuerpo.grid_rowconfigure(0, weight=1)

        # --- Izquierda: la práctica (se ve y se revisa) y lo que quieres que te prepare
        izquierda = ctk.CTkScrollableFrame(cuerpo, width=282, fg_color="transparent",
                                           **BARRA_SCROLL)
        izquierda.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        caja_practica = self._tarjeta(
            izquierda, "\u2328", "Práctica de código",
            "Se revisa mientras escribes: cada aviso, con su línea y su columna.",
            ancho_texto=248)
        self.txt_prog_codigo = ctk.CTkTextbox(
            caja_practica, height=158, fg_color=COLOR_CODIGO, border_width=1,
            border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_CODIGO_TEXTO, font=(tema.FUENTE_MONO, 11), wrap="none",
            state="disabled")
        self.txt_prog_codigo.pack(fill="x")
        rueda.acelerar_caja(self.txt_prog_codigo)
        self.lbl_prog_estado = ctk.CTkLabel(
            caja_practica, text="Listo cuando quieras.", font=(tema.FUENTE_UI, 11),
            anchor="w", justify="left", wraplength=248, text_color=COLOR_TEXTO_SUAVE)
        self.lbl_prog_estado.pack(fill="x", pady=(8, 0))
        # El código se escribe en la ventana del editor (aquí solo se ve): es lo que
        # pedía el alumno, que el editor tenga sitio y no quede apretado.
        self.btn_prog_abrir_editor = ctk.CTkButton(
            caja_practica, text="\u270F  Abrir el editor", height=38,
            corner_radius=RADIO_CHIP, fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO, font=(tema.FUENTE_UI, 13, "bold"),
            command=self.abrir_editor)
        self.btn_prog_abrir_editor.pack(fill="x", pady=(10, 0))

        caja_tareas = self._tarjeta(
            izquierda, "\U0001F3AF", "Qué quieres hacer",
            "El tema solo se usa para lección, documentación, comparaciones y ejercicios.",
            ancho_texto=248)
        self.entry_prog_tema = ctk.CTkEntry(
            caja_tareas, height=34, fg_color=COLOR_CODIGO, border_color=COLOR_BORDE,
            corner_radius=RADIO_CHIP, text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
            placeholder_text="Tema: p. ej. bucles, equals")
        self.entry_prog_tema.pack(fill="x")

        cantidades = ctk.CTkFrame(caja_tareas, fg_color="transparent")
        cantidades.pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(cantidades, text="Cuántos ejercicios", font=(tema.FUENTE_UI, 11),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="left")
        self.menu_prog_cantidad = ctk.CTkOptionMenu(
            cantidades, values=[str(numero) for numero in range(3, 11)], width=70, height=30,
            font=(tema.FUENTE_UI, 12), fg_color=COLOR_CODIGO, button_color=COLOR_TARJETA_ALTA,
            button_hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            dropdown_fg_color=COLOR_TARJETA_ALTA, dropdown_text_color=COLOR_TEXTO)
        self.menu_prog_cantidad.set("5")
        self.menu_prog_cantidad.pack(side="right")

        # Una tarea por botón (en dos columnas): la corrección en acento y la de
        # borrar el avance en rojo suave.
        rejilla = ctk.CTkFrame(caja_tareas, fg_color="transparent")
        rejilla.pack(fill="x")
        self.botones_prog = {}
        for indice, (etiqueta, tarea) in enumerate(TAREAS_PROGRAMACION):
            principal = tarea == TAREA_PROG_PRINCIPAL
            peligro = tarea == TAREA_PROG_PELIGRO
            boton = ctk.CTkButton(
                rejilla, text=etiqueta, font=(tema.FUENTE_UI, 12), height=34,
                corner_radius=RADIO_CHIP, anchor="w",
                fg_color=COLOR_ACENTO if principal else COLOR_TARJETA_ALTA,
                hover_color=COLOR_ACENTO_HOVER if principal else COLOR_HOVER,
                border_width=0 if principal else 1, border_color=COLOR_BORDE,
                text_color=(COLOR_ACENTO_TEXTO if principal
                            else COLOR_PELIGRO if peligro else COLOR_TEXTO),
                command=lambda tarea=tarea: self._accion_programacion(tarea))
            boton.grid(row=indice // 2, column=indice % 2, sticky="ew", padx=2, pady=3)
            self.botones_prog[tarea] = boton
        rejilla.grid_columnconfigure(0, weight=1)
        rejilla.grid_columnconfigure(1, weight=1)

        # --- Centro: la revisión, la consola y lo que te enseño, en tarjetas
        centro = ctk.CTkFrame(cuerpo, fg_color="transparent")
        centro.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        centro.grid_columnconfigure(0, weight=1)
        centro.grid_rowconfigure(2, weight=1)   # el panel se queda con el sitio libre

        # La revisión: línea y columna de cada aviso, según se escribe.
        marco_revision = ctk.CTkFrame(centro, fg_color=COLOR_TARJETA,
                                      corner_radius=RADIO_TARJETA, border_width=1,
                                      border_color=COLOR_BORDE)
        marco_revision.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.marco_revision_prog = marco_revision
        fila_revision = ctk.CTkFrame(marco_revision, fg_color="transparent")
        fila_revision.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(fila_revision, text="\U0001F50E", font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila_revision, text="Lo que tengo que corregir",
                     font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.lbl_prog_jdk = ctk.CTkLabel(fila_revision, text="", font=(tema.FUENTE_UI, 10),
                                         text_color=COLOR_TEXTO_SUAVE)
        self.lbl_prog_jdk.pack(side="right")

        self.txt_prog_avisos = ctk.CTkTextbox(
            marco_revision, height=92, fg_color=COLOR_CODIGO, border_width=1,
            border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_TEXTO, font=(tema.FUENTE_MONO, 11), wrap="word")
        self.txt_prog_avisos.pack(fill="x", padx=14, pady=(0, 12))
        self.txt_prog_avisos.configure(state="disabled")
        rueda.acelerar_caja(self.txt_prog_avisos)

        # La consola: aquí sale lo que imprime el programa al pulsar «Ejecutar».
        marco_consola = ctk.CTkFrame(centro, fg_color=COLOR_TARJETA,
                                     corner_radius=RADIO_TARJETA, border_width=1,
                                     border_color=COLOR_BORDE)
        marco_consola.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.marco_consola_prog = marco_consola
        fila_consola = ctk.CTkFrame(marco_consola, fg_color="transparent")
        fila_consola.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(fila_consola, text="\u25B6", font=(tema.FUENTE_UI, 13),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila_consola, text="Consola", font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        ctk.CTkButton(fila_consola, text="\U0001F9F9", width=30, height=26,
                      corner_radius=RADIO_CHIP, fg_color="transparent",
                      hover_color=COLOR_HOVER, text_color=COLOR_TEXTO_SUAVE,
                      font=(tema.FUENTE_UI, 12), command=self._limpiar_consola).pack(side="right")
        self.lbl_prog_consola = ctk.CTkLabel(fila_consola, text="sin ejecutar",
                                             font=(tema.FUENTE_UI, 10),
                                             text_color=COLOR_TEXTO_SUAVE)
        self.lbl_prog_consola.pack(side="right", padx=(0, 8))
        contenedor, self.txt_prog_consola = caja_consola(marco_consola, alto=6)
        contenedor.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(marco_consola, text="Lo que leerá el programa (Scanner): un dato por línea",
                     font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE,
                     anchor="w").pack(fill="x", padx=14)
        self.txt_prog_entrada = ctk.CTkTextbox(
            marco_consola, height=42, fg_color=COLOR_CODIGO, border_width=1,
            border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_TEXTO, font=(tema.FUENTE_MONO, 11), wrap="none")
        self.txt_prog_entrada.pack(fill="x", padx=14, pady=(4, 12))
        self._atajos_caja(self.txt_prog_entrada)
        rueda.acelerar_caja(self.txt_prog_entrada)

        # --- Lo que se ve en el centro: una zona independiente por tarea ---
        # Cada botón de «Qué quieres hacer» abre su propia zona: su pestaña en el
        # centro, con su contenido, sus botones de copiar/guardar y la opción de
        # verla en una ventana aparte. Así lo de una tarea no pisa lo de otra.
        contenedor = ctk.CTkFrame(centro, fg_color="transparent")
        contenedor.grid(row=2, column=0, sticky="nsew")
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(1, weight=1)
        self._contenedor_prog = contenedor

        self.pestanas_prog = ctk.CTkFrame(contenedor, fg_color="transparent", height=34)
        self.pestanas_prog.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.pestanas_prog.grid_propagate(False)   # manda su ancho, no el de los botones
        self.pestanas_prog.bind("<Configure>", lambda e: self._colocar_pestanas())
        self.botones_prog_panel = {}
        self._zonas_prog = {}
        self._orden_zonas_prog = []

        self._crear_zona_clase(contenedor)
        # El chat del taller, en su propia zona (nace escondido: se entra por la
        # pestaña «Chat» o pulsando «Preguntar»).
        self.marco_chat_prog = self._crear_panel_chat(contenedor)
        self.marco_chat_prog.grid(row=1, column=0, sticky="nsew")
        self.marco_chat_prog.grid_remove()
        self._zonas_prog["chat"] = {
            "tipo": "chat", "marco": self.marco_chat_prog,
            "titulo": ZONAS_PROG["chat"][2], "icono": ZONAS_PROG["chat"][1],
            "ayuda": ZONAS_PROG["chat"][3], "pestana": ZONAS_PROG["chat"][0],
            "ventana": None,
        }
        self._orden_zonas_prog.append("chat")
        self._refrescar_pestanas()
        self._escribir_en_zona("clase", AYUDA_PROGRAMACION)

        # --- Derecha: la guía, en corto (lo mismo que los botones, con su porqué)
        derecha = ctk.CTkScrollableFrame(cuerpo, width=282, fg_color="transparent",
                                         **BARRA_SCROLL)
        derecha.grid(row=0, column=2, sticky="nsew")
        ctk.CTkLabel(derecha, text="\U0001F9ED  Asistencia y guía",
                     font=(tema.FUENTE_UI, 14, "bold"), text_color=COLOR_TEXTO,
                     anchor="w").pack(fill="x", padx=4, pady=(0, 10))
        self._tarjeta_guia(
            derecha, "\U0001F4D8", "Guía de uso",
            "El programa se escribe en la ventana del editor: ahí también se ejecuta "
            "y se ve lo que imprime.",
            "Ver la guía", lambda: self._escribir_programacion(AYUDA_PROGRAMACION), acento=True)
        self._tarjeta_guia(
            derecha, "\U0001F680", "Inicio rápido",
            "Empieza por el principio del temario: primer programa, variables y "
            "condicionales.",
            "Empezar por el principio", lambda: self._accion_programacion("bases"))
        self._tarjeta_guia(
            derecha, "\U0001F4AC", "Chat del taller",
            "Una conversación propia para indagar: te contesto con tu programa delante y "
            "me acuerdo de lo que ya hemos hablado.",
            "Abrir el chat", lambda: self.mostrar_panel_programacion("chat"))
        self._tarjeta_guia(
            derecha, "\u2753", "Preguntar",
            "Escribe la duda en «Tema» y la llevo al chat del taller, con tu código delante.",
            "Preguntar", self.preguntar_programacion)
        self._tarjeta_guia(
            derecha, "\U0001F4CA", "Mi avance",
            "Tu nivel, las prácticas corregidas y los fallos que más se te repiten.",
            "Ver mi avance", lambda: self._accion_programacion("progreso"))

        interior = self._tarjeta(
            derecha, "\u25B6", "Ejecutar el programa",
            "Al pulsar «Ejecutar» el programa corre de verdad y lo que imprima sale en "
            "la consola, con el código 0 si acaba bien.", ancho_texto=230,
            color_borde=COLOR_ACENTO)
        self.btn_prog_ejecutar = ctk.CTkButton(
            interior, text="\u25B6  Ejecutar", height=34, corner_radius=RADIO_CHIP,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO, font=(tema.FUENTE_UI, 12, "bold"),
            command=lambda: self._accion_programacion("probar"))
        self.btn_prog_ejecutar.pack(fill="x")
        ctk.CTkButton(interior, text="\u270F  Abrir el editor", height=32,
                      corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA,
                      hover_color=COLOR_HOVER, border_width=1, border_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
                      command=self.abrir_editor).pack(fill="x", pady=(6, 0))

        self._pintar_vista_previa()

    def _tarjeta_guia(self, parent, icono, titulo, ayuda, texto, accion, acento=False):
        """Una tarjeta corta de la guía: qué hace y su botón para probarlo."""
        interior = self._tarjeta(parent, icono, titulo, ayuda, ancho_texto=230,
                                 color_borde=COLOR_ACENTO if acento else None)
        boton = ctk.CTkButton(
            interior, text=texto, height=32, corner_radius=RADIO_CHIP,
            font=(tema.FUENTE_UI, 12),
            fg_color=COLOR_ACENTO if acento else COLOR_TARJETA_ALTA,
            hover_color=COLOR_ACENTO_HOVER if acento else COLOR_HOVER,
            border_width=0 if acento else 1, border_color=COLOR_BORDE,
            text_color=COLOR_ACENTO_TEXTO if acento else COLOR_TEXTO, command=accion)
        boton.pack(fill="x")
        return boton

    # ---------------- Las zonas del centro: una por tarea ----------------
    def _crear_zona_clase(self, parent):
        """Monta la zona de la clase: la guía, sus tarjetas y sus botones."""
        pestana, icono, titulo, ayuda = ZONAS_PROG["clase"]
        marco = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=COLOR_BORDE)
        marco.grid(row=1, column=0, sticky="nsew")
        self.marco_panel_prog = marco          # compat: es el panel de la clase
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(fila, text=icono, font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text=titulo, font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.btn_prog_ventana = ctk.CTkButton(
            fila, text="\u29C9  En ventana", width=118, height=30, corner_radius=RADIO_CHIP,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER, border_width=1,
            border_color=COLOR_BORDE, text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
            command=lambda: self.abrir_zona_en_ventana("clase"))
        self.btn_prog_ventana.pack(side="right")
        self.btn_prog_copiar = ctk.CTkButton(
            fila, text="\U0001F4CB", width=34, height=30, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=self._copiar_programacion)
        self.btn_prog_copiar.pack(side="right")
        self.btn_prog_guardar = ctk.CTkButton(
            fila, text="\U0001F4BE  Guardar", width=118, height=30, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=self._guardar_programacion)
        self.btn_prog_guardar.pack(side="right", padx=(0, 6))
        self.lbl_prog_zona = ctk.CTkLabel(
            marco, text="", font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE,
            anchor="w", justify="left", wraplength=560)
        self.lbl_prog_zona.pack(fill="x", padx=14, pady=(0, 4))

        self.scroll_prog = ctk.CTkScrollableFrame(marco, fg_color="transparent",
                                                  height=80, **BARRA_SCROLL)
        self.scroll_prog.pack(fill="both", expand=True, padx=6, pady=(2, 10))
        # Las listas de siempre (compatibilidad): son las mismas de la zona «clase».
        self._tarjetas_prog = []
        self._marcos_prog = []
        self._zonas_prog["clase"] = {
            "tipo": "tarjetas", "marco": marco, "scroll": self.scroll_prog,
            "tarjetas": self._tarjetas_prog, "marcos": self._marcos_prog,
            "texto": "", "titulo": titulo, "icono": icono, "ayuda": ayuda,
            "pestana": pestana, "lbl_estado": self.lbl_prog_zona,
            "btn_copiar": self.btn_prog_copiar, "btn_guardar": self.btn_prog_guardar,
            "ventana": None,
        }
        self._orden_zonas_prog.append("clase")
        return marco

    def _crear_zona_texto(self, parent, clave):
        """Monta la zona de una tarea: su pestaña, sus tarjetas y sus botones."""
        pestana, icono, titulo, ayuda = ZONAS_PROG[clave]
        marco = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=COLOR_BORDE)
        marco.grid(row=1, column=0, sticky="nsew")
        marco.grid_remove()             # nace escondida: se entra por su pestaña
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(fila, text=icono, font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text=titulo, font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        btn_ventana = ctk.CTkButton(
            fila, text="\u29C9  En ventana", width=118, height=30, corner_radius=RADIO_CHIP,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER, border_width=1,
            border_color=COLOR_BORDE, text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
            command=lambda c=clave: self.abrir_zona_en_ventana(c))
        btn_ventana.pack(side="right")
        btn_copiar = ctk.CTkButton(
            fila, text="\U0001F4CB", width=34, height=30, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=lambda c=clave: self.copiar_zona_programacion(c))
        btn_copiar.pack(side="right")
        btn_guardar = ctk.CTkButton(
            fila, text="\U0001F4BE  Guardar", width=118, height=30, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=lambda c=clave: self.guardar_zona_programacion(c))
        btn_guardar.pack(side="right", padx=(0, 6))
        lbl_estado = ctk.CTkLabel(
            marco, text=ayuda, font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE,
            anchor="w", justify="left", wraplength=560)
        lbl_estado.pack(fill="x", padx=14, pady=(0, 4))
        scroll = ctk.CTkScrollableFrame(marco, fg_color="transparent", height=80,
                                        **BARRA_SCROLL)
        scroll.pack(fill="both", expand=True, padx=6, pady=(2, 10))
        self._zonas_prog[clave] = {
            "tipo": "tarjetas", "marco": marco, "scroll": scroll,
            "tarjetas": [], "marcos": [], "texto": "",
            "titulo": titulo, "icono": icono, "ayuda": ayuda, "pestana": pestana,
            "lbl_estado": lbl_estado, "btn_copiar": btn_copiar,
            "btn_guardar": btn_guardar, "ventana": None,
        }
        self._orden_zonas_prog.append(clave)
        self._refrescar_pestanas()
        return marco

    def _refrescar_pestanas(self):
        """Redibuja las pestañas: primero la clase y el chat, luego las abiertas."""
        for boton in self.pestanas_prog.winfo_children():
            boton.destroy()
        self.botones_prog_panel = {}
        orden = [clave for clave in ("clase", "chat") if clave in self._zonas_prog]
        orden += [clave for clave in self._orden_zonas_prog if clave not in orden]
        self._orden_pestanas = orden
        for clave in orden:
            etiqueta = ZONAS_PROG.get(clave, (clave, "", clave, ""))[0]
            boton = ctk.CTkButton(
                self.pestanas_prog, text=etiqueta, width=104, height=30,
                corner_radius=RADIO_CHIP, border_width=1,
                font=(tema.FUENTE_UI, 11, "bold"),
                command=lambda p=clave: self._cambiar_panel_programacion(p))
            self.botones_prog_panel[clave] = boton
        self._colocar_pestanas()
        self._marcar_panel_programacion()

    def _colocar_pestanas(self):
        """Reparte las pestañas en filas según el ancho que tenga el centro.

        Las pestañas crecen con cada tarea abierta: así caben sin que el centro se
        estire ni se coma el sitio de la guía (la de la derecha).
        """
        botones = getattr(self, "botones_prog_panel", {})
        if not botones:
            return
        ancho = self.pestanas_prog.winfo_width()
        if ancho <= 1:
            ancho = self._contenedor_prog.winfo_width() if self._contenedor_prog else 0
        if ancho <= 1:
            ancho = 480
        columnas = max(2, min(5, int(ancho // 110)))
        orden = [clave for clave in getattr(self, "_orden_pestanas", [])
                 if clave in botones]
        for indice, clave in enumerate(orden):
            botones[clave].grid(row=indice // columnas, column=indice % columnas,
                                sticky="ew", padx=(0, 6), pady=(0, 4))
        for columna in range(5):
            self.pestanas_prog.grid_columnconfigure(columna, weight=1 if columna < columnas else 0)
        filas = max(1, (len(orden) + columnas - 1) // columnas)
        alto = filas * 34
        if int(self.pestanas_prog.cget("height")) != alto:
            self.pestanas_prog.configure(height=alto)

    def zonas_programacion(self):
        """Las zonas abiertas del taller (clave -> sus datos), para la ventana."""
        return self._zonas_prog

    def _abrir_zona(self, clave):
        """Asegura que la zona de esa tarea existe y la deja a la vista."""
        if clave not in self._zonas_prog:
            if clave not in ZONAS_PROG:
                clave = "clase"
            else:
                self._crear_zona_texto(self._contenedor_prog, clave)
        return self.mostrar_panel_programacion(clave)

    def abrir_zona_en_ventana(self, clave):
        """Abre (o trae al frente) la ventana aparte de una zona del taller.

        Es la misma zona que su pestaña, con lo mismo dentro: sirve para tener dos
        cosas a la vista a la vez (la lección y los ejercicios, por ejemplo). El
        chat no abre ventana: ya tiene su sitio en la pestaña «Chat».
        """
        clave = clave if clave in ZONAS_PROG else "clase"
        self._abrir_zona(clave)
        zona = self._zonas_prog.get(clave) or {}
        if zona.get("tipo") == "chat":
            return None
        ventana = zona.get("ventana")
        if ventana is not None:
            try:
                if ventana.winfo_exists():
                    ventana.deiconify()
                    ventana.lift()
                    ventana.focus_force()
                    return ventana
            except Exception:       # la ventana se cerró: se abre otra
                pass
        ventana = VentanaZonaProgramacion(self, clave, zona.get("texto") or "")
        zona["ventana"] = ventana
        return ventana

    # ---------------- El programa: dónde vive y cómo se enseña ----------------
    def codigo_programacion(self):
        """El programa del alumno, tal y como está en la ventana del editor."""
        return self.codigo_prog

    def entrada_programacion(self):
        """Lo que leerá el programa por teclado (un dato por línea)."""
        return self.txt_prog_entrada.get("1.0", "end-1c")

    def fijar_codigo_programacion(self, codigo, revisar=False):
        """Deja ese programa en el taller (lo escribe la ventana del editor).

        Se guarda el texto, se copia en la vista previa y, si se pide, se programa
        la revisión de siempre: la misma que se lanza sola al teclear.
        """
        self.codigo_prog = str(codigo or "")
        self._pintar_vista_previa()
        if revisar:
            self._revision_diferida()

    def fijar_entrada_programacion(self, entrada):
        """Deja en «Entrada» lo que leerá el programa (lo escribe el editor)."""
        self.txt_prog_entrada.delete("1.0", "end")
        self.txt_prog_entrada.insert("1.0", str(entrada or ""))

    def _pintar_vista_previa(self):
        """Copia el programa en la vista previa (aquí solo se lee: se escribe aparte)."""
        self._poner_texto(self.txt_prog_codigo, self.codigo_prog)

    @staticmethod
    def _poner_texto(caja, texto):
        """Deja un texto en una caja de solo lectura."""
        caja.configure(state="normal")
        caja.delete("1.0", "end")
        caja.insert("1.0", str(texto or ""))
        caja.configure(state="disabled")

    # ------------------------------------------------------------------
    # El chat del taller: una conversación propia, aparte de la de Jarvis
    # ------------------------------------------------------------------
    def mostrar_panel_programacion(self, panel="clase"):
        """Enseña una zona del centro (la que se pida; el chat también es una).

        Cada tarea tiene la suya: al abrirla no se pisa lo que hubiera en las
        demás, y el chat del taller sigue siendo una conversación aparte de la de
        Jarvis (no se toca ni una ni otra).
        """
        pedido = str(panel or "").strip().lower()
        if pedido.startswith(("chat", "\U0001F4AC")):
            clave = "chat"
        elif pedido.startswith(("clase", "\U0001F4DA")):
            clave = "clase"
        else:
            clave = pedido
        if clave not in self._zonas_prog:
            if clave in ZONAS_PROG:
                self._crear_zona_texto(self._contenedor_prog, clave)
            else:
                clave = "clase"
        self._panel_prog = clave
        for nombre, zona in self._zonas_prog.items():
            marco = zona.get("marco")
            if marco is None:
                continue
            if nombre == clave:
                marco.grid()
            else:
                marco.grid_remove()
        # El chat del taller se queda con todo el centro mientras conversas: la
        # revisión y la consola se apartan para no quitarle sitio (y vuelven al
        # abrir cualquier otra zona).
        for marco in (getattr(self, "marco_revision_prog", None),
                      getattr(self, "marco_consola_prog", None)):
            if marco is None:
                continue
            if clave == "chat":
                marco.grid_remove()
            else:
                marco.grid()
        try:
            self._marcar_panel_programacion()
        except Exception:
            pass                    # las pestañas aún no están montadas (o ya no existen)
        if clave == "chat":
            self.after(40, self._enfocar_chat_prog)
        return self._panel_prog

    def _marcar_panel_programacion(self):
        """Pinta las dos pestañas del centro: la puesta de acento, la otra como tarjeta.

        Es el mismo trato que el resto de la ventana: lo que está elegido va con el
        acento y el texto oscuro; lo demás, en tarjeta con su borde.
        """
        puesto = getattr(self, "_panel_prog", "clase")
        for clave, boton in getattr(self, "botones_prog_panel", {}).items():
            activo = clave == puesto
            try:
                boton.configure(
                    fg_color=COLOR_ACENTO if activo else COLOR_TARJETA,
                    hover_color=COLOR_ACENTO_HOVER if activo else COLOR_HOVER,
                    text_color=COLOR_ACENTO_TEXTO if activo else COLOR_TEXTO_SUAVE)
            except Exception:
                continue

    def _cambiar_panel_programacion(self, valor):
        """Lo que llega al pulsar una pestaña del centro (Clase / Chat)."""
        self.mostrar_panel_programacion(valor)

    def _enfocar_chat_prog(self):
        """Deja el cursor en la caja del chat del taller."""
        try:
            self.txt_chat_prog.focus_set()
        except Exception:
            pass

    def _crear_panel_chat(self, parent):
        """Monta la tarjeta del chat del taller: cabecera, mensajes y caja de escribir."""
        marco = ctk.CTkFrame(parent, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=COLOR_BORDE)
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(fila, text="\U0001F4AC", font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text="Chat del taller", font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.btn_chat_prog_nuevo = ctk.CTkButton(
            fila, text="\U0001F9F9  Nuevo", width=96, height=28,
            corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO_SUAVE,
            font=(tema.FUENTE_UI, 11), command=self.nuevo_chat_programacion)
        self.btn_chat_prog_nuevo.pack(side="right")
        ctk.CTkLabel(fila, text="te contesto con tu programa delante",
                     font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE,
                     anchor="w").pack(side="left", padx=(10, 0))

        # La caja de escribir se reserva abajo ANTES que los mensajes: si la ventana
        # se queda corta, se recorta la conversación (que ya tiene su barra), nunca
        # la entrada, que es lo que hace falta para poder usar el chat.
        self.chat_prog_scroll = ctk.CTkScrollableFrame(marco, fg_color="transparent",
                                                       height=80, **BARRA_SCROLL)
        caja = ctk.CTkFrame(marco, fg_color=COLOR_CODIGO, corner_radius=RADIO_CHIP,
                            border_width=1, border_color=COLOR_BORDE)
        caja.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        self.chat_prog_scroll.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self.txt_chat_prog = ctk.CTkTextbox(
            caja, height=52, wrap="word", fg_color="transparent", border_width=0,
            corner_radius=0, text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 13),
            scrollbar_button_color=COLOR_TARJETA_ALTA,
            scrollbar_button_hover_color=COLOR_ACENTO)
        self.txt_chat_prog.pack(side="left", fill="both", expand=True, padx=(10, 6), pady=8)
        self.txt_chat_prog._textbox.configure(spacing1=2, spacing3=2, padx=0, pady=2)
        rueda.acelerar_caja(self.txt_chat_prog)
        self.btn_chat_prog_enviar = ctk.CTkButton(
            caja, text="\u2191", width=34, height=34, corner_radius=17,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO, font=(tema.FUENTE_UI, 16, "bold"),
            command=self.enviar_chat_programacion)
        self.btn_chat_prog_enviar.pack(side="right", padx=(0, 8), pady=6)
        # Enter manda el mensaje; Mayús+Enter hace un salto de línea.
        self.txt_chat_prog.bind("<Return>", self._enviar_chat_prog_con_enter)
        self.txt_chat_prog.bind("<Shift-Return>", self._salto_chat_prog)
        self._atajos_caja(self.txt_chat_prog)
        self._pista_chat_prog = self._pintar_pista_chat_prog()
        return marco

    def _ancho_chat_prog(self):
        """Cuánto puede ocupar el texto de una burbuja del chat del taller (en px)."""
        ancho = 0
        for widget in (getattr(self, "marco_chat_prog", None),
                       getattr(self, "chat_prog_scroll", None)):
            try:
                ancho = max(ancho, int(widget.winfo_width()))
            except Exception:
                continue
        if ancho <= 1:
            ancho = 620            # todavía sin medir: un ancho de ventana normal
        return max(260, int(ancho * 0.62))

    def _pintar_pista_chat_prog(self):
        """La ayuda que se lee en el chat vacío (se quita con el primer mensaje)."""
        pista = ctk.CTkFrame(self.chat_prog_scroll, fg_color="transparent")
        pista.pack(fill="x", padx=10, pady=(4, 8))
        ctk.CTkLabel(pista, text="\U0001F393", width=28, height=28, corner_radius=14,
                     fg_color=_mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.18),
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 13)
                     ).pack(side="left", padx=(0, 6), anchor="n")
        tarjeta = ctk.CTkFrame(pista, fg_color=COLOR_TARJETA_ALTA, corner_radius=RADIO_TARJETA,
                              border_width=1, border_color=COLOR_BORDE)
        tarjeta.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(tarjeta, text="Profe", font=(tema.FUENTE_UI, 10, "bold"), anchor="w",
                     text_color=COLOR_ACENTO).pack(anchor="w", padx=12, pady=(8, 0))
        ancho = self._ancho_chat_prog()
        area = self._crear_area_markdown(tarjeta, COLOR_TARJETA_ALTA, alto=1, tam=12,
                                        columnas=self._columnas_markdown(ancho, 12))
        area.pack(fill="x", padx=12, pady=(2, 10))
        self._insertar_lineas(area, AYUDA_CHAT_PROG.splitlines())
        area.configure(state="disabled")
        self._ajustar_alto_tarjeta(area, minimo=1, maximo=240)
        area.bind("<Configure>", lambda e, a=area: self._ajustar_alto_tarjeta(a, 1, 240))
        self._permitir_rueda(area, self.chat_prog_scroll)
        return pista

    def _quitar_pista_chat_prog(self):
        """Quita la ayuda del chat en cuanto hay algo que leer de verdad."""
        pista = self._pista_chat_prog
        if pista is None:
            return
        self._pista_chat_prog = None
        try:
            pista.destroy()
        except Exception:
            pass


    def _agregar_burbuja_prog(self, autor, texto):
        """Añade un mensaje al chat del taller: tú a la derecha, el profe a la izquierda.

        Lo del profe se pinta con el mismo Markdown de las tarjetas (código,
        negritas, listas), así que una respuesta con un bloque de Java se lee igual
        que en la clase.
        """
        es_usuario = str(autor or "").strip().lower() in ("tú", "tu", "yo", "usuario")
        self._quitar_pista_chat_prog()
        fila = ctk.CTkFrame(self.chat_prog_scroll, fg_color="transparent")
        fila.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(fila, text="\U0001F464" if es_usuario else "\U0001F393",
                     width=28, height=28, corner_radius=14,
                     fg_color=COLOR_TARJETA_ALTA if es_usuario
                     else _mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.18),
                     text_color=COLOR_TEXTO_SUAVE if es_usuario else COLOR_ACENTO,
                     font=(tema.FUENTE_UI, 13)
                     ).pack(side="right" if es_usuario else "left",
                            padx=(6, 0) if es_usuario else (0, 6), anchor="n")
        burbuja = ctk.CTkFrame(
            fila, corner_radius=RADIO_TARJETA, border_width=1,
            fg_color=COLOR_USUARIO if es_usuario else COLOR_TARJETA_ALTA,
            border_color=_mezclar(COLOR_USUARIO, COLOR_ACENTO, 0.45) if es_usuario
            else COLOR_BORDE)
        burbuja.pack(side="right" if es_usuario else "left")
        ctk.CTkLabel(burbuja, text="Tú" if es_usuario else "Profe",
                     font=(tema.FUENTE_UI, 10, "bold"), anchor="w",
                     text_color=COLOR_TEXTO_SUAVE if es_usuario else COLOR_ACENTO
                     ).pack(anchor="w", padx=12, pady=(8, 0))
        ancho = self._ancho_chat_prog()
        if es_usuario:
            ctk.CTkLabel(burbuja, text=str(texto or ""), wraplength=ancho, justify="left",
                         anchor="w", font=(tema.FUENTE_UI, 12), text_color=COLOR_TEXTO
                         ).pack(anchor="w", padx=12, pady=(2, 10))
        else:
            area = self._crear_area_markdown(burbuja, COLOR_TARJETA_ALTA, alto=1, tam=12,
                                             columnas=self._columnas_markdown(ancho, 12))
            area.pack(fill="x", padx=12, pady=(2, 10))
            self._insertar_lineas(area, str(texto or "").splitlines())
            area.configure(state="disabled")
            self._ajustar_alto_tarjeta(area, minimo=1, maximo=240)
            area.bind("<Configure>", lambda e, a=area: self._ajustar_alto_tarjeta(a, 1, 240))
            self._permitir_rueda(area, self.chat_prog_scroll)
        self._burbujas_chat_prog.append((autor, texto))
        self.after(40, self._scroll_chat_prog)
        return burbuja

    def _scroll_chat_prog(self):
        """Deja el chat del taller abajo del todo (lo último que se ha dicho)."""
        try:
            self.chat_prog_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _pensando_chat_prog(self, activo=True):
        """Muestra (o quita) el «el profe está escribiendo…» del chat del taller.

        Mientras la IA piensa, el chat lo dice en su sitio, con los puntos que van
        latiendo: la ventana sigue viva y se puede seguir leyendo la clase.
        """
        if self._latido_prog is not None:
            try:
                self.after_cancel(self._latido_prog)
            except Exception:
                pass
            self._latido_prog = None
        if self._fila_pensando_prog is not None:
            try:
                self._fila_pensando_prog.destroy()
            except Exception:
                pass
            self._fila_pensando_prog = None
        if not activo:
            return None
        fila = ctk.CTkFrame(self.chat_prog_scroll, fg_color="transparent")
        fila.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkLabel(fila, text="\U0001F393", width=28, height=28, corner_radius=14,
                     fg_color=_mezclar(COLOR_TARJETA, COLOR_ACENTO, 0.18),
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 13)
                     ).pack(side="left", padx=(0, 6))
        self.lbl_pensando_prog = ctk.CTkLabel(
            fila, text="El profe está mirando tu código",
            font=(tema.FUENTE_UI, 12, "italic"), text_color=COLOR_TEXTO_SUAVE, anchor="w")
        self.lbl_pensando_prog.pack(side="left")
        self._fila_pensando_prog = fila
        self._latir_chat_prog(0)
        self._scroll_chat_prog()
        return fila

    def _latir_chat_prog(self, paso):
        """Los puntos suspensivos del «está mirando tu código…»."""
        if self._fila_pensando_prog is None:
            return
        try:
            self.lbl_pensando_prog.configure(
                text="El profe está mirando tu código" + "." * (paso % 3 + 1))
            self._latido_prog = self.after(420, lambda: self._latir_chat_prog(paso + 1))
        except Exception:
            self._latido_prog = None






    def enviar_chat_programacion(self, texto=None):
        """Manda una duda al profe por su chat y trae la respuesta.

        La duda sale de la caja del chat o, si se pasa, de lo que se haya escrito
        (el botón «Preguntar» reutiliza lo de «Tema»). El hilo se guarda en el
        taller, así que la siguiente pregunta se contesta con lo ya hablado.
        """
        duda = str(texto if texto is not None else self._texto_chat_prog()).strip()
        if not duda:
            self._estado_programacion(
                "Escribe tu duda en el chat del taller y te la contesto.", COLOR_AVISO)
            self.mostrar_panel_programacion("chat")
            return ""
        self.mostrar_panel_programacion("chat")
        self._limpiar_chat_prog()
        self._hilo_prog = self._hilo_prog[-MAX_TURNOS_CHAT_PROG:]
        hilo = list(self._hilo_prog)            # lo hablado *antes* de esta pregunta
        self._agregar_burbuja_prog("Tú", duda)
        self._apuntar_turno_chat("Tú", duda)
        encargo = str(self.app.system.programacion.conversar(
            duda, self.codigo_prog, hilo) or "")
        if not encargo.startswith(MARCA_PROFE):
            # Lo que el taller contesta sin IA (por ejemplo, la pista de qué escribir).
            self._agregar_burbuja_prog("Profe", encargo)
            self._apuntar_turno_chat("Profe", encargo)
            self._estado_programacion("Esto lo tengo escrito yo: no ha hecho falta la IA.")
            return encargo
        self._estado_programacion("Pensando la respuesta\u2026")
        self._pensando_chat_prog(True)
        threading.Thread(target=self._pedir_chat_prog,
                         args=(encargo[len(MARCA_PROFE):],), daemon=True).start()
        return encargo

    def _pedir_chat_prog(self, encargo):
        """Pide la respuesta al cerebro (en su hilo) y la trae al chat del taller."""
        try:
            respuesta = self.app.brain.analizar_documento(
                encargo, sistema=APIBrain.SISTEMA_PROGRAMADOR)
        except Exception as error:
            respuesta = ""
            print(f"No pude preguntar al profe de programación: {error}")
        self.after(0, lambda: self._mostrar_chat_prog(respuesta))

    def _mostrar_chat_prog(self, respuesta):
        """Pinta la respuesta del profe en el chat (ya en el hilo de la ventana)."""
        self._pensando_chat_prog(False)
        texto = str(respuesta or "").strip()
        if texto:
            self._estado_programacion(f"Listo ({_hora_actual()}).")
        else:
            texto = SIN_RESPUESTA_PROG
            self._estado_programacion("No hubo respuesta de la IA.", COLOR_AVISO)
        self._agregar_burbuja_prog("Profe", texto)
        self._apuntar_turno_chat("Profe", texto)
        self._enfocar_chat_prog()

    def preguntar_programacion(self):
        """«Preguntar»: lleva la duda de «Tema» al chat del taller (o lo abre)."""
        tema = self.entry_prog_tema.get().strip()
        self.mostrar_panel_programacion("chat")
        if not tema:
            self._estado_programacion(
                "Escríbeme la duda en el chat del taller y te la contesto con tu código.")
            self._enfocar_chat_prog()
            return ""
        return self.enviar_chat_programacion(tema)

    def _texto_chat_prog(self):
        """Lo que hay escrito en la caja del chat del taller."""
        try:
            return self.txt_chat_prog.get("1.0", "end-1c").strip()
        except Exception:
            return ""

    def _limpiar_chat_prog(self):
        """Vacía la caja de escribir del chat del taller."""
        try:
            self.txt_chat_prog.delete("1.0", "end")
        except Exception:
            pass

    def _enviar_chat_prog_con_enter(self, evento=None):
        """Enter manda el mensaje del chat (Mayús+Enter hace un salto de línea)."""
        if evento is not None and (evento.state & 0x0001):     # Mayús pulsada
            return None
        self.enviar_chat_programacion()
        return "break"

    def _salto_chat_prog(self, evento=None):
        """Mayús+Enter: un salto de línea dentro del mensaje, sin mandarlo."""
        try:
            self.txt_chat_prog.insert("insert", "\n")
        except Exception:
            pass
        return "break"

    def texto_chat_programacion(self):
        """Lo que se lee en el chat del taller, en texto plano (para las pruebas).

        Es la ayuda de entrada (si sigue puesta) más lo que han dicho el alumno y el
        profe, en orden: lo mismo que se ve en su panel.
        """
        trozos = [f"{autor}: {texto}" for autor, texto in self._burbujas_chat_prog]
        if self._pista_chat_prog is not None:
            trozos.insert(0, f"Profe: {AYUDA_CHAT_PROG}")
        return "\n\n".join(trozos).strip()

    def conversacion_programacion(self):
        """Lo que se ha dicho en el chat del taller, en orden ([(quién, texto)])."""
        return [(autor, texto) for autor, texto in self._burbujas_chat_prog]


    def nuevo_chat_programacion(self):
        """Empieza un chat limpio en el taller (la conversación anterior queda guardada)."""
        self._pensando_chat_prog(False)
        for widget in self.chat_prog_scroll.winfo_children():
            widget.destroy()
        self._burbujas_chat_prog = []
        self._hilo_prog = []
        self._chat_prog_ruta = None
        self._limpiar_chat_prog()
        self._pista_chat_prog = self._pintar_pista_chat_prog()
        self._estado_programacion("Chat nuevo: pregunta lo que quieras del taller.")
        self.mostrar_panel_programacion("chat")
        return []

    def _apuntar_turno_chat(self, autor, texto):
        """Apunta un turno en el hilo (para seguir hablando) y en su archivo."""
        self._hilo_prog.append((autor, texto))
        self._hilo_prog = self._hilo_prog[-MAX_TURNOS_CHAT_PROG:]
        try:
            if self._chat_prog_ruta is None:
                self._chat_prog_ruta = self._ruta_chat_prog()
            with open(self._chat_prog_ruta, "a", encoding="utf-8") as archivo:
                archivo.write(f"**[{_hora_actual()}] {autor}:** {texto}\n\n")
        except OSError as error:
            print(f"No pude guardar el chat del taller: {error}")

    def _ruta_chat_prog(self):
        """Un archivo por conversación del taller, en la carpeta del propio taller.

        Así el chat del módulo se guarda junto a su avance (y no se mezcla con los
        chats de la conversación de Jarvis).
        """
        try:
            carpeta = self.app.system.programacion.carpeta
        except Exception:
            carpeta = rutas.PROGRAMACION
        try:
            os.makedirs(carpeta, exist_ok=True)
        except OSError:
            pass
        inicio = os.path.join(carpeta, "chat_taller_" + datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        ruta = inicio + ".md"
        numero = 2
        while os.path.exists(ruta):
            ruta = f"{inicio}_{numero}.md"
            numero += 1
        return ruta




    def abrir_editor(self):
        """Abre (o trae al frente) la ventana del editor con el programa de ahora."""
        if getattr(self, "_editor", None) is not None:
            try:
                if self._editor.winfo_exists():
                    self._editor.deiconify()
                    self._editor.lift()
                    self._editor.focus_force()
                    return self._editor
            except Exception:       # la ventana se cerró: se abre otra
                pass
        self._editor = VentanaEditorCodigo(self)
        return self._editor

    def guardar_java(self):
        """Guarda el programa como `.java` en la carpeta de documentos."""
        if not self.codigo_prog.strip():
            self._estado_programacion("Escribe el programa antes de guardarlo.", COLOR_AVISO)
            return ""
        try:
            os.makedirs(rutas.DOCUMENTOS, exist_ok=True)
            ruta = os.path.join(rutas.DOCUMENTOS, f"{nombre_de_clase(self.codigo_prog)}.java")
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(self.codigo_prog)
        except OSError as error:
            self._estado_programacion(f"No pude guardarlo: {error}", COLOR_AVISO)
            return ""
        self._estado_programacion(f"Guardado en {ruta}", COLOR_OK)
        return ruta

    def corregir_programacion(self):
        """Pasa el compilador de verdad y deja el resultado en su propia zona."""
        self._estado_programacion("Pasando el compilador…")
        datos = self._revisar_programacion(compilar=True, apuntar=True)
        self._escribir_en_zona("revision", datos.get("texto") or "")
        cabecera = self._avisos_de_revision(datos).splitlines()[0]
        self._zona_estado("revision", cabecera,
                          COLOR_OK if not datos.get("errores") else COLOR_AVISO)
        return datos

    def _escribir_programacion(self, texto):
        """Enseña un texto en la zona que esté pidiendo el turno (la clase si no).

        Lo de siempre (la corrección, la ayuda, una clase) va a la zona «clase»;
        las tareas escriben en la suya con `_escribir_en_zona`, para que una no
        pise a otra.
        """
        return self._escribir_en_zona(getattr(self, "_zona_destino", None) or "clase",
                                      texto)

    def _escribir_en_zona(self, clave, texto, mostrar=True):
        """Escribe en la zona de una tarea: su pestaña y su ventana, si está abierta.

        El Markdown se trocea por sus títulos, igual que la clase de inglés: cada
        apartado es una tarjeta con su icono y los ejemplos van en monoespaciada.
        """
        if clave not in ZONAS_PROG:
            clave = "clase"
        if clave not in self._zonas_prog:
            self._crear_zona_texto(self._contenedor_prog, clave)
        zona = self._zonas_prog[clave]
        if zona.get("tipo") == "chat":
            return ""
        texto = str(texto or "")
        zona["texto"] = texto
        if clave == "clase":
            self._clase_prog = texto
        self._pintar_tarjetas(zona["scroll"], texto, zona["tarjetas"], zona["marcos"])
        listos = "normal" if texto else "disabled"
        for boton in (zona.get("btn_copiar"), zona.get("btn_guardar")):
            try:
                boton.configure(state=listos)
            except Exception:
                pass
        ventana = zona.get("ventana")
        if ventana is not None:
            try:
                if ventana.winfo_exists():
                    ventana.actualizar(texto)
                else:
                    zona["ventana"] = None
            except Exception:
                zona["ventana"] = None
        if mostrar:
            self.mostrar_panel_programacion(clave)
        return texto

    def _zona_estado(self, clave, texto, color=None):
        """Dice en una zona (y en su ventana, si está abierta) qué está pasando."""
        zona = self._zonas_prog.get(clave)
        if not zona:
            return
        etiqueta = zona.get("lbl_estado")
        if etiqueta is not None:
            try:
                etiqueta.configure(text=str(texto or ""),
                                   text_color=color or COLOR_TEXTO_SUAVE)
            except Exception:
                pass
        ventana = zona.get("ventana")
        if ventana is not None:
            try:
                if ventana.winfo_exists():
                    ventana.estado(texto, color)
            except Exception:
                zona["ventana"] = None

    def texto_programacion_visible(self):
        """Lo que se está viendo en la zona abierta, en texto plano (pruebas)."""
        zona = self._zonas_prog.get(getattr(self, "_panel_prog", "clase"))
        if not zona:
            zona = self._zonas_prog.get("clase") or {}
        trozos = [f"{titulo}\n{area.get('1.0', 'end-1c').strip()}"
                  for titulo, area in zona.get("tarjetas") or []]
        return "\n\n".join(trozos).strip()

    def _estado_programacion(self, texto, color=None):
        """Escribe en la línea de estado del taller qué está pasando."""
        self.lbl_prog_estado.configure(text=texto, text_color=color or COLOR_TEXTO_SUAVE)

    def _actualizar_programacion(self):
        """Refresca la cabecera del taller con cómo va el alumno."""
        resumen = self.app.system.programacion.resumen()
        self.menu_prog_nivel.set(resumen["nivel"])
        partes = [f"Nivel {resumen['nivel']}", f"{resumen['practicas']} prácticas"]
        if resumen["desde"]:
            partes[-1] += f" desde {resumen['desde']}"
        repetidos = resumen["repetidos"]
        if repetidos:
            nombres = ", ".join((datos.get("titulo") or clave) for clave, datos in repetidos[:3])
            partes.append(f"lo que más se te repite: {nombres}")
        else:
            partes.append("todavía sin fallos apuntados")
        self.lbl_prog_resumen.configure(text=" \u00b7 ".join(partes))
        # El JDK se dice donde se mira la revisión: es lo que decide si se compila
        # de verdad o solo se revisa lo básico.
        self.lbl_prog_jdk.configure(
            text="JDK instalado: compila y ejecuta de verdad" if resumen["jdk"]
            else "sin JDK: revisión básica")

    def _cambiar_nivel_programacion(self, nivel):
        """Fija el nivel del alumno desde el desplegable del taller."""
        if nivel != self.app.system.programacion.nivel():
            self.app.system.programacion.fijar_nivel(nivel)
            self._estado_programacion(f"Nivel {nivel}: explico y corrijo con esa dificultad.")
        self._actualizar_programacion()

    # ---------------- La corrección: analizador propio + javac ----------------
    def _revision_diferida(self):
        """Programa la revisión de lo escrito (una sola vez por pausa al teclear).

        Se escribe mucho más deprisa de lo que se revisa: en vez de analizar en cada
        tecla, se espera a que el alumno pare un momento. Así el panel se actualiza
        al momento sin que el editor se note pesado.
        """
        if self._revision_prog is not None:
            try:
                self.after_cancel(self._revision_prog)
            except Exception:
                pass
        self._revision_prog = self.after(700, self._revision_al_escribir)

    def _revision_al_escribir(self):
        """La revisión que se lanza sola mientras se escribe (sin compilar)."""
        self._revision_prog = None
        try:
            self._revisar_programacion(compilar=False)
        except Exception as error:      # que un fallo del analizador no rompa la ventana
            print(f"No pude revisar el código: {error}")

    def _revisar_programacion(self, compilar=False, apuntar=False):
        """Revisa el programa del editor y lo enseña en el panel de la revisión.

        La revisión de mientras se escribe es local y gratis (``compilar=False``);
        «Corregir» pasa además el `javac` de verdad y apunta los fallos al avance
        del alumno. Devuelve el diccionario de `ProgrammingTutor.revisar`.
        """
        tutor = self.app.system.programacion
        codigo = self.codigo_prog
        try:
            datos = tutor.revisar(codigo, compilar=compilar)
        except Exception as error:      # el taller nunca debe romper la ventana
            print(f"No pude revisar el código: {error}")
            return {"ok": True, "errores": [], "compilado": False, "jdk": tutor.hay_jdk(),
                    "total": 0, "texto": f"No pude revisar el código: {error}"}
        self._pintar_avisos(self._avisos_de_revision(datos))
        if apuntar and codigo.strip():
            tutor.registrar(datos["errores"], "revisión del editor")
            self._actualizar_programacion()
        self._decir_como_va(datos, codigo, compilar)
        return datos

    def _decir_como_va(self, datos, codigo, compilar):
        """La línea de estado de la revisión: qué se ha hecho y qué se ha visto."""
        if not codigo.strip():
            self._estado_programacion("Escribe tu programa y lo reviso al momento.")
            return
        if datos["errores"]:
            cuantos = len(datos["errores"])
            self._estado_programacion(
                f"{cuantos} aviso(s): mira la línea y la columna.", COLOR_AVISO)
        elif compilar:
            self._estado_programacion("Revisado con el compilador: nada que corregir.",
                                      COLOR_OK)
        else:
            self._estado_programacion(
                "Revisión rápida: nada que corregir (pulsa «Corregir» para compilarlo).",
                COLOR_OK)

    def _pintar_avisos(self, texto):
        """Escribe en el panel de la revisión (es de solo lectura)."""
        self.txt_prog_avisos.configure(state="normal")
        self.txt_prog_avisos.delete("1.0", "end")
        self.txt_prog_avisos.insert("1.0", str(texto or ""))
        self.txt_prog_avisos.configure(state="disabled")

    @staticmethod
    def _avisos_de_revision(datos):
        """La revisión en texto llano, con la línea y la columna de cada fallo.

        Los avisos van en un `CTkTextbox` (no en las tarjetas del Markdown): aquí
        interesa la lista, apretada y copiable, para ir arreglando de arriba abajo.
        """
        fallos = datos.get("errores") or []
        graves = sum(1 for fallo in fallos if fallo.get("gravedad") == "error")
        avisos = len(fallos) - graves
        if not fallos:
            cabecera = "\u2705 Nada que corregir"
        elif graves:
            cabecera = f"\u274C {graves} fallo(s)"
            if avisos:
                cabecera += f" y {avisos} aviso(s)"
        else:
            cabecera = f"\u26A0 {avisos} aviso(s): el código compila"
        if not datos.get("jdk"):
            cabecera += "  \u00b7  sin JDK: revisión básica"
        lineas = [cabecera]
        for fallo in fallos[:MAX_AVISOS_PANTALLA]:
            icono = "\u26A0" if fallo.get("gravedad") == "aviso" else "\u274C"
            donde = f"línea {fallo['linea']}"
            if fallo.get("columna"):
                donde += f", columna {fallo['columna']}"
            lineas.append(f"{icono} {donde} {chr(183)} {fallo['mensaje']}")
            if fallo.get("sugerencia"):
                lineas.append(f"      \u2192 {fallo['sugerencia']}")
        if len(fallos) > MAX_AVISOS_PANTALLA:
            lineas.append(f"\u2026 y {len(fallos) - MAX_AVISOS_PANTALLA} más")
        return "\n".join(lineas)

    # ---------------- Las tareas del taller ----------------
    def _accion_programacion(self, tarea):
        """Prepara una tarea del taller y la trae a su propia zona (sin tocar el chat).

        `ProgrammingTutor` devuelve siempre texto: o lo que ya tiene escrito en sus
        tablas —temario, lección, documentación, comparaciones y el avance—, que se
        enseña tal cual y **no gasta IA**, o el *encargo* para la IA, marcado con
        `MARCA_PROFE`. Los encargos se piden al cerebro con el mensaje de sistema
        del profesor de programación en un hilo aparte, para que la ventana no se
        quede congelada mientras se escribe la respuesta.
        """
        tutor = self.app.system.programacion
        codigo = self.codigo_prog
        entrada = self.entrada_programacion()
        tema = self.entry_prog_tema.get().strip()
        cuantos = self.menu_prog_cantidad.get()
        if tarea != TAREA_PROG_PELIGRO:
            self._prog_borrar_pendiente = False

        zona = ZONA_DE_TAREA.get(tarea, "clase")
        if tarea == TAREA_PROG_PRINCIPAL:
            # Corregir de verdad: el analizador propio y, si hay JDK, el `javac`.
            # El resultado va a su zona, para no pisar la lección ni el avance.
            self._abrir_zona(zona)
            self.corregir_programacion()
            return
        if tarea == "probar":
            # Compilar y ejecutar tarda (hasta TIEMPO_EJECUTAR si el programa se
            # cuelga): va en un hilo para que la ventana siga respondiendo.
            self._abrir_zona(zona)
            self.ejecutar_programacion()
            return
        if tarea == "preguntar":
            # Las dudas van por su propio chat: el taller tiene una conversación
            # aparte de la de Jarvis, así que aquí solo se abre y se lleva la duda.
            self.preguntar_programacion()
            return
        self._abrir_zona(zona)          # cada tarea, en su propia zona
        if tarea == "bases":
            resultado = tutor.bases()
        elif tarea == "leccion":
            resultado = tutor.leccion(tema)
        elif tarea == "documentacion":
            resultado = tutor.documentacion(tema)
        elif tarea == "comparar":
            resultado = tutor.comparar(tema)
        elif tarea == "ejercicios":
            resultado = tutor.ejercicios(tema, cuantos)
        elif tarea == "preguntar":
            # Ya no llega aquí (se atiende arriba, en su chat), pero el tutor sigue
            # sabiendo contestar una duda suelta sin conversación.
            resultado = tutor.preguntar(tema, codigo)
        elif tarea == "progreso":
            resultado = tutor.progreso()
        else:                       # borrar el avance: se confirma la segunda vez
            if not self._prog_borrar_pendiente:
                self._prog_borrar_pendiente = True
                self._estado_programacion(
                    "Pulsa otra vez «Borrar» si de verdad quieres empezar de cero.",
                    COLOR_AVISO)
                return
            self._prog_borrar_pendiente = False
            resultado = tutor.progreso("borrar")

        self._actualizar_programacion()
        resultado = str(resultado or "")
        if not resultado.startswith(MARCA_PROFE):
            # Lo que ya está en sus tablas: se lee sin conexión y sin gastar IA.
            self._escribir_en_zona(zona, resultado)
            self._zona_estado(zona, "Esto ya viene escrito en mis tablas: sin gastar IA.")
            self._estado_programacion("Esto ya viene escrito en mis tablas: sin gastar IA.")
            return
        self._zona_estado(zona, "Escribiendo con la IA…")
        self._estado_programacion("Escribiendo con la IA…")
        threading.Thread(target=self._pedir_al_profe,
                         args=(resultado[len(MARCA_PROFE):], zona), daemon=True).start()

    def _pedir_al_profe(self, encargo, zona="clase"):
        """Pide al cerebro la explicación (hilo de trabajo) y la trae a su zona."""
        try:
            respuesta = self.app.brain.analizar_documento(encargo,
                                                      sistema=APIBrain.SISTEMA_PROGRAMADOR)
        except Exception as error:
            respuesta = ""
            print(f"No pude preparar la explicación de programación: {error}")
        self.after(0, lambda: self._mostrar_programacion_ia(respuesta, zona))

    def _mostrar_programacion_ia(self, respuesta, zona="clase"):
        """Pinta lo que ha contestado la IA en su zona (hilo de Tk).

        No se cambia de pestaña: si mientras la IA escribía te has ido a otra
        zona, la respuesta espera en la suya (y en su ventana, si está abierta).
        """
        if not respuesta:
            self._escribir_en_zona(
                zona,
                "No pude preparar la explicación con la IA: revisa tu API Key (DeepSeek) en "
                "Ajustes y vuelve a pedírmela.\n\n"
                "Lo demás sigue funcionando sin conexión: la revisión del código con su línea "
                "y su columna, el temario, las lecciones, la documentación, las comparaciones "
                "y tu avance.", mostrar=False)
            self._zona_estado(zona, "No hubo respuesta de la IA.", COLOR_AVISO)
            self._estado_programacion("No hubo respuesta de la IA.", COLOR_AVISO)
            return
        self._escribir_en_zona(zona, respuesta, mostrar=False)
        listo = f"Listo ({datetime.now().strftime('%H:%M')})."
        self._zona_estado(zona, listo, COLOR_OK)
        self._estado_programacion(listo, COLOR_OK)

    def ejecutar_programacion(self, al_terminar=None):
        """Compila y ejecuta el programa en un hilo (la ventana sigue respondiendo).

        ``al_terminar`` es a quién se le avisa al acabar con lo que ha pasado: la
        ventana del editor lo usa para escribir en su consola; el taller, para lo
        suyo. Lo que imprima el programa se enseña en la consola del taller.
        """
        if not self.codigo_prog.strip():
            self._estado_programacion("Escribe el programa antes de ejecutarlo.", COLOR_AVISO)
            self._consola_estado("sin programa", COLOR_AVISO)
            if al_terminar is not None:     # la ventana del editor espera respuesta
                al_terminar({"ok": False, "salida": "", "errores": [], "compilado": False,
                             "jdk": True, "texto": "No hay programa que ejecutar."})
            return
        clase = nombre_de_clase(self.codigo_prog)
        self._estado_programacion("Compilando y ejecutando tu programa…")
        self._consola_estado("ejecutando…", COLOR_ACENTO)
        limpiar_consola(self.txt_prog_consola)
        escribir_consola(self.txt_prog_consola,
                         f"$ javac {clase}.java\n$ java {clase}\n", "prompt")
        if hasattr(self, "btn_prog_ejecutar"):
            self.btn_prog_ejecutar.configure(state="disabled")
        threading.Thread(target=self._probar_programacion,
                         args=(self.codigo_prog, self.entrada_programacion(), al_terminar),
                         daemon=True).start()

    def _probar_programacion(self, codigo, entrada, al_terminar=None):
        """Compila y ejecuta el programa fuera del hilo de la ventana."""
        try:
            datos = self.app.system.programacion.ejecutar(codigo, entrada)
        except Exception as error:      # que un fallo del JDK no rompa la ventana
            datos = {"ok": False, "salida": "", "errores": [], "compilado": False,
                     "jdk": True, "texto": f"No pude probar el programa: {error}"}
        self.after(0, lambda: self._entregar_ejecucion(datos, al_terminar))

    def _entregar_ejecucion(self, datos, al_terminar=None):
        """Enseña lo que ha hecho el programa y, si no compiló, sus fallos."""
        if datos.get("errores"):
            self._pintar_avisos(self._avisos_de_revision(datos))
        self._pintar_consola(datos)
        self._escribir_en_zona("probar", datos.get("texto") or "El programa no dijo nada.",
                               mostrar=False)
        if datos.get("ok"):
            self._zona_estado("probar", "Salió bien: eso es lo que imprimió.", COLOR_OK)
            self._estado_programacion("El programa funcionó: mira lo que imprimió.", COLOR_OK)
        else:
            self._zona_estado("probar", "Mira la consola: hay algo que arreglar.", COLOR_AVISO)
            self._estado_programacion("Mira la salida: hay algo que arreglar.", COLOR_AVISO)
        if hasattr(self, "btn_prog_ejecutar"):
            self.btn_prog_ejecutar.configure(state="normal")
        if al_terminar is not None:
            al_terminar(datos)

    def _pintar_consola(self, datos):
        """Enseña en la consola del taller lo que ha impreso el programa."""
        limpiar_consola(self.txt_prog_consola)
        if not datos.get("jdk"):
            escribir_consola(self.txt_prog_consola,
                             "Sin el JDK de Java no se puede compilar ni ejecutar: instálalo "
                             "y vuelve a probar.\n", "aviso")
            self._consola_estado("sin JDK", COLOR_AVISO)
            return
        if datos.get("errores") and not datos.get("compilado"):
            escribir_consola(self.txt_prog_consola, "Todavía no compila:\n", "error")
            escribir_consola(self.txt_prog_consola,
                             self._avisos_de_revision(datos) + "\n", "error")
            self._consola_estado("no compila", COLOR_PELIGRO)
            return
        salida = (datos.get("salida") or "").rstrip()
        if salida:
            escribir_consola(self.txt_prog_consola, salida + "\n", "salida")
        elif not datos.get("ok"):
            # Se colgó o se cayó antes de imprimir: se cuenta lo que pasó.
            escribir_consola(self.txt_prog_consola, (datos.get("texto") or "") + "\n", "aviso")
        else:
            escribir_consola(self.txt_prog_consola, "(el programa no imprimió nada)\n", "info")
        if datos.get("ok"):
            escribir_consola(self.txt_prog_consola, "[terminó bien: código 0]\n", "ok")
            self._consola_estado("código 0", COLOR_OK)
        else:
            escribir_consola(self.txt_prog_consola, "[terminó con un error]\n", "error")
            self._consola_estado("con errores", COLOR_AVISO)

    def _consola_estado(self, texto, color=None):
        """El estado de la consola: sin ejecutar, ejecutando, código 0…"""
        self.lbl_prog_consola.configure(text=texto, text_color=color or COLOR_TEXTO_SUAVE)

    def _limpiar_consola(self):
        """Vacía la consola del taller (el programa no se toca)."""
        limpiar_consola(self.txt_prog_consola)
        self._consola_estado("sin ejecutar")

    # ---------------- Copiar y guardar lo de una zona ----------------
    def copiar_zona_programacion(self, clave):
        """Copia el texto de una zona al portapapeles (dice si había algo)."""
        zona = self._zonas_prog.get(clave) or {}
        texto = zona.get("texto") or ""
        if not texto:
            self._zona_estado(clave, "Todavía no hay nada que copiar.", COLOR_AVISO)
            return False
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._zona_estado(clave, "Copiado al portapapeles.", COLOR_OK)
        return True

    def guardar_zona_programacion(self, clave):
        """Guarda una zona como `.md` en documentos y devuelve la ruta (o "")."""
        zona = self._zonas_prog.get(clave) or {}
        texto = zona.get("texto") or ""
        if not texto:
            self._zona_estado(clave, "Todavía no hay nada que guardar.", COLOR_AVISO)
            return ""
        try:
            os.makedirs(rutas.DOCUMENTOS, exist_ok=True)
            nombre = (f"{zona.get('titulo') or 'Programación'} "
                      f"{datetime.now().strftime('%Y-%m-%d %H-%M')}.md")
            ruta = os.path.join(rutas.DOCUMENTOS, nombre)
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(texto)
        except OSError as error:
            self._zona_estado(clave, f"No pude guardarlo: {error}", COLOR_AVISO)
            return ""
        self._zona_estado(clave, f"Guardado en {ruta}", COLOR_OK)
        return ruta

    def _copiar_programacion(self):
        """Copia lo que se está viendo al portapapeles."""
        if not self._clase_prog:
            return
        self.clipboard_clear()
        self.clipboard_append(self._clase_prog)
        self._estado_programacion("Copiado al portapapeles.")

    def _guardar_programacion(self):
        """Guarda lo que se está viendo como .md en la carpeta de documentos."""
        if not self._clase_prog:
            return
        try:
            os.makedirs(rutas.DOCUMENTOS, exist_ok=True)
            nombre = f"Programación {datetime.now().strftime('%Y-%m-%d %H-%M')}.md"
            ruta = os.path.join(rutas.DOCUMENTOS, nombre)
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(self._clase_prog)
        except OSError as error:
            self._estado_programacion(f"No pude guardarlo: {error}", COLOR_AVISO)
            return
        self._estado_programacion(f"Guardado en {ruta}")
