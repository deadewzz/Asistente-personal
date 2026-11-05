"""Apartado de ajustes: tu nombre, la voz, la nube, el correo y Spotify.

Todo lo que se configura en Jarvis se toca aquí y se guarda en el mismo
`config.json` que leen los módulos: la ventana solo le pasa la ruta
(`self.app.config_path`) y le pide que recargue los campos cuando cambia algo.
"""
import json
import os
import re
import threading
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

from modules import rutas
from modules.cloud_matrix import COLUMNAS_DEFECTO
from ui import tema
from ui import scroll as rueda
from ui.tema import (
    BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_HOVER, COLOR_ACENTO_TEXTO, COLOR_BORDE,
    COLOR_CODIGO, COLOR_FONDO, COLOR_HOVER, COLOR_OK, COLOR_PANEL, COLOR_PELIGRO,
    COLOR_PELIGRO_HOVER, COLOR_TARJETA, COLOR_TARJETA_ALTA, COLOR_TEXTO,
    COLOR_TEXTO_SUAVE, RADIO_CHIP, RADIO_TARJETA, _mezclar,
)

from views.base import Vista


class VistaAjustes(Vista):
    """Ajustes de la app: identidad, voz, nube, correo y Spotify."""

    nombre = "ajustes"

    def _preparar(self):
        """Estado del apartado: si hay una conexión en marcha (correo o Spotify)."""
        self._conectando_correo = False
        self._conectando_spotify = False

    # ---------------- Vista de ajustes ----------------
    def _construir(self):
        """Monta el apartado: la tarjeta de la voz y los ajustes, sección a sección."""
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(16, 10))
        ctk.CTkButton(cabecera, text="\u2039  Volver al chat", width=150, height=34,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, anchor="w", font=(tema.FUENTE_UI, 13),
                      command=lambda: self.app._mostrar_vista("chat")).pack(side="left")
        ctk.CTkLabel(cabecera, text="\u2699", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 16)).pack(side="left", padx=(16, 8))
        ctk.CTkLabel(cabecera, text="Voz y Ajustes", font=(tema.FUENTE_UI, 20, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")

        # El resto del apartado va con barras de desplazamiento: la tarjeta de la
        # voz y todos los ajustes no caben en cualquier alto de ventana, así que se
        # llega a todo sin que se corte nada por abajo.
        self.scroll_ajustes = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                                     height=220, **BARRA_SCROLL)
        self.scroll_ajustes.pack(fill="both", expand=True, padx=(26, 12), pady=(0, 16))

        # La voz, en su tarjeta: a la izquierda cómo está y a la derecha el botón,
        # que es lo único que se pulsa aquí.
        marco_voz = ctk.CTkFrame(self.scroll_ajustes, fg_color=COLOR_TARJETA,
                                 corner_radius=RADIO_TARJETA,
                                 border_width=1, border_color=COLOR_BORDE)
        marco_voz.pack(fill="x", padx=6, pady=(0, 14))
        ctk.CTkLabel(marco_voz, text="\U0001F3A4  Escucha por voz",
                     font=(tema.FUENTE_UI, 13, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(16, 10), pady=16)
        self.lbl_estado = ctk.CTkLabel(marco_voz, text="Estado: Inactivo",
                                       text_color=COLOR_TEXTO_SUAVE, font=(tema.FUENTE_UI, 13))
        self.lbl_estado.pack(side="left", pady=16)
        self.btn_toggle = ctk.CTkButton(marco_voz, text="\U0001F3A4  Iniciar Escucha",
                                        command=self.app.toggle_escucha, fg_color=COLOR_ACENTO,
                                        hover_color=COLOR_ACENTO_HOVER,
                                        text_color=COLOR_ACENTO_TEXTO, corner_radius=RADIO_CHIP,
                                        height=40, width=236, font=(tema.FUENTE_UI, 13, "bold"))
        self.btn_toggle.pack(side="right", padx=16, pady=10)

        # Marco de ajustes: una tarjeta con sus apartados, cada uno con su icono.
        self.frame_config = ctk.CTkFrame(self.scroll_ajustes, fg_color=COLOR_TARJETA,
                                         corner_radius=RADIO_TARJETA,
                                         border_width=1, border_color=COLOR_BORDE)
        self.frame_config.pack(fill="x", padx=6, pady=(0, 18))

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
            font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE, anchor="w",
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
            font=(tema.FUENTE_UI, 12))
        self.btn_cfg_ado.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_cfg_excel = ctk.CTkButton(
            frame_nube, text="Excel (archivo o URL)",
            command=self._abrir_config_excel, fg_color=COLOR_ACENTO,
            hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO, height=36,
            font=(tema.FUENTE_UI, 12, "bold"))
        self.btn_cfg_excel.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.lbl_nube_excel = ctk.CTkLabel(self.frame_config,
                                           text="Excel: sin configurar",
                                           text_color=COLOR_TEXTO_SUAVE,
                                           font=(tema.FUENTE_UI, 11), anchor="w",
                                           justify="left", wraplength=620)
        self.lbl_nube_excel.pack(anchor="w", padx=18, pady=(4, 2))
        self.lbl_nube_ado = ctk.CTkLabel(self.frame_config,
                                         text="Azure DevOps: sin configurar",
                                         text_color=COLOR_TEXTO_SUAVE,
                                         font=(tema.FUENTE_UI, 11), anchor="w",
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
            text_color=COLOR_ACENTO_TEXTO, height=38, font=(tema.FUENTE_UI, 12, "bold"))
        self.btn_conectar_correo.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_desconectar_correo = ctk.CTkButton(
            frame_correo, text="Desconectar", command=self._desconectar_correo,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, height=36,
            font=(tema.FUENTE_UI, 12, "bold"))
        self.btn_desconectar_correo.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.lbl_correo = ctk.CTkLabel(self.frame_config, text="Correo: sin conectar",
                                       text_color=COLOR_TEXTO_SUAVE,
                                       font=(tema.FUENTE_UI, 11), anchor="w",
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
            font=(tema.FUENTE_UI, 12, "bold"))
        self.btn_conectar_spotify.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_cfg_spotify = ctk.CTkButton(
            frame_spotify, text="Client ID", command=self._abrir_config_spotify,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            height=36, font=(tema.FUENTE_UI, 12))
        self.btn_cfg_spotify.pack(side="left", expand=True, fill="x", padx=6)
        self.btn_desconectar_spotify = ctk.CTkButton(
            frame_spotify, text="Desconectar", command=self._desconectar_spotify,
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER, text_color=COLOR_TEXTO,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            height=36, font=(tema.FUENTE_UI, 12))
        self.btn_desconectar_spotify.pack(side="left", expand=True, fill="x",
                                          padx=(6, 0))

        self.lbl_spotify = ctk.CTkLabel(self.frame_config, text="Spotify: sin conectar",
                                        text_color=COLOR_TEXTO_SUAVE,
                                        font=(tema.FUENTE_UI, 11), anchor="w",
                                        justify="left", wraplength=620)
        self.lbl_spotify.pack(anchor="w", padx=18, pady=(4, 10))

        self.btn_guardar = ctk.CTkButton(self.frame_config,
                                         text="\U0001F4BE  Guardar configuración",
                                         command=self.app.guardar_config, fg_color=COLOR_ACENTO,
                                         hover_color=COLOR_ACENTO_HOVER, corner_radius=RADIO_CHIP,
                                         text_color=COLOR_ACENTO_TEXTO,
                                         height=40, width=250, font=(tema.FUENTE_UI, 13, "bold"))
        self.btn_guardar.pack(pady=(10, 14))

        # Reglas permanentes (memoria del asistente: se añaden a cada consulta)
        self._titulo_config("\U0001F4CC", "Reglas permanentes (Jarvis las recuerda siempre)")
        self.txt_reglas = ctk.CTkTextbox(self.frame_config, height=110,
                                         fg_color=COLOR_CODIGO, border_width=1,
                                         border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
                                         text_color=COLOR_TEXTO, undo=True, maxundo=200,
                                         font=(tema.FUENTE_UI, 12), wrap="word")
        self.txt_reglas.pack(padx=18, fill="x")
        rueda.acelerar_caja(self.txt_reglas)
        # Las reglas también se escriben a mano: los mismos atajos que en el chat.
        self._atajos_caja(self.txt_reglas)
        self.btn_guardar_reglas = ctk.CTkButton(
            self.frame_config, text="Guardar reglas", command=self._guardar_reglas_ui,
            fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_TEXTO, height=36, font=(tema.FUENTE_UI, 12))
        self.btn_guardar_reglas.pack(pady=(10, 18))

    def _titulo_config(self, icono, texto):
        """Cabecera de un apartado dentro de la tarjeta de ajustes (icono + título)."""
        ctk.CTkLabel(self.frame_config, text=f"{icono}  {texto}",
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 12, "bold")).pack(
                         anchor="w", padx=18, pady=(16, 4))

    def _campo_config(self, parent, etiqueta, nombre_attr, show=None, pady_top=(14, 4)):
        ctk.CTkLabel(parent, text=etiqueta, text_color=COLOR_TEXTO,
                     font=(tema.FUENTE_UI, 12)).pack(anchor="w", padx=18, pady=pady_top)
        entrada = ctk.CTkEntry(parent, show=show, fg_color=COLOR_CODIGO,
                               border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
                               text_color=COLOR_TEXTO, height=36, font=(tema.FUENTE_UI, 12))
        entrada.pack(padx=18, pady=(0, 10), fill="x")
        setattr(self, nombre_attr, entrada)

    # ---------------- Matriz en la nube: configuración con botones ----------------
    def _leer_config_json(self):
        """Devuelve el diccionario completo de config_usuario.json."""
        if os.path.exists(self.app.config_path):
            try:
                with open(self.app.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"Error leyendo configuración: {e}")
        return {}

    def _escribir_config_json(self, data):
        """Escribe config_usuario.json (creando la carpeta si hace falta)."""
        carpeta = os.path.dirname(self.app.config_path)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(self.app.config_path, "w", encoding="utf-8") as f:
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
                ok, mensaje = CorreoNube(self.app.config_path).entrar(avisar=avisar)
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

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Desconectar correo")
        dlg.geometry("470x230")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)
        dlg.after(150, dlg.grab_set)
        ctk.CTkLabel(dlg, text="¿Olvidar la sesión de tu correo?",
                     font=(tema.FUENTE_UI, 15, "bold"), text_color=COLOR_TEXTO).pack(
                         anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(dlg,
                     text=("Jarvis borrará el token guardado y dejará de leer tu correo.\n"
                           "Podrás volver a conectarlo cuando quieras."),
                     font=(tema.FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                     justify="left").pack(anchor="w", padx=24)

        def confirmar():
            from modules.correo_nube import CorreoNube
            correo_nube = CorreoNube(self.app.config_path)
            correo_nube.salir()
            dlg.destroy()
            self.lbl_correo.configure(
                text="Correo desconectado. Jarvis ya no accede a tu buzón.",
                text_color=COLOR_TEXTO_SUAVE)

        botones = ctk.CTkFrame(dlg, fg_color="transparent")
        botones.pack(pady=(20, 12))
        ctk.CTkButton(botones, text="Desconectar", command=confirmar,
                      fg_color=COLOR_PELIGRO, hover_color=COLOR_PELIGRO_HOVER, text_color=COLOR_ACENTO_TEXTO,
                      height=34, font=(tema.FUENTE_UI, 12, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, border_width=1, border_color=COLOR_BORDE,
                      height=34, font=(tema.FUENTE_UI, 12)).pack(side="left", padx=6)

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
            cliente_id = Spotify(self.app.config_path).cliente_id()
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
                ok, mensaje = Spotify(self.app.config_path).entrar(avisar=avisar)
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

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Configurar Azure DevOps")
        dlg.geometry("640x640")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Azure DevOps (work items)",
                     font=(tema.FUENTE_UI, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(dlg,
                     text=("Genera un PAT en dev.azure.com → icono de usuario → "
                           "Tokens de acceso personal\n(permiso \"Work Items: Read & "
                           "Write\"). No necesitas una API key de administrador."),
                     font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
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
                         font=(tema.FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(8, 2))
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
                                  font=(tema.FUENTE_UI, 11), justify="left",
                                  wraplength=590)
        lbl_estado.pack(anchor="w", padx=24, pady=(10, 0))

        def _probar():
            datos = {k: e.get().strip() for k, e in entradas.items()}
            lbl_estado.configure(text="Probando conexión...",
                                 text_color=COLOR_TEXTO_SUAVE)
            resultado = {}

            def _worker():
                try:
                    resultado["texto"] = self.app.system.cloud.probar_azure(
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
                      height=36, font=(tema.FUENTE_UI, 12, "bold")).pack(side="right",
                                                                     padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Probar conexión", command=_probar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=36,
                      font=(tema.FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
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

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Desconectar Spotify")
        dlg.geometry("480x230")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)
        dlg.after(150, dlg.grab_set)
        ctk.CTkLabel(dlg, text="¿Olvidar la sesión de Spotify?",
                     font=(tema.FUENTE_UI, 15, "bold"), text_color=COLOR_TEXTO).pack(
                         anchor="w", padx=24, pady=(22, 6))
        ctk.CTkLabel(dlg,
                     text=("Jarvis borrará el token guardado y volverá a pedir permiso "
                           "la próxima vez.\nLa música seguirá funcionando con el "
                           "reproductor de siempre."),
                     font=(tema.FUENTE_UI, 12), text_color=COLOR_TEXTO_SUAVE,
                     justify="left").pack(anchor="w", padx=24)

        def confirmar():
            from modules.spotify import Spotify
            try:
                Spotify(self.app.config_path).salir()
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
                      font=(tema.FUENTE_UI, 12, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO, border_width=1, border_color=COLOR_BORDE,
                      height=34, font=(tema.FUENTE_UI, 12)).pack(side="left", padx=6)

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

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Configurar Spotify")
        dlg.geometry("700x600")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Música con Spotify (API oficial)",
                     font=(tema.FUENTE_UI, 16, "bold"),
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
                     font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24)

        entradas = {}
        for clave, etiqueta, ayuda in (
                ("cliente_id", "Client ID:",
                 "Se copia de tu app de Spotify (no es la contraseña de tu cuenta)."),
                ("dispositivo", "Dispositivo preferido (opcional):",
                 "Parte del nombre del aparato donde quieres que suene (por ejemplo "
                 "«PC-escritorio»). Vacío = el que esté activo.")):
            ctk.CTkLabel(dlg, text=etiqueta, font=(tema.FUENTE_UI, 12),
                         text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(14, 2))
            entrada = ctk.CTkEntry(dlg, height=34, width=620)
            entrada.insert(0, str(spotify.get(clave) or ""))
            entrada.pack(anchor="w", padx=24)
            ctk.CTkLabel(dlg, text=ayuda, font=(tema.FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE, justify="left",
                         wraplength=620).pack(anchor="w", padx=24, pady=(2, 0))
            entradas[clave] = entrada

        lbl_estado = ctk.CTkLabel(dlg, text="", font=(tema.FUENTE_UI, 11),
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
                      font=(tema.FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=36).pack(side="right")

    def _cargar_reglas_ui(self):
        """Vuelca las reglas permanentes guardadas en el editor de la interfaz."""
        if not hasattr(self, "txt_reglas"):
            return
        try:
            reglas = self.app.system.productivity.leer_reglas()
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
        ok = self.app.system.productivity.guardar_reglas(contenido)
        self.btn_guardar_reglas.configure(
            text="Reglas guardadas \u2713" if ok else "Error al guardar")
        self.after(1600, lambda: self.btn_guardar_reglas.configure(
            text="Guardar reglas"))

    def _abrir_config_excel(self):
        """Diálogo para elegir el Excel de la matriz: archivo local o URL."""
        cfg = self._leer_config_json()
        matriz = cfg.get("matriz") if isinstance(cfg.get("matriz"), dict) else {}

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Configurar Excel de la matriz")
        dlg.geometry("700x580")
        dlg.configure(fg_color=COLOR_FONDO)
        dlg.transient(self.app)
        dlg.after(150, dlg.grab_set)

        ctk.CTkLabel(dlg, text="Excel de la matriz", font=(tema.FUENTE_UI, 16, "bold"),
                     text_color=COLOR_TEXTO).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(dlg,
                     text=("Elige el archivo .xlsx o pega el enlace (URL) del Excel.\n"
                           "· Archivo dentro de una carpeta sincronizada de "
                           "OneDrive/SharePoint: se sube solo.\n"
                           "· URL + \"Carpeta sincronizada\": la copia se edita ahí y "
                           "OneDrive sube los cambios a SharePoint solo.\n"
                           "· URL sola: se edita una copia local y los cambios NO llegan a "
                           "SharePoint."),
                     font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24,
                                                          pady=(0, 10))

        ctk.CTkLabel(dlg, text="Archivo (.xlsx) o URL:", text_color=COLOR_TEXTO,
                     font=(tema.FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(6, 2))
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
                    resultado["ruta"] = self.app.system.cloud.descargar_excel(
                        valor, forzar=True, carpeta_sincronizada=carpeta or "")
                except Exception as e:
                    self.app.system.cloud.error_ruta = f"No pude descargar el Excel: {e}"
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
                            text=self.app.system.cloud.error_ruta or
                                 "No pude descargar el Excel.",
                            text_color=COLOR_PELIGRO)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
            dlg.after(250, _revisar)

        ctk.CTkLabel(dlg, text="Hoja:", text_color=COLOR_TEXTO,
                     font=(tema.FUENTE_UI, 12)).pack(anchor="w", padx=24, pady=(12, 2))
        entrada_hoja = ctk.CTkEntry(dlg, fg_color=COLOR_PANEL,
                                    border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
                                    height=34)
        entrada_hoja.pack(padx=24, fill="x")
        entrada_hoja.insert(0, str(matriz.get("hoja") or "Matriz"))

        # Carpeta sincronizada (solo con URL): así los cambios se suben solos a SharePoint
        ctk.CTkLabel(dlg, text="Carpeta sincronizada de OneDrive/SharePoint (opcional):",
                     text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12)).pack(
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
                     font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE,
                     justify="left", wraplength=640).pack(anchor="w", padx=24, pady=(2, 0))

        lbl_estado = ctk.CTkLabel(dlg, text="", text_color=COLOR_TEXTO_SUAVE,
                                  font=(tema.FUENTE_UI, 11), justify="left",
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
                      height=36, font=(tema.FUENTE_UI, 12, "bold")).pack(side="right",
                                                                     padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Descargar URL ahora", command=_descargar,
                      fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
                      text_color=COLOR_ACENTO_TEXTO, height=36,
                      font=(tema.FUENTE_UI, 12, "bold")).pack(side="right", padx=(8, 0))
        ctk.CTkButton(frame_botones, text="Cancelar", command=dlg.destroy,
                      fg_color=COLOR_HOVER, hover_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, height=36).pack(side="right")
