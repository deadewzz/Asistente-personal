"""El texto de dentro de un documento, para clasificarlo por su contenido.

El clasificador de SharePoint solo veía los **nombres** de los archivos, así que
un `Documento1.docx` acababa donde dijera su nombre (o en 'Otros'). Aquí se saca
el texto de un Word o un PowerPoint **desde sus bytes**: hace falta porque el
archivo no está en disco, llega en memoria desde SharePoint (ver
`sharepoint.SharePoint.leer_textos`).

Es la misma idea que la extracción de adjuntos de la ventana (`app_gui`), pero
desde memoria y pensada para leer deprisa y barato:

- ``.docx``: párrafos y **tablas** con `python-docx` (en las tablas va a menudo
  lo que clasifica: cliente, tipo, mes).
- ``.pptx``: texto de las formas (incluidas las agrupadas), tablas y notas del
  orador con `python-pptx`.
- ``.doc`` y ``.ppt`` (los formatos antiguos, binarios) no se pueden leer sin
  Office: se dice el motivo y ese archivo se clasifica por su nombre, como antes.

Las librerías se importan dentro de cada función a propósito: si falta alguna, el
motivo se devuelve y la clasificación sigue (no se cae la tarea entera por un
lector que no está instalado).
"""

import io

#: Caracteres de cada documento que se le mandan a la IA. Es lo justo para saber
#: de qué va (título, cliente, primeras líneas) sin inflar el prompt: 75
#: documentos de 900 caracteres son unos 17.000 caracteres en total.
MAX_TEXTO_DOCUMENTO = 900

#: Diapositivas que se recorren de una presentación: el asunto viene en las
#: primeras, y una de 100 diapositivas solo daría texto que luego se recorta.
MAX_DIAPOSITIVAS = 15

#: Lo que se puede abrir por dentro. Los antiguos (``.doc``/``.ppt``) no.
EXTENSIONES_LEGIBLES = (".docx", ".pptx")

#: Formatos antiguos de Office: son binarios y no hay lector en Python.
EXTENSIONES_ANTIGUAS = (".doc", ".ppt")


def extension(nombre):
    """Extensión en minúsculas de un nombre o ruta ('' si no tiene)."""
    nombre = str(nombre or "").rsplit("/", 1)[-1]
    punto = nombre.rfind(".")
    return nombre[punto:].lower() if punto > 0 else ""


def texto_de_documento(datos, nombre, maximo=MAX_TEXTO_DOCUMENTO):
    """Devuelve ``(texto, motivo)`` del documento que llega en ``datos``.

    ``texto`` es un extracto **de una línea** (los saltos se vuelven ' / ', que
    ocupa menos y se lee igual de bien en el prompt) recortado a ``maximo``
    caracteres. ``motivo`` explica por qué no hay texto: formato que no sé leer,
    librería que falta, documento sin texto (solo imágenes)... Quien llama decide
    qué hacer con ello; la clasificación sigue funcionando por el nombre.
    """
    tipo = extension(nombre)
    if tipo in EXTENSIONES_ANTIGUAS:
        return "", f"formato antiguo ({tipo}): no sé leerlo por dentro"
    if tipo not in EXTENSIONES_LEGIBLES:
        cual = f"'{tipo}'" if tipo else "este formato"
        return "", f"no sé leer por dentro {cual}"
    if not datos:
        return "", "el archivo llegó vacío"
    if tipo == ".docx":
        return _de_word(datos, maximo)
    return _de_powerpoint(datos, maximo)


def _de_word(datos, maximo):
    """Párrafos y tablas de un ``.docx`` (necesita `python-docx`)."""
    try:
        import docx
    except Exception:
        return "", "no tengo 'python-docx' instalado para leerlo por dentro"
    try:
        documento = docx.Document(io.BytesIO(datos))
    except Exception as e:
        return "", f"no pude abrirlo ({e})"
    partes = [parrafo.text for parrafo in documento.paragraphs]
    for tabla in getattr(documento, "tables", []) or []:
        for fila in tabla.rows:
            celdas = [celda.text.strip() for celda in fila.cells]
            if any(celdas):
                partes.append(" | ".join(celdas))
    texto = _aplanar(partes, maximo)
    return (texto, "" if texto else "no tiene texto (¿solo imágenes?)")


def _de_powerpoint(datos, maximo):
    """Textos, tablas y notas de un ``.pptx`` (necesita `python-pptx`)."""
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except Exception:
        return "", "no tengo 'python-pptx' instalado para leerlo por dentro"
    try:
        presentacion = Presentation(io.BytesIO(datos))
    except Exception as e:
        return "", f"no pude abrirla ({e})"

    partes = []

    def recorrer(formas):
        """Saca el texto de las formas, entrando en las que van agrupadas."""
        for forma in formas:
            try:
                if forma.shape_type == MSO_SHAPE_TYPE.GROUP:
                    recorrer(forma.shapes)
                    continue
                if forma.has_table:
                    for fila in forma.table.rows:
                        celdas = [celda.text.strip() for celda in fila.cells]
                        if any(celdas):
                            partes.append(" | ".join(celdas))
                    continue
                if forma.has_text_frame and forma.text_frame.text.strip():
                    partes.append(forma.text_frame.text)
            except Exception:
                continue    # una forma rara no tira la diapositiva entera

    for numero, diapositiva in enumerate(presentacion.slides, start=1):
        if numero > MAX_DIAPOSITIVAS:
            break
        recorrer(diapositiva.shapes)
        try:
            notas = diapositiva.notes_slide.notes_text_frame.text.strip()
        except Exception:
            notas = ""
        if notas:
            partes.append(notas)
    texto = _aplanar(partes, maximo)
    return (texto, "" if texto else "no tiene texto (¿solo imágenes?)")


def _aplanar(partes, maximo):
    """Junta los trozos en una línea y la corta por un espacio (no a media palabra)."""
    texto = " ".join(" ".join(str(parte).split()) for parte in partes
                     if str(parte).strip())
    if len(texto) <= maximo:
        return texto
    corte = texto[:maximo]
    if " " in corte:
        corte = corte[:corte.rfind(" ")]
    return corte.rstrip() + " […]"
