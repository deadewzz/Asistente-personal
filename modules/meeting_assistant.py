import os
import json
import time
import threading
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

    # ---------------- Transcripción y resumen ----------------
    def finalizar(self):
        audio = self.detener_grabacion()
        if audio is None or len(audio) < 16000:
            self._alerta("No se grabó audio suficiente.")
            return None
        self._alerta("Procesando la reunión...")
        transcripcion = self._transcribir(audio)
        if not transcripcion:
            self._alerta("No pude transcribir la reunión.")
            return None
        resumen = self._resumir(transcripcion)
        ruta = self.guardar_resumen(transcripcion, resumen)
        self._alerta("Resumen de la reunión guardado en tu carpeta de notas.")
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

    def guardar_resumen(self, transcripcion, resumen):
        ahora = datetime.now()
        carpeta = os.path.join(self.notas_dir, ahora.strftime("%Y-%m"))
        os.makedirs(carpeta, exist_ok=True)
        nombre = f"{ahora.strftime('%Y-%m-%d_%H%M')}_Reunion.md"
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("# Resumen de Reunión\n\n")
            f.write(f"- **Fecha:** {ahora.strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"## Resumen\n\n{resumen}\n\n")
            f.write(f"## Transcripción completa\n\n{transcripcion}\n")
        return ruta

    def _alerta(self, texto):
        if self.on_alerta:
            try:
                self.on_alerta(texto)
            except Exception as e:
                print(f"Error alertando: {e}")

