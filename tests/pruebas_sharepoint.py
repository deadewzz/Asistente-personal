"""Pruebas de SharePoint sin Graph.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_sharepoint.py

Prueba la lógica que no necesita Brave ni red: parseo de URLs de
SharePoint/OneDrive, construcción de las llamadas `_api` (con una pestaña
falsa), recorrido de carpetas y subcarpetas (solo Word y PowerPoint),
clasificación y resumen de desplazamientos. Las llamadas reales se validan
contra la sesión del usuario con `tests/diagnostico_brave.py`.
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.progreso import Progreso
from modules.sharepoint import ErrorSharePoint, SharePoint

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


class PestanaFalsa:
    """Sustituye a navegador_cdp.Pestana: devuelve una respuesta fija."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.visto = []

    def evaluar(self, expresion, navegar=None):
        self.visto.append(expresion)
        return self.respuesta

    def cerrar(self):
        pass


SITIO = "https://contoso.sharepoint.com/sites/Tech"
PERSONAL = "https://contoso-my.sharepoint.com/personal/john_doe_contoso_com"


class PestanaPuente(PestanaFalsa):
    """Pestaña falsa que contesta distinto si le piden descargar o subir."""

    def __init__(self, base64_texto="QUJD", tamano=3, grande=False, subida=None):
        super().__init__(None)
        self.base64_texto = base64_texto
        self.tamano = tamano
        self.grande = grande
        self.subida = subida if subida is not None else {"estado": 200,
                                                         "cuerpo": "{}"}

    def evaluar(self, expresion, navegar=None):
        self.visto.append(expresion)
        if "$value" in expresion:
            if self.grande:
                return {"estado": 200, "tamano": self.tamano, "grande": True}
            return {"estado": 200, "base64": self.base64_texto,
                    "tamano": self.tamano}
        return self.subida


def con_pestana(respuesta):
    """SharePoint con una pestaña falsa ya inyectada (sin tocar Brave)."""
    sp = SharePoint()
    pestana = PestanaFalsa(respuesta)
    sp._pestanas[SITIO] = pestana
    return sp, pestana


def pruebas_parseo_url():
    print("\n== Parseo de URLs de SharePoint ==")
    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Documentos%20compartidos/Sub")
    comprobar(p["sitio"] == SITIO, "sitio de una URL /sites/")
    comprobar(p["carpeta_rel"] == "/sites/Tech/Documentos compartidos/Sub",
              "carpeta server-relative de una URL /sites/")
    comprobar(p["dominio"] == "contoso.sharepoint.com", "dominio extraído")
    comprobar(p["web_rel"] == "/sites/Tech", "ruta del sitio dentro del host")

    p = SharePoint.parsear_url("https://contoso.sharepoint.com/teams/Tech/Archivo")
    comprobar(p["sitio"] == "https://contoso.sharepoint.com/teams/Tech",
              "sitio de una URL /teams/")
    comprobar(p["carpeta_rel"] == "/teams/Tech/Archivo",
              "carpeta relativa de una URL /teams/")

    p = SharePoint.parsear_url(
        "https://contoso-my.sharepoint.com/personal/john_doe_contoso_com/Documents/Invoices")
    comprobar(p["sitio"] == "https://contoso-my.sharepoint.com/personal/john_doe_contoso_com",
              "sitio de OneDrive personal")
    comprobar(p["carpeta_rel"] == "/personal/john_doe_contoso_com/Documents/Invoices",
              "carpeta de OneDrive personal")

    p = SharePoint.parsear_url("https://contoso.sharepoint.com/")
    comprobar(p["sitio"] == "https://contoso.sharepoint.com/"
              and p["carpeta_rel"] == "/", "URL raíz del sitio")

    # Las URLs que se copian de SharePoint traen la vista web y sus parámetros.
    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Oportunidad/Forms/"
        "AllItems.aspx?viewid=cc6180f7%2Dd03f%2D4ee0%2Da546%2D0c7a85fe3902"
        "&FolderCTID=0x0120002B8F763F31F15643983416479C046D67"
        "&CT=1785254039012")
    comprobar(p["sitio"] == SITIO, "sitio de una URL con vista Forms/AllItems.aspx")
    comprobar(p["carpeta_rel"] == "/sites/Tech/Oportunidad",
              "la vista AllItems.aspx se queda con su carpeta, no con el .aspx")

    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Oportunidad/Forms/"
        "AllItems.aspx?RootFolder=%2Fsites%2FTech%2FOportunidad%2F2026"
        "&FolderCTID=0x0120")
    comprobar(p["carpeta_rel"] == "/sites/Tech/Oportunidad/2026",
              "RootFolder= manda sobre la ruta de la vista")

    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Oportunidad/Forms/"
        "AllItems.aspx?id=%2Fsites%2FTech%2FOportunidad%2F2026%2Ffactura.pdf")
    comprobar(p["carpeta_rel"] == "/sites/Tech/Oportunidad/2026",
              "si id= apunta a un archivo, se usa su carpeta")

    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Docs/Forms/OneUp.aspx?"
        "sourcedoc=%7BABC%7D")
    comprobar(p["carpeta_rel"] == "/sites/Tech/Docs",
              "cualquier vista .aspx (OneUp) se recorta")

    # El enlace que comparte Teams ('.../my?id=...') NO dice el sitio en el camino:
    # la carpeta viene codificada en el parámetro y de ahí hay que sacar también el
    # sitio. Sin eso, todo se pedía a la raíz del host y una carpeta llena de
    # subcarpetas salía como vacía (el fallo que reportó el usuario).
    p = SharePoint.parsear_url(
        "https://contoso-my.sharepoint.com/my?id=%2Fpersonal%2Fjohn_doe_contoso_com"
        "%2FDocuments%2FPropuestas&viewid=7a54bd05%2D155b%2D4a81%2D8dfc%2D21990001e908"
        "&ct=1790613931627&or=WORD%2DWEB%2EBODY%2ENT")
    comprobar(p["sitio"] == PERSONAL,
              "enlace de Teams: el sitio sale de la ruta del id=")
    comprobar(p["carpeta_rel"] == "/personal/john_doe_contoso_com/Documents/Propuestas",
              "enlace de Teams: la carpeta es la del id=")
    comprobar(p["web_rel"] == "/personal/john_doe_contoso_com",
              "enlace de Teams: web_rel apunta al OneDrive, no al host")

    p = SharePoint.parsear_url(
        "https://contoso-my.sharepoint.com/my?id=%2Fpersonal%2Fjohn_doe_contoso_com"
        "%2FDocuments%2FPropuestas%2FActa%2Edocx&viewid=x")
    comprobar(p["carpeta_rel"] == "/personal/john_doe_contoso_com/Documents/Propuestas",
              "enlace de Teams a un archivo: se usa su carpeta")

    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/my?id=%2Fsites%2FTech%2FDocumentos%20compartidos"
        "%2F2026&viewid=x")
    comprobar(p["sitio"] == SITIO and p["carpeta_rel"]
              == "/sites/Tech/Documentos compartidos/2026",
              "enlace de Teams a una carpeta de un sitio de equipo")

    # '.../my' a secas es la portada de OneDrive, no una carpeta llamada 'my'.
    p = SharePoint.parsear_url("https://contoso-my.sharepoint.com/my")
    comprobar(p["sitio"] == "https://contoso-my.sharepoint.com/" and p["carpeta_rel"] == "/",
              "'.../my' se trata como la raíz del OneDrive")

    # Los enlaces con atajo ('/:w:/r/sites/Tech/...') también se entienden.
    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/:w:/r/sites/Tech/Documentos%20compartidos/2026"
        "?d=abc&csf=1")
    comprobar(p["sitio"] == SITIO and p["carpeta_rel"]
              == "/sites/Tech/Documentos compartidos/2026",
              "el atajo '/:w:/r/' no se cuela en el sitio ni en la carpeta")

    # Una carpeta que se llame 'sites' por dentro no cambia el sitio.
    p = SharePoint.parsear_url(
        "https://contoso.sharepoint.com/sites/Tech/Docs/sites/Antiguo")
    comprobar(p["sitio"] == SITIO and p["carpeta_rel"]
              == "/sites/Tech/Docs/sites/Antiguo",
              "una carpeta llamada 'sites' no mueve el sitio")


def pruebas_odata():
    print("\n== Literales OData ==")
    comprobar(SharePoint._odata("/sites/Tech/Documentos compartidos")
              == "/sites/Tech/Documentos%20compartidos",
              "escapa espacios y deja las barras")
    comprobar(SharePoint._odata("/sites/Tech/O'Brien") == "/sites/Tech/O''Brien",
              "duplica la comilla simple")


def pruebas_api():
    print("\n== Llamadas a /_api (pestaña falsa) ==")
    sp, pestana = con_pestana({"estado": 200, "cuerpo": '{"d": {"results": [1]}}'})
    comprobar(sp._api(SITIO, "/web/x") == {"d": {"results": [1]}},
              "parsea el JSON de una respuesta 200")
    js = pestana.visto[-1]
    comprobar("credentials:'include'" in js, "el fetch manda las cookies de sesión")
    comprobar("_api/web/x" in js, "llama al endpoint pedido")

    sp, pestana = con_pestana({"estado": 200, "cuerpo": "{}"})
    sp._api(SITIO, "/web/folders", metodo="POST",
            datos={"__metadata": {"type": "SP.Folder"}})
    js = pestana.visto[-1]
    comprobar("contextinfo" in js and "X-RequestDigest" in js,
              "pide y reutiliza el token de escritura")
    comprobar("SP.Folder" in js, "envía el cuerpo JSON de la petición")
    comprobar("credentials:'include'" in js, "también las cookies en el POST")

    for estado, esperado, texto in (
            (401, "sesión", "el 401 avisa de que la sesión no vale"),
            (403, "permiso", "el 403 avisa de que falta permiso (no de sesión)"),
            (500, "500", "el 500 muestra el código de error")):
        sp, _ = con_pestana({"estado": estado, "cuerpo": "vaya"})
        try:
            sp._api(SITIO, "/web/x")
            comprobar(False, texto)
        except ErrorSharePoint as e:
            comprobar(esperado in str(e), texto)

    sp, _ = con_pestana({"estado": -1, "cuerpo": "NetworkError"})
    try:
        sp._api(SITIO, "/web/x")
        comprobar(False, "un fallo de red avisa de conexión/Brave cerrado")
    except ErrorSharePoint as e:
        comprobar("navegador" in str(e),
                  "un fallo de red avisa de conexión/Brave cerrado")

    sp, _ = con_pestana({"estado": 403, "cuerpo": "Acceso denegado",
                         "paso": "token"})
    try:
        sp._api(SITIO, "/web/x", metodo="POST", datos={})
        comprobar(False, "avisa si falla el token de escritura")
    except ErrorSharePoint as e:
        comprobar("token de escritura" in str(e),
                  "avisa si falla el token de escritura")

    sp, _ = con_pestana("texto suelto")
    try:
        sp._api(SITIO, "/web/x")
        comprobar(False, "una respuesta rara lanza ErrorSharePoint")
    except ErrorSharePoint:
        comprobar(True, "una respuesta rara lanza ErrorSharePoint")

    sp, _ = con_pestana({"estado": 200,
                         "cuerpo": "<html><head><title>Iniciar sesión"})
    try:
        sp._api(SITIO, "/web/x")
        comprobar(False, "detecta la página de login en vez de datos")
    except ErrorSharePoint as e:
        comprobar("sesión" in str(e), "detecta la página de login en vez de datos")


def pruebas_listados():
    print("\n== Listar archivos y carpetas ==")
    sp = SharePoint()
    visto = {}

    def api_falsa(sitio, ruta, metodo="GET", datos=None):
        visto.update(sitio=sitio, ruta=ruta, metodo=metodo)
        if ruta.endswith("Folders?$select=Name,ServerRelativeUrl"):
            return {"d": {"results": [{"Name": "Facturas",
                                       "ServerRelativeUrl": "/sites/Tech/Docs/Facturas"}]}}
        return {"d": {"results": [{"Name": "a.pdf",
                                   "ServerRelativeUrl": "/sites/Tech/Docs/a.pdf",
                                   "Length": 12}]}}

    sp._api = api_falsa
    archivos = sp.listar_archivos("https://contoso.sharepoint.com/sites/Tech/Docs")
    comprobar(archivos == [{"nombre": "a.pdf",
                            "ruta_rel": "/sites/Tech/Docs/a.pdf", "tamano": 12}],
              "listar_archivos mapea nombre/ruta/tamaño")
    comprobar(visto["sitio"] == SITIO, "usa la URL raíz del sitio")
    comprobar("/sites/Tech/Docs" in visto["ruta"],
              "usa la ruta server-relative de la carpeta")

    carpetas = sp.listar_carpetas("https://contoso.sharepoint.com/sites/Tech/Docs")
    comprobar(carpetas == [{"nombre": "Facturas",
                            "ruta_rel": "/sites/Tech/Docs/Facturas"}],
              "listar_carpetas mapea nombre/ruta")


def con_api_estado(estado, cuerpo=""):
    """SharePoint cuyo `_api` siempre responde con ese código HTTP."""
    sp = SharePoint()

    def api_falsa(sitio, ruta, metodo="GET", datos=None):
        if estado == 200:
            return {}
        error = ErrorSharePoint(f"SharePoint respondió {estado}: {cuerpo}")
        error.estado = estado
        raise error

    sp._api = api_falsa
    return sp


def pruebas_existencia():
    """SharePoint contesta 200 con lista vacía a rutas que no existen.

    Por eso el código pregunta explícitamente por la carpeta/archivo antes de
    fiarse de un listado: si no, una carpeta mal escrita parecería vacía y un
    archivo del destino sin detectar se sobrescribiría.
    """
    print("\n== Existencia de carpetas y archivos ==")
    sp = con_api_estado(404, "Archivo no encontrado")
    comprobar(sp.carpeta_existe(SITIO, "/sites/Tech/Docs") is False,
              "404 en la carpeta = no existe")
    comprobar(sp.archivo_existe(SITIO, "/sites/Tech/Docs/a.pdf") is False,
              "404 en el archivo = no existe")

    sp = con_api_estado(200, "{}")
    comprobar(sp.carpeta_existe(SITIO, "/sites/Tech/Docs") is True,
              "200 en la carpeta = existe")
    comprobar(sp.archivo_existe(SITIO, "/sites/Tech/Docs/a.pdf") is True,
              "200 en el archivo = existe")

    sp = con_api_estado(403, "Acceso denegado")
    try:
        sp.carpeta_existe(SITIO, "/sites/Tech/Docs")
        comprobar(False, "un 403 no se toma por 'no existe' (se propaga)")
    except ErrorSharePoint as e:
        comprobar("403" in str(e), "un 403 no se toma por 'no existe' (se propaga)")

    sp = con_api_estado(404)
    try:
        sp.listar_archivos("https://contoso.sharepoint.com/sites/Tech/NoExiste")
        comprobar(False, "listar_archivos avisa cuando la carpeta no existe")
    except ErrorSharePoint as e:
        comprobar("no existe" in str(e),
                  "listar_archivos avisa cuando la carpeta no existe")
    try:
        sp.listar_carpetas("https://contoso.sharepoint.com/sites/Tech/NoExiste")
        comprobar(False, "listar_carpetas avisa cuando la carpeta no existe")
    except ErrorSharePoint as e:
        comprobar("no existe" in str(e),
                  "listar_carpetas avisa cuando la carpeta no existe")


# Biblioteca de mentira para el recorrido: archivos (nombre, tamaño) y
# subcarpetas de cada carpeta server-relative.
ARBOL_DOCS = {
    "/sites/Tech/Colombia": {
        "archivos": [("Propuesta.docx", 10), ("Viejo.doc", 20),
                     ("Charla.ppt", 30), ("Costos.xlsx", 40),
                     ("Demo.mp4", 50)],
        "carpetas": ["/sites/Tech/Colombia/2026", "/sites/Tech/Colombia/Forms"],
    },
    "/sites/Tech/Colombia/2026": {
        "archivos": [("Acta.PPTX", 60), ("Informe.doc", 70), ("foto.jpg", 80)],
        "carpetas": ["/sites/Tech/Colombia/2026/Viejo"],
    },
    "/sites/Tech/Colombia/2026/Viejo": {
        "archivos": [("Antiguo.pptx", 90)],
        "carpetas": [],
    },
    "/sites/Tech/Colombia/Forms": {
        "archivos": [("AllItems.aspx", 1)],
        "carpetas": ["/sites/Tech/Colombia/Forms/sub"],
    },
}

COLOMBIA = "https://contoso.sharepoint.com/sites/Tech/Colombia"


def con_arbol(arbol=None, sin_permiso=(), llamadas=None, paginado=()):
    """SharePoint con un `_api` de mentira que sirve ese árbol de carpetas.

    Con ``paginado`` (rutas de carpeta) la respuesta llega en dos páginas, como
    hace SharePoint con las colecciones grandes (`d.__next`).
    """
    arbol = ARBOL_DOCS if arbol is None else arbol
    sp = SharePoint()

    def api_falsa(sitio, ruta, metodo="GET", datos=None):
        if llamadas is not None:
            llamadas.append(ruta)
        trozos = re.match(
            r"/web/GetFolderByServerRelativeUrl\('(.*?)'\)(.*)", ruta)
        carpeta = urllib.parse.unquote(trozos.group(1))
        resto = trozos.group(2)
        nodo = arbol.get(carpeta)
        if nodo is not None and carpeta in sin_permiso:
            error = ErrorSharePoint("SharePoint respondió 403 (Acceso denegado)")
            error.estado = 403
            raise error
        if nodo is None:
            error = ErrorSharePoint(
                f"SharePoint respondió 404 (no existe): {carpeta}")
            error.estado = 404
            raise error
        if resto.startswith("?"):        # ¿existe la carpeta?
            return {"d": {"Name": carpeta.rsplit("/", 1)[-1]}}
        if resto.startswith("/Folders"):
            lista = [{"Name": c.rsplit("/", 1)[-1], "ServerRelativeUrl": c}
                     for c in nodo["carpetas"]]
        else:
            lista = [{"Name": n, "ServerRelativeUrl": carpeta + "/" + n,
                      "Length": t} for n, t in nodo["archivos"]]
        if carpeta in paginado:
            if "$skiptoken=2" in ruta:
                return {"d": {"results": lista[len(lista) // 2:]}}
            return {"d": {"results": lista[:len(lista) // 2],
                          "__next": (sitio.rstrip("/") + "/_api" + ruta
                                     + ("&" if "?" in ruta else "?")
                                     + "$skiptoken=2")}}
        return {"d": {"results": lista}}

    sp._api = api_falsa
    return sp


class SharepointFalso:
    """Sustituye a `sharepoint.SharePoint` en las pruebas de acciones: ni Brave ni red.

    `listar_documentos` devuelve el listado que se le dé y apunta con qué filtro
    se llamó, para comprobar que la acción le pasa el `;;acta` del usuario. Con
    `error` se simula que SharePoint no contesta (sin permiso, sin sesión...).

    `carpetas` es lo que hay dentro del destino (las que la acción le pasa a la
    IA para que elija entre ellas); con `error_carpetas` se simula que no se
    pudo leer esa lista.

    `textos` es lo que se "leería" por dentro de cada documento ({rel: extracto}):
    `leer_textos` devuelve eso y apunta a qué archivos se les pidió el contenido,
    que es como se comprueba que la acción lee (o que con ';;sin leer' no lee).
    Con `error_lectura` se simula que la sesión de Brave falló al bajarlos.
    """

    def __init__(self, listado=None, plan=(), error=None,
                 carpetas=("Clientes", "Actas", "Otros"), error_carpetas=None,
                 textos=None, avisos_lectura=(), error_lectura=None):
        self.listado = listado if listado is not None else {
            "archivos": [], "ignorados": [], "excluidos": [], "carpetas": 0,
            "fallos": [], "truncado": False}
        # El plan es la lista que contestaría la IA, o una función
        # (nombres, regla) -> lista para contestar distinto a cada tanda.
        self.plan = plan
        self.error = error
        self.carpetas = list(carpetas)
        self.error_carpetas = error_carpetas
        self.textos = dict(textos or {})
        self.avisos_lectura = list(avisos_lectura)
        self.error_lectura = error_lectura
        self.on_clasificar = self._clasificar
        self.pedido = None          # (nombres, regla) que recibió la IA
        self.pedido_carpetas = None  # carpetas del destino que recibió la IA
        self.pedido_extractos = None  # textos de dentro que recibió la IA
        self.pedidos_ia = []        # (nombres, regla, extractos) de cada llamada
        self.pedidos_lectura = []   # (url, [rel, ...]) de cada lectura de contenido
        self.pedido_listado = None  # (url, filtro) del último listado
        self.pedido_carpetas_destino = None  # url de la que se leyeron carpetas
        self.movido = None
        self.movido_copiar = None

    def asegurar_navegador(self, url):
        return "Brave ya estaba abierto con depuración; no toco nada."

    def listar_documentos(self, url, solo=None):
        self.pedido_listado = (url, solo)
        if self.error:
            raise self.error
        return self.listado

    def listar_carpetas(self, url):
        self.pedido_carpetas_destino = url
        if self.error_carpetas:
            raise self.error_carpetas
        return [{"nombre": c, "ruta_rel": f"/sites/Tech/Archivo/{c}"}
                for c in self.carpetas]

    def leer_textos(self, url, archivos, maximo=None, limite=None):
        """Lo que la prueba diga que se leyó por dentro: ni Brave ni bajadas.

        Apunta a qué archivos se les pidió el contenido (para comprobar que la
        acción lee de verdad, y que con ';;sin leer' no llama aquí).
        """
        self.pedidos_lectura.append((url, [a["rel"] for a in archivos]))
        if self.error_lectura:
            raise self.error_lectura
        return dict(self.textos), list(self.avisos_lectura), len(self.textos)

    def _clasificar(self, nombres, regla, carpetas=None, extractos=None):
        self.pedido = (nombres, regla)
        self.pedido_carpetas = carpetas
        self.pedido_extractos = extractos
        self.pedidos_ia.append((list(nombres), regla, dict(extractos or {})))
        if callable(self.plan):
            return self.plan(nombres, regla)
        return self.plan

    def clasificar_y_mover(self, origen, destino, plan, copiar=False):
        self.movido = (origen, destino, plan)
        self.movido_copiar = copiar
        return f"{'Copiados' if copiar else 'Movidos'} 2 de 2 archivo(s):"


def con_asistente(sharepoint):
    """Un SystemActions de verdad (para usar sus ayudantes) con SharePoint de mentira.

    Solo se le pone el SharePoint: `_listar_sharepoint` y `_clasificar_archivos` no
    tocan nada más del objeto, así que no hace falta montar sus herramientas (y el
    import se queda dentro, como el resto de pruebas de acciones).
    """
    from modules.system_actions import SystemActions

    class AsistenteFalso(SystemActions):
        def __init__(self, sp):
            self.sharepoint = sp
            # Canal de progreso propio: así la prueba puede escuchar lo que la
            # acción cuenta antes de ejecutarse, como hace la ventana.
            self.progreso = Progreso()

    return AsistenteFalso(sharepoint)


class _MensajeIAClasificador:
    def __init__(self, contenido):
        self.content = contenido


class _RespuestaIAClasificador:
    def __init__(self, contenido):
        self.choices = [type("C", (), {"message": _MensajeIAClasificador(contenido)})()]


class ClienteIAClasificadorFalso:
    """Cliente mínimo de OpenAI: lo que la IA contestaría, sin red."""

    def __init__(self, respuesta="Acta.docx|Actas\nViejo.pptx|dejar"):
        self.respuesta = respuesta
        self.mensajes = None
        self.chat = self
        self.completions = self

    def create(self, **datos):
        self.mensajes = datos["messages"]
        return _RespuestaIAClasificador(self.respuesta)

    def instrucciones(self):
        """Todo lo que se le mandó a la IA (sistema + prompt), en un texto."""
        return " ".join(m["content"] for m in (self.mensajes or []))


def cerebro_de_prueba(respuesta="Acta.docx|Actas\nViejo.pptx|dejar"):
    """Un APIBrain sin constructor (ni API Key ni red) con cliente de mentira."""
    from modules.api_brain import APIBrain

    cerebro = APIBrain.__new__(APIBrain)
    cliente = ClienteIAClasificadorFalso(respuesta)
    cerebro.client = cliente
    return cerebro, cliente


def pruebas_documentos():

    """Revisar carpetas: también dentro de las subcarpetas y solo Word/PowerPoint.

    Es lo que hace la acción CLASIFICAR_ARCHIVOS antes de clasificar: si el
    listado no baja a las subcarpetas, una carpeta con los documentos dentro
    parece vacía (fue justo el fallo que se arregló aquí).
    """
    print("\n== Documentos (recursivo y filtrado) ==")
    sp = con_arbol()
    listado = sp.listar_documentos(COLOMBIA)
    comprobar([a["rel"] for a in listado["archivos"]]
              == ["Propuesta.docx", "Viejo.doc", "Charla.ppt",
                  "2026/Acta.PPTX", "2026/Informe.doc",
                  "2026/Viejo/Antiguo.pptx"],
              "baja por las subcarpetas y guarda la ruta relativa")
    comprobar([a["ruta_rel"] for a in listado["archivos"]][-1]
              == "/sites/Tech/Colombia/2026/Viejo/Antiguo.pptx",
              "la ruta server-relative sirve para mover")
    comprobar(listado["ignorados"]
              == ["Costos.xlsx", "Demo.mp4", "2026/foto.jpg"],
              "ignora Excel, vídeo e imágenes (y los nombra)")
    comprobar(listado["carpetas"] == 3, "cuenta las carpetas que recorrió")
    comprobar(listado["fallos"] == [] and listado["truncado"] is False,
              "sin fallos ni corte con un árbol normal")
    comprobar("AllItems.aspx" not in str(listado),
              "no entra en las carpetas técnicas (Forms)")

    listado = con_arbol().listar_documentos(COLOMBIA, maximo=2)
    comprobar(len(listado["archivos"]) == 2 and listado["truncado"] is True,
              "corta al llegar al tope de documentos y lo dice")

    listado = con_arbol().listar_documentos(COLOMBIA, extensiones=[])
    comprobar(len(listado["archivos"]) == 9 and listado["ignorados"] == [],
              "sin filtro se lista todo (el filtro es opcional)")

    listado = con_arbol().listar_documentos(COLOMBIA, extensiones=".docx")
    comprobar([a["rel"] for a in listado["archivos"]] == ["Propuesta.docx"],
              "acepta una extensión suelta y filtra por ella")

    # El filtro por nombre ('solo') es lo que permite probar con UN archivo sin
    # recorrer la biblioteca a mano: 'acta' o incluso la subcarpeta ('2026/viejo').
    listado = con_arbol().listar_documentos(COLOMBIA, solo="acta")
    comprobar([a["rel"] for a in listado["archivos"]] == ["2026/Acta.PPTX"],
              "con 'solo' se queda únicamente con los que coinciden")
    comprobar(listado["excluidos"] == ["Propuesta.docx", "Viejo.doc",
                                       "Charla.ppt", "2026/Informe.doc",
                                       "2026/Viejo/Antiguo.pptx"],
              "y cuenta aparte los documentos que deja fuera el filtro")

    listado = con_arbol().listar_documentos(COLOMBIA, solo="2026/viejo")
    comprobar([a["rel"] for a in listado["archivos"]]
              == ["2026/Viejo/Antiguo.pptx"],
              "el filtro también vale por subcarpeta y sin distinguir mayúsculas")

    listado = con_arbol().listar_documentos(COLOMBIA, solo="ACTÁ")
    comprobar([a["rel"] for a in listado["archivos"]] == ["2026/Acta.PPTX"],
              "el filtro no distingue mayúsculas ni acentos")

    listado = con_arbol().listar_documentos(COLOMBIA, solo="presupuesto, 2025")
    comprobar(listado["archivos"] == [] and len(listado["excluidos"]) == 6,
              "si el filtro no coincide con nada, la lista va vacía (nada se pierde)")

    listado = con_arbol(sin_permiso=("/sites/Tech/Colombia/2026",)) \
        .listar_documentos(COLOMBIA)
    comprobar([a["rel"] for a in listado["archivos"]]
              == ["Propuesta.docx", "Viejo.doc", "Charla.ppt"],
              "una subcarpeta sin permiso no tira el resto del listado")
    comprobar(len(listado["fallos"]) == 1 and "403" in listado["fallos"][0],
              "avisa de la subcarpeta que no pudo leer")

    llamadas = []
    con_arbol(llamadas=llamadas).listar_documentos(COLOMBIA)
    comprobar(sum(1 for r in llamadas if r.endswith("?$select=Name")) == 1,
              "solo pregunta si existe la carpeta de partida")

    listado = con_arbol().listar_documentos(
        "https://contoso.sharepoint.com/sites/Tech/Colombia/Forms/AllItems.aspx"
        "?id=%2Fsites%2FTech%2FColombia&viewid=cc6180f7")
    comprobar(listado["archivos"][0]["rel"] == "Propuesta.docx",
              "acepta la URL de la vista con id= (la que copia SharePoint)")

    listado = con_arbol({
        "/sites/Tech/Colombia 2026": {
            "archivos": [("Acta 2026.docx", 5)],
            "carpetas": ["/sites/Tech/Colombia 2026/Olas & mar"],
        },
        "/sites/Tech/Colombia 2026/Olas & mar": {
            "archivos": [("Informe final.docx", 6)],
            "carpetas": [],
        },
    }).listar_documentos(
        "https://contoso.sharepoint.com/sites/Tech/Colombia%202026")
    comprobar([a["rel"] for a in listado["archivos"]]
              == ["Acta 2026.docx", "Olas & mar/Informe final.docx"],
              "los espacios y los '&' de las rutas van y vienen bien")

    listado = con_arbol(paginado=("/sites/Tech/Colombia",)) \
        .listar_documentos(COLOMBIA)
    comprobar(len(listado["archivos"]) == 6 and listado["ignorados"] ==
              ["Costos.xlsx", "Demo.mp4", "2026/foto.jpg"],
              "sigue las páginas (__next) de una carpeta con muchos archivos")

    try:
        con_arbol().listar_documentos(
            "https://contoso.sharepoint.com/sites/Tech/NoExiste")
        comprobar(False, "avisa cuando la carpeta pedida no existe")
    except ErrorSharePoint as e:
        comprobar("no existe" in str(e),
                  "avisa cuando la carpeta pedida no existe")


def pruebas_plan_con_subcarpetas():
    """El plan puede traer la ruta del documento dentro de la carpeta de origen."""
    print("\n== Mover documentos de subcarpetas ==")
    sp = con_arbol()
    movidos = []
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp.crear_carpeta = lambda sitio, rel: None
    sp._carpetas = lambda sitio, rel: []
    sp.mover = lambda sitio, origen, destino, nombre: movidos.append(
        (sitio, origen, destino, nombre))

    resumen = sp.clasificar_y_mover(
        COLOMBIA, COLOMBIA + "/Archivado", [("2026/Acta.PPTX", "Actas")])
    comprobar(movidos == [(SITIO, "/sites/Tech/Colombia/2026/Acta.PPTX",
                           "/sites/Tech/Colombia/Archivado/Actas",
                           "Acta.PPTX")],
              "mueve desde su subcarpeta y en destino deja solo el nombre")
    comprobar("2026/Acta.PPTX → Actas" in resumen,
              "el resumen enseña de qué subcarpeta venía")


def pruebas_clasificar_y_mover():
    print("\n== Clasificar y mover ==")
    sp = SharePoint()
    creadas, movidos = [], []
    sp._carpetas = lambda sitio, rel: [{"nombre": "Otros", "ruta_rel": "/x"}]
    sp.crear_carpeta = lambda sitio, rel: creadas.append(rel)
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp.mover = lambda sitio, origen, destino, nombre: movidos.append(
        (origen, destino, nombre))

    resumen = sp.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Destino",
        [("a.pdf", "Estimaciones"), ("b.docx", "Otros"), ("c.txt", "")])

    comprobar(creadas == ["/sites/Tech/Destino/Estimaciones"],
              "crea solo la subcarpeta que falta")
    comprobar(len(movidos) == 3, "mueve los tres archivos")
    comprobar(movidos[0] == ("/sites/Tech/Origen/a.pdf",
                             "/sites/Tech/Destino/Estimaciones", "a.pdf"),
              "origen y destino correctos para el primer archivo")
    comprobar(movidos[2][1] == "/sites/Tech/Destino",
              "sin subcarpeta deja el archivo en la raíz del destino")
    comprobar("Movidos 3 de 3" in resumen, "resume los movimientos")
    comprobar("(raíz)" in resumen, "marca los que van a la raíz")

    sp2 = SharePoint()
    sp2.crear_carpeta = lambda sitio, rel: None
    sp2._carpetas = lambda sitio, rel: []
    sp2.carpeta_existe = lambda sitio, rel: True
    sp2.archivo_existe = lambda sitio, rel: False

    def mover_falla(sitio, origen, destino, nombre):
        raise ErrorSharePoint("no me dejan")

    sp2.mover = mover_falla
    resumen = sp2.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Destino", [("a.pdf", "X")])
    comprobar("Movidos 0 de 1" in resumen and "no me dejan" in resumen,
              "los fallos no abortan el resto y se listan")

    sp3 = SharePoint()
    movidos3 = []
    sp3._carpetas = lambda sitio, rel: []
    sp3.crear_carpeta = lambda sitio, rel: None
    sp3.carpeta_existe = lambda sitio, rel: True
    # SharePoint no distingue mayúsculas: la comprobación la hace él, así que
    # 'a.pdf' existe aunque el destino guarde 'A.PDF'.
    sp3.archivo_existe = lambda sitio, rel: rel.lower().endswith("a.pdf")
    sp3.mover = lambda sitio, origen, destino, nombre: movidos3.append(nombre)
    resumen = sp3.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Destino",
        [("A.PDF", "X"), ("b.pdf", "X")])
    comprobar(movidos3 == ["b.pdf"], "no pisa el archivo que ya existía en destino")
    comprobar("Movidos 1 de 2" in resumen and "Ya existían" in resumen,
              "el resumen avisa de los que ya existían")

    sp4 = SharePoint()
    movidos4 = []
    sp4._carpetas = lambda sitio, rel: []
    sp4.crear_carpeta = lambda sitio, rel: None
    sp4.archivo_existe = lambda sitio, rel: False
    sp4.mover = lambda sitio, origen, destino, nombre: movidos4.append(nombre)

    def carpeta_sin_permiso(sitio, rel):
        if rel.endswith("/X"):
            error = ErrorSharePoint("SharePoint respondió 403 (Acceso denegado)")
            error.estado = 403
            raise error
        return True

    sp4.carpeta_existe = carpeta_sin_permiso
    resumen = sp4.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Destino", [("a.pdf", "X")])
    comprobar(movidos4 == [],
              "si no puede comprobar el destino no mueve (así no pisa nada)")
    comprobar("no pude comprobar el destino" in resumen.lower() and "403" in resumen,
              "el resumen explica por qué no lo movió")

    sp5 = SharePoint()
    creados5 = []
    sp5._carpetas = lambda sitio, rel: []
    sp5.crear_carpeta = lambda sitio, rel: creados5.append(rel)
    sp5.carpeta_existe = lambda sitio, rel: rel != "/sites/Tech/Nuevo"
    sp5.archivo_existe = lambda sitio, rel: False
    sp5.mover = lambda sitio, origen, destino, nombre: None
    sp5.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Nuevo", [("a.pdf", "")])
    comprobar(creados5 == ["/sites/Tech/Nuevo"],
              "crea la carpeta destino si todavía no existe")

    sp6 = SharePoint()
    sp6._carpetas = lambda sitio, rel: []
    sp6.crear_carpeta = lambda sitio, rel: None
    sp6.archivo_existe = lambda sitio, rel: False

    def carpeta_destino_fallida(sitio, rel):
        error = ErrorSharePoint("SharePoint respondió 403 (Acceso denegado)")
        error.estado = 403
        raise error

    sp6.carpeta_existe = carpeta_destino_fallida
    resumen = sp6.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        "https://contoso.sharepoint.com/sites/Tech/Otro", [("a.pdf", "")])
    comprobar("No moví nada" in resumen and "403" in resumen,
              "si el destino entero no se puede ni mirar, no intenta nada")

    # Mover entre sitios distintos ya no es un error: lo resuelve el puente
    # (descargar, subir y reciclar el original). Se prueba en pruebas_puente().


def pruebas_dejar_archivos():
    """La regla puede pedir que un archivo se quede: la IA contesta 'dejar'.

    Con eso, una sola regla reparte unos cuantos documentos por carpeta y deja
    el resto quieto, sin tener que enumerar antes los que sí se mueven (que era
    lo que obligaba a una ida y vuelta de mensajes).
    """
    print("\n== Dejar archivos donde están ==")
    for marca in ("dejar", "DEJAR", "(dejar)", "- dejar -", "  Dejar.  ",
                  "no lo muevas", "sin mover", "se queda donde está",
                  "déjalo donde estaba"):
        comprobar(SharePoint.es_dejar(marca),
                  f"'{marca}' quiere decir 'déjalo donde está'")
    for carpeta in ("Otros", "Dejar constancia", "Bolsa de horas",
                    "Propuestas", "", "(raíz)"):
        comprobar(not SharePoint.es_dejar(carpeta),
                  f"'{carpeta}' es una carpeta de verdad, no una marca de dejar")

    origen = "https://contoso.sharepoint.com/sites/Tech/Origen"
    destino = "https://contoso.sharepoint.com/sites/Tech/Destino"
    sp = SharePoint()
    movidos, pasos, avisos = [], [], []
    sp.progreso.conectar(
        lambda texto, tipo: (pasos if tipo == "paso" else avisos).append(texto))
    sp._carpetas = lambda sitio, rel: []
    sp.crear_carpeta = lambda sitio, rel: None
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp.mover = lambda sitio, ruta, carpeta, nombre: movidos.append((ruta, nombre))

    resumen = sp.clasificar_y_mover(origen, destino, [
        ("2026/Acta.docx", "Actas"),
        ("2026/Viejo.pptx", "dejar"),
        ("Notas.docx", "no lo muevas"),
    ])
    comprobar(movidos == [("/sites/Tech/Origen/2026/Acta.docx", "Acta.docx")],
              "mueve el que la regla manda a una carpeta y se salta los de 'dejar'")
    comprobar(pasos == ["Moviendo 1 de 1: 2026/Acta.docx → Actas"],
              "cuenta solo los que mueve: el resto no es trabajo pendiente")
    comprobar("Movidos 1 de 1" in resumen,
              "y el resumen no dice 'de 3' como si le faltaran dos")
    comprobar("Se quedan donde estaban" in resumen
              and "2026/Viejo.pptx" in resumen and "Notas.docx" in resumen,
              "nombra los que se quedan donde estaban")
    comprobar(any("se quedan donde están" in a for a in avisos),
              "y lo avisa en vivo mientras trabaja")

    # Si la regla deja todo, no se toca nada y no se dice 'Movidos 0 de 0'.
    movidos.clear()
    resumen = sp.clasificar_y_mover(origen, destino, [("Acta.docx", "dejar"),
                                                      ("Otro.pptx", "Dejar.")])
    comprobar(not movidos, "con todo en 'dejar' no mueve ni un archivo")
    comprobar(resumen.startswith("Nada que mover") and "Acta.docx" in resumen,
              "y lo dice claro en vez de 'Movidos 0 de 0'")

    # Clasificar dentro de la MISMA biblioteca suele mandar cada archivo a la
    # carpeta en la que ya está: no es un movimiento ni un choque de nombres.
    movidos.clear()
    resumen = sp.clasificar_y_mover(origen, origen, [
        ("2026/Acta.docx", "2026"),
        ("2026/Viejo.pptx", "dejar"),
        ("Otro.docx", "2025"),
    ])
    comprobar([m[1] for m in movidos] == ["Otro.docx"],
              "solo mueve el que cambia de carpeta (los que ya están no se tocan)")
    comprobar("Ya estaban en su carpeta" in resumen and "2026/Acta.docx" in resumen
              and "Ya existían en el destino" not in resumen,
              "y lo informa como 'ya estaba en su carpeta', no como choque")
    comprobar("Movidos 1 de 1" in resumen,
              "sin contar como pendientes los que ya estaban en su sitio")

    # El clasificador (la IA) tiene que saber que puede contestar 'dejar'.
    cerebro, cliente = cerebro_de_prueba()
    plan = cerebro.clasificar_archivos(["Acta.docx", "Viejo.pptx"], "deja uno")
    comprobar(plan == [("Acta.docx", "Actas"), ("Viejo.pptx", "dejar")],
              "el plan de la IA llega con 'dejar' tal cual (quien pasa lo entiende)")
    instrucciones = cliente.instrucciones()
    comprobar("dejar" in instrucciones and "REGLA" in instrucciones,
              "y al clasificador se le dice que puede contestar 'dejar'")


def pruebas_copiar_archivos():
    """Clasificar copiando: la copia queda en su carpeta y el original no se toca."""
    print("\n== Clasificar copiando (sin tocar el original) ==")

    # Qué órdenes piden copiar y cuáles no (ahí se pasa como siempre).
    for orden in ("copia cada archivo en su carpeta", "COPIAR por tipo y año",
                  "duplica cada documento donde toque",
                  "clasifícalos pero sin mover el original",
                  "reparte los documentos dejando el original donde está"):
        comprobar(SharePoint.quiere_copiar(orden), f"'{orden}' pide copiar")
    for orden in ("por tipo y año", "mueve cada uno a su carpeta",
                  "reparte las copias de seguridad por año", ""):
        comprobar(not SharePoint.quiere_copiar(orden),
                  f"'{orden}' NO pide copiar (se pasa como siempre)")

    # CopyTo dentro del mismo sitio: una sola llamada, sin bajar el archivo.
    sp = SharePoint()
    visto = []
    sp._api = lambda sitio, ruta, metodo="GET", datos=None: visto.append(
        (sitio, ruta, metodo))
    sp.copiar(SITIO, "/sites/Tech/Origen/Acta.docx",
              "/sites/Tech/Destino/Actas", "Acta.docx")
    comprobar(visto == [(
        SITIO,
        "/web/GetFileByServerRelativeUrl('/sites/Tech/Origen/Acta.docx')"
        "/CopyTo(strNewUrl='/sites/Tech/Destino/Actas/Acta.docx',"
        "bOverwrite=false)", "POST")],
        "copia dentro del sitio con CopyTo (y sin poder pisar nada)")

    origen = "https://contoso.sharepoint.com/sites/Tech/Origen"
    destino = "https://contoso.sharepoint.com/sites/Tech/Destino"
    sp = SharePoint()
    copiados, movidos, pasos, avisos = [], [], [], []
    sp.progreso.conectar(
        lambda texto, tipo: (pasos if tipo == "paso" else avisos).append(texto))
    sp._carpetas = lambda sitio, rel: []
    sp.crear_carpeta = lambda sitio, rel: None
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp.copiar = lambda sitio, ruta, carpeta, nombre: copiados.append(
        (ruta, carpeta, nombre))
    sp.mover = lambda *a: movidos.append(a)

    resumen = sp.clasificar_y_mover(origen, destino, [
        ("Acta.docx", "QA"), ("Viejo.pptx", "dejar")], copiar=True)
    comprobar(copiados == [("/sites/Tech/Origen/Acta.docx",
                            "/sites/Tech/Destino/QA", "Acta.docx")],
              "copia el que la regla manda y deja el original en su sitio")
    comprobar(not movidos, "en modo copiar no se mueve nada")
    comprobar(pasos == ["Copiando 1 de 1: Acta.docx → QA"],
              "cuenta lo que copia (no dice 'moviendo')")
    comprobar("Copiados 1 de 1" in resumen and "Son COPIAS" in resumen
              and "originales siguen donde estaban" in resumen,
              "y el resumen deja claro que el original no se ha tocado")
    comprobar("Se quedan donde estaban" in resumen and "Viejo.pptx" in resumen,
              "el que la regla deja quieto tampoco se copia")

    # Entre sitios el puente copia con el navegador: con copiar=True no recicla.
    sp2 = SharePoint()
    reciclados = []
    sp2._carpetas = lambda sitio, rel: []
    sp2.crear_carpeta = lambda sitio, rel: None
    sp2.carpeta_existe = lambda sitio, rel: True
    sp2.archivo_existe = lambda sitio, rel: False
    sp2._descargar = lambda sitio, rel: ("QUJD", 3)
    sp2._subir = lambda *a: None
    sp2._tamano = lambda sitio, rel: 3
    sp2._reciclar = lambda sitio, rel: reciclados.append((sitio, rel))
    resumen = sp2.clasificar_y_mover(
        SITIO + "/Origen", PERSONAL + "/Documents/Entrada",
        [("a.pdf", "Estimaciones")], copiar=True)
    comprobar(not reciclados,
              "entre sitios la copia deja el original (no va a la papelera)")
    comprobar("originales se quedan donde" in resumen,
              "y el resumen lo dice")
    sp2.clasificar_y_mover(
        SITIO + "/Origen", PERSONAL + "/Documents/Entrada",
        [("b.pdf", "Estimaciones")])
    comprobar(reciclados == [(SITIO, "/sites/Tech/Origen/b.pdf")],
              "sin pedir copia sí recicla el original (mover de verdad)")

    # La acción: lo pide la orden de la regla o la bandera ';;copiar'.
    listado = {"archivos": [{"nombre": "Propuesta.docx", "rel": "Propuesta.docx",
                             "ruta_rel": "/sites/Tech/Colombia/Propuesta.docx",
                             "tamano": 10}],
               "ignorados": [], "excluidos": [], "carpetas": 1,
               "fallos": [], "truncado": False}
    sp3 = SharepointFalso(listado, [("Propuesta.docx", "Clientes")])
    texto = con_asistente(sp3)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;copia cada uno en su carpeta")
    comprobar(sp3.movido_copiar is True and "Modo copiar" in texto,
              "la orden 'copia...' de la regla se ejecuta como copia")

    sp4 = SharepointFalso(listado, [("Propuesta.docx", "Clientes")])
    con_asistente(sp4)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo;;copiar")
    comprobar(sp4.movido_copiar is True
              and sp4.pedido_listado == (COLOMBIA, ""),
              "la bandera ';;copiar' copia y no se confunde con el filtro")

    sp5 = SharepointFalso(listado, [("Propuesta.docx", "Clientes")])
    con_asistente(sp5)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar(sp5.movido_copiar is False,
              "sin pedir copia se pasa como siempre (nada cambia por defecto)")


def pruebas_carpetas_destino():
    """La IA elige entre las carpetas que ya hay y nada acaba suelto en la raíz."""
    print("\n== Carpetas del destino (nada suelto) ==")

    ramas = ["Assessment", "Bolsa de horas", "Licenciamiento", "QA",
             "Soporte y-o administración", "Otros"]
    comprobar(SharePoint.normalizar_carpeta("QA", ramas) == "QA",
              "el nombre tal cual se respeta")
    comprobar(SharePoint.normalizar_carpeta("qa", ramas) == "QA",
              "un 'qa' en minúsculas cae en la carpeta real 'QA'")
    comprobar(SharePoint.normalizar_carpeta(" qa ", ramas) == "QA",
              "y con espacios de más también")
    comprobar(SharePoint.normalizar_carpeta("soporte", ramas)
              == "Soporte y-o administración",
              "un nombre corto encaja con la carpeta de verdad")
    comprobar(SharePoint.normalizar_carpeta("Bolsa de horas 2026", ramas)
              == "Bolsa de horas",
              "y uno más largo que empieza por ella también")
    comprobar(SharePoint.normalizar_carpeta(
        "qa", ["Quality Assurance", "Assessment"]) == "Quality Assurance",
        "unas siglas encajan con la carpeta ('QA' -> 'Quality Assurance')")
    for raro in ("", "(raíz)", "sin clasificar", "Invntada"):
        comprobar(SharePoint.normalizar_carpeta(raro, ramas) == "",
                  f"'{raro}' no es ninguna carpeta real del destino")

    # El plan corregido: 'dejar' se respeta, lo que no encaja se avisa y lo que
    # llega sin carpeta va a 'Otros' (nunca a la raíz).
    plan, avisos = SharePoint.encajar_plan([
        ("a.docx", "qa"), ("b.docx", ""), ("c.docx", "dejar"),
        ("d.docx", "Nueva rama"), ("e.docx", "Otros"),
    ], ramas)
    comprobar([sub for _n, sub in plan] == ["QA", "Otros", "dejar",
                                            "Nueva rama", "Otros"],
              "encaja cada respuesta con la carpeta real y nada queda vacío")
    comprobar(any("Nueva rama" in a for a in avisos),
              "avisa de la carpeta que no existe (se creará esa)")
    comprobar(any("Sin carpeta clara" in a for a in avisos)
              and any("b.docx" in a for a in avisos),
              "y avisa de los que se van a 'Otros' por no saber dónde van")
    comprobar(not any("+ " in a and "Otros" in a for a in avisos),
              "'Otros' es el cajón de siempre: no se avisa como carpeta nueva")

    # La acción le pasa a la IA las carpetas que hay en el DESTINO.
    listado = {"archivos": [{"nombre": "Acta.PPTX", "rel": "Acta.PPTX",
                             "ruta_rel": "/sites/Tech/Colombia/Acta.PPTX",
                             "tamano": 20}],
               "ignorados": [], "excluidos": [], "carpetas": 1,
               "fallos": [], "truncado": False}
    sp = SharepointFalso(listado, [("Acta.PPTX", "QA")],
                         carpetas=("Assessment", "QA", "Forms"))
    con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por rama")
    comprobar(sp.pedido_carpetas == ["Assessment", "QA"],
              "la IA recibe las carpetas que ya hay (sin las técnicas)")
    comprobar(sp.pedido_carpetas_destino == COLOMBIA + "/Archivo",
              "y se leen del destino, no del origen")
    comprobar(sp.movido[2] == [("Acta.PPTX", "QA")],
              "el archivo va a la carpeta real que ya existía")

    # Si la IA contesta algo que no existe, no se crea nada en silencio.
    sp = SharepointFalso(listado, [("Acta.PPTX", "Quality Assurance")],
                         carpetas=("QA",))
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por rama")
    comprobar("no son ninguna de las que ya hay" in texto
              and "Quality Assurance" in texto,
              "si se inventa un nombre, se respeta pero se avisa")

    # Sin carpeta clara: a 'Otros', nunca suelto en la raíz del destino.
    sp = SharepointFalso(listado, [("Acta.PPTX", "")], carpetas=("QA",))
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por rama")
    comprobar(sp.movido[2] == [("Acta.PPTX", "Otros")],
              "sin carpeta el archivo va a 'Otros' (no se queda en la raíz)")
    comprobar("Sin carpeta clara" in texto, "y lo dice en el resumen")

    # Si no se pueden leer las carpetas del destino, se dice y se sigue.
    sp = SharepointFalso(listado, [("Acta.PPTX", "QA")],
                         error_carpetas=ErrorSharePoint("403"))
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por rama")
    comprobar(sp.pedido_carpetas == []
              and "No pude leer las carpetas del destino" in texto,
              "sin poder leerlas avisa (la IA podría crear nombres nuevos)")

    # Lo que se le pide a la IA: elegir entre las que hay y no dejar nada sin
    # carpeta.
    cerebro, cliente = cerebro_de_prueba("Acta.docx|QA")
    plan = cerebro.clasificar_archivos(["Acta.docx"], "por rama",
                                       ["QA", "Assessment"])
    instrucciones = cliente.instrucciones()
    comprobar("ESTAS CARPETAS YA EXISTEN EN EL DESTINO" in instrucciones
              and "- QA" in instrucciones and "- Assessment" in instrucciones,
              "el prompt le pasa las carpetas reales para que elija entre ellas")
    comprobar("NUNCA dejes un archivo sin carpeta" in instrucciones,
              "y le prohíbe dejar un archivo sin carpeta")
    comprobar(plan == [("Acta.docx", "QA")], "el plan llega tal cual")

    cerebro, cliente = cerebro_de_prueba("Acta.docx|Actas")
    plan = cerebro.clasificar_archivos(["Acta.docx", "Olvidado.pptx"], "por tipo")
    comprobar(plan == [("Acta.docx", "Actas"), ("Olvidado.pptx", "Otros")],
              "si la IA se olvida de uno, va a 'Otros' (no se queda sin carpeta)")

def _word_en_memoria(*parrafos):
    """Un .docx de verdad, en memoria: lo que se baja de SharePoint."""
    from docx import Document

    documento = Document()
    for parrafo in parrafos:
        documento.add_paragraph(parrafo)
    guardado = io.BytesIO()
    documento.save(guardado)
    return guardado.getvalue()


def _word_con_tabla_en_memoria(*celdas):
    """Un .docx con una tabla: ahí es donde van el cliente, el tipo y el mes."""
    from docx import Document

    documento = Document()
    tabla = documento.add_table(rows=1, cols=len(celdas))
    for celda, texto in zip(tabla.rows[0].cells, celdas):
        celda.text = texto
    guardado = io.BytesIO()
    documento.save(guardado)
    return guardado.getvalue()


def _powerpoint_en_memoria(*textos):
    """Un .pptx de verdad, en memoria (con su diapositiva de título)."""
    from pptx import Presentation

    presentacion = Presentation()
    for texto in textos:
        diapositiva = presentacion.slides.add_slide(presentacion.slide_layouts[0])
        diapositiva.shapes.title.text = texto
    guardado = io.BytesIO()
    presentacion.save(guardado)
    return guardado.getvalue()


def pruebas_leer_contenido():
    """Clasificar leyendo por dentro: el nombre deja de ser la única pista.

    Un `Documento1.docx` no dice nada, y acaba en 'Otros' o mal colocado. Con el
    texto de dentro (que se baja con la pestaña de Brave, sin pasar por disco) la
    IA sí sabe de qué va cada archivo. Leer cuesta una bajada por documento, así
    que la orden puede pedir ir por el nombre (';;sin leer').
    """
    print("\n== Leer el contenido de los documentos ==")
    import base64

    from modules import documentos

    comprobar(documentos.extension("2026/Acta.PPTX") == ".pptx",
              "la extensión se mira en minúsculas y sin la carpeta")

    texto, motivo = documentos.texto_de_documento(
        _word_en_memoria("Propuesta de soporte para el cliente Bavaria",
                         "Bolsa de horas 2026"), "Documento1.docx")
    comprobar(texto.startswith("Propuesta de soporte para el cliente Bavaria")
              and "Bolsa de horas 2026" in texto and motivo == "",
              "de un Word se saca su texto (aunque el nombre no diga nada)")

    texto, motivo = documentos.texto_de_documento(
        _powerpoint_en_memoria("Assessment de seguridad QA"), "Charla.pptx")
    comprobar("Assessment de seguridad QA" in texto and motivo == "",
              "y de un PowerPoint, el texto de sus diapositivas")

    texto, motivo = documentos.texto_de_documento(
        _word_con_tabla_en_memoria("Bavaria", "Assessment", "marzo"), "Tabla.docx")
    comprobar(texto == "Bavaria | Assessment | marzo" and motivo == "",
              "las tablas del Word también se leen (ahí va el cliente y el tipo)")

    largo, _ = documentos.texto_de_documento(
        _word_en_memoria("palabra " * 200), "Largo.docx", maximo=50)
    comprobar(len(largo) <= 55 and largo.endswith("[…]"),
              "el extracto se recorta (no se manda el documento entero a la IA)")

    for nombre in ("Viejo.doc", "Viejo.ppt"):
        texto, motivo = documentos.texto_de_documento(b"x" * 10, nombre)
        comprobar(texto == "" and "formato antiguo" in motivo,
                  f"'{nombre}' no se puede abrir por dentro: se dice el motivo")

    texto, motivo = documentos.texto_de_documento(
        _word_en_memoria(), "Vacio.docx")
    comprobar(texto == "" and "texto" in motivo,
              "uno sin texto (solo imágenes) tampoco inventa contenido")

    # SharePoint: se baja con la pestaña del sitio y se saca el extracto.
    sp = SharePoint()
    bajadas = []

    def descarga_falsa(sitio, ruta_rel, limite=None):
        bajadas.append((ruta_rel, limite))
        if ruta_rel.endswith("Enorme.docx"):
            return None, 40 * 1048576
        return base64.b64encode(_word_en_memoria("Assessment QA")), 123

    sp._descargar = descarga_falsa
    archivos = [{"nombre": "Nuevo.docx", "rel": "Nuevo.docx",
                 "ruta_rel": "/sites/Tech/Colombia/Nuevo.docx", "tamano": 10},
                {"nombre": "Viejo.doc", "rel": "Viejo.doc",
                 "ruta_rel": "/sites/Tech/Colombia/Viejo.doc", "tamano": 10},
                {"nombre": "Enorme.docx", "rel": "Enorme.docx",
                 "ruta_rel": "/sites/Tech/Colombia/Enorme.docx", "tamano": 10},
                {"nombre": "Gigante.docx", "rel": "Gigante.docx",
                 "ruta_rel": "/sites/Tech/Colombia/Gigante.docx",
                 "tamano": 40 * 1048576}]
    textos, avisos, leidos = sp.leer_textos(COLOMBIA, archivos)
    comprobar(textos == {"Nuevo.docx": "Assessment QA"} and leidos == 1,
              "el texto se guarda por la ruta relativa del archivo (y se cuenta)")
    comprobar([ruta for ruta, _limite in bajadas]
              == ["/sites/Tech/Colombia/Nuevo.docx",
                  "/sites/Tech/Colombia/Enorme.docx"]
              and all(limite == SharePoint.LIMITE_LECTURA
                      for _ruta, limite in bajadas),
              "no se baja ni el .doc antiguo ni el que ya se ve enorme en el listado")
    comprobar(any("Viejo.doc" in a and "formato antiguo" in a for a in avisos)
              and any("Enorme.docx" in a and "MB" in a for a in avisos)
              and any("Gigante.docx" in a and "MB" in a for a in avisos),
              "lo que no se lee se avisa con su motivo (y ese va por el nombre)")

    # Y si la sesión falla al bajar, no se corta la clasificación: se avisa.
    sp = SharePoint()

    def descarga_rota(sitio, ruta_rel, limite=None):
        raise ErrorSharePoint("SharePoint respondió 403")

    sp._descargar = descarga_rota
    textos, avisos, leidos = sp.leer_textos(
        COLOMBIA, [archivos[0]] * 4)
    comprobar(textos == {} and leidos == 0
              and sum(1 for a in avisos if "no pude bajar" in a) == 3
              and any("Dejo de leer" in a for a in avisos),
              "si no puede bajar, avisa y deja de insistir (no 4 intentos)")

    # La acción: lee el contenido y se lo da a la IA pegado a cada nombre (sin
    # leer nada si la orden dice ';;sin leer').
    listado = {"archivos": [{"nombre": "Documento1.docx", "rel": "Documento1.docx",
                             "ruta_rel": "/sites/Tech/Colombia/Documento1.docx",
                             "tamano": 10}],
               "ignorados": [], "excluidos": [], "carpetas": 1,
               "fallos": [], "truncado": False}
    comprobar(SharePoint.quiere_sin_leer("clasifícalos sin leerlos")
              and SharePoint.quiere_sin_leer("solo por el nombre")
              and not SharePoint.quiere_sin_leer("lee los documentos y clasifícalos"),
              "se entiende 'sin leer' dicho de varias formas (y leer es lo normal)")

    sp = SharepointFalso(
        listado, [("Documento1.docx", "QA")], carpetas=("QA", "Otros"),
        textos={"Documento1.docx": "Assessment | seguridad para el cliente X"})
    cerebro, cliente = cerebro_de_prueba("Documento1.docx|QA")
    sp.on_clasificar = cerebro.clasificar_archivos    # la IA de verdad, sin red
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por lo que ponga dentro")
    comprobar(sp.pedidos_lectura == [(COLOMBIA, ["Documento1.docx"])]
              and "> texto del documento: Assessment / seguridad para el cliente X"
              in cliente.instrucciones(),
        "la acción lee el contenido y se lo pasa a la IA (limpiando los '|')")
    comprobar("Leí el contenido de 1 de 1 documento(s)" in texto
              and sp.movido[2] == [("Documento1.docx", "QA")],
              "lo cuenta en el resumen y coloca el archivo donde toca")

    # ';;sin leer' en el hueco del filtro: ni se baja nada ni se toma por filtro.
    sp = SharepointFalso(
        listado, [("Documento1.docx", "QA")], carpetas=("QA",),
        textos={"Documento1.docx": "Assessment QA"})
    cerebro, cliente = cerebro_de_prueba("Documento1.docx|QA")
    sp.on_clasificar = cerebro.clasificar_archivos
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo;;sin leer")
    comprobar(sp.pedidos_lectura == [] and sp.pedido_extractos is None,
              "';;sin leer' no baja ni un documento: se va por el nombre")
    comprobar(sp.pedido_listado == (COLOMBIA, ""),
              "y no se toma 'sin leer' por un filtro de nombres")
    comprobar("texto del documento" not in cliente.instrucciones()
              and "Modo rápido" in texto,
              "no se le manda texto a la IA y se avisa de que va por el nombre")

    # Si leer falla (sesión caída), se avisa y la clasificación sigue por nombre.
    sp = SharepointFalso(listado, [("Documento1.docx", "QA")], carpetas=("QA",),
                         error_lectura=ErrorSharePoint("403"))
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar("No pude leer el contenido" in texto and sp.movido is not None,
              "si leer falla se dice y el archivo se coloca igual (por su nombre)")

    # Con muchos documentos la IA va por lotes: no una llamada gigante que se corta.
    muchos = {"archivos": [{"nombre": f"Doc{i}.docx", "rel": f"Doc{i}.docx",
                            "ruta_rel": f"/sites/Tech/Colombia/Doc{i}.docx",
                            "tamano": 10} for i in range(1, 27)],
              "ignorados": [], "excluidos": [], "carpetas": 1, "fallos": [],
              "truncado": False}
    sp = SharepointFalso(
        muchos, lambda nombres, regla: [(n, "QA") for n in nombres],
        carpetas=("QA",),
        textos={f"Doc{i}.docx": "assessment" for i in range(1, 27)})
    con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar([len(p[0]) for p in sp.pedidos_ia] == [25, 1],
              "con 26 documentos la IA va en lotes de 25 (no una sola llamada)")
    comprobar([len(p[2]) for p in sp.pedidos_ia] == [25, 1],
              "y cada lote lleva solo los textos de sus documentos")
    comprobar(len(sp.movido[2]) == 26
              and all(sub == "QA" for _n, sub in sp.movido[2]),
              "el plan de todos los lotes se junta entero")


def pruebas_puente():
    """Mover entre sitios: copiar con el navegador y reciclar el original."""
    print("\n== Puente entre sitios (copiar y reciclar) ==")

    eventos = []

    def descarga_falsa(sitio, ruta):
        eventos.append(("descargar", sitio, ruta))
        return "QUJD", 3

    def subida_falsa(sitio, carpeta, nombre, b64):
        eventos.append(("subir", sitio, carpeta, nombre, b64))

    def tamano_falso(sitio, ruta):
        eventos.append(("tamano", sitio, ruta))
        return 3

    def reciclar_falso(sitio, ruta):
        eventos.append(("reciclar", sitio, ruta))

    sp = SharePoint()
    sp._descargar = descarga_falsa
    sp._subir = subida_falsa
    sp._tamano = tamano_falso
    sp._reciclar = reciclar_falso
    sp.mover_entre_sitios(SITIO, "/sites/Tech/Origen/a.pdf", PERSONAL,
                          "/personal/john_doe_contoso_com/Documents", "a.pdf")
    comprobar(eventos == [
        ("descargar", SITIO, "/sites/Tech/Origen/a.pdf"),
        ("subir", PERSONAL, "/personal/john_doe_contoso_com/Documents",
         "a.pdf", "QUJD"),
        ("tamano", PERSONAL, "/personal/john_doe_contoso_com/Documents/a.pdf"),
        ("reciclar", SITIO, "/sites/Tech/Origen/a.pdf")],
        "puente: descarga del origen, sube al destino, verifica y recicla")

    # Las peticiones de verdad (pestañas falsas): qué URL y con qué cabeceras.
    sp2 = SharePoint()
    pestana_origen = PestanaPuente(base64_texto="QUJD", tamano=3)
    pestana_destino = PestanaPuente()
    sp2._pestanas[SITIO] = pestana_origen
    sp2._pestanas[PERSONAL] = pestana_destino
    base64_texto, tamano = sp2._descargar(SITIO, "/sites/Tech/Origen/a b'c.pdf")
    comprobar((base64_texto, tamano) == ("QUJD", 3),
              "la descarga devuelve los bytes (base64) y el tamaño")
    js = pestana_origen.visto[-1]
    comprobar("GetFileByServerRelativeUrl('/sites/Tech/Origen/a%20b''c.pdf')"
              "/$value" in js,
              "la descarga pide el contenido ($value) del archivo")
    comprobar("credentials:'include'" in js,
              "la descarga va con la sesión del navegador")
    comprobar("r.redirected" in js and "Content-Type" in js,
              "la descarga desconfía si le llega una página web en vez del archivo")

    sp_aviso = SharePoint()
    sp_aviso._pestanas[PERSONAL] = PestanaFalsa({"estado": 200, "html": True})
    try:
        sp_aviso._descargar(PERSONAL, "/personal/john_doe_contoso_com/Documents/a.pdf")
        comprobar(False, "si la descarga trae una página web, avisa de la sesión")
    except ErrorSharePoint as e:
        comprobar("sesión" in str(e),
                  "si la descarga trae una página web, avisa de la sesión")

    sp2._subir(PERSONAL, "/personal/john_doe_contoso_com/Documents", "a.pdf",
               "QUJD")
    js = pestana_destino.visto[-1]
    comprobar("Files/Add(url='a.pdf',overwrite=false)" in js,
              "la subida usa Files/Add y no sobrescribe lo que ya hubiera")
    comprobar("GetFolderByServerRelativeUrl('/personal/john_doe_contoso_com/"
              "Documents')" in js,
              "la subida apunta a la carpeta del destino")
    comprobar("contextinfo" in js and "X-RequestDigest" in js,
              "la subida pide el token de escritura de SU sitio")
    comprobar('atob("QUJD")' in js, "la subida manda los bytes descargados")
    comprobar(len(pestana_origen.visto) == 1,
              "para subir usa la pestaña del destino, no la del origen")

    # Si algo sale mal ANTES de verificar, el original no se toca.
    def puente_con(tamano_destino=3, subida_error=None, descarga=("QUJD", 3)):
        sp_p = SharePoint()
        reciclados = []
        sp_p._descargar = lambda sitio, ruta: descarga
        if subida_error:
            def subir_falla(sitio, carpeta, nombre, b64):
                raise ErrorSharePoint(subida_error)
            sp_p._subir = subir_falla
        else:
            sp_p._subir = lambda sitio, carpeta, nombre, b64: None
        sp_p._tamano = lambda sitio, ruta: tamano_destino
        sp_p._reciclar = lambda sitio, ruta: reciclados.append(ruta)
        return sp_p, reciclados

    def intentar(sp_p, texto):
        try:
            sp_p.mover_entre_sitios(SITIO, "/sites/Tech/Origen/a.pdf", PERSONAL,
                                    "/personal/john_doe_contoso_com/Documents",
                                    "a.pdf")
            comprobar(False, texto)
        except ErrorSharePoint as e:
            return str(e)
        return ""

    sp3, reciclados3 = puente_con(tamano_destino=99)
    error3 = intentar(sp3, "si el tamaño no cuadra no recicla el original")
    comprobar("otro tamaño" in error3 and reciclados3 == [],
              "si el tamaño no cuadra no recicla el original")

    sp4, reciclados4 = puente_con(subida_error="SharePoint respondió 403")
    error4 = intentar(sp4, "si la subida falla no recicla el original")
    comprobar("403" in error4 and reciclados4 == [],
              "si la subida falla no recicla el original")

    sp5, reciclados5 = puente_con(descarga=(None, 200 * 1024 * 1024))
    error5 = intentar(sp5, "un archivo enorme se explica y no se copia")
    comprobar("MB" in error5 and "Copiar a" in error5 and reciclados5 == [],
              "un archivo enorme se explica y no se copia")

    sp6 = SharePoint()
    sp6._pestanas[SITIO] = PestanaPuente(grande=True, tamano=100 * 1024 * 1024)
    comprobar(sp6._descargar(SITIO, "/sites/Tech/Origen/nota.zip")
              == (None, 100 * 1024 * 1024),
              "la descarga no se trae un archivo que pasa del límite")

    sp7 = SharePoint()
    sp7._pestanas[PERSONAL] = PestanaPuente(
        subida={"estado": 403, "cuerpo": "Acceso denegado"})
    try:
        sp7._subir(PERSONAL, "/personal/john_doe_contoso_com/Documents",
                   "a.pdf", "QUJD")
        comprobar(False, "una subida sin permiso avisa de permiso")
    except ErrorSharePoint as e:
        comprobar("permiso" in str(e), "una subida sin permiso avisa de permiso")

    # Clasificar con el destino en otro sitio: puente, no MoveTo.
    sp8 = SharePoint()
    llamadas = []
    sp8._carpetas = lambda sitio, rel: []
    sp8.crear_carpeta = lambda sitio, rel: llamadas.append(("carpeta", sitio, rel))
    sp8.carpeta_existe = lambda sitio, rel: True
    sp8.archivo_existe = lambda sitio, rel: False
    sp8.mover = lambda *a: llamadas.append(("mover",) + a)
    sp8.mover_entre_sitios = lambda *a, **resto: llamadas.append(("puente",) + a)
    resumen = sp8.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen",
        PERSONAL + "/Documents/Entrada", [("a.pdf", "Estimaciones")])
    comprobar(("puente", SITIO, "/sites/Tech/Origen/a.pdf", PERSONAL,
               "/personal/john_doe_contoso_com/Documents/Entrada/Estimaciones",
               "a.pdf") in llamadas,
              "entre sitios mueve con el puente y con las rutas bien armadas")
    comprobar("Movidos 1 de 1" in resumen and "papelera" in resumen,
              "lo cuenta como movido y avisa de que el original va a la papelera")
    comprobar(("carpeta", PERSONAL, "/personal/john_doe_contoso_com/Documents/"
               "Entrada/Estimaciones") in llamadas,
              "prepara las subcarpetas en el sitio de DESTINO")
    comprobar(not any(llamada[0] == "mover" for llamada in llamadas),
              "entre sitios no intenta MoveTo")

    llamadas.clear()
    sp8.clasificar_y_mover("https://contoso.sharepoint.com/sites/Tech/Origen",
                           "https://contoso.sharepoint.com/sites/Tech/Destino",
                           [("b.pdf", "")])
    comprobar(any(llamada[0] == "mover" for llamada in llamadas)
              and not any(llamada[0] == "puente" for llamada in llamadas),
              "en el mismo sitio sigue usando MoveTo (es más rápido)")

    # La dirección suelta del OneDrive no es una carpeta: los archivos viven en
    # Documentos, y el asistente lo resuelve solo.
    raiz = "https://contoso-my.sharepoint.com/"
    web_personal = {"estado": 200,
                    "cuerpo": '{"d": {"ServerRelativeUrl": '
                              '"/personal/john_doe_contoso_com"}}'}
    sp9 = SharePoint()
    sp9._pestanas[raiz] = PestanaFalsa(web_personal)
    comprobar(sp9._carpeta_destino(sp9.parsear_url(raiz))
              == "/personal/john_doe_contoso_com/Documents",
              "la dirección suelta del OneDrive acaba en Documentos")
    comprobar(sp9._carpeta_destino(sp9.parsear_url(PERSONAL))
              == "/personal/john_doe_contoso_com/Documents",
              "y la raíz del sitio personal también")
    comprobar(sp9._carpeta_destino(sp9.parsear_url(PERSONAL + "/Documents/2026"))
              == "/personal/john_doe_contoso_com/Documents/2026",
              "una carpeta concreta del OneDrive se respeta")
    comprobar(sp9._carpeta_destino(
        sp9.parsear_url("https://contoso.sharepoint.com/sites/Tech/Docs"))
        == "/sites/Tech/Docs",
        "una carpeta de un sitio de equipo se deja como está")

    sp10 = SharePoint()
    sp10._pestanas[raiz] = PestanaFalsa(web_personal)
    sp10._carpetas = lambda sitio, rel: []
    sp10.crear_carpeta = lambda sitio, rel: None
    sp10.carpeta_existe = lambda sitio, rel: True
    sp10.archivo_existe = lambda sitio, rel: False
    sp10.mover_entre_sitios = lambda *a, **resto: None
    resumen10 = sp10.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen", raiz, [("a.pdf", "")])
    comprobar("(destino: /personal/john_doe_contoso_com/Documents)" in resumen10,
              "el resumen dice en qué carpeta acabaron")

    # La raíz del OneDrive de verdad contesta 'ServerRelativeUrl: "/"' (no cuenta
    # cuál es tu carpeta personal) y encima lista '/personal' como vacía. Antes
    # eso acababa moviendo a ciegas a la raíz del sitio; ahora se pide la carpeta.
    sp11 = SharePoint()

    def api_raiz(sitio, ruta, metodo="GET", datos=None):
        if ruta.startswith("/web?$select=ServerRelativeUrl"):
            return {"d": {"ServerRelativeUrl": "/", "Url": sitio}}
        return {"d": {"results": []}}

    sp11._api = api_raiz
    sp11._carpetas = lambda sitio, rel: []
    sp11.crear_carpeta = lambda sitio, rel: None
    sp11.carpeta_existe = lambda sitio, rel: True
    movidos11 = []
    sp11.mover = lambda *a: movidos11.append(a)
    resumen11 = sp11.clasificar_y_mover(
        "https://contoso.sharepoint.com/sites/Tech/Origen", raiz, [("a.pdf", "")])
    comprobar(not movidos11 and resumen11.startswith("No moví nada"),
              "sin carpeta de destino se pide el enlace, no se mueve a la raíz")
    comprobar("carpeta concreta" in resumen11,
              "y el aviso explica qué enlace hace falta")


def pruebas_javascript_valido():
    """Si hay Node instalado, comprueba que el JS construido compila.

    El `_api` arma las llamadas concatenando cadenas; un fallo ahí solo se
    vería al hablar con Brave. Con Node lo detectamos sin abrir el navegador.
    """
    print("\n== El JavaScript generado compila ==")
    node = shutil.which("node")
    if not node:
        print("  --  node no está instalado: se omite la comprobación")
        return
    sp, pestana = con_pestana({"estado": 200, "cuerpo": "{}"})
    sp._api(SITIO, "/web/x")
    sp._api(SITIO, "/web/x", metodo="POST", datos={"a": "b'c", "n": 1})
    pestana_destino = PestanaPuente()
    sp._pestanas[PERSONAL] = pestana_destino
    # El puente arma su propio JS (descarga y subida): que también compile.
    sp._descargar(SITIO, "/sites/Tech/Documentos compartidos/a'b.pdf")
    sp._subir(PERSONAL, "/personal/john_doe_contoso_com/Documents", "a'b.pdf",
              "QUJD")
    ruta = os.path.join(tempfile.gettempdir(), "asistente_sharepoint_js.js")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            for i, js in enumerate(pestana.visto + pestana_destino.visto):
                f.write(f"const j{i} = {js};\n")
        proceso = subprocess.run([node, "--check", ruta],
                                 capture_output=True, text=True)
        comprobar(proceso.returncode == 0,
                  "las expresiones JS (GET, POST, descarga y subida) compilan"
                  + ("" if proceso.returncode == 0
                     else f": {proceso.stderr[:200]}"))
    finally:
        if os.path.exists(ruta):
            os.remove(ruta)


def pruebas_clasificacion_ia():
    """La IA contesta 'nombre|carpeta' y el nombre puede traer su subcarpeta."""
    print("\n== Clasificación de la IA con rutas ==")
    from modules.api_brain import APIBrain

    nombres = ["Propuesta.docx", "2026/Acta.PPTX", "2026/Informe.doc"]
    asignadas = APIBrain._parsear_clasificacion(
        "Propuesta.docx|Clientes\n"
        "2026/Acta.PPTX|Actas\n"
        "Informe.doc|Actas\n",
        nombres)
    comprobar(asignadas == {"Propuesta.docx": "Clientes",
                            "2026/Acta.PPTX": "Actas",
                            "2026/Informe.doc": "Actas"},
              "acepta la ruta tal cual y el nombre suelto si es único")

    asignadas = APIBrain._parsear_clasificacion(
        "Acta.docx|Actas", ["2026/Acta.docx", "2025/Acta.docx"])
    comprobar(asignadas == {},
              "con el mismo nombre en dos carpetas no adivina cuál es")


def pruebas_accion_revisar():
    """La acción CLASIFICAR_ARCHIVOS cuenta lo que revisó y lo que ignoró."""
    print("\n== Acción CLASIFICAR_ARCHIVOS ==")

    sp = SharepointFalso(
        {"archivos": [{"nombre": "Propuesta.docx", "rel": "Propuesta.docx",
                       "ruta_rel": "/sites/Tech/Colombia/Propuesta.docx",
                       "tamano": 10},
                      {"nombre": "Acta.PPTX", "rel": "2026/Acta.PPTX",
                       "ruta_rel": "/sites/Tech/Colombia/2026/Acta.PPTX",
                       "tamano": 20}],
         "ignorados": ["Costos.xlsx", "Demo.mp4"], "carpetas": 2,
         "fallos": [], "truncado": False},
        [("Propuesta.docx", "Clientes"), ("2026/Acta.PPTX", "Actas")])
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar("Revisé 2 carpeta(s)" in texto and "2 documento(s)" in texto,
              "dice cuántas carpetas y documentos revisó")
    comprobar("se quedan donde están: 2" in texto and "Costos.xlsx" in texto,
              "nombra los que ignora (Excel, vídeo)")
    comprobar(sp.pedido == (["Propuesta.docx", "2026/Acta.PPTX"], "por tipo"),
              "clasifica con la ruta de cada documento")
    comprobar(sp.movido[2] == [("Propuesta.docx", "Clientes"),
                               ("2026/Acta.PPTX", "Actas")],
              "mueve según el plan de la IA")
    comprobar(sp.pedido_listado == (COLOMBIA, ""),
              "sin cuarto campo no filtra nada")

    # Con el filtro al final (';;acta') se clasifica solo lo que coincida: es lo
    # que permite probar con un archivo sin tocar el resto de la carpeta.
    sp = SharepointFalso(
        {"archivos": [{"nombre": "Acta.PPTX", "rel": "2026/Acta.PPTX",
                       "ruta_rel": "/sites/Tech/Colombia/2026/Acta.PPTX",
                       "tamano": 20}],
         "ignorados": [], "excluidos": ["Propuesta.docx"], "carpetas": 2,
         "fallos": [], "truncado": False},
        [("2026/Acta.PPTX", "Actas")])
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por año;;acta")
    comprobar(sp.pedido_listado == (COLOMBIA, "acta"),
              "pasa el filtro del usuario al listado")
    comprobar("con tu filtro dejo fuera 1 documento(s): Propuesta.docx" in texto,
              "avisa de los documentos que el filtro dejó fuera")
    comprobar(sp.pedido == (["2026/Acta.PPTX"], "por año"),
              "la IA clasifica solo el documento filtrado")
    comprobar(sp.movido[2] == [("2026/Acta.PPTX", "Actas")],
              "mueve solo el documento filtrado")

    sp = SharepointFalso({"archivos": [], "ignorados": [],
                          "excluidos": ["Propuesta.docx"], "carpetas": 3,
                          "fallos": [], "truncado": False})
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo;;acta")
    comprobar("coincidan con tu filtro" in texto and "Propuesta.docx" in texto,
              "si el filtro no encuentra nada lo dice (y no habla de vacío)")
    comprobar(sp.movido is None, "sin coincidencias no llama al mover")

    sp = SharepointFalso({"archivos": [], "ignorados": ["Costos.xlsx"],
                          "carpetas": 3, "fallos": [], "truncado": False})
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar("No hay documentos de Word o PowerPoint" in texto
              and "3 carpeta(s)" in texto and "Costos.xlsx" in texto,
              "con solo Excel o vídeo explica qué hay, no 'no hay archivos'")

    sp = SharepointFalso({"archivos": [], "ignorados": [], "excluidos": [],
                          "carpetas": 1, "fallos": [], "truncado": False})
    texto = con_asistente(sp)._clasificar_archivos(
        COLOMBIA + ";;" + COLOMBIA + "/Archivo;;por tipo")
    comprobar(texto.startswith(f"No hay archivos en {COLOMBIA}"),
              "vacía de verdad: avisa de la carpeta y sus subcarpetas")


def pruebas_accion_listar():
    """LISTAR_SHAREPOINT enseña qué hay dentro (numerado) y no mueve nada.

    Es la acción que faltaba: al pedir listar una carpeta de SharePoint, el
    modelo acababa pasando la URL a LISTAR_CARPETA (rutas del PC) y la respuesta
    era "No pude abrir la carpeta: https://...".
    """
    print("\n== Acción LISTAR_SHAREPOINT ==")

    listado = {"archivos": [{"nombre": "Propuesta.docx", "rel": "Propuesta.docx",
                             "ruta_rel": "/sites/Tech/Colombia/Propuesta.docx",
                             "tamano": 10},
                            {"nombre": "Acta.PPTX", "rel": "2026/Acta.PPTX",
                             "ruta_rel": "/sites/Tech/Colombia/2026/Acta.PPTX",
                             "tamano": 20}],
               "ignorados": ["Costos.xlsx"], "excluidos": [], "carpetas": 2,
               "fallos": [], "truncado": False}
    sp = SharepointFalso(listado)
    texto = con_asistente(sp)._listar_sharepoint(COLOMBIA)
    comprobar("1. Propuesta.docx" in texto and "2. 2026/Acta.PPTX" in texto,
              "enumera los documentos con su subcarpeta")
    comprobar("Revisé 2 carpeta(s)" in texto and "Costos.xlsx" in texto,
              "dice cuántas carpetas miró y qué ignora")
    comprobar("Dime cuál quieres clasificar" in texto,
              "dice cómo seguir (elegir uno) en vez de dejarlo en el aire")
    comprobar("clasifícalos todos" in texto,
              "y ofrece clasificarlos todos de golpe (sin elegir uno por uno)")
    comprobar(sp.pedido_listado == (COLOMBIA, "") and sp.movido is None
              and sp.pedido is None,
              "sin filtro lista todo y no clasifica ni mueve nada")

    con_asistente(sp)._listar_sharepoint(COLOMBIA + ";;acta, 2026")
    comprobar(sp.pedido_listado == (COLOMBIA, "acta, 2026"),
              "acepta el filtro tras ';;' (para listar solo algunos)")

    sp = SharepointFalso({"archivos": [], "ignorados": [], "excluidos": [],
                          "carpetas": 2, "fallos": [], "truncado": False})
    texto = con_asistente(sp)._listar_sharepoint(COLOMBIA + ";;acta")
    comprobar(texto.startswith(f"No hay archivos en {COLOMBIA}"),
              "carpeta vacía: lo dice en vez de inventarse archivos")

    sp = SharepointFalso(error=ErrorSharePoint("SharePoint respondió 403"))
    texto = con_asistente(sp)._listar_sharepoint(COLOMBIA)
    comprobar("No pude acceder a la carpeta de SharePoint" in texto
              and "403" in texto,
              "si SharePoint no contesta, avisa del motivo (sin traceback)")

    sp = SharepointFalso()
    texto = con_asistente(sp)._listar_sharepoint("")
    comprobar("Necesito la URL" in texto and sp.pedido_listado is None,
              "sin URL la pide y no toca el navegador")

    sp = SharepointFalso(
        {"archivos": [{"nombre": "Acta.PPTX", "rel": "2026/Acta.PPTX",
                       "ruta_rel": "/sites/Tech/Colombia/2026/Acta.PPTX",
                       "tamano": 20}],
         "ignorados": [], "excluidos": ["Propuesta.docx"], "carpetas": 2,
         "fallos": ["2026/Viejo: 403"], "truncado": True})
    texto = con_asistente(sp)._listar_sharepoint(COLOMBIA)
    comprobar("con tu filtro dejo fuera 1" in texto
              and "no pude mirar dentro de 2026/Viejo" in texto,
              "informa de lo que dejó fuera y de las ramas que no pudo leer")
    comprobar("me paré al llegar a 1 documentos" in texto,
              "avisa si el listado se cortó por el tope")


def pruebas_comando_acciones():
    """Las acciones nuevas se ejecutan tal cual las escribe el modelo.

    `ejecutar_comando` corta por el primer '|' y conserva el resto tal cual: el
    ';;' del filtro tiene que llegar entero al listado (si se perdiera, el
    filtro se ignoraría en silencio).
    """
    print("\n== Comando [ACCION: ...] del listado y del filtro ==")
    listado = {"archivos": [{"nombre": "Acta.docx", "rel": "Acta.docx",
                             "ruta_rel": "/sites/Tech/Colombia/Acta.docx",
                             "tamano": 1}],
               "ignorados": [], "excluidos": [], "carpetas": 1,
               "fallos": [], "truncado": False}
    asistente = con_asistente(SharepointFalso(listado))
    texto = asistente.ejecutar_comando("LISTAR_SHAREPOINT|" + COLOMBIA + ";;acta")
    comprobar(asistente.sharepoint.pedido_listado == (COLOMBIA, "acta"),
              "LISTAR_SHAREPOINT|url;;filtro llega entero al listado")
    comprobar(str(texto).startswith("Revisé 1 carpeta(s)"),
              "y la respuesta es el listado (sin pasar por la IA)")

    asistente = con_asistente(SharepointFalso(listado, [("Acta.docx", "Actas")]))
    asistente.ejecutar_comando(
        "CLASIFICAR_ARCHIVOS|" + COLOMBIA + ";;" + COLOMBIA + "/Archivo"
        ";;por año;;acta")
    comprobar(asistente.sharepoint.pedido_listado == (COLOMBIA, "acta")
              and asistente.sharepoint.movido[2] == [("Acta.docx", "Actas")],
              "CLASIFICAR_ARCHIVOS|origen;;destino;;regla;;filtro también")

    # Y antes de ejecutar se cuenta qué se va a hacer: es el paso que la ventana
    # enseña mientras la acción tarda (una biblioteca grande no se ve muda).
    vistos = []
    asistente = con_asistente(SharepointFalso(listado))
    asistente.progreso.conectar(lambda texto, tipo: vistos.append((tipo, texto)))
    asistente.ejecutar_comando("LISTAR_SHAREPOINT|" + COLOMBIA)
    comprobar(("paso", asistente.PROGRESO_ACCIONES["LISTAR_SHAREPOINT"]) in vistos,
              "la acción larga se anuncia antes de empezar")


def pruebas_acciones_documentadas():
    """Toda acción que el prompt anuncia existe de verdad en el ejecutor.

    Evita el fallo de fondo del listado de SharePoint: el modelo no puede usar
    una acción que el prompt promete y el despachador no conoce (ni al revés:
    quedó sin anunciar, así que nunca la elegiría).
    """
    print("\n== Acciones del prompt vs. ejecutor ==")
    # 'TIPO' es la plantilla del ejemplo ('[ACCION: TIPO|PARAMETRO]'), no una
    # acción de verdad.
    plantillas = {"TIPO"}
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def leer(*partes):
        with open(os.path.join(raiz, *partes), encoding="utf-8") as f:
            return f.read()

    prompt = leer("modules", "api_brain.py")
    sistema = leer("modules", "system_actions.py")
    ejecutor = sistema + leer("app_gui.py")

    anunciadas = set(re.findall(r"ACCION: ([A-Z_]+)", prompt)) - plantillas
    manejadas = set(re.findall(r'accion == "([A-Z_]+)"', ejecutor))
    faltan = sorted(a for a in anunciadas if a not in manejadas)
    comprobar(not faltan, "cada acción del prompt está en el ejecutor"
              + ("" if not faltan else f": faltan {faltan}"))
    comprobar("LISTAR_SHAREPOINT" in anunciadas
              and "LISTAR_SHAREPOINT" in manejadas,
              "listar una carpeta de SharePoint está anunciado y ejecutado")
    comprobar("NUNCA pases una URL" in prompt
              and "LISTAR_SHAREPOINT|url" in prompt,
              "el prompt avisa de no mandar URLs a las acciones de rutas locales")
    comprobar("CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;por tipo;;acta"
              in prompt,
              "el prompt explica cómo clasificar solo algunos (el filtro ';;')")
    comprobar("NO la uses como paso previo a clasificar" in prompt
              and "Emítela en el MISMO mensaje" in prompt,
              "el prompt manda clasificar sin listar antes ni preguntar cuál")

    # Las acciones que tardan tienen su "qué se está haciendo" (lo pinta la
    # ventana); una que falte se vería como un "escribiendo..." mudo, y una de
    # más sería un rótulo que nunca se enseña.
    con_progreso = set(re.findall(r'^\s+"([A-Z_]+)": ".*",?$', sistema, re.M))
    sobran = sorted(a for a in con_progreso if a not in manejadas)
    comprobar(not sobran, "cada acción con progreso existe en el ejecutor"
              + ("" if not sobran else f": sobran {sobran}"))
    comprobar({"LISTAR_SHAREPOINT", "CLASIFICAR_ARCHIVOS", "EJECUTAR_TERMINAL"}
              <= con_progreso,
              "las acciones más lentas (SharePoint, terminal) cuentan qué hacen")


def pruebas_progreso():
    """Lo que se va contando mientras trabaja: lo que la ventana enseña en vivo.

    Sin esto, una biblioteca de SharePoint tardando un minuto era indistinguible de
    un atasco: la ventana solo sabía decir "Jarvis está escribiendo".
    """
    print("\n== Progreso: qué está haciendo ahora ==")
    origen = "https://contoso.sharepoint.com/sites/Tech/Origen"
    destino = "https://contoso.sharepoint.com/sites/Tech/Destino"

    # El canal es mudo sin receptor (los módulos usados sueltos no llenan la
    # consola) y limpia el texto: los nombres salen de SharePoint o del disco y
    # pueden traer saltos de línea que rompen el rótulo de la ventana.
    limpio = []
    canal = Progreso()
    canal.paso("sin receptor no pasa nada")
    canal.conectar(lambda texto, tipo: limpio.append((tipo, texto)))
    canal.aviso("  Acta  \n  de prueba  ")
    canal.paso("")
    comprobar(limpio == [("aviso", "Acta de prueba")],
              "limpia el texto, descarta los pasos vacíos y calla sin receptor")

    with contextlib.redirect_stdout(io.StringIO()) as salida:
        Progreso(receptor=lambda texto, tipo: 1 / 0).paso("receptor roto")
    comprobar("no pude informar" in salida.getvalue(),
              "si el receptor falla, se avisa por consola y el trabajo sigue")

    # Recorrer carpetas: se dice en qué carpeta entra y cuántos documentos lleva.
    vistos = []
    sp = con_arbol()
    sp.progreso.conectar(lambda texto, tipo: vistos.append((tipo, texto)))
    listado = sp.listar_documentos(COLOMBIA)
    pasos = [texto for tipo, texto in vistos if tipo == "paso"]
    comprobar(any(t.startswith("Leyendo la carpeta pedida") for t in pasos),
              "dice que está leyendo la carpeta pedida")
    comprobar(any(t.startswith("Leyendo 2026/Viejo") for t in pasos),
              "y nombra cada subcarpeta que abre (como la ve el usuario)")
    comprobar(any(tipo == "hecho"
                  and f"Revisadas {listado['carpetas']} carpeta(s) y "
                      f"{len(listado['archivos'])} documento(s)" in texto
                  for tipo, texto in vistos),
              "al terminar resume cuántas carpetas y documentos revisó")

    # Una rama sin permiso se avisa al momento, sin cortar el resto del trabajo.
    vistos.clear()
    sp = con_arbol(sin_permiso=("/sites/Tech/Colombia/2026",))
    sp.progreso.conectar(lambda texto, tipo: vistos.append((tipo, texto)))
    listado = sp.listar_documentos(COLOMBIA)
    comprobar(any(tipo == "aviso" and "No pude entrar en 2026" in texto
                  for tipo, texto in vistos),
              "avisa en el momento de la subcarpeta que no puede leer")
    comprobar(bool(listado["archivos"]), "y sigue listando las demás ramas")

    # Mover: cada archivo con su destino y el total al acabar.
    vistos.clear()
    sp = SharePoint()
    sp.progreso.conectar(lambda texto, tipo: vistos.append((tipo, texto)))
    sp._carpetas = lambda sitio, rel: []
    sp.crear_carpeta = lambda sitio, rel: None
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp.mover = lambda sitio, ruta, carpeta, nombre: None
    sp.clasificar_y_mover(origen, destino,
                          [("2026/Acta.docx", "Actas"), ("b.docx", "Actas")])
    pasos = [texto for tipo, texto in vistos if tipo == "paso"]
    comprobar(pasos == ["Moviendo 1 de 2: 2026/Acta.docx → Actas",
                        "Moviendo 2 de 2: b.docx → Actas"],
              "nombra cada archivo que mueve y su subcarpeta de destino")
    comprobar(any(tipo == "hecho" and "Movidos 2 de 2" in texto
                  for tipo, texto in vistos),
              "y al terminar dice cuántos movió")

    # El puente entre sitios (descargar y subir con el navegador) es lo más lento:
    # también se cuenta, y se avisa de que el original va a la papelera.
    vistos.clear()
    sp = SharePoint()
    sp.progreso.conectar(lambda texto, tipo: vistos.append((tipo, texto)))
    sp._carpetas = lambda sitio, rel: []
    sp.crear_carpeta = lambda sitio, rel: None
    sp.carpeta_existe = lambda sitio, rel: True
    sp.archivo_existe = lambda sitio, rel: False
    sp._descargar = lambda sitio, rel: ("base64", 2048)
    sp._subir = lambda sitio, carpeta, nombre, datos: None
    sp._tamano = lambda sitio, rel: 2048
    sp._reciclar = lambda sitio, rel: None
    sp.clasificar_y_mover(origen, "https://contoso.sharepoint.com/sites/Personal/Colombia",
                          [("Acta.docx", "Actas")])
    pasos = [texto for tipo, texto in vistos if tipo == "paso"]
    comprobar(any("Descargando 'Acta.docx'" in t for t in pasos),
              "cuenta la descarga por el navegador (lo más lento del puente)")
    comprobar(any("Subiendo 'Acta.docx' (2 KB)" in t for t in pasos),
              "y la subida al otro sitio")
    comprobar(any(tipo == "aviso" and "otro sitio" in texto
                  for tipo, texto in vistos),
              "y avisa de que cruza de sitio (el original va a la papelera)")


def pruebas_clasificacion_naive():
    print("\n== Clasificación de respaldo ==")
    plan = SharePoint.clasificar_naive(["a.txt", "b.pdf"], "cualquier regla")
    comprobar(plan == [("a.txt", ""), ("b.pdf", "")], "sin IA todo va a la raíz")


def main_pruebas():
    pruebas_parseo_url()
    pruebas_odata()
    pruebas_api()
    pruebas_listados()
    pruebas_existencia()
    pruebas_documentos()
    pruebas_plan_con_subcarpetas()
    pruebas_clasificar_y_mover()
    pruebas_dejar_archivos()
    pruebas_copiar_archivos()
    pruebas_carpetas_destino()
    pruebas_leer_contenido()
    pruebas_puente()
    pruebas_javascript_valido()
    pruebas_clasificacion_ia()
    pruebas_accion_revisar()
    pruebas_accion_listar()
    pruebas_comando_acciones()
    pruebas_acciones_documentadas()
    pruebas_progreso()
    pruebas_clasificacion_naive()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
