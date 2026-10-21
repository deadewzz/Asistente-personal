"""SharePoint / OneDrive por la API REST de SharePoint, sin Microsoft Graph.

Idea: en vez de registrar una app en Azure y pelearse con los permisos de Graph,
reutilizamos la **sesión que el usuario ya tiene abierta en Brave**. El propio
navegador firma las peticiones, así que no hay que descifrar cookies ni
gestionar tokens.

Cómo funciona (ver `modules/navegador_cdp.py`):
- Se abre/adjunta Brave con ``--remote-debugging-port`` y se controla por CDP
  (Chrome DevTools Protocol).
- Dentro de una pestaña del sitio se ejecuta ``fetch(url, {credentials:'include'})``
  contra los endpoints ``/_api/web/...``: listar carpetas y archivos, crear
  carpetas, mover (``MoveTo``) y copiar (``CopyTo``).
- ``MoveTo``/``CopyTo`` solo funcionan **dentro del mismo sitio**. Para cruzar de
  un sitio a otro (por ejemplo, del sitio de equipo a tu OneDrive) está el
  *puente*: se descarga el archivo por la pestaña del origen, se sube por la
  pestaña del destino y, solo si el tamaño cuadra, el original va a la papelera
  de SharePoint (recuperable). Cada petición sale de una pestaña de SU sitio, así
  que no hay CORS ni líos de cookies entre dominios.
- Al clasificar se puede **copiar** en vez de mover (``copiar=True``, ver
  `SharePoint.clasificar_y_mover`): la copia queda en su carpeta y el original se
  queda donde estaba, sin pasar por la papelera.
- Al clasificar se puede **leer el contenido** de cada documento
  (`SharePoint.leer_textos`): se baja con la pestaña de su sitio (sin pasar por
  disco) y se saca un extracto de texto, para que la IA decida por lo que pone
  dentro y no solo por el nombre del archivo.

¿Por qué NO leemos la base de cookies de Brave? Porque Brave moderno las cifra
con **App-Bound Encryption** (prefijo ``v20``), que por diseño no se puede
descifrar desde fuera del navegador. Comprobado en este equipo: había
``app_bound_encrypted_key``, las cookies eran ``v20`` y SharePoint devolvía 401.
Dejar que Brave haga la petición es la vía fiable.

No guarda contraseñas: solo reutiliza la sesión que el usuario ya abrió.
"""

import base64
import json
import urllib.parse

from modules import documentos
from modules import navegador_cdp
from modules.progreso import Progreso


class ErrorSharePoint(Exception):
    pass


class SharePoint:
    """Listar, crear carpetas y mover archivos en SharePoint/OneDrive."""

    #: Tamaño máximo (bytes) que el puente entre sitios se trae al navegador en
    #: una pieza. Por encima de esto el archivo viaja en base64 por CDP y ocupa
    #: memoria de más: mejor moverlo a mano y decirlo claro.
    LIMITE_PUENTE = 64 * 1024 * 1024

    #: Tope (bytes) para **leer el contenido** de un documento (ver `leer_textos`).
    #: Uno más grande que esto se clasifica por su nombre: bajarlo solo para sacarle
    #: un extracto de texto no compensa la espera (ni la memoria en base64).
    LIMITE_LECTURA = 16 * 1024 * 1024

    #: Descargas fallidas seguidas al leer contenido antes de dejarlo por
    #: imposible. Lo normal cuando falla es que la sesión de SharePoint se cayó, y
    #: entonces no tiene sentido repetir 70 bajadas que van a fallar igual.
    MAX_FALLOS_LECTURA = 3

    #: Documentos que se revisan al clasificar una carpeta: Word y PowerPoint.
    #: El resto (Excel, PDF, vídeo, imágenes...) se queda donde está y se avisa.
    EXTENSIONES_DOCUMENTO = (".docx", ".doc", ".pptx", ".ppt")

    #: Tope del paseo por subcarpetas: niveles hacia abajo (la carpeta de partida
    #: cuenta como uno) y documentos listados. Una biblioteca enorme se corta y se
    #: dice, en vez de dejar al usuario esperando.
    MAX_PROFUNDIDAD = 6
    MAX_ARCHIVOS = 500

    #: Carpetas técnicas de las bibliotecas (formularios, páginas .aspx): dentro
    #: no hay documentos que clasificar, así que no se recorren.
    CARPETAS_TECNICAS = ("forms", "_catalogs", "_vti_bin")

    #: Separadores admitidos en el filtro por nombre ('acta, 2026'; 'acta|2026').
    SEPARADORES_FILTRO = (",", ";", "|")

    #: Primer segmento con el que SharePoint nombra un sitio dentro de un host
    #: ('/sites/Tech', '/teams/Equipo', '/personal/ana_contoso_com').
    MARCAS_SITIO = ("personal", "sites", "teams")

    #: Lo que la IA puede contestar como "carpeta" cuando la regla pide que ese
    #: archivo **no se mueva** (ver `es_dejar`). Con esto, una sola regla puede
    #: repartir unos cuantos documentos y dejar el resto en su sitio, sin tener
    #: que enumerar antes los que sí se mueven.
    MARCAS_DEJAR = (
        "dejar", "dejarlo", "dejarla", "dejarlos", "dejarlas",
        "dejalo", "dejala", "dejalo donde esta", "dejalo donde estaba",
        "dejar como esta", "dejar como estaba", "dejar donde esta",
        "dejar donde estaba", "dejar en su sitio", "dejar en su carpeta",
        "dejarlo donde esta", "dejarlo donde estaba", "dejarla donde esta",
        "sin mover", "no mover", "no moverlo", "no moverla", "no lo muevas",
        "no la muevas", "no los muevas", "no tocar", "no lo toques",
        "que se quede", "que se queden", "se queda", "se quedan", "quedarse",
        "se queda donde esta", "se quedan donde estaban",
        "se queda en su sitio", "se quedan en su sitio",
        "mismo sitio", "misma carpeta", "sin cambio", "sin cambios",
        "mantener", "mantener donde esta", "igual", "ninguna", "ninguno",
        "no aplica", "n/a", "-", "—",
    )

    #: Lo que el clasificador contesta cuando un documento no encaja en ninguna
    #: carpeta del destino: se le hace una carpeta propia en vez de dejarlo
    #: suelto en la raíz. No confundir con `MARCAS_DEJAR`: «dejar» es que la
    #: regla pide que se quede donde está (ver `es_dejar`).
    FALLBACK_CARPETA = "Otros"

    #: Cuando el clasificador contesta una de estas, no está diciendo «déjalo
    #: donde está» sino «aquí no me encaja»: el archivo acaba en
    #: `FALLBACK_CARPETA`, nunca suelto en la raíz del destino. Ojo: ``-``,
    #: ``ninguna`` y compañía NO están aquí a propósito, porque esas ya significan
    #: «déjalo quieto» (ver `MARCAS_DEJAR`): el plan las resuelve antes.
    MARCAS_SIN_CARPETA = ("", "(raiz)", "raiz", "/", "sin carpeta",
                          "sin clasificar", "por clasificar", "clasificar",
                          "desconocida", "desconocido", "nada")

    #: Con esto en la orden se COPIAN los documentos y los originales se quedan
    #: donde están, en vez de moverlos (que es lo normal). Ver `quiere_copiar`.
    MARCAS_COPIAR = (
        "copia", "copiar", "copiando", "copiado", "copiada", "copiados",
        "copiadas", "copialo", "copiala", "copiarlo", "copiarla", "copiarse",
        "duplica", "duplicar",
        "sin mover el original", "sin tocar el original", "sin borrar el original",
        "no muevas el original", "no borres el original", "no toques el original",
        "deja el original", "dejando el original", "dejar el original",
        "conserva el original", "conservar el original", "conservando el original",
        "el original se queda", "el original sigue", "los originales se quedan",
        "los originales siguen", "que se quede el original",
    )

    #: Con esto en la orden NO se lee el contenido de los documentos: se clasifican
    #: por su nombre, que es lo de antes. Leerlo es lo que hace buena la
    #: clasificación (un 'Documento1.docx' no dice nada), pero cuesta una bajada por
    #: archivo, así que la orden manda. Ver `quiere_sin_leer`.
    MARCAS_SIN_LEER = (
        "sin leer", "sin leerlo", "sin leerla", "sin leerlos", "sin leerlas",
        "no leer", "no leerlo", "no leerla", "no leerlos", "no leas", "no los leas",
        "sin abrir", "sin abrirlo", "sin abrirlos", "no abrir", "no los abras",
        "no abras", "sin abrir los archivos",
        "solo nombres", "solo el nombre", "solo por el nombre", "por el nombre",
        "sin el contenido", "sin contenido", "sin mirar el contenido",
        "sin descargar", "sin descargarlo", "sin descargarlos", "no descargues",
        "no los descargues", "sin bajar", "sin bajarlos", "no bajes",
    )

    def __init__(self):
        self.error = ""
        self.nota = ""             # aviso del último acceso al navegador
        self.on_clasificar = None  # (nombres, regla, carpetas, textos) -> [(nombre, sub)]
        self._pestanas = {}        # sitio -> navegador_cdp.Pestana
        # Por aquí se cuenta lo que está haciendo (lo conecta la ventana, para no
        # dejar al usuario mirando un "escribiendo..." mientras recorre carpetas).
        self.progreso = Progreso()

    # ---------------- Sesión de Brave (CDP) ----------------
    def asegurar_navegador(self, url):
        """Deja Brave controlable por CDP. Devuelve una nota de lo que hizo."""
        self.progreso.paso("Comprobando la sesión de Brave en SharePoint "
                           "(si hace falta, lo abro)")
        self.nota = navegador_cdp.asegurar(url)
        self.progreso.hecho(self.nota)
        return self.nota

    def _pestana(self, sitio):
        """Pestaña de Brave abierta en 'sitio' (se reutiliza entre llamadas)."""
        if sitio not in self._pestanas:
            self._pestanas[sitio] = navegador_cdp.Pestana(sitio).abrir()
        return self._pestanas[sitio]

    def cerrar(self):
        """Cierra las pestañas que abrimos (Brave se queda abierto)."""
        for pestana in self._pestanas.values():
            pestana.cerrar()
        self._pestanas.clear()

    # ---------------- REST de SharePoint vía Brave ----------------
    def _api(self, sitio, ruta_api, metodo="GET", datos=None):
        """Llamada a ``/_api`` ejecutada DENTRO de una pestaña de Brave.

        Brave añade las cookies de sesión y, en las escrituras, el token
        ``X-RequestDigest``. Devuelve el JSON ya parseado.
        """
        url = sitio.rstrip("/") + "/_api" + ruta_api
        aceptar = "'Accept':'application/json;odata=verbose'"
        if metodo == "GET":
            js = ("(async () => { try {"
                  " const r = await fetch(" + json.dumps(url) + ","
                  " {credentials:'include', cache:'no-store',"
                  " headers:{" + aceptar + "}});"
                  " return {estado: r.status, cuerpo: await r.text()};"
                  " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        else:
            contexto = sitio.rstrip("/") + "/_api/contextinfo"
            cuerpo = json.dumps(datos or {})
            js = ("(async () => { try {"
                  " const c = await fetch(" + json.dumps(contexto) + ","
                  " {method:'POST', credentials:'include',"
                  " headers:{" + aceptar + "}});"
                  " if (!c.ok) return {estado: c.status, cuerpo: await c.text(),"
                  " paso: 'token'};"
                  " const token = (await c.json()).d"
                  ".GetContextWebInformation.FormDigestValue;"
                  " const r = await fetch(" + json.dumps(url) + ","
                  " {method:" + json.dumps(metodo) + ", credentials:'include',"
                  " headers:{" + aceptar + ", 'X-RequestDigest': token},"
                  " body:" + json.dumps(cuerpo) + "});"
                  " return {estado: r.status, cuerpo: await r.text()};"
                  " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        return self._revisar(self._pestana(sitio).evaluar(js))

    def _revisar(self, resultado):
        """Valida la respuesta cruda de una pestaña y devuelve el JSON.

        Lo usan todas las llamadas que hablan con SharePoint (``_api``, y las
        descargas y subidas del puente entre sitios), así los avisos de sesión,
        permisos y token son idénticos en todas partes. Lanza ErrorSharePoint si
        SharePoint no respondió 200 (y le deja el código en ``.estado``).
        """
        if not isinstance(resultado, dict):
            raise ErrorSharePoint(
                f"Respuesta inesperada del navegador: {resultado!r}")
        estado = resultado.get("estado")
        cuerpo = resultado.get("cuerpo") or ""

        def fallar(mensaje, codigo=None):
            error = ErrorSharePoint(mensaje)
            error.estado = estado if codigo is None else codigo
            raise error

        if resultado.get("paso") == "token":
            fallar("No pude obtener el token de escritura de SharePoint "
                   f"(respondió {estado}). Detalle: {str(cuerpo)[:200]}")
        if estado == -1:
            fallar("El navegador no pudo completar la petición (¿sin conexión o "
                   f"Brave cerrado?). Detalle: {str(cuerpo)[:200]}")
        if estado == 401:
            fallar("SharePoint respondió 401: la sesión de Brave no vale. Entra en "
                   "la carpeta desde la ventana de Brave que abrí, inicia sesión y "
                   "vuelve a pedírmelo.")
        if estado == 403:
            fallar("SharePoint respondió 403 (Acceso denegado): la sesión sí vale, "
                   "pero tu cuenta no tiene permiso en esa carpeta o sitio. "
                   f"Detalle: {str(cuerpo)[:200]}")
        if estado == 404:
            fallar(f"SharePoint respondió 404 (no existe). Detalle: "
                   f"{str(cuerpo)[:200]}")
        if estado != 200:
            fallar(f"SharePoint respondió {estado}: {str(cuerpo)[:200]}")
        try:
            return json.loads(cuerpo or "{}")
        except ValueError:
            pass
        if "<html" in cuerpo[:2000].lower():
            fallar("SharePoint devolvió su página de inicio de sesión en vez de "
                   "datos. Entra en la carpeta desde la ventana de Brave que abrí, "
                   "inicia sesión y vuelve a pedírmelo.")
        return {}

    @staticmethod
    def _odata(ruta):
        """Prepara una ruta server-relative para un literal OData '...'.

        Codifica espacios y demás caracteres raros, deja las barras y las
        comillas simples (que OData escapa duplicándolas: O'Brien -> O''Brien).
        """
        return urllib.parse.quote(ruta, safe="/'").replace("'", "''")

    # ---------------- Parseo de URLs ----------------
    @staticmethod
    def _sin_paginas(segmentos):
        """Quita el final de la vista web: 'Forms/AllItems.aspx', 'OneUp.aspx'."""
        while segmentos and segmentos[-1].lower().endswith(".aspx"):
            segmentos = segmentos[:-1]
        if segmentos and segmentos[-1].lower() == "forms":
            segmentos = segmentos[:-1]
        return segmentos

    @staticmethod
    def _carpeta_de_parametro(ruta):
        """Carpeta a la que apunta un parámetro 'id='/'parent=' de la URL.

        Si apunta a un archivo (tiene extensión) devuelve su carpeta.
        """
        limpia = "/" + ruta.strip("/")
        ultimo = limpia.rsplit("/", 1)[-1]
        if "." in ultimo.strip("."):
            limpia = limpia.rsplit("/", 1)[0]
        return limpia or "/"

    @staticmethod
    def _web_de_carpeta(carpeta_rel):
        """Sitio al que pertenece una ruta server-relative, o '' si no se ve.

        ``/personal/ana_contoso_com/Documents/X`` -> ``/personal/ana_contoso_com``
        y ``/sites/Tech/Docs/X`` -> ``/sites/Tech``. Lo necesitan los enlaces que
        comparte Teams (``.../my?id=%2Fpersonal%2Fana...``), donde la carpeta
        viene en el parámetro pero el camino de la URL no dice el sitio: sin
        esto, la carpeta se pediría a la raíz del host y saldría vacía.
        """
        segmentos = [s for s in str(carpeta_rel or "").split("/") if s]
        if segmentos and segmentos[0].lower() in SharePoint.MARCAS_SITIO:
            return "/" + "/".join(segmentos[:2])
        return ""

    @staticmethod
    def parsear_url(url):
        """Convierte una URL de SharePoint/OneDrive en (sitio, carpeta, dominio).

        Acepta tanto la carpeta en crudo como la URL de la vista que copia
        SharePoint (``.../Oportunidad/Forms/AllItems.aspx?viewid=...``): se
        queda con la carpeta de la que cuelga la vista. Si la URL trae
        ``RootFolder=`` o ``id=`` (SharePoint los añade al navegar por dentro
        de una biblioteca) mandan esos valores, que son los que de verdad
        apuntan a la carpeta. Los enlaces que comparte Teams entran por ahí
        (``.../my?id=%2Fpersonal%2Fana%2FDocuments%2FX``): como su camino no
        dice el sitio, también se saca de esa ruta (si no, se pediría todo a la
        raíz del host y una carpeta con subcarpetas parecería vacía).

        Devuelve un dict con:
        - 'sitio': URL raíz del sitio (p. ej. https://empresa.sharepoint.com/sites/Tech)
        - 'carpeta_rel': ruta SERVER-relative de la carpeta (la que espera la API `_api`)
        - 'dominio': host del sitio
        - 'web_rel': ruta del sitio dentro del host (p. ej. /sites/Tech)
        """
        partes = urllib.parse.urlparse((url or "").strip())
        dominio = partes.netloc or ""
        consulta = urllib.parse.parse_qs(partes.query or "")

        camino = urllib.parse.unquote(partes.path or "").strip("/")
        segmentos = [s for s in camino.split("/") if s]
        # Los enlaces modernos llevan un atajo delante ('/:w:/r/sites/Tech/...')
        # que no forma parte del sitio.
        if segmentos and segmentos[0].startswith(":"):
            segmentos = segmentos[1:]
            if segmentos and segmentos[0].lower() == "r":
                segmentos = segmentos[1:]
        web_rel = "/"
        resto = segmentos
        if segmentos and segmentos[0].lower() in SharePoint.MARCAS_SITIO:
            web_rel = "/" + "/".join(segmentos[:2])
            resto = segmentos[2:]
        elif segmentos and segmentos[0].lower() == "my":
            # '.../my' es la portada de OneDrive, no una carpeta: quien pega esa
            # dirección se refiere a su OneDrive entero (y luego se resuelve).
            resto = segmentos[1:]

        dentro = ""
        for clave in ("RootFolder", "id", "parent"):
            valores = consulta.get(clave)
            if valores and valores[0].strip():
                dentro = urllib.parse.unquote(valores[0])
                if clave != "RootFolder":
                    dentro = SharePoint._carpeta_de_parametro(dentro)
                break
        if dentro.startswith("/"):
            carpeta_rel = "/" + dentro.strip("/")
            # Los enlaces que comparte Teams ('.../my?id=%2Fpersonal%2Fana%2F
            # Documents%2FX') traen la carpeta ahí pero NO el sitio en el camino:
            # se saca de la propia ruta, o las llamadas irían a la raíz del host
            # y una carpeta llena de subcarpetas parecería vacía.
            web_rel = SharePoint._web_de_carpeta(carpeta_rel) or web_rel
        else:
            resto = SharePoint._sin_paginas(resto)
            carpeta_rel = web_rel.rstrip("/") + ("/" + "/".join(resto)
                                                 if resto else "")
        carpeta_rel = carpeta_rel or "/"
        sitio = f"{partes.scheme}://{dominio}{web_rel}"
        return {"sitio": sitio, "carpeta_rel": carpeta_rel,
                "dominio": dominio, "web_rel": web_rel}

    # ---------------- Existencia (a prueba de mentiras de la API) ----------------
    def _existe(self, sitio, ruta_api):
        """True si la llamada responde 200, False si responde 404.

        Cualquier otro fallo (permiso, red...) se propaga: mejor saber que no
        se pudo comprobar que suponer que no existe.
        """
        try:
            self._api(sitio, ruta_api)
        except ErrorSharePoint as e:
            if getattr(e, "estado", None) == 404:
                return False
            raise
        return True

    def carpeta_existe(self, sitio, carpeta_rel):
        """¿Existe la carpeta? (por su ruta server-relative).

        Hace falta comprobarlo porque ``/Files`` de una ruta que no existe
        responde 200 con una lista vacía: sin esto, una carpeta mal escrita
        parecería vacía.
        """
        ruta = ("/web/GetFolderByServerRelativeUrl('"
                + self._odata(carpeta_rel) + "')?$select=Name")
        return self._existe(sitio, ruta)

    def archivo_existe(self, sitio, ruta_rel):
        """¿Existe el archivo? (por su ruta server-relative).

        La comparación la hace SharePoint, así que no distingue mayúsculas
        (``informe.pdf`` y ``INFORME.PDF`` son el mismo archivo).
        """
        ruta = ("/web/GetFileByServerRelativeUrl('"
                + self._odata(ruta_rel) + "')?$select=Name")
        return self._existe(sitio, ruta)

    def _paginado(self, sitio, datos):
        """Todas las entradas de una colección, siguiendo los ``__next``.

        SharePoint parte las colecciones grandes (muchos archivos o carpetas en
        la misma carpeta) y avisa en ``d.__next``: sin seguirlo, un listado
        grande se cortaría a la mitad sin decir nada.
        """
        resultados = list(datos.get("d", {}).get("results", []))
        siguiente = datos.get("d", {}).get("__next")
        while siguiente and isinstance(siguiente, str):
            base = sitio.rstrip("/") + "/_api"
            if siguiente.startswith(base):
                siguiente = siguiente[len(base):]
            elif siguiente.startswith("http"):
                break  # no es de este sitio: mejor no adivinar la dirección
            datos = self._api(sitio, siguiente)
            resultados += datos.get("d", {}).get("results", [])
            siguiente = datos.get("d", {}).get("__next")
        return resultados

    # ---------------- Lectura ----------------
    def listar_archivos(self, url):
        """Archivos de una carpeta. Lista de {nombre, ruta_rel, tamano}."""
        info = self.parsear_url(url)
        return self._archivos(info["sitio"], info["carpeta_rel"])

    def _archivos(self, sitio, carpeta_rel, comprobar=True):
        """Archivos de una carpeta, por su ruta server-relative.

        Con ``comprobar=False`` no pregunta antes si la carpeta existe: lo usan
        los recorridos de `listar_documentos`, que vienen de listarla.
        """
        if comprobar and not self.carpeta_existe(sitio, carpeta_rel):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {carpeta_rel}. Comprueba la "
                "dirección (puedes pegar la de la vista 'Forms/AllItems.aspx').")
        carpeta = self._odata(carpeta_rel)
        datos = self._api(
            sitio,
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
            "?$select=Name,ServerRelativeUrl,Length")
        return [{"nombre": f.get("Name", ""),
                 "ruta_rel": f.get("ServerRelativeUrl", ""),
                 "tamano": f.get("Length", 0)}
                for f in self._paginado(sitio, datos)]

    def listar_carpetas(self, url):
        """Subcarpetas de una carpeta (lista de {nombre, ruta_rel})."""
        info = self.parsear_url(url)
        return self._carpetas(info["sitio"], info["carpeta_rel"])

    def _carpetas(self, sitio, carpeta_rel, comprobar=True):
        """Subcarpetas de una carpeta, por su ruta server-relative."""
        if comprobar and not self.carpeta_existe(sitio, carpeta_rel):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {carpeta_rel}.")
        carpeta = self._odata(carpeta_rel)
        datos = self._api(
            sitio,
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Folders"
            "?$select=Name,ServerRelativeUrl")
        return [{"nombre": f.get("Name", ""),
                 "ruta_rel": f.get("ServerRelativeUrl", "")}
                for f in self._paginado(sitio, datos)]

    @staticmethod
    def _relativa(base, ruta):
        """Ruta de 'ruta' vista desde 'base' (sin barra al principio)."""
        base = "/" + (base or "/").strip("/")
        ruta = "/" + (ruta or "").strip("/")
        if ruta.lower() == base.lower():
            return ""
        if base != "/" and ruta.lower().startswith(base.lower() + "/"):
            return ruta[len(base) + 1:]
        return ruta.lstrip("/")

    @staticmethod
    def _normalizar(texto):
        """Texto comparable por nombre: minúsculas y sin acentos."""
        texto = str(texto or "").lower()
        return texto.translate(str.maketrans(
            "áàäâãéèëêíìïîóòöôõúùüûñç", "aaaaaeeeeiiiiooooouuuunc"))

    @classmethod
    def _filtros(cls, solo):
        """Partes del filtro por nombre: 'acta; 2026' -> ('acta', '2026')."""
        texto = str(solo or "")
        if not texto.strip():
            return ()
        for separador in cls.SEPARADORES_FILTRO:
            texto = texto.replace(separador, "|")
        return tuple(p for p in (cls._normalizar(x).strip()
                                 for x in texto.split("|")) if p)

    @classmethod
    def _coincide(cls, rel, filtros):
        """True si el documento (o su subcarpeta) entra en el filtro pedido.

        'acta' encuentra ``2026/Acta.PPTX`` y '2026' encuentra todo lo que esté
        dentro de esa subcarpeta: sirve para elegir uno o un grupo antes de
        clasificar, sin tener que bajar a mano por el árbol.
        """
        if not filtros:
            return True
        ruta = cls._normalizar(rel)
        return any(parte in ruta for parte in filtros)

    @classmethod
    def es_dejar(cls, subcarpeta):
        """¿La 'carpeta' que devolvió la IA significa «déjalo donde está»?

        La regla puede pedir que algunos archivos no se muevan («deja un Word y
        un PowerPoint en cada carpeta y los demás no los toques»): el
        clasificador contesta ``dejar`` en esos y aquí se reconoce para saltarlos
        al mover. Así una sola regla reparte unos cuantos documentos y deja el
        resto quieto, sin tener que enumerar antes los que sí se mueven.

        Vale con los adornos que se cuelan en la respuesta (``(dejar)``,
        ``- dejar``, ``dejar.``, ``"DEJAR"``, ``no lo muevas``), pero un nombre
        de carpeta real como ``Dejar constancia`` no se confunde: se compara la
        frase completa.
        """
        texto = cls._normalizar(subcarpeta).strip()
        for adorno in ('"', "'", "`", "*", "(", ")", "[", "]", "{", "}",
                       ".", ":", "!", "?", ",", ";"):
            texto = texto.strip(adorno)
        texto = " ".join(texto.split())
        if texto in cls.MARCAS_DEJAR:
            return True
        # Sigue valiendo con guiones alrededor ('- dejar -'). Un '-' suelto ya se
        # reconoció arriba: aquí se quedaría vacío y dejaría de valer.
        compacto = texto.strip("-–— ").strip()
        return bool(compacto) and compacto in cls.MARCAS_DEJAR

    @classmethod
    def quiere_copiar(cls, texto):
        """¿La orden pide COPIAR (y dejar los originales donde están)?

        «Copia cada documento en la carpeta que le toque» copia; sin decirlo, se
        mueven, que es lo de siempre. Se mira la orden/regla entera, así que
        también vale decirlo con una frase («sin mover el original»).

        Se comparan palabras completas (``copias`` no es ``copia``): una regla
        sobre «las copias de seguridad» no cambia de modo por accidente.
        """
        return cls._tiene_marcas(texto, cls.MARCAS_COPIAR)

    @classmethod
    def quiere_sin_leer(cls, texto):
        """¿La orden pide clasificar SIN leer el contenido de los documentos?

        Se compara igual que `quiere_copiar` (palabras completas y frases): vale
        «clasifícalos sin leerlos», «solo por el nombre» o un ``;;sin leer`` al
        final. Sin decirlo, se lee el contenido, que es lo que permite colocar un
        documento que por su nombre no dice nada.
        """
        return cls._tiene_marcas(texto, cls.MARCAS_SIN_LEER)

    @classmethod
    def es_bandera(cls, campo):
        """¿Ese campo entero es una bandera y no un filtro ni una carpeta?

        El cuarto campo de la orden es el filtro por nombre (``;;acta``), pero ahí
        es donde más se cuela lo que uno recuerda: ``;;copiar``, ``;;sin leer``. Si
        el campo entero es una de esas órdenes no hay filtro que valga, y tomarlo
        por filtro dejaría el listado vacío (o peor: 'sin leer' filtraría por los
        archivos que tengan 'sin' o 'leer' en el nombre).
        """
        texto = " ".join(cls._normalizar(campo).split())
        if not texto:
            return False
        return texto in cls.MARCAS_COPIAR or texto in cls.MARCAS_SIN_LEER

    @classmethod
    def _tiene_marcas(cls, texto, marcas):
        """¿El texto trae alguna de esas palabras o frases?

        Las palabras se comparan **completas** (``copias`` no es ``copia``): una
        regla sobre «las copias de seguridad» no cambia de modo por accidente. Las
        marcas con espacios se buscan como frase.
        """
        normal = cls._normalizar(texto)
        if not normal.strip():
            return False
        palabras = set()
        for palabra in normal.split():
            limpia = "".join(c for c in palabra if c.isalnum())
            if limpia:
                palabras.add(limpia)
        for marca in marcas:
            if " " in marca:
                if marca in normal:
                    return True
            elif marca in palabras:
                return True
        return False

    @classmethod
    def normalizar_carpeta(cls, respuesta, carpetas):
        """Encaja lo que contestó la IA con una carpeta REAL del destino.

        La IA no siempre copia el nombre tal cual (``QA`` por
        ``Quality Assurance``, ``Soporte`` por ``Soporte y-o administración``) y
        crear una carpeta que ya existe no da error: sin esto se acabaría
        creando una segunda ``QA`` al lado de la que ya hay.

        Devuelve el nombre real de la carpeta, o ``''`` si ninguno se parece (el
        archivo no encaja): quien llama decide entonces entre crearla o mandarlo
        a `FALLBACK_CARPETA`, pero nunca dejarlo suelto en la raíz.
        """
        texto = cls._normalizar(respuesta).strip()
        if texto in cls.MARCAS_SIN_CARPETA:
            return ""
        reales = [(c, cls._normalizar(c).strip()) for c in (carpetas or ())]
        for carpeta, real in reales:              # el nombre tal cual
            if real == texto:
                return carpeta
        for carpeta, real in reales:              # 'soporte' -> 'Soporte y-o admin.'
            if real.startswith(texto + " ") or texto.startswith(real + " "):
                return carpeta
        for carpeta, real in reales:              # siglas: 'QA' -> 'Quality Assurance'
            siglas = "".join(p[0] for p in real.split() if p)
            if siglas and siglas == texto:
                return carpeta
        return ""

    @classmethod
    def encajar_plan(cls, plan, carpetas):
        """Repasa el plan de la IA para que nada acabe suelto en la raíz.

        Con las carpetas reales del destino a la vista:
        - lo que conteste se encaja con una carpeta que **ya existe**
          (`normalizar_carpeta`), para no crear una segunda 'QA' al lado de la
          que hay;
        - si no se parece a ninguna, se respeta el nombre que dijo (se creará, y
          se avisa, para que un nombre raro no pase desapercibido);
        - si llega **sin carpeta** (`''`, `(raíz)`, `sin clasificar`...) va a
          `FALLBACK_CARPETA`: 'dejar' (que la regla lo pida) y un despiste no son
          lo mismo, y «no lo dejes libre» se cumple siempre.

        Devuelve ``(plan, avisos)``: el plan corregido y las líneas que cuentan
        lo que hubo que arreglar (lista vacía si no hubo nada que arreglar).
        """
        corregido, nuevos, sin_sitio = [], [], []
        for nombre, subcarpeta in plan or ():
            sub = (subcarpeta or "").strip()
            if cls.es_dejar(sub):
                corregido.append((nombre, subcarpeta))
                continue
            if cls._normalizar(sub).strip() in cls.MARCAS_SIN_CARPETA:
                corregido.append((nombre, cls.FALLBACK_CARPETA))
                sin_sitio.append(nombre)
                continue
            real = cls.normalizar_carpeta(sub, carpetas)
            if real:
                corregido.append((nombre, real))
                continue
            corregido.append((nombre, sub))
            # 'Otros' es el cajón de los que no encajan (no es una carpeta
            # inventada): no se avisa de él como si fuera nueva.
            if cls._normalizar(sub).strip() != cls._normalizar(
                    cls.FALLBACK_CARPETA):
                nuevos.append(f"{nombre} → {sub}")
        avisos = []
        if nuevos:
            avisos.append("Estas carpetas no son ninguna de las que ya hay en el "
                          "destino: las creo con ese nombre (mira que no sea un "
                          "nombre repetido con otro):")
            avisos += [f"  + {n}" for n in nuevos]
        if sin_sitio:
            avisos.append(f"Sin carpeta clara: los dejo en "
                          f"'{cls.FALLBACK_CARPETA}' en vez de soltarlos en la raíz:")
            avisos += [f"  ~ {n}" for n in sin_sitio]
        return corregido, avisos

    def listar_documentos(self, url, extensiones=EXTENSIONES_DOCUMENTO,
                          maximo=MAX_ARCHIVOS, solo=None):
        """Documentos de Word/PowerPoint de una carpeta Y de sus subcarpetas.

        Recorre el árbol desde la carpeta pedida (una petición por carpeta) y
        devuelve un dict:

        - ``archivos``: los que se revisan, con ``rel`` = ruta relativa a la
          carpeta pedida (``2026/Propuesta.docx``). Guardar de qué subcarpeta
          sale importa: hay bibliotecas con el mismo nombre en ramas distintas.
        - ``ignorados``: los que no son Word ni PowerPoint (Excel, PDF, vídeo,
          imágenes...): se quedan donde están y se informa de ellos.
        - ``carpetas``: cuántas carpetas se llegaron a leer.
        - ``fallos``: subcarpetas que no se pudieron leer (sin permiso, por
          ejemplo). Se avisa y se sigue con el resto: una rama cerrada no tira
          el trabajo hecho en las demás.
        - ``truncado``: True si se llegó al tope de ``maximo`` documentos.

        Con ``solo`` (nombre o parte, o subcarpeta: ``'acta'``, ``'2026, informe'``)
        se queda únicamente con los documentos que coincidan y cuenta el resto en
        ``excluidos``: es lo que permite decir "lista o clasifica solo el
        Acta" sin recorrer la biblioteca a mano.

        ``MAX_PROFUNDIDAD`` y ``maximo`` evitan que una biblioteca enorme eternice
        el paseo: se revisa lo primero que aparece y se dice que se cortó.
        """
        info = self.parsear_url(url)
        sitio = info["sitio"]
        raiz = (info["carpeta_rel"] or "/").rstrip("/") or "/"
        if isinstance(extensiones, str):
            extensiones = (extensiones,)
        terminaciones = tuple(str(x).lower() for x in (extensiones or ()))
        filtros = self._filtros(solo)
        archivos, ignorados, excluidos, fallos = [], [], [], []
        carpetas, truncado = 0, False
        pendientes, visitadas = [(raiz, 0)], set()
        while pendientes and not truncado:
            carpeta_rel, profundidad = pendientes.pop(0)
            if carpeta_rel.lower() in visitadas:
                continue
            visitadas.add(carpeta_rel.lower())
            # Solo a la carpeta pedida le pregunto si existe: `_api` responde 200
            # con lista vacía a rutas inexistentes, y no quiero decir "no hay
            # archivos" cuando el problema es la dirección.
            # Se dice en qué carpeta está entrando: es lo único que ve el usuario
            # mientras la biblioteca tarda en contestar (y delata un atasco).
            etiqueta = self._relativa(raiz, carpeta_rel) or "la carpeta pedida"
            self.progreso.paso(f"Leyendo {etiqueta} ({carpetas + 1}ª carpeta · "
                               f"{len(archivos)} documento(s) hasta ahora)")
            try:
                lista = self._archivos(sitio, carpeta_rel,
                                       comprobar=(carpeta_rel == raiz))
            except ErrorSharePoint as e:
                if carpeta_rel == raiz:
                    raise  # la carpeta pedida: que se sepa por qué no hay nada
                fallos.append(f"{self._relativa(raiz, carpeta_rel)}: {e}")
                self.progreso.aviso(f"No pude entrar en "
                                    f"{self._relativa(raiz, carpeta_rel)}; sigo con el resto")
                continue
            carpetas += 1
            padre = self._relativa(raiz, carpeta_rel)  # '' en la carpeta pedida
            for fichero in lista:
                # La ruta relativa se arma con la carpeta que acabo de listar y
                # el nombre del archivo (no con la ruta que devuelva la API), así
                # cuadra siempre con el origen que luego usa el mover.
                rel = "/".join(x for x in (padre, fichero["nombre"]) if x)
                if terminaciones and not rel.lower().endswith(terminaciones):
                    ignorados.append(rel)
                    continue
                if not self._coincide(rel, filtros):
                    excluidos.append(rel)
                    continue
                archivos.append({"nombre": fichero["nombre"], "rel": rel,
                                 "ruta_rel": fichero["ruta_rel"],
                                 "tamano": fichero["tamano"]})
                if len(archivos) >= maximo:
                    truncado = True
                    break
            if truncado or profundidad + 1 >= self.MAX_PROFUNDIDAD:
                continue
            try:
                hijas = self._carpetas(sitio, carpeta_rel, comprobar=False)
            except ErrorSharePoint as e:
                fallos.append(f"{self._relativa(raiz, carpeta_rel)}: {e}")
                self.progreso.aviso(f"No pude ver las subcarpetas de "
                                    f"{self._relativa(raiz, carpeta_rel)}")
                continue
            for hija in hijas:
                if (hija["nombre"] or "").lower() in self.CARPETAS_TECNICAS:
                    continue
                pendientes.append((hija["ruta_rel"], profundidad + 1))
        detalle = f"Revisadas {carpetas} carpeta(s) y {len(archivos)} documento(s)"
        if excluidos:
            detalle += f" (el filtro dejó fuera {len(excluidos)})"
        if truncado:
            detalle += " (me paré al llegar al tope)"
        self.progreso.hecho(detalle)
        return {"archivos": archivos, "ignorados": ignorados,
                "excluidos": excluidos, "carpetas": carpetas,
                "fallos": fallos, "truncado": truncado}


    # ---------------- Escritura ----------------
    def crear_carpeta(self, sitio, carpeta_rel):
        """Crea una carpeta en SharePoint (si ya existe, se ignora el error)."""
        datos = {"__metadata": {"type": "SP.Folder"},
                 "ServerRelativeUrl": carpeta_rel}
        try:
            self._api(sitio, "/web/folders", metodo="POST", datos=datos)
        except ErrorSharePoint:
            pass  # ya existía: el mover funcionará igual

    def mover(self, sitio, ruta_rel_origen, carpeta_rel_destino, nombre):
        """Mueve un archivo a otra carpeta del MISMO sitio (``MoveTo``).

        ``flags=1`` sobrescribe si ya hay un archivo con ese nombre en destino
        (por eso quien llama comprueba antes que no exista). Para pasar de un
        sitio a otro usa `mover_entre_sitios`: SharePoint no deja cruzar sitios.
        """
        destino = carpeta_rel_destino.rstrip("/") + "/" + nombre
        nueva_url = self._odata(destino)
        origen = self._odata(ruta_rel_origen)
        ruta_api = (f"/web/GetFileByServerRelativeUrl('{origen}')"
                    f"/MoveTo(newUrl='{nueva_url}',flags=1)")
        self._api(sitio, ruta_api, metodo="POST", datos={})

    def copiar(self, sitio, ruta_rel_origen, carpeta_rel_destino, nombre):
        """Copia un archivo a otra carpeta del MISMO sitio (``CopyTo``).

        El original **no se toca** (esa es la diferencia con `mover`), y la copia
        la hace SharePoint de una pieza: no viaja por el navegador ni por disco.

        ``bOverwrite=false``: si justo aparece algo con ese nombre en el destino
        (una carrera entre la comprobación y la copia) SharePoint responde error
        en vez de pisarlo.
        """
        destino = carpeta_rel_destino.rstrip("/") + "/" + nombre
        nueva_url = self._odata(destino)
        origen = self._odata(ruta_rel_origen)
        ruta_api = (f"/web/GetFileByServerRelativeUrl('{origen}')"
                    f"/CopyTo(strNewUrl='{nueva_url}',bOverwrite=false)")
        self._api(sitio, ruta_api, metodo="POST", datos={})

    # ---------------- Puente entre sitios ----------------
    # SharePoint solo sabe mover dentro del mismo sitio (`MoveTo`), así que para
    # cruzar de un sitio a otro se copia y luego se recicla el original, todo con
    # la sesión de Brave: la descarga la hace la pestaña del origen y la subida la
    # pestaña del destino, de modo que cada petición es del mismo origen que su
    # sitio (sin CORS y con las cookies de ESE sitio).

    def _descargar(self, sitio, ruta_rel, limite=None):
        """Trae un archivo (en base64) con la pestaña de su propio sitio.

        Devuelve ``(base64, tamano)``. Si el archivo supera ``limite`` (por
        defecto ``LIMITE_PUENTE``) devuelve ``(None, tamano)`` sin traérselo, para
        no llenar la memoria. Con un ``limite`` más bajo se usa para leer el
        contenido de un documento (ver `leer_textos`): así un archivo enorme no
        viaja en balde.
        """
        tope = int(limite or self.LIMITE_PUENTE)
        url = (sitio.rstrip("/") + "/_api/web/GetFileByServerRelativeUrl('"
               + self._odata(ruta_rel) + "')/$value")
        js = ("(async () => { try {"
              " const r = await fetch(" + json.dumps(url) + ","
              " {credentials:'include', cache:'no-store'});"
              " if (!r.ok) return {estado: r.status,"
              " cuerpo: (await r.text()).slice(0, 200)};"
              " const largo = Number(r.headers.get('Content-Length') || 0);"
              " const tipo = r.headers.get('Content-Type') || '';"
              " if (r.redirected && tipo.indexOf('html') !== -1)"
              " return {estado: 200, html: true};"
              " if (largo > " + str(tope) + ")"
              " return {estado: 200, tamano: largo, grande: true};"
              " const b = new Uint8Array(await r.arrayBuffer());"
              " let s = '';"
              " for (let i = 0; i < b.length; i += 0x8000)"
              " s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));"
              " return {estado: 200, base64: btoa(s), tamano: b.length};"
              " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        resultado = self._pestana(sitio).evaluar(js)
        self._revisar(resultado)
        if resultado.get("html"):
            raise ErrorSharePoint(
                "SharePoint devolvió una página web en vez del archivo: lo más "
                "probable es que la sesión se haya caído. Entra en la carpeta "
                "desde la ventana de Brave, inicia sesión y vuelve a pedírmelo.")
        if resultado.get("grande"):
            return None, int(resultado.get("tamano") or 0)
        return resultado.get("base64") or "", int(resultado.get("tamano") or 0)

    def _subir(self, sitio, carpeta_rel, nombre, base64_texto):
        """Sube un archivo (de una pieza) a una carpeta, con la pestaña de su sitio.

        ``overwrite=false``: si en el destino aparece algo con ese nombre (una
        carrera entre la comprobación y la subida), SharePoint responde error en
        vez de pisarlo.
        """
        carpeta = carpeta_rel.rstrip("/") or "/"
        url = (sitio.rstrip("/") + "/_api/web/GetFolderByServerRelativeUrl('"
               + self._odata(carpeta) + "')/Files/Add(url='"
               + self._odata(nombre) + "',overwrite=false)")
        contexto = sitio.rstrip("/") + "/_api/contextinfo"
        aceptar = "'Accept':'application/json;odata=verbose'"
        js = ("(async () => { try {"
              " const c = await fetch(" + json.dumps(contexto) + ","
              " {method:'POST', credentials:'include', headers:{" + aceptar + "}});"
              " if (!c.ok) return {estado: c.status, cuerpo: await c.text(),"
              " paso: 'token'};"
              " const token = (await c.json()).d"
              ".GetContextWebInformation.FormDigestValue;"
              " const bin = atob(" + json.dumps(base64_texto) + ");"
              " const bytes = new Uint8Array(bin.length);"
              " for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);"
              " const r = await fetch(" + json.dumps(url) + ","
              " {method:'POST', credentials:'include',"
              " headers:{" + aceptar + ", 'X-RequestDigest': token,"
              " 'Content-Type': 'application/octet-stream'},"
              " body: bytes});"
              " return {estado: r.status, cuerpo: (await r.text()).slice(0, 400)};"
              " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        return self._revisar(self._pestana(sitio).evaluar(js))

    def _tamano(self, sitio, ruta_rel):
        """Tamaño en bytes de un archivo (0 si SharePoint no lo dice)."""
        ruta = ("/web/GetFileByServerRelativeUrl('" + self._odata(ruta_rel)
                + "')?$select=Length")
        datos = self._api(sitio, ruta)
        return int((datos.get("d") or {}).get("Length") or 0)

    def _reciclar(self, sitio, ruta_rel):
        """Manda un archivo a la papelera de SharePoint (es reversible).

        El puente copia y luego borra: usar la papelera deja siempre una vuelta
        atrás por si el archivo subido no sirviera.
        """
        ruta = ("/web/GetFileByServerRelativeUrl('" + self._odata(ruta_rel)
                + "')/Recycle()")
        self._api(sitio, ruta, metodo="POST", datos={})

    def mover_entre_sitios(self, sitio_origen, ruta_rel_origen, sitio_destino,
                           carpeta_rel_destino, nombre, conservar_origen=False):
        """Mueve un archivo de un sitio a OTRO (copiar con el navegador y reciclar).

        Pasos: descargar con la pestaña del origen, subir con la del destino y,
        solo si el tamaño del archivo subido coincide con el del original, mandar
        el original a la papelera. Si algo falla antes de ese punto, el original
        **no se toca**.

        Con ``conservar_origen=True`` se hace lo mismo pero **sin reciclar**: la
        copia queda en el destino y el original se queda donde estaba (es lo que
        pide una clasificación «copiar»).
        """
        # Descargar y subir por el navegador es lo más lento de todo (el archivo
        # viaja en base64), así que se cuenta: si no, parece que se colgó.
        self.progreso.paso(f"Descargando '{nombre}' con el navegador")
        base64_texto, tamano = self._descargar(sitio_origen, ruta_rel_origen)
        if base64_texto is None:
            megas = tamano / (1024 * 1024)
            maximo = self.LIMITE_PUENTE // (1024 * 1024)
            raise ErrorSharePoint(
                f"'{nombre}' pesa {megas:.1f} MB y moverlo entre sitios llega "
                f"hasta {maximo} MB. Muévelo con 'Copiar a' de SharePoint (o "
                "ábrelo y guárdalo en el destino).")
        self.progreso.paso(f"Subiendo '{nombre}' ({tamano / 1024:.0f} KB) al destino")
        self._subir(sitio_destino, carpeta_rel_destino, nombre, base64_texto)
        destino_rel = (carpeta_rel_destino.rstrip("/") or "") + "/" + nombre
        subido = self._tamano(sitio_destino, destino_rel)
        if subido != tamano:
            raise ErrorSharePoint(
                f"'{nombre}' llegó al destino con otro tamaño ({subido} bytes, "
                f"esperaba {tamano}): no toco el original, que sigue donde estaba.")
        if conservar_origen:
            return
        self._reciclar(sitio_origen, ruta_rel_origen)

    @staticmethod
    def _es_personal(dominio, carpeta):
        """¿La ruta es la raíz de un OneDrive personal (sin carpeta detrás)?"""
        if "-my.sharepoint.com" not in (dominio or ""):
            return False
        partes = [p for p in (carpeta or "").split("/") if p]
        return len(partes) == 2 and partes[0].lower() == "personal"

    def _raiz_personal(self, sitio):
        """Carpeta del web de un OneDrive personal, según SharePoint ('' si no)."""
        try:
            datos = self._api(sitio, "/web?$select=ServerRelativeUrl")
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador, OSError,
                ValueError):
            return ""  # si no puedo preguntar, mejor no inventarme la carpeta
        return ((datos.get("d") or {}).get("ServerRelativeUrl") or "").rstrip("/")

    def _carpeta_destino(self, info):
        """Carpeta del destino, entendiendo la dirección suelta de un OneDrive.

        Si pegas solo la dirección de tu OneDrive (``https://empresa-my.
        sharepoint.com/`` o su raíz de sitio), esa ruta no es una carpeta con
        archivos: los archivos viven en ``Documentos``. Se resuelve para que el
        destino sea el que esperas (y te lo digo en el resumen).
        """
        carpeta = info["carpeta_rel"]
        if carpeta not in ("", "/"):
            if self._es_personal(info["dominio"], carpeta):
                return carpeta + "/Documents"
            return carpeta
        raiz = self._raiz_personal(info["sitio"])
        if raiz.startswith("/personal/"):
            return raiz + "/Documents"
        return carpeta

    # ---------------- Clasificación ----------------
    def leer_textos(self, url, archivos, maximo=documentos.MAX_TEXTO_DOCUMENTO,
                    limite=LIMITE_LECTURA):
        """El texto de dentro de cada documento, para clasificar por contenido.

        Baja cada archivo **con la pestaña de su sitio** (no pasa por disco) y le
        saca un extracto corto con `modules.documentos`. Es lo que permite colocar
        un `Documento1.docx` por lo que pone dentro, que con el nombre solo
        acababa en 'Otros'.

        Devuelve ``(textos, avisos, leidos)``:

        - ``textos``: ``{ruta_relativa: extracto}``. Lo que no se pudo leer no
          aparece, y ese archivo se clasifica por su nombre (como antes).
        - ``avisos``: las frases para el resumen, ya con su viñeta (formato
          antiguo, archivo enorme, sin texto, descarga fallida...).
        - ``leidos``: cuántos documentos sí se leyeron.

        ``archivos`` es lo que devuelve `listar_documentos` (cada uno con
        ``rel``, ``nombre``, ``ruta_rel`` y ``tamano``). Los formatos antiguos
        (``.doc``/``.ppt``) ni se descargan: no hay lector y sería una bajada para
        nada.
        """
        info = self.parsear_url(url)
        sitio = info.get("sitio") or url.rstrip("/")
        textos, avisos = {}, []
        leidos, fallos_seguidos = 0, 0
        for numero, archivo in enumerate(archivos, start=1):
            nombre = archivo.get("nombre") or ""
            rel = archivo.get("rel") or nombre
            ruta_rel = archivo.get("ruta_rel") or ""
            if not ruta_rel:
                continue
            tipo = documentos.extension(nombre)
            if tipo not in documentos.EXTENSIONES_LEGIBLES:
                # El motivo lo pone el propio lector (con los bytes vacíos se queja
                # de la extensión, que es lo que falla aquí): así el aviso dice lo
                # mismo que diría si lo hubiera intentado leer.
                _texto, motivo = documentos.texto_de_documento(b"", nombre)
                avisos.append(f"  · {rel}: lo clasifico por su nombre ({motivo})")
                continue
            tamano = int(archivo.get("tamano") or 0)
            if tamano > limite:
                avisos.append(f"  · {rel}: pesa {tamano / 1048576:.1f} MB y no lo "
                              "leo entero: lo clasifico por su nombre")
                continue
            self.progreso.paso(f"Leyendo el contenido ({numero} de {len(archivos)}): "
                               f"{nombre}")
            try:
                contenido, tamano_real = self._descargar(sitio, ruta_rel, limite=limite)
            except Exception as e:
                fallos_seguidos += 1
                avisos.append(f"  · {rel}: no pude bajar el archivo ({e})")
                if fallos_seguidos >= self.MAX_FALLOS_LECTURA:
                    avisos.append("  · Dejo de leer el contenido (varios fallos "
                                  "seguidos): el resto va por su nombre")
                    break
                continue
            fallos_seguidos = 0
            if not contenido:
                avisos.append(f"  · {rel}: pesa {tamano_real / 1048576:.1f} MB, "
                              "demasiado para leerlo por dentro: lo clasifico por "
                              "su nombre")
                continue
            texto, motivo = documentos.texto_de_documento(
                base64.b64decode(contenido), nombre, maximo)
            if texto:
                textos[rel] = texto
                leidos += 1
            else:
                avisos.append(f"  · {rel}: {motivo}")
        self.progreso.hecho(f"Leí el contenido de {leidos} de {len(archivos)} "
                            "documento(s) para clasificarlos mejor")
        return textos, avisos, leidos

    def clasificar_y_mover(self, origen_url, destino_url, plan, copiar=False):
        """Mueve (o copia) archivos según 'plan' (lista de (nombre, subcarpeta)).

        El 'nombre' puede ser solo el nombre del archivo (``Acta.docx``) o su
        ruta relativa a la carpeta de origen (``2026/Acta.docx``), que es lo que
        devuelve `listar_documentos`: así no se confunden dos archivos con el
        mismo nombre en ramas distintas. En el destino manda el nombre del
        archivo, no la carpeta de la que venía.

        Nunca pisa un archivo que ya exista en el destino: en ese caso lo deja
        donde está y lo informa. Si no puede comprobar el destino (por ejemplo
        sin permiso), tampoco mueve ese archivo. Devuelve un texto con el
        resumen.

        La 'subcarpeta' puede ser también 'dejar' (o cualquiera de las marcas de
        `MARCAS_DEJAR`, ver `es_dejar`): ese archivo se queda donde está y no se
        toca. Es lo que permite repartir unos cuantos documentos y dejar el
        resto quieto con una sola regla.

        Y si la 'subcarpeta' es la carpeta en la que el archivo **ya está** (lo
        normal al clasificar dentro de la misma biblioteca), tampoco es un
        movimiento: se informa aparte, en vez de decir "ya existía en el
        destino", que suena a problema cuando está justo donde tiene que estar.

        También vale si el destino está en **otro sitio** (p. ej. pasar del sitio
        de equipo a tu OneDrive): ahí SharePoint no deja mover, así que se copia
        con el navegador y el original se manda a la papelera (ver
        `mover_entre_sitios`).

        Con ``copiar=True`` no se mueve nada: se deja una **copia** en la
        subcarpeta y el original se queda donde estaba (mismo sitio, con `copiar`
        en una sola pieza; entre sitios, con el puente pero sin reciclar). El
        resumen lo dice como 'Copiados', para que no haya duda de que los
        originales siguen ahí.

        La 'subcarpeta' vacía sigue significando «a la raíz del destino»: quien
        clasifica con IA ya se encarga de no mandar ahí nada que no sepa dónde va
        (lo manda a `FALLBACK_CARPETA`), y la clasificación de respaldo (sin IA)
        usa la raíz a propósito y lo dice en voz alta.
        """
        info_origen = self.parsear_url(origen_url)
        info_destino = self.parsear_url(destino_url)
        sitio_origen = info_origen["sitio"]
        sitio_destino = info_destino["sitio"]
        # Mover entre sitios SharePoint no lo sabe hacer: se copia con el
        # navegador y se recicla el original (ver `mover_entre_sitios`).
        puente = sitio_origen != sitio_destino

        # El destino tiene que existir (y si no, lo crea) antes de nada.
        raiz_destino = self._carpeta_destino(info_destino).rstrip("/") or "/"
        if raiz_destino == "/":
            # Pegar la raíz del OneDrive (suelta o como '.../my') no dice en qué
            # carpeta dejar los archivos, y ahí SharePoint no cuenta cuál es tu
            # carpeta personal (su web raíz es '/': medido en un tenant real, y
            # '/personal' responde con la lista vacía). Mejor pedirlo que mover a
            # ciegas a la raíz del sitio.
            return ("No moví nada: en esa dirección no veo una carpeta de destino. "
                    "Pégame el enlace de la carpeta concreta (el que copia "
                    "SharePoint o el que comparte Teams, con su '/Documents/...' "
                    "dentro) y la uso como destino.")
        resuelta = raiz_destino != (info_destino["carpeta_rel"].rstrip("/") or "/")
        try:
            if not self.carpeta_existe(sitio_destino, raiz_destino):
                self.crear_carpeta(sitio_destino, raiz_destino)
        except ErrorSharePoint as e:
            return ("No moví nada: no pude preparar la carpeta de destino "
                    f"({raiz_destino}): {e}")
        try:
            existentes = {c["nombre"]
                          for c in self._carpetas(sitio_destino, raiz_destino)}
        except ErrorSharePoint:
            existentes = set()  # la intentaré crear y ya dirá

        movidos, conflictos, sin_comprobar, fallos = [], [], [], []
        comprobados = {}
        # El plan se reparte en tres: lo que hay que mover, lo que la regla pide
        # dejar donde está (la IA contesta 'dejar' como carpeta: ver `es_dejar`)
        # y lo que ya está en la carpeta a la que se le manda. Lo que no se mueve
        # no es trabajo pendiente, así que no cuenta en el "Moviendo 1 de N" ni
        # en el "Movidos X de N" del resumen.
        raiz_origen = info_origen["carpeta_rel"].rstrip("/")
        tareas, dejados, ya_estaba = [], [], []
        for nombre, subcarpeta in plan:
            # El plan puede traer el nombre suelto o con su subcarpeta de
            # origen delante ('2026/Acta.docx'): la ruta se usa para el origen y
            # el nombre, para el archivo de destino.
            rel = (nombre or "").strip().replace("\\", "/").strip("/")
            archivo = rel.rsplit("/", 1)[-1]
            if not archivo:
                continue
            subcarpeta = (subcarpeta or "").strip()
            if self.es_dejar(subcarpeta):
                dejados.append(rel)
                continue
            # Ya está en la carpeta a la que se le manda (la clasificación suele
            # repartir dentro de la misma biblioteca): no hay nada que mover, y
            # sin esto saldría como "ya existía en el destino", que suena a
            # problema cuando el archivo está justo donde tiene que estar.
            destino_rel = raiz_destino.rstrip("/")
            if subcarpeta:
                destino_rel += "/" + subcarpeta.strip("/")
            destino_rel = destino_rel or "/"
            if (raiz_origen + "/" + rel).lower() == (
                    destino_rel.rstrip("/") + "/" + archivo).lower():
                ya_estaba.append(rel)
                continue
            tareas.append((rel, archivo, subcarpeta))
        total = len(tareas)

        if puente:
            if copiar:
                self.progreso.aviso("El destino está en otro sitio: copio con el "
                                    "navegador y el original se queda donde está")
            else:
                self.progreso.aviso("El destino está en otro sitio: copio con el "
                                    "navegador y el original va a la papelera de "
                                    "SharePoint")
        if dejados:
            self.progreso.aviso(f"{len(dejados)} archivo(s) se quedan donde están "
                                "(la regla lo pide)")
        if ya_estaba:
            self.progreso.aviso(f"{len(ya_estaba)} archivo(s) ya estaban en su "
                                "carpeta: no los toco")
        for numero, (rel, archivo, subcarpeta) in enumerate(tareas, 1):
            destino_rel = raiz_destino.rstrip("/")
            if subcarpeta:
                destino_rel += "/" + subcarpeta.strip("/")
            destino_rel = destino_rel or "/"
            etiqueta = subcarpeta or "(raíz)"
            ruta_final = destino_rel.rstrip("/") + "/" + archivo
            # Se nombra el archivo y su carpeta: es lo que se está pasando ahora.
            verbo = "Copiando" if copiar else "Moviendo"
            self.progreso.paso(f"{verbo} {numero} de {total}: {rel} → {etiqueta}")

            # 1) Preparar el destino y mirar si el archivo ya está ahí.
            #    Si algo de esto falla, NO muevo: prefiero no mover a pisar.
            try:
                if subcarpeta and subcarpeta not in existentes:
                    self.crear_carpeta(sitio_destino, destino_rel)
                    existentes.add(subcarpeta)
                if destino_rel not in comprobados:
                    comprobados[destino_rel] = self.carpeta_existe(
                        sitio_destino, destino_rel)
                if comprobados[destino_rel]:
                    if ruta_final not in comprobados:
                        comprobados[ruta_final] = self.archivo_existe(
                            sitio_destino, ruta_final)
                    if comprobados[ruta_final]:
                        conflictos.append(f"{rel} → {etiqueta}")
                        continue
            except ErrorSharePoint as e:
                sin_comprobar.append(f"{rel} → {etiqueta}: {e}")
                continue

            # 2) Pasar el archivo: dentro del sitio con MoveTo/CopyTo; entre
            #    sitios, con el puente (sin reciclar el original si es copia).
            #    Los que ya estaban en su carpeta se descartaron arriba.
            try:
                origen_rel = raiz_origen + "/" + rel
                if puente:
                    self.mover_entre_sitios(sitio_origen, origen_rel,
                                            sitio_destino, destino_rel, archivo,
                                            conservar_origen=copiar)
                elif copiar:
                    self.copiar(sitio_origen, origen_rel, destino_rel, archivo)
                else:
                    self.mover(sitio_origen, origen_rel, destino_rel, archivo)
                comprobados[ruta_final] = True
                movidos.append(f"{rel} → {etiqueta}")
            except ErrorSharePoint as e:
                fallos.append(f"{rel}: {e}")

        # El resumen habla de copiar o de mover según lo pedido: en modo copiar
        # hay que dejar claro que los originales siguen donde estaban.
        verbo = "Copiados" if copiar else "Movidos"
        nada = "Nada que copiar" if copiar else "Nada que mover"
        if total:
            lineas = [f"{verbo} {len(movidos)} de {total} archivo(s):"]
        elif dejados and ya_estaba:
            lineas = [f"{nada}: los archivos ya estaban donde van."]
        elif dejados:
            lineas = [f"{nada}: la regla deja los archivos donde estaban."]
        elif ya_estaba:
            lineas = [f"{nada}: los archivos ya estaban en su carpeta."]
        else:
            lineas = ["No había archivos que pasar con esas instrucciones."]
        if resuelta:
            lineas.append(f"  (destino: {raiz_destino})")
        lineas += [f"  ✓ {m}" for m in movidos]
        if dejados:
            lineas.append("Se quedan donde estaban (la regla lo pide):")
            lineas += [f"  · {d}" for d in dejados]
        if ya_estaba:
            lineas.append("Ya estaban en su carpeta (no había nada que pasar):")
            lineas += [f"  · {y}" for y in ya_estaba]
        if conflictos:
            lineas.append("Ya existían en el destino (los dejo como están):")
            lineas += [f"  = {c}" for c in conflictos]
        if sin_comprobar:
            lineas.append("No los toqué: no pude comprobar el destino "
                          "(así no piso nada):")
            lineas += [f"  ? {s}" for s in sin_comprobar]
        if fallos:
            lineas.append("Fallos:")
            lineas += [f"  ✗ {f}" for f in fallos]
        if copiar and movidos:
            lineas.append("Son COPIAS: los originales siguen donde estaban "
                          "(no he borrado nada).")
        if puente and movidos:
            if copiar:
                lineas.append("Entre sitios SharePoint no deja mover: los copié con "
                              "tu sesión de Brave y los originales se quedan donde "
                              "estaban.")
            else:
                lineas.append("Entre sitios SharePoint no deja mover: los copié con "
                              "tu sesión de Brave y el original de los movidos está "
                              "en la papelera de SharePoint (recuperable).")
        if total:
            avance = f"{verbo} {len(movidos)} de {total} archivo(s)"
        else:
            avance = nada
        if dejados:
            avance += f"; {len(dejados)} se quedan donde están"
        if ya_estaba:
            avance += f"; {len(ya_estaba)} ya estaban en su carpeta"
        if conflictos:
            avance += f"; {len(conflictos)} ya estaban en el destino"
        if fallos or sin_comprobar:
            avance += f"; {len(fallos) + len(sin_comprobar)} con problemas"
        self.progreso.hecho(avance)
        return "\n".join(lineas)

    @staticmethod
    def clasificar_naive(nombres, regla):
        """Clasificación de respaldo (sin IA): todo a la raíz del destino."""
        return [(n, "") for n in nombres]

    # ---------------- Diagnóstico ----------------
    def probar(self, url):
        """Comprueba la sesión listando la carpeta. Devuelve un texto."""
        try:
            self.asegurar_navegador(url)
            archivos = self.listar_archivos(url)
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador) as e:
            return f"No pude acceder: {e}"
        if not archivos:
            return ("Conectado. La carpeta no tiene archivos en su raíz "
                    "(puede tener subcarpetas dentro).")
        return (f"Conectado. {len(archivos)} archivo(s):\n"
                + "\n".join(f"  📄 {a['nombre']}" for a in archivos[:20]))
