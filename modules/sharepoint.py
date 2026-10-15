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
  carpetas y mover archivos (``MoveTo``).

¿Por qué NO leemos la base de cookies de Brave? Porque Brave moderno las cifra
con **App-Bound Encryption** (prefijo ``v20``), que por diseño no se puede
descifrar desde fuera del navegador. Comprobado en este equipo: había
``app_bound_encrypted_key``, las cookies eran ``v20`` y SharePoint devolvía 401.
Dejar que Brave haga la petición es la vía fiable.

No guarda contraseñas: solo reutiliza la sesión que el usuario ya abrió.
"""

import json
import urllib.parse

from modules import navegador_cdp


class ErrorSharePoint(Exception):
    pass


class SharePoint:
    """Listar, crear carpetas y mover archivos en SharePoint/OneDrive."""

    def __init__(self):
        self.error = ""
        self.nota = ""             # aviso del último acceso al navegador
        self.on_clasificar = None  # (nombres, regla) -> [(nombre, subcarpeta)]
        self._pestanas = {}        # sitio -> navegador_cdp.Pestana

    # ---------------- Sesión de Brave (CDP) ----------------
    def asegurar_navegador(self, url):
        """Deja Brave controlable por CDP. Devuelve una nota de lo que hizo."""
        self.nota = navegador_cdp.asegurar(url)
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
        resultado = self._pestana(sitio).evaluar(js)
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
    def parsear_url(url):
        """Convierte una URL de SharePoint/OneDrive en (sitio, carpeta, dominio).

        Acepta tanto la carpeta en crudo como la URL de la vista que copia
        SharePoint (``.../Oportunidad/Forms/AllItems.aspx?viewid=...``): se
        queda con la carpeta de la que cuelga la vista. Si la URL trae
        ``RootFolder=`` o ``id=`` (SharePoint los añade al navegar por dentro
        de una biblioteca) mandan esos valores, que son los que de verdad
        apuntan a la carpeta.

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
    def listar_archivos(self, url):
        """Archivos de una carpeta. Lista de {nombre, ruta_rel, tamano}."""
        info = self.parsear_url(url)
        if not self.carpeta_existe(info["sitio"], info["carpeta_rel"]):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {info['carpeta_rel']}. Comprueba la "
                "dirección (puedes pegar la de la vista 'Forms/AllItems.aspx').")
        carpeta = self._odata(info["carpeta_rel"])
        datos = self._api(
            info["sitio"],
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Files"
            "?$select=Name,ServerRelativeUrl,Length")
        return [{"nombre": f.get("Name", ""),
                 "ruta_rel": f.get("ServerRelativeUrl", ""),
                 "tamano": f.get("Length", 0)}
                for f in datos.get("d", {}).get("results", [])]

    def listar_carpetas(self, url):
        """Subcarpetas de una carpeta (lista de {nombre, ruta_rel})."""
        info = self.parsear_url(url)
        if not self.carpeta_existe(info["sitio"], info["carpeta_rel"]):
            raise ErrorSharePoint(
                f"Esa carpeta no existe: {info['carpeta_rel']}.")
        carpeta = self._odata(info["carpeta_rel"])
        datos = self._api(
            info["sitio"],
            f"/web/GetFolderByServerRelativeUrl('{carpeta}')/Folders"
            "?$select=Name,ServerRelativeUrl")
        return [{"nombre": f.get("Name", ""),
                 "ruta_rel": f.get("ServerRelativeUrl", "")}
                for f in datos.get("d", {}).get("results", [])]

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

        ``flags=1`` sobrescribe si ya hay un archivo con ese nombre en destino.
        """
        destino = carpeta_rel_destino.rstrip("/") + "/" + nombre
        nueva_url = self._odata(destino)
        origen = self._odata(ruta_rel_origen)
        ruta_api = (f"/web/GetFileByServerRelativeUrl('{origen}')"
                    f"/MoveTo(newUrl='{nueva_url}',flags=1)")
        self._api(sitio, ruta_api, metodo="POST", datos={})

    # ---------------- Clasificación ----------------
    def clasificar_y_mover(self, origen_url, destino_url, plan):
        """Mueve archivos según 'plan' (lista de (nombre, subcarpeta)).

        Nunca pisa un archivo que ya exista en el destino: en ese caso lo deja
        donde está y lo informa. Si no puede comprobar el destino (por ejemplo
        sin permiso), tampoco mueve ese archivo. Devuelve un texto con el
        resumen.
        """
        info_origen = self.parsear_url(origen_url)
        info_destino = self.parsear_url(destino_url)
        if info_origen["sitio"] != info_destino["sitio"]:
            raise ErrorSharePoint(
                "SharePoint solo deja mover archivos dentro del mismo sitio: "
                f"origen {info_origen['sitio']} y destino {info_destino['sitio']}.")
        sitio = info_origen["sitio"]

        # El destino tiene que existir (y si no, lo crea) antes de nada.
        raiz_destino = info_destino["carpeta_rel"].rstrip("/") or "/"
        try:
            if not self.carpeta_existe(sitio, raiz_destino):
                self.crear_carpeta(sitio, raiz_destino)
        except ErrorSharePoint as e:
            return ("No moví nada: no pude preparar la carpeta de destino "
                    f"({raiz_destino}): {e}")
        try:
            existentes = {c["nombre"] for c in self.listar_carpetas(destino_url)}
        except ErrorSharePoint:
            existentes = set()  # la intentaré crear y ya dirá

        movidos, conflictos, sin_comprobar, fallos = [], [], [], []
        comprobados = {}
        for nombre, subcarpeta in plan:
            subcarpeta = (subcarpeta or "").strip()
            destino_rel = info_destino["carpeta_rel"].rstrip("/")
            if subcarpeta:
                destino_rel += "/" + subcarpeta.strip("/")
            destino_rel = destino_rel or "/"
            etiqueta = subcarpeta or "(raíz)"
            ruta_final = destino_rel.rstrip("/") + "/" + nombre

            # 1) Preparar el destino y mirar si el archivo ya está ahí.
            #    Si algo de esto falla, NO muevo: prefiero no mover a pisar.
            try:
                if subcarpeta and subcarpeta not in existentes:
                    self.crear_carpeta(sitio, destino_rel)
                    existentes.add(subcarpeta)
                if destino_rel not in comprobados:
                    comprobados[destino_rel] = self.carpeta_existe(sitio,
                                                                   destino_rel)
                if comprobados[destino_rel]:
                    if ruta_final not in comprobados:
                        comprobados[ruta_final] = self.archivo_existe(
                            sitio, ruta_final)
                    if comprobados[ruta_final]:
                        conflictos.append(f"{nombre} → {etiqueta}")
                        continue
            except ErrorSharePoint as e:
                sin_comprobar.append(f"{nombre} → {etiqueta}: {e}")
                continue

            # 2) Mover.
            try:
                origen_rel = (info_origen["carpeta_rel"].rstrip("/") + "/"
                              + nombre)
                self.mover(sitio, origen_rel, destino_rel, nombre)
                comprobados[ruta_final] = True
                movidos.append(f"{nombre} → {etiqueta}")
            except ErrorSharePoint as e:
                fallos.append(f"{nombre}: {e}")

        lineas = [f"Movidos {len(movidos)} de {len(plan)} archivo(s):"]
        lineas += [f"  ✓ {m}" for m in movidos]
        if conflictos:
            lineas.append("Ya existían en el destino (no los toco):")
            lineas += [f"  = {c}" for c in conflictos]
        if sin_comprobar:
            lineas.append("No los moví: no pude comprobar el destino "
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
