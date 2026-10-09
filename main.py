import os
import sys
import json

# Silencia el aviso de huggingface_hub sobre los enlaces simbólicos en Windows.
# Debe fijarse ANTES de importar módulos que cargan Whisper (voice_engine /
# meeting_assistant) para que el aviso no aparezca en el arranque. La caché de
# los modelos funciona igual; solo ocupa algo más de disco sin enlaces simbólicos.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from app_gui import AppGUI
from modules.voice_output import VoiceOutput
from modules import rutas

# Toda la configuración y los datos de Jarvis viven bajo la carpeta raíz de
# Jarvis (por defecto <Documentos del usuario>/Jarvis).
CONFIG_PATH = rutas.CONFIG_USUARIO


def obtener_directorio_base():
    """Devuelve el directorio base: junto al ejecutable (congelado) o al script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def cargar_dotenv(path=".env"):
    """Carga variables de entorno desde un archivo .env (sin dependencias externas)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            os.environ.setdefault(clave, valor)

def verificar_entorno():
    """Crea la carpeta raíz de Jarvis con sus subcarpetas y el JSON de
    configuración si no existen en la primera ejecución."""
    rutas.asegurar()

    if not os.path.exists(CONFIG_PATH):
        config_inicial = {
            "api_key": "",
            "nombre_asistente": "jarvis",
            "modelo_rvc_path": "",
            "programas": {
                "discord": "discord://",
                "spotify": "spotify:",
                "vscode": "code"
            }
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_inicial, f, indent=4)

if __name__ == "__main__":
    # Directorio de la aplicación (para recursos empaquetados como
    # assets/tools/tessdata); los datos del usuario van a la carpeta de Jarvis.
    base_dir = obtener_directorio_base()
    os.chdir(base_dir)

    # Cargar variables de entorno (.env) antes de leer la configuración
    cargar_dotenv()

    # Migrar los datos de la estructura antigua (assets/, config/) a la carpeta
    # de Jarvis y asegurar que exista toda la estructura de carpetas.
    rutas.asegurar()
    migrados = rutas.migrar_datos_antiguos(base_dir)
    print(f"Jarvis: carpeta de datos -> {rutas.JARVIS_HOME}")
    if migrados:
        print(f"Jarvis: {migrados} archivo(s) migrados a la nueva ubicación.")

    verificar_entorno()

    # Inicialización del motor de voz rápido (offline, fallback)
    voice_output = VoiceOutput()

    # Pasamos voice_output a la interfaz
    app = AppGUI(config_path=CONFIG_PATH, voice_output=voice_output)
    app.mainloop()