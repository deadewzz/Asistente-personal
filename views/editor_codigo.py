"""La ventana del código: el editor grande, el botón ▶ Ejecutar y su consola.

En el apartado se ve el programa y sus avisos, pero se escribe aquí: una ventana
aparte con sitio de sobra, el código arriba y la consola debajo, que es donde
sale lo que imprime el programa (`System.out.println`) al pulsar **▶ Ejecutar**.

La ventana no guarda nada por su cuenta: lee y escribe el programa en el
apartado (`vista.codigo_programacion()` y `vista.fijar_codigo_programacion`), que
es el que lo revisa mientras se escribe y el que apunta el avance del alumno. Así
el taller y el editor nunca enseñan cosas distintas.
"""
import os
import re
import tkinter as tk

import customtkinter as ctk

from ui import tema
from ui.tema import (
    COLOR_ACENTO, COLOR_ACENTO_2, COLOR_ACENTO_HOVER, COLOR_ACENTO_TEXTO,
    COLOR_AVISO, COLOR_BORDE, COLOR_CODIGO, COLOR_CODIGO_TEXTO, COLOR_FONDO, COLOR_HOVER,
    COLOR_OK, COLOR_PANEL, COLOR_PELIGRO, COLOR_TARJETA_ALTA, COLOR_TEXTO,
    COLOR_TEXTO_SUAVE, RADIO_CHIP, RADIO_TARJETA,
)
from views.base import caja_consola, escribir_consola, limpiar_consola

# ---------------- Coloreado del código (ligero, sin depender de nada) ----------------
#: Palabras de Java que se pintan en azul eléctrico (el segundo color de la casa).
PALABRAS_JAVA = frozenset("""
abstract assert boolean break byte case catch char class const continue default do
double else enum extends final finally float for goto if implements import instanceof
int interface long native new package private protected public return short static
strictfp super switch synchronized this throw throws transient try void volatile while
var record true false null String System Scanner Math Integer Double Boolean List
ArrayList HashMap Map Set
""".split())

RE_PALABRA = re.compile(r"\b[A-Za-z_$][\w$]*\b")
RE_CADENA = re.compile(r'"(?:[^"\\\n]|\\.)*"')
RE_COMENTARIO = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
RE_NUMERO = re.compile(r"\b\d+(?:\.\d+)?[fFdDlL]?\b")
RE_CLASE = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")

#: Lo que se escribe al pulsar Tab (Java usa cuatro espacios, no tabuladores).
SANGRIA = "    "


class VentanaEditorCodigo(ctk.CTkToplevel):
    """Ventana aparte con el editor de Java, el botón ▶ Ejecutar y la consola."""

    ANCHO = 1060
    ALTO = 730

    def __init__(self, vista):
        super().__init__(vista.app)
        #: El apartado de programación: de él salen el programa, los avisos y el
        #: módulo que compila y ejecuta (`app.system.programacion`).
        self.vista = vista
        self.app = vista.app
        self._resaltado = None      # `after` del coloreado mientras se escribe
        self._ejecutando = False
        self.title("Editor de Java \u00b7 Jarvis")
        self.geometry(f"{self.ANCHO}x{self.ALTO}")
        self.minsize(720, 480)
        self.configure(fg_color=COLOR_FONDO)
        self.transient(self.app)
        self._construir()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.vista.after(140, self._al_abrir)

    # ---------------- Lo que hay dentro de la ventana ----------------
    def _construir(self):
        """Monta la ventana: cabecera, botones, el editor y la consola."""
        self._crear_cabecera()
        self._crear_barra_botones()
        self._crear_editor()
        self._crear_consola()

    def _crear_cabecera(self):
        """La cabecera: qué se está editando y si se puede compilar de verdad."""
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=20, pady=(14, 6))
        ctk.CTkLabel(cabecera, text="\u2328", width=34, height=34, corner_radius=RADIO_CHIP,
                     fg_color=COLOR_TARJETA_ALTA, text_color=COLOR_ACENTO,
                     font=(tema.FUENTE_UI, 16)).pack(side="left")
        ctk.CTkLabel(cabecera, text="Editor de Java", font=(tema.FUENTE_UI, 18, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(10, 8))
        self.lbl_archivo = ctk.CTkLabel(cabecera, text="Hola.java",
                                        font=(tema.FUENTE_MONO, 12),
                                        text_color=COLOR_TEXTO_SUAVE)
        self.lbl_archivo.pack(side="left", pady=(4, 0))
        self.btn_guardar_java = ctk.CTkButton(
            cabecera, text="\U0001F4BE  Guardar .java", width=150, height=32,
            corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDE, text_color=COLOR_TEXTO,
            font=(tema.FUENTE_UI, 12), command=self._guardar_java)
        self.btn_guardar_java.pack(side="right")
        self.lbl_jdk = ctk.CTkLabel(
            cabecera, text="", height=26, corner_radius=RADIO_CHIP, padx=12,
            fg_color=COLOR_TARJETA_ALTA, text_color=COLOR_TEXTO_SUAVE,
            font=(tema.FUENTE_UI, 11, "bold"))
        self.lbl_jdk.pack(side="right", padx=(0, 10))

    def _crear_barra_botones(self):
        """La barra de trabajo: ejecutar, corregir, limpiar y el estado."""
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=20, pady=(0, 8))
        self.btn_ejecutar = ctk.CTkButton(
            barra, text="\u25B6  Ejecutar", width=132, height=36, corner_radius=RADIO_CHIP,
            fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
            text_color=COLOR_ACENTO_TEXTO, font=(tema.FUENTE_UI, 13, "bold"),
            command=self._ejecutar)
        self.btn_ejecutar.pack(side="left")
        ctk.CTkButton(barra, text="\U0001F50E  Corregir", width=126, height=36,
                      corner_radius=RADIO_CHIP, fg_color=COLOR_TARJETA_ALTA,
                      hover_color=COLOR_HOVER, border_width=1, border_color=COLOR_BORDE,
                      text_color=COLOR_TEXTO, font=(tema.FUENTE_UI, 12),
                      command=self._corregir).pack(side="left", padx=(8, 0))
        ctk.CTkButton(barra, text="\U0001F9F9  Limpiar consola", width=150, height=36,
                      corner_radius=RADIO_CHIP, fg_color="transparent",
                      hover_color=COLOR_HOVER, text_color=COLOR_TEXTO_SUAVE,
                      font=(tema.FUENTE_UI, 12),
                      command=self._limpiar).pack(side="left", padx=(8, 0))
        self.lbl_estado = ctk.CTkLabel(barra, text="Listo cuando quieras.",
                                       font=(tema.FUENTE_UI, 11),
                                       text_color=COLOR_TEXTO_SUAVE)
        self.lbl_estado.pack(side="right")

    def _crear_editor(self):
        """El editor: números de línea, el código y las barras de desplazamiento."""
        marco = ctk.CTkFrame(self, fg_color=COLOR_CODIGO, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=COLOR_BORDE)
        marco.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        interior = ctk.CTkFrame(marco, fg_color="transparent")
        interior.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.numeros = tk.Text(interior, width=4, state="disabled", wrap="none",
                               bg=COLOR_CODIGO, fg=COLOR_TEXTO_SUAVE, borderwidth=0,
                               highlightthickness=0, padx=6, pady=8,
                               font=(tema.FUENTE_MONO, 13))
        self.txt_codigo = tk.Text(interior, wrap="none", undo=True, maxundo=600,
                                  bg=COLOR_CODIGO, fg=COLOR_CODIGO_TEXTO, borderwidth=0,
                                  highlightthickness=0, insertbackground=COLOR_ACENTO,
                                  selectbackground=COLOR_HOVER, selectforeground=COLOR_TEXTO,
                                  padx=8, pady=8, font=(tema.FUENTE_MONO, 13))
        barra_v = ctk.CTkScrollbar(interior, command=self.txt_codigo.yview, width=12,
                                   button_color=COLOR_TARJETA_ALTA,
                                   button_hover_color=COLOR_ACENTO)
        barra_h = ctk.CTkScrollbar(interior, command=self.txt_codigo.xview, height=12,
                                   orientation="horizontal",
                                   button_color=COLOR_TARJETA_ALTA,
                                   button_hover_color=COLOR_ACENTO)
        self.txt_codigo.configure(xscrollcommand=barra_h.set,
                                  yscrollcommand=lambda primero, ultimo: (
                                      barra_v.set(primero, ultimo),
                                      self.numeros.yview_moveto(primero)))
        self.numeros.pack(side="left", fill="y")
        barra_v.pack(side="right", fill="y", padx=(4, 0))
        barra_h.pack(side="bottom", fill="x", pady=(4, 0))
        self.txt_codigo.pack(side="left", fill="both", expand=True)
        self._colorear_etiquetas()
        self.txt_codigo.insert("1.0", self.vista.codigo_programacion())
        self.txt_codigo.bind("<KeyRelease>", self._al_escribir)
        self.txt_codigo.bind("<<Paste>>", lambda e: self.vista.after(30, self._al_escribir))
        self.txt_codigo.bind("<Tab>", self._sangrar)
        self.txt_codigo.bind("<F5>", lambda e: (self._ejecutar(), "break")[1])
        self.txt_codigo.bind("<Control-Return>", lambda e: (self._ejecutar(), "break")[1])
        self.txt_codigo.bind("<Control-s>", lambda e: (self._guardar_java(), "break")[1])
        pie = ctk.CTkLabel(marco, text="Tab = 4 espacios  \u00b7  F5 ejecuta  "
                                       "\u00b7  Ctrl+S guarda el .java",
                           font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE)
        pie.pack(fill="x", padx=14, pady=(2, 8))
        self._refrescar_numeros()
        self._pintar_colores()

    def _crear_consola(self):
        """La consola: lo que imprime el programa y lo que leerá por teclado."""
        marco = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=RADIO_TARJETA,
                             border_width=1, border_color=COLOR_BORDE)
        marco.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(fila, text="\u25B6", font=(tema.FUENTE_UI, 12),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(fila, text="Consola", font=(tema.FUENTE_UI, 12, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        self.lbl_consola = ctk.CTkLabel(fila, text="Sin ejecutar",
                                        font=(tema.FUENTE_UI, 10),
                                        text_color=COLOR_TEXTO_SUAVE)
        self.lbl_consola.pack(side="right")
        contenedor, self.consola = caja_consola(marco, alto=9, tam=12)
        contenedor.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        entrar = ctk.CTkFrame(marco, fg_color="transparent")
        entrar.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(entrar, text="Entrada (Scanner): un dato por línea",
                     font=(tema.FUENTE_UI, 10), text_color=COLOR_TEXTO_SUAVE).pack(anchor="w")
        self.txt_entrada = ctk.CTkTextbox(
            entrar, height=44, fg_color=COLOR_CODIGO, border_width=1,
            border_color=COLOR_BORDE, corner_radius=RADIO_CHIP,
            text_color=COLOR_TEXTO, font=(tema.FUENTE_MONO, 11), wrap="none")
        self.txt_entrada.pack(fill="x", pady=(4, 0))
        self.txt_entrada.insert("1.0", self.vista.entrada_programacion())
        self.txt_entrada.bind("<KeyRelease>", lambda e: self._al_escribir_entrada())
        self.vista._atajos_caja(self.txt_entrada)

    # ---------------- El código: lo que se escribe y cómo se pinta ----------------
    def codigo(self):
        """El programa que hay escrito en el editor ahora mismo."""
        return self.txt_codigo.get("1.0", "end-1c")

    def _al_abrir(self):
        """Deja la ventana lista: avisa del JDK, saluda en la consola y pone el foco."""
        if not self.winfo_exists():
            return
        jdk = bool(self.vista.app.system.programacion.hay_jdk())
        self.lbl_jdk.configure(text="JDK instalado" if jdk else "sin JDK",
                               text_color=COLOR_OK if jdk else COLOR_AVISO)
        escribir_consola(self.consola, "Escribe tu programa y pulsa \u25B6 Ejecutar (F5): "
                                       "aquí sale lo que imprima.\n", "info")
        self.lbl_archivo.configure(text=f"{nombre_de_clase(self.codigo())}.java")
        self.txt_codigo.focus_set()
        self.lift()

    def _al_escribir(self, evento=None):
        """Cada tecla: el programa va al taller, se numeran las líneas y se colorea."""
        codigo = self.codigo()
        self.lbl_archivo.configure(text=f"{nombre_de_clase(codigo)}.java")
        self.vista.fijar_codigo_programacion(codigo, revisar=True)
        self._refrescar_numeros()
        if self._resaltado is not None:
            try:
                self.vista.after_cancel(self._resaltado)
            except Exception:
                pass
        self._resaltado = self.vista.after(140, self._pintar_colores)

    def _sangrar(self, evento=None):
        """Tab escribe cuatro espacios (en Java no se usan tabuladores)."""
        self.txt_codigo.insert("insert", SANGRIA)
        self._al_escribir()
        return "break"

    def _al_escribir_entrada(self):
        """Lo que se escriba en «Entrada» es lo que leerá el programa por teclado."""
        self.vista.fijar_entrada_programacion(self.txt_entrada.get("1.0", "end-1c"))

    def _refrescar_numeros(self):
        """Numera las líneas del código (y las deja a la altura del texto)."""
        lineas = int(self.txt_codigo.index("end-1c").split(".")[0])
        if self.numeros.get("1.0", "end-1c").count("\n") + 1 == lineas:
            return
        self.numeros.configure(state="normal")
        self.numeros.delete("1.0", "end")
        self.numeros.insert("1.0", "\n".join(str(numero) for numero in range(1, lineas + 1)))
        self.numeros.configure(state="disabled")
        self.numeros.yview_moveto(self.txt_codigo.yview()[0])

    def _colorear_etiquetas(self):
        """Prepara los colores del código (se crean una vez, al montar el editor)."""
        #: primero las palabras y los números, y al final cadenas y comentarios: así
        #: lo que va entre comillas gana a la palabra que lleve dentro.
        self.txt_codigo.tag_configure("palabra", foreground=COLOR_ACENTO_2)
        self.txt_codigo.tag_configure("numero", foreground=COLOR_ACENTO)
        self.txt_codigo.tag_configure("cadena", foreground=COLOR_OK)
        self.txt_codigo.tag_configure("comentario", foreground=COLOR_TEXTO_SUAVE)

    def _pintar_colores(self):
        """Pinta palabras de Java, números, cadenas y comentarios (sin tocar el texto)."""
        self._resaltado = None
        if not self.winfo_exists():
            return
        codigo = self.codigo()
        for etiqueta in ("palabra", "numero", "cadena", "comentario"):
            self.txt_codigo.tag_remove(etiqueta, "1.0", "end")
        for encontrado in RE_PALABRA.finditer(codigo):
            if encontrado.group() in PALABRAS_JAVA:
                self._marcar("palabra", encontrado.start(), encontrado.end())
        for encontrado in RE_NUMERO.finditer(codigo):
            self._marcar("numero", encontrado.start(), encontrado.end())
        for encontrado in RE_CADENA.finditer(codigo):
            self._marcar("cadena", encontrado.start(), encontrado.end())
        for encontrado in RE_COMENTARIO.finditer(codigo):
            self._marcar("comentario", encontrado.start(), encontrado.end())

    def _marcar(self, etiqueta, inicio, fin):
        """Colorea un trozo del código contado en caracteres desde el principio."""
        self.txt_codigo.tag_add(etiqueta, f"1.0 + {inicio} c", f"1.0 + {fin} c")

    # ---------------- Ejecutar, corregir y guardar ----------------
    def _ejecutar(self):
        """Manda el programa a compilar y ejecutar; lo que imprima sale en la consola."""
        if self._ejecutando:
            return                  # ya hay una ejecución en marcha: no se duplica
        if not self.codigo().strip():
            escribir_consola(self.consola, "Escribe el programa antes de ejecutarlo.\n",
                             "aviso")
            self.lbl_estado.configure(text="No hay programa que ejecutar.",
                                      text_color=COLOR_AVISO)
            return
        self._ejecutando = True
        self._al_escribir()         # el taller trabaja siempre con el código de ahora
        clase = nombre_de_clase(self.codigo())
        self.btn_ejecutar.configure(state="disabled", text="\u23F3  Ejecutando\u2026")
        self.lbl_estado.configure(text="Compilando y ejecutando\u2026",
                                  text_color=COLOR_TEXTO_SUAVE)
        self.lbl_consola.configure(text="Ejecutando\u2026", text_color=COLOR_ACENTO)
        limpiar_consola(self.consola)
        escribir_consola(self.consola, f"$ javac {clase}.java\n$ java {clase}\n", "prompt")
        self.vista.ejecutar_programacion(al_terminar=self._mostrar_salida)

    def _mostrar_salida(self, datos):
        """Enseña en la consola lo que ha impreso el programa (o por qué no corrió)."""
        self._ejecutando = False
        if not self.winfo_exists():
            return
        self.btn_ejecutar.configure(state="normal", text="\u25B6  Ejecutar")
        if not datos.get("jdk"):
            escribir_consola(self.consola, "Para ejecutarlo hace falta el JDK de Java "
                                           "(javac y java). Instálalo y vuelve a probar.\n",
                             "aviso")
            self.lbl_consola.configure(text="Sin JDK", text_color=COLOR_AVISO)
            self.lbl_estado.configure(text="Sin JDK no se puede ejecutar.",
                                      text_color=COLOR_AVISO)
            return
        if datos.get("errores") and not datos.get("compilado"):
            escribir_consola(self.consola, "Todavía no compila:\n", "error")
            escribir_consola(self.consola, self.vista._avisos_de_revision(datos) + "\n",
                             "error")
            self.lbl_consola.configure(text="No compila", text_color=COLOR_PELIGRO)
            self.lbl_estado.configure(text="Hay fallos: mira la revisión del taller.",
                                      text_color=COLOR_AVISO)
            return
        salida = (datos.get("salida") or "").rstrip()
        escribir_consola(self.consola, (salida or "(el programa no imprimió nada)") + "\n",
                         "salida")
        if datos.get("ok"):
            escribir_consola(self.consola, "\n[terminó bien: código 0]\n", "ok")
            self.lbl_consola.configure(text="Código 0", text_color=COLOR_OK)
            self.lbl_estado.configure(text="Salió bien: eso es lo que ha impreso.",
                                      text_color=COLOR_OK)
        else:
            escribir_consola(self.consola, "\n[terminó con un error]\n", "error")
            self.lbl_consola.configure(text="Con errores", text_color=COLOR_PELIGRO)
            self.lbl_estado.configure(text="Terminó con un error: mira la consola.",
                                      text_color=COLOR_AVISO)

    def _corregir(self):
        """Pasa el compilador de verdad y deja los fallos en la revisión del taller."""
        self._al_escribir()
        clase = nombre_de_clase(self.codigo())
        datos = self.vista.corregir_programacion()
        limpiar_consola(self.consola)
        escribir_consola(self.consola, f"$ javac {clase}.java\n", "prompt")
        escribir_consola(self.consola, self.vista._avisos_de_revision(datos) + "\n",
                         "error" if datos.get("errores") else "ok")
        self.lbl_consola.configure(
            text="Revisado" if not datos.get("errores") else "Con avisos",
            text_color=COLOR_OK if not datos.get("errores") else COLOR_AVISO)
        self.lbl_estado.configure(
            text="Nada que corregir." if not datos.get("errores")
            else "Mira la consola y la revisión del taller.",
            text_color=COLOR_OK if not datos.get("errores") else COLOR_AVISO)

    def _guardar_java(self):
        """Guarda el programa como `.java` en la carpeta de documentos."""
        ruta = self.vista.guardar_java()
        if not ruta:
            return
        escribir_consola(self.consola, f"Guardado en {ruta}\n", "ok")
        self.lbl_estado.configure(text=f"Guardado {os.path.basename(ruta)}",
                                  text_color=COLOR_OK)

    def _limpiar(self):
        """Vacía la consola (el código se queda como está)."""
        limpiar_consola(self.consola)
        self.lbl_consola.configure(text="Sin ejecutar", text_color=COLOR_TEXTO_SUAVE)

    def _cerrar(self):
        """Cierra la ventana: el programa se queda en el taller, tal y como esté."""
        self._al_escribir()
        if getattr(self.vista, "_editor", None) is self:
            self.vista._editor = None
        self.destroy()


def nombre_de_clase(codigo, defecto="Hola"):
    """El nombre de la clase pública del programa (es el del archivo .java)."""
    encontrado = RE_CLASE.search(str(codigo or ""))
    return encontrado.group(1) if encontrado else defecto
