import os
import re
import json
import time
import threading
import unicodedata
from datetime import datetime

import numpy as np

from modules import rutas

try:
    import psutil
except ImportError:
    psutil = None


class MeetingAssistant:
    """Detecta reuniones, graba audio (sistema + micrófono), transcribe con Whisper,
    resume con la IA y guarda el resultado en Markdown."""

    APPS_REUNION = ["Teams.exe", "Zoom.exe", "CptHost.exe", "CiscoWebex.exe", "webex.exe", "GoogleMeet.exe"]
    PATRONES_TITULO = ["reunión", "reunion", "meeting", "llamada", "call", "conference", "videollamada"]
    WHISPER_MODEL = "small"

    def __init__(self, config_path=rutas.CONFIG_USUARIO, notas_dir=rutas.REUNIONES):
        self.config_path = config_path
        self.notas_dir = notas_dir
        os.makedirs(self.notas_dir, exist_ok=True)

        self.en_reunion = False
        self.grabando = False
        self._chunks_loop = []
        self._chunks_mic = []
        self._hilos = []
        self._monitor_hilo = None
        self._monitor_activo = False
        self._whisper_model = None

        self.on_alerta = None    # callback de voz (app_gui)
        self.on_resumen = None   # callback para resumir con la IA (app_gui -> brain)
        self.on_metadatos = None  # callback para saber título e invitados (calendario)

        # Datos de la reunión que se está grabando (título, invitados, inicio)
        self._meta = {}

    # ---------------- Detección automática ----------------
    def iniciar_monitoreo(self):
        if self._monitor_activo:
            return
        self._monitor_activo = True
        self._monitor_hilo = threading.Thread(target=self._monitor_bucle, daemon=True)
        self._monitor_hilo.start()

    def detener_monitoreo(self):
        self._monitor_activo = False

    def _monitor_bucle(self):
        while self._monitor_activo:
            en_reunion = self._detectar_reunion()
            if en_reunion and not self.en_reunion:
                self.en_reunion = True
                self.iniciar_grabacion()
                self._alerta("Reunión detectada. Empezando a grabar.")
            elif not en_reunion and self.en_reunion:
                self.en_reunion = False
                self.finalizar()
            time.sleep(5)

    def _detectar_reunion(self):
        if psutil is None:
            return False
        try:
            procesos = {p.info["name"].lower() for p in psutil.process_iter(["name"])}
        except Exception:
            procesos = set()
        hay_app = any(app.lower() in procesos for app in self.APPS_REUNION)
        if not hay_app:
            return False
        try:
            import pygetwindow as gw
            for titulo in gw.getAllTitles():
                t = (titulo or "").lower()
                if any(pat in t for pat in self.PATRONES_TITULO):
                    return True
        except Exception:
            pass
        return False

    # ---------------- Grabación ----------------
    def iniciar_grabacion(self):
        if self.grabando:
            return
        self.grabando = True
        self._chunks_loop = []
        self._chunks_mic = []
        self._hilos = []
        # Datos de la reunión (los rellena la GUI con el calendario si puede). Se piden
        # en segundo plano para que Outlook no retrase el inicio de la grabación.
        self._meta = {"inicio": datetime.now(), "titulo": "", "asistentes": []}
        threading.Thread(target=self._pedir_metadatos, daemon=True).start()
        # Cada fuente se graba en su propio hilo (soundcard y pyaudio se importan de forma diferida)
        self._hilos.append(threading.Thread(target=self._grabar_loopback, args=(self._chunks_loop,), daemon=True))
        self._hilos.append(threading.Thread(target=self._grabar_mic, args=(self._chunks_mic,), daemon=True))
        for t in self._hilos:
            t.start()

    def detener_grabacion(self):
        if not self.grabando:
            return None
        self.grabando = False
        for t in self._hilos:
            t.join(timeout=2)
        audio = self._mezclar(self._chunks_loop, self._chunks_mic)
        self._chunks_loop = []
        self._chunks_mic = []
        self._hilos = []
        return audio

    def _grabar_loopback(self, chunks):
        try:
            import soundcard as sc
            fuente = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            with fuente.recorder(samplerate=16000) as rec:
                while self.grabando and len(chunks) < 7200:  # máx 2 horas
                    data = rec.record(numframes=16000)
                    if data.ndim == 2:
                        data = data.mean(axis=1)
                    chunks.append(data.astype(np.float32))
        except Exception as e:
            print(f"Error grabando loopback: {e}")

    def _grabar_mic(self, chunks):
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            idx = p.get_default_input_device_info()["index"]
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                            frames_per_buffer=16000, input_device_index=idx)
            while self.grabando and len(chunks) < 7200:
                data = stream.read(16000, exception_on_overflow=False)
                chunks.append(np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"Error grabando micrófono: {e}")

    def _mezclar(self, chunks_loop, chunks_mic):
        arr_loop = np.concatenate(chunks_loop) if chunks_loop else None
        arr_mic = np.concatenate(chunks_mic) if chunks_mic else None
        if arr_loop is not None and arr_mic is not None:
            n = max(len(arr_loop), len(arr_mic))
            a = np.zeros(n, dtype=np.float32)
            b = np.zeros(n, dtype=np.float32)
            a[:len(arr_loop)] = arr_loop
            b[:len(arr_mic)] = arr_mic
            return (a + b) / 2
        return arr_loop if arr_loop is not None else arr_mic

    # ---------------- Metadatos de la reunión ----------------
    def _pedir_metadatos(self):
        """Pregunta a la GUI (calendario) el título y los invitados de la reunión.

        Si no hay calendario disponible se usa el título de la ventana de la
        reunión como aproximación; nunca falla por esto.
        """
        datos = None
        if self.on_metadatos:
            try:
                datos = self.on_metadatos()
            except Exception as e:
                print(f"No pude obtener los datos de la reunión: {e}")
        if isinstance(datos, dict):
            titulo = str(datos.get("titulo") or "").strip()
            asistentes = datos.get("asistentes") or []
            if titulo:
                self._meta["titulo"] = titulo
            self._meta["asistentes"] = [str(a).strip() for a in asistentes
                                        if a and str(a).strip()]
        if not self._meta.get("titulo"):
            self._meta["titulo"] = self.titulo_ventana()

    def titulo_ventana(self):
        """Título de la ventana de la reunión en curso (aproximación del asunto)."""
        try:
            import pygetwindow as gw
            for titulo in gw.getAllTitles():
                t = (titulo or "").strip()
                bajo = t.lower()
                if any(pat in bajo for pat in self.PATRONES_TITULO):
                    # Quita el sufijo de la aplicación ("... - Microsoft Teams")
                    for sufijo in (" - microsoft teams", " | microsoft teams", " - zoom",
                                   " - webex", " - google meet", " - cisco webex"):
                        if bajo.endswith(sufijo):
                            t = t[: -len(sufijo)].strip()
                    return t
        except Exception:
            pass
        return ""

    # ---------------- Transcripción y resumen ----------------
    def finalizar(self):
        duracion = 0
        if isinstance(self._meta.get("inicio"), datetime):
            duracion = int((datetime.now() - self._meta["inicio"]).total_seconds() // 60)
        audio = self.detener_grabacion()
        if audio is None or len(audio) < 16000:
            self._alerta("No se grabó audio suficiente.")
            return None
        self._alerta("Procesando la reunión...")
        transcripcion = self._transcribir(audio)
        if not transcripcion:
            self._alerta("No pude transcribir la reunión.")
            return None
        acta = self._resumir(transcripcion)
        ruta = self.guardar_acta(transcripcion, acta, duracion=duracion)
        nombre = os.path.basename(ruta) if ruta else ""
        self._alerta(f"Acta de la reunión guardada ({nombre}). "
                     "Dime 'envía el acta' para mandarla por correo.")
        return ruta

    def _transcribir(self, audio):
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                self._whisper_model = WhisperModel(self.WHISPER_MODEL, device="cpu", compute_type="int8")
            except Exception as e:
                print(f"No se pudo cargar Whisper: {e}")
                return ""
        try:
            segs, _ = self._whisper_model.transcribe(
                audio, language="es", beam_size=1,
                vad_filter=True, without_timestamps=True, condition_on_previous_text=False,
            )
            return " ".join(s.text for s in segs).strip()
        except Exception as e:
            print(f"Error transcribiendo: {e}")
            return ""

    def _resumir(self, transcripcion):
        if self.on_resumen:
            try:
                return self.on_resumen(transcripcion)
            except Exception as e:
                print(f"Error resumiendo: {e}")
        return ""

    def guardar_acta(self, transcripcion, acta, duracion=0, meta=None):
        """Escribe el acta de la reunión (cabecera + acta de la IA + transcripción).

        La cabecera lleva los datos que se pueden leer después (título, fecha,
        duración y asistentes), de modo que el correo del acta y el listado de
        reuniones funcionen incluso tras reiniciar Jarvis.
        """
        ahora = datetime.now()
        datos = dict(meta or self._meta or {})
        titulo = str(datos.get("titulo") or "").strip() or "Reunión sin título"
        asistentes = [str(a).strip() for a in (datos.get("asistentes") or []) if str(a).strip()]
        carpeta = os.path.join(self.notas_dir, ahora.strftime("%Y-%m"))
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"{ahora.strftime('%Y-%m-%d_%H%M')}_Acta.md")
        cuerpo = str(acta or "").strip()
        if not cuerpo:
            cuerpo = ("No se pudo generar el acta con la IA. Debajo queda la "
                      "transcripción completa de la reunión.")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self._cabecera(titulo, ahora, duracion, asistentes))
            f.write(f"\n{cuerpo}\n")
            f.write("\n## Transcripción\n\n" + str(transcripcion).strip() + "\n")
        return ruta

    @staticmethod
    def _cabecera(titulo, cuando, duracion, asistentes):
        """Cabecera del acta en Markdown (datos legibles por 'leer_acta')."""
        lineas = [
            "# Acta de reunión",
            "",
            f"- **Título:** {titulo}",
            f"- **Fecha:** {cuando.strftime('%Y-%m-%d %H:%M')}",
            f"- **Duración:** {duracion} min" if duracion else "- **Duración:** no medida",
            ("- **Asistentes:** " + "; ".join(asistentes)) if asistentes
            else "- **Asistentes:** no identificados",
        ]
        return "\n".join(lineas) + "\n"

    # ---------------- Actas guardadas ----------------
    def _archivos(self):
        """Todos los archivos de reuniones guardados, del más reciente al más antiguo."""
        archivos = []
        for raiz, _dirs, ficheros in os.walk(self.notas_dir):
            for nombre in ficheros:
                if nombre.lower().endswith(".md"):
                    archivos.append(os.path.join(raiz, nombre))
        archivos.sort(key=lambda r: os.path.getmtime(r), reverse=True)
        return archivos

    @staticmethod
    def _sin_acentos(texto):
        """Texto sin acentos y en minúsculas, para comparar nombres."""
        plano = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in plano if not unicodedata.combining(c)).lower()

    @staticmethod
    def _titulo_de_nombre(nombre):
        """Título aproximado de una reunión a partir del nombre de su archivo."""
        base = os.path.splitext(str(nombre or ""))[0]
        coincidencia = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})", base)
        if coincidencia:
            return (f"Reunión del {coincidencia.group(1)}-{coincidencia.group(2)}-"
                    f"{coincidencia.group(3)} {coincidencia.group(4)}:{coincidencia.group(5)}")
        return base.replace("_", " ")

    def _datos_archivo(self, ruta):
        """Datos de cabecera de un acta guardada."""
        datos = {"ruta": ruta, "nombre": os.path.basename(ruta), "titulo": "",
                 "fecha": "", "duracion": "", "asistentes": []}
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                primeras = f.read(2000)     # con el principio sobra para la cabecera
        except Exception as e:
            print(f"No pude leer {ruta}: {e}")
            return datos
        for etiqueta, clave in (("Título", "titulo"), ("Fecha", "fecha"),
                                ("Duración", "duracion")):
            coincidencia = re.search(rf"^- \*\*{etiqueta}:\*\* (.+)$", primeras, re.MULTILINE)
            if coincidencia:
                datos[clave] = coincidencia.group(1).strip()
        coincidencia = re.search(r"^- \*\*Asistentes:\*\* (.+)$", primeras, re.MULTILINE)
        if coincidencia and "no identificados" not in coincidencia.group(1):
            datos["asistentes"] = [a.strip() for a in coincidencia.group(1).split(";") if a.strip()]
        if not datos["titulo"]:
            datos["titulo"] = self._titulo_de_nombre(datos["nombre"])
        if not datos["fecha"]:
            try:
                datos["fecha"] = datetime.fromtimestamp(
                    os.path.getmtime(ruta)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                datos["fecha"] = ""
        return datos

    def listar_actas(self, n=8):
        """Lista las actas guardadas (de la más reciente a la más antigua)."""
        return [self._datos_archivo(r) for r in self._archivos()[:max(1, int(n))]]

    def reunion_actual(self):
        """Datos de la reunión que se acaba de grabar (título y asistentes)."""
        return dict(self._meta or {})

    def _resolver_acta(self, clave=None):
        """Localiza el archivo de una reunión por número, por nombre o por su ruta."""
        texto = str(clave or "").strip()
        if texto and os.path.isfile(texto):
            return texto
        archivos = self._archivos()
        if not archivos:
            return None
        if not texto or self._sin_acentos(texto) in (
                "ultima", "la ultima", "el ultimo", "ultimo"):
            return archivos[0]
        if texto.isdigit():
            indice = int(texto) - 1
            return archivos[indice] if 0 <= indice < len(archivos) else None
        buscado = self._sin_acentos(texto)
        for ruta in archivos[:40]:
            if buscado in self._sin_acentos(os.path.basename(ruta)):
                return ruta
            if buscado in self._sin_acentos(self._datos_archivo(ruta)["titulo"]):
                return ruta
        return None

    def leer_acta(self, clave=None):
        """Devuelve un acta guardada: (dict con cuerpo y transcripción) o (None, error)."""
        ruta = self._resolver_acta(clave)
        if ruta is None:
            return None, ("No encuentro esa reunión. Dime 'mis reuniones' para ver las "
                          "actas guardadas.")
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                contenido = f.read()
        except Exception as e:
            return None, f"No pude leer el acta: {e}"
        datos = self._datos_archivo(ruta)
        datos["contenido"] = contenido
        datos["cabecera"], datos["cuerpo"], datos["transcripcion"] = self._partir(contenido)
        return datos, ""

    @staticmethod
    def _partir(contenido):
        """Separa (cabecera, cuerpo del acta, transcripción) de un archivo de acta.

        Sirve para el formato nuevo (cabecera de datos + acta + '## Transcripción')
        y para los resúmenes antiguos ('## Resumen' + '## Transcripción completa'):
        el cuerpo es todo lo que va desde el primer '## ' hasta la transcripción.
        """
        lineas = str(contenido or "").splitlines()
        corte = next((i for i, l in enumerate(lineas)
                      if l.strip().lower().startswith("## transcripci")), None)
        tope = corte if corte is not None else len(lineas)
        transcripcion = "\n".join(lineas[corte + 1:]).strip() if corte is not None else ""
        inicio = next((i for i in range(tope) if lineas[i].startswith("## ")), tope)
        cabecera = "\n".join(lineas[:inicio]).strip()
        cuerpo = "\n".join(lineas[inicio:tope]).strip()
        return cabecera, cuerpo, transcripcion

    def acta_para_correo(self, clave=None, intro=""):
        """Prepara el correo del acta: (dict con asunto/cuerpo/destinatarios) o (None, error)."""
        acta, error = self.leer_acta(clave)
        if acta is None:
            return None, error
        cuerpo = acta["cuerpo"] or "No hay acta generada para esa reunión."
        if intro:
            cuerpo = intro.strip() + "\n\n" + cuerpo
        if acta["transcripcion"]:
            cuerpo += ("\n\n---\n\nLa transcripción completa de la reunión está en el "
                       f"archivo {acta['nombre']} de tu equipo.")
        asunto = f"Acta — {acta['titulo']}"
        if acta["fecha"]:
            asunto += f" ({acta['fecha']})"
        return {"asunto": asunto, "cuerpo": cuerpo, "ruta": acta["ruta"],
                "titulo": acta["titulo"], "destinatarios": list(acta["asistentes"]),
                "con_transcripcion": bool(acta["transcripcion"])}, ""

    def rehacer_acta(self, clave=None):
        """Vuelve a generar el acta de una reunión a partir de su transcripción."""
        acta, error = self.leer_acta(clave)
        if acta is None:
            return error
        if not acta["transcripcion"]:
            return (f"El archivo {acta['nombre']} no tiene transcripción, así que no "
                    "puedo rehacer el acta.")
        if self.on_resumen is None:
            return "No tengo la IA disponible ahora mismo para rehacer el acta."
        nueva = self._resumir(acta["transcripcion"])
        if not str(nueva or "").strip():
            return "La IA no devolvió contenido, así que el acta se queda como estaba."
        # Se conserva la cabecera (título, fecha, asistentes) y la transcripción
        cabecera = str(acta.get("cabecera") or "").strip()
        if not cabecera.startswith("# "):
            cabecera = ("# Acta de reunión\n\n" + cabecera).strip()
        contenido = (cabecera.rstrip() + "\n\n" + str(nueva).strip()
                     + "\n\n## Transcripción\n\n" + acta["transcripcion"].strip() + "\n")
        try:
            with open(acta["ruta"], "w", encoding="utf-8") as f:
                f.write(contenido)
        except Exception as e:
            return f"No pude guardar el acta rehecha: {e}"
        return f"Acta rehecha con la IA y guardada en {acta['ruta']}."

    def _alerta(self, texto):
        if self.on_alerta:
            try:
                self.on_alerta(texto)
            except Exception as e:
                print(f"Error alertando: {e}")

