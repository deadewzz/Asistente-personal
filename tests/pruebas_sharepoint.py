"""Pruebas de SharePoint sin Graph.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_sharepoint.py

Prueba la lógica que no necesita Brave ni red: parseo de URLs de
SharePoint/OneDrive, construcción de las llamadas `_api` (con una pestaña
falsa), clasificación y resumen de desplazamientos. Las llamadas reales se
validan contra la sesión del usuario con `tests/diagnostico_brave.py`.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def pruebas_clasificar_y_mover():
    print("\n== Clasificar y mover ==")
    sp = SharePoint()
    creadas, movidos = [], []
    sp.listar_carpetas = lambda url: [{"nombre": "Otros", "ruta_rel": "/x"}]
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
    sp2.listar_carpetas = lambda url: []
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
    sp3.listar_carpetas = lambda url: []
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
    sp4.listar_carpetas = lambda url: []
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
    sp5.listar_carpetas = lambda url: []
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
    sp6.listar_carpetas = lambda url: []
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

    try:
        sp.clasificar_y_mover("https://a.sharepoint.com/sites/X",
                              "https://b.sharepoint.com/sites/Y", [("a.pdf", "X")])
        comprobar(False, "avisa si origen y destino están en sitios distintos")
    except ErrorSharePoint:
        comprobar(True, "avisa si origen y destino están en sitios distintos")


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
    ruta = os.path.join(tempfile.gettempdir(), "asistente_sharepoint_js.js")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            for i, js in enumerate(pestana.visto):
                f.write(f"const j{i} = {js};\n")
        proceso = subprocess.run([node, "--check", ruta],
                                 capture_output=True, text=True)
        comprobar(proceso.returncode == 0,
                  "las expresiones JS (GET y POST) compilan sin errores"
                  + ("" if proceso.returncode == 0
                     else f": {proceso.stderr[:200]}"))
    finally:
        if os.path.exists(ruta):
            os.remove(ruta)


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
    pruebas_clasificar_y_mover()
    pruebas_javascript_valido()
    pruebas_clasificacion_naive()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
