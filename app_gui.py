"""La ventana de Jarvis: el armazón y el cambio de apartado.

Los apartados de la app son vistas independientes (`views/`): el chat, el tutor
de inglés, el taller de programación y los ajustes. Cada una trae sus widgets, su
estado y sus métodos; aquí queda lo que comparten todas:

- el armazón de la ventana (barra lateral, barra superior y área principal),
- el cambio de apartado (`_mostrar_vista`),
- los servicios que usa todo el mundo: el cerebro (`APIBrain`), las acciones del
  sistema (`SystemActions`), la voz y el historial de conversaciones.
"""
import glob
import json
import os
import re
import threading
import tkinter as tk
import webbrowser                      # compat: las pruebas lo sustituyen aquí
from datetime import datetime

import customtkinter as ctk

from modules.api_brain import APIBrain
from modules.system_actions import SystemActions
from modules.voice_engine import VoiceEngine
from modules.voice_output import VoiceOutput
from modules.ocr_engine import motor as ocr_motor
from modules import rutas
from modules import notificaciones
from ui import tema
from ui.tema import (
    ATAJOS_CAMPO, BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_2, COLOR_ACENTO_HOVER,
    COLOR_ACENTO_TEXTO, COLOR_BORDE, COLOR_HOVER, COLOR_OK, COLOR_PANEL,
    COLOR_PELIGRO, COLOR_PELIGRO_HOVER, COLOR_SIDEBAR, COLOR_TARJETA,
    COLOR_TARJETA_ALTA, COLOR_TEXTO, COLOR_TEXTO_SUAVE, RADIO_CHIP,
    USUARIO_SIN_NOMBRE, _mezclar, imagen_degradado,
)

from views import VistaAjustes, VistaChat, VistaIngles, VistaProgramacion
# Compatibilidad: lo que antes se leía de aquí y ahora vive en su apartado.
from views.chat import MARCAS_PASOS                                        # noqa: F401
from views.ingles import TAREAS_INGLES                                     # noqa: F401
from views.ingles import TAREA_INGLES_PELIGRO, TAREA_INGLES_PRINCIPAL     # noqa: F401
from views.programacion import (CODIGO_EJEMPLO, TAREAS_PROGRAMACION,      # noqa: F401
                                AYUDA_PROGRAMACION, MAX_AVISOS_PANTALLA)


def __getattr__(nombre):
    """La paleta, las medidas y las fuentes se leen de `ui/tema.py`.

    Así `app_gui.COLOR_ACENTO` (o `app_gui.FUENTE_UI`, que se resuelve al montar
    la ventana) sigue funcionando sin duplicar el tema aquí.
    """
    try:
        return getattr(tema, nombre)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} no tiene «{nombre}»") from None


class AppGUI(ctk.CTk):
    """La ventana: junta los servicios, monta los apartados y cambia entre ellos."""

    def __init__(self, config_path=rutas.CONFIG_USUARIO, voice_output=None):
        super().__init__()

        self.config_path = config_path
        self.escuchando = False
        #: Las vistas montadas, por nombre de apartado («chat», «ingles»...). La
        #: ventana las coloca en el área principal y cambia de una a otra.
        self.vistas = {}

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

        # Configuración de la ventana principal
        self.title("Jarvis")
        self.geometry("1120x760")
        self.resizable(True, True)
        self.minsize(900, 600)
        self.configure(fg_color=tema.COLOR_FONDO)

        self._crear_interfaz()
        self._cargar_config_en_inputs()
        self._cargar_conversaciones_sidebar()

    # ---------------- Construcción de la interfaz ----------------
    def _crear_interfaz(self):
        # Las fuentes se eligen al montar la ventana: hasta que no hay un root de
        # Tk no se pueden consultar las familias instaladas del sistema.
        tema._resolver_fuentes()
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True)

        self._crear_sidebar(contenedor)

        # Área principal (derecha)
        self.area_principal = ctk.CTkFrame(contenedor, fg_color=tema.COLOR_PANEL,
                                           corner_radius=0)
        self.area_principal.pack(side="left", fill="both", expand=True)

        # Barra superior con degradado: da el toque de color de la casa (turquesa
        # → azul → fondo) sin ensuciar el resto de la ventana.
        self._crear_barra_superior(self.area_principal)

        # Cada apartado es su propia vista (un módulo de `views/`): trae sus
        # widgets, su estado y sus métodos, y la ventana solo la coloca en el área
        # principal y cambia de una a otra. Así el chat, el tutor de inglés, el
        # taller de programación y los ajustes son piezas independientes.
        self.vista_chat = VistaChat(self)
        self.vista_ajustes = VistaAjustes(self)
        self.vista_ingles = VistaIngles(self)
        self.vista_programacion = VistaProgramacion(self)
        self.vistas = {vista.nombre: vista for vista in (self.vista_chat, self.vista_ajustes,
                                                        self.vista_ingles,
                                                        self.vista_programacion)}

        self._mostrar_vista("chat")
        self.vista_chat._mostrar_estado_chat(False)

        # Los campos de una línea (tu nombre, la API Key, el tema de inglés...) van
        # con los mismos atajos: se recorren ahora, que ya están todos creados.
        self._atajos_en_campos()

    def _mostrar_vista(self, vista):
        # Al salir del apartado de inglés se apaga su micrófono: si no, seguiría
        # escuchando (y gastando IA) desde una vista que ya no se ve.
        if vista != "ingles" and getattr(self.vista_ingles, "_speaking_activo", False):
            self.vista_ingles._parar_speaking("Micrófono apagado.")
        for otra in self.vistas.values():
            otra.pack_forget()
        self._resaltar_apartado(vista)
        if vista == "ajustes":
            self.vista_ajustes.pack(fill="both", expand=True)
            self.vista_ajustes._cargar_reglas_ui()
        elif vista == "ingles":
            self.vista_ingles.pack(fill="both", expand=True)
            self.vista_ingles._actualizar_ingles()
        elif vista == "programar":
            self.vista_programacion.pack(fill="both", expand=True)
            self.vista_programacion._actualizar_programacion()
            # Al entrar se revisa lo que haya en el editor: así el panel de avisos
            # cuenta algo desde el primer momento (y no gasta IA).
            self.vista_programacion._revisar_programacion(compilar=False)
        else:
            self.vista_chat.pack(fill="both", expand=True)

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
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 18)).pack(side="left")
        titulos = ctk.CTkFrame(cabecera, fg_color="transparent")
        titulos.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(titulos, text="Jarvis", font=(tema.FUENTE_UI, 17, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w")
        ctk.CTkLabel(titulos, text="Tu asistente personal", font=(tema.FUENTE_UI, 10),
                     text_color=COLOR_TEXTO_SUAVE).pack(anchor="w")

        # Botón "Nuevo chat" (tarjeta con borde suave: la acción de la casa es
        # escribir en el chat, pero no compite con el acento del apartado)
        self.btn_nuevo = ctk.CTkButton(
            self.sidebar, text="\uff0b   Nuevo chat", anchor="w",
            font=(tema.FUENTE_UI, 13), height=40, corner_radius=RADIO_CHIP,
            fg_color=COLOR_TARJETA, hover_color=COLOR_TARJETA_ALTA, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE,
            command=lambda: self.vista_chat._nueva_conversacion(),
        )
        self.btn_nuevo.pack(fill="x", padx=14, pady=(0, 16))

        # Apartado del tutor de inglés: botón propio con su vista, porque el tutor
        # no se usa desde el chat (se escribe en su caja, no en el mensaje).
        ctk.CTkLabel(self.sidebar, text="APARTADOS", font=(tema.FUENTE_UI, 10, "bold"),
                     text_color=COLOR_TEXTO_SUAVE).pack(anchor="w", padx=20, pady=(0, 6))
        self.btn_ingles = ctk.CTkButton(
            self.sidebar, text="\U0001F393   Inglés", anchor="w",
            font=(tema.FUENTE_UI, 13), height=40, corner_radius=RADIO_CHIP,
            fg_color="transparent", hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE,
            command=lambda: self._mostrar_vista("ingles"),
        )
        self.btn_ingles.pack(fill="x", padx=14, pady=(0, 6))
        # Taller de programación: su propio apartado, por lo mismo (el código se
        # escribe en su editor y se corrige mientras se escribe, no en el chat).
        self.btn_programar = ctk.CTkButton(
            self.sidebar, text="\U0001F4BB   Programar", anchor="w",
            font=(tema.FUENTE_UI, 13), height=40, corner_radius=RADIO_CHIP,
            fg_color="transparent", hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE,
            command=lambda: self._mostrar_vista("programar"),
        )
        self.btn_programar.pack(fill="x", padx=14, pady=(0, 18))

        # Encabezado de sección
        ctk.CTkLabel(self.sidebar, text="CONVERSACIONES", font=(tema.FUENTE_UI, 10, "bold"),
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
                                   font=(tema.FUENTE_UI, 13, "bold"), cursor="hand2")
        self.avatar.pack(side="left")
        self.lbl_usuario = ctk.CTkLabel(pie, text=USUARIO_SIN_NOMBRE,
                                        font=(tema.FUENTE_UI, 13), text_color=COLOR_TEXTO_SUAVE,
                                        cursor="hand2")
        self.lbl_usuario.pack(side="left", padx=(10, 0))
        # Pulsar tu nombre lleva a Ajustes, que es donde se cambia.
        for widget in (self.avatar, self.lbl_usuario):
            widget.bind("<Button-1>", lambda e: self._mostrar_vista("ajustes"))
        ctk.CTkButton(pie, text="\u2699", width=32, height=32, corner_radius=RADIO_CHIP,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 16),
                      command=self._toggle_ajustes).pack(side="right")

    def _resaltar_apartado(self, vista):
        """Deja marcado en la barra lateral en qué apartado estás.

        El apartado abierto se ve como una tarjeta con el borde encendido en el
        color de acento (un «glow» sutil); al salir vuelve a su sitio.
        """
        for nombre, boton in (("ingles", getattr(self, "btn_ingles", None)),
                              ("programar", getattr(self, "btn_programar", None))):
            if boton is None:
                continue
            abierto = vista == nombre
            try:
                boton.configure(
                    fg_color=COLOR_TARJETA if abierto else "transparent",
                    border_color=COLOR_ACENTO if abierto else COLOR_BORDE,
                    text_color=COLOR_ACENTO if abierto else COLOR_TEXTO)
            except Exception:
                pass

    def _toggle_ajustes(self):
        if self.vista_ajustes.winfo_ismapped():
            self._mostrar_vista("chat")
        else:
            self._mostrar_vista("ajustes")

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
                         font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
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
            ctk.CTkLabel(cabecera, text="\U0001F4AC", font=(tema.FUENTE_UI, 12),
                         text_color=COLOR_ACENTO).pack(side="left")
            ctk.CTkLabel(cabecera, text=fecha, font=(tema.FUENTE_UI, 10, "bold"),
                         text_color=COLOR_TEXTO_SUAVE).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(tarjeta, text=titulo, font=(tema.FUENTE_UI, 11), anchor="w",
                         justify="left", wraplength=196, text_color=COLOR_TEXTO).pack(
                             anchor="w", padx=10, pady=(2, 9))
            self.vista_chat._vincular_clic(
                tarjeta, lambda e, r=ruta: self.vista_chat._abrir_conversacion(r))
            # Al pasar el ratón, la tarjeta se eleva y el borde se enciende un poco.
            for widget in self.vista_chat._widgets_clickeables(tarjeta):
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

    # ---------------- Configuración ----------------
    def _pintar_usuario(self, nombre=None):
        """Deja el pie de la barra lateral con tu nombre (o el aviso de ponerlo).

        El nombre sale del campo «Tu nombre» de Ajustes: el de la sesión de Windows
        no se usa, que era lo que enseñaba «coutt · Free» sin que nadie lo pidiera.
        """
        if nombre is None:
            nombre = (self.vista_ajustes.entry_usuario.get().strip()
                      if hasattr(self.vista_ajustes, "entry_usuario") else "")
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

        # Los campos son de Ajustes: la ventana solo los rellena con lo guardado.
        ajustes = self.vista_ajustes
        ajustes.entry_api.delete(0, "end")
        ajustes.entry_nombre.delete(0, "end")
        ajustes.entry_rvc.delete(0, "end")
        ajustes.entry_usuario.delete(0, "end")
        ajustes.entry_api.insert(0, api_key)
        ajustes.entry_nombre.insert(0, nombre)
        ajustes.entry_rvc.insert(0, rvc)
        ajustes.entry_usuario.insert(0, usuario)

        # Matriz en la nube: se configura con sus propios botones/diálogos
        ajustes._actualizar_estado_nube()
        # Correo: idem (se conecta con 'Conectar correo')
        ajustes._actualizar_estado_correo()
        # Música: idem (se conecta con 'Conectar Spotify')
        ajustes._actualizar_estado_spotify()

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
        ajustes = self.vista_ajustes
        api_key = ajustes.entry_api.get().strip()
        api_key_env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key and api_key_env and api_key == api_key_env:
            api_key = ""

        existente["api_key"] = api_key
        existente["nombre_asistente"] = ajustes.entry_nombre.get().strip().lower()
        existente["usuario"] = ajustes.entry_usuario.get().strip()
        existente["modelo_rvc_path"] = ajustes.entry_rvc.get().strip()

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
        ajustes.lbl_estado.configure(
            text=("Configuración guardada · Jarvis te llamará " + existente["usuario"]
                  if existente["usuario"] else "Configuración guardada"),
            text_color=COLOR_OK)

    # ---------------- Control por voz ----------------
    def toggle_escucha(self):
        ajustes = self.vista_ajustes
        if not self.escuchando:
            # El micrófono del chat y el del apartado de inglés no pueden estar
            # escuchando a la vez: se apaga el del speaking si estaba encendido.
            if getattr(self.vista_ingles, "_speaking_activo", False):
                self.vista_ingles._parar_speaking("Micrófono apagado.")
            self.escuchando = True
            ajustes.lbl_estado.configure(text="Estado: Escuchando...", text_color=COLOR_OK)
            ajustes.btn_toggle.configure(text="\u23F9  Detener Escucha", fg_color=COLOR_PELIGRO,
                                         hover_color=COLOR_PELIGRO_HOVER)
            threading.Thread(target=self._bucle_escucha, daemon=True).start()
        else:
            self.escuchando = False
            ajustes.lbl_estado.configure(text="Estado: Inactivo", text_color=COLOR_TEXTO_SUAVE)
            ajustes.btn_toggle.configure(text="\U0001F3A4  Iniciar Escucha", fg_color=COLOR_ACENTO,
                                         hover_color=COLOR_ACENTO_HOVER)
        # El micrófono de la barra de entrada refleja el mismo estado (y su anillo
        # late mientras escucha), tanto si se pulsó aquí como si vino por voz.
        self.vista_chat._actualizar_mic()

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
                chat = self.vista_chat
                chat._guardar_regla_si_aplica(comando_usuario)
                chat._agregar_chat("Tú", comando_usuario)

                # 2-3-4. Procesar y responder por voz (con el indicador del chat:
                # por voz pasa lo mismo y sin él no se sabía qué estaba haciendo).
                modelo_rvc = self.vista_ajustes.entry_rvc.get().strip()
                self.after(0, lambda: chat._mostrar_pensando(True))
                try:
                    respuesta = chat._procesar_mensaje(comando_usuario)
                finally:
                    self.after(0, lambda: chat._mostrar_pensando(False))
                if respuesta:
                    chat._agregar_chat("Jarvis", respuesta)
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
            self.after(0, lambda: self.vista_chat._agregar_chat("Jarvis", texto))
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

    # ---------------- Los nombres de siempre (compatibilidad) ----------------
    # Los widgets y el estado de cada apartado viven ahora en su vista. Para que
    # el resto del código y las pruebas puedan seguir pidiéndolos a la ventana
    # (`app.btn_mic`, `app.txt_prog_codigo`, `app._burbujas`...), la ventana los
    # busca en sus vistas cuando no los tiene: es un puente, no una copia.
    def __getattr__(self, nombre):
        if nombre.startswith("__") or nombre == "vistas":
            raise AttributeError(nombre)
        for vista in self.__dict__.get("vistas", {}).values():
            try:
                return getattr(vista, nombre)
            except AttributeError:
                continue
        raise AttributeError(f"'{type(self).__name__}' no tiene «{nombre}»")

    def __setattr__(self, nombre, valor):
        # Y al revés: escribir `app.<algo>` de un apartado lo escribe en su vista.
        for vista in self.__dict__.get("vistas", {}).values():
            if nombre in vista.__dict__ or hasattr(vista, nombre):
                setattr(vista, nombre, valor)
                return
        super().__setattr__(nombre, valor)
