import json
import os
import re
from openai import OpenAI

from modules import rutas

class APIBrain:
    MAX_MENSAJES_HISTORIAL = 30  # evita superar el límite de contexto de DeepSeek
    MODELO = "deepseek-chat"
    # Tope de seguridad: el contexto de DeepSeek ronda los 64k tokens (unas 120.000
    # letras), de modo que un texto mayor se recorta antes de enviarlo.
    MAX_CARACTERES_ANALISIS = 120000
    # Mensaje de sistema de los análisis largos (actas, informes): aquí se pide un
    # documento completo en Markdown y no se ejecuta ninguna acción.
    SISTEMA_ANALISIS = (
        "Eres Jarvis, un asistente experto en analizar información y redactar "
        "documentos de trabajo. Escribes en español, en Markdown, con datos concretos "
        "y sin relleno, y te ciñes a la información que se te da: no inventas nombres, "
        "cifras ni fechas. Devuelves SOLO el documento pedido, sin saludos, sin "
        "comentarios y sin comandos [ACCION: ...]."
    )
    # Marca de un comando interno de acción ('[ACCION: ...]') dentro de la respuesta.
    RE_MARCA_ACCION = re.compile(r"\[\s*ACCION\s*:\s*", re.IGNORECASE)
    # Adornos que pueden envolver al comando (backticks, paréntesis, punto final,
    # corchetes y espacios); sirven para saber si el comando cierra el mensaje y
    # para limpiar lo que queda al retirarlo del texto visible.
    RE_ADORNOS_CIERRE = re.compile(r"[\s`.)\]]*")
    ADORNOS_APERTURA = " \t`*->#"
    # Cerca de un bloque de código Markdown (```), donde un comando solo puede ser
    # parte de una explicación: ahí no se ejecuta nada salvo que cierre el mensaje.
    RE_CERCA_CODIGO = re.compile(r"^\s*```")
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
                    "- Listar el contenido de una carpeta (OneDrive incluido): [ACCION: LISTAR_CARPETA|C:\\ruta\\carpeta] (sin ruta se lista la carpeta principal de OneDrive)\n"
                    "- Buscar archivos DENTRO de una carpeta concreta: [ACCION: BUSCAR_EN_CARPETA|C:\\ruta\\carpeta;;nombre]\n"
                    "- Mover archivos entre carpetas: [ACCION: MOVER_ARCHIVOS|C:\\...\\a.txt;C:\\...\\b.pdf;;C:\\...\\destino] (rutas separadas por ';' y, tras ';;', la carpeta destino). Primero enseña qué vas a mover SIN ';;mover'; añade ';;mover' AL FINAL solo cuando el usuario lo confirme: [ACCION: MOVER_ARCHIVOS|origen;;destino;;mover]\n"
                    "- Copiar archivos entre carpetas: [ACCION: COPIAR_ARCHIVOS|C:\\...\\a.txt;;C:\\...\\destino] (misma idea que mover; ';;copiar' para confirmar)\n"
                    "- Clasificar archivos de SharePoint/OneDrive según una regla (usa tu sesión de Brave, sin Graph): [ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;regla de clasificación]\n"
                    "- Leer correos de Outlook: [ACCION: LEER_CORREOS|5] (los numera para que luego puedas responder o mover el que el usuario diga)\n"
                    "- Crear borrador de correo: [ACCION: CREAR_BORRADOR|correo;;asunto;;cuerpo]\n"
                    "- Resumen del correo (criterio opcional: 'hoy', 'no leídos', un número): [ACCION: RESUMEN_CORREOS|hoy], [ACCION: RESUMEN_CORREOS|no leídos], [ACCION: RESUMEN_CORREOS|10]\n"
                    "- Sacar pendientes y compromisos del correo: [ACCION: CORREO_PENDIENTES|10]\n"
                    "- Buscar correos: [ACCION: BUSCAR_CORREOS|factura acme]\n"
                    "- Leer un correo completo: [ACCION: LEER_CORREO|3] (el 3 es el número de la lista que acabas de mostrar; también vale parte del asunto o del remitente)\n"
                    "- Responder un correo: [ACCION: RESPONDER_CORREO|3;;texto de la respuesta]. Añade ';;enviar' AL FINAL SOLO si el usuario dice explícitamente que lo mandes ('envíalo', 'mándalo', 'respóndele'); si no, la respuesta queda como BORRADOR: [ACCION: RESPONDER_CORREO|3;;texto de la respuesta;;enviar]\n"
                    "- Enviar el borrador que dejaste preparado: [ACCION: ENVIAR_BORRADOR] (con asunto o número si hay varios)\n"
                    "- Etiquetar un correo (categorías de Outlook; con '-' delante las quita): [ACCION: ETIQUETAR_CORREO|3;;Propuesta], [ACCION: ETIQUETAR_CORREO|3;;-Propuesta]\n"
                    "- Archivar o mover un correo a una carpeta: [ACCION: ARCHIVAR_CORREO|3] (carpeta de archivo) o [ACCION: ARCHIVAR_CORREO|3;;Proyectos]\n"
                    "- Marcar leído o no leído: [ACCION: MARCAR_CORREO|3], [ACCION: MARCAR_CORREO|3;;no leído]\n"
                    "- Eliminar un correo (va a Elementos eliminados, se puede recuperar): [ACCION: ELIMINAR_CORREO|3]\n"
                    "- Crear un documento de ARCHIVO en la carpeta de documentos de Jarvis (sirve para .txt, .md, .csv, .docx o .pdf); el nombre puede incluir subcarpeta: [ACCION: CREAR_DOCUMENTO|nombre.txt;;contenido completo del documento]. Usa esto (NO 'NOTA') siempre que el usuario pida crear/guardar un archivo, un .txt, un documento, una receta, etc.\n"
                    "- Activar dictado (escribir lo que dices): [ACCION: DICTADO_ON] / desactivar: [ACCION: DICTADO_OFF]\n"
                    "- Buscar en Brave: [ACCION: BUSCAR|consulta] o con plataforma: [ACCION: BUSCAR|youtube:consulta], [ACCION: BUSCAR|google:consulta], [ACCION: BUSCAR|spotify:consulta]\n"
                    "- Reproducir video en YouTube: [ACCION: REPRODUCIR_VIDEO|consulta] (primer resultado) o [ACCION: REPRODUCIR_VIDEO|consulta::2] (segundo resultado)\n"
                    "- Grabar reunión: [ACCION: GRABAR_REUNION] / Terminar, transcribir y generar el acta: [ACCION: TERMINAR_REUNION]\n"
                    "- Ver las actas de reunión guardadas: [ACCION: REUNIONES|8]\n"
                    "- Leer o resumir un acta guardada: [ACCION: LEER_ACTA|1] (el 1 es el número del listado de REUNIONES; también vale parte del título)\n"
                    "- Rehacer el acta de una reunión a partir de su transcripción: [ACCION: REHACER_ACTA|1]\n"
                    "- Saber quiénes asistieron a una reunión (del acta o de la invitación del calendario): [ACCION: ASISTENTES_REUNION|1] o [ACCION: ASISTENTES_REUNION]\n"
                    "- Preparar el correo del acta para los asistentes: [ACCION: ENVIAR_ACTA] (a los asistentes del acta) o [ACCION: ENVIAR_ACTA|ana@empresa.com;luis@empresa.com;;1] (correos separados por ';' y, opcionalmente, el número del acta; si solo hay un número, se entiende que es el acta: [ACCION: ENVIAR_ACTA|2]). Añade ';;enviar' AL FINAL SOLO si el usuario pide explícitamente que lo mandes: [ACCION: ENVIAR_ACTA;;enviar]. Si no hay asistentes conocidos, pide los correos en vez de inventarlos.\n"
                    "- Agenda previa de las próximas reuniones del calendario: [ACCION: AGENDA_REUNION] o [ACCION: AGENDA_REUNION|3] (próximos 3 días) o [ACCION: AGENDA_REUNION|nombre de la reunión]\n"
                    "- Llenar la matriz de la nube con los datos copiados en el portapapeles (Excel en OneDrive/SharePoint + Azure DevOps): [ACCION: MATRIZ_NUBE] (solo Excel: [ACCION: MATRIZ_EXCEL]; solo Azure DevOps: [ACCION: MATRIZ_AZURE])\n"
                    "- Crear presentación PowerPoint desde un archivo .md (puedes indicar la ruta y, opcionalmente, un límite de diapositivas): [ACCION: CREAR_PRESENTACION|ruta_del.md] o [ACCION: CREAR_PRESENTACION|ruta_del.md;30]. Si el usuario menciona un .md concreto ('el que acabas de crear', 'usa presentacion_bot_pagos_bancolombia.md', etc.), pasa su ruta o su nombre de archivo; si no indica ninguno, pasa la acción sin parámetro y se usará el .md más reciente de la carpeta presentaciones: [ACCION: CREAR_PRESENTACION]\n"
                    "- Generar documento de preventa (copia los requerimientos al portapapeles primero): [ACCION: GENERAR_PREVENTA|propuesta], [ACCION: GENERAR_PREVENTA|requisitos], [ACCION: GENERAR_PREVENTA|historias], [ACCION: GENERAR_PREVENTA|glosario], [ACCION: GENERAR_PREVENTA|resumen], [ACCION: GENERAR_PREVENTA|estimacion]\n"
                    "- Guardar una regla permanente que el usuario pida recordar siempre (p. ej. 'recuerda que...', 'de ahora en adelante...', 'a partir de ahora...'): [ACCION: RECORDAR_REGLA|texto de la regla]\n"
                    "- Mostrar las reglas permanentes guardadas: [ACCION: LEER_REGLAS]\n"
                    "\n"
                    "Las REGLAS PERMANENTES DEL USUARIO que aparezcan más abajo son instrucciones fijas: cúmplelas en TODAS tus respuestas y acciones (incluida la creación de tareas/Work Items), salvo que el usuario indique explícitamente lo contrario.\n"
                    "\n"
                    "CUANDO EL USUARIO PIDA ALGO QUE REQUIERA LEER DATOS (resumir portapapeles, explicar error, leer notas/correos, generar commit, buscar archivos, ejecutar terminal), responde SOLO con la acción [ACCION: ...] sin texto adicional.\n"
                    "\n"
                    "EL FORMATO [ACCION: ...] ES INTERNO: sirve para ejecutar una acción de verdad. Escribe el comando "
                    "únicamente cuando quieras ejecutarla y siempre como última línea del mensaje. Nunca lo incluyas en "
                    "explicaciones, ejemplos, listas ni bloques de código: si describes lo que puedes hacer, explícalo "
                    "con palabras (por ejemplo 'puedo abrir Brave, buscar en él y reproducir vídeos') sin escribir el comando.\n"
                    "\n"
                    "SEGURIDAD DEL CORREO: no envíes ningún correo (ni con ';;enviar' en RESPONDER_CORREO "
                    "o ENVIAR_ACTA, ni con ENVIAR_BORRADOR) ni elimines nada (ELIMINAR_CORREO) si el "
                    "usuario no lo pide de forma explícita en su último mensaje; por defecto prepara el "
                    "borrador y pregúntale si lo mandas. Si el usuario dice 'el correo 3', se refiere al "
                    "número 3 del último listado que tú mostraste."
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
                model=self.MODELO,
                messages=self.historial,
                stream=False
            )

            respuesta_full = response.choices[0].message.content or ""
            self.historial.append({"role": "assistant", "content": respuesta_full})

            # El comando de acción se separa solo si CIERRA el mensaje: antes se
            # cortaba el texto en la primera aparición de '[ACCION:', de modo que una
            # respuesta que mencionaba el formato aparecía truncada a media frase.
            return self._extraer_accion(respuesta_full)

        except Exception as e:
            return f"Error de conexión: {str(e)}", None

    def _extraer_accion(self, respuesta):
        """Separa el comando de acción del texto que se muestra en el chat.

        El prompt pide al modelo añadir el comando exacto AL FINAL del mensaje, así
        que se interpreta como orden el último comando que CIERRA la respuesta o, si
        el modelo añadió algo después, el último que ocupa una línea completa. Una
        mención dentro de una frase (una explicación o un ejemplo) es texto normal:
        no se ejecuta y, sobre todo, NO recorta el mensaje.

        Devuelve (texto_visible, comando); el comando es None si el mensaje no lleva
        ninguna orden.
        """
        texto = respuesta or ""
        candidatos = []
        for marca in self.RE_MARCA_ACCION.finditer(texto):
            cuerpo = self._cuerpo_comando(texto, marca.end())
            if not cuerpo:
                continue
            comando, fin = cuerpo
            if not comando:
                continue
            candidatos.append((marca.start(), fin, comando,
                               self._cierra_mensaje(texto, fin),
                               self._linea_propia(texto, marca.start(), fin)
                               and not self._dentro_de_bloque(texto, marca.start())))

        elegido = None
        for candidato in reversed(candidatos):
            if candidato[3]:
                elegido = candidato
                break
        if elegido is None:
            for candidato in reversed(candidatos):
                if candidato[4]:
                    elegido = candidato
                    break
        if elegido is None:
            return texto, None

        inicio, fin, comando = elegido[0], elegido[1], elegido[2]
        # Si el modelo envolvió el comando con backticks, se quitan los dos.
        inicio_visible = inicio - 1 if texto[inicio - 1:inicio] == "`" else inicio
        fin_visible = fin + 1 if texto[fin:fin + 1] == "`" else fin
        visible = texto[:inicio_visible] + texto[fin_visible:]
        # Un bloque de código que solo tenía el comando queda vacío: fuera.
        visible = re.sub(r"```[^\n]*\n\s*```", "", visible)
        visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
        return visible, comando

    @staticmethod
    def _cuerpo_comando(texto, desde):
        """Devuelve (comando, fin) del comando que empieza en 'desde'.

        El contenido de la orden puede ser largo y llevar corchetes dentro (p. ej.
        el Markdown de un documento con '[SUPUESTO]'), así que se toma el último ']'
        que cierra una línea (el que cierra la orden) y, si no hay ninguno, el
        último ']' del mensaje.
        """
        resto = texto[desde:]
        if "]" not in resto:
            return None
        fin_rel = None
        for posicion in range(len(resto) - 1, -1, -1):
            if resto[posicion] == "]" and APIBrain._cierra_linea(texto, desde + posicion):
                fin_rel = posicion
                break
        if fin_rel is None:
            fin_rel = resto.rfind("]")
        comando = resto[:fin_rel].strip()
        return comando, desde + fin_rel + 1

    @staticmethod
    def _cierra_linea(texto, posicion):
        """True si tras el ']' de 'posicion' solo hay adornos hasta el fin de línea."""
        fin_linea = texto.find("\n", posicion + 1)
        if fin_linea == -1:
            fin_linea = len(texto)
        return APIBrain.RE_ADORNOS_CIERRE.fullmatch(
            texto[posicion + 1:fin_linea]) is not None

    @staticmethod
    def _cierra_mensaje(texto, fin):
        """True si después del comando solo quedan adornos y espacios."""
        return APIBrain.RE_ADORNOS_CIERRE.fullmatch(texto[fin:]) is not None

    @staticmethod
    def _linea_propia(texto, inicio, fin):
        """True si el comando ocupa una línea completa (con o sin adornos)."""
        antes = texto.rfind("\n", 0, inicio) + 1
        if texto[antes:inicio].strip(APIBrain.ADORNOS_APERTURA):
            return False
        fin_linea = texto.find("\n", fin)
        if fin_linea == -1:
            fin_linea = len(texto)
        return APIBrain.RE_ADORNOS_CIERRE.fullmatch(texto[fin:fin_linea]) is not None

    @classmethod
    def _dentro_de_bloque(cls, texto, posicion):
        """True si la posición cae dentro de un bloque de código ``` ... ```."""
        dentro = False
        for linea in texto[:posicion].split("\n"):
            if cls.RE_CERCA_CODIGO.match(linea):
                dentro = not dentro
        return dentro

    def _recortar_historial(self):
        """Mantiene el mensaje de sistema y los últimos mensajes dentro del límite."""
        if len(self.historial) <= self.MAX_MENSAJES_HISTORIAL:
            return

        sistema = self.historial[0] if self.historial[0]["role"] == "system" else None
        margen = self.MAX_MENSAJES_HISTORIAL - (1 if sistema else 0)
        self.historial = ([sistema] if sistema else []) + self.historial[-margen:]

    def limpiar_historial(self):
        self.historial = [self.historial[0]]

    def analizar_documento(self, prompt, max_tokens=4000, temperature=0.2):
        """Redacta un documento largo (acta, informe, propuesta) con la IA.

        A diferencia de `procesar_mensaje` (chat con comandos) y de `analizar`
        (respuestas de tres frases), aquí:
        - el texto no entra en el historial de la conversación, así que una
          transcripción larga no ensucia el chat ni lo desborda,
        - no se limita la brevedad y se piden hasta `max_tokens` de salida,
        - no se interpretan comandos de acción, de modo que el Markdown (tablas,
          corchetes) llega intacto.
        Devuelve el texto generado, o "" si no hay IA configurada o falla la llamada.
        """
        if not self.client:
            self.api_key = self._cargar_api_key()
            if self.api_key:
                self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            else:
                print("No hay API Key configurada: no puedo generar el documento.")
                return ""

        contenido = str(prompt or "").strip()
        if not contenido:
            return ""
        if len(contenido) > self.MAX_CARACTERES_ANALISIS:
            print(f"El texto es demasiado largo ({len(contenido)} caracteres): se recorta.")
            contenido = contenido[:self.MAX_CARACTERES_ANALISIS]

        try:
            response = self.client.chat.completions.create(
                model=self.MODELO,
                messages=[
                    {"role": "system", "content": self.SISTEMA_ANALISIS},
                    {"role": "user", "content": contenido},
                ],
                max_tokens=int(max_tokens),
                temperature=float(temperature),
                stream=False,
            )
            return self._limpiar_cerco_markdown(response.choices[0].message.content)
        except Exception as e:
            print(f"Error generando el documento con la IA: {e}")
            return ""

    @staticmethod
    def _limpiar_cerco_markdown(texto):
        """Quita el bloque de código con el que a veces el modelo envuelve el documento."""
        limpio = str(texto or "").strip()
        if not limpio.startswith("```"):
            return limpio
        lineas = limpio.splitlines()
        if lineas and lineas[0].startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].strip().startswith("```"):
            lineas = lineas[:-1]
        return "\n".join(lineas).strip()

    def analizar(self, contexto):
        """Envía un contexto (datos recopilados por el sistema) para que el asistente lo procese."""
        if not self.client:
            return "Configura tu API Key."
        texto, _ = self.procesar_mensaje(
            "Responde de forma breve y clara en español (máximo 3 frases) a lo siguiente:\n\n" + str(contexto)
        )
        return texto

    def clasificar_archivos(self, nombres, regla):
        """Devuelve un plan [(nombre, subcarpeta)] para clasificar archivos según 'regla'.

        Llama a la IA pidiendo una línea por archivo con el formato 'nombre|carpeta'.
        Si no hay API Key o falla la llamada, devuelve None (el llamador decide).
        """
        if not self.client:
            self.api_key = self._cargar_api_key()
            if self.api_key:
                self.client = OpenAI(api_key=self.api_key,
                                     base_url="https://api.deepseek.com")
            else:
                return None
        if not nombres:
            return []
        prompt = (
            "Vas a clasificar archivos en subcarpetas según la regla del usuario. "
            "Responde SOLO con una línea por archivo, en el formato exacto:\n"
            "nombre_del_archivo|carpeta\n"
            "La 'carpeta' es el nombre de la subcarpeta de destino (sin barras). "
            "Si un archivo no encaja en ninguna, usa 'Otros'.\n"
            "No añadas texto, ni títulos, ni listas, ni bloques de código.\n\n"
            "REGLA:\n" + str(regla or "") + "\n\n"
            "ARCHIVOS:\n" + "\n".join(nombres)
        )
        try:
            respuesta = self.client.chat.completions.create(
                model=self.MODELO,
                messages=[
                    {"role": "system",
                     "content": "Eres un clasificador de archivos. Responde SOLO con "
                                "una línea por archivo en el formato 'nombre_archivo|carpeta'."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600, temperature=0, stream=False,
            )
            texto = respuesta.choices[0].message.content
        except Exception as e:
            print(f"Error clasificando archivos con la IA: {e}")
            return None
        asignadas = self._parsear_clasificacion(texto, nombres)
        return [(n, asignadas.get(n, "Otros")) for n in nombres]

    @staticmethod
    def _parsear_clasificacion(texto, nombres):
        """Convierte la salida 'nombre|carpeta' de la IA en {nombre: carpeta}."""
        resultado = {}
        nombres_bajo = {n.lower(): n for n in nombres}
        for linea in (texto or "").splitlines():
            linea = linea.strip().strip("-*•").strip()
            if not linea:
                continue
            partes = re.split(r"\s*(?:\||->|→|\t)\s*", linea, maxsplit=1)
            nombre = partes[0].strip().strip('"`')
            carpeta = partes[1].strip().strip('"`') if len(partes) > 1 else ""
            if not nombre or not carpeta:
                continue
            clave = nombre.lower()
            objetivo = nombres_bajo.get(clave)
            if objetivo is None:
                for real in nombres:
                    if real.lower() == clave or real.lower().startswith(clave):
                        objetivo = real
                        break
            if objetivo is not None and objetivo not in resultado:
                resultado[objetivo] = carpeta
        return resultado