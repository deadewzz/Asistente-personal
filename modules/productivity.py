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

    @staticmethod
    def _escribir_docx(ruta, contenido):
        from docx import Document
        doc = Document()
        for linea in contenido.splitlines():
            doc.add_paragraph(linea)
        doc.save(ruta)

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

