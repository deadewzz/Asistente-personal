"""Pruebas de la música: poner una canción en Spotify y controlar lo que suena.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_musica.py

No navega, no abre Spotify y no pulsa teclas de verdad: la web (buscador y ficha de la
pista), la API de Spotify (`modules.spotify`), Brave por CDP (`navegador_cdp`),
`os.startfile` y `pyautogui` se cambian por dobles de prueba y se comprueba qué
*habría* hecho. Lo que sí se prueba de verdad es lo que importa:

- que una canción se resuelva a **una pista concreta** y no a una búsqueda escrita (que
  no suena hasta que alguien le da al play),
- que la consulta llegue legible aunque la IA la mande codificada (`+`, `%20`),
- que solo se diga «poniendo» cuando hay algo que lo confirme,
- que con Spotify conectado se ponga por la **API** (sin abrir ni enfocar nada) y que,
  sin sesión o sin Premium, se siga por el camino de siempre,
- y que **no se pulse ninguna tecla a ciegas**, que es lo que con el foco cambiado
  acababa escribiendo en otra ventana.
"""
import json
import os
import sys
import tempfile
import time
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from modules import system_actions
from modules.spotify import ErrorSpotify
from modules.system_actions import SystemActions

CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_musica.json")
fallos = []
total = [0]

#: Lo que había conectado antes de empezar, para dejarlo como estaba al terminar.
PYAUTOGUI_REAL = system_actions.pyautogui
CDP_REAL = system_actions.navegador_cdp

#: La pista que devolvería el buscador y su ficha pública (oembed). El buscador
#: esconde los enlaces en su redirector codificado (`uddg=`), como en la web de verdad.
PISTA = "https://open.spotify.com/track/0uQhDYHyoZe5DpncrPolb6"
HTML_BUSCADOR = (
    '<a href="https://open.spotify.com/artist/7Gi6gjaWy3DxyilpF1a8Is">Junior H</a>'
    '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopen.spotify.com%2Ftrack%2F'
    '0uQhDYHyoZe5DpncrPolb6&amp;rut=abc">Junior H - LAS NOCHES | Spotify</a>')
FICHA_PISTA = json.dumps({"title": "LAS NOCHEs", "provider_name": "Spotify"})


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


class VentanaFalsa:
    """Ventana de `pygetwindow` de mentira: solo el título que se le diga."""

    def __init__(self, titulo):
        self.title = titulo


class TeclasFalsas:
    """`pyautogui` de mentira: apunta las teclas que se le piden."""

    def __init__(self):
        self.pulsadas = []

    def press(self, tecla, **resto):
        self.pulsadas.append(tecla)


class PestanaFalsa:
    """Pestaña de Brave de mentira: apunta los guiones que se le piden evaluar."""

    def __init__(self, respuesta=None, error=None):
        self.respuesta = {"ok": True} if respuesta is None else respuesta
        self.error = error
        self.evaluado = []
        self.timeout = 40

    def evaluar(self, guion, navegar=None):
        self.evaluado.append((guion, navegar))
        if self.error:
            raise self.error
        return self.respuesta


class NavegadorFalso:
    """`navegador_cdp` de mentira: control (o no) del reproductor web."""

    def __init__(self, activo=False, pestana=None):
        self.activo = activo
        self.pestana = pestana
        self.abiertas = []          # pestañas que se habrían abierto

    def esta_activo(self):
        return self.activo

    def pestana_de(self, fragmento):
        return self.pestana

    def Pestana(self, url, **resto):
        self.abiertas.append(url)
        return self.pestana or PestanaFalsa()


#: La misma canción, tal y como la devuelve la API de Spotify (`/search`): la uri es lo
#: que se le manda a sonar.
PISTA_API = {
    "uri": "spotify:track:0uQhDYHyoZe5DpncrPolb6",
    "titulo": "LAS NOCHEs",
    "artista": "Junior H",
    "album": "Mi vida en un cigarro",
    "enlace": PISTA,
}


class SpotifyFalso:
    """Cliente de la API de Spotify de mentira: apunta lo que se le pide.

    Solo lo que usa `SystemActions`: la sesión (`disponible`), buscar la pista, ponerla
    y los mandos. Se puede decir qué contesta cada cosa —por ejemplo que la cuenta no es
    Premium y Spotify no deja controlar la reproducción— para poder comprobar el camino
    de siempre.
    """

    def __init__(self, conectado=True, pista="", poner=None, mando=None,
                 error_buscar=None, error_poner=None):
        self.conectado = conectado
        self.pedidas = []          # consultas de búsqueda que recibiría
        self.puestas = []          # pistas que se le mandarían a sonar
        self.mandos = []           # órdenes (pausar, siguiente, anterior)
        self._pista = PISTA_API if pista == "" else pista
        self._poner = poner or {"ok": True, "motivo": "",
                                "dispositivo": "PC-escritorio", "pista": PISTA_API}
        self._mando = mando or {"ok": True, "motivo": "",
                                "dispositivo": "PC-escritorio", "pista": PISTA_API}
        self._error_buscar = error_buscar
        self._error_poner = error_poner

    def disponible(self):
        return self.conectado

    def buscar_pista(self, consulta):
        self.pedidas.append(consulta)
        if self._error_buscar:
            raise self._error_buscar
        return dict(self._pista) if self._pista else None

    def poner_pista(self, uri, titulo=""):
        self.puestas.append((uri, titulo))
        if self._error_poner:
            raise self._error_poner
        return dict(self._poner)

    def _contestar(self, orden):
        """Los cuatro mandos contestan igual: se apunta cuál se pidió."""
        self.mandos.append(orden)
        return dict(self._mando)

    def pausar(self):
        return self._contestar("pausar")

    def reanudar(self):
        return self._contestar("reanudar")

    def siguiente(self):
        return self._contestar("siguiente")

    def anterior(self):
        return self._contestar("anterior")


class AsistenteFalso(SystemActions):
    """Solo la música: no monta Office, correo, reuniones ni navegador."""

    def __init__(self, respuestas=None):
        self.respuestas = dict(respuestas or {})   # URL -> contenido de la web
        self.descargas = []                        # direcciones que se pedirían
        self.abiertas = []                         # enlaces de la app de Spotify
        self.urls = []                             # enlaces que se abrirían en Brave
        self.buscado = []                          # búsquedas web pedidas
        self.videos = []                           # vídeos de YouTube pedidos
        #: Títulos de las ventanas que se harán pasar por las de Spotify. None = las
        #: de verdad (por proceso), que es lo que se prueba en su propio apartado.
        self.titulos_spotify = None

    def _descargar(self, direccion):
        self.descargas.append(direccion)
        for comienzo, contenido in self.respuestas.items():
            if direccion.startswith(comienzo):
                return contenido
        raise OSError("sin red en la prueba")

    def _ventanas_por_proceso(self, nombre_proceso):
        if self.titulos_spotify is None:
            return super()._ventanas_por_proceso(nombre_proceso)
        return [VentanaFalsa(titulo) for titulo in self.titulos_spotify]


def montar(ventanas=None, respuestas=None, cdp=None, uri_ok=True):
    """Asistente con la música de verdad y los dobles de prueba conectados."""
    if respuestas is None:
        respuestas = {SystemActions.BUSCADOR_PISTAS: HTML_BUSCADOR,
                      SystemActions.FICHA_PISTA: FICHA_PISTA}
    sistema = AsistenteFalso(respuestas)
    sistema.ESPERA_MUSICA = 0.5        # que las esperas no alarguen la prueba
    sistema._abrir_uri_spotify = lambda uri: bool(sistema.abiertas.append(uri)) or uri_ok
    sistema._abrir_url_brave = lambda url: sistema.urls.append(url)
    sistema.buscar_en_brave = lambda consulta, plataforma=None: (
        sistema.buscado.append((consulta, plataforma)) or f"buscando {consulta}")
    sistema.reproducir_video_youtube = lambda consulta, posicion=0: (
        sistema.videos.append((consulta, posicion)) or f"reproduciendo {consulta}")
    system_actions.pyautogui = TeclasFalsas()
    system_actions.navegador_cdp = cdp if cdp is not None else NavegadorFalso()
    if ventanas is not None:
        sistema.titulos_spotify = tuple(ventanas)
    return sistema, system_actions.pyautogui


def pruebas_consulta():
    print("\n== La consulta que llega de la IA ==")
    comprobar(SystemActions._consulta_legible("Junior+H+Las+noches")
              == "Junior H Las noches",
              "«Junior+H+Las+noches» (lo que a veces manda la IA) se lee como se dijo")
    comprobar(SystemActions._consulta_legible("Junior%20H%20Las%20noches")
              == "Junior H Las noches", "y con %20 igual")
    comprobar(SystemActions._consulta_legible("  Junior H  ") == "Junior H",
              "los espacios de fuera se recortan")
    comprobar(SystemActions._consulta_legible("Café Tacvba") == "Café Tacvba",
              "los acentos y el resto del texto se respetan")
    comprobar(SystemActions._consulta_legible("AC/DC") == "AC/DC",
              "un título con símbolos de verdad no se estropea")


def pruebas_pista():
    print("\n== Resolver la canción a una pista concreta ==")
    sistema, _ = montar()
    comprobar(sistema._pista_en_spotify("Junior H Las noches")
              == ("LAS NOCHEs", PISTA),
              "se resuelve la pista (título confirmado por su ficha pública)")
    pedido = urllib.parse.unquote_plus(
        sistema.descargas[0].replace(SystemActions.BUSCADOR_PISTAS, ""))
    comprobar(pedido == "site:open.spotify.com Junior H Las noches",
              "la búsqueda va legible y acotada a Spotify")
    comprobar(urllib.parse.unquote(sistema.descargas[1])
              == SystemActions.FICHA_PISTA + PISTA,
              "el título se contrasta con la ficha de esa misma pista")
    comprobar("artist" not in sistema.descargas[1],
              "entre un artista y una canción se elige la canción (es lo que se pide)")

    sistema, _ = montar(respuestas={SystemActions.BUSCADOR_PISTAS: "<p>nada</p>"})
    comprobar(sistema._pista_en_spotify("Las noches") is None,
              "sin resultados no se inventa ninguna pista")
    sistema, _ = montar(respuestas={})
    comprobar(sistema._pista_en_spotify("Las noches") is None,
              "sin red tampoco (y no revienta)")
    sistema, _ = montar(respuestas={SystemActions.BUSCADOR_PISTAS: HTML_BUSCADOR})
    comprobar(sistema._pista_en_spotify("Las noches") == ("Las noches", PISTA),
              "si la ficha no contesta, se usa la consulta como título provisional")


def pruebas_reproducir():
    print("\n== Poner música ==")
    # 1. Con el reproductor web controlable: se pulsa su play y se comprueba.
    pestana = PestanaFalsa()
    sistema, teclas = montar(ventanas=[], cdp=NavegadorFalso(True, pestana))
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(respuesta == "Poniendo «LAS NOCHEs» en Spotify." and sistema.urls == [],
              "con el reproductor controlado se pone la canción y se dice cuál es")
    comprobar(pestana.evaluado and SystemActions.JS_REPRODUCIR in pestana.evaluado[0][0]
              and pestana.evaluado[0][1] == PISTA,
              "pulsando su play por DOM, en la pestaña de esa pista")
    comprobar(pestana.timeout == SystemActions.ESPERA_REPRODUCTOR_WEB,
              "con margen de sobra para que cargue y arranque")
    comprobar(teclas.pulsadas == [], "y sin pulsar ninguna tecla a ciegas")

    # 2. Sin control del navegador: se abre la pista y se comprueba si suena.
    sistema, _ = montar(ventanas=["Junior H - LAS NOCHEs"], cdp=NavegadorFalso(False))
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(sistema.urls == [PISTA]
              and respuesta == "Poniendo «LAS NOCHEs» en Spotify.",
              "sin control del navegador se abre la pista y, si suena, se confirma")

    # 3. Y si no se puede confirmar que suene, no se promete nada.
    sistema, teclas = montar(ventanas=[], cdp=NavegadorFalso(False))
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(sistema.urls == [PISTA] and "dale al play" in respuesta
              and not respuesta.startswith("Poniendo"),
              "si no hay forma de comprobarlo, se avisa de que hay que darle al play")
    comprobar(teclas.pulsadas == [], "y no se pulsa ninguna tecla para «probarlo»")

    sistema, _ = montar(ventanas=[],
                        cdp=NavegadorFalso(True, PestanaFalsa({"ok": False})))
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(sistema.urls == [PISTA] and "dale al play" in respuesta,
              "si el reproductor web no arranca, se deja la pista abierta y se avisa")

    # 4. Sin poder resolver la canción: la búsqueda de siempre, y sin teclazos.
    sistema, teclas = montar(ventanas=[], respuestas={})
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(sistema.abiertas == ["spotify:search:Junior%20H%20Las%20noches"]
              and "dale al play" in respuesta,
              "sin resolverla se deja la búsqueda en Spotify y se dice lo que falta")
    comprobar(teclas.pulsadas == [],
              "sin teclazos: da igual qué ventana esté delante")

    sistema, _ = montar(ventanas=[], respuestas={}, uri_ok=False)
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(sistema.urls
              == ["https://open.spotify.com/search/Junior%20H%20Las%20noches"]
              and "reproductor web" in respuesta,
              "sin la aplicación de Spotify se deja la búsqueda en el reproductor web")

    sistema, _ = montar()
    comprobar(sistema.reproducir_musica("") == "Dime qué canción quieres poner.",
              "sin canción se pide una")


def pruebas_plataformas():
    print("\n== Plataformas ==")
    sistema, _ = montar()
    sistema.reproducir_musica("youtube:Junior H")
    comprobar(sistema.videos == [("Junior H", 0)] and sistema.urls == [],
              "'youtube:' manda al vídeo (el de YouTube, no el de Spotify)")

    sistema, _ = montar()
    sistema.reproducir_musica("brave:Junior H")
    comprobar(sistema.buscado == [("Junior H", "spotify")] and sistema.urls == [],
              "'brave:' deja la búsqueda del reproductor web")

    sistema, _ = montar(ventanas=[], cdp=NavegadorFalso(True, PestanaFalsa()))
    comprobar(sistema.reproducir_musica("spotify:Junior H")
              == "Poniendo «LAS NOCHEs» en Spotify.",
              "'spotify:' es lo mismo que no poner plataforma")

    sistema, _ = montar()
    sistema.reproducir_musica("Junior H: Las noches")
    comprobar("Junior+H%3A+Las+noches" in sistema.descargas[0],
              "un ':' dentro del título no se confunde con una plataforma")


def pruebas_palabras():
    print("\n== Reconocer la canción que suena ==")
    comprobar(SystemActions._palabras("LAS NOCHEs") == {"noches"},
              "se quitan acentos y palabras que no distinguen («las»)")
    comprobar(SystemActions._palabras("Junior H - LAS NOCHEs") >= {"noches"},
              "el título de la ventana contiene las palabras de la canción")
    comprobar(SystemActions._palabras("Café Tacvba")
              == SystemActions._palabras("cafe tacvba"),
              "los acentos no separan dos títulos iguales")
    comprobar(SystemActions._palabras("") == set(), "un texto vacío no tiene palabras")


def pruebas_ventana_por_proceso():
    """La ventana de Spotify **con música sonando** no dice «Spotify» por ningún lado.

    Comprobado en este equipo: su título es el de la canción («Junior H - LAS NOCHEs»),
    así que ahí solo se puede reconocer por proceso. Se prueba con una ventana y un
    proceso de verdad (un Tk de este mismo Python, que hace de Spotify), sin tener
    Spotify abierto ni pulsar nada.
    """
    print("\n== La ventana cuando ya suena una canción ==")
    import psutil
    import tkinter as tk

    raiz = tk.Tk()
    raiz.title("Junior H - LAS NOCHEs")
    raiz.geometry("240x90+40+40")
    raiz.update()
    time.sleep(0.3)                       # que Windows ya cuente esa ventana
    raiz.update()
    proceso = psutil.Process().name().lower()
    proceso_antes = SystemActions.PROCESO_SPOTIFY
    SystemActions.PROCESO_SPOTIFY = proceso      # este Python hace de Spotify
    try:
        ventanas = SystemActions._ventanas_por_proceso(proceso)
        titulos = [ventana.title for ventana in ventanas]
        comprobar("Junior H - LAS NOCHEs" in titulos,
                  "una ventana titulada con la canción se encuentra por proceso")
        indice = titulos.index("Junior H - LAS NOCHEs")
        comprobar(SystemActions._pid_de_ventana(ventanas[indice]._hWnd) == os.getpid(),
                  "y el proceso que se le atribuye es el dueño de verdad")
        comprobar(os.getpid() in SystemActions._pids_de(proceso),
                  "los PIDs salen de los procesos de verdad")
        comprobar(SystemActions._ventanas_por_proceso("jarvis-no-existe.exe") == [],
                  "un proceso que no existe no da ventanas: no se adivina")

        sistema, _ = montar()
        sistema.ESPERA_MUSICA = 1.0
        comprobar(sistema._sonando_en_spotify("LAS NOCHEs") is True,
                  "así se sabe que esa canción está sonando (y se puede decir)")
        comprobar(sistema._sonando_en_spotify("Otra canción") is False,
                  "una canción que no está en el título no se da por sonando")
    finally:
        SystemActions.PROCESO_SPOTIFY = proceso_antes
        raiz.destroy()


def pruebas_control():
    print("\n== Control de lo que suena ==")
    sistema, teclas = montar()
    comprobar("pausa" in sistema.control_musica("pausa")
              and teclas.pulsadas == ["playpause"],
              "«pausa» pulsa la tecla de play/pausa")
    sistema.control_musica("Siguiente canción")
    comprobar(teclas.pulsadas[-1] == "nexttrack", "«siguiente canción» salta de canción")
    sistema.control_musica("vuelve a la anterior")
    comprobar(teclas.pulsadas[-1] == "prevtrack", "«vuelve a la anterior» vuelve atrás")
    teclas.pulsadas.clear()
    sistema.control_musica("")
    comprobar(teclas.pulsadas == ["playpause"], "sin decir qué, pausa")
    teclas.pulsadas.clear()
    respuesta = sistema.control_musica("ponme un té")
    comprobar(teclas.pulsadas == []
              and "pausa, reanudar, siguiente o anterior" in respuesta,
              "una orden que no es de música no toca el reproductor")

    # Con el reproductor web controlado se pulsa su mando en vez de la tecla ciega.
    pestana = PestanaFalsa()
    sistema, teclas = montar(ventanas=[], cdp=NavegadorFalso(True, pestana))
    sistema.control_musica("siguiente")
    comprobar(teclas.pulsadas == [] and pestana.evaluado
              and "control-button-skip-forward" in pestana.evaluado[-1][0],
              "si se controla el reproductor web, se pulsa su botón de siguiente")


def pruebas_spotify_api():
    print("\n== Poner música por la API de Spotify (sin abrir nada) ==")
    # Con Spotify conectado: la canción se pone por la API y Spotify lo confirma.
    sistema, teclas = montar(ventanas=[])       # sin ventanas: no hace falta ninguna
    cliente = SpotifyFalso()
    sistema.spotify = cliente
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar(respuesta
              == "Poniendo «LAS NOCHEs» de Junior H en Spotify (PC-escritorio).",
              "se pone por la API y se dice qué suena y en qué aparato")
    comprobar(cliente.pedidas == ["Junior H Las noches"]
              and cliente.puestas == [(PISTA_API["uri"], "LAS NOCHEs")],
              "se busca la canción y se le manda la pista exacta (uri), no una búsqueda")
    comprobar(sistema.descargas == [] and sistema.urls == [] and sistema.abiertas == [],
              "y no se abre ni se navega nada: vale con un juego en primer plano")
    comprobar(teclas.pulsadas == [], "sin pulsar ninguna tecla")

    # Sin sesión conectada se sigue por el reproductor de siempre, sin tocar la API.
    sistema, _ = montar(ventanas=["Junior H - LAS NOCHEs"])
    cliente = SpotifyFalso(conectado=False)
    sistema.spotify = cliente
    comprobar(sistema.reproducir_musica("Junior H Las noches")
              == "Poniendo «LAS NOCHEs» en Spotify.",
              "sin sesión conectada se sigue por el camino de siempre")
    comprobar(cliente.pedidas == [] and cliente.puestas == []
              and sistema.descargas,
              "y a la API no se le pide nada: se resuelve por la web, como siempre")

    # Sin Premium Spotify no deja ponerla: se cuenta por qué y se deja cargada.
    sistema, _ = montar(ventanas=["Junior H - LAS NOCHEs"])
    sistema.spotify = SpotifyFalso(poner={
        "ok": False, "dispositivo": "PC-escritorio", "pista": None,
        "motivo": "Player command failed: Premium required. Reason: PREMIUM_REQUIRED"})
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar("No pude ponerla sola: Player command failed" in respuesta
              and "Poniendo «LAS NOCHEs» en Spotify." in respuesta,
              "sin Premium se dice por qué y se deja la canción cargada, que sí suena")
    comprobar(sistema.urls == [PISTA], "abriendo la pista concreta en el reproductor web")

    # Sin ningún dispositivo (Spotify cerrado): igual, se avisa y se deja cargada.
    sistema, _ = montar(ventanas=[])
    sistema.spotify = SpotifyFalso(poner={
        "ok": False, "dispositivo": "", "pista": None,
        "motivo": ("No hay ningún dispositivo de Spotify disponible: abre Spotify en "
                   "este PC (o el altavoz) y lo intento otra vez.")})
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar("No hay ningún dispositivo" in respuesta and "dale al play" in respuesta,
              "sin dispositivo se dice qué falta y se deja la canción lista para el play")

    # Si la API no encuentra la canción, no se va a buscar a la web: no hay nada mejor.
    sistema, _ = montar(ventanas=[])
    sistema.spotify = SpotifyFalso(pista=None)
    comprobar(sistema.reproducir_musica("Junior H Las noches")
              == "No encuentro «Junior H Las noches» en Spotify.",
              "si la API no encuentra la canción, se dice claramente")
    comprobar(sistema.descargas == [] and sistema.urls == [],
              "y no se busca en la web por si suena de casualidad")

    # Si la API falla (sin red, token caducado...), se cuenta y se sigue por lo de antes.
    sistema, _ = montar(ventanas=["Junior H - LAS NOCHEs"])
    sistema.spotify = SpotifyFalso(
        error_buscar=ErrorSpotify("Spotify no contesta.", 502))
    respuesta = sistema.reproducir_musica("Junior H Las noches")
    comprobar("No pude buscar la canción en Spotify (Spotify no contesta)" in respuesta
              and "Poniendo «LAS NOCHEs» en Spotify." in respuesta,
              "si la API falla, se cuenta el motivo y se sigue por el camino de siempre")


def pruebas_despachador():
    print("\n== El despachador del chat ==")
    sistema, teclas = montar(ventanas=["Junior H - LAS NOCHEs"])
    respuesta = sistema.ejecutar_comando("REPRODUCIR_MUSICA|Junior+H+Las+noches")
    comprobar(respuesta == "Poniendo «LAS NOCHEs» en Spotify.",
              "REPRODUCIR_MUSICA llega hasta Spotify (con el texto ya legible)")
    sistema.ejecutar_comando("MUSICA|siguiente")
    comprobar(teclas.pulsadas[-1] == "nexttrack", "MUSICA|siguiente salta de canción")
    comprobar(sistema.ejecutar_comando("REPRODUCIR_MUSICA")
              == "Dime qué canción quieres poner.",
              "REPRODUCIR_MUSICA sin canción pide una")
    comprobar("REPRODUCIR_MUSICA" in SystemActions.PROGRESO_ACCIONES,
              "mientras busca, la ventana cuenta que está con Spotify")


def pruebas_spotify_control():
    print("\n== Control por la API (pausa, siguiente, anterior) ==")
    sistema, teclas = montar()
    cliente = SpotifyFalso()
    sistema.spotify = cliente
    comprobar(sistema.control_musica("pausa")
              == "Hecho: dejo «LAS NOCHEs» en pausa."
              and cliente.mandos == ["pausar"],
              "«pausa» se manda a Spotify y él confirma que la dejó en pausa")
    comprobar(teclas.pulsadas == [], "sin pulsar ninguna tecla multimedia")
    comprobar(sistema.control_musica("Siguiente canción")
              == "Hecho: cambio a «LAS NOCHEs»."
              and cliente.mandos[-1] == "siguiente",
              "«siguiente canción» salta por la API")
    comprobar(sistema.control_musica("vuelve a la anterior")
              == "Hecho: vuelvo a «LAS NOCHEs»."
              and cliente.mandos[-1] == "anterior",
              "«vuelve a la anterior» vuelve por la API")
    comprobar(sistema.control_musica("reanudar")
              == "Hecho: sigue «LAS NOCHEs»."
              and cliente.mandos[-1] == "reanudar",
              "«reanudar» sigue donde estaba")
    comprobar(teclas.pulsadas == [], "y en ningún momento se toca el teclado")

    # Spotify contesta que ya estaba así: se cuenta tal cual, sin un «hecho» de más.
    sistema, _ = montar()
    sistema.spotify = SpotifyFalso(mando={
        "ok": True, "dispositivo": "PC-escritorio", "pista": PISTA_API,
        "motivo": "La música ya estaba en pausa."})
    comprobar(sistema.control_musica("pausa") == "La música ya estaba en pausa.",
              "si ya estaba en pausa, se dice eso y no se inventa nada")

    # Sin Premium (o sin nada sonando) la API no puede: se dice y no se pulsa a ciegas.
    sistema, teclas = montar()
    sistema.spotify = SpotifyFalso(mando={
        "ok": False, "dispositivo": "", "pista": None,
        "motivo": "Spotify no confirma que haya cambiado nada."})
    comprobar(sistema.control_musica("siguiente")
              == "No pude: Spotify no confirma que haya cambiado nada."
              and teclas.pulsadas == [],
              "si Spotify no lo confirma, se dice y no se pulsa ninguna tecla a ciegas")

    # Una orden que no es de música no llega ni a Spotify.
    comprobar(sistema.control_musica("ponme un té")
              == "Para la música dime pausa, reanudar, siguiente o anterior."
              and sistema.spotify.mandos == ["siguiente"],
              "una orden que no es de música no llega a la API")

    # Sin sesión conectada, el control sigue siendo el de siempre (la tecla multimedia).
    sistema, teclas = montar()
    cliente = SpotifyFalso(conectado=False)
    sistema.spotify = cliente
    comprobar("pausa" in sistema.control_musica("pausa")
              and teclas.pulsadas == ["playpause"] and cliente.mandos == [],
              "sin sesión conectada se sigue pulsando la tecla de siempre")


def pruebas_prompt():
    """El fallo de la captura: la IA contestaba «Buscando ... en Brave» una y otra vez.

    Con `BUSCAR` la canción solo queda listada en el navegador y no suena nada, así que
    el prompt tiene que mandar la música a `REPRODUCIR_MUSICA`, pedir el texto de la
    canción sin codificar y no dejar que la IA vuelva a caer en la búsqueda cuando el
    usuario dice que no ha sonado.
    """
    print("\n== Lo que se le pide a la IA ==")
    if os.path.exists(CONFIG):
        os.remove(CONFIG)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"nombre_asistente": "jarvis"}, f)
    from modules.api_brain import APIBrain

    prompt = APIBrain(config_path=CONFIG).historial[0]["content"]
    comprobar("REPRODUCIR_MUSICA|artista y canción" in prompt,
              "el prompt le enseña a poner música con REPRODUCIR_MUSICA")
    comprobar("sin codificarla" in prompt and "%20" in prompt,
              "y a escribir la canción tal cual, sin %20 ni +")
    comprobar("NO para poner música" in prompt and "NUNCA uses BUSCAR" in prompt,
              "y le prohíbe poner música con BUSCAR")
    comprobar("MUSICA|pausa" in prompt and "MUSICA|siguiente" in prompt
              and "MUSICA|anterior" in prompt,
              "también sabe pausar, saltar y volver atrás")
    comprobar("manda otra vez REPRODUCIR_MUSICA" in prompt,
              "si el usuario dice que no ha sonado, repite la música (no una búsqueda)")


def main_pruebas():
    pruebas_consulta()
    pruebas_pista()
    pruebas_reproducir()
    pruebas_plataformas()
    pruebas_palabras()
    pruebas_ventana_por_proceso()
    pruebas_control()
    pruebas_spotify_api()
    pruebas_spotify_control()
    pruebas_despachador()
    pruebas_prompt()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    try:
        codigo = main_pruebas()
    finally:
        system_actions.pyautogui = PYAUTOGUI_REAL
        system_actions.navegador_cdp = CDP_REAL
        if os.path.exists(CONFIG):
            os.remove(CONFIG)
    raise SystemExit(codigo)
