import os
import re
import sys
import json
import webbrowser
import urllib.parse
import time
import threading
import psutil
import pyautogui
from screeninfo import get_monitors
from modules.office_automation import OfficeAutomation
from modules.productivity import ProductivityTools
from modules.dev_tools import DevTools
from modules.outlook_tools import OutlookTools          # noqa: F401  (compatibilidad)
from modules.correo import crear_cliente_correo
from modules.meeting_assistant import MeetingAssistant
from modules.calendario_tools import CalendarioTools
from modules.preventa_tools import PreventaTools
from modules.cloud_matrix import CloudMatrix
from modules.archivos import Explorador
from modules.sharepoint import SharePoint
from modules import navegador_cdp
from modules import rutas

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    AudioUtilities = None

class SystemActions:
    # Mapeo de nombres amigables a nombres de ejecutable de Windows
    PROCESOS_CONOCIDOS = {
        "riot client": ["RiotClientServices.exe", "RiotClientUx.exe"],
        "radio client": ["RiotClientServices.exe", "RiotClientUx.exe"],
        "valorant": ["VALORANT-Win64-Shipping.exe", "VALORANT.exe", "RiotClientServices.exe"],
        "discord": ["Discord.exe"],
        "spotify": ["Spotify.exe"],
        "chrome": ["chrome.exe"],
        "edge": ["msedge.exe"],
        "brave": ["brave.exe"],
        "roblox": ["RobloxPlayerBeta.exe"],
        "visual studio": ["Code.exe", "devenv.exe"],
        "visual studio code": ["Code.exe"],
        "vscode": ["Code.exe"],
        "obs": ["obs64.exe", "obs32.exe"]
    }

    # Plataformas soportadas para búsqueda web
    PLATAFORMAS_BUSQUEDA = {
        "youtube", "yt", "google", "wikipedia", "wiki", "github",
        "spotify", "twitter", "x", "amazon", "stackoverflow", "stack overflow", "reddit"
    }

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self.on_aviso = None       # (texto): cuenta lo que va haciendo (chat)
        self.office_tool = OfficeAutomation()
        self.productivity = ProductivityTools(config_path)
        self.dev = DevTools(config_path)
        self.outlook = crear_cliente_correo(config_path)
        self.meeting = MeetingAssistant(config_path)
        self.calendario = CalendarioTools()
        self.preventa = PreventaTools()
        self.cloud = CloudMatrix(config_path)
        self.archivos = Explorador()
        self.sharepoint = SharePoint()

    def ejecutar_comando(self, comando_str):
        if not comando_str:
            return

        partes = comando_str.split("|")
        accion = partes[0].upper().strip()
        parametro = partes[1].strip() if len(partes) > 1 else None
        # Texto libre: conserva todo lo que va tras el primer '|' (los '|' internos
        # importan: tablas de Markdown en un documento, tuberías en un comando de
        # terminal, etc.). Antes se perdía todo a partir del primer '|'.
        parametro_libre = comando_str.split("|", 1)[1].strip() if len(partes) > 1 else None

        if accion == "ABRIR_APP":
            self.abrir_aplicacion(parametro)
        elif accion == "CERRAR_APP":
            self.cerrar_aplicacion(parametro)
        elif accion == "MINIMIZAR_APP":
            self.minimizar_aplicacion_especifica(parametro)
        elif accion == "ABRIR_SEGUNDO_MONITOR":
            self.abrir_lineups_segundo_monitor(parametro)
        elif accion == "VOLUMEN":
            self.ajustar_volumen(parametro)
        elif accion == "VOLUMEN_APP":
            self.ajustar_volumen_app(parametro)
        elif accion == "SISTEMA":
            self.gestion_ventanas(parametro)
        elif accion == "CLIMA":
            return self.productivity.obtener_clima(parametro)
        elif accion == "BRIEFING":
            return self.productivity.generar_briefing()
        elif accion == "NOTA":
            self.productivity.agregar_nota(parametro_libre or "")
            return None
        elif accion == "LEER_NOTAS":
            return "__CONTEXTO__" + "Lee estas notas en voz alta:\n" + self.productivity.leer_notas()
        elif accion == "BORRAR_NOTAS":
            return self.productivity.borrar_notas()
        elif accion == "RECORDAR_REGLA":
            return self.productivity.agregar_regla(parametro_libre or "")
        elif accion == "LEER_REGLAS":
            reglas = self.productivity.leer_reglas()
            if not reglas:
                return "No hay reglas permanentes guardadas."
            return "Reglas permanentes guardadas:\n" + reglas
        elif accion == "BORRAR_REGLAS":
            return self.productivity.borrar_reglas()
        elif accion == "RESUMIR_PORTAPAPELES":
            texto = self.productivity.leer_portapapeles()
            if not texto.strip():
                return "No hay nada copiado en el portapapeles."
            return "__CONTEXTO__" + "Resume este texto en dos frases:\n\n" + texto
        elif accion == "EXPLICAR_ERROR":
            texto = self.productivity.leer_portapapeles()
            if not texto.strip():
                return "No hay ningún error copiado en el portapapeles."
            return "__CONTEXTO__" + "Explica qué significa este error y cómo solucionarlo:\n\n" + texto
        elif accion == "GENERAR_COMMIT":
            return ("__CONTEXTO__"
                    "Escribe un mensaje de commit para Git en formato Conventional Commits "
                    "(feat:, fix:, docs:, refactor:...). Aquí están los cambios:\n"
                    + self.dev.obtener_contexto_git())
        elif accion == "EJECUTAR_TERMINAL":
            return "__CONTEXTO__" + "Resume el resultado de este comando:\n" + self.dev.ejecutar_comando(parametro_libre or "")
        elif accion == "POMODORO":
            try:
                mins = int(parametro) if (parametro and parametro.isdigit()) else 25
            except Exception:
                mins = 25
            return self.productivity.iniciar_pomodoro(mins)
        elif accion == "DETENER_POMODORO":
            return self.productivity.detener_pomodoro()
        elif accion == "PERFIL":
            return self.productivity.activar_perfil(parametro or "")
        elif accion == "BUSCAR_ARCHIVOS":
            archivos = self.productivity.buscar_archivos(parametro or "")
            if not archivos:
                return f"No encontré archivos que coincidan con '{parametro}'."
            return "__CONTEXTO__" + "Lista brevemente estos archivos encontrados:\n" + "\n".join(archivos)
        elif accion == "LISTAR_CARPETA":
            return self.archivos.listar_texto(parametro or "")
        elif accion == "BUSCAR_EN_CARPETA":
            partes = (parametro_libre or "").split(";;", 1)
            carpeta = partes[0].strip() if partes else ""
            nombre = partes[1].strip() if len(partes) > 1 else ""
            hallazgos = self.archivos.buscar(carpeta, nombre)
            if not hallazgos:
                return (f"No encontré '{nombre or 'archivos'}' dentro de "
                        f"{carpeta or 'esa carpeta'}.")
            return ("__CONTEXTO__"
                    "Estos son los archivos encontrados (di dónde están y, si el "
                    "usuario quiere, propón moverlos o copiarlos a otra carpeta):\n"
                    + "\n".join(hallazgos))
        elif accion == "MOVER_ARCHIVOS":
            partes = (parametro_libre or "").split(";;", 2)
            origen = partes[0].strip() if partes else ""
            destino = partes[1].strip() if len(partes) > 1 else ""
            modo = partes[2].strip() if len(partes) > 2 else ""
            return self.archivos.resumen(
                self.archivos.mover(origen, destino,
                                    confirmado=self._quiere_confirmar(modo)))
        elif accion == "COPIAR_ARCHIVOS":
            partes = (parametro_libre or "").split(";;", 2)
            origen = partes[0].strip() if partes else ""
            destino = partes[1].strip() if len(partes) > 1 else ""
            modo = partes[2].strip() if len(partes) > 2 else ""
            return self.archivos.resumen(
                self.archivos.copiar(origen, destino,
                                     confirmado=self._quiere_confirmar(modo)))
        elif accion == "CLASIFICAR_ARCHIVOS":
            return self._clasificar_archivos(parametro_libre or "")
        elif accion == "LEER_CORREOS":
            return ("__CONTEXTO__"
                    "Resume estos correos recientes, los importantes primero (máximo 6 "
                    "líneas), y dime si hay algo que requiera respuesta o acción:\n"
                    + self.outlook.leer_correos(self._numero_correos(parametro, 8)))
        elif accion == "RESUMEN_CORREOS":
            return ("__CONTEXTO__"
                    "Haz un resumen ejecutivo de este correo: qué es urgente, quién espera "
                    "respuesta y qué se puede ignorar. Termina con una lista corta de "
                    "acciones pendientes (con quién y para cuándo, si se menciona):\n"
                    + self.outlook.resumen(parametro or "",
                                           n=self._numero_correos(parametro, 10)))
        elif accion == "BUSCAR_CORREOS":
            return ("__CONTEXTO__"
                    "Resume qué dicen estos correos sobre la búsqueda del usuario (di "
                    "remitente, fecha y lo esencial de cada uno):\n"
                    + self.outlook.buscar(parametro or "",
                                          n=self._numero_correos(parametro, 10)))
        elif accion == "CORREO_PENDIENTES":
            return ("__CONTEXTO__"
                    "Extrae de estos correos las tareas y compromisos pendientes y devuélvelos "
                    "como lista (tarea, de quién depende y fecha límite si aparece). Si no hay "
                    "ninguno claro, dilo:\n"
                    + self.outlook.resumen(parametro or "",
                                           n=self._numero_correos(parametro, 10)))
        elif accion == "LEER_CORREO":
            return ("__CONTEXTO__"
                    "Resume y explica este correo en pocas frases; si pide algo, dilo:\n"
                    + self.outlook.detalle(parametro_libre or parametro or ""))
        elif accion == "RESPONDER_CORREO":
            # clave;;texto[;;enviar]: el texto puede ser largo y llevar '|' o saltos
            # de línea, así que se usa el parámetro completo troceado por ';;'.
            partes_correo = (parametro_libre or "").split(";;", 2)
            clave = partes_correo[0].strip() if partes_correo else ""
            texto = partes_correo[1].strip() if len(partes_correo) > 1 else ""
            modo = partes_correo[2].strip() if len(partes_correo) > 2 else ""
            return self.outlook.responder(clave, texto, enviar=self._quiere_enviar(modo))
        elif accion == "ENVIAR_BORRADOR":
            return self.outlook.enviar_borrador((parametro_libre or parametro or "").strip())
        elif accion == "ETIQUETAR_CORREO":
            partes_etiqueta = (parametro_libre or "").split(";;", 1)
            return self.outlook.etiquetar(
                partes_etiqueta[0].strip() if partes_etiqueta else "",
                partes_etiqueta[1].strip() if len(partes_etiqueta) > 1 else "")
        elif accion == "ARCHIVAR_CORREO":
            partes_archivo = (parametro_libre or "").split(";;", 1)
            return self.outlook.archivar(
                partes_archivo[0].strip() if partes_archivo else "",
                partes_archivo[1].strip() if len(partes_archivo) > 1 else None)
        elif accion == "MARCAR_CORREO":
            partes_marca = (parametro_libre or "").split(";;", 1)
            estado = partes_marca[1].strip().lower() if len(partes_marca) > 1 else ""
            return self.outlook.marcar(
                partes_marca[0].strip() if partes_marca else "",
                leido=not ("no" in estado or "sin leer" in estado))
        elif accion == "ELIMINAR_CORREO":
            return self.outlook.eliminar((parametro_libre or parametro or "").strip())
        elif accion == "CREAR_DOCUMENTO":
            # El contenido de un documento Markdown lleva '|' (tablas) y corchetes,
            # así que se usa el parámetro completo, no el primero troceado por '|'.
            partes_doc = (parametro_libre or "").split(";;", 1)
            nombre_doc = partes_doc[0].strip() if partes_doc else ""
            cuerpo_doc = partes_doc[1] if len(partes_doc) > 1 else ""
            return self.productivity.crear_documento(nombre_doc, cuerpo_doc)
        elif accion == "CREAR_BORRADOR":
            partes_draft = (parametro_libre or "").split(";;", 2)
            dest = partes_draft[0].strip() if partes_draft else ""
            asunto = partes_draft[1].strip() if len(partes_draft) > 1 else ""
            cuerpo = partes_draft[2].strip() if len(partes_draft) > 2 else ""
            return self.outlook.crear_borrador(dest, asunto, cuerpo)
        elif accion == "DICTADO_ON":
            self.productivity.dictado_activo = True
            return "Dictado activado. Todo lo que digas se escribirá donde tengas el cursor."
        elif accion == "DICTADO_OFF":
            self.productivity.dictado_activo = False
            return "Dictado desactivado."
        elif accion == "BUSCAR":
            plataforma = None
            consulta = (parametro or "").strip()
            if ":" in consulta:
                posible, _, resto = consulta.partition(":")
                if posible.strip().lower() in self.PLATAFORMAS_BUSQUEDA:
                    plataforma = posible.strip()
                    consulta = resto.strip()
            return self.buscar_en_brave(consulta, plataforma)
        elif accion == "REPRODUCIR_VIDEO":
            consulta = (parametro or "").strip()
            posicion = 0
            if "::" in consulta:
                consulta, _, pos = consulta.partition("::")
                try:
                    posicion = max(0, int(pos.strip()) - 1)
                except Exception:
                    posicion = 0
            return self.reproducir_video_youtube(consulta, posicion)
        elif accion == "GRABAR_REUNION":
            self.meeting.iniciar_grabacion()
            titulo = (self.meeting.reunion_actual() or {}).get("titulo")
            return (f"Grabando la reunión: {titulo}." if titulo else "Grabando la reunión.")
        elif accion == "TERMINAR_REUNION":
            threading.Thread(target=self.meeting.finalizar, daemon=True).start()
            return None
        elif accion == "REUNIONES":
            return self._listar_reuniones(parametro)
        elif accion == "LEER_ACTA":
            return self._leer_acta(parametro_libre or parametro or "")
        elif accion == "REHACER_ACTA":
            return self.meeting.rehacer_acta(parametro_libre or parametro or "")
        elif accion == "ASISTENTES_REUNION":
            return self._asistentes_reunion(parametro_libre or parametro or "")
        elif accion == "ENVIAR_ACTA":
            return self._enviar_acta(parametro_libre or parametro or "")
        elif accion == "AGENDA_REUNION":
            return self._agenda_reunion(parametro_libre or parametro or "")
        elif accion == "CREAR_PRESENTACION":
            return self.crear_presentacion_desde_md(parametro)
        elif accion == "GENERAR_PREVENTA":
            contenido = self.productivity.leer_portapapeles()
            return self.preventa.generar(parametro, contenido)
        elif accion == "MATRIZ_NUBE":
            return self.cloud.llenar(self.productivity.leer_portapapeles(),
                                     parametro or "ambos")
        elif accion == "MATRIZ_EXCEL":
            return self.cloud.llenar(self.productivity.leer_portapapeles(), "excel")
        elif accion == "MATRIZ_AZURE":
            return self.cloud.llenar(self.productivity.leer_portapapeles(), "azure")
        elif accion == "REEMPLAZAR_LOGOS_PPT":
            ruta_ppt = parametro if parametro else self._obtener_ppt_reciente()
            if ruta_ppt:
                res = self.office_tool.reemplazar_logos_ppt(ruta_ppt)
                print(res)
            else:
                print("No se encontró ningún archivo .pptx disponible.")

    @staticmethod
    def _numero_correos(parametro, defecto):
        """Número de correos que pide el usuario ('5', 'los 3 últimos', 'hoy 4')."""
        coincidencia = re.search(r"\d{1,2}", str(parametro or ""))
        if coincidencia:
            return max(1, min(20, int(coincidencia.group())))
        return defecto

    @staticmethod
    def _quiere_enviar(modo):
        """True si el parámetro de la acción pide enviar el correo de verdad.

        El modelo solo añade ';;enviar' cuando el usuario lo pide explícitamente;
        sin ese indicador, 'RESPONDER_CORREO' deja un borrador sin enviar nada.
        """
        return str(modo or "").strip().lower() in (
            "enviar", "envia", "envía", "send", "mandar", "manda", "ya", "si", "sí")

    @staticmethod
    def _quiere_confirmar(modo):
        """True si la acción de archivos pide ejecutarse de verdad.

        Igual que con el correo (';;enviar'), mover/copiar solo se ejecuta cuando
        el usuario lo confirma explícitamente (';;mover' / ';;copiar' o sinónimos);
        sin eso, solo se muestra la vista previa de lo que se haría.
        """
        return str(modo or "").strip().lower() in (
            "mover", "copiar", "si", "sí", "ya", "confirmar", "confirmado",
            "adelante", "dale", "ok", "hazlo")

    # A partir de cuántos archivos se enseña el plan y se pide confirmación: una
    # carpeta con subcarpetas puede tener cientos, y moverlos sin verlo no es plan.
    UMBRAL_CLASIFICAR = 25

    def _aviso(self, texto):
        """Cuenta por el chat (y por consola) qué está haciendo la acción.

        Las acciones largas tardan minutos (clasificar archivos de SharePoint:
        listar la carpeta y sus subcarpetas, clasificar cientos de archivos con
        la IA y pasarlos uno a uno); sin esto el chat solo enseña 'Jarvis está
        escribiendo...' y parece colgado. Si nadie escucha (``on_aviso`` lo pone
        la ventana) queda al menos la consola.
        """
        if not texto:
            return
        print(f"  [accion] {texto}", flush=True)
        # getattr: los dobles de prueba (y cualquier subclase) no tienen por qué
        # pasar por el __init__ que crea 'on_aviso'.
        aviso = getattr(self, "on_aviso", None)
        if not aviso:
            return
        try:
            aviso(texto)
        except Exception as e:
            # Un fallo al avisar no puede tumbar el trabajo que está en marcha.
            print(f"  [accion] no pude avisar del progreso: {e}", flush=True)

    def _clasificar_archivos(self, parametro):
        """CLASIFICAR_ARCHIVOS|origen_url;;destino_url;;regla[;;confirmar]

        Lista los archivos de la URL de origen (SharePoint/OneDrive) con la
        **sesión real de Brave** (controlado por CDP; el navegador firma las
        peticiones), los clasifica según la regla con la IA y los lleva a
        subcarpetas de la URL de destino. Todo sin Microsoft Graph.

        Busca también **dentro de las subcarpetas** (dos niveles), así que vale
        pasarle la carpeta de arriba (la de los clientes): entra en la carpeta
        de cada cliente y clasifica los documentos que encuentre ahí dentro, sin
        tener que bajar a mano hasta la que tenga los archivos.

        De esas carpetas solo salen los **documentos de oficina**
        (``SharePoint.EXTENSIONES_UTILES``: ppt, pptx, doc y docx). Los vídeos
        (y las fotos, los zip o los PDF) ni se listan, ni se bajan, ni se mueven:
        de esos solo se avisa de cuántos me salté y **en qué carpetas están**
        (con su ruta), que en estas bibliotecas son justo los que más pesan y
        los que nada pintan en una clasificación.

        Dentro del mismo sitio los **mueve**, pero si el destino es otro sitio
        (por ejemplo, tu OneDrive), los **copia**: los baja y los sube, y los
        originales se quedan donde estaban. También entiende la URL de un sitio
        "a secas" (``https://empresa-my.sharepoint.com/`` = "mi unidad") usando
        su biblioteca de documentos.

        Los archivos **grandes** (más de ``SharePoint.TAMANO_POR_DISCO``, 10 MB)
        no se pasan "de una vez" porque SharePoint deja a medias esos
        movimientos: se bajan a tu PC por trozos y se suben al destino igual
        (y, si era un movimiento, el original se borra solo si lo que llegó pesa
        lo mismo). Los tamaños salen del listado y se le pasan a
        ``clasificar_y_mover`` para no preguntarlos otra vez.

        Con muchos archivos (más de ``UMBRAL_CLASIFICAR``) enseña primero qué
        haría y no toca nada hasta que se repita la acción con ';;confirmar'.

        Y a los que la IA deja **'sin clasificar'** (``SharePoint.DUDOSO``: no
        supo a qué carpeta van, cosa que pasa con los nombres de archivo que son
        un hash) les hace un **segundo intento**: les lee el documento por dentro
        (``pistas_de``: el título y las primeras líneas o diapositivas, de los
        bytes que se bajan de SharePoint) y vuelve a preguntar solo por esos. Lo
        que siga sin carpeta se queda donde está, y se dice en el resumen: mejor
        un archivo quieto que uno en la carpeta equivocada.

        Mientras trabaja va **contando por el chat** lo que hace (qué carpeta
        lee, cuántos archivos encuentra, el plan y cada archivo que pasa): la
        ventana pone ``on_aviso`` y aquí se enlaza con el módulo de SharePoint,
        que es quien avisa de cada paso.

        Si Brave no está abierto se abre; si lo está sin depuración, se
        reinicia con aviso (las cookies de sesión de SharePoint son persistentes,
        así que no se pierde el inicio de sesión).
        """
        partes = (parametro or "").split(";;", 3)
        origen = partes[0].strip() if partes else ""
        destino = partes[1].strip() if len(partes) > 1 else ""
        regla = partes[2].strip() if len(partes) > 2 else ""
        modo = partes[3].strip() if len(partes) > 3 else ""
        if not origen or not destino:
            return ("Necesito la URL de origen y la de destino: "
                    "CLASIFICAR_ARCHIVOS|origen;;destino;;regla")
        # Los avisos del módulo de SharePoint salen por aquí (listado paginado,
        # búsqueda dentro de las subcarpetas y cada archivo que pasa): así el
        # chat va contando lo que se hace mientras se hace.
        self.sharepoint.on_aviso = self._aviso
        self._aviso(f"Clasificando los archivos de {origen} según tu regla y "
                    f"llevándolos a {destino}.")
        try:
            # La raíz de un sitio no tiene archivos: se usa su biblioteca.
            origen = self.sharepoint.resolver(origen)
            destino = self.sharepoint.resolver(destino)
            nota = self.sharepoint.asegurar_navegador(origen)
            if not nota.startswith("Brave ya estaba"):
                self._aviso(nota)
            self._aviso("Leyendo la carpeta y bajando a sus subcarpetas (para "
                        "no dejarme archivos por el camino)...")
            # Dentro de las subcarpetas también: ahí están los documentos.
            archivos = self.sharepoint.listar_archivos(
                origen, profundidad=self.sharepoint.PROFUNDIDAD_BUSQUEDA)
        except Exception as e:
            return (f"No pude acceder a la carpeta de SharePoint.\n{e}")
        aviso = "" if nota.startswith("Brave ya estaba") else f"{nota}\n"
        if self.sharepoint.nota_listado:
            aviso += f"{self.sharepoint.nota_listado}\n"
            self._aviso(self.sharepoint.nota_listado)
        if not archivos:
            return (aviso + f"No hay archivos en {origen} ni dentro de sus "
                    f"subcarpetas ({self.sharepoint.PROFUNDIDAD_BUSQUEDA} "
                    "nivel(es)).")
        nombres = [a["subruta"] for a in archivos]
        # Cuánto pesa cada uno, tal como lo dijo el listado: sin esto, mover o
        # copiar tendría que preguntarlo archivo por archivo.
        tamanos = {a["subruta"]: a.get("tamano") for a in archivos}
        # Qué carpetas tiene YA el destino (hasta dos niveles): con esa lista la
        # IA deja cada archivo en una de las que existen, en vez de inventarse
        # otra que se le parezca al lado de la buena.
        carpetas = self._carpetas_del_destino(destino)
        self._aviso(f"Encontré {len(archivos)} archivo(s): los clasifico según "
                    "la regla.")
        clasificador = getattr(self.sharepoint, "on_clasificar", None)
        if clasificador:
            plan = self._clasificar_con_ia(clasificador, nombres, regla,
                                           carpetas)
            if plan is None:
                return "No pude clasificar: configura tu API Key (DeepSeek) primero."
        else:
            plan = self.sharepoint.clasificar_naive(nombres, regla)
        plan = self.sharepoint.ajustar_plan(plan, archivos, carpetas)
        # Lo que la IA no supo clasificar no está perdido: se le lee el documento
        # por dentro (título y primeras líneas) y se le vuelve a preguntar por
        # esos. Es lo que hace que una propuesta con nombre de hash acabe en su
        # carpeta en vez de quedarse quieta.
        plan, dudosos = self.sharepoint.separar_dudosos(plan)
        if dudosos and clasificador:
            rescatados, dudosos = self._reintentar_dudosos(dudosos, origen, regla,
                                                           carpetas)
            plan = plan + rescatados
        # Lo que la regla deja fuera (una transcripción, una Consultoría, algo por
        # revisar) no es un archivo a pasar: se aparta ANTES de contar y de
        # enseñar el plan, para no pedir confirmación por él ni bajarlo a tu PC.
        plan, omitidos = self.sharepoint.separar_omitidos(plan)
        grandes = self._grandes_del_plan(plan, tamanos)
        aviso_plan = self._resumen_plan(plan, omitidos, carpetas, dudosos, regla)
        if grandes:
            aviso_plan += (f" {grandes} pasan de "
                           f"{self.sharepoint.TAMANO_POR_DISCO // 1048576} MB: "
                           "esos van bajándolos a tu PC y subiéndolos (tardan "
                           "más, pero pasan).")
        self._aviso("Plan listo: " + aviso_plan)
        if not plan:
            return aviso + self._nada_que_pasar(omitidos, dudosos, regla)
        if len(plan) > self.UMBRAL_CLASIFICAR and not self._quiere_confirmar(modo):
            self._aviso(f"Son más de {self.UMBRAL_CLASIFICAR} archivos: te "
                        "enseño el plan y no toco nada hasta que me confirmes.")
            return aviso + self._vista_previa_clasificacion(plan, origen, destino,
                                                            omitidos, carpetas,
                                                            dudosos, regla)
        try:
            resumen = self.sharepoint.clasificar_y_mover(origen, destino, plan,
                                                        tamanos=tamanos,
                                                        carpetas=carpetas)
        except Exception as e:
            mismo = (self.sharepoint.parsear_url(origen)["sitio"]
                     == self.sharepoint.parsear_url(destino)["sitio"])
            return (f"Error {'moviendo' if mismo else 'copiando'} los archivos: "
                    f"{e}")
        return aviso + resumen

    def _carpetas_del_destino(self, destino):
        """Las carpetas que ya existen en el destino ([] si no se pueden leer).

        Se leen ANTES de clasificar y se le pasan a la IA. Sin esto clasificaba
        a ciegas: no sabía qué carpetas había hechas al otro lado y creaba
        nuevas ('Assessment/Data Analysis') al lado de las de siempre
        ('Assessment/Data'), que es justo lo que no se quiere en una biblioteca
        que ya tiene su orden.

        Si no se pueden leer (el destino todavía no existe, no hay permiso, Brave
        no responde) se sigue clasificando sin esa lista: es un atajo, no un
        requisito.
        """
        try:
            carpetas = self.sharepoint.catalogo_carpetas(destino)
        except Exception as e:
            self._aviso(f"No pude mirar qué carpetas tiene ya el destino "
                        f"({e}): clasifico sin esa lista.")
            return []
        if not carpetas:
            self._aviso("El destino todavía no tiene subcarpetas: las que hagan "
                        "falta se crearán ahí.")
            return []
        self._aviso(f"El destino ya tiene {len(carpetas)} carpeta(s): le pido a "
                    "la IA que use esas cuando un archivo encaje, en vez de "
                    "crear otras parecidas.")
        nota = getattr(self.sharepoint, "nota_catalogo", "")
        if nota:
            self._aviso(nota)
        return carpetas

    @staticmethod
    def _clasificar_con_ia(clasificador, nombres, regla, carpetas, pistas=None):
        """Pide el plan a la IA, pasándole las carpetas que existen y las pistas.

        El enganche (``SharePoint.on_clasificar``, que pone la ventana) recibe
        las carpetas del destino y, en el segundo intento, lo que dicen por
        dentro los documentos (``pistas``). Si alguno se quedó con la firma de
        antes (dos o tres argumentos) se le llama como entienda: mejor clasificar
        sin el atajo que reventar la acción.
        """
        intentos = [(nombres, regla, carpetas, pistas),
                    (nombres, regla, carpetas),
                    (nombres, regla)]
        for argumentos in intentos:
            try:
                return clasificador(*argumentos)
            except TypeError as e:
                if "positional argument" not in str(e):
                    raise
        return None

    def _reintentar_dudosos(self, dudosos, origen, regla, carpetas):
        """Segundo intento con los que la IA dejó 'sin clasificar'.

        Se le enseña a la IA lo que dice el propio documento por dentro
        (``SharePoint.pistas_de``: el título de las propiedades y las primeras
        líneas o diapositivas, leídos de los bytes que se bajan de SharePoint) y
        se le pide el plan otra vez, solo para esos archivos y con las mismas
        carpetas del destino. Un nombre como 'PROPUESTA COMERCIAL bfddfa36 RFI
        Soporte y-o administración.pptx' no dice de qué disciplina es; la portada
        del documento sí, y es lo único que hacía falta para clasificarlo.

        Devuelve (lo que ahora sí tiene carpeta, los que siguen sin saberlo): de
        los segundos se dice en el resumen que se quedan donde están, sin
        inventarles una carpeta (una propuesta en la carpeta equivocada es peor
        que una propuesta quieta).
        """
        nombres = [nombre for nombre, _ in dudosos]
        self._aviso(f"{len(nombres)} archivo(s) se quedaron sin clasificar: les "
                    "leo el documento por dentro y vuelvo a preguntar.")
        try:
            pistas = self.sharepoint.pistas_de(origen, nombres)
        except Exception as e:
            self._aviso(f"No pude leer esos documentos por dentro ({e}).")
            return [], dudosos
        if not pistas:
            self._aviso("No saqué nada de dentro de esos documentos: se quedan "
                        "donde están.")
            return [], dudosos
        self._aviso(f"Leí el contenido de {len(pistas)} de {len(nombres)} "
                    "archivo(s): a ver si con eso sabe dónde van.")
        clasificador = getattr(self.sharepoint, "on_clasificar", None)
        if not clasificador:
            return [], dudosos
        plan = self._clasificar_con_ia(clasificador, nombres, regla, carpetas,
                                       pistas)
        if plan is None:
            return [], dudosos
        # De listado del segundo intento vale la propia lista de esos archivos:
        # así, si la IA devuelve el nombre a medias ('bfddfa36.pptx' en vez de
        # 'Cliente/bfddfa36.pptx'), el plan se completa con su ruta de verdad y
        # el archivo no se pierde por un nombre mal copiado.
        listado = [{"nombre": nombre.rsplit("/", 1)[-1], "subruta": nombre}
                   for nombre in nombres]
        plan = self.sharepoint.ajustar_plan(plan, listado, carpetas)
        return self.sharepoint.separar_dudosos(plan)

    def _grandes_del_plan(self, plan, tamanos):
        """Cuántos archivos del plan van a pasar por tu PC (pesan > 10 MB).

        Se cuenta con los tamaños del listado, para poder avisarlo en el plan y
        que no sorprenda que esos tarden mucho más (se bajan y se suben).
        """
        umbral = getattr(self.sharepoint, "TAMANO_POR_DISCO", 0)
        if not umbral or not tamanos:
            return 0

        def pesado(nombre):
            try:
                return int(tamanos.get(nombre) or 0) > umbral
            except (TypeError, ValueError):
                return False

        return sum(1 for nombre, _ in plan or [] if pesado(nombre))

    @staticmethod
    def _nada_que_pasar(omitidos, dudosos=None, regla=""):
        """Qué decir cuando no hay NADA que pasar.

        Sin esto, el plan queda vacío y el resumen hablaría de '0 archivo(s)': lo
        que hay que contar es por qué no se pasa ninguno, y eso depende de quién
        los dejó fuera. Si tu regla dice que no se tocan (transcripciones,
        Consultoría, lo que haya que revisar) es eso lo que se cuenta; si no, es
        que la IA no supo dónde ponerlos ni mirando el documento por dentro, y
        decirlo así es lo que hace falta para entender qué pasó (antes se decía
        siempre 'tu regla deja fuera', aunque la regla no dijera eso).

        En los dos casos se enseña la lista con el motivo de cada uno y que no se
        tocó nada.
        """
        total = len(omitidos or []) + len(dudosos or [])
        if SharePoint.regla_deja_fuera(regla):
            lineas = ["No hay nada que pasar: tu regla deja fuera a los "
                      f"{total} archivo(s) que encontré."]
        else:
            lineas = ["No hay nada que pasar: de los "
                      f"{total} archivo(s) que encontré, ninguno tiene carpeta "
                      "en el plan (ni mirando dentro de los documentos)."]
        lineas += [f"  - {nombre} → {carpeta or '(raíz)'}"
                   for nombre, carpeta in (omitidos or [])[:40]]
        lineas += [f"  - {nombre} → sin clasificar (no supe dónde va)"
                   for nombre, _ in (dudosos or [])[:40]]
        if total > 40:
            lineas.append(f"  … y {total - 40} más")
        lineas.append("Los dejé donde estaban.")
        return "\n".join(lineas)

    @staticmethod
    def _resumen_plan(plan, omitidos=None, carpetas=None, dudosos=None, regla=""):
        """Texto corto del plan: cuántos archivos y a qué subcarpetas van.

        Los que no se pasan (los que la regla deja fuera y los que la IA no supo
        clasificar) no cuentan, pero se dicen: si no, la cuenta no cuadra con lo
        que se encontró. Y se dice **por qué** se quedan, que no es lo mismo:
        'tu regla los deja fuera' si la regla habla de eso, y 'no les encontré
        carpeta' cuando es la IA la que no supo; los que se quedaron 'sin
        clasificar' se cuentan aparte, para que se vea que ahí sí se intentó
        leer el documento por dentro. Con ``carpetas`` (las que ya existían en el
        destino) se dice cuántos archivos van a carpetas de las de siempre y
        cuántos estrenan carpeta.
        """
        carpetas = carpetas or []
        vistas = []
        for _, subcarpeta in plan or []:
            etiqueta = (subcarpeta or "").strip() or "(raíz)"
            if etiqueta not in vistas:
                vistas.append(etiqueta)
        detalle = ", ".join(vistas[:6]) + ("…" if len(vistas) > 6 else "")
        texto = (f"{len(plan or [])} archivo(s) a {len(vistas)} subcarpeta(s) "
                 f"({detalle}).")
        if omitidos:
            if SharePoint.regla_deja_fuera(regla):
                texto += (f" Y {len(omitidos)} se quedan sin tocar: tu regla los "
                          "deja fuera.")
            else:
                texto += (f" Y {len(omitidos)} se quedan sin tocar: no les "
                          "encontré carpeta.")
        if dudosos:
            texto += (f" {len(dudosos)} archivo(s) se quedaron 'sin clasificar': "
                      "no supe a qué carpeta van ni leyendo el documento por "
                      "dentro, así que se quedan donde están.")
        if carpetas and plan:
            dadas = {(c or "").strip().strip("/") for c in carpetas}
            ya = sum(1 for _, subcarpeta in plan
                     if (subcarpeta or "").strip().strip("/") in dadas)
            if ya:
                texto += (f" {ya} van a carpetas que ya estaban en el destino; "
                          f"{len(plan) - ya} estrenan carpeta.")
        return texto

    def _vista_previa_clasificacion(self, plan, origen, destino, omitidos=None,
                                    carpetas=None, dudosos=None, regla=""):
        """Qué haría con cada archivo, sin tocar nada (pide confirmación).

        Se usa cuando son muchos: ver antes la lista (de qué carpeta sale cada
        uno y a dónde va) es la forma de no llevarse media biblioteca por
        delante. Los que no se tocarían también se enseñan (los de la regla y
        los que la IA no supo clasificar, cada grupo con su motivo), para que se
        sepa desde el principio qué se va a quedar quieto. Y las carpetas que ya
        existen en el destino, para que se vea de dónde salen los destinos que no
        estrenan carpeta.
        """
        mismo = (self.sharepoint.parsear_url(origen)["sitio"]
                 == self.sharepoint.parsear_url(destino)["sitio"])
        lineas = [f"Encontré {len(plan) + len(omitidos or []) + len(dudosos or [])} "
                  f"archivo(s) en {origen} y sus subcarpetas.",
                  f"Todavía NO he tocado nada. Los "
                  f"{'movería' if mismo else 'copiaría'} así:"]
        lineas += [f"  {nombre} → {carpeta or '(raíz)'}"
                   for nombre, carpeta in plan[:40]]
        if len(plan) > 40:
            lineas.append(f"  … y {len(plan) - 40} más")
        fuera = self.sharepoint.regla_deja_fuera(regla)
        if omitidos:
            motivo = ("tu regla los deja fuera" if fuera
                      else "no les encontré carpeta")
            lineas.append(f"Y estos NO los tocaría ({motivo}):")
            lineas += [f"  - {nombre} → {carpeta or '(raíz)'}"
                       for nombre, carpeta in omitidos[:20]]
            if len(omitidos) > 20:
                lineas.append(f"  … y {len(omitidos) - 20} más")
        if dudosos:
            lineas.append("Y estos tampoco, porque no supe a qué carpeta van "
                          "(ni leyendo el documento por dentro):")
            lineas += [f"  - {nombre}" for nombre, _ in dudosos[:20]]
            if len(dudosos) > 20:
                lineas.append(f"  … y {len(dudosos) - 20} más")
        if carpetas:
            dichas = ", ".join(carpetas[:20]) + ("…" if len(carpetas) > 20 else "")
            lineas.append(f"En el destino ya hay {len(carpetas)} carpeta(s) "
                          f"({dichas}): los archivos que encajan van a esas, no "
                          "a una nueva que se les parezca.")
        lineas.append("Si te parece bien, dímelo y lo hago de verdad "
                      "(CLASIFICAR_ARCHIVOS|origen;;destino;;regla;;confirmar).")
        return "\n".join(lineas)

    # ------------------------------------------------------------------ Reuniones, actas y calendario
    def _listar_reuniones(self, parametro=None):
        """Lista las actas de reunión guardadas (numeradas para poder pedirlas)."""
        actas = self.meeting.listar_actas(self._numero_correos(parametro, 8))
        if not actas:
            return f"No hay ninguna reunión guardada todavía en {rutas.REUNIONES}."
        lineas = []
        for i, acta in enumerate(actas, 1):
            detalle = acta["fecha"] or ""
            if acta["duracion"]:
                detalle += f" · {acta['duracion']}"
            lineas.append(f"{i}. {acta['titulo']} — {detalle} — {acta['nombre']}")
        return f"Reuniones guardadas ({len(actas)}):\n" + "\n".join(lineas)

    def _leer_acta(self, clave=None):
        """Pasa el acta a la IA para que la presente (asistentes, acuerdos y tareas)."""
        acta, error = self.meeting.leer_acta(clave)
        if acta is None:
            return error
        asistentes = ", ".join(acta["asistentes"]) or "no identificados"
        contexto = (f"Título: {acta['titulo']}\n"
                    f"Fecha: {acta['fecha'] or '(sin fecha)'}\n"
                    f"Duración: {acta['duracion'] or 'no medida'}\n"
                    f"Asistentes: {asistentes}\n\n{acta['cuerpo']}")
        return ("__CONTEXTO__"
                "Resume esta acta de reunión en español: primero los datos y los "
                "acuerdos, y al final las tareas con su responsable y su fecha. Sé "
                "claro y breve, y no inventes nada que no esté en el acta:\n\n" + contexto)

    def _asistentes_reunion(self, clave=None):
        """Asistentes de una reunión: los del acta o, si no hay, los del calendario."""
        acta = None
        if str(clave or "").strip():
            acta, error = self.meeting.leer_acta(clave)
            if acta is None:
                return error
        if acta is not None and acta["asistentes"]:
            return (f"Asistentes de '{acta['titulo']}': " + "; ".join(acta["asistentes"]) + ".")
        reunion = self.meeting.reunion_actual()
        if reunion.get("asistentes"):
            return ("Asistentes de la reunión grabada: "
                    + "; ".join(reunion["asistentes"]) + ".")
        datos, mensaje = self.calendario.invitados(acta["titulo"] if acta else None)
        if datos is None:
            return mensaje
        if not datos["correos"]:
            return (f"La reunión '{datos['asunto']}' del calendario no tiene invitados "
                    "con correo.")
        texto = f"Invitados de '{datos['asunto']}' ({self.calendario.texto_evento(datos, con_invitados=False)}): " + "; ".join(datos["correos"]) + "."
        if datos["sin_correo"]:
            texto += f"\nSin correo en la invitación: {', '.join(datos['sin_correo'])}."
        return texto

    def _crear_o_enviar(self, destinatarios, asunto, cuerpo, enviar=False):
        """Crea el borrador del correo y, solo si 'enviar' es True, lo manda."""
        resultado = str(self.outlook.crear_borrador(destinatarios, asunto, cuerpo))
        if not enviar or "Borrador creado" not in resultado:
            return resultado
        envio = self.outlook.enviar_borrador()
        return f"{resultado} {envio}"

    def _enviar_acta(self, parametro=None):
        """Prepara (o envía) el correo con el acta de una reunión.

        Formato: ENVIAR_ACTA[|destinatarios separados por ';'][;;acta][;;enviar]

        La 'acta' admite el número del listado de 'mis reuniones', parte de su
        nombre o de su título; sin ella se usa la última reunión. Sin destinatarios
        se usan los asistentes del acta, los de la reunión que se acaba de grabar o
        los invitados del calendario. Como en el resto del correo, sin ';;enviar'
        solo se deja el borrador preparado en Outlook.
        """
        partes = [p.strip() for p in str(parametro or "").split(";;")]
        destinatarios, clave, enviar = "", "", False
        posicion = 0
        for parte in partes:
            if parte.lower() in ("enviar", "envialo", "envíalo", "mandar", "manda",
                                 "send", "si", "sí"):
                enviar = True
                continue
            if posicion == 0:
                destinatarios = parte
            elif posicion == 1:
                clave = parte
            posicion += 1          # las partes vacías también ocupan su posición
        if not clave and destinatarios.isdigit():
            # 'ENVIAR_ACTA|2' es el acta 2, no un destinatario
            destinatarios, clave = "", destinatarios
        correo, error = self.meeting.acta_para_correo(clave)
        if correo is None:
            return error
        if destinatarios.lower() in ("asistentes", "los asistentes", "invitados",
                                     "los invitados", "todos", "auto", "automático",
                                     "automatico"):
            destinatarios = ""
        if not destinatarios:
            destinatarios = "; ".join(correo["destinatarios"])
        if not destinatarios:
            destinatarios = "; ".join((self.meeting.reunion_actual() or {}).get("asistentes") or [])
        if not destinatarios:
            datos, _mensaje = self.calendario.invitados(correo["titulo"])
            if datos is not None:
                destinatarios = "; ".join(datos["correos"])
        if not destinatarios:
            return ("No sé a quién mandar el acta. Dime los correos, por ejemplo: "
                    "'envía el acta a ana@empresa.com y luis@empresa.com'.")
        return self._crear_o_enviar(destinatarios, correo["asunto"], correo["cuerpo"], enviar)

    def _agenda_reunion(self, parametro=None):
        """Lee el calendario y pide a la IA una agenda para las próximas reuniones."""
        texto = str(parametro or "").strip()
        asunto = ""
        dias = 7
        coincidencia = re.match(r"^(\d{1,2})\s*(d[ií]as?|d)?$", texto.lower())
        if coincidencia:
            dias = max(1, min(30, int(coincidencia.group(1))))
        elif texto:
            asunto = texto
        eventos, mensaje = self.calendario.proximos(dias=dias, limite=12)
        if eventos is None:
            return mensaje
        if asunto:
            filtrados = [e for e in eventos if asunto.lower() in e["asunto"].lower()]
            eventos = filtrados or eventos
        if not eventos:
            return f"No veo reuniones en el calendario en los próximos {dias} día(s)."
        lineas = [self.calendario.texto_evento(e) for e in eventos]
        enfoque = (f"Concentra la agenda en la reunión '{asunto}'." if asunto else
                   "Propón la agenda para la reunión más próxima de la lista.")
        return ("__CONTEXTO__"
                "Con estas reuniones del calendario, redacta la agenda previa de una "
                "reunión en español: objetivo, temas a tratar con tiempos, decisiones "
                "que hay que tomar y qué conviene llevar preparado. " + enfoque +
                "\n\nReuniones del calendario:\n" + "\n".join(lineas))

    def abrir_aplicacion(self, nombre_app):
        if not nombre_app:
            return

        nombre_app = nombre_app.lower().strip()

        # 1. Invocación directa para Valorant y Riot Client
        if any(x in nombre_app for x in ["valorant", "riot client", "riot", "abreva lorent"]):
            rutas_riot = [
                r"C:\Riot Games\Riot Services\RiotClientServices.exe",
                r"D:\Riot Games\Riot Services\RiotClientServices.exe"
            ]
            
            for ruta in rutas_riot:
                if os.path.exists(ruta):
                    try:
                        if "riot" in nombre_app and "client" in nombre_app:
                            os.system(f'"{ruta}"')
                            print("Lanzando Riot Client...")
                        else:
                            os.system(f'"{ruta}" --launch-product=valorant --launch-patchline=live')
                            print("Lanzando Valorant directamente...")
                        return
                    except Exception as e:
                        print(f"Error lanzando Riot: {e}")

        # 2. Protocolos URI (se abren con el manejador del sistema) y comandos directos
        protocolos_uri = {
            "discord": "discord://",
            "spotify": "spotify:",
            "roblox": "roblox://",
            "steam": "steam://"
        }

        comandos_directos = {
            "vscode": "code",
            "visual studio code": "code",
            "visual studio": "code",
            "chrome": "start chrome",
            "edge": "start msedge",
            "brave": "start brave"
        }

        if nombre_app in protocolos_uri:
            try:
                webbrowser.open(protocolos_uri[nombre_app])
                print(f"Lanzando {nombre_app}...")
                return
            except Exception as e:
                print(f"Error al abrir mediante protocolo: {e}")

        if nombre_app in comandos_directos:
            try:
                os.system(comandos_directos[nombre_app])
                print(f"Lanzando {nombre_app}...")
                return
            except Exception as e:
                print(f"Error al abrir mediante comando: {e}")

        # 3. Rutas personalizadas en discos secundarios (D:)
        rutas_personalizadas = {
            "obs": r"D:\obs-studio\bin\64bit\obs64.exe",
            "obs studio": r"D:\obs-studio\bin\64bit\obs64.exe"
        }

        if nombre_app in rutas_personalizadas and os.path.exists(rutas_personalizadas[nombre_app]):
            try:
                os.startfile(rutas_personalizadas[nombre_app])
                print(f"Iniciando desde ruta directa: {rutas_personalizadas[nombre_app]}")
                return
            except Exception as e:
                print(f"Error abriendo desde ruta personal: {e}")

        # 4. Búsqueda por menú inicio
        try:
            print(f"Buscando '{nombre_app}' en el sistema...")
            pyautogui.press("win")
            time.sleep(0.3)
            pyautogui.write(nombre_app, interval=0.03)
            time.sleep(0.3)
            pyautogui.press("enter")
        except Exception as e:
            print(f"No se pudo ejecutar la aplicación {nombre_app}: {e}")

    def _obtener_ejecutables(self, nombre_app):
        """Devuelve la lista de nombres de ejecutable asociados a una app amigable."""
        nombre_app = nombre_app.lower().strip()
        return self.PROCESOS_CONOCIDOS.get(nombre_app, [f"{nombre_app}.exe"])

    def cerrar_aplicacion(self, nombre_app):
        """Finaliza procesos de Windows por nombre o cierra la ventana activa si es 'ventana_activa'."""
        if not nombre_app or "activa" in nombre_app.lower():
            pyautogui.hotkey("alt", "f4")
            print("Cerrando la ventana activa en pantalla.")
            return

        nombre_app = nombre_app.lower().strip()

        ejecutables_a_cerrar = self._obtener_ejecutables(nombre_app)

        cerrado = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                p_name = proc.info['name']
                if p_name and any(exe.lower() == p_name.lower() for exe in ejecutables_a_cerrar):
                    proc.kill()
                    print(f"Proceso {p_name} (PID: {proc.info['pid']}) finalizado.")
                    cerrado = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if not cerrado:
            if gw:
                ventanas = gw.getAllTitles()
                for titulo in ventanas:
                    if titulo and nombre_app in titulo.lower():
                        v = gw.getWindowsWithTitle(titulo)[0]
                        v.close()
                        print(f"Ventana '{titulo}' cerrada.")
                        cerrado = True
                        break
            
            if not cerrado:
                print(f"No se encontró un proceso o ventana activa para '{nombre_app}'.")

    def minimizar_aplicacion_especifica(self, nombre_app):
        if not nombre_app or not gw:
            pyautogui.hotkey("win", "down")
            return

        nombre_app = nombre_app.lower().strip()
        ventanas = gw.getAllTitles()

        encontrada = False
        for titulo in ventanas:
            if titulo and nombre_app in titulo.lower():
                ventana = gw.getWindowsWithTitle(titulo)[0]
                if not ventana.isMinimized:
                    ventana.minimize()
                    print(f"Ventana '{titulo}' minimizada.")
                    encontrada = True
                    break

        if not encontrada:
            pyautogui.hotkey("win", "down")

    def gestion_ventanas(self, accion):
        if not accion:
            return

        accion = accion.lower().strip()
        if "minimizar" in accion:
            pyautogui.hotkey("win", "down")
        elif "maximizar" in accion:
            pyautogui.hotkey("win", "up")
        elif "cerrar" in accion:
            pyautogui.hotkey("alt", "f4")
        elif "pantalla completa" in accion or "f11" in accion:
            pyautogui.press("f11")
        elif "apagar" in accion:
            # El apagado del asistente lo gestiona la interfaz (app_gui) al detectar esta acción
            print("Solicitud de apagado del asistente recibida.")

    def ajustar_volumen(self, parametro):
        if not parametro:
            return

        parametro = parametro.lower().replace("%", "").strip()

        if parametro.isdigit() and AudioUtilities:
            porcentaje = int(parametro)
            porcentaje = max(0, min(100, porcentaje))
            
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                volume.SetMasterVolumeLevelScalar(porcentaje / 100.0, None)
                print(f"Volumen ajustado al {porcentaje}%")
                return
            except Exception as e:
                print(f"Error ajustando volumen porcentual: {e}")

        if "silenciar" in parametro or "mute" in parametro or "quitar" in parametro:
            pyautogui.press("volumemute")
        elif "subir" in parametro or "mas" in parametro:
            for _ in range(5):
                pyautogui.press("volumeup")
        elif "bajar" in parametro or "menos" in parametro:
            for _ in range(5):
                pyautogui.press("volumedown")

    def ajustar_volumen_app(self, parametro):
        """
        Ajusta el volumen o el silencio de una aplicación específica usando el
        mezclador de volumen de Windows (sesiones de audio por proceso).
        Formato esperado en `parametro`: "nombre_app:accion"
          - accion: porcentaje (ej. 30%), "mute"/"silenciar", "subir"/"bajar", "unmute"
        """
        if not parametro:
            return

        if ":" not in parametro:
            print("Formato de volumen por app esperado: app:accion (ej. spotify:30%)")
            return

        nombre_app, accion = parametro.split(":", 1)
        nombre_app = nombre_app.strip().lower()
        accion = accion.strip().lower()

        if not AudioUtilities:
            print("pycaw no está disponible; no se puede ajustar el volumen por aplicación.")
            return

        sesion_objetivo = self._buscar_sesion_audio(nombre_app)
        if not sesion_objetivo:
            print(f"No se encontró una sesión de audio activa para '{nombre_app}'.")
            return

        try:
            simple_vol = sesion_objetivo.SimpleAudioVolume
            if accion in ("mute", "mutear", "silenciar", "silencio", "quitar"):
                simple_vol.SetMute(1, None)
                print(f"'{nombre_app}' silenciada (solo esa app).")
            elif accion in ("unmute", "desmutear", "activar", "sonido"):
                simple_vol.SetMute(0, None)
                print(f"'{nombre_app}' con sonido reactivado.")
            elif accion.replace("%", "").isdigit():
                porcentaje = max(0, min(100, int(accion.replace("%", ""))))
                simple_vol.SetMasterVolume(porcentaje / 100.0, None)
                print(f"Volumen de '{nombre_app}' ajustado al {porcentaje}%.")
            elif "subir" in accion or "mas" in accion:
                actual = simple_vol.GetMasterVolume()
                simple_vol.SetMasterVolume(min(1.0, actual + 0.1), None)
                print(f"Volumen de '{nombre_app}' subido.")
            elif "bajar" in accion or "menos" in accion:
                actual = simple_vol.GetMasterVolume()
                simple_vol.SetMasterVolume(max(0.0, actual - 0.1), None)
                print(f"Volumen de '{nombre_app}' bajado.")
            else:
                print(f"Acción de volumen desconocida: '{accion}'")
        except Exception as e:
            print(f"Error ajustando el volumen de '{nombre_app}': {e}")

    def _buscar_sesion_audio(self, nombre_app):
        """Busca la sesión de audio (AudioSession) cuyo proceso coincide con la app."""
        ejecutables = self._obtener_ejecutables(nombre_app)
        try:
            sesiones = AudioUtilities.GetAllSessions()
        except Exception as e:
            print(f"Error enumerando sesiones de audio: {e}")
            return None

        for sesion in sesiones:
            try:
                if not sesion.Process:
                    continue
                p_name = sesion.Process.name().lower()
                if any(exe.lower() == p_name for exe in ejecutables) or nombre_app in p_name:
                    return sesion
            except Exception:
                continue
        return None

    def abrir_lineups_segundo_monitor(self, mapa_o_url):
        url = "https://lineups.gg"
        if mapa_o_url and "http" in mapa_o_url:
            url = mapa_o_url
        elif mapa_o_url:
            url = f"https://lineups.gg/map/{mapa_o_url.lower()}"

        try:
            monitores = get_monitors()
            webbrowser.open(url)

            if len(monitores) > 1:
                time.sleep(1.2)
                pyautogui.hotkey('win', 'shift', 'right')
                print(f"Ventana movida al segundo monitor ({url})")
            else:
                print(f"Abierto en monitor principal ({url})")
        except Exception as e:
            print(f"Error gestionando pantallas: {e}")

    def _obtener_ppt_reciente(self):
        user_path = os.path.expanduser("~")
        downloads_path = os.path.join(user_path, "Downloads")

        if not os.path.exists(downloads_path):
            return None

        archivos = [os.path.join(downloads_path, f) for f in os.listdir(downloads_path) if f.endswith(".pptx")]
        if not archivos:
            return None

        return max(archivos, key=os.path.getmtime)

    # ------------------------------------------------------------------ Búsqueda web
    def buscar_en_brave(self, consulta, plataforma=None):
        """Abre una búsqueda en Brave (o el navegador por defecto si no está Brave)."""
        if not consulta:
            return "Dime qué quieres buscar."
        url = self._url_busqueda(consulta, plataforma)
        self._abrir_url_brave(url)
        nombre = f" en {plataforma}" if plataforma else ""
        return f"Buscando {consulta}{nombre} en Brave."

    def reproducir_video_youtube(self, consulta, posicion=0):
        """Busca en YouTube y reproduce el video en la posición indicada (0 = primero)."""
        if not consulta:
            return "Dime qué video quieres ver."
        try:
            import yt_dlp
            ydl_opts = {"quiet": True, "skip_download": True, "extract_flat": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{int(posicion) + 5}:{consulta}", download=False)
            entries = info.get("entries") or []
            # Filtrar solo videos (excluir canales "UC..." y listas de reproducción)
            videos = [e for e in entries if e.get("id") and not e.get("id", "").startswith("UC")]
            if not videos:
                return f"No encontré videos para '{consulta}'."
            idx = min(int(posicion), len(videos) - 1)
            video = videos[idx]
            video_id = video.get("id")
            titulo = video.get("title", "")
            if not video_id:
                return "No pude obtener el enlace del video."
            url = f"https://www.youtube.com/watch?v={video_id}"
            self._abrir_url_brave(url)
            ordinal = "primer resultado" if idx == 0 else f"resultado número {idx + 1}"
            return f"Reproduciendo el {ordinal}: {titulo}."
        except Exception as e:
            return f"No pude reproducir el video: {e}"

    def _abrir_url_brave(self, url):
        """Abre una URL en Brave, o en el navegador por defecto si Brave no está."""
        import subprocess
        ruta = self._ruta_brave()
        try:
            if ruta:
                subprocess.Popen([ruta, url])
            else:
                webbrowser.open(url)
        except Exception:
            webbrowser.open(url)

    def _ruta_brave(self):
        """Ruta de brave.exe (o None si no está instalado)."""
        return navegador_cdp.ruta_brave() or None

    def _url_busqueda(self, consulta, plataforma=None):
        q = urllib.parse.quote(consulta)
        p = (plataforma or "").strip().lower()
        if p in ("youtube", "yt"):
            return f"https://www.youtube.com/results?search_query={q}"
        if p == "google":
            return f"https://www.google.com/search?q={q}"
        if p in ("wikipedia", "wiki"):
            return f"https://es.wikipedia.org/w/index.php?search={q}"
        if p == "github":
            return f"https://github.com/search?q={q}"
        if p == "spotify":
            return f"https://open.spotify.com/search/{q}"
        if p in ("twitter", "x"):
            return f"https://twitter.com/search?q={q}"
        if p == "amazon":
            return f"https://www.amazon.com/s?k={q}"
        if p in ("stackoverflow", "stack overflow"):
            return f"https://stackoverflow.com/search?q={q}"
        if p == "reddit":
            return f"https://www.reddit.com/search/?q={q}"
        # Búsqueda general con Brave Search
        return f"https://search.brave.com/search?q={q}"

    # ------------------------------------------------------------------ Crear presentación desde Markdown
    def crear_presentacion_desde_md(self, parametro=None):
        """Genera el .pptx desde un .md usando los diseños de la plantilla.

        'parametro' puede ser la ruta del .md y, opcionalmente, un límite de
        diapositivas separado por ';' o ',' (p. ej. "ruta.md;30"), o directamente
        solo el número (p. ej. "30") para usar el .md más reciente.

        Las primeras diapositivas de la plantilla ('slides_fijos_presentacion' en
        la config, por defecto 4) y las últimas ('slides_cola_plantilla_presentacion'
        en la config, por defecto 4) se conservan tal cual, sin tocarlas. Al
        recortar se conservan siempre las últimas diapositivas de cierre del .md
        ('slides_finales_presentacion' en la config, por defecto 6), así que un
        límite de 30 genera 30 + 6 = 36 diapositivas de contenido.
        """
        plantilla = self._buscar_plantilla()
        ruta_md, limite = self._parsear_parametro_presentacion(parametro)
        limite = limite or self._limite_slides_config()
        contenido_md = self._resolver_md(ruta_md)
        if not contenido_md:
            return (f"No encontré un archivo .md. Pon tu contenido en la carpeta "
                    f"{rutas.PRESENTACIONES} o indica su ruta.")
        resultado = self.office_tool.crear_presentacion(
            contenido_md, plantilla,
            max_slides=limite,
            finales=self._finales_slides_config(),
            fijos=self._fijos_slides_config(),
            colas=self._colas_slides_config())
        if not plantilla:
            resultado += (f"\n\nOjo: no hay ninguna plantilla .pptx/.potx en "
                          f"{rutas.PLANTILLAS}, así que se usó un diseño genérico "
                          f"sin el fondo, la línea de cabecera ni el logo de la marca. "
                          f"Copia tu plantilla corporativa en esa carpeta para que la "
                          f"presentación salga con el diseño.")
        return resultado

    @staticmethod
    def _parsear_parametro_presentacion(parametro):
        """Separa la ruta del .md y un posible límite de diapositivas del parámetro."""
        if not parametro:
            return None, None
        ruta, limite = None, None
        for parte in re.split(r"[;,]", str(parametro)):
            parte = parte.strip()
            if not parte:
                continue
            if re.fullmatch(r"\d+", parte):
                limite = int(parte)
            elif ruta is None:
                ruta = parte
        return ruta, limite

    def _limite_slides_config(self):
        """Límite de diapositivas opcional definido en config_usuario.json."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            valor = datos.get("max_slides_presentacion")
            return int(valor) if valor else None
        except Exception:
            return None

    def _finales_slides_config(self):
        """Nº de diapositivas de cierre (las últimas) que se conservan siempre.

        Se define en 'slides_finales_presentacion' de config_usuario.json; por
        defecto 6.
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            valor = datos.get("slides_finales_presentacion")
            return int(valor) if valor is not None else 6
        except Exception:
            return 6

    def _fijos_slides_config(self):
        """Nº de diapositivas iniciales de la plantilla que se conservan fijas.

        Se define en 'slides_fijos_presentacion' de config_usuario.json; por
        defecto 4 (portada, presentación, confidencialidad e inicio). Estas
        diapositivas se copian tal cual de la plantilla, sin tocar su contenido.
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            valor = datos.get("slides_fijos_presentacion")
            return int(valor) if valor is not None else 4
        except Exception:
            return 4

    def _colas_slides_config(self):
        """Nº de diapositivas finales de la plantilla que se conservan tal cual.

        Se define en 'slides_cola_plantilla_presentacion' de config_usuario.json;
        por defecto 4 (las diapositivas de cierre). Estas diapositivas se copian
        tal cual de la plantilla y quedan al final, después del contenido generado,
        sin tocar su contenido.
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            valor = datos.get("slides_cola_plantilla_presentacion")
            return int(valor) if valor is not None else 4
        except Exception:
            return 4


    def _buscar_plantilla(self):
        carpeta = rutas.PLANTILLAS
        if not os.path.isdir(carpeta):
            return None
        extensiones = (".pptx", ".pptm", ".potx")
        for f in os.listdir(carpeta):
            if f.lower().endswith(extensiones) and not f.startswith("~$"):
                return os.path.join(carpeta, f)
        return None

    def _resolver_md(self, ruta=None):
        """Localiza el .md que se usará para generar la presentación.

        - Si se indica una ruta que existe, se usa tal cual.
        - Si se indica solo un nombre (o una ruta que ya no existe), se busca
          ese nombre (con o sin '.md') en las carpetas conocidas de Jarvis
          (presentaciones, documentos y preventa).
        - Sin ruta, se usa el .md más reciente de 'presentaciones'.

        Devuelve la ruta del .md o None si no lo encuentra.
        """
        if ruta:
            if os.path.exists(ruta):
                return ruta
            nombre = os.path.basename(str(ruta).strip()).lower()
            nombres = {nombre}
            if not nombre.endswith(".md"):
                nombres.add(nombre + ".md")
            for carpeta in (rutas.PRESENTACIONES, rutas.DOCUMENTOS, rutas.PREVENTA):
                if not os.path.isdir(carpeta):
                    continue
                for f in os.listdir(carpeta):
                    if f.lower() in nombres:
                        return os.path.join(carpeta, f)
            return None
        return self._buscar_md_reciente()

    def _buscar_md_reciente(self):
        carpeta = rutas.PRESENTACIONES
        if not os.path.isdir(carpeta):
            return None
        mds = [os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.lower().endswith(".md")]
        if not mds:
            return None
        return max(mds, key=os.path.getmtime)