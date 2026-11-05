"""Apartado del chat: la conversación, los adjuntos y la barra de escribir.

Aquí vive todo lo que pasa en el chat: las burbujas con su icono, la barra de
entrada (que crece con el mensaje y lleva micrófono y adjuntos), el indicador de
lo que está haciendo el asistente con sus pasos, la barra de selección para
copiar o guardar trozos, el mini-explorador de archivos y el envío a la IA.

El apartado no sabe nada de la ventana: cuando necesita cambiar de vista, hablar
o mirar la configuración, se lo pide a `self.app` (la ventana, ver `app_gui.py`).
"""
import os
import re
import threading
import time
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from modules.ocr_engine import motor as ocr_motor, ocr_imagen
from modules import rutas
from ui import tema
from ui import scroll as rueda
from ui.tema import (
    ALTO_INPUT_LINEA, ALTO_INPUT_LINEAS_MAX, ALTO_INPUT_MIN, AVISO_INPUT,
    BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_2, COLOR_ACENTO_HOVER,
    COLOR_ACENTO_TEXTO, COLOR_AVISO, COLOR_BORDE, COLOR_FONDO, COLOR_HOVER,
    COLOR_OK, COLOR_PANEL, COLOR_TARJETA, COLOR_TARJETA_ALTA, COLOR_TEXTO,
    COLOR_TEXTO_SUAVE, COLOR_USUARIO, RADIO_CHIP, RADIO_TARJETA, _mezclar,
)

from views.base import Vista

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

# ---------------- Ubicaciones (rutas/URLs) citadas en los mensajes ----------------
# Se detectan para ofrecer un botón que las abra con un solo clic.
RE_UBICACION = re.compile(
    r'"([A-Za-z]:[\\/][^"\r\n]+)"'        # "C:\ruta con espacios\archivo.txt"
    r'|`([A-Za-z]:[\\/][^`\r\n]+)`'       # `C:\ruta\archivo.txt`
    r'|(\\\\[^\s<>"\'`)\]]+)'             # \\servidor\recurso\archivo.txt (UNC)
    r'|([A-Za-z]:[\\/][^\s<>"\'`)\]]*)'   # C:\ruta\archivo.txt (sin espacios)
    r'|(https?://[^\s<>"\'`)\]]+)'        # https://ejemplo.com
)


class VistaChat(Vista):
    """El chat con Jarvis: la conversación de siempre, con su barra de escribir."""

    nombre = "chat"

    def _preparar(self):
        """Estado del chat: el hilo abierto, las burbujas y lo que se está enviando."""
        self.chat_activo = None      # None = sin definir, False = bienvenida, True = conversación
        self._procesando = False
        self._ind_pensando = None
        self._lbl_pensando = None    # rótulo "Jarvis está trabajando (0:12)"
        self._lbl_pulso = None       # punto que late a su lado
        self._marco_pasos = None     # caja donde van cayendo los pasos
        self._pasos = []             # [(tipo, texto)] de la tarea en curso
        self._tarea_inicio = None    # cuándo empezó (para el reloj del indicador)
        self._pegado_abajo = True    # True si el usuario está viendo el final del chat
        self.adjuntos = []           # lista de dicts con los archivos adjuntos pendientes
        self._burbujas = []          # registros de las burbujas visibles (para selección)
        self._seleccion = []         # registros de las burbujas seleccionadas
        self.conversacion_actual = None  # ruta del archivo de la conversación activa
        os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)

        # Lo que va haciendo el asistente se ve en el chat: el chat escucha el
        # canal de progreso de las acciones (SharePoint, IA, correo...) y lo pinta
        # en el indicador, en vez de dejar un "escribiendo..." sin explicación.
        self.app.system.progreso.conectar(self._progreso_gui)

    def _construir(self):
        """Monta el chat dentro de su marco: bienvenida, historial y barra de escribir."""
        # Espaciadores para centrar la bienvenida verticalmente. Se les da un alto
        # mínimo (por defecto un CTkFrame pide 200 px): así el reparto del espacio
        # sobrante es igual para los dos y el hero queda realmente centrado.
        self.spacer_top = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.spacer_bottom = ctk.CTkFrame(self, fg_color="transparent", height=1)

        # Hero (pantalla de bienvenida): el icono de la casa en una pastilla con el
        # borde encendido, para que la primera pantalla hable el mismo idioma visual
        # que el resto (tarjetas redondeadas y acento).
        self.hero = ctk.CTkFrame(self, fg_color="transparent")
        pastilla = ctk.CTkFrame(self.hero, fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.10),
                                corner_radius=24, border_width=1, border_color=COLOR_ACENTO,
                                width=78, height=78)
        pastilla.pack()
        pastilla.pack_propagate(False)
        ctk.CTkLabel(pastilla, text="\u2726", font=(tema.FUENTE_UI, 34),
                     text_color=COLOR_ACENTO).pack(expand=True)
        ctk.CTkLabel(self.hero, text="\u00bfEn qué puedo ayudarte hoy?",
                     font=(tema.FUENTE_UI, 26, "bold"), text_color=COLOR_TEXTO).pack(pady=(14, 0))
        ctk.CTkLabel(self.hero, text="Escribe tu mensaje o usa el micrófono para dictarlo.",
                     font=(tema.FUENTE_UI, 13), text_color=COLOR_TEXTO_SUAVE).pack(pady=(6, 0))

        # Historial de conversación (burbujas)
        self.chat_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
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
        self._crear_barra_input(self)

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
            text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 15),
            command=self._adjuntar_archivos)
        self.btn_adjuntar.pack(side="left", padx=(10, 0), pady=8)

        self.btn_explorador = ctk.CTkButton(
            caja, text="\U0001F4C1", width=36, height=36, corner_radius=18,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 15),
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
            font=(tema.FUENTE_UI, 14))
        self.entry_chat.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=8)
        self.entry_chat._textbox.configure(spacing1=2, spacing3=2, padx=0, pady=2)
        rueda.acelerar_caja(self.entry_chat)   # la rueda avanza más líneas de golpe
        self._alto_input_actual = ALTO_INPUT_MIN
        self._chat_vacio = True          # dentro está el aviso, no un mensaje
        self._poner_fantasma()

        self.btn_enviar = ctk.CTkButton(
            caja, text="\u2191", width=38, height=38, corner_radius=19,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO,
            font=(tema.FUENTE_UI, 18, "bold"), command=self._enviar_chat)
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
            text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 17),
            command=self.app.toggle_escucha)
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
                     font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE).pack(pady=(6, 0))

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

    def _enviar_con_enter(self, evento=None):
        """Enter envía el mensaje (Shift+Enter, que no pasa por aquí, salta de línea)."""
        if not self._texto_input() and not self.adjuntos:
            return None      # caja vacía: Enter solo baja de línea
        self._enviar_chat()
        return "break"       # sin esto, además de enviar se escribiría un salto

    def _actualizar_mic(self):
        """Pinta el botón del micrófono según el estado de la escucha."""
        escuchando = bool(getattr(self.app, "escuchando", False))
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
        if not getattr(self.app, "escuchando", False) or self._onda_mic is None:
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
            self.after(0, self.app._cargar_conversaciones_sidebar)

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
            width=32, height=32, corner_radius=16, font=(tema.FUENTE_UI, 15),
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

        ancho_panel = self.app.area_principal.winfo_width()
        if ancho_panel <= 1:
            ancho_panel = 820
        ancho_texto = max(320, int(ancho_panel * 0.6))

        # Quién habla: con su nombre sobre el texto se sigue el hilo de un vistazo.
        ctk.CTkLabel(burbuja, text="Tú" if es_usuario else "Jarvis",
                     font=(tema.FUENTE_UI, 10, "bold"), anchor="w",
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
                             font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                             fg_color=COLOR_HOVER, corner_radius=8).pack(
                                 padx=12, pady=(6, 0), anchor="w")

        area_texto = None
        if texto:
            if es_usuario:
                # Tu mensaje se enseña tal cual lo escribiste.
                ctk.CTkLabel(burbuja, text=texto, wraplength=ancho_texto, justify="left",
                             anchor="w", font=(tema.FUENTE_UI, 13),
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
                      font=(tema.FUENTE_UI, 12),
                      command=self._limpiar_seleccion).pack(side="left", padx=(10, 6), pady=6)
        self.lbl_sel = ctk.CTkLabel(self.barra_seleccion, text="0 mensajes seleccionados",
                                    font=(tema.FUENTE_UI, 12), text_color=COLOR_TEXTO)
        self.lbl_sel.pack(side="left", pady=8)
        ctk.CTkButton(self.barra_seleccion, text="Guardar .txt", width=110, height=28,
                      corner_radius=8, fg_color=COLOR_ACENTO,
                      hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      font=(tema.FUENTE_UI, 12, "bold"),
                      command=self._guardar_seleccion_txt).pack(side="right", padx=(4, 10), pady=6)
        ctk.CTkButton(self.barra_seleccion, text="Copiar", width=80, height=28,
                      corner_radius=8, fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
                      command=self._copiar_seleccion).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(self.barra_seleccion, text="Todo", width=60, height=28,
                      corner_radius=8, fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 12),
                      command=self._seleccionar_todos).pack(side="right", padx=4, pady=6)

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
                font=(tema.FUENTE_UI, 11),
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
        self._ventana_explorador = ctk.CTkToplevel(self.app)
        dlg = self._ventana_explorador
        dlg.title("Explorador de archivos")
        dlg.geometry("760x560")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)

        self._expl_dir = None       # carpeta actual
        self._expl_sel = set()      # rutas de archivos seleccionados
        self._expl_todos = []       # rutas de archivos visibles (para 'seleccionar todo')
        self._expl_botones = {}     # ruta -> (botón, texto base) de los archivos

        # Cabecera: ruta actual + navegación
        cabecera = ctk.CTkFrame(dlg, fg_color="transparent")
        cabecera.pack(fill="x", padx=16, pady=(16, 6))
        ctk.CTkButton(cabecera, text="⬆", width=38, height=34, font=(tema.FUENTE_UI, 14),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, command=self._expl_subir).pack(side="left")
        ctk.CTkButton(cabecera, text="⌂", width=38, height=34, font=(tema.FUENTE_UI, 14),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO,
                      command=self._expl_raiz).pack(side="left", padx=(6, 6))
        self._expl_entry_ruta = ctk.CTkEntry(
            cabecera, placeholder_text="Ruta de la carpeta...", fg_color=COLOR_TARJETA,
            border_color=COLOR_BORDE, text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12))
        self._expl_entry_ruta.pack(side="left", fill="x", expand=True)
        self._expl_entry_ruta.bind("<Return>", lambda e: self._expl_ir())
        ctk.CTkButton(cabecera, text="Ir", width=44, height=34, font=(tema.FUENTE_UI, 12),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, command=self._expl_ir).pack(side="left", padx=(6, 0))

        # Búsqueda dentro de la carpeta
        busqueda = ctk.CTkFrame(dlg, fg_color="transparent")
        busqueda.pack(fill="x", padx=16, pady=(4, 6))
        self._expl_entry_buscar = ctk.CTkEntry(
            busqueda, placeholder_text="Buscar dentro de esta carpeta...",
            fg_color=COLOR_TARJETA, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12))
        self._expl_entry_buscar.pack(side="left", fill="x", expand=True)
        self._expl_entry_buscar.bind("<Return>", lambda e: self._expl_buscar())
        ctk.CTkButton(busqueda, text="Buscar", width=72, height=34, font=(tema.FUENTE_UI, 12),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=self._expl_buscar).pack(side="left", padx=(6, 0))
        ctk.CTkButton(busqueda, text="Carpeta", width=72, height=34, font=(tema.FUENTE_UI, 12),
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
        self._expl_lbl_estado = ctk.CTkLabel(pie, text="", font=(tema.FUENTE_UI, 11),
                                             text_color=COLOR_TEXTO_SUAVE, anchor="w",
                                             justify="left")
        self._expl_lbl_estado.pack(fill="x", pady=(0, 6))
        botones = ctk.CTkFrame(pie, fg_color="transparent")
        botones.pack(fill="x")
        self._expl_lbl_sel = ctk.CTkLabel(botones, text="0 seleccionados",
                                          font=(tema.FUENTE_UI, 11),
                                          text_color=COLOR_TEXTO_SUAVE)
        self._expl_lbl_sel.pack(side="left", pady=6)
        ctk.CTkButton(botones, text="Seleccionar todo", width=120, height=30,
                      font=(tema.FUENTE_UI, 11), fg_color=COLOR_TARJETA,
                      hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
                      command=self._expl_todo).pack(side="left", padx=(10, 0))
        ctk.CTkButton(botones, text="Abrir", width=70, height=30, font=(tema.FUENTE_UI, 11),
                      fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO,
                      command=self._expl_abrir).pack(side="left", padx=(6, 0))
        ctk.CTkButton(botones, text="Mover a…", width=90, height=30, font=(tema.FUENTE_UI, 11),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=lambda: self._expl_mover_copiar("mover")).pack(side="right")
        ctk.CTkButton(botones, text="Copiar a…", width=90, height=30, font=(tema.FUENTE_UI, 11),
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO,
                      command=lambda: self._expl_mover_copiar("copiar")).pack(
                          side="right", padx=(0, 6))

        # Punto de partida: primera raíz disponible (OneDrive si existe)
        raices = self.app.system.archivos.raices()
        self._expl_ir(raices[0] if raices else os.path.expanduser("~"))

    def _expl_ir(self, ruta=None):
        ruta = ruta or self._expl_entry_ruta.get().strip()
        ruta = self.app.system.archivos.normalizar(ruta)
        entradas = self.app.system.archivos.listar(ruta)
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
                          text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 12),
                          command=self._expl_subir).pack(fill="x", padx=6, pady=2)
            return
        es_carpeta = bool(entrada.get("es_carpeta"))
        ruta = entrada["ruta"]
        if es_carpeta:
            ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                          fg_color="transparent", hover_color=COLOR_HOVER,
                          text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
                          command=lambda r=ruta: self._expl_ir(r)).pack(fill="x", padx=6, pady=2)
        else:
            self._expl_todos.append(ruta)
            boton = ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                                  fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                                  text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12))
            boton.pack(fill="x", padx=6, pady=2)
            self._expl_botones[ruta] = (boton, texto)
            boton.configure(command=lambda r=ruta, b=boton, t=texto:
                            self._expl_toggle(r, b, t))

    def _expl_subir(self):
        actual = self.app.system.archivos.normalizar(self._expl_dir or "")
        if actual:
            self._expl_ir(os.path.dirname(actual))

    def _expl_raiz(self):
        raices = self.app.system.archivos.raices()
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
        resultados = self.app.system.archivos.buscar(carpeta, nombre)
        for widget in self._expl_lista.winfo_children():
            widget.destroy()
        self._expl_todos = list(resultados)
        self._expl_sel.clear()
        self._expl_botones = {}
        if not resultados:
            ctk.CTkLabel(self._expl_lista, text=f"Sin resultados para «{nombre}»",
                         font=(tema.FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                         anchor="w").pack(fill="x", padx=10, pady=8)
        for ruta in resultados:
            texto = f"📄  {ruta}"
            boton = ctk.CTkButton(self._expl_lista, text=texto, anchor="w", height=28,
                                  fg_color=COLOR_TARJETA, hover_color=COLOR_HOVER,
                                  text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12))
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
        operacion = (self.app.system.archivos.mover if accion == "mover"
                     else self.app.system.archivos.copiar)
        resultado = operacion(seleccion, destino, confirmado=True)
        self._expl_estado(self.app.system.archivos.resumen(resultado))
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
            ctk.CTkLabel(chip, text=f"{icono}{nombre}", font=(tema.FUENTE_UI, 11),
                         text_color=COLOR_TEXTO).pack(side="left", padx=(6, 4), pady=5)

            ctk.CTkButton(chip, text="\u2715", width=20, height=20, corner_radius=10,
                          fg_color="transparent", hover_color=COLOR_ACENTO_HOVER,
                          text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 11),
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
                                           font=(tema.FUENTE_UI, 11),
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
        self.app.system.productivity.agregar_regla(regla)
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
                                               font=(tema.FUENTE_UI, 13), text_color=COLOR_ACENTO)
                self._lbl_pulso.pack(side="left", padx=(16, 6), pady=(10, 4))
                self._lbl_pensando = ctk.CTkLabel(cabecera,
                                                  text="Jarvis está trabajando",
                                                  font=(tema.FUENTE_UI, 12, "italic"),
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
                         font=(tema.FUENTE_UI, 11), justify="left", anchor="w",
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
        self.app._mostrar_vista("chat")
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
                self.app.system.progreso.paso("Leyendo el contenido de los adjuntos"
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
        self.app.system.progreso.paso("Pensando con la IA qué hacer…")
        respuesta_texto, comando_accion = self.app.brain.procesar_mensaje(texto)
        resultado = None
        if comando_accion:
            resultado = self.app.system.ejecutar_comando(comando_accion)
            if comando_accion.strip().upper() == "SISTEMA|APAGAR":
                self.app.reproducir_voz("Entendido, cerrando el programa. Hasta luego.")
                self.after(0, self.app.destroy)
                return "Cerrando el programa..."
        if resultado:
            if str(resultado).startswith("__CONTEXTO__"):
                contexto = str(resultado)[len("__CONTEXTO__"):]
                self.app.system.progreso.paso("Redactando la respuesta con la IA…")
                return self.app.brain.analizar(contexto) or "No pude procesar la solicitud."
            return str(resultado)
        if respuesta_texto:
            return respuesta_texto
        if comando_accion:
            return ""  # se ejecutó una acción sin texto de respuesta
        return "No entendí eso."

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

    def _abrir_conversacion(self, ruta):
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        self._ind_pensando = None
        self._pegado_abajo = True    # al abrir un hilo se muestra el final
        self._procesando = False
        self._burbujas = []
        self._seleccion = []
        self.conversacion_actual = ruta  # los mensajes nuevos siguen este hilo
        self.app._mostrar_vista("chat")

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
