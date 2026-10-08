"""Motor OCR para leer el texto contenido en imágenes (capturas, fotos, escaneos).

Motores soportados, en orden de preferencia:
  1. Tesseract (vía pytesseract). Es el más preciso para español. El binario se
     localiza automáticamente en las rutas habituales de Windows o en la
     variable de entorno TESSERACT_CMD. Si existe la carpeta local de idiomas
     "assets/tools/tessdata" (con spa/eng) se usa esa para no depender de la
     instalación del sistema.
  2. RapidOCR (onnxruntime). Alternativa 100% Python (sin binarios externos)
     que se usa automáticamente si Tesseract no está disponible.

Todas las funciones son tolerantes a fallos: si no hay ningún motor OCR
disponible devuelven cadena vacía en lugar de propagar excepciones.
"""

import os
import shutil
import sys

# Carpeta del proyecto (o del ejecutable empaquetado) donde viven los recursos.
def _raiz_aplicacion():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


TESSDATA_LOCAL = os.path.join(_raiz_aplicacion(), "assets", "tools", "tessdata")

# Rutas habituales del binario de Tesseract en Windows.
_RUTAS_TESSERACT = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
]

_ruta_tesseract_cache = None       # None = aún sin calcular, "" = no encontrado
_disponible_cache = None
_motor_rapidocr = None


def ruta_tesseract():
    """Devuelve la ruta al ejecutable de Tesseract, o None si no se encuentra."""
    global _ruta_tesseract_cache
    if _ruta_tesseract_cache is not None:
        return _ruta_tesseract_cache or None

    candidatos = []
    env = os.environ.get("TESSERACT_CMD")
    if env:
        candidatos.append(env)
    en_path = shutil.which("tesseract")
    if en_path:
        candidatos.append(en_path)
    candidatos.extend(_RUTAS_TESSERACT)

    for ruta in candidatos:
        if ruta and os.path.isfile(ruta):
            _ruta_tesseract_cache = ruta
            return ruta
    _ruta_tesseract_cache = ""
    return None


def _idioma_local():
    """Idioma a usar con la carpeta de idiomas local (spa+eng según lo que haya)."""
    idiomas = [i for i in ("spa", "eng")
               if os.path.isfile(os.path.join(TESSDATA_LOCAL, f"{i}.traineddata"))]
    return "+".join(idiomas)


def _configurar_pytesseract():
    """Configura pytesseract. Devuelve el idioma a usar, o None si no hay Tesseract."""
    cmd = ruta_tesseract()
    if not cmd:
        return None
    try:
        import pytesseract
    except Exception:
        return None
    pytesseract.pytesseract.tesseract_cmd = cmd
    if os.path.isdir(TESSDATA_LOCAL):
        idioma = _idioma_local()
        if idioma:
            # Tesseract 4/5 espera TESSDATA_PREFIX apuntando a la propia carpeta tessdata.
            os.environ["TESSDATA_PREFIX"] = TESSDATA_LOCAL
            return idioma
    return "eng"


def _ocr_tesseract(ruta):
    idioma = _configurar_pytesseract()
    if not idioma:
        return ""
    try:
        import pytesseract
        from PIL import Image
        with Image.open(ruta) as im:
            return (pytesseract.image_to_string(im, lang=idioma) or "").strip()
    except Exception as e:
        print(f"[OCR] Tesseract no pudo procesar la imagen: {e}")
        return ""


def _ocr_rapidocr(ruta):
    global _motor_rapidocr
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return ""
    try:
        if _motor_rapidocr is None:
            _motor_rapidocr = RapidOCR()
        resultado, _ = _motor_rapidocr(ruta)
        if not resultado:
            return ""
        return "\n".join(item[1] for item in resultado).strip()
    except Exception as e:
        print(f"[OCR] RapidOCR no pudo procesar la imagen: {e}")
        return ""


def motor():
    """Nombre del motor OCR activo, o None si ninguno está disponible."""
    if ruta_tesseract():
        return "Tesseract"
    try:
        import importlib.util
        if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
            return "RapidOCR"
    except Exception:
        pass
    return None


def disponible():
    """True si hay algún motor OCR utilizable."""
    global _disponible_cache
    if _disponible_cache is None:
        _disponible_cache = motor() is not None
    return _disponible_cache


def ocr_imagen(ruta):
    """Devuelve el texto detectado en la imagen.

    Intenta primero Tesseract y, si no está o no extrae nada, RapidOCR.
    Devuelve "" si no se detectó texto o no hay OCR disponible.
    """
    if ruta_tesseract():
        texto = _ocr_tesseract(ruta)
        if texto:
            return texto
    return _ocr_rapidocr(ruta)
