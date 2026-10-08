import pyttsx3
import threading

class VoiceOutput:
    def __init__(self):
        self.engine = pyttsx3.init()
        # Aumentamos la velocidad de voz (el estándar es ~200, 230-240 se siente ágil y fluido)
        self.engine.setProperty('rate', 235)
        self._configurar_voz_espanol()
        # pyttsx3 no es thread-safe: serializamos las llamadas con un candado
        self._lock = threading.Lock()

    def _configurar_voz_espanol(self):
        """Intenta seleccionar una voz en español si está disponible."""
        try:
            voces = self.engine.getProperty('voices')
            for voz in voces:
                nombre = (voz.name or "").lower()
                if "spanish" in nombre or "espa" in nombre or "es-" in nombre or "es_" in nombre:
                    self.engine.setProperty('voice', voz.id)
                    break
        except Exception as e:
            print(f"No se pudo configurar voz en español: {e}")

    def hablar(self, texto):
        if not texto:
            return
        
        # Ocultar la sintaxis interna [ACCION: ...] para que no la lea verbalmente
        if "[ACCION:" in texto:
            texto = texto.split("[ACCION:")[0].strip()

        if texto:
            # Se dispara en un hilo demonio para que la interfaz/consola no sufran congelamientos
            threading.Thread(target=self._decir_texto, args=(texto,), daemon=True).start()

    def _decir_texto(self, texto):
        try:
            with self._lock:
                self.engine.say(texto)
                self.engine.runAndWait()
        except Exception as e:
            print(f"Error en síntesis de voz: {e}")