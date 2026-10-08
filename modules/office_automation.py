import hashlib
import io
import os
import re
import zipfile

from PIL import ImageGrab
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Pt

from modules import rutas

class OfficeAutomation:
    # Espacio de nombres de las relaciones OOXML (atributos r:id, r:embed, ...)
    _R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    # Extensión de PowerPoint 2010 con las secciones de la presentación.
    _P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"

    def __init__(self, temp_folder=rutas.TEMP):
        self.temp_folder = temp_folder
        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder)

    def guardar_imagen_portapapeles(self):
        """Captura la imagen actual del portapapeles y la guarda en disco."""
        try:
            imagen = ImageGrab.grabclipboard()
            if imagen is None:
                print("Error: No hay ninguna imagen en el portapapeles.")
                return None
            
            temp_path = os.path.join(self.temp_folder, "temp_clipboard.png")
            imagen.save(temp_path, "PNG")
            return temp_path
        except Exception as e:
            print(f"Error leyendo el portapapeles: {e}")
            return None

    def reemplazar_logos_ppt(self, ruta_ppt, nueva_imagen_path=None):
        """
        Reemplaza todas las imágenes de un PowerPoint por la imagen del portapapeles,
        manteniendo la posición, coordenadas y dimensiones originales.
        """
        # Si no se pasa una imagen específica, la toma del portapapeles
        imagen_temporal = False
        if not nueva_imagen_path:
            nueva_imagen_path = self.guardar_imagen_portapapeles()
            imagen_temporal = True

        if not nueva_imagen_path or not os.path.exists(nueva_imagen_path):
            return "No hay ninguna imagen válida en el portapapeles para realizar el reemplazo."

        if not os.path.exists(ruta_ppt):
            return f"No se encontró el archivo PowerPoint en la ruta: {ruta_ppt}"

        try:
            prs = Presentation(ruta_ppt)
            reemplazos = 0

            for slide in prs.slides:
                # Copia de la lista de formas para permitir eliminación segura en bucle
                for shape in list(slide.shapes):
                    # Verificar si la forma es una imagen
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        # Guardar coordenadas y dimensiones exactas
                        left = shape.left
                        top = shape.top
                        width = shape.width
                        height = shape.height

                        # Eliminar imagen antigua
                        sp = shape._element
                        sp.getparent().remove(sp)

                        # Insertar nueva imagen en las mismas coordenadas
                        slide.shapes.add_picture(nueva_imagen_path, left, top, width, height)
                        reemplazos += 1

            # Guardar el archivo modificado
            ruta_salida = ruta_ppt.replace(".pptx", "_modificado.pptx")
            prs.save(ruta_salida)

            # Si el origen era un .pptm/.potx, evita el aviso de PowerPoint
            # ('la extensión del archivo ha cambiado') al reescribirlo como .pptx.
            if ruta_salida.lower().endswith(".pptx"):
                self._normalizar_pptx(ruta_salida)

            # Limpiar solo si la imagen fue generada internamente (no borrar archivos del usuario)
            if imagen_temporal and os.path.exists(nueva_imagen_path):
                os.remove(nueva_imagen_path)

            return f"Proceso completado. Se reemplazaron {reemplazos} imágenes en el PowerPoint."

        except Exception as e:
            return f"Error durante la automatización de PowerPoint: {str(e)}"

    # ------------------------------------------------------------------ Crear presentación desde Markdown
    def crear_presentacion(self, ruta_md, ruta_plantilla=None, ruta_salida=None,
                           max_slides=None, finales=None, fijos=None, colas=None):
        """Crea una presentación .pptx a partir de un archivo .md usando la plantilla.

        Las primeras 'fijos' diapositivas de la plantilla (por defecto 4) y las
        últimas 'colas' (por defecto 4) se conservan SIEMPRE tal cual, idénticas
        al original. Entre ambas se añade una diapositiva de contenido por cada
        sección del Markdown, con el diseño corporativo de la plantilla (fondo,
        línea y logo) y un contenido limpio de "título + texto": el título va a
        su marcador y las viñetas al marcador de cuerpo, autoajustando la letra
        para que todo quepa, sin superposiciones ni cuadros vacíos de "Haga clic
        para agregar texto".

        'max_slides' (o la directiva "<!-- max_slides: N -->" dentro del .md)
        limita el número de secciones de contenido generadas. Al recortar se
        conservan SIEMPRE las últimas 'finales' secciones del Markdown (por
        defecto las 6 de cierre: forma de pago, condiciones comerciales, garantía,
        cierre, certificaciones y final), de modo que el total es 'max_slides' +
        'finales' (salvo que se solapen).
        """
        if not os.path.exists(ruta_md):
            return f"No encontré el archivo: {ruta_md}"

        contenido = self._parsear_markdown(ruta_md)
        if not contenido or not contenido.get("slides"):
            return "El archivo .md está vacío o no pude leer su contenido."

        titulo = contenido.get("titulo", "Presentación")
        secciones = contenido["slides"]

        # Límite de diapositivas: parámetro explícito > directiva del .md.
        limite = max_slides or contenido.get("max_slides")
        finales = 6 if finales is None else finales
        secciones = self._aplicar_limite(secciones, limite, finales)

        try:
            plantilla = ruta_plantilla if (ruta_plantilla and os.path.exists(ruta_plantilla)) else None
            ok = False
            if plantilla:
                prs = Presentation(plantilla)
                ok = self._construir_desde_plantilla(
                    prs, secciones,
                    fijos=4 if fijos is None else fijos,
                    colas=4 if colas is None else colas)
            else:
                prs = Presentation()

            if not ok:
                # Sin plantilla (o sin diseños válidos): usar los layouts genéricos.
                self._limpiar_diapositivas(prs)
                self._agregar_portada(prs, titulo)
                for seccion in secciones:
                    self._agregar_diapositiva(prs, seccion["titulo"], seccion["puntos"])

            if not ruta_salida:
                ruta_salida = os.path.splitext(ruta_md)[0] + ".pptx"

            prs.save(ruta_salida)

            # Si la plantilla era .pptm/.potx, el paquete conserva su content-type
            # y las macros; al guardarlo como .pptx PowerPoint avisa de que "la
            # extensión del archivo ha cambiado". Lo normalizamos a .pptx real.
            if ruta_salida.lower().endswith(".pptx"):
                self._normalizar_pptx(ruta_salida)

            return f"Presentación creada: {ruta_salida}"
        except Exception as e:
            return f"Error creando la presentación: {e}"

    def _aplicar_limite(self, secciones, limite, finales):
        """Recorta las secciones al número 'limite' conservando SIEMPRE las
        últimas 'finales' (las diapositivas de cierre del documento).

        Si no hay límite válido o el total cabe dentro del límite, devuelve todas
        las secciones sin tocar.
        """
        try:
            limite = int(limite)
        except (TypeError, ValueError):
            limite = 0
        try:
            finales = int(finales)
        except (TypeError, ValueError):
            finales = 0
        if limite <= 0 or len(secciones) <= limite:
            return secciones
        primeras = secciones[:limite]
        if finales > 0:
            indices = {s.get("indice") for s in primeras}
            primeras += [s for s in secciones[-finales:] if s.get("indice") not in indices]
        return primeras

    # Nombres de los diseños (layouts) aptos para viñetas, por orden de preferencia.
    _LAYOUTS_CONTENIDO = (
        "title and body", "título y texto", "titulo y texto",
        "título y objetos", "titulo y objetos", "title and content",
        "contenido con título", "contenido con titulo",
    )

    def _construir_desde_plantilla(self, prs, secciones, fijos=4, colas=4):
        """Genera la presentación conservando fijas las diapositivas de los extremos.

        Las 'fijos' primeras diapositivas de la plantilla (portada, presentación,
        confidencialidad e inicio) y las 'colas' últimas (cierre) se conservan tal
        cual, sin tocarlas. Entre ambas se añade una diapositiva de contenido por
        cada sección del Markdown, replicando el diseño corporativo de la propia
        plantilla (fondo, línea y logo).

        Devuelve True si pudo generar las diapositivas; False para que el
        llamador use el método genérico.
        """
        if not secciones:
            return False
        try:
            originales = list(prs.slides._sldIdLst)
            total = len(originales)
            fijos = self._entero(fijos, 4)
            colas = self._entero(colas, 4)
            fijos = max(0, min(fijos, total))
            colas = max(0, min(colas, total - fijos))
            cola = originales[total - colas:] if colas else []
            sobrantes = originales[fijos:total - colas] if colas else originales[fijos:]

            # Diseño corporativo (fondo, línea y logo) y posición del título tal
            # como aparecen en una diapositiva de contenido de la plantilla.
            decoracion, geometria_titulo = self._modelo_decoracion(prs)

            layout = self._layout_contenido(prs)
            for seccion in secciones:
                self._crear_slide_contenido(
                    prs, layout, seccion.get("titulo", ""),
                    seccion.get("puntos", []), decoracion, geometria_titulo)

            # Se descartan las diapositivas de contenido de la plantilla; las
            # generadas se añaden al final y quedan justo tras la cabecera.
            self._quitar_slides(prs, sobrantes)

            # El bloque de cierre de la plantilla se mueve al final, después del
            # contenido generado (así el orden es cabecera + contenido + cierre).
            if cola:
                sldIdLst = prs.slides._sldIdLst
                for sldId in cola:
                    if sldId.getparent() is sldIdLst:
                        sldIdLst.remove(sldId)
                        sldIdLst.append(sldId)
            return True
        except Exception as e:
            print(f"No pude generar las diapositivas desde la plantilla: {e}")
            return False
    # Fracción superior de la diapositiva que ocupa la decoración (línea y logo).
    _BANDA_DECORACION = 0.15

    @staticmethod
    def _entero(valor, por_defecto):
        """Convierte 'valor' a entero; si no se puede, devuelve 'por_defecto'."""
        try:
            return int(valor)
        except (TypeError, ValueError):
            return por_defecto

    def _modelo_decoracion(self, prs):
        """Localiza la decoración corporativa de las diapositivas de contenido.

        Devuelve (decoracion, geometria_titulo) donde 'decoracion' es una lista
        de diccionarios con la imagen (blob) y la posición de cada elemento del
        diseño (fondo a sangre, línea superior y logo) y 'geometria_titulo' es la
        posición (left, top, width, height) del marcador de título de esa
        diapositiva modelo, o None si no la encuentra.

        El fondo corporativo se identifica como la imagen a sangre que más se
        repite en la plantilla y la decoración como las imágenes de la banda
        superior. Se elige, entre las diapositivas de contenido que lo usan, la
        que tiene menos formas para no arrastrar contenido propio de la sección.
        """
        ancho, alto = prs.slide_width, prs.slide_height
        if not ancho or not alto:
            return [], None
        banda = int(alto * self._BANDA_DECORACION)

        def es_fondo(forma):
            return (forma.shape_type == MSO_SHAPE_TYPE.PICTURE
                    and forma.width and forma.height
                    and forma.width >= ancho * 0.9 and forma.height >= alto * 0.9)

        def con_texto(forma):
            try:
                return bool(forma.has_text_frame and forma.text_frame.text.strip())
            except Exception:
                return False

        def es_placeholder(forma):
            try:
                return bool(forma.is_placeholder)
            except Exception:
                return False

        # Fondo corporativo: la imagen a sangre que más se repite en la plantilla.
        frecuencia = {}
        for slide in prs.slides:
            for forma in slide.shapes:
                if es_fondo(forma):
                    clave = hashlib.md5(forma.image.blob).hexdigest()
                    frecuencia[clave] = frecuencia.get(clave, 0) + 1
        if not frecuencia:
            return [], None
        patron = max(frecuencia, key=lambda clave: frecuencia[clave])

        modelo = None
        for slide in prs.slides:
            fondos = [f for f in slide.shapes if es_fondo(f)]
            if len(fondos) != 1:
                continue
            if hashlib.md5(fondos[0].image.blob).hexdigest() != patron:
                continue
            # Toda la banda superior (salvo texto y marcadores) debe ser imagen;
            # si hay conectores o autoformas no podríamos replicarla fielmente.
            intrusos = [f for f in slide.shapes
                        if not es_placeholder(f) and not con_texto(f)
                        and not es_fondo(f)
                        and f.shape_type != MSO_SHAPE_TYPE.PICTURE
                        and (f.top or 0) + (f.height or 0) <= banda]
            if intrusos:
                continue
            if modelo is None or len(slide.shapes) < len(modelo.shapes):
                modelo = slide
        if modelo is None:
            return [], None

        decoracion = []
        for forma in modelo.shapes:
            if forma.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            if es_placeholder(forma) or con_texto(forma):
                continue
            if not (es_fondo(forma) or (forma.top or 0) + (forma.height or 0) <= banda):
                continue
            decoracion.append({
                "blob": forma.image.blob,
                "left": forma.left or 0,
                "top": forma.top or 0,
                "width": forma.width,
                "height": forma.height,
                "fondo": es_fondo(forma),
            })

        geometria_titulo = None
        try:
            marcador = modelo.shapes.title
        except Exception:
            marcador = None
        if marcador is not None:
            geometria_titulo = (marcador.left, marcador.top,
                                marcador.width, marcador.height)
        return decoracion, geometria_titulo

    def _aplicar_decoracion(self, slide, decoracion):
        """Replica la decoración corporativa (fondo, línea y logo) en una diapositiva.

        El fondo se lleva al fondo del árbol de formas para que quede detrás del
        texto; la línea y el logo quedan por encima del mismo.
        """
        if not decoracion:
            return
        spTree = slide.shapes._spTree
        for parte in decoracion:
            try:
                forma = slide.shapes.add_picture(
                    io.BytesIO(parte["blob"]), parte["left"], parte["top"],
                    parte["width"], parte["height"])
            except Exception as e:
                print(f"No pude copiar la decoración: {e}")
                continue
            if parte.get("fondo") and forma._element.getparent() is spTree:
                spTree.remove(forma._element)
                # Tras <p:nvGrpSpPr> y <p:grpSpPr>: la forma más al fondo.
                spTree.insert(2, forma._element)

    def _layout_contenido(self, prs):
        """Elige el diseño de "título + texto" de la plantilla para el contenido.

        Busca por nombre (los layouts traen marcadores de título y cuerpo, sin
        superposición) y, si no hay coincidencia, usa el layout estándar de
        contenido.
        """
        layouts = list(prs.slide_layouts)
        if not layouts:
            return None
        for nombre in self._LAYOUTS_CONTENIDO:
            for layout in layouts:
                if (layout.name or "").strip().lower() == nombre:
                    return layout
        return layouts[1] if len(layouts) > 1 else layouts[0]

    def _marcadores_contenido(self, slide):
        """Devuelve los marcadores (título, cuerpo) utilizables de una diapositiva.

        Se ignoran los marcadores de fecha, pie y número de diapositiva, que no
        deben llevar texto ni mostrar avisos de "Haga clic...".
        """
        titulo, cuerpo = None, None
        for marcador in slide.placeholders:
            formato = marcador.placeholder_format
            tipo = formato.type
            if tipo in (PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER,
                        PP_PLACEHOLDER.SLIDE_NUMBER):
                continue
            if formato.idx == 0 or tipo in (PP_PLACEHOLDER.TITLE,
                                            PP_PLACEHOLDER.CENTER_TITLE):
                if titulo is None:
                    titulo = marcador
            elif cuerpo is None:
                cuerpo = marcador
        return titulo, cuerpo

    def _crear_slide_contenido(self, prs, layout, titulo, puntos,
                               decoracion=None, geometria_titulo=None):
        """Añade una diapositiva con título y viñetas, sin superponer contenido.

        El título se escribe en el marcador de título y las viñetas en el
        marcador de cuerpo. Se activa el autoajuste de PowerPoint y se fija un
        tamaño de letra calculado para que todas las viñetas quepan.

        'decoracion' replica el diseño corporativo de la plantilla (fondo, línea
        y logo) y 'geometria_titulo' coloca el título donde lo tiene la
        diapositiva modelo, para que no choque con la línea superior.
        """
        if layout is None:
            layout = self._layout_contenido(prs) or prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)

        titulo = (titulo or "").strip()
        puntos = [p.strip() for p in (puntos or []) if p and p.strip()]

        marcador_titulo, marcador_cuerpo = self._marcadores_contenido(slide)
        if marcador_titulo is not None:
            marcador_titulo.text_frame.text = titulo
            if geometria_titulo and all(v is not None for v in geometria_titulo):
                marcador_titulo.left, marcador_titulo.top = geometria_titulo[:2]
                marcador_titulo.width, marcador_titulo.height = geometria_titulo[2:]

        # El diseño corporativo se copia después de los marcadores: el fondo se
        # manda al fondo del árbol, así que no tapa el texto.
        self._aplicar_decoracion(slide, decoracion)

        if marcador_cuerpo is None or not puntos:
            if marcador_cuerpo is not None:
                # Sin viñetas: se quita el marcador para no mostrar el aviso
                # "Haga clic para agregar texto".
                marcador_cuerpo._element.getparent().remove(marcador_cuerpo._element)
            return slide

        tf = marcador_cuerpo.text_frame
        tf.word_wrap = True
        try:
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except Exception:
            pass

        tf.text = puntos[0]
        for punto in puntos[1:]:
            parrafo = tf.add_paragraph()
            parrafo.text = punto
            parrafo.level = 0

        tamano = self._tamano_fuente_cuerpo(puntos)
        for parrafo in tf.paragraphs:
            parrafo.font.size = Pt(tamano)
            for run in parrafo.runs:
                run.font.size = Pt(tamano)
        return slide

    def _tamano_fuente_cuerpo(self, puntos):
        """Tamaño de letra (pt) para que todas las viñetas quepan en el cuerpo.

        Estima la capacidad del marcador de cuerpo (ancho x alto aproximados) y
        devuelve el mayor tamaño de una escala descendente que quepa, para no
        depender de que PowerPoint recalcule el autoajuste al abrir el archivo.
        """
        total = sum(len(p) for p in puntos) + 20 * len(puntos)
        for tamano in (20, 18, 16, 14, 12, 11, 10, 9):
            # Capacidad ≈ área_útil / (ancho_letra * alto_línea); constante
            # calibrada para el marcador de cuerpo de la plantilla UTP.
            if 300000 / (tamano * tamano) >= total:
                return tamano
        return 9

    def _parsear_markdown(self, ruta_md):
        try:
            with open(ruta_md, "r", encoding="utf-8") as f:
                lineas = f.read().splitlines()
        except Exception:
            return None

        titulo = "Presentación"
        slides = []
        actual = None
        max_slides = None
        for linea in lineas:
            linea = linea.rstrip()
            limpia = linea.strip()
            if not limpia:
                continue
            # Ignorar notas/citas ("> ...") y reglas horizontales (---, ***, ___)
            # para que no generen diapositivas "basura".
            if limpia.startswith(">"):
                continue
            if re.fullmatch(r"([-*_])\1{2,}", limpia):
                continue
            # Directiva opcional para limitar el nº de diapositivas generadas.
            directiva = re.fullmatch(
                r"(?:<!--\s*)?max_slides\s*:\s*(\d+)\s*(?:-->)?", limpia, re.IGNORECASE)
            if directiva:
                max_slides = int(directiva.group(1))
                continue
            linea = limpia
            if linea.startswith("# "):
                titulo = linea[2:].strip()
            elif linea.startswith("## "):
                actual = {"titulo": linea[3:].strip(), "puntos": []}
                slides.append(actual)
            elif linea.startswith("### "):
                if actual is None:
                    actual = {"titulo": linea[4:].strip(), "puntos": []}
                    slides.append(actual)
                else:
                    actual["puntos"].append(linea[4:].strip())
            elif linea.startswith("- ") or linea.startswith("* "):
                if actual is None:
                    actual = {"titulo": titulo, "puntos": []}
                    slides.append(actual)
                actual["puntos"].append(linea[2:].strip())
            else:
                if actual is None:
                    actual = {"titulo": titulo, "puntos": []}
                    slides.append(actual)
                actual["puntos"].append(linea.strip())
        # Guardar el índice original de cada sección (su posición en el .md) para
        # poder recortar secciones intermedias sin perder el diseño que le toca.
        for i, seccion in enumerate(slides):
            seccion["indice"] = i
        return {"titulo": titulo, "slides": slides, "max_slides": max_slides}

    def _quitar_slides(self, prs, sldIds):
        """Elimina de la presentación las diapositivas cuyos sldId se pasan."""
        sldIdLst = prs.slides._sldIdLst
        for sldId in list(sldIds):
            rId = sldId.get(self._R_NS + "id")
            try:
                prs.part.drop_rel(rId)
            except Exception:
                pass
            if sldId.getparent() is sldIdLst:
                sldIdLst.remove(sldId)
        self._quitar_secciones(prs)

    def _quitar_secciones(self, prs):
        """Elimina las secciones (p14:sectionLst) de presentation.xml.

        Las secciones agrupan diapositivas por su id; al reemplazar las
        diapositivas originales de la plantilla por las generadas, esas
        referencias quedan colgando y PowerPoint muestra el aviso
        'encontró un problema con el contenido'. Como las diapositivas se
        regeneran por completo, se descartan las secciones del diseño.
        """
        try:
            raiz = prs.slides._sldIdLst.getroottree().getroot()
            secciones = raiz.findall(".//{%s}sectionLst" % self._P14_NS)
        except Exception:
            return
        for seccion in secciones:
            ext = seccion.getparent()  # <p:ext> que envuelve la extensión
            ext.remove(seccion)
            # Limpiamos el <p:ext> y el <p:extLst> si quedaron vacíos.
            if ext.tag.endswith("}ext") and len(ext) == 0:
                extLst = ext.getparent()
                extLst.remove(ext)
                if extLst.tag.endswith("}extLst") and len(extLst) == 0:
                    extLst.getparent().remove(extLst)

    def _limpiar_diapositivas(self, prs):
        sldIdLst = prs.slides._sldIdLst
        for sldId in list(sldIdLst):
            rId = sldId.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            prs.part.drop_rel(rId)
            sldIdLst.remove(sldId)
        self._quitar_secciones(prs)

    def _agregar_portada(self, prs, titulo):
        try:
            layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(layout)
            if slide.shapes.title:
                slide.shapes.title.text = titulo
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == 1:
                    ph.text = ""
        except Exception as e:
            print(f"Error agregando portada: {e}")

    def _agregar_diapositiva(self, prs, titulo, puntos):
        try:
            layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(layout)
            if slide.shapes.title:
                slide.shapes.title.text = titulo
            body = None
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == 1:
                    body = ph
                    break
            if body is not None and puntos:
                tf = body.text_frame
                tf.text = puntos[0]
                for p in puntos[1:]:
                    para = tf.add_paragraph()
                    para.text = p
                    para.level = 0
        except Exception as e:
            print(f"Error agregando diapositiva '{titulo}': {e}")

    # ------------------------------------------------------------------ Normalizar paquete .pptx
    def _normalizar_pptx(self, ruta):
        """Reescribe un .pptx heredado de una plantilla .pptm/.potx para que sea
        un .pptx real: ajusta el content-type del presentation.xml y elimina el
        proyecto VBA (macros) y su relación.

        Sin esto, PowerPoint muestra: 'no puede abrir este archivo porque su
        extensión de archivo ha cambiado'."""
        if not zipfile.is_zipfile(ruta):
            return
        # ¿Hace falta tocar el paquete? Solo si arrastra un content-type de
        # macro-enabled/template/slideshow o un proyecto VBA.
        with zipfile.ZipFile(ruta, "r") as z:
            nombres = z.namelist()
            ct_actual = z.read("[Content_Types].xml").decode("utf-8", "ignore")
        necesita = (
            "macroEnabled.main+xml" in ct_actual
            or "presentationml.template.main+xml" in ct_actual
            or "presentationml.slideshow.main+xml" in ct_actual
            or "vbaProject" in ct_actual
            or any(n.lower() == "ppt/vbaproject.bin" for n in nombres)
        )
        if not necesita:
            return
        reemplazos = {
            "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml":
                "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
            "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml":
                "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml":
                "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        }
        temporal = ruta + ".tmp"
        try:
            with zipfile.ZipFile(ruta, "r") as origen, \
                    zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
                for item in origen.infolist():
                    nombre = item.filename
                    if nombre.lower() == "ppt/vbaproject.bin":
                        continue  # fuera las macros
                    datos = origen.read(nombre)
                    if nombre == "[Content_Types].xml":
                        texto = datos.decode("utf-8")
                        for viejo, nuevo in reemplazos.items():
                            texto = texto.replace(viejo, nuevo)
                        texto = re.sub(
                            r'<Override[^>]*PartName="/ppt/vbaProject\.bin"[^>]*/>',
                            "", texto, flags=re.IGNORECASE)
                        datos = texto.encode("utf-8")
                    elif nombre == "ppt/_rels/presentation.xml.rels":
                        texto = datos.decode("utf-8")
                        texto = re.sub(r'<Relationship[^>]*vbaProject[^>]*/>',
                                       "", texto, flags=re.IGNORECASE)
                        datos = texto.encode("utf-8")
                    item.compress_type = zipfile.ZIP_DEFLATED
                    destino.writestr(item, datos)
            os.replace(temporal, ruta)
        except Exception as e:
            print(f"No pude normalizar el .pptx: {e}")
            if os.path.exists(temporal):
                os.remove(temporal)