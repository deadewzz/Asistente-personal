import os
import json
import re
import time
import asyncio
import unicodedata
import speech_recognition as sr
import edge_tts
import pygame

from modules import rutas

try:
    import numpy as np
except ImportError:
    np = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

class VoiceEngine:
    # Variantes fonéticas comunes de la palabra de activación (Google a veces las transcribe así)
    VARIANTES_ACTIVACION = {
        "jarvis": ["javis", "yarvis", "jarbis", "yarbis", "harvis", "charvis", "jarviz", "yarbiz"]
    }

    USAR_WHISPER = True   # True: Whisper local (más preciso). Cambia a False si quieres solo Google.
    WHISPER_MODEL = "small"  # "base"(rápido) | "small"(mejor con habla rápida) | "medium"(más preciso, lento)

    def __init__(self, config_path=rutas.CONFIG_USUARIO, temp_folder=rutas.TEMP):
        self.config_path = config_path
        self.temp_folder = temp_folder
        self.nombre_activacion = self._cargar_nombre_asistente()
        self.voz_tts = "es-MX-DaliaNeural"
        #: Voz inglesa (para el «speaking» del tutor de inglés): el mismo motor, otra
        #: voz. Pedir `hablar(..., idioma="en")` lee la respuesta en inglés.
        self.voz_ingles = "en-US-AriaNeural"
        self.voz_rate = "+15%"  # habla un poco más ágil para que no se sienta pausada
        
        self.recognizer = sr.Recognizer()
        
        # --- CONFIGURACIÓN DE ESCUCHA ---
        self.recognizer.dynamic_energy_threshold = True   # Ajusta el umbral al ruido ambiente (evita recortar palabras)
        self.recognizer.energy_threshold = 300            # Umbral base (se recalibra automáticamente)
        self.recognizer.pause_threshold = 1.2             # Silencio para detectar el fin de frase (sin cortar a media palabra)
        self.recognizer.non_speaking_duration = 0.8
        self.whisper_model = None                          # Modelo Whisper (carga diferida, solo si USAR_WHISPER)
        
        # Modo Conversación Continua
        self.modo_continuo = False
        self.ultimo_tiempo_interaccion = 0
        self.timeout_conversacion = 120  # Segundos de conversación continua antes de requerir la palabra clave

        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder)
            
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"No se pudo inicializar el mezclador de audio: {e}")

    def _cargar_nombre_asistente(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    nombre = data.get("nombre_asistente", "").strip().lower()
                    if nombre:
                        return nombre
            except Exception as e:
                print(f"Error cargando nombre del asistente: {e}")
        return "jarvis"

    def escuchar_microfono(self):
        with sr.Microphone() as source:
            print("Escuchando...")
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=12)
            except sr.WaitTimeoutError:
                return None

            # 1. Reconocimiento principal: Whisper local (más preciso), con fallback a Google
            texto_es = self._reconocer_whisper(audio)
            if not texto_es:
                texto_es = self._reconocer(audio, "es-CO")
            if texto_es:
                print(f"Oído (es): {texto_es}")

            # 2a. Comando para cerrar el programa por completo
            if texto_es and self._es_comando_cerrar(texto_es):
                return "COMANDO_CERRAR"

            # 2b. Comando para detener la escucha (sin cerrar la app)
            if texto_es and self._es_comando_apagado(texto_es):
                return "COMANDO_APAGAR"

            # 3. Control de tiempo en modo continuo
            tiempo_actual = time.time()
            if self.modo_continuo and (tiempo_actual - self.ultimo_tiempo_interaccion > self.timeout_conversacion):
                print("Ventana de conversación continua cerrada.")
                self.modo_continuo = False

            # 4. Modo continuo: si ya estamos conversando, procesar directamente (sin re-escuchar en inglés)
            if self.modo_continuo and texto_es:
                self.ultimo_tiempo_interaccion = time.time()
                # quitar la palabra de activación si el usuario la repite por costumbre
                return self._limpiar_comando(self._quitar_activacion(texto_es))

            # 5. Detección de la palabra de activación (en español)
            if texto_es and self._contiene_activacion(texto_es):
                self._activar_modo_continuo()
                comando = self._limpiar_comando(self._quitar_activacion(texto_es))
                return comando if comando else "hola"

            # 6. Fallback en inglés (solo si hubo habla en español sin palabra de activación)
            if texto_es:
                texto_en = self._reconocer(audio, "en-US")
                if texto_en:
                    print(f"Oído (en): {texto_en}")
                    if self._contiene_activacion(texto_en):
                        self._activar_modo_continuo()
                        # Para el comando preferimos el texto en español (si hubo algo útil)
                        comando = texto_es if (texto_es and len(texto_es.strip()) > 2) else self._quitar_activacion(texto_en)
                        comando = self._limpiar_comando(self._quitar_activacion(comando))
                        return comando if comando else "hola"

            return None

    def escuchar_ingles(self, timeout=6, frase_max=14):
        """Escucha una frase en inglés y la devuelve (para el «speaking» del tutor).

        Es el mismo micrófono que usa el chat, pero aquí no hay nada que
        interpretar: lo que diga el alumno *es* la práctica, así que no se busca
        palabra de activación ni comandos de cierre. Se transcribe con Whisper en
        inglés (conservando las mayúsculas: «i» → «I») y, si no está disponible,
        con Google. Devuelve el texto oído, o None si no se oyó nada.
        """
        try:
            with sr.Microphone() as source:
                audio = self.recognizer.listen(source, timeout=timeout,
                                                phrase_time_limit=frase_max)
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"No pude escuchar por el micrófono: {e}")
            return None

        texto = self._reconocer_whisper(audio, "en", minusculas=False)
        if not texto:
            texto = self._reconocer(audio, "en-US")
        if not texto:
            return None
        texto = self._arreglar_mayusculas(texto)
        print(f"Oído (en, speaking): {texto}")
        return texto

    @staticmethod
    def _arreglar_mayusculas(texto):
        """Devuelve el dictado con las mayúsculas que le quitan los traductores.

        Whisper y Google entregan todo en minúsculas, y para practicar inglés hay
        que ver «I am from Spain» y no «i am from spain»: además de quedar mal, el
        analizador del tutor contaría como fallo del alumno algo que no ha dicho.
        """
        texto = str(texto or "").strip()
        if not texto:
            return ""
        # El pronombre «I» (y sus contracciones) va siempre en mayúscula.
        texto = re.sub(r"\bi\b", "I", texto)
        texto = re.sub(r"\bi('(?:m|ll|ve|d))\b", lambda m: "I" + m.group(1), texto)
        # Y cada frase empieza en mayúscula.
        return re.sub(r"(^\s*|[.!?]\s+)([a-z])",
                      lambda m: m.group(1) + m.group(2).upper(), texto)

    def _activar_modo_continuo(self):
        self.modo_continuo = True
        self.ultimo_tiempo_interaccion = time.time()

    def _reconocer(self, audio, lang):
        try:
            return self.recognizer.recognize_google(audio, language=lang).lower().strip()
        except (sr.UnknownValueError, sr.RequestError):
            return None
        except Exception as e:
            print(f"Error reconociendo voz ({lang}): {e}")
            return None

    def _cargar_modelo_whisper(self):
        """Carga (una sola vez) el modelo de Whisper. Devuelve None si no está disponible."""
        if WhisperModel is None:
            return None
        if self.whisper_model is None:
            try:
                print(f"Cargando modelo Whisper '{self.WHISPER_MODEL}' (solo la primera vez)...")
                self.whisper_model = WhisperModel(self.WHISPER_MODEL, device="cpu", compute_type="int8")
            except Exception as e:
                print(f"No se pudo cargar Whisper, se usará Google: {e}")
                self.whisper_model = None
        return self.whisper_model

    def _reconocer_whisper(self, audio, idioma="es", minusculas=True):
        """Transcribe el audio con Whisper (local). Devuelve el texto o None si falla.

        `minusculas` se pone a False para el inglés hablado: ahí las mayúsculas
        («I», los nombres) forman parte de lo que se está practicando.
        """
        if not self.USAR_WHISPER:
            return None
        modelo = self._cargar_modelo_whisper()
        if modelo is None or np is None:
            return None
        try:
            data = audio.get_raw_data(convert_rate=16000, convert_width=2)
            arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            segmentos, _ = modelo.transcribe(
                arr,
                language=idioma,
                beam_size=1,
                vad_filter=True,                  # recorta silencios (más rápido y preciso)
                without_timestamps=True,          # texto limpio, sin marcas de tiempo
                condition_on_previous_text=False,  # evita alucinaciones en frases cortas
            )
            texto = " ".join(s.text for s in segmentos).strip()
            return texto.lower() if minusculas else texto
        except Exception as e:
            print(f"Error en Whisper: {e}")
            return None

    def _normalizar(self, texto):
        texto = texto.lower()
        texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
        # quitar signos de puntuación (para que "pedro," coincida con "pedro")
        texto = "".join(c for c in texto if c.isalnum() or c.isspace())
        return texto.strip()

    def _contiene_activacion(self, texto):
        if not texto:
            return False
        t = self._normalizar(texto)
        nombre = self._normalizar(self.nombre_activacion)
        if nombre in t:
            return True
        variantes = self.VARIANTES_ACTIVACION.get(nombre, [])
        return any(v in t for v in variantes)

    def _quitar_activacion(self, texto):
        if not texto:
            return ""
        t = texto.lower().strip()
        nombre = self.nombre_activacion.lower()
        candidatos = [nombre] + self.VARIANTES_ACTIVACION.get(nombre, [])
        for v in candidatos:
            if v in t:
                t = t.replace(v, "", 1)
                break
        return t.strip()

    def _limpiar_comando(self, texto):
        """Quita puntuación residual y normaliza espacios del comando."""
        if not texto:
            return ""
        t = texto.strip().strip(" \t,.;:!?¿¡()[]\"'")
        t = " ".join(t.replace(",", " ").replace(".", " ").replace(";", " ").split())
        return t.strip(" ,.;:!?¿¡()[]\"'")

    def _es_comando_apagado(self, texto):
        """Detener la escucha (sin cerrar la app)."""
        t = self._normalizar(texto)
        return any(p in t for p in ["detente", "silencio", "deja de escuchar", "pausa"])

    def _es_comando_cerrar(self, texto):
        """Cerrar el programa por completo."""
        t = self._normalizar(texto)
        return any(p in t for p in [
            "cierra el programa", "cierra la aplicacion", "cierra la app",
            "sal del programa", "cierrate", "apagate", "adios", "salir",
            "apaga el programa", "cierra el asistente", "termina el programa",
        ])

    def hablar(self, texto, rvc_model_path=None, idioma="es"):
        """Dice el texto en voz alta (español por defecto; ``idioma="en"`` en inglés)."""
        if not texto:
            return

        voz = self.voz_ingles if str(idioma or "es").lower().startswith("en") else self.voz_tts
        ruta_audio_temp = os.path.join(self.temp_folder, "respuesta_base.mp3")
        ruta_audio_final = os.path.join(self.temp_folder, "respuesta_final.wav")

        asyncio.run(self._generar_tts(texto, ruta_audio_temp, voz))

        if rvc_model_path and os.path.exists(rvc_model_path):
            self._aplicar_rvc(ruta_audio_temp, ruta_audio_final, rvc_model_path)
            archivo_reproducir = ruta_audio_final
        else:
            archivo_reproducir = ruta_audio_temp

        self._reproducir_audio(archivo_reproducir)

    async def _generar_tts(self, texto, output_path, voz=None):
        communicate = edge_tts.Communicate(texto, voz or self.voz_tts, rate=self.voz_rate)
        await communicate.save(output_path)

    def _aplicar_rvc(self, input_audio, output_audio, model_path):
        try:
            from rvc_python.infer import RVCInference
            rvc = RVCInference(device="cpu")
            rvc.load_model(model_path)
            rvc.infer_file(input_audio, output_audio)
        except Exception as e:
            print(f"Error procesando RVC: {e}")

    def _reproducir_audio(self, filepath):
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()

            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)

            pygame.mixer.music.unload()
        except Exception as e:
            print(f"Error reproduciendo audio: {e}")