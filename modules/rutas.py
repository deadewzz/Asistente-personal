"""Rutas centralizadas de Jarvis.

Todos los archivos que genera y utiliza Jarvis (conversaciones, notas, reglas
permanentes, documentos, adjuntos, reuniones, presentaciones, preventa,
plantillas, modelos, temporales y configuración) viven bajo una única carpeta
raíz organizada por tipo en subcarpetas.

Por defecto la raíz es  C:\\Users\\<usuario>\\Documents\\Jarvis  y se puede
personalizar con la variable de entorno JARVIS_HOME.
"""

import os
import shutil


def _carpeta_raiz():
    """Carpeta raíz de Jarvis donde se guardan todos sus archivos."""
    personalizada = os.environ.get("JARVIS_HOME")
    if personalizada:
        return os.path.abspath(os.path.expanduser(personalizada))
    documentos = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(documentos, "Jarvis")


# ---------------- Raíz y subcarpetas por tipo de contenido ----------------
JARVIS_HOME = _carpeta_raiz()
CONFIG = os.path.join(JARVIS_HOME, "config")                 # Ajustes y memoria del asistente
CONVERSACIONES = os.path.join(JARVIS_HOME, "conversaciones")  # Historiales de chat (.md)
NOTAS = os.path.join(JARVIS_HOME, "notas")                    # Notas diarias (.md)
REUNIONES = os.path.join(JARVIS_HOME, "reuniones")            # Resúmenes de reuniones (.md)
MATRICES = os.path.join(JARVIS_HOME, "matrices")              # Matrices (.xlsx) para la nube
DOCUMENTOS = os.path.join(JARVIS_HOME, "documentos")         # Documentos de texto (.txt)
ADJUNTOS = os.path.join(JARVIS_HOME, "adjuntos")             # Imágenes/textos pegados o adjuntos
PRESENTACIONES = os.path.join(JARVIS_HOME, "presentaciones")  # Fuentes .md para PowerPoint
PREVENTA = os.path.join(JARVIS_HOME, "preventa")             # Documentos de preventa (.md)
PLANTILLAS = os.path.join(JARVIS_HOME, "plantillas")         # Plantillas .pptx
MODELOS = os.path.join(JARVIS_HOME, "modelos")               # Modelos locales (p. ej. voz)
TEMP = os.path.join(JARVIS_HOME, "temp")                     # Archivos temporales (audio, capturas)

# ---------------- Archivos concretos ----------------
CONFIG_USUARIO = os.path.join(CONFIG, "config_usuario.json")
REGLAS = os.path.join(CONFIG, "reglas.md")

CARPETAS = [
    CONFIG, CONVERSACIONES, NOTAS, REUNIONES, MATRICES, DOCUMENTOS, ADJUNTOS,
    PRESENTACIONES, PREVENTA, PLANTILLAS, MODELOS, TEMP,
]


def asegurar():
    """Crea la carpeta raíz y todas sus subcarpetas si no existen. Devuelve la raíz."""
    for carpeta in CARPETAS:
        os.makedirs(carpeta, exist_ok=True)
    return JARVIS_HOME


# ---------------- Migración desde la estructura antigua (assets/, config/) ----------------
def _mover_si_falta(origen, destino_dir):
    """Mueve 'origen' a 'destino_dir' si todavía no existe allí. Devuelve True si movió."""
    if not os.path.exists(origen):
        return False
    destino = os.path.join(destino_dir, os.path.basename(origen))
    if os.path.exists(destino):
        return False
    try:
        os.makedirs(destino_dir, exist_ok=True)
        shutil.move(origen, destino)
        return True
    except Exception as e:
        print(f"[rutas] No pude mover {origen}: {e}")
        return False


def _mover_arbol(origen_dir, destino_dir):
    """Mueve recursivamente el contenido de 'origen_dir' a 'destino_dir' conservando
    las subcarpetas, sin sobrescribir los archivos ya presentes en el destino."""
    if not os.path.isdir(origen_dir):
        return
    for raiz, _dirs, archivos in os.walk(origen_dir):
        rel = os.path.relpath(raiz, origen_dir)
        destino_sub = destino_dir if rel == "." else os.path.join(destino_dir, rel)
        for nombre in archivos:
            _mover_si_falta(os.path.join(raiz, nombre), destino_sub)


def migrar_datos_antiguos(base_dir):
    """Migra los datos de la estructura antigua (carpetas 'assets/' y 'config/'
    relativas a 'base_dir') a la carpeta raíz de Jarvis.

    Es idempotente y no sobrescribe archivos que ya existan en el destino, por lo
    que se puede llamar en cada arranque sin riesgo de duplicar o perder datos.
    Devuelve el número de archivos migrados.
    """
    migrados = 0

    # 'assets/notas' mezclaba conversaciones, notas y reglas: se reparten por tipo.
    notas_antiguo = os.path.join(base_dir, "assets", "notas")
    if os.path.isdir(notas_antiguo):
        for nombre in os.listdir(notas_antiguo):
            ruta = os.path.join(notas_antiguo, nombre)
            if os.path.isdir(ruta):
                continue
            bajo = nombre.lower()
            if bajo.startswith("historial_chat_"):
                migrados += _mover_si_falta(ruta, CONVERSACIONES)
            elif bajo == "reglas.md":
                migrados += _mover_si_falta(ruta, CONFIG)
            elif bajo.startswith("notas_"):
                migrados += _mover_si_falta(ruta, NOTAS)
        # Reuniones: subcarpetas por mes dentro de assets/notas/reuniones
        antes = _contar_archivos(REUNIONES)
        _mover_arbol(os.path.join(notas_antiguo, "reuniones"), REUNIONES)
        migrados += _contar_archivos(REUNIONES) - antes

    # Resto de carpetas de 'assets'
    assets = os.path.join(base_dir, "assets")
    for origen, destino in (
        ("documentos", DOCUMENTOS),
        ("adjuntos", ADJUNTOS),
        ("presentaciones", PRESENTACIONES),
        ("preventa", PREVENTA),
        ("plantillas", PLANTILLAS),
        ("modelos", MODELOS),
    ):
        antes = _contar_archivos(destino)
        _mover_arbol(os.path.join(assets, origen), destino)
        migrados += _contar_archivos(destino) - antes

    # Configuración del usuario
    migrados += _mover_si_falta(
        os.path.join(base_dir, "config", "config_usuario.json"), CONFIG)

    return migrados


def _contar_archivos(carpeta):
    if not os.path.isdir(carpeta):
        return 0
    total = 0
    for _raiz, _dirs, archivos in os.walk(carpeta):
        total += len(archivos)
    return total
