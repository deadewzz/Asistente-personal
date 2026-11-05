"""La base de los apartados: un marco con lo que se repite en todos.

Cada apartado de Jarvis es una vista: un `CTkFrame` que la ventana coloca en el
área principal y que guarda **sus** widgets, su estado y sus métodos. La ventana
no entra en lo que hay dentro: solo la enseña y la esconde, y le pasa lo que
comparten todos (el cerebro, las acciones del sistema y la voz) en `self.app`.

Esta base trae lo común: los atajos de edición de las cajas, el Markdown de los
paneles (con sus bloques de código) y las tarjetas con icono que usan la clase
de inglés y el taller de programación.
"""
import os
import re
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from modules import rutas
from ui import tema
from ui import scroll as rueda
from ui.tema import (
    ATAJOS_CAJA, COLOR_ACENTO, COLOR_AVISO, COLOR_BORDE, COLOR_CODIGO,
    COLOR_CODIGO_TEXTO, COLOR_OK, COLOR_PELIGRO, COLOR_TARJETA, COLOR_TARJETA_ALTA,
    COLOR_TEXTO, COLOR_TEXTO_SUAVE, RADIO_CHIP, RADIO_TARJETA, _mezclar,
)

#: Carpeta de los documentos que crea la app (`crear_documento_txt`).
CARPETA_DOCUMENTOS = rutas.DOCUMENTOS

# ---------------- La consola del taller de programación ----------------
# Lo que imprime un programa se lee en una caja de solo lectura con un color por
# tipo de línea: la salida en claro, los errores en rojo, las órdenes que se
# lanzan en acento y las notas en gris. La usan las dos consolas del taller: la
# del propio apartado y la de la ventana del editor.
COLORES_CONSOLA = {
    "salida": COLOR_TEXTO,
    "ok": COLOR_OK,
    "error": COLOR_PELIGRO,
    "aviso": COLOR_AVISO,
    "info": COLOR_TEXTO_SUAVE,
    "prompt": COLOR_ACENTO,
}


def caja_consola(parent, alto=8, tam=11):
    """Crea una consola: devuelve el marco que se coloca y la caja donde escribir."""
    marco = ctk.CTkFrame(parent, fg_color=COLOR_CODIGO, corner_radius=RADIO_CHIP,
                         border_width=1, border_color=COLOR_BORDE)
    caja = tk.Text(marco, height=alto, wrap="word", borderwidth=0, highlightthickness=0,
                   bg=COLOR_CODIGO, fg=COLOR_TEXTO, insertbackground=COLOR_ACENTO,
                   padx=10, pady=8, spacing1=1, spacing3=1, font=(tema.FUENTE_MONO, tam),
                   state="disabled")
    barra = ctk.CTkScrollbar(marco, command=caja.yview, width=10,
                             button_color=COLOR_TARJETA_ALTA,
                             button_hover_color=COLOR_ACENTO)
    caja.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y", padx=(0, 4), pady=4)
    caja.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
    for etiqueta, color in COLORES_CONSOLA.items():
        caja.tag_configure(etiqueta, foreground=color)
    rueda.acelerar_caja(caja)       # la rueda avanza varias líneas de golpe
    return marco, caja


def escribir_consola(caja, texto, etiqueta="salida"):
    """Añade texto a una consola y la deja abajo del todo (como una terminal)."""
    caja.configure(state="normal")
    caja.insert("end", texto, etiqueta)
    caja.see("end")
    caja.configure(state="disabled")


def limpiar_consola(caja):
    """Borra todo lo que hay en una consola."""
    caja.configure(state="normal")
    caja.delete("1.0", "end")
    caja.configure(state="disabled")


class Vista(ctk.CTkFrame):
    """Un apartado de la ventana, con su propia vida (widgets, estado y métodos)."""

    #: Nombre con el que la ventana lo enseña («chat», «ingles», «programar»...).
    nombre = ""

    def __init__(self, app):
        super().__init__(app.area_principal, fg_color="transparent")
        #: La ventana que la contiene: de ahí salen los servicios compartidos
        #: (`app.brain`, `app.system`, `app.voice`...) y el cambio de apartado.
        self.app = app
        self._preparar()      # el estado propio, antes de montar nada
        self._construir()     # los widgets, dentro de sí misma

    def _preparar(self):
        """Prepara el estado propio de la vista (antes de montar los widgets)."""

    def _construir(self):
        """Monta los widgets de la vista. Cada apartado escribe los suyos."""

    def _es_caja_chat(self, caja):
        """¿Esa caja de escribir es la del chat? (solo el chat tiene su aviso)."""
        return False

    # --- Un solo bucle de eventos: los `after` se cuelgan de la ventana -------
    # Tk apunta cada `after` al widget que lo pide y lo borra al destruirlo; con
    # apartados que van y vienen, eso deja avisos pendientes de un marco que ya
    # no está. En Jarvis hay una sola ventana, así que todo se programa en ella.
    def after(self, ms, func=None, *args):
        """Programa algo en el bucle de la ventana (no en este marco)."""
        if func is None:
            return self.app.after(ms)
        return self.app.after(ms, func, *args)

    def after_cancel(self, ident):
        """Cancela algo programado en el bucle de la ventana."""
        return self.app.after_cancel(ident)

    def after_idle(self, func, *args):
        """Programa algo para cuando la ventana esté al día."""
        return self.app.after_idle(func, *args)

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

    def _caja_de(self, evento, caja):
        """El widget que hay que editar: el que se pasa o el que disparó la tecla."""
        if caja is not None:
            return caja
        return getattr(evento, "widget", None)

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

    def _pintar_tarjetas(self, panel, texto, tarjetas, marcos):
        """Redibuja un panel de tarjetas: una por apartado del Markdown.

        Lo usan la clase de inglés y el taller de programación: el mismo Markdown,
        el mismo aspecto y cada uno en su panel. ``tarjetas`` y ``marcos`` se
        rellenan con lo pintado (los usan las pruebas y los botones de copiar).
        """
        for widget in panel.winfo_children():
            widget.destroy()
        del tarjetas[:]                # [(título, área de texto)] de lo que se ve
        del marcos[:]                  # marcos de las tarjetas (para las pruebas)
        for seccion in self._secciones_de_clase(texto):
            self._tarjeta_clase(seccion, panel, tarjetas, marcos)
        try:
            panel._parent_canvas.yview_moveto(0)
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
                icono, nombre = Vista._separar_icono(titulo.group(1))
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

    def _tarjeta_clase(self, seccion, panel=None, tarjetas=None, marcos=None):
        """Pinta un apartado de la clase como tarjeta con su icono y su texto.

        La tarjeta de la versión corregida (lo que el alumno se lleva) lleva el
        borde encendido en el color de acento: es la que destaca entre las demás.
        Sin ``panel`` pinta en el de la clase de inglés (el de siempre).
        """
        panel = self.scroll_ingles if panel is None else panel
        tarjetas = self._tarjetas_clase if tarjetas is None else tarjetas
        marcos = self._marcos_clase if marcos is None else marcos
        titulo = seccion["titulo"]
        es_correccion = bool(re.search(r"corregid|versi[oó]n", titulo, re.I))
        marco = ctk.CTkFrame(
            panel, fg_color=COLOR_TARJETA_ALTA, corner_radius=RADIO_TARJETA,
            border_width=1, border_color=COLOR_ACENTO if es_correccion else COLOR_BORDE)
        marco.pack(fill="x", padx=6, pady=(0, 10))
        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(cabecera, text=seccion["icono"], font=(tema.FUENTE_UI, 15),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(cabecera, text=titulo, font=(tema.FUENTE_UI, 13, "bold"),
                     text_color=COLOR_ACENTO if es_correccion else COLOR_TEXTO).pack(
                         side="left", padx=(8, 0))
        if es_correccion:
            ctk.CTkLabel(cabecera, text="listo para copiar", font=(tema.FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE).pack(side="right")
        area = self._area_de_tarjeta(marco, seccion["lineas"], panel)
        if area is not None:
            tarjetas.append((titulo, area))
            marcos.append({"marco": marco, "icono": seccion["icono"],
                           "titulo": titulo})

    def _area_de_tarjeta(self, marco, lineas, panel=None):
        """Pinta las líneas de un apartado de la clase y devuelve su área de texto.

        Se usa un `tk.Text` (y no el de customtkinter) porque permite cambiar la
        tipografía por línea: hace falta para el monoespaciado de los ejemplos y los
        ejercicios, y para las negritas dentro del propio texto.
        """
        panel = self.scroll_ingles if panel is None else panel
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
        self._permitir_rueda(area, panel)
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
                       font=(tema.FUENTE_UI, tam), padx=0, pady=0, cursor="arrow",
                       spacing1=2, spacing3=2, takefocus=0,
                       selectbackground=_mezclar(fondo, COLOR_ACENTO, 0.35),
                       selectforeground=COLOR_TEXTO, **ancho)
        area.tag_config("fuerte", font=(tema.FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        area.tag_config("cursiva", font=(tema.FUENTE_UI, tam, "italic"))
        area.tag_config("titulo", font=(tema.FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        area.tag_config("cita", font=(tema.FUENTE_UI, tam, "italic"), foreground=COLOR_TEXTO_SUAVE)
        area.tag_config("codigo", font=(tema.FUENTE_MONO, max(9, tam - 1)),
                        foreground=COLOR_CODIGO_TEXTO, background=COLOR_CODIGO,
                        lmargin1=10, lmargin2=10, rmargin=10)
        area.tag_config("vineta", font=(tema.FUENTE_UI, tam, "bold"), foreground=COLOR_ACENTO)
        return area

    @staticmethod
    def _columnas_markdown(ancho_px, tam=13):
        """Cuántos caracteres caben en el ancho de la burbuja (para el `tk.Text`).

        El ancho de un `tk.Text` se pide en caracteres, así que se mide el ancho
        real que ocupa una letra con la tipografía de la ventana: así el texto se
        envuelve donde toca y la burbuja queda del ancho justo.
        """
        try:
            medida = tkfont.Font(family=tema.FUENTE_UI, size=tam).measure("n")
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
                paso = rueda.paso_de(evento)
                if paso:
                    marco_scroll._parent_canvas.yview_scroll(paso, "units")
            except Exception:
                pass
            return "break"

        widget.bind("<MouseWheel>", mover)

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
    def _tarjeta(self, parent, icono, titulo, ayuda=None, color_borde=None, ancho_texto=286):
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
        ctk.CTkLabel(cabecera, text=icono, font=(tema.FUENTE_UI, 14),
                     text_color=COLOR_ACENTO).pack(side="left")
        ctk.CTkLabel(cabecera, text=titulo, font=(tema.FUENTE_UI, 13, "bold"),
                     text_color=COLOR_TEXTO).pack(side="left", padx=(8, 0))
        interior = ctk.CTkFrame(marco, fg_color="transparent")
        interior.pack(fill="x", padx=14, pady=(0, 12))
        if ayuda:
            ctk.CTkLabel(interior, text=ayuda, font=(tema.FUENTE_UI, 10),
                         text_color=COLOR_TEXTO_SUAVE, anchor="w", justify="left",
                         wraplength=ancho_texto).pack(anchor="w", pady=(0, 8))
        return interior
