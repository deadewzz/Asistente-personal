"""Pruebas del correo en la nube (Microsoft Graph) con la capa HTTP simulada.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_correo_nube.py

No toca tu configuración real ni sale a internet: todo lo que responde Microsoft
está simulado.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, time, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.correo_nube import CorreoNube, ErrorCorreo, CLIENTE_PUBLICO

# Configuración de usar y tirar, en la carpeta temporal (no ensucia el proyecto).
CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_correo.json")
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


def preparar_config(datos):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4)


def _iso(dias_atras, hora=14):
    """Fecha ISO en UTC equivalente a esa hora local de 'hace N días'."""
    dia = datetime.now().astimezone().date() - timedelta(days=dias_atras)
    return datetime.combine(dia, time(hora, 0)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# El correo 1 es de hoy (para poder probar el filtro 'hoy' cualquier día)
FECHA_HOY = _iso(0)[:10]

MENSAJES = [
    {"id": "m1", "subject": "Factura de octubre", "isRead": False,
     "receivedDateTime": _iso(0),
     "from": {"emailAddress": {"name": "Ana Pérez", "address": "ana@acme.com"}},
     "bodyPreview": "Adjunto la factura del mes; queda pendiente de aprobación."},
    {"id": "m2", "subject": "Reunión de proyecto", "isRead": True,
     "receivedDateTime": _iso(2, 9),
     "from": {"emailAddress": {"address": "luis@acme.com"}},
     "bodyPreview": "Te confirmo la reunión del jueves."},
    {"id": "m3", "subject": "Recordatorio de vacaciones", "isRead": True,
     "receivedDateTime": _iso(9, 8),
     "from": {"emailAddress": {"name": "RRHH", "address": "rrhh@acme.com"}},
     "bodyPreview": "Recuerda solicitar tus vacaciones antes de fin de mes."},
]

DETALLE = {
    "m1": {"id": "m1", "subject": "Factura de octubre", "isRead": False,
           "receivedDateTime": _iso(0), "categories": ["Propuesta", "Otro"],
           "from": {"emailAddress": {"name": "Ana Pérez", "address": "ana@acme.com"}},
           "bodyPreview": "Adjunto la factura",
           "body": {"contentType": "html",
                    "content": "<p>Hola,</p><p>Adjunto la <b>factura</b>.</p><p>Gracias</p>"}},
    "m2": {"id": "m2", "subject": "Reunión de proyecto", "isRead": True,
           "receivedDateTime": _iso(2, 9), "categories": [],
           "from": {"emailAddress": {"address": "luis@acme.com"}},
           "bodyPreview": "Te confirmo la reunión",
           "body": {"contentType": "text", "content": "Te confirmo la reunión del jueves."}},
}


class GrafoFalso:
    """Simula Microsoft Graph y anota todo lo que se le pide."""

    def __init__(self):
        self.llamadas = []
        self.borradores = [{"id": "b1", "subject": "Respuesta factura",
                            "toRecipients": [{"emailAddress": {"address": "ana@acme.com"}}]},
                           {"id": "b2", "subject": "Otro borrador",
                            "toRecipients": []}]
        self.carpetas = [{"id": "c1", "displayName": "Archivo", "childFolderCount": 1},
                         {"id": "c2", "displayName": "Proyectos", "childFolderCount": 0}]
        self.error = None

    def filtro(self, metodo, ruta, exacto=False):
        """Llamadas registradas que coinciden (por ruta exacta o por contenido)."""
        return [l for l in self.llamadas
                if l[0] == metodo and (l[1] == ruta if exacto else ruta in l[1])]

    def __call__(self, metodo, ruta, json_cuerpo=None, params=None, reintentar=True):
        self.llamadas.append((metodo, ruta, json_cuerpo, params))
        if self.error:
            raise ErrorCorreo(self.error)
        if ruta == "/me":
            return {"mail": "neydermanrique@cbit-online.com", "displayName": "Neyder"}
        if ruta.endswith("/mailFolders/inbox/messages"):
            return {"value": MENSAJES}
        if ruta.endswith("/mailFolders/drafts/messages"):
            return {"value": self.borradores}
        if ruta == "/me/mailFolders":
            return {"value": self.carpetas}
        if ruta.endswith("/childFolders"):
            return {"value": [{"id": "c11", "displayName": "2026"}]}
        if ruta == "/me/messages" and metodo == "POST":
            return {"id": "nuevo-1", "subject": (json_cuerpo or {}).get("subject")}
        if ruta.endswith("/createReply"):
            return {"id": "borrador-1"}
        if ruta.endswith("/send") or ruta.endswith("/move"):
            return {}
        if metodo == "DELETE":
            return {}
        if metodo == "PATCH":
            return {}
        identificador = ruta.rsplit("/", 1)[-1]
        if identificador == "borrador-1":
            return {"body": {"contentType": "html", "content": "<div>citado</div>"}}
        if identificador == "nuevo-1":
            return {"id": "nuevo-1", "toRecipients": [], "subject": "Asunto de prueba"}
        for borrador in self.borradores:
            if borrador["id"] == identificador:
                return borrador
        if identificador in DETALLE:
            return DETALLE[identificador]
        raise ErrorCorreo("El correo ya no existe", 404)


def cliente_con_grafo():
    """Cliente con sesión 'iniciada' y Graph simulado."""
    preparar_config({"api_key": "secreto", "nombre_asistente": "jarvis",
                     "correo": {"token": "refresco-falso", "cifrado": False,
                                "cliente_id": CLIENTE_PUBLICO}})
    cliente = CorreoNube(CONFIG)
    grafo = GrafoFalso()
    cliente._graph = grafo
    cliente._token_valido = lambda: "token-falso"
    return cliente, grafo


def pruebas_basicas():
    print("\n== Cifrado y configuración ==")
    cifrado = CorreoNube._cifrar("refresco-secreto")
    comprobar(bool(cifrado) and cifrado != "refresco-secreto", "el token se cifra con DPAPI")
    comprobar(CorreoNube._descifrar(cifrado) == "refresco-secreto", "el token se descifra bien")
    comprobar(CorreoNube._descifrar("no-es-base64") == "", "un token ilegible no rompe nada")

    preparar_config({"api_key": "secreto", "programas": ["brave"],
                     "correo": {"token": "t", "cifrado": False}})
    cliente = CorreoNube(CONFIG)
    comprobar(cliente.disponible() is True, "disponible() con token guardado")
    cliente._guardar_ajustes({"cuenta": "quien@sea.com"})
    with open(CONFIG, "r", encoding="utf-8") as f:
        guardado = json.load(f)
    comprobar(guardado.get("api_key") == "secreto", "no se pierde la api_key al guardar")
    comprobar(guardado.get("programas") == ["brave"], "no se pierden otras claves")
    comprobar(guardado["correo"]["cuenta"] == "quien@sea.com", "se guarda la cuenta")
    comprobar(guardado["correo"]["cliente_id"] == CLIENTE_PUBLICO, "cliente por defecto")
    comprobar(CorreoNube(CONFIG).disponible() is True, "otra instancia ve la sesión")

    preparar_config({"api_key": "secreto"})
    comprobar(CorreoNube(CONFIG).disponible() is False, "sin token no está disponible")
    cliente2 = CorreoNube(CONFIG)
    cliente2._token_valido = lambda: "x"
    cliente2._graph = GrafoFalso()
    comprobar(cliente2.listar() is None, "listar() devuelve None sin sesión")
    comprobar("no he conectado" in cliente2.leer_correos(), "mensaje claro sin sesión")
    comprobar("no he conectado" in cliente2.detalle("1"), "detalle avisa sin sesión")
    comprobar(cliente2.crear_borrador("a@b.com", "x", "y").startswith("Todavía"),
              "crear_borrador avisa sin sesión")
    comprobar("no he conectado" in cliente2.etiquetar("1", "X"), "etiquetar avisa sin sesión")


def pruebas_listado():
    print("\n== Listar, resumir y buscar ==")
    cliente, grafo = cliente_con_grafo()
    texto = cliente.leer_correos(3)
    comprobar("Tus últimos 3 correos:" in texto, "cabecera del listado")
    comprobar("Ana Pérez" in texto and "Factura de octubre" in texto,
              "primer correo con remitente y asunto")
    comprobar("[NO LEÍDO]" in texto, "marca los no leídos")
    comprobar(FECHA_HOY in texto, "fecha formateada (día local de hoy)")
    comprobar(len(cliente._ultimo_listado) == 3, "se recuerdan los 3 correos")
    comprobar(grafo.filtro("GET", "inbox/messages")[0][3]["$top"] == cliente.LIMITE_BARRIDO,
              "se pide la ventana de barrido")

    comprobar("sin leer (1)" in cliente.resumen("no leídos"), "filtro de no leídos")
    comprobar("de hoy (1)" in cliente.resumen("hoy"), "filtro de hoy")
    comprobar("recientes (2)" in cliente.resumen("2"), "resumen con número")
    comprobar(len(cliente._ultimo_listado) == 2, "resumen('2') respeta el número")
    comprobar("Correos recientes (3)" in cliente.resumen(""), "resumen sin criterio")

    comprobar("Factura" in cliente.buscar("factura"), "buscar por asunto")
    comprobar("Ana" in cliente.buscar("ana"), "buscar por remitente")
    comprobar("vacaciones" in cliente.buscar("vacaciones"), "buscar por extracto")
    comprobar("No encontré" in cliente.buscar("hipoteca"), "buscar sin resultados")
    comprobar(cliente.buscar("") == "¿Qué quieres que busque en el correo?",
              "buscar sin término")

    print("\n== Leer un correo completo ==")
    cliente.leer_correos(3)
    detalle = cliente.detalle("1")
    comprobar(detalle.startswith("De Ana Pérez"), "detalle con remitente")
    comprobar("Asunto: Factura de octubre" in detalle, "detalle con asunto")
    comprobar("factura" in detalle and "<p>" not in detalle and "<b>" not in detalle,
              "el HTML se convierte en texto")
    comprobar(cliente.detalle("2").startswith("De luis@acme.com"),
              "detalle con remitente sin nombre (usa la dirección)")
    comprobar("Ana" in cliente.detalle("ana pérez"), "detalle por texto del remitente")
    comprobar("no había un correo número 99" in cliente.detalle("99"),
              "detalle con número inexistente")
    comprobar("¿A qué correo te refieres?" in cliente.detalle(""), "detalle sin clave")
    comprobar("No encontré ningún correo" in cliente.detalle("hipoteca"),
              "detalle con texto inexistente")


def pruebas_escribir():
    print("\n== Responder y borradores ==")
    cliente, grafo = cliente_con_grafo()
    cliente.leer_correos(3)
    respuesta = cliente.responder("1", "Gracias, lo reviso.\nQuedo atento.")
    comprobar("Borradores" in respuesta and "Ana Pérez" in respuesta,
              "la respuesta queda en Borradores")
    cuerpo_enviado = grafo.filtro("PATCH", "/me/messages/borrador-1")[0][2]["body"]["content"]
    comprobar("<p>Gracias, lo reviso.</p><p>Quedo atento.</p>" in cuerpo_enviado,
              "el texto va encima y con saltos de línea")
    comprobar(cuerpo_enviado.endswith("<div>citado</div>"),
              "se conserva el correo original citado")
    comprobar(cliente._ultimo_borrador == "borrador-1", "se recuerda el borrador")
    comprobar(cliente.responder("1", "   ") == "No me diste el texto de la respuesta.",
              "respuesta sin texto")
    comprobar("no había un correo número 77" in cliente.responder("77", "hola"),
              "responder a un número inexistente")
    enviada = cliente.responder("1", "Confirmado.", enviar=True)
    comprobar(enviada.startswith("Respuesta enviada a Ana Pérez"),
              "responder con enviar=True manda el correo")
    comprobar(bool(grafo.filtro("POST", "/me/messages/borrador-1/send")),
              "se llamó a /send")

    nuevo = cliente.crear_borrador("ana@acme.com; Luis <luis@acme.com>", "Asunto de prueba",
                                   "Hola:\n\nAdjunto lo que pediste.")
    comprobar(nuevo.startswith("Borrador creado"), "contrato 'Borrador creado'")
    peticion = grafo.filtro("POST", "/me/messages", exacto=True)[0][2]
    comprobar([d["emailAddress"]["address"] for d in peticion["toRecipients"]]
              == ["ana@acme.com", "luis@acme.com"], "se separan los destinatarios")
    comprobar(peticion["body"]["content"].count("<p>") == 3,
              "el cuerpo se convierte en párrafos")
    comprobar(cliente._ultimo_borrador == "nuevo-1", "se recuerda el borrador nuevo")
    comprobar(cliente.crear_borrador("", "x", "y") == "¿A quién le mando el correo? "
              "Dime el destinatario.", "crear_borrador sin destinatario")
    comprobar("no parece una dirección" in cliente.crear_borrador("sin arroba", "x", "y"),
              "crear_borrador con destinatario inválido")

    print("\n== Enviar el borrador ==")
    salida = cliente.enviar_borrador()
    comprobar(salida.startswith("Borrador enviado: 'Asunto de prueba'"),
              "envía el último borrador preparado")
    comprobar(cliente._ultimo_borrador == "", "se olvida el borrador enviado")
    grafo.borradores = [{"id": "b1", "subject": "Respuesta factura", "toRecipients": []},
                        {"id": "b2", "subject": "Otro borrador", "toRecipients": []}]
    comprobar("Otro borrador" in cliente.enviar_borrador("2"),
              "se puede elegir el borrador por número")
    comprobar("Respuesta factura" in cliente.enviar_borrador("factura"),
              "se puede elegir el borrador por asunto")
    grafo.borradores = []
    comprobar("No encontré ese borrador" in cliente.enviar_borrador(),
              "sin borradores avisa")

    print("\n== Organizar: etiquetas, carpetas, leído y borrado ==")
    cliente, grafo = cliente_con_grafo()
    cliente.leer_correos(3)
    etiquetado = cliente.etiquetar("1", "Propuesta")
    comprobar("ahora tiene: Propuesta, Otro" in etiquetado, "añade la etiqueta")
    comprobar(grafo.filtro("PATCH", "/me/messages/m1")[0][2]["categories"]
              == ["Propuesta", "Otro"], "respeta las categorías existentes")
    comprobar("Etiqueta quitada" in cliente.etiquetar("1", "-Otro"), "quita la etiqueta")
    comprobar(cliente.etiquetar("1", "") == "¿Con qué etiqueta quieres marcar el correo?",
              "etiqueta vacía")
    comprobar("carpeta Archivo" in cliente.archivar("1"),
              "archiva en la carpeta Archivo del buzón")
    comprobar(grafo.filtro("POST", "/me/messages/m1/move")[0][2]["destinationId"] == "c1",
              "el destino es la carpeta encontrada")
    comprobar("carpeta Proyectos" in cliente.archivar("1", "proyectos"),
              "archivar en una carpeta concreta (sin acentos)")
    comprobar("No encontré la carpeta 'Volantes'" in cliente.archivar("1", "Volantes"),
              "carpeta inexistente avisa")
    comprobar("carpeta Archivo" in cliente.archivar("1"),
              "sin carpeta usa el archivo estándar")
    comprobar("marcado como no leído" in cliente.marcar("1", False), "marcar no leído")
    comprobar(grafo.filtro("PATCH", "/me/messages/m1")[-1][2]["isRead"] is False,
              "se envía isRead=False")
    comprobar("marcado como leído" in cliente.marcar("1"), "marcar leído")
    comprobar("Elementos eliminados" in cliente.eliminar("1"), "eliminar mueve a papelera")
    comprobar(bool(grafo.filtro("DELETE", "/me/messages/m1")), "se llamó a DELETE")


def pruebas_conectar():
    print("\n== Conectar con el código de dispositivo ==")
    preparar_config({"api_key": "x"})
    cliente = CorreoNube(CONFIG)
    estado = {"token": 0}

    def pedir_json(url, metodo="POST", form=None, json_cuerpo=None, cabeceras=None):
        if "devicecode" in url:
            return {"user_code": "ABCD-1234", "device_code": "dc", "interval": 1,
                    "expires_in": 900,
                    "verification_uri": "https://microsoft.com/devicelogin"}
        if url.endswith("/token"):
            if (form or {}).get("grant_type") == "device_code":
                estado["token"] += 1
                if estado["token"] == 1:
                    raise ErrorCorreo("authorization_pending")
                return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        raise ErrorCorreo("ruta no esperada")

    cliente._pedir_json = pedir_json
    cliente.cuenta = lambda: "neydermanrique@cbit-online.com"
    avisos = []
    ok, texto = cliente.entrar(avisar=avisos.append, tiempo_max=30)
    comprobar(ok is True, "entrar() termina bien")
    comprobar("ABCD-1234" in " ".join(avisos), "se enseña el código al usuario")
    comprobar("neydermanrique@cbit-online.com" in texto, "dice la cuenta conectada")
    with open(CONFIG, "r", encoding="utf-8") as f:
        guardado = json.load(f)
    comprobar(guardado["correo"]["token"] != "rt", "el refresh token no se guarda en claro")
    comprobar(guardado["correo"]["cifrado"] is True, "el token queda cifrado")
    comprobar(CorreoNube(CONFIG)._token_guardado() == "rt", "se descifra al usarlo")
    comprobar(CorreoNube(CONFIG).disponible() is True, "queda disponible para el asistente")
    _ok, salida = cliente.salir()
    comprobar(CorreoNube(CONFIG).disponible() is False, "salir() borra la sesión")
    comprobar("olvidé la sesión" in salida, "salir() lo explica")


def pruebas_error():
    print("\n== Errores de conexión ==")
    cliente, grafo = cliente_con_grafo()
    cliente.leer_correos(3)                 # deja preparado el listado
    grafo.error = "La sesión caducó"
    comprobar("No pude hablar con tu correo: La sesión caducó" in cliente.leer_correos(),
              "un error de Graph se explica al usuario")
    comprobar(cliente.etiquetar("1", "X").startswith("No pude"),
              "etiquetar avisa del error de conexión (no de 'ya no está')")
    comprobar(cliente.resumen("hoy").startswith("No pude"), "resumen avisa del error")
    comprobar(cliente.buscar("x").startswith("No pude"), "buscar avisa del error")
    comprobar(cliente.marcar("1").startswith("No pude"), "marcar avisa del error")
    comprobar(cliente.eliminar("1").startswith("No pude"), "eliminar avisa del error")
    comprobar(cliente.archivar("1").startswith("No pude"), "archivar avisa del error")
    grafo.error = None
    DETALLE.pop("m3", None)                 # el correo 3 ya no existe (404 real)
    cliente.leer_correos(3)
    comprobar("ya no está en el buzón" in cliente.detalle("3"),
              "un 404 real dice que el correo ya no está")


def pruebas_utilidades():
    print("\n== Utilidades ==")
    texto = CorreoNube._html_a_texto(
        "<div><p>Hola   mundo</p><br><ul><li>uno</li><li>dos</li></ul></div>")
    comprobar("Hola mundo" in texto and "- uno" in texto and "<" not in texto,
              "HTML -> texto (párrafos y listas)")
    comprobar(CorreoNube._html_a_texto(
        "<script>malo()</script><style>x{}</style><p>bueno</p>").strip() == "bueno",
        "se descartan scripts y estilos")
    comprobar(CorreoNube._texto_a_html("a & b\nc") == "<p>a &amp; b</p><p>c</p>",
              "texto -> HTML con escapado")
    comprobar(CorreoNube._direcciones("A <a@b.com>, c@d.com; e@f.com")
              == ["a@b.com", "c@d.com", "e@f.com"], "se leen los destinatarios")
    momento = datetime.fromisoformat("2026-10-09T20:31:00+00:00")
    comprobar(CorreoNube._fecha("2026-10-09T20:31:00Z")
              == momento.astimezone().strftime("%Y-%m-%d %H:%M"),
              "fecha ISO de Graph -> local")
    comprobar(CorreoNube._fecha("").startswith("sin fecha"), "fecha vacía")
    comprobar(CorreoNube._sin_acentos("AñO") == "ano", "sin acentos")
    comprobar(CorreoNube._limpiar("uno    dos", 100) == "uno dos", "se colapsan espacios")
    comprobar(CorreoNube._limpiar("x" * 30, 10).endswith("..."), "se recorta el extracto")
    comprobar(CorreoNube()._cliente_id() == CLIENTE_PUBLICO, "cliente por defecto")


def pruebas_sesion_compartida():
    print("\n== El asistente abierto se entera de la conexión ==")
    ruta = os.path.join(tempfile.gettempdir(), "jarvis_prueba_correo_compartida.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"correo": {"token": ""}}, f)
    # `abre_y_conecta` hace de consola/Ajustes; `asistente_abierto` simula la app
    # que ya estaba en marcha (leyó la configuración antes de conectar).
    abre_y_conecta = CorreoNube(ruta)
    asistente_abierto = CorreoNube(ruta)
    comprobar(asistente_abierto.disponible() is False, "al principio no hay sesión")
    abre_y_conecta._guardar_ajustes({"token": "t-de-prueba", "cuenta": "yo@acme.com"})
    comprobar(asistente_abierto.disponible() is True,
              "un asistente ya abierto ve la sesión al momento")
    comprobar(asistente_abierto.ajustes().get("cuenta") == "yo@acme.com",
              "y también la cuenta conectada")
    comprobar(asistente_abierto._token_guardado() == "t-de-prueba",
              "y el token guardado")
    asistente_abierto.salir()
    comprobar(abre_y_conecta.disponible() is False,
              "al desconectar, la otra instancia también lo ve")
    os.remove(ruta)


def pruebas_cli():
    print("\n== Consola del módulo ==")
    from modules.correo_nube import main as cli_correo
    comprobar(cli_correo(["ayuda"]) == 0, "la ayuda de la consola funciona")


def main_pruebas():
    pruebas_basicas()
    pruebas_listado()
    pruebas_escribir()
    pruebas_conectar()
    pruebas_error()
    pruebas_utilidades()
    pruebas_sesion_compartida()
    pruebas_cli()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    try:
        codigo = main_pruebas()
    finally:
        if os.path.exists(CONFIG):
            os.remove(CONFIG)
    raise SystemExit(codigo)

