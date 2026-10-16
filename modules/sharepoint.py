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
  carpetas, mover archivos (``MoveTo``), copiarlos (``CopyTo``), bajarlos
  (``$value``) y subirlos (``Files/add``).
- Al listar se puede bajar a las subcarpetas (``profundidad``): en las
  bibliotecas de verdad la carpeta de arriba solo tiene carpetas (una por
  cliente) y los documentos están dentro, así que sin mirar dentro de ellas
  parecería que no hay archivos. Cada carpeta se pide con sus archivos en una
  sola llamada (``$expand=Files``).
- De esas carpetas solo se pasan los **documentos de oficina**
  (``SharePoint.EXTENSIONES_UTILES``: ppt, pptx, doc y docx). Son bibliotecas
  donde hay vídeos (y fotos, zip, PDF...) que no se clasifican y pesan
  muchísimo: lo que no esté en esa lista no se lista, no se baja y no se mueve.
- SharePoint **solo deja mover** archivos dentro del MISMO sitio. Para llevar
  archivos a otro sitio (por ejemplo, de una biblioteca de equipo a tu OneDrive)
  la única vía es bajarlos y volverlos a subir: eso hace ``copiar``, que deja el
  original donde estaba.
- Los archivos **grandes** (``TAMANO_POR_DISCO``) no se pasan "de una vez":
  SharePoint se queda a medias con unos pocos MB y por la pestaña de Brave
  tampoco caben enteros. Esos se bajan **a tu PC** por trozos (``Range``) y desde
  ahí se suben al destino con la subida por trozos de SharePoint
  (``StartUpload`` / ``ContinueUpload`` / ``FinishUpload``). Cuando el encargo era
  un movimiento, el original se borra SOLO después de comprobar que la copia del
  destino pesa lo mismo; si algo sale mal, el archivo se queda en tu PC
  (``Jarvis/temp/sharepoint``) y el mensaje dice dónde.

¿Por qué NO leemos la base de cookies de Brave? Porque Brave moderno las cifra
con **App-Bound Encryption** (prefijo ``v20``), que por diseño no se puede
descifrar desde fuera del navegador. Comprobado en este equipo: había
``app_bound_encrypted_key``, las cookies eran ``v20`` y SharePoint devolvía 401.
Dejar que Brave haga la petición es la vía fiable.

No guarda contraseñas: solo reutiliza la sesión que el usuario ya abrió.
"""

import base64
import json
import os
import re
import urllib.parse
import uuid

from modules import navegador_cdp
from modules import pistas
from modules import rutas


class ErrorSharePoint(Exception):
    pass


def _entero(valor):
    """Convierte a número lo que SharePoint manda como texto.

    La API v2 devuelve los enteros grandes (``Length``, ``ItemCount``...) entre
    comillas porque vienen de .NET: sin esto, el tamaño de un archivo llegaría
    como ``'1536'`` y cualquier cuenta (KB, comparar cuál es el más pequeño)
    reventaría con un ``TypeError``.
    """
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


class SharePoint:
    """Listar, leer, crear carpetas y mover o copiar archivos en SharePoint/OneDrive.

    Mover dentro de un sitio lo hace SharePoint (``MoveTo``). Copiar dentro del
    mismo sitio, también (``CopyTo``). Copiar a OTRO sitio (a tu OneDrive, por
    ejemplo) se hace bajando el archivo y volviéndolo a subir, porque la API no
    lo permite de otra forma. Y los archivos grandes (``TAMANO_POR_DISCO``) se
    bajan a tu PC por trozos y se suben desde ahí, porque SharePoint los deja a
    medias con ``MoveTo``/``CopyTo``. Solo se pasan los **documentos de oficina**
    (``EXTENSIONES_UTILES``: ppt, pptx, doc y docx): los vídeos y demás archivos
    que hay en esas carpetas se ignoran (no se listan, ni se bajan, ni se mueven).
    """

    def __init__(self):
        self.error = ""
        self.nota = ""             # aviso del último acceso al navegador
        self.nota_listado = ""     # aviso del último listado (búsqueda cortada...)
        # Aviso del último catálogo de carpetas del destino (se cortó en el tope).
        self.nota_catalogo = ""
        # De lo último que se listó: cuántos archivos me salté (vídeos y demás) y
        # en qué carpetas están. Es la prueba de que no se me pasó nada por alto.
        self.descartados = {"total": 0, "carpetas": []}
        # Cómo se clasifican los archivos: (nombres, regla, carpetas_del_destino)
        # -> [(nombre, subcarpeta)]. ``carpetas_del_destino`` son las que YA
        # existen en el destino (``catalogo_carpetas``), para reutilizarlas en
        # vez de inventar otras.
        self.on_clasificar = None
        self.on_aviso = None       # (texto): cuenta lo que va haciendo (chat)
        self._pestanas = {}        # sitio -> navegador_cdp.Pestana

    # ---------------- Avisos de progreso ----------------
    def _aviso(self, texto):
        """Cuenta lo que está haciendo, para que el chat no se quede mudo.

        Una biblioteca de verdad (una carpeta por cliente, cientos de archivos)
        tarda minutos en listarse y en pasarse: cada paso que importa se imprime
        en consola y, si hay quien lo escuche (``on_aviso``, que pone la ventana
        del chat), se le pasa como texto para que lo vaya diciendo.
        """
        if not texto:
            return
        print(f"  [sharepoint] {texto}", flush=True)
        # getattr: los dobles de prueba no pasan por el __init__ que lo crea.
        aviso = getattr(self, "on_aviso", None)
        if not aviso:
            return
        try:
            aviso(texto)
        except Exception as e:
            # Un fallo al avisar no puede tumbar la tarea que está en marcha.
            print(f"  [sharepoint] no pude avisar del progreso: {e}", flush=True)

    # ---------------- Sesión de Brave (CDP) ----------------
    def asegurar_navegador(self, url):
        """Deja Brave controlable por CDP. Devuelve una nota de lo que hizo."""
        self.nota = navegador_cdp.asegurar(url)
        if self.nota != navegador_cdp.NOTA_YA_ABIERTO:
            # Brave se acaba de abrir (o de reiniciar): es otra sesión, así que
            # las pestañas que tuviéramos apuntadas ya no existen.
            self._pestanas.clear()
        return self.nota

    def _pestana(self, sitio):
        """Pestaña de Brave abierta en 'sitio' (se reutiliza entre llamadas).

        Antes de reutilizarla se comprueba que Brave todavía la tenga: si el
        usuario la cerró (o Brave se reinició), su id ya no vale y conectar
        daría un 500 en el handshake. Se abre otra y se sigue.
        """
        pestana = self._pestanas.get(sitio)
        if pestana is None or not pestana.sigue_viva():
            self._pestanas[sitio] = navegador_cdp.Pestana(sitio).abrir()
        return self._pestanas[sitio]

    def cerrar(self):
        """Cierra las pestañas que abrimos (Brave se queda abierto)."""
        for pestana in self._pestanas.values():
            pestana.cerrar()
        self._pestanas.clear()

    # ---------------- REST de SharePoint vía Brave ----------------
    def _api(self, sitio, ruta_api, metodo="GET", datos=None, cabeceras=None):
        """Llamada a ``/_api`` ejecutada DENTRO de una pestaña de Brave.

        Brave añade las cookies de sesión y, en las escrituras, el token
        ``X-RequestDigest``. Devuelve el JSON ya parseado.

        ``cabeceras`` permite añadir cabeceras propias: hace falta, por ejemplo,
        para borrar (``X-HTTP-Method: DELETE`` + ``IF-MATCH: *``).
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
            extra = "".join(", " + json.dumps(nombre) + ": " + json.dumps(valor)
                            for nombre, valor in (cabeceras or {}).items())
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
                  " headers:{" + aceptar + ", 'X-RequestDigest': token"
                  + extra + "},"
                  " body:" + json.dumps(cuerpo) + "});"
                  " return {estado: r.status, cuerpo: await r.text()};"
                  " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        resultado = self._pestana(sitio).evaluar(js)
        _, cuerpo = self._respuesta(resultado)
        try:
            return json.loads(cuerpo or "{}")
        except ValueError:
            pass
        if "<html" in cuerpo[:2000].lower():
            raise ErrorSharePoint(
                "SharePoint devolvió su página de inicio de sesión en vez de "
                "datos. Entra en la carpeta desde la ventana de Brave que abrí, "
                "inicia sesión y vuelve a pedírmelo.")
        return {}

    def _respuesta(self, resultado, correctos=(200,)):
        """Valida lo que contestó la pestaña y devuelve ``(estado, cuerpo)``.

        El JavaScript de las peticiones devuelve ``{estado, cuerpo}`` (y
        ``paso:'token'`` cuando lo que falló fue el token de escritura). Aquí se
        traducen los códigos de SharePoint a mensajes entendibles, y se
        aprovecha lo mismo para las respuestas binarias.

        ``correctos`` son los códigos que valen por buenos: un trozo de archivo
        (``Range``) responde **206** y las subidas por trozos, a veces **204**.
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
        if estado not in correctos:
            fallar(f"SharePoint respondió {estado}: {str(cuerpo)[:200]}")
        return estado, cuerpo

    # ---------------- Qué archivos sí se pasan ----------------
    @staticmethod
    def extension_de(nombre):
        """La extensión de un archivo en minúsculas ('' si no tiene ninguna).

        Se saca con ``splitext`` (lo de después del ÚLTIMO punto), no con
        ``endswith``: así 'Informe 2024.12.DOCX' da '.docx' sin líos de
        mayúsculas ni de puntos en el nombre.
        """
        return os.path.splitext((nombre or "").strip())[1].lower()

    def es_util(self, nombre):
        """¿Es uno de los documentos que sí paso? (``EXTENSIONES_UTILES``).

        Con la lista vacía se pasa todo: es la forma de quitar el filtro.
        """
        if not self.EXTENSIONES_UTILES:
            return True
        permitidas = {e.lower() for e in self.EXTENSIONES_UTILES}
        return self.extension_de(nombre) in permitidas

    def extensiones_texto(self):
        """Las extensiones que sí paso, escritas para un mensaje.

        Devuelve 'ppt, pptx, doc y docx' (sin el punto y con 'y' al final), que
        es como se dice en el chat.
        """
        limpias = [e.lstrip(".") for e in self.EXTENSIONES_UTILES]
        if not limpias:
            return "cualquier archivo"
        if len(limpias) == 1:
            return limpias[0]
        return ", ".join(limpias[:-1]) + " y " + limpias[-1]

    def _exigir_util(self, nombre, ruta=None):
        """Protesta si el archivo no es de los que paso (``EXTENSIONES_UTILES``).

        El listado ya deja fuera lo que no toca, pero esto es la red de
        seguridad: si un vídeo llega hasta aquí (pedido por su nombre, o un plan
        viejo que lo traía), se para ANTES de bajarlo. ``ruta`` es la ruta del
        archivo en SharePoint y sirve para decir en qué carpeta está.
        """
        if self.es_util(nombre):
            return
        carpeta = ""
        if "/" in (ruta or ""):
            carpeta = ruta.strip("/").rsplit("/", 1)[0]
        donde = f" (está en {carpeta})" if carpeta else ""
        raise ErrorSharePoint(
            f"No paso '{nombre}': solo {self.extensiones_texto()}{donde}. "
            "No lo bajo ni lo muevo.")

    # ---------------- REST binario (bajar y subir archivos) ----------------
    # Un archivo más grande que esto no cabe en el mensaje que le mandamos a la
    # pestaña: el contenido viaja dentro del JavaScript, en base64.
    TAMANO_MAXIMO = 25 * 1024 * 1024

    # A partir de aquí (10 MB) no se pasa "de una vez": SharePoint deja a medias
    # los movimientos de unos pocos MB (en este tenant, pasados ~4 MB) y el
    # archivo tampoco cabe entero en el mensaje de la pestaña. Los que pasan de
    # este tamaño se bajan a tu PC por trozos y desde ahí se suben al destino
    # (ver ``_pasar_por_disco``).
    TAMANO_POR_DISCO = 10 * 1024 * 1024

    # Tamaño de cada trozo de esas bajadas y subidas grandes. El trozo viaja en
    # base64 dentro del JavaScript, así que no conviene que sea muy gordo: 2 MB
    # (que además es múltiplo de 4, que es lo que pide la subida por trozos).
    TAMANO_TROZO = 2 * 1024 * 1024

    # Y de todo lo que hay en esas carpetas solo se pasan los documentos de
    # oficina. En una biblioteca de verdad (actas, informes, presentaciones) hay
    # también vídeos, fotos, zip y PDF que no se clasifican y pesan muchísimo:
    # bajar uno de esos para nada es lo peor que se puede hacer con el disco y
    # con el tiempo del usuario. Lo que no esté aquí no se lista, no se baja y
    # no se mueve (con la tupla vacía se pasa todo, por si algún día hace falta).
    EXTENSIONES_UTILES = (".ppt", ".pptx", ".doc", ".docx")

    # Y hay archivos que la regla manda NO tocar (una transcripción de reunión, un
    # anexo técnico, una propuesta de Consultoría, o algo que hay que revisar
    # antes de clasificar). Para eso el plan trae esta palabra en lugar de una
    # carpeta: el archivo no se pasa (ni se baja, ni acaba en 'Otros', ni se crea
    # una carpeta con el nombre de la excusa). ``es_omitir`` la reconoce escrita
    # de cualquier forma ('omitir', 'SE OMITE', '[REVISAR]', 'revisar: falta
    # alcance').
    OMITIR = "omitir"
    PALABRAS_OMITIR = (
        "omitir", "omitido", "omitida", "omitidos", "omitidas", "omite",
        "se omite", "obviar", "ignorar", "descartar", "descartado",
        "no se mueve", "no mover", "no pasar", "no aplica", "no clasifica",
        "sin clasificar", "excluir", "excluido", "revisar", "pendiente",
        "ninguna", "ninguno", "n/a",
        # Tal como lo dice la regla de propuestas: 'no es propuesta' es una
        # excusa, no una carpeta donde dejar el archivo.
        "no es propuesta", "no es una propuesta", "no es nuestra propuesta",
    )
    # Y hay un tercer caso, que es el que deja los archivos sin clasificar: la IA
    # no sabe a qué carpeta va un archivo con solo verlo ('PROPUESTA COMERCIAL
    # bfddfa36 RFI...' no dice si es de QA, de Portales o de IA). Antes eso salía
    # como 'omitir' (no se movía nada y el usuario no entendía por qué) o como
    # raíz del destino (todo amontonado en la misma carpeta). Ahora el plan lo
    # dice con esta palabra y quien llama hace algo con ella: le leer el contenido
    # al documento (``modules.pistas``) y volver a preguntarle a la IA. Lo que
    # siga aquí no se toca: mejor un archivo quieto que uno en la carpeta
    # equivocada.
    DUDOSO = "sin clasificar"

    # Para poder contarle al usuario la verdad hay que saber qué dice su REGLA
    # (el texto que escribió). Si la regla manda dejar archivos fuera, un archivo
    # sin carpeta es justo lo que se pidió; si no dice nada de eso, un archivo sin
    # carpeta es que no se supo clasificar, y eso hay que decirlo así (no echarle
    # la culpa a la regla).
    PALABRAS_OMITIR_REGLA = (
        "omit", "no se toca", "no se tocan", "no toques", "no tocar", "sin tocar",
        "no mover", "no los muevas", "no pasar", "no los pases", "deja fuera",
        "dejar fuera", "excluir", "excluye", "excluido", "descartar", "descarta",
    )
    # Y si la regla manda dejar algo TAL CUAL en la carpeta de destino, la raíz es
    # una respuesta buena: sin esto, un plan que manda todo a la raíz se tomaría
    # por un fallo y se volvería a preguntar en balde.
    PALABRAS_RAIZ_REGLA = (
        "raíz", "raiz", "tal cual", "sin subcarpeta", "sin carpeta",
        "sin subcarpetas", "directo", "donde están", "donde estan",
    )

    @classmethod
    def regla_deja_fuera(cls, regla):
        """¿La regla del usuario dice que hay archivos que no se tocan?

        Solo se usa para hablarle al usuario con la verdad (un archivo sin
        carpeta porque la regla lo manda no es lo mismo que uno sin carpeta
        porque la IA no supo clasificarlo) y para no volver a preguntar cuando el
        plan es exactamente lo que la regla pedía.
        """
        texto = (regla or "").lower()
        return any(palabra in texto for palabra in cls.PALABRAS_OMITIR_REGLA)

    @classmethod
    def regla_pide_la_raiz(cls, regla):
        """¿La regla dice que hay archivos que se quedan sin subcarpeta?"""
        texto = (regla or "").lower()
        return any(palabra in texto for palabra in cls.PALABRAS_RAIZ_REGLA)

    # Lo que SharePoint NO admite dentro del nombre de una carpeta. El separador
    # de niveles es '/', así que se limpia antes de crear cada nivel.
    CARACTERES_VETADOS = '"*:<>?\\|'

    # Al listar una carpeta se puede mirar también DENTRO de sus subcarpetas:
    # 2 niveles (las carpetas de dentro y las de dentro de esas), que es donde
    # están los documentos en las bibliotecas de verdad (una carpeta por cliente
    # y, dentro, sus años y sus expedientes).
    PROFUNDIDAD_BUSQUEDA = 2
    # Topes de esa búsqueda: mejor acotar y avisar (``nota_listado``) que
    # recorrer media biblioteca sin decir nada.
    MAXIMO_CARPETAS = 300
    MAXIMO_ARCHIVOS = 400
    # Cuántas carpetas del DESTINO se le enseñan a la IA (``catalogo_carpetas``)
    # para que use las que ya existen en vez de inventarse otras parecidas. En
    # una biblioteca de verdad hay cientos: se corta y se dice (``nota_catalogo``),
    # que un prompt con 500 nombres es peor que uno con 120.
    MAXIMO_CARPETAS_CATALOGO = 120

    def _api_binario(self, sitio, ruta_api, contenido=None, correctos=(200,)):
        """Baja o sube contenido BINARIO usando la pestaña de Brave.

        Sin ``contenido`` hace un GET del archivo (``$value``) y devuelve sus
        bytes. Con contenido sube esos bytes al endpoint que se le pida
        (``Files/add``), que es la única forma de llevar un archivo a OTRO sitio:
        bajarlo y volverlo a subir.

        El contenido se pasa al navegador en base64 y en trozos; si se pasara de
        golpe, el motor de JavaScript se cae con los archivos grandes (o con los
        que no lo son tanto).
        """
        url = sitio.rstrip("/") + "/_api" + ruta_api
        if contenido is None:
            js = ("(async () => { try {"
                  " const r = await fetch(" + json.dumps(url) + ","
                  " {credentials:'include', cache:'no-store'});"
                  " const buf = new Uint8Array(await r.arrayBuffer());"
                  " const texto = r.ok ? ''"
                  " : new TextDecoder().decode(buf);"
                  " let s = ''; const TROZO = 0x8000;"
                  " for (let i = 0; i < buf.length; i += TROZO) {"
                  "  s += String.fromCharCode.apply(null,"
                  "       buf.subarray(i, i + TROZO)); }"
                  " return {estado: r.status, cuerpo: texto,"
                  " base64: btoa(s), tamano: buf.length};"
                  " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        else:
            contexto = sitio.rstrip("/") + "/_api/contextinfo"
            datos = base64.b64encode(contenido).decode("ascii")
            js = ("(async () => { try {"
                  " const c = await fetch(" + json.dumps(contexto) + ","
                  " {method:'POST', credentials:'include',"
                  " headers:{'Accept':'application/json;odata=verbose'}});"
                  " if (!c.ok) return {estado: c.status, cuerpo: await c.text(),"
                  " paso: 'token'};"
                  " const token = (await c.json()).d"
                  ".GetContextWebInformation.FormDigestValue;"
                  " const bin = atob(" + json.dumps(datos) + ");"
                  " const buf = new Uint8Array(bin.length);"
                  " for (let i = 0; i < bin.length; i++)"
                  " { buf[i] = bin.charCodeAt(i); }"
                  " const r = await fetch(" + json.dumps(url) + ","
                  " {method:'POST', credentials:'include',"
                  " headers:{'X-RequestDigest': token}, body: buf});"
                  " return {estado: r.status, cuerpo: await r.text()};"
                  " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        resultado = self._pestana(sitio).evaluar(js)
        self._respuesta(resultado, correctos=correctos)
        if contenido is None:
            codificado = resultado.get("base64") or ""
            return base64.b64decode(codificado) if codificado else b""
        return b""

    def _api_rango(self, sitio, ruta_api, desde, hasta):
        """Un trozo del archivo (``Range: bytes=desde-hasta``).

        Es lo que permite bajar un archivo grande sin meterlo entero en un
        mensaje de la pestaña. Devuelve ``(bytes del trozo, tamaño total)``; el
        total es ``None`` si el servidor no contesta con ``Content-Range`` (en
        ese caso los bytes que llegan son todo el archivo).
        """
        url = sitio.rstrip("/") + "/_api" + ruta_api
        rango = f"bytes={desde}-{hasta}"
        js = ("(async () => { try {"
              " const r = await fetch(" + json.dumps(url) + ","
              " {credentials:'include', cache:'no-store',"
              " headers:{'Range':" + json.dumps(rango) + "}});"
              " const buf = new Uint8Array(await r.arrayBuffer());"
              " const partes = (r.headers.get('Content-Range') || '').split('/');"
              " const total = partes.length > 1 ? Number(partes[1]) : 0;"
              " let s = ''; const TROZO = 0x8000;"
              " for (let i = 0; i < buf.length; i += TROZO) {"
              "  s += String.fromCharCode.apply(null,"
              "       buf.subarray(i, i + TROZO)); }"
              " return {estado: r.status,"
              " cuerpo: r.ok ? '' : new TextDecoder().decode(buf),"
              " base64: r.ok ? btoa(s) : '', total: total};"
              " } catch (e) { return {estado: -1, cuerpo: String(e)}; } })()")
        resultado = self._pestana(sitio).evaluar(js)
        self._respuesta(resultado, correctos=(200, 206))
        codificado = resultado.get("base64") or ""
        return (base64.b64decode(codificado) if codificado else b"",
                _entero(resultado.get("total")) or None)

    @staticmethod
    def _odata(ruta):
        """Prepara una ruta server-relative para un literal OData '...'.

        Codifica espacios y demás caracteres raros, deja las barras y las
        comillas simples (que OData escapa duplicándolas: O'Brien -> O''Brien).
        """
        return urllib.parse.quote(ruta, safe="/'").replace("'", "''")

    # ---------------- Listados paginados ----------------
    def _paginado(self, sitio, ruta_api, paginas=25):
        """Todas las páginas de un listado de la API.

        SharePoint corta los listados (unos 100 elementos) y pone la página
        siguiente en ``d.__next`` con un ``$skiptoken``: sin seguirla, una
        carpeta con 250 archivos (o con 180 subcarpetas) parecería tener 100.
        """
        elementos, siguiente = [], ruta_api
        for numero in range(paginas):
            if not siguiente:
                break
            if numero:
                self._aviso(f"El listado viene por partes: {len(elementos)} "
                            f"elemento(s) leídos, pidiendo la página "
                            f"{numero + 1}...")
            datos = self._api(sitio, siguiente)
            d = datos.get("d") or {}
            elementos += d.get("results") or []
            siguiente = self._siguiente_pagina(d.get("__next"), ruta_api)
        return elementos

    @staticmethod
    def _siguiente_pagina(enlace, ruta_api):
        """Ruta ``/_api`` de la página siguiente a partir de ``d.__next``.

        Lo normal es que venga como URL completa, pero también puede llegar como
        ruta suelta o como la consulta sin más; se acepta todo.
        """
        enlace = (enlace or "").strip()
        if not enlace:
            return ""
        if "/_api" in enlace:
            return enlace.split("/_api", 1)[1]
        if enlace.startswith("/"):
            return enlace
        return ruta_api.split("?", 1)[0] + "?" + enlace.lstrip("?")

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
    def _web_de(ruta):
        """Sitio (``/sites/X``, ``/teams/X``, ``/personal/usuario``) de una ruta.

        Devuelve '' si la ruta no empieza por uno de esos prefijos, que es lo
        normal en el web raíz de una colección de sitios.
        """
        pedazos = (ruta or "").strip("/").split("/")
        if len(pedazos) >= 2 and pedazos[0] in ("sites", "teams", "personal"):
            return "/" + "/".join(pedazos[:2])
        return ""

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
    def parsear_url(url):
        """Convierte una URL de SharePoint/OneDrive en (sitio, carpeta, dominio).

        Acepta tanto la carpeta en crudo como la URL de la vista que copia
        SharePoint (``.../Oportunidad/Forms/AllItems.aspx?viewid=...``): se
        queda con la carpeta de la que cuelga la vista. Si la URL trae
        ``RootFolder=`` o ``id=`` (SharePoint los añade al navegar por dentro
        de una biblioteca) mandan esos valores, que son los que de verdad
        apuntan a la carpeta. Y si apuntan a otro sitio del mismo host (la vista
        de 'Mi unidad' de OneDrive, ``.../my?id=/personal/<usuario>/...``, por
        ejemplo), también manda su sitio: preguntar por esa carpeta en el sitio
        equivocado da 403.

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
        web_rel = "/"
        resto = segmentos
        for marca in ("personal", "sites", "teams"):
            if marca in segmentos:
                indice = segmentos.index(marca)
                web_rel = "/" + "/".join(segmentos[:indice + 2])
                resto = segmentos[indice + 2:]
                break

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
            # La carpeta del parámetro puede estar en OTRO sitio del mismo host,
            # y entonces manda ella: la ruta de la vista solo dice por dónde
            # andaba el usuario. Pasa al copiar la dirección de 'Mi unidad' en
            # OneDrive (`.../my?id=/personal/<usuario>/...`, que vive en el host
            # -my) o al abrir un enlace de otra biblioteca. Sin esto se llamaba
            # al web raíz del host con una ruta `/personal/...` y SharePoint
            # respondía 403 (UnauthorizedAccess).
            web_de_carpeta = SharePoint._web_de(carpeta_rel)
            if web_de_carpeta:
                web_rel = web_de_carpeta
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

    # ---------------- Lectura ----------------
    def listar_archivos(self, url, profundidad=0):
        """Archivos de una carpeta. Lista de {nombre, ruta_rel, subruta, tamano}.

        Si la URL es la del sitio a secas (o la de tu unidad), se usa la
        biblioteca de documentos del sitio: es donde están los archivos.

        Con ``profundidad`` mira además DENTRO de las subcarpetas, nivel a nivel
        (``SharePoint.PROFUNDIDAD_BUSQUEDA`` es lo que usa la clasificación). Es
        lo que hace falta en las bibliotecas de verdad: la carpeta de arriba
        suele tener una carpeta por cliente y los documentos están dentro, así
        que sin bajar hasta ellas parecería vacía.

        ``subruta`` es la ruta del archivo DENTRO de la carpeta pedida
        (``AXA/2024/acta.docx``): con ella se mueve o se copia el archivo
        correcto aunque haya varios con el mismo nombre en carpetas distintas.

        Solo se devuelven los **documentos de oficina** (``EXTENSIONES_UTILES``):
        los vídeos (y fotos, zip, PDF...) que hay en esas carpetas se quedan
        fuera, así que ni se clasifican ni se bajan. Cuántos me salté y en qué
        carpetas están (con su ruta, para poder ir a mirarlos) queda en
        ``descartados``, y el aviso (tanto de eso como de una búsqueda que se
        quedó a medias) en ``nota_listado`` ('' si no hay nada que contar).
        """
        info = self.parsear_url(self.resolver(url))
        if not self.carpeta_existe(info["sitio"], info["carpeta_rel"]):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {info['carpeta_rel']}. Comprueba la "
                "dirección (puedes pegar la de la vista 'Forms/AllItems.aspx').")
        self.nota_listado = ""
        fuera = {"total": 0, "carpetas": []}
        sitio = info["sitio"]
        raiz = (info["carpeta_rel"] or "/").rstrip("/")
        carpeta = self._odata(raiz)
        crudos = self._paginado(
            sitio,
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
            "?$select=Name,ServerRelativeUrl,Length")
        archivos = self._solo_utiles([self._archivo(f, "") for f in crudos],
                                     fuera, raiz)
        if profundidad > 0:
            if archivos:
                self._aviso(f"{len(archivos)} archivo(s) en la propia carpeta; "
                            "mirando también dentro de las subcarpetas...")
            else:
                self._aviso("La carpeta no tiene archivos sueltos: mirando "
                            "dentro de sus subcarpetas...")
            archivos += self._buscar_en_subcarpetas(sitio, raiz, profundidad,
                                                    fuera)
        self.descartados = fuera
        nota = self._nota_descartados(fuera)
        if nota:
            self.nota_listado = f"{self.nota_listado} {nota}".strip()
            self._aviso(nota)
        return archivos

    def _solo_utiles(self, archivos, fuera, raiz=""):
        """Deja solo los documentos de oficina, apuntando dónde están los demás.

        ``fuera`` va acumulando cuántos archivos me salté y las carpetas donde
        están: decirlo es lo que permite comprobar que no se me pasó nada por
        alto (y saber dónde viven los vídeos que no toco). ``raiz`` es la carpeta
        que se pidió (su ruta en SharePoint): los archivos que están sueltos en
        ella se apuntan con esa ruta, que el nombre del archivo no es una
        carpeta.
        """
        utiles = []
        for archivo in archivos:
            if self.es_util(archivo.get("nombre")):
                utiles.append(archivo)
                continue
            fuera["total"] += 1
            partes = (archivo.get("subruta") or "").strip("/").rsplit("/", 1)
            carpeta = partes[0].strip("/") if len(partes) > 1 else ""
            if not carpeta:
                # Suelto en la carpeta pedida: la carpeta es la pedida (con su
                # ruta), que el nombre del archivo no es una carpeta.
                carpeta = (raiz or "").strip() or "(la carpeta pedida)"
            if carpeta not in fuera["carpetas"]:
                fuera["carpetas"].append(carpeta)
        return utiles

    def _nota_descartados(self, fuera):
        """El aviso de los archivos que me salté ('' si no me salté ninguno).

        Nombra las carpetas donde están (con su ruta) porque es lo que se dice
        por el chat: así se sabe qué hay en esas carpetas y dónde, aunque no se
        toque.
        """
        if not fuera or not fuera.get("total"):
            return ""
        carpetas = fuera.get("carpetas") or []
        donde = ", ".join(carpetas[:4])
        if len(carpetas) > 4:
            donde += f" y {len(carpetas) - 4} carpeta(s) más"
        return (f"Me salté {fuera['total']} archivo(s) que no son "
                f"{self.extensiones_texto()} (vídeos y demás: no los bajo ni "
                f"los muevo). Están en: {donde or '(esta misma carpeta)'}.")

    @staticmethod
    def _archivo(datos, prefijo):
        """Archivo de la API al formato del módulo.

        Devuelve ``{nombre, ruta_rel, subruta, tamano}``. ``prefijo`` es la
        carpeta de la que cuelga dentro de la búsqueda ('' para los que están
        directamente en la carpeta pedida).
        """
        nombre = datos.get("Name") or ""
        return {"nombre": nombre,
                "ruta_rel": datos.get("ServerRelativeUrl") or "",
                "subruta": (prefijo + "/" + nombre).strip("/"),
                "tamano": _entero(datos.get("Length"))}

    def _subcarpetas_con_archivos(self, sitio, carpeta_rel):
        """Subcarpetas de una carpeta, cada una CON sus archivos.

        Todo en una sola llamada (``$expand=Files``): una carpeta con 180
        subcarpetas (una por cliente) se resuelve con una llamada, no con 181.
        """
        carpeta = self._odata(carpeta_rel)
        return self._paginado(
            sitio,
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Folders"
            "?$select=Name,ServerRelativeUrl&$expand=Files&$top=200")

    def _buscar_en_subcarpetas(self, sitio, raiz, profundidad, fuera=None):
        """Archivos que hay DENTRO de las subcarpetas de 'raiz'.

        Baja ``profundidad`` niveles: los archivos del primer nivel (los que
        están dentro de las carpetas de 'raiz') salen de la misma llamada que
        lista esas carpetas, y a partir de ahí cuesta una llamada por carpeta.
        Solo se queda con los documentos de oficina (``fuera`` va apuntando los
        que me salté y dónde están). Si se agota ``MAXIMO_CARPETAS`` o
        ``MAXIMO_ARCHIVOS`` se para y lo deja dicho en ``nota_listado``, en vez
        de callarse lo que falta.
        """
        fuera = {"total": 0, "carpetas": []} if fuera is None else fuera
        encontrados, pendientes, recorridas = [], [("", raiz)], 0
        for nivel in range(profundidad):
            if not pendientes:
                break
            self._aviso(f"Buscando archivos dentro de {len(pendientes)} "
                        f"carpeta(s) (nivel {nivel + 1} de {profundidad})...")
            siguiente = []
            for prefijo, carpeta_rel in pendientes:
                if recorridas >= self.MAXIMO_CARPETAS:
                    self.nota_listado = (
                        f"Me quedé en {self.MAXIMO_CARPETAS} carpetas: puedo "
                        "haber dejado archivos sin mirar (pásame la carpeta "
                        "concreta si falta alguno).")
                    break
                if len(encontrados) >= self.MAXIMO_ARCHIVOS:
                    self.nota_listado = (
                        f"Paré al llegar a {self.MAXIMO_ARCHIVOS} archivos: si "
                        "faltan, pásame la carpeta concreta.")
                    break
                recorridas += 1
                if recorridas % 25 == 0:
                    self._aviso(f"... {recorridas} carpeta(s) miradas, "
                                f"{len(encontrados)} archivo(s) encontrado(s)")
                for sub in self._subcarpetas_con_archivos(sitio, carpeta_rel):
                    nombre = sub.get("Name") or ""
                    subruta = (prefijo + "/" + nombre).strip("/")
                    crudos = (sub.get("Files") or {}).get("results") or []
                    encontrados += self._solo_utiles(
                        [self._archivo(crudo, subruta) for crudo in crudos],
                        fuera)
                    if sub.get("ServerRelativeUrl"):
                        siguiente.append((subruta, sub["ServerRelativeUrl"]))
            pendientes = siguiente
            if self.nota_listado:
                self._aviso(self.nota_listado)
                break
        if encontrados:
            self._aviso(f"Encontré {len(encontrados)} archivo(s) dentro de las "
                        f"subcarpetas ({recorridas} carpeta(s) miradas).")
        return encontrados

    def _subcarpetas(self, sitio, carpeta_rel):
        """Subcarpetas de una carpeta server-relative ({nombre, ruta_rel}).

        Es la llamada que usa ``listar_carpetas``, separada para poder recorrer
        un árbol de varios niveles sin volver a montar la URL en cada paso.
        """
        carpeta = self._odata(carpeta_rel)
        crudos = self._paginado(
            sitio,
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Folders"
            "?$select=Name,ServerRelativeUrl")
        return [{"nombre": f.get("Name", ""),
                 "ruta_rel": f.get("ServerRelativeUrl", "")}
                for f in crudos]

    def listar_carpetas(self, url):
        """Subcarpetas de una carpeta (lista de {nombre, ruta_rel}).

        Igual que ``listar_archivos``: si le pasas la URL del sitio a secas,
        mira dentro de su biblioteca de documentos.
        """
        info = self.parsear_url(self.resolver(url))
        if not self.carpeta_existe(info["sitio"], info["carpeta_rel"]):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {info['carpeta_rel']}.")
        return self._subcarpetas(info["sitio"], info["carpeta_rel"])

    def catalogo_carpetas(self, url, profundidad=None):
        """Carpetas que YA existen en el destino, con su rama y su subrama.

        Devuelve rutas RELATIVAS a la carpeta pedida, tal como se le pasan a la
        IA ('Assessment', 'Assessment/Data'): son las carpetas que ya están
        hechas y donde, por tanto, hay que dejar los archivos, en vez de crear
        otras que se le parezcan ('Assessment/Data Analysis' al lado de
        'Assessment/Data').

        ``profundidad`` es cuántos niveles se miran de ese destino
        (``PROFUNDIDAD_BUSQUEDA``: la rama y, dentro, la subrama).

        Si el destino todavía no existe devuelve una lista vacía (no es un
        error: se creará al pasar los archivos). Si hay más carpetas de las que
        se pueden enseñar, se corta (``MAXIMO_CARPETAS`` miradas y
        ``MAXIMO_CARPETAS_CATALOGO`` devueltas) y lo deja dicho en
        ``nota_catalogo``: callarse que el catálogo está incompleto sería
        invitar a inventar carpetas que ya existen.
        """
        self.nota_catalogo = ""
        if profundidad is None:
            profundidad = self.PROFUNDIDAD_BUSQUEDA
        info = self.parsear_url(self.resolver(url))
        if not self.carpeta_existe(info["sitio"], info["carpeta_rel"]):
            return []
        sitio = info["sitio"]
        catalogo, pendientes, miradas = [], [("", info["carpeta_rel"])], 0
        for nivel in range(profundidad):
            if not pendientes:
                break
            # Si ya se enseñaron todas las que caben, no se sigue mirando más
            # a fondo: hay carpetas del destino (y quizá subcarpetas) que la IA
            # no va a ver, y eso hay que decirlo. Callárselo sería peor: creería
            # que ya las conoce todas y volvería a inventar otras parecidas.
            if len(catalogo) >= self.MAXIMO_CARPETAS_CATALOGO:
                if not self.nota_catalogo:   # si ya se cortó al listar, se respeta
                    self.nota_catalogo = (
                        f"Ya te enseñé {self.MAXIMO_CARPETAS_CATALOGO} carpetas "
                        "del destino: no miré más a fondo (puede haber más).")
                break
            self._aviso(f"Mirando las carpetas que ya hay en el destino "
                        f"(nivel {nivel + 1} de {profundidad})...")
            siguiente = []
            for prefijo, carpeta_rel in pendientes:
                if miradas >= self.MAXIMO_CARPETAS:
                    self.nota_catalogo = (
                        f"Me quedé en {self.MAXIMO_CARPETAS} carpetas del "
                        "destino: puede haber más de las que te enseño.")
                    break
                miradas += 1
                for sub in self._subcarpetas(sitio, carpeta_rel):
                    nombre = (sub.get("nombre") or "").strip()
                    ruta_rel = sub.get("ruta_rel")
                    if not nombre or not ruta_rel:
                        continue
                    if len(catalogo) >= self.MAXIMO_CARPETAS_CATALOGO:
                        self.nota_catalogo = (
                            f"El destino tiene más carpetas: te enseño las "
                            f"primeras {self.MAXIMO_CARPETAS_CATALOGO}.")
                        break
                    subruta = (prefijo + "/" + nombre).strip("/")
                    catalogo.append(subruta)
                    siguiente.append((subruta, ruta_rel))
            pendientes = siguiente
        if self.nota_catalogo:
            self._aviso(self.nota_catalogo)
        return catalogo

    def tamano_de(self, sitio, ruta_rel):
        """Cuánto pesa un archivo, en bytes (``None`` si SharePoint no lo dice).

        Se pregunta antes de pasarlo: los archivos grandes van por el camino de
        bajarlos a tu PC y volverlos a subir por trozos, y para decidirlo hay que
        saber cuánto pesan.
        """
        ruta_api = ("/web/GetFileByServerRelativeUrl('" + self._odata(ruta_rel)
                    + "')?$select=Length")
        datos = self._api(sitio, ruta_api)
        return _entero(datos.get("d", {}).get("Length")) or None

    def _tamano_o_nada(self, sitio, ruta_rel):
        """El tamaño del archivo, o ``None`` si no se puede saber."""
        try:
            return self.tamano_de(sitio, ruta_rel)
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador, OSError):
            return None

    @staticmethod
    def _ruta_temporal(nombre):
        """Dónde se deja en tu PC el archivo que se baja (temp de Jarvis)."""
        limpio = os.path.basename((nombre or "").strip().replace("\\", "/"))
        limpio = limpio or "archivo"
        carpeta = os.path.join(rutas.TEMP, "sharepoint")
        os.makedirs(carpeta, exist_ok=True)
        return os.path.join(carpeta, f"{uuid.uuid4().hex[:8]}_{limpio}")

    def descargar(self, sitio, ruta_rel, maximo=None):
        """Contenido del archivo (bytes), bajado con la sesión de Brave.

        Es la pieza que hace posible copiar a OTRO sitio (a tu OneDrive, por
        ejemplo), porque ahí ``MoveTo`` no vale. Todo el archivo viaja en un
        mensaje a la pestaña, así que esto es para los normales: los grandes se
        bajan por trozos con ``descargar_a_disco``.

        Y solo se baja lo que sí paso (``EXTENSIONES_UTILES``): si le piden un
        vídeo, se para aquí (así ni se trae ni se sube a otro sitio).
        """
        self._exigir_util(ruta_rel.rsplit("/", 1)[-1], ruta_rel)
        ruta_api = ("/web/GetFileByServerRelativeUrl('" + self._odata(ruta_rel)
                    + "')/$value")
        datos = self._api_binario(sitio, ruta_api)
        limite = self.TAMANO_MAXIMO if maximo is None else maximo
        if len(datos) > limite:
            error = ErrorSharePoint(
                f"'{ruta_rel}' pesa {len(datos) / 1048576:.1f} MB y no cabe en "
                f"un mensaje de la pestaña de Brave (máximo {limite // 1048576} "
                "MB): hay que pasarlo por disco (bajarlo y subirlo por trozos).")
            error.pesado = True
            raise error
        return datos

    def descargar_a_disco(self, sitio, ruta_rel, ruta_local, tamano=None):
        """Baja el archivo a un archivo de tu PC, por trozos (``Range``).

        Los grandes no caben en un mensaje de la pestaña: se piden de
        ``TAMANO_TROZO`` en ``TAMANO_TROZO`` y se van escribiendo en disco. Si al
        final no coinciden los bytes con lo que dice SharePoint, se avisa en vez
        de dejar un archivo a medias (y el que llama no lo sube).
        Devuelve los bytes escritos.

        A tu PC solo se baja lo que sí paso (``EXTENSIONES_UTILES``): un vídeo no
        empieza a bajarse ni por asomo.
        """
        self._exigir_util(ruta_rel.rsplit("/", 1)[-1], ruta_rel)
        ruta_api = ("/web/GetFileByServerRelativeUrl('" + self._odata(ruta_rel)
                    + "')/$value")
        carpeta = os.path.dirname(ruta_local)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        nombre = ruta_rel.rsplit("/", 1)[-1]
        escrito, proximo_aviso = 0, 5 * 1048576
        with open(ruta_local, "wb") as salida:
            while True:
                trozo, total = self._api_rango(sitio, ruta_api, escrito,
                                               escrito + self.TAMANO_TROZO - 1)
                if not trozo:
                    break
                salida.write(trozo)
                escrito += len(trozo)
                if total and escrito >= total:
                    break
                if not total and len(trozo) < self.TAMANO_TROZO:
                    break  # el servidor ignoró el Range: ya llegó todo
                if escrito >= proximo_aviso:
                    proximo_aviso = escrito + 5 * 1048576
                    self._aviso(
                        f"Bajando {nombre} a tu PC: {escrito / 1048576:.1f} MB"
                        + (f" de {total / 1048576:.1f} MB..." if total
                           else "..."))
        if tamano and escrito != tamano:
            raise ErrorSharePoint(
                f"Bajé {escrito} de {tamano} bytes de '{ruta_rel}': el archivo "
                "no llegó completo, así que no lo paso.")
        return escrito

    def pistas_de(self, origen_url, nombres, maximo=None):
        """Lo que dice por dentro cada archivo de ``nombres`` ({nombre: pista}).

        Es el segundo intento de la clasificación: cuando la IA no sabe a qué
        carpeta va un archivo ('sin clasificar'), se le enseña el **título y las
        primeras líneas del propio documento** (``modules.pistas``) y se le
        vuelve a preguntar. Un nombre como 'PROPUESTA COMERCIAL bfddfa36' no dice
        si es de QA o de Portales; la portada del documento sí.

        Se leen de los BYTES (se baja el archivo con la misma sesión de Brave,
        sin pasar por disco ni abrir Word) y solo de los que se piden. Del que no
        se pueda sacar nada (un .ppt viejo, un documento protegido, uno que no
        baja) no hay entrada: quien llama clasifica sin pista, como antes.

        ``origen_url`` es de donde salieron los archivos: la subcarpeta de cada
        nombre (``AXA/2024/acta.docx``) dice dónde está dentro de esa URL.
        """
        pistas_de_archivo = {}
        if not nombres:
            return pistas_de_archivo
        origen_url = self.resolver(origen_url)
        info = self.parsear_url(origen_url)
        sitio = info["sitio"]
        raiz = (info.get("carpeta_rel") or "/").rstrip("/")
        for nombre in nombres:
            dentro, archivo = self._partir_nombre(nombre)
            if not archivo:
                continue
            ruta_rel = raiz + ("/" + dentro if dentro else "") + "/" + archivo
            try:
                datos = self.descargar(sitio, ruta_rel)
            except Exception as e:
                # Nunca se tumba la clasificación por no poder leer un documento:
                # de ese se clasifica por el nombre, como antes. Lo típico es un
                # archivo grande (no cabe en un mensaje de la pestaña de Brave) o
                # uno que ya no está.
                self._aviso(f"No pude leer {archivo} por dentro ({e}).")
                continue
            pista = pistas.pista_de(datos, archivo, maximo or pistas.MAXIMO)
            if pista:
                pistas_de_archivo[nombre] = pista
        return pistas_de_archivo

    # ---------------- Escritura ----------------
    def crear_carpeta(self, sitio, carpeta_rel):
        """Crea una carpeta en SharePoint (si ya existe, se ignora el error)."""
        datos = {"__metadata": {"type": "SP.Folder"},
                 "ServerRelativeUrl": carpeta_rel}
        try:
            self._api(sitio, "/web/folders", metodo="POST", datos=datos)
        except ErrorSharePoint:
            pass  # ya existía: el mover funcionará igual

    def mover(self, sitio, ruta_rel_origen, carpeta_rel_destino, nombre,
              tamano=None):
        """Mueve un archivo a otra carpeta del MISMO sitio (``MoveTo``).

        ``flags=1`` sobrescribe si ya hay un archivo con ese nombre en destino.
        Los archivos grandes (``TAMANO_POR_DISCO``) no se mueven así porque
        SharePoint los deja a medias: se bajan a tu PC, se suben al destino y,
        ya comprobado que lo que llegó pesa lo mismo, se borra el original. Y si
        SharePoint se atraganta con un archivo que no es "tan" grande (unos
        pocos MB), se hace por disco igual.

        Lo que no sea un documento de oficina (``EXTENSIONES_UTILES``) no se
        mueve: un vídeo de esas carpetas se queda donde está.
        """
        self._exigir_util(nombre, ruta_rel_origen)
        if tamano is None:
            tamano = self._tamano_o_nada(sitio, ruta_rel_origen)
        if tamano and tamano > self.TAMANO_POR_DISCO:
            self._pasar_por_disco(sitio, ruta_rel_origen, sitio,
                                  carpeta_rel_destino, nombre, tamano=tamano,
                                  borrar_origen=True)
            return
        destino = carpeta_rel_destino.rstrip("/") + "/" + nombre
        nueva_url = self._odata(destino)
        origen = self._odata(ruta_rel_origen)
        ruta_api = (f"/web/GetFileByServerRelativeUrl('{origen}')"
                    f"/MoveTo(newUrl='{nueva_url}',flags=1)")
        try:
            self._api(sitio, ruta_api, metodo="POST", datos={})
        except ErrorSharePoint as e:
            if not self._merece_disco(e):
                raise
            self._aviso(f"SharePoint no pudo mover {nombre} de una vez ({e}). "
                        "Lo paso bajándolo a tu PC y subiéndolo.")
            self._pasar_por_disco(sitio, ruta_rel_origen, sitio,
                                  carpeta_rel_destino, nombre, tamano=tamano,
                                  borrar_origen=True)

    @staticmethod
    def _merece_disco(error):
        """¿El fallo del ``MoveTo``/``CopyTo`` se puede reintentar por disco?

        Si lo que falló es la sesión (401), el permiso (403) o que el archivo no
        está (404), bajarlo y subirlo tampoco va a servir: se deja salir el error
        original, que es el que explica lo que pasa.
        """
        return getattr(error, "estado", None) not in (401, 403, 404)

    def _pasar_por_disco(self, sitio_origen, ruta_rel_origen, sitio_destino,
                         carpeta_rel_destino, nombre, tamano=None,
                         sobrescribir=True, borrar_origen=False):
        """Lleva un archivo al destino bajándolo a tu PC y subiéndolo por trozos.

        Es el camino de los archivos grandes y el respaldo cuando SharePoint se
        atraganta con un ``MoveTo``/``CopyTo``. Con ``borrar_origen`` (un
        movimiento de verdad) el original se borra SOLO después de comprobar que
        lo que quedó en el destino pesa lo mismo; si no se puede comprobar, se
        deja el original donde estaba (antes duplicado que perdido).

        Si algo falla, no se borra nada y el archivo bajado se queda en tu PC
        (``Jarvis\\temp\\sharepoint``): el mensaje dice dónde.

        Antes de empezar se comprueba que el archivo sea de los que paso
        (``EXTENSIONES_UTILES``): esto es lo que impide bajarse un vídeo.
        """
        self._exigir_util(nombre, ruta_rel_origen)
        ruta_local = self._ruta_temporal(nombre)
        peso = f"{tamano / 1048576:.1f} MB" if tamano else "bastante"
        self._aviso(f"'{nombre}' pesa {peso}: lo bajo a tu PC y lo subo al "
                    "destino (SharePoint no lo pasa de una vez).")
        try:
            bajado = self.descargar_a_disco(sitio_origen, ruta_rel_origen,
                                            ruta_local, tamano=tamano)
            self.subir_desde_disco(sitio_destino, carpeta_rel_destino, nombre,
                                   ruta_local, sobrescribir=sobrescribir)
            destino_rel = carpeta_rel_destino.rstrip("/") + "/" + nombre
            puesto = self._tamano_o_nada(sitio_destino, destino_rel)
            if puesto is not None and puesto != bajado:
                raise ErrorSharePoint(
                    f"Subí '{nombre}' pero en el destino pesa {puesto} bytes y "
                    f"el original {bajado}: no me fío, así que no toco nada.")
            if borrar_origen and puesto is None:
                self._aviso(f"'{nombre}' está en el destino, pero no pude "
                            "comprobar cuánto pesa: dejo el original por si "
                            "acaso.")
            elif borrar_origen:
                self.borrar_archivo(sitio_origen, ruta_rel_origen)
                self._aviso(f"'{nombre}' ya está en el destino: borro el "
                            "original (queda en la papelera del sitio).")
        except Exception as e:
            raise ErrorSharePoint(
                f"{e}\nEl archivo que bajé está en tu PC: {ruta_local}. "
                "No borré nada del original.") from e
        try:
            os.remove(ruta_local)
        except OSError:
            pass

    def subir(self, sitio, carpeta_rel, nombre, datos, sobrescribir=True):
        """Sube un archivo (bytes ya en memoria) a una carpeta del sitio.

        ``Files/add`` es el endpoint de toda la vida; ``AddUsingPath`` entiende
        mejor los nombres con ``#``, ``%`` o ``+``. Se intenta el primero y, si
        el servidor no lo traga, el segundo.
        """
        carpeta = self._odata(carpeta_rel.rstrip("/") or "/")
        marca = "true" if sobrescribir else "false"
        # Dentro del literal OData '...' la comilla simple se duplica.
        decodificado = (nombre or "").replace("'", "''")
        intentos = [
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
            f"/add(url='{self._odata(nombre)}',overwrite={marca})",
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
            f"/AddUsingPath(DecodedUrl='{decodificado}',overwrite={marca})",
        ]
        ultimo = None
        for ruta_api in intentos:
            try:
                self._api_binario(sitio, ruta_api, contenido=datos)
                return
            except ErrorSharePoint as e:
                ultimo = e
        raise ultimo

    def subir_desde_disco(self, sitio, carpeta_rel, nombre, ruta_local,
                          sobrescribir=True):
        """Sube al destino un archivo que ya está en tu PC (``ruta_local``).

        Los pequeños van de una vez con ``Files/add``, que es el camino de
        siempre. Los grandes van con la subida por trozos de SharePoint
        (``StartUpload`` / ``ContinueUpload`` / ``FinishUpload``): la primera
        prepara el archivo, las siguientes le añaden trozos y la última lo cierra.
        Si esa subida no funcionara, se intenta de una vez y, si tampoco, el
        archivo se queda en tu PC y el mensaje dice dónde.
        Devuelve los bytes subidos.
        """
        tamano = os.path.getsize(ruta_local)
        if tamano <= self.TAMANO_TROZO:
            with open(ruta_local, "rb") as archivo:
                self.subir(sitio, carpeta_rel, nombre, archivo.read(),
                           sobrescribir=sobrescribir)
            return tamano
        try:
            self._crear_para_trozos(sitio, carpeta_rel, nombre, sobrescribir)
            self._subir_por_trozos(
                sitio, carpeta_rel.rstrip("/") + "/" + nombre, ruta_local,
                tamano)
        except ErrorSharePoint as e:
            self._aviso(f"La subida por trozos de {nombre} no funcionó ({e}): "
                        "lo intento de una vez.")
            if tamano > self.TAMANO_MAXIMO:
                raise ErrorSharePoint(
                    f"{e}\nTambién es demasiado grande para subirlo de una vez "
                    f"({tamano / 1048576:.1f} MB). El archivo sigue en tu PC: "
                    f"{ruta_local}") from e
            try:
                with open(ruta_local, "rb") as archivo:
                    self.subir(sitio, carpeta_rel, nombre, archivo.read(),
                               sobrescribir=sobrescribir)
            except ErrorSharePoint:
                raise ErrorSharePoint(
                    f"{e}\nNo pude subir '{nombre}' de ninguna forma. El "
                    f"archivo sigue en tu PC: {ruta_local}") from e
        return tamano

    def _crear_para_trozos(self, sitio, carpeta_rel, nombre, sobrescribir):
        """Prepara el archivo (vacío) en el destino para la subida por trozos."""
        carpeta = self._odata(carpeta_rel.rstrip("/") or "/")
        marca = "true" if sobrescribir else "false"
        ruta_api = (f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
                    f"/add(url='{self._odata(nombre)}',overwrite={marca})")
        self._api_binario(sitio, ruta_api, contenido=b"",
                          correctos=(200, 201, 204))

    def _subir_por_trozos(self, sitio, destino_rel, ruta_local, tamano):
        """Sube el archivo en trozos (``StartUpload`` ... ``FinishUpload``).

        El trozo que cierra el archivo va con ``FinishUpload`` y los demás con
        ``ContinueUpload``, cada uno con el desplazamiento (``fileOffset``) donde
        empieza. Cada paso lleva su token de escritura.
        """
        base = ("/web/GetFileByServerRelativeUrl('" + self._odata(destino_rel)
                + "')")
        subida = uuid.uuid4()
        nombre = destino_rel.rsplit("/", 1)[-1]
        self._api_binario(sitio,
                          f"{base}/StartUpload(uploadId=guid'{subida}')",
                          contenido=b"", correctos=(200, 201, 204))
        escrito = 0
        with open(ruta_local, "rb") as archivo:
            while escrito < tamano:
                trozo = archivo.read(self.TAMANO_TROZO)
                if not trozo:
                    break
                metodo = ("FinishUpload" if escrito + len(trozo) >= tamano
                          else "ContinueUpload")
                ruta_api = (f"{base}/{metodo}(uploadId=guid'{subida}',"
                            f"fileOffset={escrito})")
                self._api_binario(sitio, ruta_api, contenido=trozo,
                                  correctos=(200, 201, 204))
                escrito += len(trozo)
                self._aviso(f"Subiendo {nombre} al destino: "
                            f"{escrito / 1048576:.1f} de "
                            f"{tamano / 1048576:.1f} MB...")
        if escrito != tamano:
            raise ErrorSharePoint(
                f"Subí {escrito} de {tamano} bytes de '{nombre}': la subida se "
                "quedó a medias.")

    def copiar(self, sitio_origen, ruta_rel_origen, sitio_destino,
               carpeta_rel_destino, nombre, sobrescribir=True, tamano=None):
        """Copia un archivo a otra carpeta, del mismo sitio o de otro distinto.

        - Mismo sitio: lo copia SharePoint (``CopyTo``), sin bajarlo.
        - Sitios distintos (p. ej. de un sitio de equipo a tu OneDrive): la API
          no sabe hacerlo, así que se baja el archivo y se sube al destino. El
          original NO se toca.
        - Archivos grandes (``TAMANO_POR_DISCO``), o cuando SharePoint se
          atraganta con el ``CopyTo``, o cuando no cabe en un mensaje de la
          pestaña: se bajan a tu PC por trozos y se suben desde ahí.

        Lo que no sea un documento de oficina (``EXTENSIONES_UTILES``) no se
        copia: los vídeos de esas carpetas ni se bajan ni se suben.
        """
        self._exigir_util(nombre, ruta_rel_origen)
        if tamano is None:
            tamano = self._tamano_o_nada(sitio_origen, ruta_rel_origen)
        if tamano and tamano > self.TAMANO_POR_DISCO:
            self._pasar_por_disco(sitio_origen, ruta_rel_origen, sitio_destino,
                                  carpeta_rel_destino, nombre, tamano=tamano,
                                  sobrescribir=sobrescribir)
            return
        if sitio_origen.rstrip("/") == sitio_destino.rstrip("/"):
            destino = carpeta_rel_destino.rstrip("/") + "/" + nombre
            ruta_api = ("/web/GetFileByServerRelativeUrl('"
                        + self._odata(ruta_rel_origen) + "')"
                        + f"/CopyTo(strNewUrl='{self._odata(destino)}',"
                        + f"bOverwrite={'true' if sobrescribir else 'false'})")
            try:
                self._api(sitio_origen, ruta_api, metodo="POST", datos={})
                return
            except ErrorSharePoint as e:
                if not self._merece_disco(e):
                    raise
                self._aviso(f"SharePoint no pudo copiar {nombre} de una vez "
                            f"({e}). Lo paso bajándolo a tu PC y subiéndolo.")
                self._pasar_por_disco(sitio_origen, ruta_rel_origen,
                                      sitio_destino, carpeta_rel_destino,
                                      nombre, tamano=tamano,
                                      sobrescribir=sobrescribir)
                return
        try:
            datos = self.descargar(sitio_origen, ruta_rel_origen)
        except ErrorSharePoint as e:
            if not getattr(e, "pesado", False):
                raise
            # Pesa más de lo que cabe de una vez: se hace por disco.
            self._pasar_por_disco(sitio_origen, ruta_rel_origen, sitio_destino,
                                  carpeta_rel_destino, nombre,
                                  sobrescribir=sobrescribir)
            return
        self.subir(sitio_destino, carpeta_rel_destino, nombre, datos,
                   sobrescribir=sobrescribir)

    def borrar_archivo(self, sitio, ruta_rel):
        """Manda un archivo a la papelera del sitio (se puede recuperar).

        Se borra con un POST y ``X-HTTP-Method: DELETE``, que es como lo hace la
        API REST de SharePoint.
        """
        ruta_api = ("/web/GetFileByServerRelativeUrl('"
                    + self._odata(ruta_rel) + "')")
        self._api(sitio, ruta_api, metodo="POST", datos={},
                  cabeceras={"X-HTTP-Method": "DELETE", "IF-MATCH": "*"})

    # ---------------- Carpeta de trabajo (resolver la URL que pega el usuario) ----------------
    @staticmethod
    def _url_de(info, carpeta_rel):
        """URL completa de una carpeta a partir de lo que saca ``parsear_url``."""
        esquema = urllib.parse.urlparse(info["sitio"]).scheme or "https"
        return f"{esquema}://{info['dominio']}{carpeta_rel}"

    def _biblioteca_del_sitio(self, sitio):
        """Ruta de la biblioteca de documentos del sitio, o '' si no la veo."""
        try:
            datos = self._api(
                sitio, "/web/lists?$filter=BaseTemplate eq 101"
                       "&$select=RootFolder&$expand=RootFolder"
                       "&$orderby=Created asc&$top=1")
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador, OSError):
            # Sin permiso o sin Brave no se puede preguntar. Mejor seguir con el
            # nombre típico que reventar aquí: si la carpeta no existe, el error
            # saldrá al comprobarla.
            return ""
        for lista in datos.get("d", {}).get("results", []):
            raiz = (lista.get("RootFolder") or {}).get("ServerRelativeUrl")
            if raiz:
                return "/" + raiz.strip("/")
        return ""

    def _sitio_personal(self, info):
        """Sitio personal (OneDrive) del usuario, o '' si no se puede saber.

        Solo hace falta cuando la URL es la del host de OneDrive
        (``https://empresa-my.sharepoint.com/``) y no trae el
        ``/personal/<usuario>``: ahí la URL no dice de quién es la unidad, así
        que se le pregunta a tu perfil (``GetMyProperties``) en la raíz del
        tenant.
        """
        dominio = info.get("dominio") or ""
        if "-my.sharepoint.com" not in dominio:
            return ""
        if (info.get("web_rel") or "/").strip("/"):
            return ""
        try:
            datos = self._api(
                "https://" + dominio.replace("-my.sharepoint.com",
                                             ".sharepoint.com"),
                "/SP.UserProfiles.PeopleManager/GetMyProperties"
                "?$select=PersonalUrl,UserUrl")
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador, OSError):
            return ""
        perfil = datos.get("d") or {}
        return (perfil.get("PersonalUrl")
                or perfil.get("UserUrl") or "").rstrip("/")

    def _biblioteca(self, info):
        """Carpeta de la biblioteca de documentos del sitio de ``info``.

        - Sitio de equipo o sitio personal concreto: su biblioteca original. Se
          le pregunta a la API porque el nombre cambia con el idioma
          ('Documentos compartidos', 'Shared Documents', 'Documents').
        - OneDrive sin usuario en la URL: tu unidad, que vive en tu sitio
          personal, así que primero se busca tu sitio personal. Si no se puede
          saber (sin perfil, sin Brave), se avisa: mejor pedir la URL de la
          carpeta que inventársela.
        - Último recurso: el nombre típico, 'Documents'.
        """
        carpeta = self._biblioteca_del_sitio(info["sitio"])
        if carpeta:
            return carpeta
        dominio = info.get("dominio") or ""
        es_unidad = ("-my.sharepoint.com" in dominio
                     and not (info.get("web_rel") or "/").strip("/"))
        if es_unidad:
            personal = self._sitio_personal(info)
            if not personal:
                raise ErrorSharePoint(
                    "Esa es la URL de tu unidad de OneDrive y no trae el "
                    "usuario, así que no sé en qué carpeta dejar los archivos. "
                    "Abre tu OneDrive en Brave, copia la dirección de "
                    "'Mi unidad' (termina en /Documents) y pásamela.")
            info_personal = self.parsear_url(personal)
            carpeta = self._biblioteca_del_sitio(info_personal["sitio"])
            if carpeta:
                return carpeta
            return info_personal["web_rel"].rstrip("/") + "/Documents"
        return (info["web_rel"].rstrip("/") + "/Documents") or "/"

    def resolver(self, url):
        """URL de la carpeta REAL de trabajo a partir de lo que pegó el usuario.

        Hace falta porque pegar la URL del sitio "a secas" es lo más natural, y
        ahí no hay archivos: los documentos viven en la biblioteca del sitio.
        Sobre todo en OneDrive, donde ``https://empresa-my.sharepoint.com/``
        significa "mi unidad" y esta está en ``/personal/<usuario>/Documents``.

        Si la URL ya apunta a una carpeta concreta se devuelve tal cual (no se
        gasta ni una llamada).
        """
        info = self.parsear_url(url)
        rel = (info.get("carpeta_rel") or "/").rstrip("/")
        raiz = (info.get("web_rel") or "/").rstrip("/")
        if rel and rel != raiz:
            return url
        biblioteca = self._biblioteca(info)
        self._aviso(f"Esa dirección era la del sitio: usaré su carpeta de "
                    f"documentos ({biblioteca or '/'}), que es donde están los "
                    "archivos.")
        return self._url_de(info, biblioteca)

    # ---------------- Clasificación ----------------
    def _grandes_del_plan(self, plan, tamanos):
        """Cuántos archivos del plan pasan de ``TAMANO_POR_DISCO``.

        Solo se puede saber si quien llama trae los tamaños (el listado del
        origen los trae): sirve para avisar de que esos van por disco, que es
        mucho más lento y el usuario merece saberlo antes de esperar.
        """
        if not tamanos:
            return 0
        return sum(1 for nombre, _ in plan
                   if (_entero(tamanos.get(nombre)) > self.TAMANO_POR_DISCO))

    @staticmethod
    def _partir_nombre(nombre):
        """Separa 'carpeta/dentro/archivo.pdf' en ('carpeta/dentro', 'archivo.pdf').

        Los nombres del plan pueden traer la carpeta de la que sale el archivo
        (cuando la búsqueda bajó a las subcarpetas) o no traerla (lo normal).
        """
        limpio = (nombre or "").strip().strip("/")
        if "/" not in limpio:
            return "", limpio
        dentro, archivo = limpio.rsplit("/", 1)
        return dentro, archivo

    @staticmethod
    def es_omitir(subcarpeta):
        """¿El plan dice que este archivo NO se toque? ('omitir', '[REVISAR]'...).

        La decisión viaja en la subcarpeta, que es el único campo del plan. Sin
        esto, un archivo que la regla deja fuera (una transcripción, una
        Consultoría, algo 'por revisar') acababa copiado en el destino —y bajado
        a tu PC si era grande— solo porque el plan tenía que decir algo.
        """
        limpio = (subcarpeta or "").strip().strip("*.\"'`[](){} ").lower()
        limpio = " ".join(limpio.split())
        if not limpio:
            return False
        if limpio in SharePoint.PALABRAS_OMITIR:
            return True
        # Frases: 'se omite (no es propuesta)', 'revisar: falta el alcance',
        # 'no aplica en esta regla'. Se busca por palabra completa para que
        # 'omision' o 'revisadas' no cuelen.
        palabras = re.split(r"[\s:;,.(/\[\]]+", limpio)
        if palabras and palabras[0] in SharePoint.PALABRAS_OMITIR:
            return True
        # Y las de dos palabras ('se omite', 'no aplica'), al principio.
        for palabra in SharePoint.PALABRAS_OMITIR:
            if " " in palabra and limpio.startswith(palabra):
                return True
        return False

    @staticmethod
    def es_dudoso(subcarpeta):
        """¿El plan dice que no se supo a qué carpeta va este archivo?

        Se mira ANTES que ``es_omitir`` (que también reconoce 'sin clasificar'):
        "no lo toques" no es lo mismo que "no sé dónde va", y el segundo tiene
        arreglo (leer el documento y volver a preguntar). Lo que siga dudoso se
        queda quieto, que es lo honesto.
        """
        limpio = (subcarpeta or "").strip().strip("*.\\\"'`[](){} ").lower()
        return " ".join(limpio.split()) == SharePoint.DUDOSO

    @staticmethod
    def limpiar_subcarpeta(subcarpeta):
        """Deja la subcarpeta como una ruta que SharePoint acepte.

        La regla puede pedir dos niveles (rama y subrama: 'Assessment/Data') y
        cada uno tiene que ser un nombre válido, así que se respeta '/' como
        separador y se quita de cada nivel lo que SharePoint rechaza (comillas,
        dos puntos, '|', '*'...). Los adornos de la IA ('**Assessment**', comillas,
        corchetes) también se van: un nombre con '|' hace que la carpeta no se
        pueda crear y el archivo se quede sin destino.
        """
        texto = (subcarpeta or "").replace("\\", "/")
        niveles = []
        for trozo in texto.split("/"):
            nombre = trozo.strip().strip("*`'\"[](){} ").strip(". ")
            for veto in SharePoint.CARACTERES_VETADOS:
                nombre = nombre.replace(veto, "")
            nombre = " ".join(nombre.split()).strip(". ")
            if nombre:
                niveles.append(nombre)
        return "/".join(niveles)

    @staticmethod
    def separar_omitidos(plan):
        """Parte el plan en (los que van, los que la regla deja sin tocar).

        Se hace antes de enseñar el plan y antes de contar: los omitidos no se
        pasan, así que no deben contar para pedir confirmación (``UMBRAL_CLASIFICAR``)
        ni para decir cuántos archivos se movieron.
        """
        van, omitidos = [], []
        for nombre, subcarpeta in plan or []:
            destino = omitidos if SharePoint.es_omitir(subcarpeta) else van
            destino.append((nombre, subcarpeta))
        return van, omitidos

    @staticmethod
    def separar_dudosos(plan):
        """Parte el plan en (lo que no es dudoso, lo que la IA dejó 'sin clasificar').

        'Dudoso' es lo que la IA no supo dónde poner (``DUDOSO``), y no es lo
        mismo que lo que la regla manda no tocar (``OMITIR``): de un dudoso
        todavía se puede averiguar algo (leer el documento y volver a preguntar,
        que es lo que hace ``SystemActions`` con ``pistas_de``), y de lo que la
        regla deja fuera no hay nada que averiguar. Por eso lo que la regla deja
        fuera se queda en la primera lista (junto a los que sí tienen carpeta) y
        lo separa después ``separar_omitidos``.

        Se llama con el plan en crudo (antes de separar los omitidos) porque
        'sin clasificar' lo entienden las dos listas: quien llama se queda con
        los dudosos para el segundo intento y deja el resto para 'el que la regla
        manda no tocar'. Lo que siga dudoso después de ese intento se queda
        quieto: ``_solo_del_plan`` también lo reconoce como 'no se toca'.
        """
        van, dudosos = [], []
        for nombre, subcarpeta in plan or []:
            destino = dudosos if SharePoint.es_dudoso(subcarpeta) else van
            destino.append((nombre, subcarpeta))
        return van, dudosos

    @staticmethod
    def _partir_omitidos(omitidos):
        """Parte lo que no se pasa en (lo que la regla deja fuera, las dudas).

        Son dos cosas distintas y el resumen no puede llamarlas igual: en una la
        regla del usuario dijo 'esto no se toca' (``omitir``, ``revisar``...), y
        en la otra la IA no supo en qué carpeta poner el archivo (``DUDOSO``, o
        'sin clasificar'), que es una duda del programa, no una decisión de la
        regla. Decirlo al revés haría creer al usuario que él lo pidió así.
        """
        fuera, dudas = [], []
        for nombre, subcarpeta in omitidos or []:
            destino = dudas if SharePoint.es_dudoso(subcarpeta) else fuera
            destino.append((nombre, subcarpeta))
        return fuera, dudas

    def _solo_del_plan(self, plan):
        """Separa el plan en (los que paso, los que la regla omite, los que no).

        El plan sale del listado (que ya viene filtrado), pero puede traer de
        todo: un nombre que la IA escribió a mano, un plan viejo con vídeos
        dentro, o un archivo que la regla manda no tocar. Se separan aquí para no
        pasar ni uno de esos, y para poder decir en el resumen cuáles se quedaron
        fuera y por qué.

        Aquí también caen los que la IA dejó 'sin clasificar': ``es_omitir`` los
        reconoce, así que **nunca se pasan** ni aunque quien llama se haya saltado
        el segundo intento (``separar_dudosos`` + ``pistas_de``). Un archivo
        quieto es mejor que uno en la carpeta equivocada.
        """
        utiles, omitidos, otros = [], [], []
        for nombre, subcarpeta in plan or []:
            _, archivo = self._partir_nombre(nombre)
            if not archivo:
                continue
            if self.es_omitir(subcarpeta):
                omitidos.append((nombre, subcarpeta))
            elif self.es_util(archivo):
                utiles.append((nombre, subcarpeta))
            else:
                otros.append((nombre, subcarpeta))
        return utiles, omitidos, otros

    def _asegurar_carpetas(self, sitio, raiz, subcarpeta, creadas=None):
        """Deja lista la subcarpeta (nivel a nivel) y devuelve su ruta.

        La regla puede pedir dos niveles (rama y subrama: 'Assessment/Data'), y
        SharePoint solo crea una carpeta si su carpeta madre ya existe: pedirle de
        golpe '/Destino/Assessment/Data' cuando 'Assessment' no está no crea nada
        (``crear_carpeta`` se traga el error) y el archivo se quedaría sin
        destino. Por eso se va bajando un nivel cada vez, madre antes que hija.

        No se pregunta si cada nivel existe: crear una carpeta que ya está no
        rompe nada (``crear_carpeta`` ignora ese error) y ahorra una llamada por
        archivo. ``creadas`` es el conjunto de rutas que ya sabemos que están (las
        que trae el listado del destino más las de esta misma tanda): eso no se
        vuelve a pedir.
        """
        ruta = (raiz or "/").rstrip("/")
        for nivel in (subcarpeta or "").split("/"):
            nivel = nivel.strip()
            if not nivel:
                continue
            ruta = (ruta + "/" + nivel) if ruta else "/" + nivel
            if creadas is not None:
                if ruta in creadas:
                    continue
                creadas.add(ruta)
            self.crear_carpeta(sitio, ruta)
        return ruta or "/"

    def clasificar_y_mover(self, origen_url, destino_url, plan, copiar=None,
                           tamanos=None, carpetas=None):
        """Mueve (o copia) archivos según 'plan' (lista de (nombre, subcarpeta)).

        - Mismo sitio: se mueven con ``MoveTo`` (con ``copiar=True`` se copian
          con ``CopyTo`` y el original se queda).
        - **Sitios distintos** (por ejemplo, de una biblioteca de equipo a tu
          OneDrive): SharePoint no deja mover ni copiar de un sitio a otro, así
          que se bajan los archivos y se suben al destino. El original se queda
          donde estaba: no se pierde nada.
        - Las URLs se resuelven antes: si dan la raíz del sitio (lo típico en
          OneDrive, ``https://empresa-my.sharepoint.com/`` = "mi unidad"), se
          usa su biblioteca de documentos.
        - Los archivos grandes (``TAMANO_POR_DISCO``) no van con ``MoveTo`` ni
          ``CopyTo``: se bajan a tu PC por trozos y se suben desde ahí. Si se
          sabe cuánto pesan (``tamanos``, que es lo que trae el listado del
          origen) no hay que preguntarlo archivo por archivo.

        Cada nombre del plan puede traer la carpeta de la que sale el archivo
        (``AXA/2024/acta.docx``) cuando el origen se buscó dentro de sus
        subcarpetas: esa carpeta es del ORIGEN (sirve para encontrarlo), y al
        destino va solo el nombre del archivo, dentro de la subcarpeta que dice
        la regla.

        Del plan solo se pasa lo que son documentos de oficina
        (``EXTENSIONES_UTILES``): si viene un vídeo (o un PDF, o un zip) se queda
        fuera y se dice en el resumen, en vez de bajarlo para nada. Y lo que la
        regla manda **no tocar** (``OMITIR``: transcripciones, Consultoría, cosas
        por revisar) tampoco se pasa: ni se baja, ni se crea una carpeta con esa
        excusa por nombre. Los que la IA dejó **sin clasificar** (``DUDOSO``)
        también se quedan quietos aquí: quien llama debería haberles leído el
        documento y vuelto a preguntar (``pistas_de``), pero si llegan hasta aquí
        no se pasan (``_solo_del_plan`` los trata como omitidos): mejor un archivo
        quieto que uno en la carpeta equivocada.

        La subcarpeta del plan puede traer **dos niveles** (rama y subrama:
        'Assessment/Data'): se crean uno a uno (``_asegurar_carpetas``), porque
        SharePoint no crea una carpeta si su madre no existe.

        ``carpetas`` son las que YA existen en el destino (``catalogo_carpetas``)
        y sirven de red de seguridad: si el plan escribe 'assessment/data' y en
        el destino ya está 'Assessment/Data', el archivo va a esa (no a una
        nueva que se le parezca). Sin ese catálogo se usan las carpetas del
        primer nivel que se listan aquí mismo, que es lo que ya se hacía.

        Nunca pisa un archivo que ya exista en el destino: en ese caso lo deja
        donde está y lo informa. Si no puede comprobar el destino (por ejemplo
        sin permiso), tampoco pasa ese archivo. Devuelve un texto con el
        resumen.
        """
        plan, omitidos, ignorados = self._solo_del_plan(plan)
        pedidos = len(plan) + len(omitidos) + len(ignorados)
        origen_url = self.resolver(origen_url)
        destino_url = self.resolver(destino_url)
        info_origen = self.parsear_url(origen_url)
        info_destino = self.parsear_url(destino_url)
        sitio_origen = info_origen["sitio"]
        sitio_destino = info_destino["sitio"]
        entre_sitios = sitio_origen.rstrip("/") != sitio_destino.rstrip("/")
        copiar = entre_sitios if copiar is None else bool(copiar)
        verbo = "Copiados" if copiar else "Movidos"
        gerundio = "Copiando" if copiar else "Moviendo"
        self._aviso(f"{gerundio} {pedidos} archivo(s) a {destino_url}"
                    + (" (los originales siguen donde estaban)." if entre_sitios
                       else "."))
        # Fuera del plan se queda de dos maneras distintas, y decir cuál es cada
        # una no es lo mismo: lo que la regla manda no tocar ('omitir') es una
        # decisión, y lo que la IA no supo dónde poner ('sin clasificar') es una
        # duda. Se cuentan por separado para no llamar 'tu regla' a lo que no lo
        # es (y para que se vea que hubo archivos que no se pudieron colocar).
        fuera, sin_saber = self._partir_omitidos(omitidos)
        if ignorados:
            self._aviso(f"Me salté {len(ignorados)} archivo(s) que no son "
                        f"{self.extensiones_texto()}: esos no los toco.")
        if fuera:
            self._aviso(f"Y dejo {len(fuera)} archivo(s) sin tocar (tu regla los "
                        "deja fuera).")
        if sin_saber:
            self._aviso(f"Y dejo {len(sin_saber)} archivo(s) sin tocar: no supe "
                        "en qué carpeta ponerlos (mejor quietos que mal puestos).")
        if not plan:
            lineas = [f"No {'copié' if copiar else 'moví'} nada: de {pedidos} "
                      "archivo(s) del plan, ninguno pasa."]
            if ignorados:
                lineas.append(f"Solo paso {self.extensiones_texto()}:")
                lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in ignorados]
            if fuera:
                lineas.append("Y los demás se quedan donde están (tu regla los "
                              "deja fuera):")
                lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in fuera]
            if sin_saber:
                lineas.append("Y estos se quedan donde están porque no supe en "
                              "qué carpeta ponerlos (mejor quietos que mal "
                              "puestos):")
                lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in sin_saber]
            lineas.append("Los dejé donde estaban.")
            return "\n".join(lineas)
        grandes = self._grandes_del_plan(plan, tamanos)
        if grandes:
            self._aviso(f"{grandes} de esos archivo(s) pasan de "
                        f"{self.TAMANO_POR_DISCO // 1048576} MB: esos los bajo a "
                        "tu PC y los subo al destino (SharePoint no los pasa de "
                        "una vez).")

        # El destino tiene que existir (y si no, lo crea) antes de nada.
        raiz_origen = (info_origen["carpeta_rel"] or "/").rstrip("/")
        raiz_destino = (info_destino["carpeta_rel"] or "/").rstrip("/") or "/"
        try:
            if not self.carpeta_existe(sitio_destino, raiz_destino):
                self.crear_carpeta(sitio_destino, raiz_destino)
        except ErrorSharePoint as e:
            return (f"No {'copié' if copiar else 'moví'} nada: no pude preparar "
                    f"la carpeta de destino ({raiz_destino}): {e}")
        try:
            existentes = {c.get("ruta_rel")
                          for c in self.listar_carpetas(destino_url)
                          if c.get("ruta_rel")}
        except ErrorSharePoint:
            existentes = set()  # la intentaré crear y ya dirá
        # Red de seguridad: si el plan escribe la carpeta de otra forma que el
        # destino ('assessment/data' con el 'Assessment/Data' que ya está), se
        # usa la que existe. Sale gratis: las carpetas de arriba ya están
        # listadas, y si quien llama trae el catálogo (que se miró más a fondo
        # antes de clasificar) se usa ese.
        catalogo = carpetas or self._catalogo_de_existentes(existentes,
                                                            raiz_destino)
        if catalogo:
            alineado = [(nombre, self.alinear_carpeta(subcarpeta, catalogo))
                        for nombre, subcarpeta in plan]
            if alineado != list(plan):
                self._aviso("El destino ya tiene esas carpetas: uso las que "
                            "están hechas, no creo otras que se parezcan.")
                plan = alineado

        pasados, conflictos, sin_comprobar, fallos = [], [], [], []
        comprobados = {}
        for nombre, subcarpeta in plan:
            subcarpeta = self.limpiar_subcarpeta(subcarpeta)
            # El nombre puede traer la carpeta de la que sale el archivo
            # ('AXA/2024/acta.pdf') cuando el origen se buscó dentro de sus
            # subcarpetas: esa carpeta es del ORIGEN (sirve para encontrarlo),
            # no del destino, donde manda la subcarpeta que dice la regla.
            dentro, archivo = self._partir_nombre(nombre)
            if not archivo:
                continue
            etiqueta = subcarpeta or "(raíz)"

            # 1) Preparar el destino y mirar si el archivo ya está ahí.
            #    Si algo de esto falla, NO lo paso: antes quieto que pisando.
            try:
                # La subcarpeta (con sus niveles, si la regla pide rama y
                # subrama) se prepara primero: sin destino no hay nada que hacer.
                destino_rel = self._asegurar_carpetas(sitio_destino, raiz_destino,
                                                      subcarpeta, existentes)
                destino_rel = destino_rel or "/"
                ruta_final = destino_rel.rstrip("/") + "/" + archivo
                if destino_rel not in comprobados:
                    comprobados[destino_rel] = self.carpeta_existe(sitio_destino,
                                                                   destino_rel)
                if comprobados[destino_rel]:
                    if ruta_final not in comprobados:
                        comprobados[ruta_final] = self.archivo_existe(
                            sitio_destino, ruta_final)
                    if comprobados[ruta_final]:
                        conflictos.append(f"{nombre} → {etiqueta}")
                        self._aviso(f"Ya existe en el destino, no lo toco: "
                                    f"{archivo} ({etiqueta})")
                        continue
            except ErrorSharePoint as e:
                sin_comprobar.append(f"{nombre} → {etiqueta}: {e}")
                self._aviso(f"No paso {archivo}: no pude comprobar el destino "
                            f"({e}).")
                continue

            # 2) Pasarlo: mover dentro del sitio, copiar si son sitios distintos.
            try:
                origen_rel = (raiz_origen + ("/" + dentro if dentro else "")
                              + "/" + archivo)
                tamano = (tamanos or {}).get(nombre)
                if copiar:
                    self.copiar(sitio_origen, origen_rel, sitio_destino,
                                destino_rel, archivo, tamano=tamano)
                else:
                    self.mover(sitio_origen, origen_rel, destino_rel, archivo,
                               tamano=tamano)
                comprobados[ruta_final] = True
                pasados.append(f"{nombre} → {etiqueta}")
                self._aviso(f"{gerundio} {len(pasados)} de {len(plan)}: "
                            f"{nombre} → {etiqueta}")
            except ErrorSharePoint as e:
                fallos.append(f"{nombre}: {e}")
                self._aviso(f"No pude con {archivo}: {e}")

        lineas = [f"{verbo} {len(pasados)} de {pedidos} archivo(s):"]
        lineas += [f"  ✓ {p}" for p in pasados]
        if entre_sitios and pasados:
            lineas.append(f"Los originales siguen en {sitio_origen} "
                          "(no los toco).")
        if ignorados:
            lineas.append(f"No los toqué (solo {self.extensiones_texto()}):")
            lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in ignorados]
        if fuera:
            lineas.append("No los toqué (tu regla los deja fuera):")
            lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in fuera]
        if sin_saber:
            lineas.append("No los toqué: no supe en qué carpeta ponerlos:")
            lineas += [f"  - {n} → {s or '(raíz)'}" for n, s in sin_saber]
        if conflictos:
            lineas.append("Ya existían en el destino (no los toco):")
            lineas += [f"  = {c}" for c in conflictos]
        if sin_comprobar:
            lineas.append("No los pasé: no pude comprobar el destino "
                          "(así no piso nada):")
            lineas += [f"  ? {s}" for s in sin_comprobar]
        if fallos:
            lineas.append("Fallos:")
            lineas += [f"  ✗ {f}" for f in fallos]
        return "\n".join(lineas)

    @staticmethod
    def clasificar_naive(nombres, regla):
        """Clasificación de respaldo (sin IA): todo a la raíz del destino."""
        return [(n, "") for n in nombres]

    @staticmethod
    def _clave_nivel(nombre):
        """Nombre de carpeta reducido a una clave, para comparar sin adornos.

        'Assessment', ' assessment ' y 'ASSESSMENT' dan la misma clave: así lo
        que la IA escribe de una forma acaba en la carpeta que ya existe aunque
        esté escrita de otra.
        """
        texto = (nombre or "").strip().strip("*-`'\"[](){} ").lower()
        return " ".join(re.sub(r"[\s_\-]+", " ", texto).split())

    @staticmethod
    def alinear_carpeta(subcarpeta, catalogo):
        """Escribe la carpeta como la tiene el destino, cuando ya existe.

        ``catalogo`` son las carpetas que ya hay en el destino ('Assessment',
        'Assessment/Data'). Cada nivel de ``subcarpeta`` se cambia por el del
        destino cuando la clave coincide (mismo nombre salvo mayúsculas,
        espacios o guiones): 'assessment/data' -> 'Assessment/Data'.

        Si el nivel no está en el catálogo se deja como venía (puede ser una
        carpeta nueva de verdad) y si hay dos carpetas distintas con la misma
        clave, también: mejor dejarlo tal cual que meter el archivo en la que no
        es.

        Y lo que no es una carpeta sino una decisión ('omitir', 'sin clasificar')
        se devuelve tal cual: esas palabras no se parecen a ninguna carpeta del
        destino, y si alguna se llamara así sería pura casualidad.
        """
        pedido = (subcarpeta or "").strip().strip("/")
        if not pedido or not catalogo:
            return pedido
        if SharePoint.es_omitir(pedido) or SharePoint.es_dudoso(pedido):
            return pedido
        reales = {}
        for ruta in catalogo:
            for nivel, nombre in enumerate((ruta or "").split("/")):
                clave = SharePoint._clave_nivel(nombre)
                if clave:
                    reales.setdefault((nivel, clave), set()).add(nombre.strip())
        niveles = []
        for nivel, nombre in enumerate(pedido.split("/")):
            candidatos = reales.get((nivel, SharePoint._clave_nivel(nombre))) or ()
            niveles.append(next(iter(candidatos)) if len(candidatos) == 1 else nombre)
        return "/".join(niveles)

    @staticmethod
    def _catalogo_de_existentes(existentes, raiz, profundidad=2):
        """Rutas relativas (hasta ``profundidad`` niveles) de lo que ya existe.

        ``existentes`` son rutas absolutas de SharePoint ('/sites/X/Archivo')
        y ``raiz`` la carpeta de destino: lo que no cuelga de ella se ignora,
        que no forma parte de este destino.
        """
        prefijo = (raiz or "/").rstrip("/") + "/"
        relativas = []
        for ruta in existentes or ():
            limpia = (ruta or "").rstrip("/")
            if not limpia.startswith(prefijo):
                continue
            niveles = limpia[len(prefijo):].split("/")
            if not niveles or len(niveles) > profundidad:
                continue
            relativas.append("/".join(niveles))
        return relativas

    @staticmethod
    def ajustar_plan(plan, archivos, catalogo=None):
        """Cambia los nombres del plan por la ruta real de cada archivo.

        La IA (y cualquiera) a veces devuelve el nombre sin la carpeta
        ('acta.pdf' en vez de 'AXA/2024/acta.pdf'). Si ese nombre corto
        identifica a UN solo archivo de los encontrados se usa su ruta; si es
        ambiguo (hay varios 'acta.pdf' en carpetas distintas) o no existe, se
        deja tal cual: así el fallo se ve en el resumen y no se pasa nunca un
        archivo por otro.

        Con ``catalogo`` (las carpetas que ya existen en el destino) también se
        alinea la subcarpeta de destino (``alinear_carpeta``): el archivo va a
        la carpeta que ya está hecha y no a una nueva que se le parezca.
        """
        por_subruta, por_nombre = {}, {}
        for a in archivos or []:
            subruta = (a.get("subruta") or a.get("nombre") or "").strip("/")
            if not subruta:
                continue
            por_subruta.setdefault(subruta.lower(), subruta)
            clave = (a.get("nombre") or "").strip().lower()
            if clave:
                por_nombre.setdefault(clave, []).append(subruta)
        ajustado = []
        for nombre, subcarpeta in plan or []:
            limpio = (nombre or "").strip()
            real = por_subruta.get(limpio.strip("/").lower())
            if real is None:
                candidatos = por_nombre.get(limpio.strip("/").lower()) or []
                if len(candidatos) == 1:
                    real = candidatos[0]
            ajustado.append((real or limpio,
                             SharePoint.alinear_carpeta(subcarpeta, catalogo)))
        return ajustado

    # ---------------- Diagnóstico ----------------
    def probar(self, url):
        """Comprueba la sesión listando la carpeta. Devuelve un texto.

        Sale también lo que se saltó el listado (``nota_listado``): si la
        carpeta está llena de vídeos, sin ese aviso parecería vacía.
        """
        try:
            self.asegurar_navegador(url)
            archivos = self.listar_archivos(url)
        except (ErrorSharePoint, navegador_cdp.ErrorNavegador) as e:
            return f"No pude acceder: {e}"
        if not archivos:
            dicho = ("Conectado. La carpeta no tiene archivos en su raíz "
                     "(puede tener subcarpetas dentro).")
            if self.nota_listado:
                dicho += f"\n{self.nota_listado}"
            return dicho
        lineas = [f"Conectado. {len(archivos)} archivo(s):"]
        lineas += [f"  📄 {a['nombre']}" for a in archivos[:20]]
        if self.nota_listado:
            lineas.append(self.nota_listado)
        return "\n".join(lineas)
