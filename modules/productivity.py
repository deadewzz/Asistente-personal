import os
import json
import time
import threading
import urllib.request
import urllib.parse
from datetime import datetime

import re

import pyperclip

from modules import rutas


class ProductivityTools:
    """Herramientas de productividad: pomodoro, notas, documentos de archivo,
    portapapeles, clima, briefing, búsqueda de archivos, dictado continuo y
    perfiles de entorno."""

    # Formatos que puede generar la acción CREAR_DOCUMENTO
    EXTENSIONES_DOCUMENTO = (".txt", ".md", ".csv", ".docx", ".pdf")

    def __init__(self, config_path=rutas.CONFIG_USUARIO, notas_dir=rutas.NOTAS):
        self.config_path = config_path
        self.notas_dir = notas_dir
        os.makedirs(self.notas_dir, exist_ok=True)

        self.pomodoro_activo = False
        self._pomodoro_hilo = None
        self.dictado_activo = False
        self.on_alerta = None

    # ------------------------------------------------------------------ Pomodoro
    def iniciar_pomodoro(self, minutos=25):
        if self.pomodoro_activo:
            return "Ya hay un pomodoro en curso."
        minutos = max(1, int(minutos))
        self.pomodoro_activo = True
        self._pomodoro_hilo = threading.Thread(target=self._pomodoro_bucle, args=(minutos,), daemon=True)
        self._pomodoro_hilo.start()
        return f"Pomodoro de {minutos} minutos iniciado. Concéntrate."

    def _pomodoro_bucle(self, minutos):
        time.sleep(minutos * 60)
        if not self.pomodoro_activo:
            return
        self._alerta("Se acabó el tiempo de enfoque. Toma una pausa activa de cinco minutos.")
        time.sleep(5 * 60)
        if self.pomodoro_activo:
            self._alerta("La pausa terminó. Puedes iniciar otro pomodoro cuando quieras.")

    def detener_pomodoro(self):
        self.pomodoro_activo = False
        return "Pomodoro detenido."

    def _alerta(self, texto):
        if self.on_alerta:
            try:
                self.on_alerta(texto)
            except Exception as e:
                print(f"Error al emitir alerta: {e}")

    # ------------------------------------------------------------------ Notas (bloc diario con fecha y hora)
    def _notas_hoy(self):
        fecha = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.notas_dir, f"notas_{fecha}.md")

    def agregar_nota(self, texto):
        texto = texto.strip()
        if not texto:
            return "No había texto para anotar."
        hora = datetime.now().strftime("%H:%M")
        with open(self._notas_hoy(), "a", encoding="utf-8") as f:
            f.write(f"- [{hora}] {texto}\n")
        return None

    def leer_notas(self):
        ruta = self._notas_hoy()
        if not os.path.exists(ruta):
            return "Todavía no tienes notas de hoy."
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        return contenido or "Todavía no tienes notas de hoy."

    def borrar_notas(self):
        try:
            ruta = self._notas_hoy()
            if os.path.exists(ruta):
                os.remove(ruta)
            return "Notas de hoy borradas."
        except Exception as e:
            return f"No pude borrar las notas: {e}"

    # ------------------------------------------------------------------ Documentos de archivo (.txt/.md/.csv/.docx/.pdf)
    @staticmethod
    def _sanear_nombre(nombre):
        """Limpia un nombre de archivo o carpeta, evitando rutas o caracteres inválidos."""
        limpio = re.sub(r'[<>:"/\\|?*]', "", (nombre or "").strip())
        limpio = limpio.strip().strip(".")
        return limpio or "documento"

    def crear_documento(self, nombre, contenido):
        """Crea un documento de archivo dentro de la carpeta de documentos de Jarvis.

        'nombre' admite una subcarpeta relativa (p. ej. 'recetas/pizza.txt'); la
        extensión decide el formato: .txt/.md/.csv (texto plano), .docx o .pdf.
        Nunca escribe fuera de la carpeta de documentos de Jarvis.
        Devuelve un mensaje con la ruta creada o el motivo del fallo.
        """
        contenido = (contenido or "").strip()
        if not contenido:
            return "No había contenido para el documento."

        base = os.path.abspath(rutas.DOCUMENTOS)
        partes = [self._sanear_nombre(p)
                  for p in re.split(r"[\\/]+", (nombre or "").strip()) if p.strip()]
        if not partes:
            partes = [f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"]
        archivo = partes[-1]
        ext = os.path.splitext(archivo)[1].lower()
        if ext not in self.EXTENSIONES_DOCUMENTO:
            archivo += ".txt"
            ext = ".txt"

        destino_dir = os.path.abspath(os.path.join(base, *partes[:-1]))
        if destino_dir != base and not destino_dir.startswith(base + os.sep):
            return "No puedo crear documentos fuera de la carpeta de documentos de Jarvis."
        ruta = os.path.join(destino_dir, archivo)

        try:
            os.makedirs(destino_dir, exist_ok=True)
            if ext in (".txt", ".md", ".csv"):
                with open(ruta, "w", encoding="utf-8", newline="") as f:
                    f.write(contenido + "\n")
            elif ext == ".docx":
                self._escribir_docx(ruta, contenido)
            else:  # .pdf
                self._escribir_pdf(ruta, contenido)
        except Exception as e:
            return f"No pude crear el documento: {e}"
        return f"Documento creado en: {ruta}"

    # --- Estilos y patrones para convertir Markdown en un .docx con estructura ---
    COLOR_ACENTO = "1F6F4A"   # verde Jarvis: títulos y cabecera de las tablas
    COLOR_CELDA = "F2F4F3"    # gris muy claro para los fondos (bloques de código)
    # Títulos Markdown: #, ##, ### ... (con o sin espacio, pero no una línea de #)
    _RE_TITULO = re.compile(r"^(#{1,6})[ \t]*([^#\s].*?)[ \t]*$")
    _RE_VINETA = re.compile(r"^[-*+]\s+(.*)$")           # viñetas - * +
    _RE_NUMERO = re.compile(r"^\d+[.)]\s+(.*)$")         # listas 1. / 1)
    _RE_REGLA = re.compile(r"^([-*_])(?:\s*\1){2,}$")    # regla --- *** ___
    # Fila de asignación: "Nombre - Tarea" (guion, raya, flecha o tabulador)
    _RE_ASIGNACION = re.compile(r"^(?P<izq>[^-*+>\s].*?)\s+(?:[-–—»→]|->)\s+(?P<der>.+)$")
    # Formato inline: **negrita**, __negrita__, `código`, *cursiva*, _cursiva_
    _RE_INLINE = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|\*[^*\n]+?\*|_[^_\n]+?_)")
    # Palabras que indican que la primera fila de una tabla es su cabecera.
    _PALABRAS_CABECERA = {
        "nombre", "nombres", "persona", "personas", "responsable", "responsables",
        "encargado", "encargada", "asignado", "asignada", "usuario", "cliente",
        "tarea", "tareas", "actividad", "actividades", "accion", "descripcion",
        "detalle", "detalles", "estado", "fecha", "prioridad", "comentario",
        "comentarios", "observacion", "area", "cargo", "proyecto", "item", "punto",
        "puntos", "rol", "equipo", "sprint", "horas",
    }

    def _escribir_docx(self, ruta, contenido):
        """Genera un .docx con estructura a partir de un texto en Markdown.

        En lugar de volcar cada línea tal cual, interpreta el Markdown para que
        el Word quede ordenado: los encabezados (#, ##, ###) se vuelven títulos,
        las viñetas (- * +) y las listas numeradas (1.) en listas reales, las
        citas (>) y los bloques de código (```) con su estilo, y tanto las tablas
        con '|' como las filas del estilo 'Nombre - Tarea' se convierten en una
        tabla con cabecera resaltada.
        """
        from docx import Document

        doc = Document()
        self._configurar_estilos_docx(doc)
        titulo = None
        for tipo, datos in self._bloques_desde_markdown(contenido):
            if tipo == "titulo" and titulo is None:
                titulo = self._texto_plano(datos[1])
            self._renderizar_bloque_docx(doc, tipo, datos)
        if titulo:
            try:
                doc.core_properties.title = titulo
            except Exception:
                pass
        doc.save(ruta)

    @staticmethod
    def _configurar_estilos_docx(doc):
        """Ajusta la tipografía y los colores base para que el documento sea legible."""
        from docx.shared import Pt, RGBColor

        acento = RGBColor(0x1F, 0x6F, 0x4A)
        try:
            normal = doc.styles["Normal"]
            normal.font.name = "Calibri"
            normal.font.size = Pt(11)
            normal.font.color.rgb = RGBColor(0x28, 0x2A, 0x29)
            normal.paragraph_format.space_after = Pt(6)
            normal.paragraph_format.line_spacing = 1.15
        except Exception:
            pass
        for nombre, tam, antes in (
            ("Heading 1", 21, 0), ("Heading 2", 16, 12),
            ("Heading 3", 13.5, 10), ("Heading 4", 12, 8),
        ):
            try:
                estilo = doc.styles[nombre]
                estilo.font.name = "Calibri Light"
                estilo.font.size = Pt(tam)
                estilo.font.bold = True
                estilo.font.color.rgb = acento
                estilo.paragraph_format.space_before = Pt(antes)
                estilo.paragraph_format.space_after = Pt(6)
                estilo.paragraph_format.keep_with_next = True
            except Exception:
                continue

    # --- Clasificación del Markdown en bloques con significado ---
    def _bloques_desde_markdown(self, contenido):
        """Convierte el Markdown en una lista de bloques (tipo, datos).

        Cada bloque es una unidad lista para renderizar: 'titulo', 'vinetas',
        'numeros', 'cita', 'codigo', 'tabla', 'regla' o 'parrafo'. Así el .docx
        conserva la jerarquía del Markdown en lugar de copiarlo línea a línea.
        """
        lineas = (contenido or "").splitlines()
        bloques = []
        i, total = 0, len(lineas)
        while i < total:
            texto = lineas[i].strip()
            if not texto:
                i += 1
                continue
            # Bloque de código cercado con ```
            if texto.startswith("```"):
                i += 1
                codigo = []
                while i < total and not lineas[i].strip().startswith("```"):
                    codigo.append(lineas[i].rstrip())
                    i += 1
                bloques.append(("codigo", codigo or [""]))
                i += 1
                continue
            # Regla horizontal (---, ***, ___)
            if self._RE_REGLA.match(texto):
                bloques.append(("regla", None))
                i += 1
                continue
            # Título (#, ##, ### ...)
            titulo = self._RE_TITULO.match(texto)
            if titulo:
                bloques.append(("titulo", (len(titulo.group(1)), titulo.group(2).strip())))
                i += 1
                continue
            # Cita (> ...) uniendo las líneas consecutivas
            if texto.startswith(">"):
                citas = []
                while i < total and lineas[i].strip().startswith(">"):
                    citas.append(lineas[i].strip().lstrip(">").strip())
                    i += 1
                bloques.append(("cita", " ".join(c for c in citas if c)))
                continue
            # Tabla Markdown con tuberías (| a | b |)
            if self._es_fila_tabla_md(texto):
                filas = []
                while i < total and self._es_fila_tabla_md(lineas[i].strip()):
                    filas.append(lineas[i].strip())
                    i += 1
                bloques.append(self._tabla_desde_pipes(filas))
                continue
            # Listas con viñetas (- * +)
            if self._RE_VINETA.match(texto):
                items = []
                while i < total and self._RE_VINETA.match(lineas[i].strip()):
                    items.append(self._RE_VINETA.match(lineas[i].strip()).group(1).strip())
                    i += 1
                bloques.append(self._lista_como_bloque(items))
                continue
            # Listas numeradas (1. 2. ...)
            if self._RE_NUMERO.match(texto):
                items = []
                while i < total and self._RE_NUMERO.match(lineas[i].strip()):
                    items.append(self._RE_NUMERO.match(lineas[i].strip()).group(1).strip())
                    i += 1
                bloques.append(self._lista_como_bloque(items, "numeros"))
                continue
            # Filas "Nombre - Tarea": se agrupan y se vuelven una tabla
            if self._RE_ASIGNACION.match(texto):
                filas = []
                while i < total and self._RE_ASIGNACION.match(lineas[i].strip()):
                    coincidencia = self._RE_ASIGNACION.match(lineas[i].strip())
                    filas.append((coincidencia.group("izq").strip(),
                                  coincidencia.group("der").strip()))
                    i += 1
                bloques.append(self._bloque_asignacion(filas))
                continue
            # Párrafo: líneas seguidas hasta el siguiente bloque
            parrafo = []
            while i < total:
                actual = lineas[i].strip()
                if not actual or self._inicia_bloque(actual):
                    break
                parrafo.append(actual)
                i += 1
            if parrafo:
                bloques.append(("parrafo", " ".join(parrafo)))
        return bloques

    def _inicia_bloque(self, texto):
        """True si 'texto' abre un bloque distinto de un párrafo normal."""
        return bool(
            texto.startswith("```")
            or self._RE_REGLA.match(texto)
            or self._RE_TITULO.match(texto)
            or texto.startswith(">")
            or self._es_fila_tabla_md(texto)
            or self._RE_VINETA.match(texto)
            or self._RE_NUMERO.match(texto)
            or self._RE_ASIGNACION.match(texto)
        )

    @staticmethod
    def _es_fila_tabla_md(texto):
        """True si la línea parece una fila de tabla Markdown (| a | b |)."""
        return texto.count("|") >= 2 and (texto.startswith("|") or texto.endswith("|"))

    @staticmethod
    def _tabla_desde_pipes(filas):
        """Convierte las filas '|...|' en un bloque de tabla."""
        def celdas(fila):
            return [c.strip() for c in fila.strip().strip("|").split("|")]

        def es_separadora(columnas):
            return bool(columnas) and all(
                re.fullmatch(r":?-{2,}:?", columna or "") for columna in columnas)

        matriz = [celdas(fila) for fila in filas]
        cabeceras, datos = None, matriz
        if len(matriz) >= 2 and es_separadora(matriz[1]):
            cabeceras, datos = matriz[0], matriz[2:]
        else:
            datos = [fila for fila in matriz if not es_separadora(fila)]
        if not datos:
            return ("parrafo", " | ".join(filas))
        return ("tabla", (cabeceras, datos))

    def _lista_como_bloque(self, items, tipo="vinetas"):
        """Convierte una lista en tabla si todos sus ítems son 'Nombre - Tarea'."""
        pares = [self._RE_ASIGNACION.match(item) for item in items]
        if pares and all(pares):
            filas = [(p.group("izq").strip(), p.group("der").strip()) for p in pares]
            bloque = self._bloque_asignacion(filas)
            if bloque[0] == "tabla":
                return bloque
        return (tipo, items)

    def _bloque_asignacion(self, filas):
        """Decide si las filas 'Nombre - Tarea' forman una tabla o son texto normal."""
        if self._forman_tabla_asignacion(filas):
            return ("tabla", self._cabeceras_asignacion(filas))
        return ("parrafo", " ".join("%s - %s" % (izq, der) for izq, der in filas))

    def _forman_tabla_asignacion(self, filas):
        """Con 2+ filas siempre es tabla; con una sola, solo si parece un nombre."""
        if not filas:
            return False
        return len(filas) >= 2 or self._parece_nombre(filas[0][0])

    @staticmethod
    def _parece_nombre(texto):
        """True si 'texto' parece un nombre propio corto (1-3 palabras)."""
        palabras = (texto or "").split()
        if not 1 <= len(palabras) <= 3:
            return False
        if texto.rstrip().endswith((".", ",", ";", ":", "?", "!")):
            return False
        return all(palabra[:1].isupper() or palabra.isupper() for palabra in palabras)

    def _cabeceras_asignacion(self, filas):
        """Separa (cabeceras, datos); usa la 1ª fila como cabecera si lo parece."""
        cabeceras = None
        datos = [list(fila) for fila in filas]
        if filas:
            izq, der = filas[0]
            if (self._normalizar_palabra(izq) in self._PALABRAS_CABECERA
                    and self._normalizar_palabra(der) in self._PALABRAS_CABECERA):
                cabeceras, datos = [izq, der], [list(fila) for fila in filas[1:]]
        return cabeceras or ["Persona", "Tarea"], datos

    @staticmethod
    def _normalizar_palabra(texto):
        """Normaliza una palabra (minúsculas y sin acentos) para compararla."""
        base = (texto or "").strip().lower()
        for acento, plano in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"),
                              ("ú", "u"), ("ü", "u"), ("ñ", "n")):
            base = base.replace(acento, plano)
        return re.sub(r"[^a-z]", "", base)

    # --- Volcado de los bloques ya clasificados al documento Word ---
    def _renderizar_bloque_docx(self, doc, tipo, datos):
        """Escribe en el documento un bloque previamente clasificado."""
        if tipo == "titulo":
            self._agregar_titulo_docx(doc, datos[0], datos[1])
        elif tipo == "vinetas":
            for item in datos:
                self._agregar_parrafo_docx(doc, item, "List Bullet")
        elif tipo == "numeros":
            for item in datos:
                self._agregar_parrafo_docx(doc, item, "List Number")
        elif tipo == "cita":
            self._agregar_cita_docx(doc, datos)
        elif tipo == "codigo":
            self._agregar_codigo_docx(doc, datos)
        elif tipo == "tabla":
            self._agregar_tabla_docx(doc, datos[0], datos[1])
        elif tipo == "regla":
            self._agregar_regla_docx(doc)
        elif tipo == "parrafo":
            self._agregar_parrafo_docx(doc, datos)

    def _agregar_titulo_docx(self, doc, nivel, texto):
        """Agrega un título con el estilo Heading correspondiente."""
        nivel = max(1, min(6, int(nivel)))
        try:
            parrafo = doc.add_paragraph(style="Heading %d" % nivel)
        except Exception:
            parrafo = doc.add_paragraph()
        self._agregar_runs(parrafo, texto)
        return parrafo

    def _agregar_parrafo_docx(self, doc, texto, estilo=None):
        """Agrega un párrafo (con estilo opcional) y su formato inline."""
        try:
            parrafo = doc.add_paragraph(style=estilo) if estilo else doc.add_paragraph()
        except Exception:
            parrafo = doc.add_paragraph()
        self._agregar_runs(parrafo, texto)
        return parrafo

    def _agregar_cita_docx(self, doc, texto):
        """Agrega una cita con el estilo de cita del tema."""
        from docx.shared import Pt

        try:
            parrafo = doc.add_paragraph(style="Intense Quote")
        except Exception:
            parrafo = doc.add_paragraph()
            parrafo.paragraph_format.left_indent = Pt(18)
        self._agregar_runs(parrafo, texto)
        return parrafo

    def _agregar_codigo_docx(self, doc, lineas):
        """Agrega un bloque de código en monoespaciada con fondo gris."""
        from docx.shared import Pt

        for i, linea in enumerate(lineas or [""]):
            parrafo = doc.add_paragraph()
            formato = parrafo.paragraph_format
            formato.space_before = Pt(6 if i == 0 else 0)
            formato.space_after = Pt(6 if i == len(lineas) - 1 else 0)
            formato.left_indent = Pt(10)
            formato.line_spacing = 1.0
            run = parrafo.add_run(linea if linea.strip() else " ")
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            self._sombrear_parrafo(parrafo, self.COLOR_CELDA)

    def _agregar_regla_docx(self, doc):
        """Dibuja una línea horizontal con el borde inferior de un párrafo."""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt

        parrafo = doc.add_paragraph()
        parrafo.paragraph_format.space_before = Pt(4)
        parrafo.paragraph_format.space_after = Pt(8)
        bordes = OxmlElement("w:pBdr")
        inferior = OxmlElement("w:bottom")
        inferior.set(qn("w:val"), "single")
        inferior.set(qn("w:sz"), "6")
        inferior.set(qn("w:space"), "1")
        inferior.set(qn("w:color"), self.COLOR_ACENTO)
        bordes.append(inferior)
        parrafo._p.get_or_add_pPr().append(bordes)
        return parrafo

    def _agregar_tabla_docx(self, doc, cabeceras, filas):
        """Inserta una tabla con la cabecera resaltada y celdas legibles."""
        from docx.enum.table import WD_TABLE_ALIGNMENT

        filas = [list(fila) for fila in (filas or [])]
        cabeceras = list(cabeceras) if cabeceras else None
        ncols = max([len(cabeceras) if cabeceras else 0] + [len(f) for f in filas] or [0])
        total = (1 if cabeceras else 0) + len(filas)
        if ncols == 0 or total == 0:
            return None
        tabla = doc.add_table(rows=total, cols=ncols)
        tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
        for estilo in ("Light Grid Accent 1", "Light List Accent 1", "Table Grid"):
            try:
                tabla.style = estilo
                break
            except Exception:
                continue
        indice = 0
        if cabeceras:
            self._rellenar_fila_tabla(tabla.rows[indice], cabeceras, ncols, True)
            indice += 1
        for fila in filas:
            self._rellenar_fila_tabla(tabla.rows[indice], fila, ncols, False)
            indice += 1
        return tabla

    def _rellenar_fila_tabla(self, fila_tabla, valores, ncols, encabezado):
        """Rellena una fila de la tabla respetando el formato inline."""
        from docx.shared import Pt, RGBColor

        for columna in range(ncols):
            celda = fila_tabla.cells[columna]
            parrafo = celda.paragraphs[0]
            parrafo.paragraph_format.space_before = Pt(2)
            parrafo.paragraph_format.space_after = Pt(2)
            valor = valores[columna] if columna < len(valores) else ""
            self._agregar_runs(parrafo, str(valor))
            if encabezado:
                for run in parrafo.runs:
                    run.bold = True
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                self._sombrear_celda(celda, self.COLOR_ACENTO)
            elif columna == 0 and ncols == 2:
                for run in parrafo.runs:
                    run.bold = True

    def _agregar_runs(self, parrafo, texto):
        """Añade el texto a un párrafo aplicando el formato inline del Markdown."""
        from docx.shared import Pt, RGBColor

        for parte in self._RE_INLINE.split(texto or ""):
            if not parte:
                continue
            if ((parte.startswith("**") and parte.endswith("**"))
                    or (parte.startswith("__") and parte.endswith("__"))):
                parrafo.add_run(parte[2:-2]).bold = True
            elif parte.startswith("`") and parte.endswith("`"):
                run = parrafo.add_run(parte[1:-1])
                run.font.name = "Consolas"
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0xB0, 0x39, 0x2E)
            elif ((parte.startswith("*") and parte.endswith("*"))
                  or (parte.startswith("_") and parte.endswith("_"))):
                parrafo.add_run(parte[1:-1]).italic = True
            else:
                parrafo.add_run(parte)

    def _texto_plano(self, texto):
        """Quita el formato inline del Markdown (para títulos y metadatos)."""
        return self._RE_INLINE.sub(lambda m: m.group(0).strip("*_`"), texto or "").strip()

    @staticmethod
    def _sombrear_parrafo(parrafo, relleno):
        """Aplica un color de fondo a un párrafo."""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        sombra = OxmlElement("w:shd")
        sombra.set(qn("w:val"), "clear")
        sombra.set(qn("w:color"), "auto")
        sombra.set(qn("w:fill"), relleno)
        parrafo._p.get_or_add_pPr().append(sombra)

    @staticmethod
    def _sombrear_celda(celda, relleno):
        """Aplica un color de fondo a una celda de tabla."""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        sombra = OxmlElement("w:shd")
        sombra.set(qn("w:val"), "clear")
        sombra.set(qn("w:color"), "auto")
        sombra.set(qn("w:fill"), relleno)
        celda._tc.get_or_add_tcPr().append(sombra)

    @staticmethod
    def _escribir_pdf(ruta, contenido):
        from fpdf import FPDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for linea in contenido.splitlines():
            texto = linea.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 6, txt=texto if texto.strip() else " ")
        pdf.output(ruta)

    # ------------------------------------------------------------------ Reglas permanentes (memoria del asistente)
    def _reglas_path(self):
        """Ruta del archivo donde se guardan las reglas permanentes del usuario."""
        return rutas.REGLAS

    def agregar_regla(self, texto):
        """Añade una regla permanente (una por línea) a reglas.md."""
        texto = (texto or "").strip()
        if not texto:
            return "No había texto para la regla."
        try:
            os.makedirs(os.path.dirname(self._reglas_path()), exist_ok=True)
            with open(self._reglas_path(), "a", encoding="utf-8") as f:
                f.write(f"- {texto}\n")
            return f"Regla guardada: {texto}"
        except Exception as e:
            return f"No pude guardar la regla: {e}"

    def leer_reglas(self):
        """Devuelve el contenido de reglas.md (vacío si no existe)."""
        ruta = self._reglas_path()
        if not os.path.exists(ruta):
            return ""
        with open(ruta, "r", encoding="utf-8") as f:
            return f.read().strip()

    def guardar_reglas(self, contenido):
        """Sobrescribe reglas.md con el contenido indicado (editor de la interfaz)."""
        try:
            os.makedirs(os.path.dirname(self._reglas_path()), exist_ok=True)
            contenido = (contenido or "").strip()
            with open(self._reglas_path(), "w", encoding="utf-8") as f:
                if contenido:
                    f.write(contenido + "\n")
            return True
        except Exception as e:
            print(f"No se pudieron guardar las reglas: {e}")
            return False

    def borrar_reglas(self):
        try:
            ruta = self._reglas_path()
            if os.path.exists(ruta):
                os.remove(ruta)
            return "Reglas permanentes borradas."
        except Exception as e:
            return f"No pude borrar las reglas: {e}"

    # ------------------------------------------------------------------ Portapapeles y dictado
    def leer_portapapeles(self):
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def dictar(self, texto):
        try:
            pyperclip.copy(texto)
            import pyautogui
            pyautogui.hotkey("ctrl", "v")
        except Exception as e:
            print(f"Error al dictar: {e}")

    # ------------------------------------------------------------------ Clima (Open-Meteo, sin API key)
    def obtener_clima(self, ciudad=None):
        ciudad = (ciudad or self._ciudad_config() or "Bogotá").strip()
        try:
            lat, lon, nombre = self._geocodificar(ciudad)
        except Exception as e:
            return f"No pude ubicar la ciudad '{ciudad}': {e}"
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m&timezone=auto")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            cur = data.get("current", {})
            temp = cur.get("temperature_2m")
            aparente = cur.get("apparent_temperature")
            viento = cur.get("wind_speed_10m")
            desc = self._descripcion_clima(cur.get("weather_code"))
            return (f"En {nombre} ahora mismo está {desc}, {temp} grados "
                    f"(sensación de {aparente}), viento de {viento} kilómetros por hora.")
        except Exception as e:
            return f"No pude obtener el clima: {e}"

    def _ciudad_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return (json.load(f).get("ciudad") or "").strip()
        except Exception:
            pass
        return ""

    def _geocodificar(self, ciudad):
        url = ("https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&format=json&name="
               + urllib.parse.quote(ciudad))
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        res = data.get("results")
        if not res:
            raise ValueError("ciudad no encontrada")
        r0 = res[0]
        return r0["latitude"], r0["longitude"], r0.get("name", ciudad)

    def _descripcion_clima(self, codigo):
        if codigo is None:
            return "cielo despejado"
        if codigo == 0:
            return "despejado"
        if 1 <= codigo <= 3:
            return "parcialmente nublado"
        if codigo in (45, 48):
            return "con niebla"
        if 51 <= codigo <= 57:
            return "con llovizna"
        if 61 <= codigo <= 67:
            return "con lluvia"
        if 71 <= codigo <= 77:
            return "con nieve"
        if 80 <= codigo <= 82:
            return "con chubascos"
        if 95 <= codigo <= 99:
            return "con tormenta"
        return "con condiciones variables"

    # ------------------------------------------------------------------ Briefing
    def generar_briefing(self):
        ahora = datetime.now()
        fecha = ahora.strftime("%A %d de %B de %Y")
        hora = ahora.strftime("%H:%M")
        clima = self.obtener_clima()
        tareas = self._tareas_principales()
        return f"Buenos días. Hoy es {fecha}, son las {hora}. {clima} {tareas}"

    def _tareas_principales(self):
        ruta = self._notas_hoy()
        if not os.path.exists(ruta):
            return "No tienes tareas registradas todavía."
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                lineas = []
                for l in f:
                    l = l.strip()
                    if not l:
                        continue
                    if l.startswith("- "):
                        l = l[2:]
                    if l.startswith("[") and "] " in l:
                        l = l.split("] ", 1)[1]
                    lineas.append(l.strip())
                    if len(lineas) >= 3:
                        break
        except Exception:
            return "No pude leer tus tareas."
        if not lineas:
            return "No tienes tareas registradas todavía."
        return "Tus 3 tareas principales son: " + "; ".join(lineas) + "."

    # ------------------------------------------------------------------ Búsqueda de archivos
    def buscar_archivos(self, nombre, max_resultados=8):
        nombre = nombre.lower()
        raiz = os.path.expanduser("~")
        resultados = []
        excluir = {"AppData", "node_modules", ".git", "venv", "__pycache__", "Library", ".cache"}
        for base, dirs, files in os.walk(raiz):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in excluir]
            for f in files:
                if nombre in f.lower():
                    resultados.append(os.path.join(base, f))
                    if len(resultados) >= max_resultados:
                        return resultados
        return resultados

    # ------------------------------------------------------------------ Perfiles de entorno
    def activar_perfil(self, perfil):
        import webbrowser
        import subprocess
        perfil = perfil.lower()
        if perfil in ("desarrollo", "dev"):
            subprocess.Popen("code", shell=True)
            return "Modo desarrollo activado: VS Code abierto."
        elif perfil in ("oficina", "reunion", "reunión", "meeting"):
            for url in ["https://meet.google.com", "https://teams.microsoft.com"]:
                webbrowser.open(url)
            return "Modo oficina activado: Google Meet y Teams abiertos."
        elif perfil in ("cierre", "fin", "cierre de jornada"):
            return "Modo cierre: guarda tus cambios y revisa las notas del día."
        return f"No reconozco el perfil '{perfil}'."

