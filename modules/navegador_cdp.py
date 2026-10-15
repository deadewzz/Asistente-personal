"""Control de Brave por Chrome DevTools Protocol (CDP).

¿Por qué NO leemos las cookies de Brave? Porque Brave moderno las cifra con
**App-Bound Encryption** (prefijo ``v20``), que por diseño *ningún* proceso
externo puede descifrar. Comprobado en este equipo: ``app_bound_encrypted_key``
está presente y las cookies de SharePoint son ``v20`` -> la lectura por DPAPI
fallaba y SharePoint devolvía 401.

La forma fiable de reutilizar la sesión que el usuario ya tiene abierta es
dejar que el **propio navegador** haga las peticiones: abrimos/adjuntamos Brave
con ``--remote-debugging-port`` y ejecutamos ``fetch()`` con
``credentials:'include'`` dentro de una pestaña del sitio. El navegador añade
las cookies y firma solo, así que no hace falta descifrar nada.

Todo es local (127.0.0.1) y el puerto de depuración desaparece al cerrar Brave.
"""

import asyncio
import itertools
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None


PUERTO = 9222
BASE = f"http://127.0.0.1:{PUERTO}"

RUTAS_BRAVE = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
]

SIN_VENTANA = 0x08000000  # CREATE_NO_WINDOW


class ErrorNavegador(Exception):
    """No se pudo controlar Brave (no está, no abrió la depuración, etc.)."""


def ruta_brave():
    """Ruta de brave.exe, o cadena vacía si no está instalado."""
    for ruta in RUTAS_BRAVE:
        if os.path.exists(ruta):
            return ruta
    return ""


def _http_json(ruta, metodo="GET", tiempo=5):
    peticion = urllib.request.Request(BASE + ruta, method=metodo)
    with urllib.request.urlopen(peticion, timeout=tiempo) as respuesta:
        return json.loads(respuesta.read().decode("utf-8", "replace"))


def esta_activo():
    """True si hay un Brave escuchando en el puerto de depuración."""
    try:
        _http_json("/json/version")
        return True
    except Exception:
        return False


def brave_en_ejecucion():
    """True si hay algún proceso brave.exe abierto (con o sin depuración)."""
    try:
        import psutil
    except ImportError:
        return False
    for proceso in psutil.process_iter(["name"]):
        if (proceso.info.get("name") or "").lower() == "brave.exe":
            return True
    return False


def lanzar(url="about:blank", espera=30):
    """Abre Brave con el puerto de depuración y espera a que responda."""
    ejecutable = ruta_brave()
    if not ejecutable:
        raise ErrorNavegador("No encuentro brave.exe (¿está instalado Brave?).")
    argumentos = [ejecutable, f"--remote-debugging-port={PUERTO}"]
    if url:
        argumentos.append(url)
    subprocess.Popen(argumentos, close_fds=True)
    limite = time.time() + espera
    while time.time() < limite:
        if esta_activo():
            return True
        time.sleep(0.4)
    raise ErrorNavegador(
        "Brave no abrió el puerto de depuración. Si ya lo tenías abierto, "
        "ciérralo del todo y vuelve a intentarlo.")


def cerrar(espera=15):
    """Cierra Brave con elegancia (guarda la sesión) y espera a que termine."""
    subprocess.run(["taskkill", "/IM", "brave.exe"], capture_output=True,
                   creationflags=SIN_VENTANA)
    limite = time.time() + espera
    while time.time() < limite:
        if not brave_en_ejecucion():
            return True
        time.sleep(0.5)
    return False


def asegurar(url="about:blank", reiniciar=True):
    """Garantiza que Brave está abierto con depuración. Devuelve una nota."""
    if esta_activo():
        return "Brave ya estaba abierto con depuración."
    if brave_en_ejecucion():
        if not reiniciar:
            raise ErrorNavegador(
                "Brave está abierto sin depuración. Ciérralo y vuelve a "
                "pedírmelo (lo abriré con acceso para leer tu sesión).")
        if not cerrar():
            raise ErrorNavegador(
                "No conseguí cerrar Brave (¿pestañas sin guardar?). Ciérralo tú "
                "y vuelve a pedírmelo.")
        lanzar(url)
        return "Reinicié Brave (con depuración) para poder leer tu sesión."
    lanzar(url)
    return "Abrí Brave (con depuración) para leer tu sesión."


async def _evaluar_async(ws_url, expresion, navegar, timeout):
    """Conecta al objetivo por WebSocket y evalúa una expresión JavaScript."""
    if aiohttp is None:
        raise ErrorNavegador("Falta aiohttp (necesario para hablar con Brave).")
    contador = itertools.count(1)
    async with aiohttp.ClientSession() as sesion:
        async with sesion.ws_connect(ws_url, max_msg_size=0) as ws:
            async def orden(metodo, **params):
                ident = next(contador)
                await ws.send_json({"id": ident, "method": metodo,
                                    "params": params})
                while True:
                    mensaje = await ws.receive()
                    if mensaje.type == aiohttp.WSMsgType.TEXT:
                        datos = json.loads(mensaje.data)
                        if datos.get("id") == ident:
                            if "error" in datos:
                                raise ErrorNavegador(
                                    f"CDP {metodo}: {datos['error']}")
                            return datos.get("result", {})
                    elif mensaje.type in (aiohttp.WSMsgType.CLOSED,
                                          aiohttp.WSMsgType.CLOSE,
                                          aiohttp.WSMsgType.ERROR):
                        raise ErrorNavegador("Se perdió la conexión con Brave.")

            await orden("Runtime.enable")
            if navegar:
                await orden("Page.enable")
                await orden("Page.navigate", url=navegar)
                host = urllib.parse.urlparse(navegar).netloc
                condicion = ("document.readyState !== 'loading' && "
                             f"location.host.indexOf({json.dumps(host)}) !== -1")
                limite = time.time() + timeout
                while time.time() < limite:
                    listo = await orden("Runtime.evaluate", expression=condicion,
                                        returnByValue=True)
                    if listo.get("result", {}).get("value") is True:
                        break
                    await asyncio.sleep(0.3)
            resultado = await orden("Runtime.evaluate", expression=expresion,
                                    awaitPromise=True, returnByValue=True)
            if resultado.get("exceptionDetails"):
                raise ErrorNavegador("La página devolvió un error: "
                                     + str(resultado["exceptionDetails"])[:300])
            return resultado.get("result", {}).get("value")


class Pestana:
    """Pestaña de Brave por CDP (se reutiliza para varias llamadas)."""

    def __init__(self, url=None, timeout=40):
        self.url = url
        self.timeout = timeout
        self.id = None
        self.ws_url = None

    def abrir(self):
        objetivo = _nuevo_objetivo()
        self.id = objetivo.get("id")
        self.ws_url = objetivo.get("webSocketDebuggerUrl")
        if not self.ws_url:
            raise ErrorNavegador("Brave no me dio una pestaña utilizable.")
        if self.url:
            self.evaluar("void 0", navegar=self.url)
        return self

    def evaluar(self, expresion, navegar=None):
        return asyncio.run(
            _evaluar_async(self.ws_url, expresion, navegar, self.timeout))

    def cerrar(self):
        if not self.id:
            return
        try:
            _http_json(f"/json/close/{self.id}")
        except Exception:
            pass
        self.id = None


def _nuevo_objetivo():
    """Crea una pestaña nueva (algunos Chromium exigen PUT)."""
    try:
        return _http_json("/json/new", "PUT")
    except Exception:
        return _http_json("/json/new", "GET")
