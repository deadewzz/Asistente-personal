"""La ventana de una zona del taller: el contenido de una tarea, con sitio.

Cada botón de «Qué quieres hacer» tiene su zona en el taller (su pestaña en el
centro). Esta ventana es esa misma zona, pero aparte: sirve para leer dos cosas a
la vez —la lección y los ejercicios, el avance y la documentación…— sin que una
tape a la otra.

La ventana no guarda nada por su cuenta: enseña lo que le pasa el taller y, si el
taller vuelve a escribir en esa zona, se actualiza sola (`actualizar`). Copiar y
guardar se lo pide al taller (`copiar_zona_programacion` y
`guardar_zona_programacion`), que es el que tiene el texto de la zona.
"""
from datetime import datetime

import customtkinter as ctk

from ui import tema
from ui.tema import (
    BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_HOVER, COLOR_ACENTO_TEXTO,
    COLOR_BORDE, COLOR_FONDO, COLOR_HOVER, COLOR_OK, COLOR_TARJETA,
    COLOR_TARJETA_ALTA, COLOR_TEXTO, COLOR_TEXTO_SUAVE, RADIO_CHIP, RADIO_TARJETA,
)


class VentanaZonaProgramacion(ctk.CTkToplevel):
    """Ventana aparte con una zona del taller (sus tarjetas y sus botones)."""

    ANCHO = 880
    ALTO = 680

    def __init__(self, vista, clave, texto=""):
        super().__init__(vista.app)
        #: El taller: de él salen el texto de la zona y su copia/guardado.
        self.vista = vista
        self.app = vista.app
        self.clave = clave
        zona = vista.zonas_programacion().get(clave) or {}
        self.titulo = zona.get("titulo") or "Zona del taller"
        self.icono = zona.get("icono") or "\U0001F4C4"
        self.ayuda = zona.get("ayuda") or ""
        self.texto = ""
        self.tarjetas = []      # [(título, área)] de lo que se ve (como el taller)
        self.marcos = []        # marcos de las tarjetas (icono y título)
        self.title(f"{self.titulo} \u00b7 Jarvis")
        self.geometry(f"{self.ANCHO}x{self.ALTO}")
        self.minsize(560, 420)
        self.configure(fg_color=COLOR_FONDO)
        self.transient(self.app)
        self._construir()
        self.actualizar(texto)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(120, self._al_abrir)

    # ---------------- Lo que hay dentro de la ventana ----------------
    def _construir(self):
        """Monta la cabecera, la barra de copiar/guardar y las tarjetas."""
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=20, pady=(14, 4))
        ctk.CTkLabel(cabecera, text=self.icono, width=34, height=34,
                     corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA,
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 16)).pack(side="left")
        ctk.CTkLabel(cabecera, text=self.titulo, font=(tema.FUENTE_UI, 18, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(10, 8))
        ctk.CTkLabel(cabecera, text="zona independiente del taller",
                     font=(tema.FUENTE_UI, 11),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="left", pady=(4, 0))
        ctk.CTkButton(cabecera, text="Cerrar", width=86, height=32,
                      corner_radius=RADIO_CHIP, fg_color="transparent",
                      hover_color=COLOR_HOVER, text_color=COLOR_TEXTO_SUAVE,
                      font=(tema.FUENTE_UI, 12),
                      command=self._cerrar).pack(side="right")

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=20, pady=(0, 8))
        self.btn_copiar = ctk.CTkButton(
            barra, text="\U0001F4CB  Copiar", width=124, height=34,
            corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=self._copiar)
        self.btn_copiar.pack(side="left")
        self.btn_guardar = ctk.CTkButton(
            barra, text="\U0001F4BE  Guardar .md", width=150, height=34,
            corner_radius=RADIO_CHIP, fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO, font=(tema.FUENTE_UI, 12, "bold"),
            command=self._guardar)
        self.btn_guardar.pack(side="left", padx=(8, 0))
        self.lbl_estado = ctk.CTkLabel(barra, text="", font=(tema.FUENTE_UI, 11),
                                       text_color=COLOR_TEXTO_SUAVE)
        self.lbl_estado.pack(side="right")

        self.marco = ctk.CTkFrame(self, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA,
                                  border_width=1, border_color=COLOR_BORDE)
        self.marco.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        if self.ayuda:
            ctk.CTkLabel(self.marco, text=self.ayuda, font=(tema.FUENTE_UI, 11),
                         text_color=COLOR_TEXTO_SUAVE, anchor="w", justify="left",
                         wraplength=760).pack(fill="x", padx=16, pady=(10, 0))
        self.scroll = ctk.CTkScrollableFrame(self.marco, fg_color="transparent",
                                             **BARRA_SCROLL)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=(6, 8))
        ctk.CTkLabel(self, text="Si el taller vuelve a escribir en esta zona, esta "
                               "ventana se actualiza sola.",
                     font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE,
                     anchor="w").pack(fill="x", padx=22, pady=(0, 12))

    # ---------------- El contenido de la zona ----------------
    def actualizar(self, texto):
        """Redibuja las tarjetas con lo último que ha escrito el taller."""
        self.texto = str(texto or "")
        self.vista._pintar_tarjetas(self.scroll, self.texto, self.tarjetas, self.marcos)
        listos = "normal" if self.texto else "disabled"
        for boton in (self.btn_copiar, self.btn_guardar):
            try:
                boton.configure(state=listos)
            except Exception:
                pass
        if not self.texto:
            self.estado("Todavía no hay nada en esta zona.")
        return self.texto

    def estado(self, texto, color=None):
        """Escribe en la línea de estado de la ventana (la usa el taller)."""
        try:
            self.lbl_estado.configure(text=str(texto or ""),
                                      text_color=color or COLOR_TEXTO_SUAVE)
        except Exception:
            pass

    def _copiar(self):
        """Copia el texto de la zona (lo hace el taller, que es quien lo tiene)."""
        self.vista.copiar_zona_programacion(self.clave)

    def _guardar(self):
        """Guarda el texto de la zona como `.md` (lo hace el taller)."""
        if self.vista.guardar_zona_programacion(self.clave):
            self.estado(f"Guardado ({datetime.now().strftime('%H:%M')}).", COLOR_OK)

    def _al_abrir(self):
        """Deja la ventana delante y con el foco, sin bloquear el taller."""
        try:
            if not self.winfo_exists():
                return
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _cerrar(self):
        """Cierra la ventana: la zona sigue en el taller, tal y como esté."""
        try:
            zona = self.vista.zonas_programacion().get(self.clave)
            if zona is not None and zona.get("ventana") is self:
                zona["ventana"] = None
        except Exception:
            pass
        self.destroy()
