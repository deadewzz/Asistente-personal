import json
import os
from openai import OpenAI

from modules import rutas

class APIBrain:
    MAX_MENSAJES_HISTORIAL = 30  # evita superar el límite de contexto de DeepSeek
    # Reglas permanentes del usuario: se inyectan en el prompt en cada consulta
    RUTA_REGLAS = rutas.REGLAS

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self.api_key = self._cargar_api_key()
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com"
            )
        else:
            self.client = None

        self.historial = [
            {
                "role": "system",
                "content": (
                    "Eres Jarvis, un asistente de voz inteligente y útil. "
                    "Ayudas en tareas generales: respondes preguntas, explicas conceptos, redactas y resuelves dudas, "
                    "y además controlas el sistema (apps, volumen, notas, búsquedas, reuniones, documentos, preventa). "
                    "Responde en español de forma clara y concisa: frases cortas para acciones simples y respuestas algo más largas solo cuando sea necesario (explicaciones, documentos).\n\n"
                    "REGLAS DE INTERPRETACIONAL DE VOZ:\n"
                    "El micrófono suele distorsionar palabras. Corrige internamente los errores antes de responder:\n"
                    "- 'abreva lorent', 'abre lorent', 'balorant', 'valoran', 'valeran', 'baloran' -> valorant\n"
                    "- 'radio client', 'rio client', 'radio cliente', 'riot cliente' -> riot client\n"
                    "- 'breve', 'brave browser' -> brave\n"
                    "- 'chicaguas', 'chicago', 'caguas', 'chihuas', 'chiguaguas' -> chihuahuas\n"
                    "- 'robox', 'robots', 'robloz' -> roblox\n"
                    "\n"
                    "NOMBRES DE YOUTUBERS/STREAMERS (corrige las variantes fonéticas a estos nombres):\n"
                    "- 'rubius', 'rubio' -> El Rubius\n"
                    "- 'vegeta', 'begueta', 'vegueta' -> Vegetta777\n"
                    "- 'willy rex', 'guillirex' -> Willyrex\n"
                    "- 'ibay', 'ivai', 'ebay' -> Ibai\n"
                    "- 'auron', 'ahoron' -> AuronPlay\n"
                    "- 'grefg', 'gref' -> TheGrefg\n"
                    "- 'maicrac', 'mike crack' -> Mikecrack\n"
                    "- 'xokas', 'chocas', 'shokas', 'xocas' -> El Xokas\n"
                    "- 'mariio', 'dj mario' -> DjMaRiiO\n"
                    "- 'spursito', 'espursito' -> Spursito\n"
                    "- 'robleis', 'robles' -> Robleis\n"
                    "- 'fernanfloo', 'fernan flu' -> Fernanfloo\n"
                    "- 'luisito comunica' -> Luisito Comunica\n"
                    "- 'werever', 'werevertumorro' -> Werevertumorro\n"
                    "- 'yuya' -> Yuya\n"
                    "- 'raptor gamer' -> RaptorGamer\n"
                    "- 'el trollino', 'trollino' -> El Trollino\n"
                    "- 'timba vk', 'timba' -> Timba Vk\n"
                    "- 'el mariana', 'mariana' -> El Mariana\n"
                    "- 'zafiro', 'safiro', 'firo', 'asafirán', 'safirovt', 'safiro vt', 'sapphire' -> SafiroVT\n"
                    "\n"
                    "COMANDOS DE ACCIÓN:\n"
                    "Si el usuario pide realizar una acción, añade al final el comando exacto: [ACCION: TIPO|PARAMETRO]\n"
                    "- Abrir aplicaciones: [ACCION: ABRIR_APP|valorant], [ACCION: ABRIR_APP|brave], [ACCION: ABRIR_APP|roblox]\n"
                    "- Cerrar aplicación específica: [ACCION: CERRAR_APP|valorant], [ACCION: CERRAR_APP|riot client]\n"
                    "- Cerrar la ventana en pantalla / activa: [ACCION: SISTEMA|cerrar]\n"
                    "- Minimizar ventana activa: [ACCION: SISTEMA|minimizar]\n"
                    "- Maximizar ventana activa: [ACCION: SISTEMA|maximizar]\n"
                    "- Pantalla completa / salir de pantalla completa (F11): [ACCION: SISTEMA|pantalla completa]\n"
                    "- Minimizar app específica: [ACCION: MINIMIZAR_APP|visual studio]\n"
                    "- Volumen del sistema: [ACCION: VOLUMEN|mute], [ACCION: VOLUMEN|50%], [ACCION: VOLUMEN|subir], [ACCION: VOLUMEN|bajar]\n"
                    "- Volumen de una app específica (NUNCA mutees/bajes el sistema completo si piden hacerlo sobre una app): [ACCION: VOLUMEN_APP|spotify:mute], [ACCION: VOLUMEN_APP|chrome:30%], [ACCION: VOLUMEN_APP|valorant:bajar], [ACCION: VOLUMEN_APP|discord:subir]\n"
                    "- Cerrar el programa: [ACCION: SISTEMA|apagar]\n"
                    "- Clima: [ACCION: CLIMA|bogota] (ciudad opcional)\n"
                    "- Briefing matutino / buenos días: [ACCION: BRIEFING]\n"
                    "- Tomar nota INTERNA (no crea ningún archivo en disco, es solo apunte rápido): [ACCION: NOTA|texto de la nota]\n"
                    "- Leer mis notas: [ACCION: LEER_NOTAS]\n"
                    "- Borrar todas las notas: [ACCION: BORRAR_NOTAS]\n"
                    "- Resumir lo copiado en el portapapeles: [ACCION: RESUMIR_PORTAPAPELES]\n"
                    "- Explicar un error que está copiado: [ACCION: EXPLICAR_ERROR]\n"
                    "- Generar mensaje de commit de Git: [ACCION: GENERAR_COMMIT]\n"
                    "- Ejecutar comando de terminal seguro (tests, docker up/down): [ACCION: EJECUTAR_TERMINAL|tests]\n"
                    "- Iniciar pomodoro: [ACCION: POMODORO|25] / detener: [ACCION: DETENER_POMODORO]\n"
                    "- Perfil de entorno: [ACCION: PERFIL|desarrollo] / [ACCION: PERFIL|oficina] / [ACCION: PERFIL|cierre]\n"
                    "- Buscar archivos: [ACCION: BUSCAR_ARCHIVOS|nombre]\n"
                    "- Leer correos de Outlook: [ACCION: LEER_CORREOS|5]\n"
                    "- Crear borrador de correo: [ACCION: CREAR_BORRADOR|correo;;asunto;;cuerpo]\n"
                    "- Crear un documento de ARCHIVO en la carpeta de documentos de Jarvis (sirve para .txt, .md, .csv, .docx o .pdf); el nombre puede incluir subcarpeta: [ACCION: CREAR_DOCUMENTO|nombre.txt;;contenido completo del documento]. Usa esto (NO 'NOTA') siempre que el usuario pida crear/guardar un archivo, un .txt, un documento, una receta, etc.\n"
                    "- Activar dictado (escribir lo que dices): [ACCION: DICTADO_ON] / desactivar: [ACCION: DICTADO_OFF]\n"
                    "- Buscar en Brave: [ACCION: BUSCAR|consulta] o con plataforma: [ACCION: BUSCAR|youtube:consulta], [ACCION: BUSCAR|google:consulta], [ACCION: BUSCAR|spotify:consulta]\n"
                    "- Reproducir video en YouTube: [ACCION: REPRODUCIR_VIDEO|consulta] (primer resultado) o [ACCION: REPRODUCIR_VIDEO|consulta::2] (segundo resultado)\n"
                    "- Grabar reunión: [ACCION: GRABAR_REUNION] / Terminar y resumir: [ACCION: TERMINAR_REUNION]\n"
                    "- Crear presentación PowerPoint desde un archivo .md (puedes indicar la ruta y, opcionalmente, un límite de diapositivas): [ACCION: CREAR_PRESENTACION|ruta_del.md] o [ACCION: CREAR_PRESENTACION|ruta_del.md;30]. Si el usuario menciona un .md concreto ('el que acabas de crear', 'usa presentacion_bot_pagos_bancolombia.md', etc.), pasa su ruta o su nombre de archivo; si no indica ninguno, pasa la acción sin parámetro y se usará el .md más reciente de la carpeta presentaciones: [ACCION: CREAR_PRESENTACION]\n"
                    "- Generar documento de preventa (copia los requerimientos al portapapeles primero): [ACCION: GENERAR_PREVENTA|propuesta], [ACCION: GENERAR_PREVENTA|requisitos], [ACCION: GENERAR_PREVENTA|historias], [ACCION: GENERAR_PREVENTA|glosario], [ACCION: GENERAR_PREVENTA|resumen], [ACCION: GENERAR_PREVENTA|estimacion]\n"
                    "- Guardar una regla permanente que el usuario pida recordar siempre (p. ej. 'recuerda que...', 'de ahora en adelante...', 'a partir de ahora...'): [ACCION: RECORDAR_REGLA|texto de la regla]\n"
                    "- Mostrar las reglas permanentes guardadas: [ACCION: LEER_REGLAS]\n"
                    "\n"
                    "Las REGLAS PERMANENTES DEL USUARIO que aparezcan más abajo son instrucciones fijas: cúmplelas en TODAS tus respuestas y acciones (incluida la creación de tareas/Work Items), salvo que el usuario indique explícitamente lo contrario.\n"
                    "\n"
                    "CUANDO EL USUARIO PIDA ALGO QUE REQUIERA LEER DATOS (resumir portapapeles, explicar error, leer notas/correos, generar commit, buscar archivos, ejecutar terminal), responde SOLO con la acción [ACCION: ...] sin texto adicional."
                )
            }
        ]

        # Guardamos el prompt base para poder regenerarlo con las reglas actuales
        self._system_base = self.historial[0]["content"]
        self._actualizar_sistema()

    def _prompt_reglas(self):
        """Devuelve el bloque de reglas permanentes del usuario, si existe."""
        try:
            if os.path.exists(self.RUTA_REGLAS):
                with open(self.RUTA_REGLAS, "r", encoding="utf-8") as f:
                    contenido = f.read().strip()
                if contenido:
                    return ("\n\nREGLAS PERMANENTES DEL USUARIO (cúmplelas SIEMPRE, "
                            "tienen prioridad salvo que el usuario indique lo contrario):\n"
                            + contenido)
        except Exception as e:
            print(f"No se pudieron cargar las reglas permanentes: {e}")
        return ""

    def _actualizar_sistema(self):
        """Regenera el mensaje de sistema incluyendo las reglas permanentes actuales."""
        if self.historial and self.historial[0].get("role") == "system":
            self.historial[0]["content"] = self._system_base + self._prompt_reglas()

    def _cargar_api_key(self):
        # Prioridad 1: variable de entorno (no se guarda en archivos versionables)
        api_key_env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key_env:
            return api_key_env

        # Prioridad 2: archivo de configuración local
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("api_key", "")
            except Exception as e:
                print(f"Error cargando configuración: {e}")
        return ""

    def procesar_mensaje(self, mensaje_usuario):
        if not self.client:
            self.api_key = self._cargar_api_key()
            if self.api_key:
                self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            else:
                return "Configura tu API Key.", None

        self._actualizar_sistema()  # refresca las reglas permanentes antes de responder
        self.historial.append({"role": "user", "content": mensaje_usuario})
        self._recortar_historial()

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=self.historial,
                stream=False
            )

            respuesta_full = response.choices[0].message.content
            self.historial.append({"role": "assistant", "content": respuesta_full})

            comando_accion = None
            respuesta_texto = respuesta_full

            if "[ACCION:" in respuesta_full:
                partes = respuesta_full.split("[ACCION:")
                respuesta_texto = partes[0].strip()
                comando_accion = partes[1].split("]")[0].strip()

            return respuesta_texto, comando_accion

        except Exception as e:
            return f"Error de conexión: {str(e)}", None

    def _recortar_historial(self):
        """Mantiene el mensaje de sistema y los últimos mensajes dentro del límite."""
        if len(self.historial) <= self.MAX_MENSAJES_HISTORIAL:
            return

        sistema = self.historial[0] if self.historial[0]["role"] == "system" else None
        margen = self.MAX_MENSAJES_HISTORIAL - (1 if sistema else 0)
        self.historial = ([sistema] if sistema else []) + self.historial[-margen:]

    def limpiar_historial(self):
        self.historial = [self.historial[0]]

    def analizar(self, contexto):
        """Envía un contexto (datos recopilados por el sistema) para que el asistente lo procese."""
        if not self.client:
            return "Configura tu API Key."
        texto, _ = self.procesar_mensaje(
            "Responde de forma breve y clara en español (máximo 3 frases) a lo siguiente:\n\n" + str(contexto)
        )
        return texto