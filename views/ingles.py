"""Apartado del tutor de inglés: la clase, el speaking y el nivel del alumno.

Es un apartado con vida propia (no pasa por el chat): se escribe o se dicta el
texto en su caja, se elige qué preparar y el tutor (`EnglishTutor`) arma la
tarea con el nivel y los fallos del alumno. Las clases las redacta la IA con el
mensaje de sistema del profesor y se pintan en tarjetas (ver `views/base.py`).
"""
import os
import re
import threading
import time
from datetime import datetime

import customtkinter as ctk

from modules.api_brain import APIBrain
from modules.english_tutor import MARCA_TUTOR, NIVELES
from modules import rutas
from ui import tema
from ui.tema import (
    BARRA_SCROLL, COLOR_ACENTO, COLOR_ACENTO_2, COLOR_ACENTO_HOVER,
    COLOR_ACENTO_TEXTO, COLOR_BORDE, COLOR_CODIGO, COLOR_HOVER, COLOR_PANEL,
    COLOR_PELIGRO, COLOR_TARJETA, COLOR_TARJETA_ALTA, COLOR_TEXTO,
    COLOR_TEXTO_SUAVE, RADIO_CHIP, RADIO_TARJETA, _mezclar,
)

from views.base import Vista

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


class VistaIngles(Vista):
    """La clase de inglés: tu texto, las tareas del tutor y el panel de la clase."""

    nombre = "ingles"

    def _preparar(self):
        """Estado del apartado: la última clase, sus tarjetas y el botón de borrar."""
        self._clase_ingles = ""
        self._tarjetas_clase = []   # tarjetas pintadas en el panel de la clase
        self._marcos_clase = []     # marcos de esas tarjetas (título e icono)
        self._ingles_borrar_pendiente = False

    # ---------------- Apartado de inglés (tutor) ----------------
    def _construir(self):
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
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(16, 4))
        ctk.CTkButton(cabecera, text="\u2039  Volver al chat", width=150, height=34,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      text_color=COLOR_TEXTO_SUAVE, anchor="w", font=(tema.FUENTE_UI, 13),
                      command=lambda: self.app._mostrar_vista("chat")).pack(side="left")
        # El icono del apartado en su pastilla de acento, como en la barra lateral
        ctk.CTkLabel(cabecera, text="\U0001F393", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=_mezclar(COLOR_PANEL, COLOR_ACENTO, 0.16),
                     text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 16)).pack(side="left", padx=(16, 8))
        ctk.CTkLabel(cabecera, text="Clase de inglés",
                     font=(tema.FUENTE_UI, 20, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left")
        # El nivel es lo que más se cambia: desplegable con el botón en acento
        ctk.CTkLabel(cabecera, text="\U0001F39A  Nivel", font=(tema.FUENTE_UI, 12),
                     text_color=COLOR_TEXTO_SUAVE).pack(side="right", padx=(0, 8))
        self.menu_ingles_nivel = ctk.CTkOptionMenu(
            cabecera, values=list(NIVELES), width=92, height=34,
            font=(tema.FUENTE_UI, 13, "bold"),
            fg_color=COLOR_TARJETA, button_color=COLOR_ACENTO,
            button_hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_TEXTO,
            dropdown_fg_color=COLOR_TARJETA_ALTA, dropdown_text_color=COLOR_TEXTO,
            dropdown_hover_color=COLOR_HOVER,
            command=self._cambiar_nivel_ingles)
        self.menu_ingles_nivel.pack(side="right")

        # Cómo va el alumno (nivel, prácticas y lo que más se le repite): tarjeta
        # de estado, porque es información de un vistazo y no un párrafo.
        self.marco_ingles_resumen = ctk.CTkFrame(
            self, fg_color=COLOR_TARJETA, corner_radius=RADIO_TARJETA, border_width=1,
            border_color=COLOR_BORDE)
        self.marco_ingles_resumen.pack(fill="x", padx=30, pady=(8, 10))
        ctk.CTkLabel(self.marco_ingles_resumen, text="\U0001F4CA", font=(tema.FUENTE_UI, 13),
                     text_color=COLOR_ACENTO).pack(side="left", padx=(14, 8), pady=8)
        self.lbl_ingles_resumen = ctk.CTkLabel(self.marco_ingles_resumen, text="", anchor="w",
                                               justify="left", font=(tema.FUENTE_UI, 12),
                                               text_color=COLOR_TEXTO_SUAVE, wraplength=820)
        self.lbl_ingles_resumen.pack(side="left", padx=(0, 14), pady=8)

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
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
                                               text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
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
                                              text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
                                              placeholder_text="Tema: p. ej. for y since")
        self.entry_ingles_tema.pack(fill="x")

        cantidades = ctk.CTkFrame(caja_tareas, fg_color="transparent")
        cantidades.pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(cantidades, text="Cuántos (ejercicios o palabras)",
                     font=(tema.FUENTE_UI, 11), text_color=COLOR_TEXTO_SUAVE).pack(side="left")
        self.menu_ingles_cantidad = ctk.CTkOptionMenu(
            cantidades, values=[str(numero) for numero in range(3, 11)], width=76, height=30,
            font=(tema.FUENTE_UI, 12), fg_color=COLOR_CODIGO, button_color=COLOR_TARJETA_ALTA,
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
                rejilla, text=etiqueta, font=(tema.FUENTE_UI, 12), height=36,
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
        ctk.CTkLabel(fila, text="\U0001F393", font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text="Tu clase", font=(tema.FUENTE_UI, 14, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.btn_ingles_copiar = ctk.CTkButton(
            fila, text="\U0001F4CB  Copiar", width=96, height=32, corner_radius=RADIO_CHIP,
            state="disabled", fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=self._copiar_clase_ingles)
        self.btn_ingles_copiar.pack(side="right")
        self.btn_ingles_guardar = ctk.CTkButton(
            fila, text="\U0001F4BE  Guardar en documentos", width=242, height=32,
            corner_radius=RADIO_CHIP, state="disabled", fg_color=COLOR_ACENTO,
            hover_color=COLOR_ACENTO_HOVER, text_color=COLOR_ACENTO_TEXTO,
            font=(tema.FUENTE_UI, 12, "bold"), command=self._guardar_clase_ingles)
        self.btn_ingles_guardar.pack(side="right", padx=(0, 8))

        # Qué está pasando, en su propia línea bajo el título: así el nombre de la
        # clase y los botones tienen su sitio y no se recorta ningún texto.
        self.lbl_ingles_estado = ctk.CTkLabel(derecha, text="Listo cuando quieras.",
                                              font=(tema.FUENTE_UI, 11), anchor="w",
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
            text_color=COLOR_ACENTO, font=(tema.FUENTE_UI, 17),
            command=self._toggle_speaking)
        self.btn_ingles_mic.pack(expand=True)
        texto_speaking = ctk.CTkFrame(caja_speaking, fg_color="transparent")
        texto_speaking.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(texto_speaking, text="\U0001F5E3  Speaking: habla en inglés",
                     font=(tema.FUENTE_UI, 12, "bold"), text_color=COLOR_TEXTO).pack(anchor="w")
        self.lbl_speaking = ctk.CTkLabel(
            texto_speaking, text="Micrófono apagado: pulsa el micro y contéstame en voz alta.",
            font=(tema.FUENTE_UI, 11), anchor="w", justify="left", wraplength=380,
            text_color=COLOR_TEXTO_SUAVE)
        self.lbl_speaking.pack(anchor="w")
        self.btn_speaking_repetir = ctk.CTkButton(
            caja_speaking, text="\U0001F50A  Repetir", width=104, height=30,
            corner_radius=RADIO_CHIP, state="disabled", fg_color=COLOR_TARJETA,
            hover_color=COLOR_HOVER, border_width=1, border_color=COLOR_BORDE,
            text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 11),
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
        self._pintar_tarjetas(self.scroll_ingles, texto, self._tarjetas_clase,
                              self._marcos_clase)

    def _estado_ingles(self, texto, color=None):
        """Escribe en la línea de estado del apartado qué está pasando."""
        self.lbl_ingles_estado.configure(text=texto, text_color=color or COLOR_TEXTO_SUAVE)

    def _actualizar_ingles(self):
        """Refresca la cabecera del apartado con cómo va el alumno."""
        resumen = self.app.system.ingles.resumen()
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
        if nivel != self.app.system.ingles.nivel():
            self.app.system.ingles.fijar_nivel(nivel)
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
        tutor = self.app.system.ingles
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
            clase = self.app.brain.analizar_documento(encargo, sistema=APIBrain.SISTEMA_TUTOR)
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
        if getattr(self.app, "escuchando", False):
            self.app.toggle_escucha()
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
            frase = self.app.voice.escuchar_ingles()
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
                self.app.reproducir_voz(en_voz, idioma="en")   # se oye por los altavoces
            if getattr(self, "_speaking_activo", False):
                self.after(0, lambda: self._estado_speaking(
                    "Te escucho… habla en inglés.", COLOR_ACENTO))

    def _clase_speaking(self, frase):
        """Pide la charla a la IA con lo que se ha oído (hilo de trabajo)."""
        try:
            encargo = self.app.system.ingles.speaking(frase, getattr(self, "_speaking_tema", ""))
            if not str(encargo).startswith(MARCA_TUTOR):
                # Aviso del tutor (no hay nada que pedir a la IA): se enseña tal cual.
                self.after(0, lambda t=str(encargo): self._mostrar_speaking(frase, t, ""))
                return ""
            return self.app.brain.analizar_documento(str(encargo)[len(MARCA_TUTOR):],
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
            target=lambda: self.app.reproducir_voz(self._ultimo_en_voz, idioma="en"),
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
        secciones = Vista._secciones_de_clase(clase)
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
