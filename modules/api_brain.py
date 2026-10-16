import json
import os
import re
from openai import OpenAI

from modules import rutas
from modules.sharepoint import SharePoint

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
        self.on_aviso = None       # (texto): cuenta lo que va haciendo (chat)
        
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
                    "- Clasificar archivos de SharePoint/OneDrive según una regla (usa tu sesión de Brave, sin Graph): [ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;regla de clasificación]. Basta con la carpeta de arriba: busca también DENTRO de las subcarpetas (entra en la carpeta de cada cliente y clasifica los documentos que encuentre dentro), así que no hace falta la URL de la carpeta exacta. Si destino y origen son el MISMO sitio, los mueve; si son sitios distintos (por ejemplo, una biblioteca de equipo y tu OneDrive), los COPIA y los originales se quedan donde están, así que no digas que no se puede. Si encuentra muchos archivos primero te enseña qué haría SIN tocar nada: pregúntale al usuario y, si confirma, repite la acción añadiendo ';;confirmar' al final ([ACCION: CLASIFICAR_ARCHIVOS|origen;;destino;;regla;;confirmar]). También vale la URL del sitio a secas (por ejemplo, 'https://empresa-my.sharepoint.com/' = la unidad del usuario): el asistente usa su biblioteca de documentos. De esas carpetas solo pasan los documentos de oficina (ppt, pptx, doc y docx): los vídeos (y fotos, zip o PDF) no se listan, no se bajan y no se mueven, así que si el usuario pregunta por ellos dile en qué carpeta están y que esos no se tocan. La regla puede pedir UNO o DOS niveles de carpeta (rama y subrama, por ejemplo 'una rama por tipo de entregable y una subrama por el tipo de dato: Assessment/Data'): escribe la regla tal cual, con los dos niveles, y el asistente crea las dos carpetas (la madre antes que la hija). Antes de clasificar, el asistente mira qué carpetas tiene ya el destino (hasta dos niveles) y le pasa esa lista a la IA: los documentos que encajan se meten en las carpetas que YA existen, en vez de crear otras parecidas; si el destino tiene más carpetas de las que caben, te lo dice. Y si la regla deja archivos fuera (no son propuestas, hay que revisarlos, no se deben tocar), el destino de esos es 'omitir' y con eso no se mueven, no se copian y ni se bajan: no los mandes a 'Otros' ni les busques carpeta\n"
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

    # Cuántos archivos van en cada consulta a la IA. La respuesta tiene tope de
    # tokens, así que con muchos archivos se pregunta por tandas y se juntan los
    # planes: si no, los últimos acabarían todos en 'Otros'.
    TANDA_ARCHIVOS = 30
    # Cuántas carpetas del destino se le enseñan a la IA para que use las que ya
    # existen ('Assessment/Data') en vez de inventarse otras parecidas. Una
    # biblioteca de verdad tiene cientos: se corta y se dice en el prompt.
    MAXIMO_CARPETAS_PROMPT = 150

    def _aviso(self, texto):
        """Cuenta por el chat qué está haciendo la IA (si hay quien escuche).

        Clasificar una carpeta entera son varias consultas seguidas: decir por
        cuál va evita que parezca que se ha colgado.
        """
        if not texto:
            return
        aviso = self.on_aviso
        if not aviso:
            return
        try:
            aviso(texto)
        except Exception as e:
            # Un aviso fallido no puede tumbar la clasificación en marcha.
            print(f"Error avisando del progreso: {e}")

    def clasificar_archivos(self, nombres, regla, carpetas=None, pistas=None):
        """Devuelve un plan [(nombre, subcarpeta)] para clasificar archivos según 'regla'.

        Llama a la IA pidiendo una línea por archivo con el formato
        'nombre|rama/subrama' (la regla puede pedir uno o dos niveles). Los
        nombres pueden traer la carpeta de la que sale el archivo
        ('AXA/acta.docx') cuando se buscó dentro de las subcarpetas; se le pide
        que los copie tal cual, porque con ellos se encuentra el archivo de
        verdad.

        ``carpetas`` son las **carpetas que ya existen en el destino**
        (``SharePoint.catalogo_carpetas``: 'Assessment', 'Assessment/Data'...).
        Se le enseñan para que meta cada archivo en una de esas cuando encaje,
        en vez de inventarse una nueva que se le parezca ('Assessment/Data
        Analysis' al lado de la 'Assessment/Data' que ya está): sin esto la IA
        no tiene forma de saber qué hay hecho al otro lado.

        ``pistas`` es lo que se sabe del CONTENIDO de cada archivo
        (``modules.pistas``: el título y las primeras líneas). Es lo que permite
        clasificar un archivo cuyo nombre no dice nada ('PROPUESTA COMERCIAL
        bfddfa36 RFI...'): sin eso la IA solo puede adivinar o rendirse.

        Tres finales posibles para cada archivo:

        - Una carpeta: es lo normal, y es lo que se espera.
        - ``OMITIR``: la regla manda no tocar ese archivo (una transcripción, una
          Consultoría, algo por revisar). No se pasa, y **tampoco** se baja.
        - ``DUDOSO`` ('sin clasificar'): la IA no supo a qué categoría va con lo
          que sabe (ni el nombre ni la pista). Tampoco se pasa, pero eso sí tiene
          arreglo: quien llama puede leerle el documento y volver a preguntar.
        - El que la IA no contesta queda también como ``OMITIR``: antes se
          mandaba a 'Otros' y acababa copiado (y bajado a tu PC, si era grande)
          en un cajón que no es de nadie.

        Y si la IA deja sin carpeta a TODOS (lo hacía cuando dudaba: contestaba
        'omitir' hasta con 'Propuesta Arquitectura Cloud'), se le vuelve a
        preguntar una vez más, diciéndole a la cara que eso no es clasificar. Si
        la regla pide justo eso (dejar archivos fuera o dejarlos tal cual), no se
        insiste: el plan es el que la regla pidió.

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
        plan = self._plan_por_tandas(nombres, regla, carpetas, pistas)
        if plan and self._no_clasifico_nada(plan, regla):
            self._aviso("La IA no le puso carpeta a ninguno: se lo vuelvo a "
                        "pedir, a ver si esta vez clasifica.")
            insistido = self._plan_por_tandas(nombres, regla, carpetas, pistas,
                                              insistir=True)
            if insistido is not None:
                plan = insistido
        return plan

    def _plan_por_tandas(self, nombres, regla, carpetas=None, pistas=None,
                         insistir=False):
        """Pide el plan por tandas y las junta. None si alguna llamada falla.

        Se pregunta por tandas (``TANDA_ARCHIVOS``) porque la respuesta tiene
        tope de tokens: con muchos archivos en una sola consulta los últimos
        llegarían sin contestar.
        """
        plan = []
        for inicio in range(0, len(nombres), self.TANDA_ARCHIVOS):
            tanda = list(nombres[inicio:inicio + self.TANDA_ARCHIVOS])
            if not insistir:
                self._aviso(f"Clasificando con la IA: {inicio + len(tanda)} de "
                            f"{len(nombres)} archivo(s)...")
            asignadas = self._clasificar_tanda(tanda, regla, carpetas, pistas,
                                               insistir=insistir)
            if asignadas is None:
                return None
            plan += [(n, asignadas.get(n, SharePoint.OMITIR)) for n in tanda]
        return plan

    @staticmethod
    def _no_clasifico_nada(plan, regla=""):
        """¿Esa vuelta no llevó a NINGÚN archivo a una carpeta?

        Pasa cuando la IA se refugia en 'omitir' (o manda todo a la raíz) en vez
        de clasificar: con eso el plan no mueve nada y el usuario se queda sin
        entender por qué. Dos excepciones, que no son fallos:

        - Si la regla dice que hay archivos que no se tocan o que se quedan tal
          cual, ese plan es exactamente el que se pidió.
        - Si contestó 'sin clasificar' a todos, es un "no sé" honrado (una
          propuesta con nombre de hash y sin nada con lo que decidir): insistir
          sería empujarla a que se lo invente.
        """
        if not plan:
            return False
        if (SharePoint.regla_deja_fuera(regla)
                or SharePoint.regla_pide_la_raiz(regla)):
            return False
        if all(SharePoint.es_dudoso(subcarpeta) for _, subcarpeta in plan):
            return False
        return all(SharePoint.es_omitir(subcarpeta) or not (subcarpeta or "").strip()
                   for _, subcarpeta in plan)

    # Cómo se pide el plan a la IA: una línea por archivo y nada más (ni tablas,
    # ni listas, ni comentarios). Aun así el modelo responde como quiere, para eso
    # está ``_parsear_clasificacion``: entenderle es lo que evita que el plan
    # llegue vacío y que TODOS los archivos acaben en el mismo sitio.
    SISTEMA_CLASIFICACION = (
        "Eres un clasificador de archivos. Respondes SOLO con una línea por "
        "archivo, en el formato 'nombre_archivo|destino', sin tablas, sin "
        "listas, sin numeración y sin comentarios. Copias los nombres tal cual "
        "te llegan. Das carpeta de destino a CADA archivo: si te doy las "
        "carpetas que YA EXISTEN en el destino, usas una de esas cuando el "
        "archivo encaje, y si no, la categoría que pida la regla (se creará si "
        "no está). 'omitir' y 'raíz' son solo para lo que la regla mande "
        "expresamente: si dudas de dónde va un archivo, eliges la carpeta que "
        "mejor encaje y, si de verdad no hay forma de saberlo, escribes 'sin "
        "clasificar'. Nunca pones 'omitir' ni 'raíz' por duda."
    )

    def _prompt_clasificacion(self, nombres, regla, carpetas=None, pistas=None,
                              insistir=False):
        """El texto que se le manda a la IA para que reparta los archivos.

        ``carpetas`` son las que ya existen en el destino: van en su propia
        sección, porque saber qué está hecho es lo que evita que se invente
        carpetas nuevas al lado de las que ya hay.

        ``pistas`` es lo que se sabe del contenido de cada archivo (``pistas``):
        un archivo con nombre de hash no se puede clasificar sin mirarlo por
        dentro, así que se le enseña aparte, avisándole de que el nombre que
        tiene que copiar es el de la lista de ARCHIVOS.

        ``insistir`` es para la segunda vuelta: cuando la IA dejó sin carpeta a
        todos los archivos que se le dieron, se le dice a la cara.
        """
        prompt = (
            "Vas a clasificar archivos según la regla del usuario. Responde "
            "SOLO con una línea por archivo, en este formato exacto:\n"
            "nombre_del_archivo|destino\n"
            "El destino puede tener dos niveles separados por '/', como los pida "
            "la regla (por ejemplo: 'Assessment/Data'). Si la regla solo pide un "
            "nivel, escribe un solo nivel.\n"
            "Cada archivo lleva su carpeta: la categoría que pida la regla (si "
            "nombra categorías -'arquitectura, ciberseguridad, data, qa...'- el "
            "destino es UNA de esas, tal cual y sin cambiarle la ortografía) o "
            "una de las que YA EXISTEN en el destino, la que mejor encaje. Una "
            "categoría que no exista se crea, así que no es excusa para dejarlo "
            "sin carpeta.\n"
            "Escribe 'sin clasificar' como destino SOLO si, con lo que sabes del "
            "archivo (su nombre y, si te la doy, la pista de lo que dice por "
            "dentro), no hay forma de saber a qué categoría va: "
            "'nombre_del_archivo|sin clasificar'. Ese archivo se queda sin "
            "clasificar de verdad, así que no lo uses para no pensar.\n"
            "Escribe 'omitir' como destino SOLO si la REGLA manda NO tocar ese "
            "archivo ('las actas no se tocan', 'las transcripciones se omiten', "
            "'lo que no sea propuesta se queda donde está'): "
            "'nombre_del_archivo|omitir'. 'omitir' NO es para los que no sabes "
            "dónde poner.\n"
            "Escribe 'raíz' como destino SOLO si la REGLA manda dejar ese archivo "
            "en la carpeta de destino tal cual, sin subcarpeta. Si la regla pide "
            "clasificar, todos los archivos llevan subcarpeta: 'raíz' no vale.\n"
            "Copia el nombre EXACTAMENTE como te lo doy. Si trae una carpeta "
            "delante (por ejemplo 'AXA/acta.docx'), se copia igual: esa carpeta "
            "es de donde SALE el archivo, no el destino.\n"
            "No uses tablas, ni listas, ni numeración, ni bloques de código. No "
            "añadas títulos, ni totales, ni comentarios: una línea por archivo y "
            "nada más.\n\n"
        )
        if insistir:
            prompt += (
                "OJO: en la respuesta anterior no le diste carpeta a NINGUNO de "
                "estos archivos, y eso no es clasificar. Da a cada uno la carpeta "
                "que le toque (de las categorías de la regla o de las que ya "
                "existen) y usa 'sin clasificar' solo para los que de verdad no "
                "se puedan saber.\n\n"
            )
        prompt += self._seccion_carpetas(carpetas)
        prompt += self._seccion_pistas(pistas)
        return (prompt
                + "REGLA:\n" + str(regla or "") + "\n\n"
                + "ARCHIVOS:\n" + "\n".join(nombres))

    def _seccion_pistas(self, pistas):
        """La parte del prompt con lo que se sabe del CONTENIDO de cada archivo.

        Cada pista va con el nombre del archivo delante (entre corchetes) y con
        el aviso de que eso es la pista, no el nombre: los nombres que hay que
        copiar en la respuesta son los de la lista de ARCHIVOS, que son con los
        que después se encuentra el archivo de verdad.
        """
        lineas = [f"- [{nombre}] {pista}"
                  for nombre, pista in (pistas or {}).items()
                  if " ".join(str(pista or "").split())]
        if not lineas:
            return ""
        return (
            "LO QUE DICE CADA DOCUMENTO POR DENTRO (su título y sus primeras "
            "líneas, leídos del propio archivo; sirve para saber de qué va "
            "cuando el nombre no lo dice):\n" + "\n".join(lineas) + "\n"
            "De esto solo sacas de qué va el documento y a qué categoría "
            "pertenece. El nombre que copias es el de la lista de ARCHIVOS, tal "
            "cual, y no repitas estas pistas en tu respuesta.\n\n"
        )

    def _seccion_carpetas(self, carpetas):
        """La parte del prompt donde se le enseñan las carpetas que ya existen.

        Cada carpeta va como ruta relativa al destino ('Assessment/Data'), tal
        como se espera en la respuesta. Si hay más de las que caben
        (``MAXIMO_CARPETAS_PROMPT``) se cortan y se dice cuántas faltan: mejor
        un prompt honesto que uno enorme con 500 nombres.
        """
        nombres = [str(c).strip().strip("/") for c in carpetas or ()]
        nombres = [n for n in nombres if n]
        if not nombres:
            return ""
        recorte = max(1, self.MAXIMO_CARPETAS_PROMPT)
        restantes = len(nombres) - recorte
        listado = "\n".join(nombres[:recorte])
        if restantes > 0:
            listado += (f"\n… y {restantes} carpeta(s) más con el mismo estilo "
                        "(si ninguna de las de arriba encaja, usa una de esas "
                        "formas).")
        return (
            "CARPETAS QUE YA EXISTEN EN EL DESTINO (son las que ya están "
            "hechas):\n" + listado + "\n"
            "Si un archivo encaja en una de esas carpetas, escribe su destino "
            "EXACTAMENTE como aparece aquí (mismos niveles, misma ortografía: "
            "'Assessment/Data', no 'Assessment/data'). NO propongas una carpeta "
            "nueva si ya existe una que sirva. Solo si ninguna encaja, escribe "
            "una nueva con el mismo estilo y como mucho dos niveles.\n\n"
        )

    def _clasificar_tanda(self, nombres, regla, carpetas=None, pistas=None,
                          insistir=False):
        """Pregunta a la IA por un grupo de archivos. None si la llamada falla."""
        prompt = self._prompt_clasificacion(nombres, regla, carpetas, pistas,
                                            insistir)
        try:
            respuesta = self.client.chat.completions.create(
                model=self.MODELO,
                messages=[
                    {"role": "system", "content": self.SISTEMA_CLASIFICACION},
                    {"role": "user", "content": prompt},
                ],
                # Con dos niveles ('Rama/Subrama') las líneas son más largas:
                # si el tope se queda corto, la mitad del plan no llega.
                max_tokens=300 + 60 * len(nombres), temperature=0, stream=False,
            )
            texto = respuesta.choices[0].message.content
        except Exception as e:
            print(f"Error clasificando archivos con la IA: {e}")
            return None
        return self._parsear_clasificacion(texto, nombres)

    # Lo que la IA pone delante de cada línea: viñetas, numeración y las barras de
    # una tabla de Markdown ('| 1. **acta.docx** | Assessment |').
    RE_ADORNOS_LINEA = re.compile(r"^\s*(?:[-*•·>|]+\s*|\d+\s*[.)]\s*)+")
    # Adornos con que envuelve una celda ('**Assessment**', '`Data`', '[REVISAR]').
    RE_ADORNOS_CELDA = re.compile(r"[*`\"'\[\]{}<>]+")
    # Celdas con las que dice "aquí no hay nada" (lo típico: sin subrama).
    SIN_DATO = ("", "-", "--", "---", "—", "–", "n/a", "na", "ninguna",
                "ninguno", "sin subrama", "sin dato", "no aplica", "?", "??")
    # Y las que significan "a la carpeta de destino tal cual, sin subcarpeta".
    A_LA_RAIZ = (".", "/", "(raíz)", "(raiz)", "raíz", "raiz",
                 "raíz del destino", "raiz del destino", "directo", "(directo)")
    # Y las que significan "con lo que sé (el nombre y, si la hay, la pista de lo
    # que dice dentro) no se puede saber a qué categoría va". Se miran ANTES que
    # 'omitir' (que también reconoce 'sin clasificar'), porque no es lo mismo "no
    # lo toques" que "no sé": el 'no sé' tiene arreglo (``SystemActions`` le lee
    # el documento y vuelve a preguntar) y el plan lo dice con ``DUDOSO``. Lo que
    # siga así no se mueve: mejor quieto que en la carpeta equivocada.
    SIN_CLASIFICAR = ("sin clasificar", "no se sabe", "no sé", "no lo sé",
                      "no se puede saber", "no se puede clasificar", "duda",
                      "desconocido", "sin categoria", "sin categoría")
    # Cabeceras de tabla: no son archivos ('| Archivo | Rama | Subrama |').
    PALABRAS_CABECERA = ("archivo", "archivos", "nombre", "nombres", "documento",
                         "documentos", "file", "filename", "name", "rama", "ramas",
                         "subrama", "subramas", "carpeta", "carpetas", "ruta",
                         "destino", "nivel", "niveles", "clasificacion",
                         "clasificación")

    @classmethod
    def _limpiar_celda(cls, celda):
        """Quita de una celda los adornos de la IA ('**Data**' -> 'Data')."""
        return cls.RE_ADORNOS_CELDA.sub("", celda or "").strip()

    @classmethod
    def _es_cabecera(cls, nombre, nombres_bajo):
        """¿Esa línea es la cabecera de una tabla y no un archivo?"""
        limpio = cls._limpiar_celda(nombre).lower()
        return limpio not in nombres_bajo and limpio in cls.PALABRAS_CABECERA

    @staticmethod
    def _buscar_nombre(nombre, nombres, nombres_bajo):
        """El archivo de verdad al que se refiere la IA con ese nombre.

        La IA a veces acorta ('AXA/2024/acta.docx' -> 'acta.docx'): se acepta
        solo si ese nombre identifica a UN archivo. Con varios 'acta.docx' en
        carpetas distintas, mejor no adivinar.
        """
        clave = nombre.lower()
        objetivo = nombres_bajo.get(clave)
        if objetivo is not None:
            return objetivo
        candidatos = [real for real in nombres
                      if real.lower().endswith("/" + clave)]
        if len(candidatos) == 1:
            return candidatos[0]
        for real in nombres:
            if real.lower() == clave or real.lower().startswith(clave):
                return real
        return None

    @classmethod
    def _destino_de(cls, celdas):
        """La subcarpeta de destino a partir de las columnas de la respuesta.

        Dos columnas de destino son rama y subrama ('Assessment|Data' ->
        'Assessment/Data'). Si la IA manda no tocar el archivo se devuelve
        ``SharePoint.OMITIR``; si dice que no se puede saber a qué categoría va
        ('sin clasificar'), ``SharePoint.DUDOSO`` (que no es lo mismo: ese
        archivo todavía se puede clasificar leyéndolo); y si no dice ninguna
        carpeta utilizable, ``OMITIR`` (devolver '' lo mandaría a la raíz del
        destino: el 'todo al mismo sitio' que se quiere evitar).
        """
        for celda in celdas:
            limpio = cls._limpiar_celda(celda)
            if " ".join(limpio.lower().split()) in cls.SIN_CLASIFICAR:
                return SharePoint.DUDOSO
        for celda in celdas:
            if SharePoint.es_omitir(cls._limpiar_celda(celda)):
                return SharePoint.OMITIR
        niveles = []
        for celda in celdas:
            limpio = cls._limpiar_celda(celda)
            bajo = " ".join(limpio.lower().split())
            if bajo in cls.A_LA_RAIZ:
                return ""  # a propósito: la carpeta de destino, sin subcarpeta
            if bajo in cls.SIN_DATO:
                continue
            niveles.append(limpio)
        return "/".join(niveles) if niveles else SharePoint.OMITIR

    @classmethod
    def _parsear_clasificacion(cls, texto, nombres):
        """Convierte lo que contestó la IA en {nombre real: subcarpeta}.

        La IA responde como quiere: lo mismo escribe 'nombre|destino' (lo que se
        le pide) que una tabla de Markdown con rama y subrama ('| acta.docx |
        Assessment | Data |') o una lista numerada con '->'. Se aceptan todas,
        porque una respuesta que no se entiende deja el plan vacío y acaba con
        TODOS los archivos copiados en el mismo sitio: justo lo contrario de
        clasificar.

        Los que la IA manda no tocar llegan con ``SharePoint.OMITIR`` (o con la
        palabra que haya usado: 'revisar', 'se omite'...), y no se pasan. Y los
        que dice que no puede saber llegan con ``SharePoint.DUDOSO``: se quedan
        quietos, pero de esos sí se puede volver a preguntar (leyéndoles el
        documento) antes de darlos por perdidos.
        """
        resultado = {}
        nombres_bajo = {n.lower(): n for n in nombres}
        for linea in (texto or "").splitlines():
            limpia = cls.RE_ADORNOS_LINEA.sub("", linea.strip()).strip()
            limpia = limpia.rstrip("|").strip()
            if not limpia or set(limpia) <= set("|-: "):
                continue  # vacía, o la raya de una tabla de Markdown
            partes = re.split(r"\s*(?:\||->|→|=>|\t)\s*", limpia)
            nombre = cls._limpiar_celda(partes[0])
            celdas = partes[1:]
            if not nombre or not celdas:
                continue  # sin destino no se puede hacer nada con esta línea
            if cls._es_cabecera(nombre, nombres_bajo):
                continue  # '| Archivo | Rama | Subrama |': no es un archivo
            objetivo = cls._buscar_nombre(nombre, nombres, nombres_bajo)
            if objetivo is None or objetivo in resultado:
                continue
            resultado[objetivo] = cls._destino_de(celdas)
        return resultado