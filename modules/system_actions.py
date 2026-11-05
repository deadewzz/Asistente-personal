import os
import re
import sys
import json
import webbrowser
import urllib.parse
import urllib.request
import unicodedata
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
from modules.spotify import ErrorSpotify, Spotify
from modules.meeting_assistant import MeetingAssistant
from modules.calendario_tools import CalendarioTools
from modules.preventa_tools import PreventaTools
from modules.cloud_matrix import CloudMatrix
from modules.archivos import Explorador
from modules.sharepoint import SharePoint
from modules.progreso import Progreso
from modules.english_tutor import EnglishTutor
from modules.programming_tutor import ProgrammingTutor
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

    # Plataformas de `REPRODUCIR_MUSICA|plataforma:consulta`: por defecto Spotify
    # (la canción de verdad); 'youtube' es el vídeo y 'brave' la búsqueda en la web.
    PLATAFORMAS_MUSICA = {"spotify", "app", "youtube", "yt", "brave", "web"}

    #: Ejecutable de la aplicación de Spotify. Hace falta porque **con música
    #: sonando su ventana se titula con la canción** («Fuerza Regida - EXCESOS»): ahí
    #: no hay ninguna pista del nombre de la app. Así se sabe qué está sonando de
    #: verdad, sin creerse lo que diga el reproductor.
    PROCESO_SPOTIFY = "spotify.exe"

    #: Resolver la canción **sin claves de API**: el buscador devuelve el enlace de
    #: Spotify y la ficha pública (`oembed`, que no necesita sesión) confirma el
    #: título. Es lo que permite abrir *esa* pista en vez de dejar una búsqueda
    #: escrita, que no suena hasta que alguien le da al play.
    BUSCADOR_PISTAS = "https://lite.duckduckgo.com/lite/?q="
    FICHA_PISTA = "https://open.spotify.com/oembed?url="
    RESTOS_PISTA = re.compile(r"open\.spotify\.com/(track|album|playlist|artist)/"
                              r"([A-Za-z0-9]{22})")
    AGENTE_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Jarvis/1.0")

    #: Página del reproductor web: es donde suena una pista abierta por enlace, y se
    #: controla por CDP como SharePoint (`navegador_cdp`). Al hablar con el DOM se
    #: puede *comprobar* el resultado en vez de pulsar teclas a ciegas, que es lo que
    #: acababa escribiendo en la ventana equivocada.
    PAGINA_REPRODUCTOR = "open.spotify.com"

    #: Pulsar el play de la pista y esperar a que el propio reproductor lo confirme
    #: (el botón pasa de «Reproducir»/«Play» a «Pausa»/«Pause»).
    JS_REPRODUCIR = """
    (async () => {
      const dormir = (ms) => new Promise((listo) => setTimeout(listo, ms));
      const buscar = (selector, intentos, ms) => new Promise(async (listo) => {
        for (let i = 0; i < intentos; i++) {
          const nodo = document.querySelector(selector);
          if (nodo) { return listo(nodo); }
          await dormir(ms);
        }
        listo(null);
      });
      const suena = (nodo) => {
        const etiqueta = (nodo && nodo.getAttribute('aria-label') || '').toLowerCase();
        return etiqueta.startsWith('paus');
      };
      if (document.querySelector('[data-testid="login-button"]')) {
        return {ok: false, motivo: 'la sesion del reproductor web no esta abierta'};
      }
      const boton = await buscar('[data-testid="play-button"]', 40, 500);
      if (!boton) {
        return {ok: false, motivo: 'no encontre el boton de reproducir'};
      }
      if (!suena(boton)) { boton.click(); }
      const confirmado = await buscar(
        '[data-testid="play-button"][aria-label^="Paus"], ' +
        '[data-testid="play-button"][aria-label^="paus"]', 30, 500);
      return {ok: !!confirmado, motivo: confirmado ? 'suena' : 'el reproductor no arranco'};
    })()
    """

    #: Órdenes de `MUSICA|...` (pausa, siguiente canción...): la tecla multimedia
    #: (funciona con cualquier reproductor, sin tocar ventanas), el mando del
    #: reproductor web cuando se puede usar el DOM y lo que se cuenta después.
    #: Las claves se buscan primero completas ('pausa la música') y, si no, por la
    #: primera palabra ('siguiente canción' -> 'siguiente').
    ORDENES_MUSICA = {
        "pausa": ("playpause", "control-button-playpause",
                  "Hecho: dejo la música en pausa o la reanudo."),
        "para": ("playpause", "control-button-playpause",
                 "Hecho: dejo la música en pausa o la reanudo."),
        "parar": ("playpause", "control-button-playpause",
                  "Hecho: dejo la música en pausa o la reanudo."),
        "reanudar": ("playpause", "control-button-playpause",
                     "Hecho: dejo la música en pausa o la reanudo."),
        "continuar": ("playpause", "control-button-playpause",
                      "Hecho: dejo la música en pausa o la reanudo."),
        "sigue": ("playpause", "control-button-playpause",
                  "Hecho: dejo la música en pausa o la reanudo."),
        "siguiente": ("nexttrack", "control-button-skip-forward",
                      "Cambio a la siguiente canción."),
        "salta": ("nexttrack", "control-button-skip-forward",
                  "Cambio a la siguiente canción."),
        "siguiente cancion": ("nexttrack", "control-button-skip-forward",
                              "Cambio a la siguiente canción."),
        "anterior": ("prevtrack", "control-button-skip-back",
                     "Vuelvo a la canción anterior."),
        "atras": ("prevtrack", "control-button-skip-back",
                  "Vuelvo a la canción anterior."),
        "vuelve": ("prevtrack", "control-button-skip-back",
                   "Vuelvo a la canción anterior."),
    }

    #: Esperas: resolver la canción en la web, comprobar que está sonando y que el
    #: reproductor web cargue y confirme el play.
    ESPERA_PISTA = 15.0
    ESPERA_MUSICA = 12.0
    ESPERA_REPRODUCTOR_WEB = 90.0

    #: Palabras que no distinguen una canción de otra al comparar títulos.
    PALABRAS_VACIAS = {"de", "del", "la", "las", "el", "los", "y", "a", "al", "en",
                       "un", "una", "the", "of", "feat", "ft", "con"}

    #: Qué se le cuenta al usuario mientras una acción tarda. Es lo que aparece en
    #: el indicador de la ventana en lugar de un "escribiendo..." a secas, así que
    #: solo están las acciones que de verdad se toman su tiempo (red, navegador,
    #: IA, Office, terminal): en las instantáneas un rótulo que sale y entra no
    #: aporta nada.
    PROGRESO_ACCIONES = {
        "BUSCAR": "Buscando en internet con Brave…",
        "REPRODUCIR_VIDEO": "Buscando el vídeo y abriéndolo…",
        "REPRODUCIR_MUSICA": "Poniendo la canción en Spotify…",
        "CLIMA": "Consultando el tiempo…",
        "BRIEFING": "Preparando tu briefing: tiempo, correo y agenda…",
        "PERFIL": "Activando tu perfil de trabajo…",
        "BUSCAR_ARCHIVOS": "Buscando archivos por el disco (subcarpetas incluidas)…",
        "BUSCAR_EN_CARPETA": "Buscando dentro de la carpeta (subcarpetas incluidas)…",
        "MOVER_ARCHIVOS": "Moviendo los archivos…",
        "COPIAR_ARCHIVOS": "Copiando los archivos…",
        "LISTAR_SHAREPOINT": "Leyendo la carpeta de SharePoint (subcarpetas incluidas)…",
        "CLASIFICAR_ARCHIVOS": "Revisando la carpeta de SharePoint antes de clasificar…",
        "EJECUTAR_TERMINAL": "Ejecutando el comando en la terminal…",
        "LEER_CORREOS": "Entrando en tu correo y leyendo los últimos…",
        "RESUMEN_CORREOS": "Repasando tu correo…",
        "BUSCAR_CORREOS": "Buscando esos correos…",
        "CORREO_PENDIENTES": "Mirando qué tienes pendiente en el correo…",
        "LEER_CORREO": "Abriendo el correo…",
        "RESPONDER_CORREO": "Escribiendo la respuesta…",
        "ENVIAR_BORRADOR": "Enviando el correo…",
        "ETIQUETAR_CORREO": "Etiquetando el correo…",
        "ARCHIVAR_CORREO": "Archivando el correo…",
        "MARCAR_CORREO": "Marcando el correo…",
        "ELIMINAR_CORREO": "Eliminando el correo…",
        "CREAR_DOCUMENTO": "Creando el documento…",
        "CREAR_BORRADOR": "Creando el borrador…",
        "CREAR_PRESENTACION": "Montando la presentación…",
        "REEMPLAZAR_LOGOS_PPT": "Reemplazando los logos de la presentación…",
        "GENERAR_PREVENTA": "Generando el documento con la IA…",
        "MATRIZ_NUBE": "Actualizando la matriz en la nube…",
        "MATRIZ_EXCEL": "Actualizando la matriz en Excel…",
        "MATRIZ_AZURE": "Actualizando la matriz en Azure DevOps…",
        "GRABAR_REUNION": "Empezando a grabar la reunión…",
        "TERMINAR_REUNION": "Cerrando la grabación y guardando el acta…",
        "REUNIONES": "Listando tus actas guardadas…",
        "LEER_ACTA": "Buscando el acta…",
        "REHACER_ACTA": "Rehaciendo el acta con la IA…",
        "ASISTENTES_REUNION": "Mirando quién estaba en la reunión…",
        "ENVIAR_ACTA": "Enviando el acta a los asistentes…",
        "AGENDA_REUNION": "Preparando la agenda de la reunión…",
    }

    #: Documentos que se le mandan a la IA de una vez al clasificar. El prompt lleva
    #: el texto de dentro (hasta 900 caracteres por archivo), así que con decenas de
    #: documentos una sola llamada se alarga, cuesta y se corta a medias: por lotes
    #: cada llamada es corta, se ve cómo avanza y caben todos.
    LOTE_IA = 25

    #: Canal de progreso de respaldo. La ventana conecta el suyo en `__init__`;
    #: está también en la clase para que las pruebas que montan solo un trozo del
    #: objeto (sin pasar por `__init__`) no revienten al informar de un paso.
    progreso = Progreso()

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self.progreso = Progreso()
        self.office_tool = OfficeAutomation()
        self.productivity = ProductivityTools(config_path)
        self.dev = DevTools(config_path)
        self.outlook = crear_cliente_correo(config_path)
        # Música: con la cuenta de Spotify conectada, el asistente pone las canciones
        # por la API (sin abrir ventanas ni tocar el teclado, así que se puede pedir
        # una canción en mitad de una partida). Sin conexión, este cliente no se usa
        # nunca y la música sigue por el camino de siempre.
        self.spotify = Spotify(config_path)
        self.meeting = MeetingAssistant(config_path)
        self.calendario = CalendarioTools()
        self.preventa = PreventaTools()
        self.cloud = CloudMatrix(config_path)
        self.archivos = Explorador()
        self.sharepoint = SharePoint()
        # SharePoint y el resto de herramientas cuentan por el mismo canal: un
        # solo sitio donde la ventana escucha (y nada que reconectar si cambia).
        self.sharepoint.progreso = self.progreso
        # Tutor de inglés: detecta los errores en local (sin gastar IA) y prepara
        # la clase. Lo usa el apartado «Clase de inglés» de la ventana (no el
        # chat) y guarda el nivel y los errores repetidos en `Jarvis/ingles`.
        self.ingles = EnglishTutor(config_path)
        # Taller de programación: corrige en local con su analizador y con `javac`
        # (sin gastar IA) y guarda el nivel y los fallos repetidos en
        # `Jarvis/programacion`. Lo usa el apartado «Aprender programación».
        self.programacion = ProgrammingTutor(config_path)

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

        # Antes de arrancar se dice qué se va a hacer: las acciones largas dejan de
        # ser un "escribiendo..." mudo (ver PROGRESO_ACCIONES).
        descripcion = self.PROGRESO_ACCIONES.get(accion)
        if descripcion:
            self.progreso.paso(descripcion)

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
        elif accion == "LISTAR_SHAREPOINT":
            return self._listar_sharepoint(parametro_libre or "")
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
        elif accion == "REPRODUCIR_MUSICA":
            return self.reproducir_musica(parametro_libre or parametro or "")
        elif accion == "MUSICA":
            return self.control_musica(parametro_libre or parametro or "")
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

    @staticmethod
    def _resumen_listado(origen, listado):
        """Qué se revisó: carpetas, documentos y lo que se dejó fuera.

        Se enseña antes del resultado para que se vea que también se miró dentro
        de las subcarpetas y que Excel, PDF o vídeo se ignoran a propósito (no se
        pierden: se quedan donde estaban). Si se pidió un filtro por nombre
        (``solo``), también se dice cuántos documentos quedaron fuera por él.
        """
        archivos = listado.get("archivos") or []
        ignorados = listado.get("ignorados") or []
        excluidos = listado.get("excluidos") or []
        carpetas = listado.get("carpetas") or 0
        if not archivos:
            if excluidos:
                detalle = "\n".join(f"  · {n}" for n in excluidos[:10])
                if len(excluidos) > 10:
                    detalle += f"\n  · … y {len(excluidos) - 10} más"
                return (f"No hay documentos de Word o PowerPoint que coincidan "
                        f"con tu filtro en {origen} (miré dentro de {carpetas} "
                        f"carpeta(s), subcarpetas incluidas). Estos "
                        f"{len(excluidos)} sí están, pero no coinciden:\n{detalle}")
            if ignorados:
                detalle = "\n".join(f"  · {n}" for n in ignorados[:10])
                if len(ignorados) > 10:
                    detalle += f"\n  · … y {len(ignorados) - 10} más"
                return (f"No hay documentos de Word o PowerPoint en {origen} "
                        f"(miré dentro de {carpetas} carpeta(s), subcarpetas "
                        f"incluidas). Estos {len(ignorados)} no son de Word ni "
                        f"de PowerPoint:\n{detalle}")
            return (f"No hay archivos en {origen} (ni en sus subcarpetas: "
                    f"{carpetas} carpeta(s)).")
        lineas = [f"Revisé {carpetas} carpeta(s), subcarpetas incluidas: "
                  f"{len(archivos)} documento(s) de Word/PowerPoint."]
        if ignorados:
            muestra = ", ".join(ignorados[:6])
            lineas.append(f"  (no son de Word ni de PowerPoint, se quedan donde "
                          f"están: {len(ignorados)}; {muestra}"
                          + (", …" if len(ignorados) > 6 else "") + ")")
        if excluidos:
            muestra = ", ".join(excluidos[:6])
            lineas.append(f"  (con tu filtro dejo fuera {len(excluidos)} "
                          f"documento(s): {muestra}"
                          + (", …" if len(excluidos) > 6 else "") + ")")
        if listado.get("truncado"):
            lineas.append(f"  (me paré al llegar a {len(archivos)} documentos: "
                          "para los que falten, pásame la subcarpeta exacta)")
        for fallo in (listado.get("fallos") or [])[:5]:
            lineas.append(f"  (no pude mirar dentro de {fallo})")
        return "\n".join(lineas)

    def _listar_sharepoint(self, parametro):
        """LISTAR_SHAREPOINT|url;;filtro

        Enseña qué hay dentro de una carpeta de SharePoint/OneDrive —subcarpetas
        incluidas y solo documentos de Word y PowerPoint— **sin mover nada**.
        Con un filtro (``;;acta`` o ``;;2026, informe``) se queda con los que
        coincidan: así se elige uno concreto antes de clasificar.

        Usa la misma sesión de Brave que CLASIFICAR_ARCHIVOS (controlado por CDP,
        sin Microsoft Graph): el navegador firma las peticiones con tu sesión.
        """
        partes = (parametro or "").split(";;", 1)
        origen = partes[0].strip() if partes else ""
        filtro = partes[1].strip() if len(partes) > 1 else ""
        if not origen:
            return ("Necesito la URL de la carpeta de SharePoint/OneDrive, "
                    "LISTAR_SHAREPOINT|https://.../sites/Sitio/Carpeta")
        try:
            nota = self.sharepoint.asegurar_navegador(origen)
            listado = self.sharepoint.listar_documentos(origen, solo=filtro)
        except Exception as e:
            return f"No pude acceder a la carpeta de SharePoint.\n{e}"
        detalle = self._resumen_listado(origen, listado)
        archivos = listado["archivos"]
        aviso = "" if nota.startswith("Brave ya estaba") else f"{nota}\n"
        if not archivos:
            return f"{aviso}{detalle}"
        lineas = [f"{i}. {a['rel']}" for i, a in enumerate(archivos, 1)]
        return (f"{aviso}{detalle}\n" + "\n".join(lineas)
                + "\nDime cuál quieres clasificar (el número o parte del nombre) "
                  "y la carpeta de destino, y muevo solo ese. Y si los quieres "
                  "todos de una vez, no hace falta que elijas uno por uno: "
                  "dímelo con la regla ('clasifícalos todos así: ...') y se "
                  "reparten de golpe.")

    def _clasificar_archivos(self, parametro):
        """CLASIFICAR_ARCHIVOS|origen_url;;destino_url;;regla;;solo_estos;;banderas

        Revisa la URL de origen (SharePoint/OneDrive) con la **sesión real de
        Brave** (controlado por CDP; el navegador firma las peticiones), bajando
        también por sus **subcarpetas**, y se queda solo con los documentos de
        Word y PowerPoint (`.docx`, `.doc`, `.pptx`, `.ppt`): Excel, PDF, vídeo y
        demás se ignoran y se informan. Los clasifica según la regla con la IA y
        los reparte por subcarpetas de la URL de destino. Todo sin Microsoft
        Graph.

        El cuarto campo (opcional) limita el trabajo a los documentos que
        coincidan por nombre o subcarpeta (``;;acta``), para probar con uno solo.

        Por defecto se **lee el contenido** de cada documento (se baja con la
        pestaña de su sitio, sin pasar por disco) y se le da a la IA un extracto
        junto a su nombre: así un ``Documento1.docx`` se coloca por lo que pone
        dentro y no por lo que se llame (ver `SharePoint.leer_textos`). Lo que no
        se pueda leer (un ``.doc`` antiguo, uno enorme, uno sin texto) va por su
        nombre, como antes, y se avisa en el resumen. Con ``;;sin leer`` (o con
        «solo por el nombre» en la regla) no se lee nada: va más rápido, pero
        acierta menos.

        Al clasificar se le pasan a la IA **las carpetas que ya existen en el
        destino**, para que elija entre ellas en vez de inventarse nombres (una
        'QA' nueva al lado de la que hay). Lo que conteste se encaja después con
        esas carpetas, y lo que llegue sin carpeta va a 'Otros': así ningún
        archivo se queda suelto en la raíz del destino.

        La regla puede pedir también que algunos se queden donde están («deja un
        Word y un PowerPoint por carpeta y los demás no los toques»): el
        clasificador los marca como ``dejar`` y no se tocan (ver
        `SharePoint.es_dejar`), así que en una sola pasada se reparte unos
        cuantos y el resto se queda quieto.

        Si la orden pide **copiar** (o se añade ``;;copiar`` al final), no se
        mueve nada: se deja una copia en cada carpeta y los originales se quedan
        donde estaban (ver `SharePoint.clasificar_y_mover`).

        El destino puede estar en **otro sitio** (p. ej. tu OneDrive) aunque
        SharePoint no deje mover entre sitios: en ese caso se copia con el
        navegador y, si no es una copia, el original va a la papelera (ver
        `sharepoint.SharePoint.mover_entre_sitios`).

        Si Brave no está abierto se abre; si lo está sin depuración, se
        reinicia con aviso (las cookies de sesión de SharePoint son persistentes,
        así que no se pierde el inicio de sesión).
        """
        partes = (parametro or "").split(";;", 4)
        origen = partes[0].strip() if partes else ""
        destino = partes[1].strip() if len(partes) > 1 else ""
        regla = partes[2].strip() if len(partes) > 2 else ""
        solo = partes[3].strip() if len(partes) > 3 else ""
        bandera = partes[4].strip() if len(partes) > 4 else ""
        if not origen or not destino:
            return ("Necesito la URL de origen y la de destino: "
                    "CLASIFICAR_ARCHIVOS|origen;;destino;;regla")
        # El cuarto campo es el filtro (';;acta'), pero ahí se escribe lo que uno
        # recuerda: ';;copiar' copia y ';;sin leer' va por el nombre. Cuando el
        # campo ENTERO es una de esas órdenes, no hay filtro que valga.
        copiar = (SharePoint.quiere_copiar(solo)
                  or SharePoint.quiere_copiar(bandera)
                  or SharePoint.quiere_copiar(regla))
        sin_leer = (SharePoint.quiere_sin_leer(solo)
                    or SharePoint.quiere_sin_leer(bandera)
                    or SharePoint.quiere_sin_leer(regla))
        if SharePoint.es_bandera(solo):
            solo = ""
        try:
            nota = self.sharepoint.asegurar_navegador(origen)
            listado = self.sharepoint.listar_documentos(origen, solo=solo)
        except Exception as e:
            return (f"No pude acceder a la carpeta de SharePoint.\n{e}")
        detalle = self._resumen_listado(origen, listado)
        archivos = listado["archivos"]
        if not archivos:
            return detalle
        # Las carpetas del destino se leen ANTES de clasificar: son las
        # candidatas entre las que elegir, y lo que evita que se cree una carpeta
        # nueva con un nombre que ya existe.
        carpetas, fallo_carpetas = self._carpetas_destino(destino)
        # El plan va con la ruta relativa de cada documento ('2026/Acta.pptx'),
        # para que el reparto acierte con la subcarpeta en la que está de verdad.
        nombres = [a["rel"] for a in archivos]
        clasificador = getattr(self.sharepoint, "on_clasificar", None)
        # Leer el contenido es lo que hace buena la clasificación (un nombre no
        # dice nada), pero cuesta una bajada por documento: con ';;sin leer' se va
        # por el nombre, que es lo de antes.
        textos, avisos_lectura, leidos = {}, [], 0
        if clasificador and not sin_leer:
            try:
                textos, avisos_lectura, leidos = self.sharepoint.leer_textos(
                    origen, archivos)
            except Exception as e:
                avisos_lectura = [f"  · No pude leer el contenido de los documentos "
                                  f"({e}): los clasifico por su nombre"]
        avisos = []
        if clasificador:
            plan = self._plan_con_ia(clasificador, nombres, regla, carpetas, textos)
            if plan is None:
                return "No pude clasificar: configura tu API Key (DeepSeek) primero."
            plan, avisos = SharePoint.encajar_plan(plan, carpetas)
        else:
            plan = self.sharepoint.clasificar_naive(nombres, regla)
        try:
            resumen = self.sharepoint.clasificar_y_mover(origen, destino, plan,
                                                         copiar=copiar)
        except Exception as e:
            return f"Error {'copiando' if copiar else 'moviendo'} los archivos: {e}"
        lineas = []
        if not nota.startswith("Brave ya estaba"):
            lineas.append(nota)
        lineas.append(detalle)
        if fallo_carpetas:
            lineas.append(fallo_carpetas)
        if leidos or avisos_lectura:
            lineas.append(f"Leí el contenido de {leidos} de {len(archivos)} "
                          "documento(s) para colocarlos mejor.")
        lineas += avisos_lectura
        lineas += avisos
        if sin_leer and clasificador:
            lineas.append("Modo rápido: clasifico por el nombre de los archivos, "
                          "sin leer lo que hay dentro.")
        if copiar:
            lineas.append(f"Modo copiar: dejo una copia en cada carpeta "
                          f"({len(carpetas)} en el destino) y los originales se "
                          "quedan donde estaban.")
        lineas.append(resumen)
        return "\n".join(lineas)

    def _plan_con_ia(self, clasificador, nombres, regla, carpetas, textos):
        """El reparto que propone la IA, por lotes si hay muchos documentos.

        El prompt lleva el texto de dentro de cada documento, así que con decenas
        de ellos una llamada sola se alarga y cuesta: se parte en lotes de
        `LOTE_IA` documentos y se pegan los trozos. Devuelve el plan entero, o
        None si la IA no contesta (sin API Key o sin conexión), que es lo que mira
        quien llama para decidir si sigue con el reparto de respaldo.

        A cada lote se le pasan **solo sus** textos ('textos' es {nombre: extracto})
        para que el prompt no crezca de más.
        """
        lotes = [nombres[i:i + self.LOTE_IA]
                 for i in range(0, len(nombres), self.LOTE_IA)] or [[]]
        plan = []
        for numero, lote in enumerate(lotes, start=1):
            if len(lotes) > 1:
                self.progreso.paso(f"Clasificando el lote {numero} de {len(lotes)} "
                                   f"({len(lote)} documento(s))")
            trozo = clasificador(lote, regla, carpetas,
                                 {n: textos[n] for n in lote if n in textos})
            if trozo is None:
                return None
            plan.extend(trozo)
        return plan

    def _carpetas_destino(self, destino):
        """Las subcarpetas que YA existen en el destino (y el aviso si no se pudo).

        Son las candidatas entre las que elige la IA. Sin esta lista se inventa
        el nombre ('QA' cuando la carpeta se llama 'Quality Assurance') y, como
        crear una carpeta que existe no da error, se acaba creando una segunda al
        lado de la que ya hay. Devuelve ``(carpetas, aviso)``.
        """
        try:
            carpetas = [c.get("nombre", "")
                        for c in self.sharepoint.listar_carpetas(destino)]
        except Exception as e:
            return [], (f"No pude leer las carpetas del destino, así que la IA "
                        f"puede crear nombres nuevos: {e}")
        tecnicas = getattr(self.sharepoint, "CARPETAS_TECNICAS",
                           SharePoint.CARPETAS_TECNICAS)
        return [c for c in carpetas
                if c and c.lower() not in tecnicas], ""

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

    # ------------------------------------------------------------------ Música
    def reproducir_musica(self, parametro=None):
        """Pone música: por defecto, en la aplicación de Spotify.

        `REPRODUCIR_MUSICA|artista canción`, `REPRODUCIR_MUSICA|youtube:consulta`
        (el vídeo de YouTube, igual que `REPRODUCIR_VIDEO`) o
        `REPRODUCIR_MUSICA|brave:consulta` (la búsqueda en la web, igual que
        `BUSCAR|spotify:consulta`).
        """
        texto = str(parametro or "").strip()
        plataforma = ""
        if ":" in texto:
            posible, _, resto = texto.partition(":")
            if posible.strip().lower() in self.PLATAFORMAS_MUSICA:
                plataforma = posible.strip().lower()
                texto = resto.strip()
        if not texto:
            return "Dime qué canción quieres poner."
        if plataforma in ("youtube", "yt"):
            return self.reproducir_video_youtube(texto, 0)
        if plataforma in ("brave", "web"):
            return self.buscar_en_brave(texto, "spotify")
        return self.reproducir_en_spotify(texto)

    def _spotify_api(self):
        """La sesión de la API de Spotify, si está conectada (None si no).

        Se usa el cliente del propio asistente (aquí no se crea ninguno) para que
        las pruebas puedan cambiarlo por un doble sin tocar la sesión de verdad.
        """
        cliente = getattr(self, "spotify", None)
        try:
            return cliente if cliente is not None and cliente.disponible() else None
        except Exception as e:
            print(f"No pude comprobar la sesión de Spotify ({e}).")
            return None

    def reproducir_en_spotify(self, consulta):
        """Pone una canción en Spotify, y solo dice que suena si de verdad suena.

        Primero por la **API oficial** (si la cuenta está conectada): se resuelve la
        pista, se le manda al dispositivo y Spotify confirma que suena. Eso no abre
        ninguna ventana ni toca el teclado, así que se puede pedir una canción con un
        juego en primer plano. Si no hay sesión conectada —o Spotify no deja (sin
        Premium, sin dispositivo)— se sigue por el camino de siempre: resolver la
        pista y dejarla cargada en el reproductor, que suena en cuanto alguien le da
        al play.
        """
        texto = self._consulta_legible(consulta)
        api = self._spotify_api()
        if api is None:
            return self._reproducir_sin_api(texto)
        respuesta, seguir = self._poner_con_api(api, texto)
        if not seguir:
            return respuesta
        return f"{respuesta} {self._reproducir_sin_api(texto)}"

    def _poner_con_api(self, api, texto):
        """Pone la canción por la API: (lo que se cuenta, ¿seguir por la web?).

        Se sigue por la web cuando la API no pudo por algo que el camino clásico sí
        puede salvar: sin Premium no deja controlar la reproducción, pero la pista se
        puede dejar cargada. Si la API simplemente no encuentra la canción, se dice y
        ya está: el buscador no va a encontrar nada mejor.
        """
        try:
            pista = api.buscar_pista(texto)
        except ErrorSpotify as e:
            return f"No pude buscar la canción en Spotify ({self._sin_punto(e)})", True
        if pista is None:
            return f"No encuentro «{texto}» en Spotify.", False
        try:
            resultado = api.poner_pista(pista["uri"], pista["titulo"])
        except ErrorSpotify as e:
            return f"No pude poner la canción en Spotify ({self._sin_punto(e)})", True
        if not resultado.get("ok"):
            motivo = self._sin_punto(resultado.get("motivo") or "")
            return f"No pude ponerla sola: {motivo or 'Spotify no lo confirmó'}.", True
        sonando = resultado.get("pista") or {}
        titulo = sonando.get("titulo") or pista["titulo"]
        artista = sonando.get("artista") or pista["artista"]
        de_quien = f" de {artista}" if artista else ""
        donde = f" ({resultado['dispositivo']})" if resultado.get("dispositivo") else ""
        return f"Poniendo «{titulo}»{de_quien} en Spotify{donde}.", False

    @staticmethod
    def _sin_punto(texto):
        """El motivo sin el punto final: se encaja dentro de otra frase."""
        return str(texto or "").strip().rstrip(".").strip()

    def _reproducir_sin_api(self, texto):
        """Poner la canción sin la API: resolver la pista y dejarla cargada.

        El camino es: resolver la **pista exacta** (título y enlace) y abrirla en el
        reproductor web, que es el que arranca una canción abierta por enlace. Antes se
        dejaba la búsqueda escrita y se pulsaba Enter con la ventana delante, y eso no
        reproduce nada (el Enter solo confirma la búsqueda): si el foco cambiaba en ese
        instante, el teclazo acababa incluso en otra ventana.
        """
        pista = self._pista_en_spotify(texto)
        if pista is None:
            return self._dejar_busqueda_en_spotify(texto)
        titulo, enlace = pista
        if self._arrancar_en_reproductor_web(enlace):
            return f"Poniendo «{titulo}» en Spotify."
        self._abrir_url_brave(enlace)
        if self._sonando_en_spotify(titulo):
            return f"Poniendo «{titulo}» en Spotify."
        return (f"Te dejo «{titulo}» cargada en el reproductor web de Spotify: dale "
                "al play.")

    @staticmethod
    def _consulta_legible(consulta):
        """La búsqueda tal cual se pidió, aunque venga codificada como una URL.

        La IA a veces manda «Junior+H+Las+noches» (o con `%20`), y eso acaba escrito
        así, con símbolos raros, en el buscador de Spotify.
        """
        texto = str(consulta or "").strip()
        if "%" in texto:
            texto = urllib.parse.unquote(texto)
        if " " not in texto and "+" in texto:
            texto = texto.replace("+", " ")
        return re.sub(r"\s+", " ", texto).strip()

    def _pista_en_spotify(self, consulta):
        """La canción de Spotify que corresponde a la consulta: (título, enlace).

        Se resuelve por la web, sin claves de API: el buscador devuelve el enlace de
        Spotify y la ficha pública (`oembed`, que no pide sesión) confirma el título.
        Así se puede decir *qué* canción es en vez de dar por hecho que es la pedida.
        None si no se pudo resolver (red caída, sin resultados...).
        """
        try:
            html = self._descargar(self.BUSCADOR_PISTAS + urllib.parse.quote_plus(
                f"site:open.spotify.com {consulta}"))
        except Exception as e:
            print(f"No pude buscar la canción en la web ({e}).")
            return None
        # El buscador esconde los enlaces dentro de su redirector codificado
        # (`...uddg=https%3A%2F%2Fopen.spotify.com%2Ftrack%2F...`): se leen tal cual.
        encontrados = self.RESTOS_PISTA.findall(urllib.parse.unquote(html))
        if not encontrados:
            print(f"La búsqueda de «{consulta}» no dejó ninguna pista de Spotify.")
            return None
        # Primero canciones: es lo que se ha pedido. Si no hay, lo que aparezca.
        pistas = [enlace for enlace in encontrados if enlace[0] == "track"]
        tipo, identificador = (pistas or encontrados)[0]
        enlace = f"https://open.spotify.com/{tipo}/{identificador}"
        return (self._titulo_de_pista(enlace) or consulta), enlace

    def control_musica(self, orden=None):
        """Pausa, reanuda, salta o vuelve atrás en lo que esté sonando.

        Con Spotify conectado la orden va por la API y Spotify confirma que la hizo
        (eso no toca el teclado ni ninguna ventana, así que vale con un juego en
        primer plano). Si no, se usa el reproductor web cuando se controla por CDP y,
        como último recurso, la tecla multimedia del reproductor que esté sonando.
        """
        clave = re.sub(r"\s+", " ", str(orden or "").strip().lower())
        if not clave:
            clave = "pausa"
        elegida = (self.ORDENES_MUSICA.get(clave)
                   or self.ORDENES_MUSICA.get(clave.split(" ")[0]))
        if not elegida:
            return "Para la música dime pausa, reanudar, siguiente o anterior."
        tecla, mando_web, texto = elegida
        api = self._spotify_api()
        if api is not None:
            respuesta = self._controlar_con_api(api, clave)
            if respuesta:
                return respuesta
        if self._controlar_reproductor_web(mando_web):
            return texto
        try:
            pyautogui.press(tecla)
        except Exception as e:
            return f"No pude controlar la música: {e}"
        return texto

    def _controlar_con_api(self, api, clave):
        """Manda la orden a Spotify por la API. '' si esa orden no es de música."""
        primera = clave.split(" ")[0]
        if primera in ("pausa", "para", "parar"):
            mando, hecho = api.pausar, "dejo «{0}» en pausa"
        elif primera in ("reanudar", "continuar", "sigue"):
            mando, hecho = api.reanudar, "sigue «{0}»"
        elif primera in ("siguiente", "salta"):
            mando, hecho = api.siguiente, "cambio a «{0}»"
        elif primera in ("anterior", "atras", "vuelve"):
            mando, hecho = api.anterior, "vuelvo a «{0}»"
        else:
            return ""
        try:
            resultado = mando()
        except ErrorSpotify as e:
            print(f"No pude mandar «{clave}» a Spotify ({e}).")
            return ""
        if not resultado.get("ok"):
            motivo = str(resultado.get("motivo") or "").strip()
            return f"No pude: {motivo}" if motivo else ""
        aviso = str(resultado.get("motivo") or "").strip()
        if aviso:
            return aviso                   # «ya estaba en pausa», sin adornos
        titulo = ((resultado.get("pista") or {}).get("titulo") or "").strip()
        return "Hecho: " + hecho.format(titulo or "la canción") + "."

    @staticmethod
    def _uri_spotify_search(consulta):
        """Enlace que abre la aplicación de Spotify con esa búsqueda escrita."""
        return "spotify:search:" + urllib.parse.quote(str(consulta).strip())

    @staticmethod
    def _abrir_uri_spotify(uri):
        """Lanza el enlace de Spotify. False si no hay ninguna aplicación asociada."""
        try:
            os.startfile(uri)
            return True
        except Exception as e:
            print(f"No pude abrir la aplicación de Spotify ({e}).")
            return False

    def _titulo_de_pista(self, enlace):
        """Título de esa pista según la ficha pública de Spotify (sin sesión)."""
        try:
            ficha = self._descargar(self.FICHA_PISTA
                                    + urllib.parse.quote(enlace, safe=""))
            return str(json.loads(ficha).get("title") or "").strip()
        except Exception as e:
            print(f"No pude leer la ficha de la pista ({e}).")
            return ""

    def _descargar(self, direccion):
        """Contenido de una dirección de la web, con cabecera de navegador."""
        peticion = urllib.request.Request(direccion,
                                          headers={"User-Agent": self.AGENTE_WEB})
        with urllib.request.urlopen(peticion, timeout=self.ESPERA_PISTA) as respuesta:
            return respuesta.read().decode("utf-8", "replace")

    def _arrancar_en_reproductor_web(self, enlace):
        """Le da al play de esa pista en la pestaña controlada de Brave.

        Solo se intenta si Brave está abierto **con** depuración (como cuando se
        trabaja con SharePoint): entonces se puede pulsar el botón exacto del
        reproductor y leer si arrancó. Si no, esto devuelve False y quien llama deja
        el enlace abierto, que es mejor que adivinar dónde está el botón.
        """
        if navegador_cdp is None or not navegador_cdp.esta_activo():
            return False
        try:
            pestana = (navegador_cdp.pestana_de(self.PAGINA_REPRODUCTOR)
                       or navegador_cdp.Pestana(enlace).abrir())
            pestana.timeout = self.ESPERA_REPRODUCTOR_WEB
            estado = pestana.evaluar(self.JS_REPRODUCIR, navegar=enlace)
        except Exception as e:
            print(f"No pude manejar el reproductor web ({e}).")
            return False
        return bool(estado and estado.get("ok"))

    def _controlar_reproductor_web(self, mando):
        """Pulsa ese mando (pausa, siguiente...) en el reproductor web, si se puede."""
        if navegador_cdp is None or not navegador_cdp.esta_activo():
            return False
        try:
            pestana = navegador_cdp.pestana_de(self.PAGINA_REPRODUCTOR)
            if pestana is None:
                return False
            guion = ("(() => { const boton = document.querySelector("
                     + json.dumps(f'[data-testid="{mando}"]') + ");"
                     " if (!boton) { return {ok: false}; }"
                     " boton.click(); return {ok: true}; })()")
            estado = pestana.evaluar(guion)
        except Exception as e:
            print(f"No pude usar el reproductor web ({e}).")
            return False
        return bool(estado and estado.get("ok"))

    def _sonando_en_spotify(self, titulo):
        """True si la ventana de Spotify dice que esa canción está sonando.

        Con música sonando, el título de su ventana **es el de la canción**: es la
        única señal fiable de que suena de verdad (un reproductor puede tener la pista
        cargada y estar en silencio).
        """
        referencia = self._palabras(titulo)
        if not referencia:
            return False
        limite = time.time() + self.ESPERA_MUSICA
        while time.time() < limite:
            for ventana in self._ventanas_por_proceso(self.PROCESO_SPOTIFY):
                if referencia <= self._palabras(getattr(ventana, "title", "")):
                    return True
            time.sleep(1)
        return False

    @classmethod
    def _palabras(cls, texto):
        """Palabras que distinguen una canción de otra (sin acentos ni mayúsculas)."""
        limpio = unicodedata.normalize("NFKD", str(texto or "").lower())
        limpio = "".join(letra for letra in limpio
                         if not unicodedata.combining(letra))
        palabras = set(re.split(r"[^a-z0-9]+", limpio)) - {""}
        utiles = palabras - cls.PALABRAS_VACIAS
        return utiles or palabras

    def _dejar_busqueda_en_spotify(self, consulta):
        """Último recurso: dejar la búsqueda abierta y decir que falta el play."""
        if not self._abrir_uri_spotify(self._uri_spotify_search(consulta)):
            self._abrir_url_brave(self._url_busqueda(consulta, "spotify"))
            return (f"No encuentro la aplicación de Spotify, así que te dejo la "
                    f"búsqueda de «{consulta}» en el reproductor web: dale al play.")
        return (f"Te dejo «{consulta}» buscado en Spotify: dale al play del primer "
                "resultado.")

    @classmethod
    def _ventanas_por_proceso(cls, nombre_proceso):
        """Ventanas visibles cuyo proceso se llama así (lista vacía si no hay).

        Es lo que permite encontrar la ventana de Spotify cuando se titula con la
        canción, sin adivinar: si ese proceso no tiene ninguna ventana visible, la
        lista viene vacía y quien llame no pulsa nada.
        """
        if gw is None:
            return []
        pids = cls._pids_de(nombre_proceso)
        if not pids:
            return []
        try:
            ventanas = gw.getAllWindows()
        except Exception as e:
            print(f"No pude listar las ventanas abiertas: {e}")
            return []
        encontradas = []
        for ventana in ventanas:
            hwnd = getattr(ventana, "_hWnd", None)
            if hwnd is None or not (getattr(ventana, "title", "") or "").strip():
                continue
            if cls._pid_de_ventana(hwnd) in pids:
                encontradas.append(ventana)
        return encontradas

    @staticmethod
    def _pid_de_ventana(hwnd):
        """PID del proceso dueño de esa ventana (0 si no se puede averiguar)."""
        try:
            import ctypes
            import ctypes.wintypes as wintypes
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value
        except Exception as e:
            print(f"No pude averiguar el proceso de una ventana: {e}")
            return 0

    @staticmethod
    def _pids_de(nombre_proceso):
        """PIDs de los procesos que se llaman así (Spotify abre varios)."""
        pids = set()
        for proceso in psutil.process_iter(["name"]):
            if (proceso.info.get("name") or "").lower() == nombre_proceso:
                pids.add(proceso.pid)
        return pids

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