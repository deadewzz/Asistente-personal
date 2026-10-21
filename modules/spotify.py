"""Música en Spotify por la API oficial (Web API + OAuth2 con PKCE).

Por qué existe esto: Jarvis tiene que poder poner una canción **de verdad** sin
tocar el teclado, sin abrir ventanas y sin robarle el foco a lo que estés haciendo
(por ejemplo, una partida). Eso solo lo consigue hablándole a Spotify por su API:
se resuelve la pista exacta (título, artista, `uri`), se le manda reproducir al
dispositivo que toca y después se **comprueba** con `GET /me/player` que está
sonando. Nada de ventanas y nada de teclas a ciegas.

Se conecta una sola vez (`python -m modules.spotify entrar`, o el botón «Conectar
Spotify» de Ajustes): se pega el *Client ID* de una aplicación gratuita del panel de
Spotify y se autoriza en el navegador. El *refresh token* se guarda **cifrado con
DPAPI** (solo tu usuario de Windows puede descifrarlo) en `config_usuario.json`,
igual que el del correo.

    python -m modules.spotify entrar        # conectar la cuenta (una sola vez)
    python -m modules.spotify probar        # quién eres, dispositivos y qué suena
    python -m modules.spotify dispositivos  # altavoces y equipos disponibles
    python -m modules.spotify poner "Junior H Las noches"   # poner una canción
    python -m modules.spotify salir         # olvidar la sesión guardada

Ojo: la reproducción por API es cosa de **Spotify Premium** (es una regla de
Spotify, no de Jarvis). Si la cuenta no lo es, este módulo lo dice claro y quien
llame decide: Jarvis sigue con el camino de siempre (dejar la pista cargada).
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from modules import rutas

CUENTAS = "https://accounts.spotify.com"
API = "https://api.spotify.com/v1"
#: Vuelta de la autorización. Spotify solo admite direcciones seguras o de bucle
#: local, y la propia documentación pone `http://127.0.0.1:puerto` como ejemplo. Se
#: registra tal cual en el panel de la aplicación y se puede cambiar aquí (y en el
#: panel) si ese puerto estuviera ocupado.
REDIRECCION = "http://127.0.0.1:8888/callback"
#: Permisos mínimos: saber quién eres (para ver si hay Premium), lo que suena y
#: mandar reproducir. Nada de la biblioteca del usuario ni de sus listas.
PERMISOS = "user-read-private user-read-playback-state user-modify-playback-state"


class ErrorSpotify(Exception):
    """Error de Spotify ya traducido a algo que se puede contar y arreglar."""

    def __init__(self, mensaje, estado=0):
        super().__init__(mensaje)
        self.mensaje = str(mensaje)
        self.estado = int(estado or 0)


class Spotify:
    """Sesión de Spotify del usuario (una sola) y control de la reproducción."""

    CUENTAS = CUENTAS
    API = API
    REDIRECCION = REDIRECCION
    PERMISOS = PERMISOS

    ESPERA_RED = 15          # segundos de paciencia por petición
    ESPERA_SONANDO = 12      # a que Spotify confirme que esa canción suena
    ESPERA_MANDO = 8         # a que confirme una pausa, un salto o una vuelta
    PUERTO_ESCUCHA = 8888    # puerto local donde vuelve la autorización

    #: Explicaciones propias de los errores que más se ven, por el motivo que manda
    #: Spotify (`reason`) o por el texto. Se prefieren a la explicación genérica.
    AYUDAS_ERROR = {
        "invalid_client": ("El Client ID no vale: copia otra vez el que enseña el "
                           "panel de Spotify en «Configurar Spotify»."),
        "invalid_grant": ("La autorización de Spotify ya no vale: hay que volver a "
                          "conectar la cuenta."),
        "PREMIUM_REQUIRED": ("Controlar la reproducción desde el asistente necesita "
                             "Spotify Premium (es una regla de Spotify)."),
        "NO_ACTIVE_DEVICE": ("No hay ningún dispositivo de Spotify activo: abre "
                             "Spotify en el PC y lo intento otra vez."),
        "RESTRICTION_VIOLATED": ("Spotify no deja mandar eso ahora en ese "
                                 "dispositivo (lo marca como restringido)."),
        "Device not found": "Ese dispositivo de Spotify ya no está disponible.",
    }

    #: Los códigos de HTTP se explican solos cuando Spotify no manda un motivo claro.
    AYUDAS_CODIGO = {
        400: "Spotify no entendió la petición.",
        401: "Spotify me ha pedido que renueve la sesión.",
        403: "Spotify no deja hacer eso (suele ser la cuenta: hace falta Premium).",
        404: "No hay ningún dispositivo de Spotify activo.",
        429: "Spotify me pide esperar un momento (demasiadas peticiones seguidas).",
        500: "Spotify está fallando ahora mismo.",
        502: "Spotify está fallando ahora mismo.",
        503: "Spotify está de mantenimiento.",
    }
    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self._config = {}
        self._token = ""         # access token en memoria (una hora de vida)
        self._token_expira = 0.0

    # ------------------------------------------------------------ Configuración
    def _leer_config(self):
        """Lee config_usuario.json (dict vacío si todavía no existe)."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def _guardar_config(self, datos):
        carpeta = os.path.dirname(self.config_path)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4)
        self._config = datos

    def ajustes(self):
        """Sección 'spotify' de la configuración (dict vacío si no hay ninguna).

        Se relee del archivo para que un asistente ya abierto se entere de una
        conexión hecha después (por ejemplo desde Ajustes o desde la consola).
        """
        config = self._leer_config()
        if config or not self._config:
            self._config = config
        seccion = self._config.get("spotify")
        return dict(seccion) if isinstance(seccion, dict) else {}

    def _guardar_ajustes(self, cambios):
        """Actualiza la sección 'spotify' sin tocar el resto de la configuración."""
        config = self._leer_config()
        seccion = config.get("spotify")
        if not isinstance(seccion, dict):
            seccion = {}
        seccion.update(cambios)
        config["spotify"] = seccion
        self._guardar_config(config)
        return seccion

    def cliente_id(self):
        """Client ID de la aplicación de Spotify del usuario ('' si no hay)."""
        return str(self.ajustes().get("cliente_id") or "").strip()

    def redireccion(self):
        """Dirección de vuelta de la autorización (la que se registra en el panel)."""
        return (str(self.ajustes().get("redireccion") or "").strip()
                or self.REDIRECCION)

    def disponible(self):
        """True si ya se conectó la cuenta alguna vez (hay token guardado)."""
        return bool(self.ajustes().get("token"))

    def cuenta(self):
        """Nombre de la cuenta conectada ('' si no se sabe todavía)."""
        return str(self.ajustes().get("cuenta") or "").strip()

    def premium(self):
        """True si la cuenta es Premium (sin Premium Spotify no deja controlar nada)."""
        return bool(self.ajustes().get("premium"))

    # ------------------------------------------------------------ Cifrado (DPAPI)
    @staticmethod
    def _cifrar(texto):
        """Cifra un texto con DPAPI. Devuelve '' si no se puede cifrar."""
        try:
            import win32crypt
            blob = win32crypt.CryptProtectData(str(texto).encode("utf-8"),
                                               "jarvis-spotify", None, None, None, 0)
            if isinstance(blob, tuple):
                blob = blob[0]
            return base64.b64encode(blob).decode("ascii")
        except Exception as e:
            print(f"[spotify] No pude cifrar el token de sesión: {e}")
            return ""

    @staticmethod
    def _descifrar(valor):
        """Descifra un texto guardado con `_cifrar`. Devuelve '' si no se puede."""
        if not valor:
            return ""
        try:
            import win32crypt
            datos = win32crypt.CryptUnprotectData(base64.b64decode(valor),
                                                  None, None, None, 0)
            if isinstance(datos, tuple):
                datos = datos[1]
            return datos.decode("utf-8")
        except Exception:
            return ""

    def _token_guardado(self):
        """Refresh token guardado (descifrado si hace falta)."""
        seccion = self.ajustes()
        valor = seccion.get("token") or ""
        if not valor:
            return ""
        if seccion.get("cifrado", True):
            return self._descifrar(valor) or ""
        return str(valor)

    def _guardar_token(self, refresco):
        """Guarda el refresh token (cifrado con DPAPI, como el del correo)."""
        cifrado = self._cifrar(refresco)
        if cifrado:
            self._guardar_ajustes({"token": cifrado, "cifrado": True})
            return
        print("[spotify] Sin DPAPI: guardo el token sin cifrar.")
        self._guardar_ajustes({"token": refresco, "cifrado": False})
    # -------------------------------------------------- Conectar (OAuth2 + PKCE)
    @staticmethod
    def _desafio(verificador):
        """Reto PKCE (S256): con esto el secreto no viaja hasta el último paso."""
        resumen = hashlib.sha256(str(verificador).encode("ascii")).digest()
        return base64.urlsafe_b64encode(resumen).decode("ascii").rstrip("=")

    def _url_autorizacion(self, desafio, estado, cliente_id=None):
        """Enlace que se abre en el navegador para autorizar a Jarvis."""
        parametros = {
            "client_id": cliente_id or self.cliente_id(),
            "response_type": "code",
            "redirect_uri": self.redireccion(),
            "scope": self.PERMISOS,
            "code_challenge": desafio,
            "code_challenge_method": "S256",
            "state": estado,
        }
        return self.CUENTAS + "/authorize?" + urllib.parse.urlencode(parametros)

    @staticmethod
    def _abrir_navegador(url):
        """Abre el navegador del sistema (solo al conectar, una única vez)."""
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[spotify] No pude abrir el navegador ({e}).")

    def _esperar_codigo(self, estado, tiempo_max=300):
        """Espera la vuelta de la autorización: (código, error).

        Se levanta un servidor de un solo uso en 127.0.0.1 (el navegador vuelve ahí
        con el código) y se comprueba el `state` para no aceptar una respuesta que
        no sea la de esta conexión.
        """
        resultado = {"codigo": "", "error": ""}
        listo = threading.Event()
        puerto = urllib.parse.urlparse(self.redireccion()).port or self.PUERTO_ESCUCHA

        class Manejador(http.server.BaseHTTPRequestHandler):
            def log_message(self, *resto):
                pass                      # sin ruido en la consola

            def do_GET(self):
                datos = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if (datos.get("state") or [""])[0] != estado:
                    resultado["error"] = ("La respuesta no venía de Spotify: no "
                                          "conecto nada por seguridad.")
                elif datos.get("error"):
                    resultado["error"] = ("No has autorizado la conexión con Spotify "
                                          f"({(datos.get('error') or [''])[0]}).")
                else:
                    resultado["codigo"] = (datos.get("code") or [""])[0]
                self._responder()
                listo.set()

            def _responder(self):
                cuerpo = ("<html><body style='font-family:sans-serif;padding:40px;"
                          "background:#0f172a;color:#e2e8f0'><h2>Listo</h2><p>Ya "
                          "puedes cerrar esta pestaña y volver a Jarvis.</p>"
                          "</body></html>").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

        try:
            servidor = http.server.HTTPServer(("127.0.0.1", puerto), Manejador)
        except OSError as e:
            return "", (f"No pude escuchar en el puerto {puerto} ({e}). Cierra lo que "
                        f"lo esté usando y vuelve a intentarlo.")
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            listo.wait(tiempo_max)
        finally:
            servidor.shutdown()
            servidor.server_close()
        if resultado["error"]:
            return "", resultado["error"]
        if not resultado["codigo"]:
            return "", ("Se acabó el tiempo esperando a Spotify. Vuelve a intentarlo "
                        "con «Conectar Spotify».")
        return resultado["codigo"], ""
    def entrar(self, avisar=None, cliente_id=None, tiempo_max=300):
        """Conecta la cuenta de Spotify: (ok, mensaje). Se hace una sola vez.

        `avisar` es cómo se le cuenta al usuario lo que va pasando (Ajustes enseña
        el enlace en su etiqueta; por consola se imprime). El enlace se abre solo en
        el navegador, pero se cuenta igualmente: si no se abre, se puede copiar.
        """
        def decir(texto):
            print(f"[spotify] {texto}")
            if avisar:
                try:
                    avisar(texto)
                except Exception as e:
                    print(f"[spotify] No pude avisar en la ventana ({e}).")

        identificador = (cliente_id or self.cliente_id() or "").strip()
        if not identificador:
            return False, ("Para conectar Spotify necesito el Client ID de una "
                           "aplicación gratuita del panel de Spotify "
                           "(developer.spotify.com/dashboard). Se pega una vez y ya "
                           "no se vuelve a pedir.")
        self._guardar_ajustes({"cliente_id": identificador,
                               "redireccion": self.redireccion()})
        verificador = secrets.token_urlsafe(64)
        estado = secrets.token_urlsafe(16)
        enlace = self._url_autorizacion(self._desafio(verificador), estado)
        decir("Abre este enlace y pulsa «Aceptar» (se abre solo en el navegador): "
              + enlace)
        self._abrir_navegador(enlace)
        codigo, error = self._esperar_codigo(estado, tiempo_max)
        if error:
            return False, error
        try:
            datos = self._pedir_json(self.CUENTAS + "/api/token", metodo="POST",
                                     form={
                                         "grant_type": "authorization_code",
                                         "code": codigo,
                                         "redirect_uri": self.redireccion(),
                                         "client_id": identificador,
                                         "code_verifier": verificador,
                                     })
        except ErrorSpotify as e:
            return False, f"No pude terminar la conexión con Spotify. {e}"
        refresco = str((datos or {}).get("refresh_token") or "")
        if not refresco:
            return False, ("Spotify no me dio permiso para recordar la sesión: "
                           "vuelve a intentarlo con «Conectar Spotify».")
        self._guardar_token(refresco)
        self._token = str((datos or {}).get("access_token") or "")
        self._token_expira = time.time() + 60 * 50
        try:
            perfil = self._perfil()
        except ErrorSpotify as e:
            return True, f"Spotify conectado, pero no pude leer tu perfil. {e}"
        quien = perfil["nombre"] or perfil["id"] or "tu cuenta"
        if perfil["premium"]:
            extra = (" Ya puedo poner canciones, pausar, saltar y volver atrás sin "
                     "tocar el teclado ni abrir ventanas.")
        else:
            extra = (" Ojo: esta cuenta no es Premium, así que Spotify no me deja "
                     "controlar la reproducción (es una regla suya). Te dejaré la "
                     "canción cargada para que le des al play.")
        return True, f"Spotify conectado como {quien}.{extra}"

    def _perfil(self, guardar=True):
        """Tu perfil de Spotify: nombre, id y si la cuenta es Premium."""
        datos = self._api("GET", "/me") or {}
        producto = str(datos.get("product") or "").lower()
        perfil = {"nombre": str(datos.get("display_name") or "").strip(),
                  "id": str(datos.get("id") or "").strip(),
                  "producto": producto,
                  "premium": producto == "premium"}
        if guardar:
            self._guardar_ajustes({"cuenta": perfil["nombre"] or perfil["id"],
                                   "premium": perfil["premium"]})
        return perfil

    def salir(self):
        """Olvida la sesión guardada (no toca lo que esté sonando)."""
        self._token = ""
        self._token_expira = 0.0
        self._guardar_ajustes({"token": "", "cifrado": True, "cuenta": "",
                               "premium": False})
        return True, ("Sesión de Spotify olvidada: para volver a usar la API hay que "
                      "conectar la cuenta otra vez.")

    def _token_valido(self):
        """Access token listo para usar (renueva el del refresh guardado si toca)."""
        if self._token and time.time() < self._token_expira:
            return self._token
        refresco = self._token_guardado()
        if not refresco:
            raise ErrorSpotify("Todavía no he conectado Spotify: hay que conectar la "
                               "cuenta una vez («Conectar Spotify»).")
        try:
            datos = self._pedir_json(self.CUENTAS + "/api/token", metodo="POST",
                                     form={
                                         "grant_type": "refresh_token",
                                         "refresh_token": refresco,
                                         "client_id": self.cliente_id(),
                                     })
        except ErrorSpotify as e:
            raise ErrorSpotify(f"{e} Vuelve a conectar Spotify («Conectar "
                               f"Spotify»).", e.estado) from None
        token = str((datos or {}).get("access_token") or "")
        if not token:
            raise ErrorSpotify("Spotify no me dio sesión nueva: vuelve a conectar la "
                               "cuenta («Conectar Spotify»).")
        self._token = token
        self._token_expira = time.time() + max(
            60, int((datos or {}).get("expires_in") or 3600) - 60)
        nuevo = str((datos or {}).get("refresh_token") or "")
        if nuevo and nuevo != refresco:
            self._guardar_token(nuevo)     # Spotify rota el refresh token a veces
        return token
    # ------------------------------------------------------------ Llamadas HTTP
    def _pedir_json(self, url, metodo="GET", params=None, form=None,
                    json_cuerpo=None, cabeceras=None):
        """Petición a Spotify que devuelve lo que responda (dict, o None si vacío).

        Todo el módulo pasa por aquí: es el único sitio que habla por la red, así
        que las pruebas lo cambian por un doble y se comprueba qué se *habría*
        pedido sin salir a internet.
        """
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        datos = None
        cabeceras = dict(cabeceras or {})
        cabeceras.setdefault("Accept", "application/json")
        if form is not None:
            datos = urllib.parse.urlencode(form).encode("utf-8")
            cabeceras.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif json_cuerpo is not None:
            datos = json.dumps(json_cuerpo).encode("utf-8")
            cabeceras.setdefault("Content-Type", "application/json")
        peticion = urllib.request.Request(url, data=datos, method=metodo,
                                          headers=cabeceras)
        try:
            with urllib.request.urlopen(peticion, timeout=self.ESPERA_RED) as salida:
                cuerpo = salida.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                cuerpo = e.read().decode("utf-8", "replace")
            except Exception:
                cuerpo = ""
            raise ErrorSpotify(self._explicar_error(e.code, cuerpo), e.code) from None
        except Exception as e:
            raise ErrorSpotify(f"No pude hablar con Spotify ({e}).") from None
        if not cuerpo.strip():
            return None                   # 204: se hizo, y no hay nada que contar
        try:
            return json.loads(cuerpo)
        except ValueError:
            raise ErrorSpotify("Spotify respondió algo que no sé leer.") from None

    @classmethod
    def _explicar_error(cls, codigo, cuerpo):
        """Traduce el error de Spotify a algo que se entienda y se pueda arreglar."""
        motivo = mensaje = ""
        try:
            datos = json.loads(cuerpo or "{}")
            interno = datos.get("error")
            if isinstance(interno, dict):
                motivo = str(interno.get("reason") or "").strip()
                mensaje = str(interno.get("message") or "").strip()
            elif isinstance(interno, str):
                motivo = interno.strip()
                mensaje = str(datos.get("error_description") or interno).strip()
        except ValueError:
            mensaje = str(cuerpo or "").strip()
        if "premium" in str(cuerpo or "").lower():   # lo dice de varias formas
            motivo = "PREMIUM_REQUIRED"
        ayuda = cls.AYUDAS_ERROR.get(motivo) or cls.AYUDAS_CODIGO.get(int(codigo or 0))
        if ayuda:
            return ayuda
        return f"Spotify devolvió un error ({codigo}): {mensaje or 'sin detalle'}."

    def _api(self, metodo, ruta, params=None, json_cuerpo=None, reintentar=True):
        """Llamada a la Web API con la sesión del usuario."""
        token = self._token_valido()
        try:
            return self._pedir_json(self.API + ruta, metodo=metodo, params=params,
                                    json_cuerpo=json_cuerpo,
                                    cabeceras={"Authorization": f"Bearer {token}"})
        except ErrorSpotify as e:
            if e.estado == 401 and reintentar:
                self._token = ""          # el token caducó: se renueva y se reintenta
                self._token_expira = 0.0
                return self._api(metodo, ruta, params=params,
                                 json_cuerpo=json_cuerpo, reintentar=False)
            raise
    # ---------------------------------------------------- Buscar y elegir dónde
    def dispositivos(self):
        """Dónde puede sonar Spotify ahora mismo (lista de dicts)."""
        datos = self._api("GET", "/me/player/devices") or {}
        lista = []
        for bruto in datos.get("devices") or []:
            lista.append({
                "id": str(bruto.get("id") or ""),
                "nombre": str(bruto.get("name") or "").strip(),
                "tipo": str(bruto.get("type") or "").lower(),
                "activo": bool(bruto.get("is_active")),
                "restringido": bool(bruto.get("is_restricted")),
                "volumen": bruto.get("volume_percent"),
            })
        return lista

    def elegir_dispositivo(self, nombre=None):
        """El dispositivo que toca usar (None si no hay ninguno disponible).

        Se prefiere el ordenador con Spotify abierto: es donde suele estar sonando
        y con el volumen que ya tenías puesto. Se puede fijar otro en
        `spotify.dispositivo` con parte de su nombre (por ejemplo un altavoz).
        """
        utiles = [d for d in self.dispositivos() if not d["restringido"]]
        pedido = str(nombre or self.ajustes().get("dispositivo") or "").strip().lower()
        if pedido:
            for dispositivo in utiles:
                if pedido in dispositivo["nombre"].lower():
                    return dispositivo
        ordenados = ([d for d in utiles if d["tipo"] == "computer" and d["activo"]]
                     + [d for d in utiles if d["tipo"] == "computer"]
                     + [d for d in utiles if d["activo"]]
                     + utiles)
        return ordenados[0] if ordenados else None

    def buscar_pista(self, consulta):
        """La mejor pista para esa consulta (dict), o None si no hay resultados."""
        limpio = self._limpiar_consulta(consulta)
        if not limpio:
            return None
        datos = self._api("GET", "/search",
                          params={"q": limpio, "type": "track", "limit": 5}) or {}
        pistas = (datos.get("tracks") or {}).get("items") or []
        if not pistas:
            return None
        return self._pista_de(pistas[0])

    @staticmethod
    def _pista_de(bruto):
        """Los datos de una pista tal y como los usa Jarvis (título, artista, uri)."""
        artistas = [str(a.get("name") or "").strip()
                    for a in (bruto.get("artists") or [])]
        return {
            "id": str(bruto.get("id") or "").strip(),
            "titulo": str(bruto.get("name") or "").strip(),
            "artista": ", ".join([a for a in artistas if a]),
            "album": str((bruto.get("album") or {}).get("name") or "").strip(),
            "uri": str(bruto.get("uri") or "").strip(),
            "duracion_ms": int(bruto.get("duration_ms") or 0),
            "enlace": str((bruto.get("external_urls") or {}).get("spotify") or ""),
        }

    @staticmethod
    def _limpiar_consulta(consulta):
        """Consulta legible: la IA a veces manda «Junior+H+Las+noches»."""
        texto = str(consulta or "").replace("+", " ").strip()
        if "%" in texto:
            try:
                texto = urllib.parse.unquote_plus(texto)
            except Exception:
                pass
        return re.sub(r"\s+", " ", texto).strip()

    def sonando(self):
        """Qué está sonando ahora (dict), o None si Spotify no dice nada."""
        datos = self._api("GET", "/me/player")
        if not datos:
            return None
        pista = datos.get("item") or {}
        dispositivo = datos.get("device") or {}
        return {
            "suena": bool(datos.get("is_playing")),
            "progreso_ms": int(datos.get("progress_ms") or 0),
            "dispositivo": str(dispositivo.get("name") or ""),
            "tipo": str(dispositivo.get("type") or "").lower(),
            "pista": self._pista_de(pista) if pista else None,
        }
    # ------------------------------------------------------------- Reproducción
    def poner_pista(self, uri, titulo=""):
        """Manda sonar esa pista y comprueba que suena de verdad.

        Devuelve un dict con `ok`, `motivo` (cuando no se pudo), `dispositivo` y
        `pista` (lo que está sonando). No se abre ni se enfoca ninguna ventana: se
        le manda la orden al dispositivo y Spotify contesta.
        """
        respuesta = {"ok": False, "motivo": "", "dispositivo": "", "pista": None}
        dispositivo = self.elegir_dispositivo()
        if dispositivo is None:
            respuesta["motivo"] = ("No hay ningún dispositivo de Spotify disponible: "
                                   "abre Spotify en este PC (o el altavoz) y lo "
                                   "intento otra vez.")
            return respuesta
        respuesta["dispositivo"] = dispositivo["nombre"]
        try:
            self._api("PUT", "/me/player/play",
                      params={"device_id": dispositivo["id"]},
                      json_cuerpo={"uris": [uri], "position_ms": 0})
        except ErrorSpotify as e:
            respuesta["motivo"] = str(e)
            return respuesta
        estado = self._esperar_sonando(uri, titulo)
        if estado is None:
            respuesta["motivo"] = ("Le mandé la canción a Spotify, pero no confirma "
                                   "que esté sonando: mira que ese dispositivo no "
                                   "esté en silencio ni con otra cuenta.")
            return respuesta
        respuesta.update({"ok": True, "pista": estado["pista"],
                          "dispositivo": estado["dispositivo"]
                          or respuesta["dispositivo"]})
        return respuesta

    def _esperar_sonando(self, uri, titulo=""):
        """Espera a que Spotify diga que esa pista suena (None si no lo confirma)."""
        limite = time.time() + self.ESPERA_SONANDO
        while time.time() < limite:
            try:
                estado = self.sonando()
            except ErrorSpotify as e:
                print(f"[spotify] No pude preguntar qué suena ({e}).")
                estado = None
            if (estado and estado["suena"] and estado["pista"]
                    and self._misma_pista(estado["pista"], uri, titulo)):
                return estado
            time.sleep(1)
        return None

    @classmethod
    def _misma_pista(cls, pista, uri="", titulo=""):
        """True si lo que suena es la pista que se pidió (por uri o por título).

        El `uri` es lo exacto; el título se mira además porque Spotify a veces
        reproduce otra versión parecida (relink) con otro `uri`.
        """
        if uri and pista.get("uri") and pista["uri"] == uri:
            return True
        pedidas = cls._palabras(titulo)
        if not pedidas:
            return False
        suenan = cls._palabras(f"{pista.get('titulo', '')} {pista.get('artista', '')}")
        return pedidas <= suenan

    #: Palabras que no distinguen una canción de otra (se ignoran al comparar).
    PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "e",
                       "en", "con", "por", "para", "que", "the", "of", "feat", "ft",
                       "spotify", "song", "cancion", "musica"}

    @classmethod
    def _palabras(cls, texto):
        """Palabras que distinguen una canción de otra (sin acentos ni mayúsculas)."""
        limpio = unicodedata.normalize("NFKD", str(texto or "").lower())
        limpio = "".join(letra for letra in limpio
                         if not unicodedata.combining(letra))
        palabras = set(re.split(r"[^a-z0-9]+", limpio)) - {""}
        utiles = palabras - cls.PALABRAS_VACIAS
        return utiles or palabras
    def pausar(self):
        """Pausa lo que esté sonando (comprobando que se pausó)."""
        return self._mando("pausar")

    def reanudar(self):
        """Sigue con lo que estaba puesto (comprobando que suena)."""
        return self._mando("reanudar")

    def siguiente(self):
        """Salta a la siguiente canción (comprobando que cambió)."""
        return self._mando("siguiente")

    def anterior(self):
        """Vuelve a la canción anterior (comprobando que cambió)."""
        return self._mando("anterior")

    def _mando(self, orden):
        """Pausa, reanuda, salta o vuelve atrás, y comprueba que Spotify lo hizo.

        Los mandos van solos al dispositivo que está sonando (Spotify los aplica al
        activo), así que funcionan con música ya puesta sin tener que elegir dónde.
        """
        respuesta = {"ok": False, "motivo": "", "dispositivo": "", "pista": None}
        try:
            antes = self.sonando()
        except ErrorSpotify as e:
            respuesta["motivo"] = str(e)
            return respuesta
        if antes is None or antes["pista"] is None:
            respuesta["motivo"] = "Ahora mismo no está sonando nada en Spotify."
            return respuesta
        if orden == "pausar" and not antes["suena"]:
            respuesta.update({"ok": True, "pista": antes["pista"],
                              "dispositivo": antes["dispositivo"],
                              "motivo": "La música ya estaba en pausa."})
            return respuesta
        if orden == "reanudar" and antes["suena"]:
            respuesta.update({"ok": True, "pista": antes["pista"],
                              "dispositivo": antes["dispositivo"],
                              "motivo": "La música ya estaba sonando."})
            return respuesta
        try:
            if orden == "pausar":
                self._api("PUT", "/me/player/pause")
            elif orden == "reanudar":
                self._api("PUT", "/me/player/play")
            elif orden == "siguiente":
                self._api("POST", "/me/player/next")
            else:
                self._api("POST", "/me/player/previous")
        except ErrorSpotify as e:
            respuesta["motivo"] = str(e)
            return respuesta
        estado = self._esperar_cambio(orden, antes)
        if estado is None:
            respuesta["motivo"] = ("Spotify no confirma que haya cambiado nada, así "
                                   "que no sé si lo hice.")
            return respuesta
        respuesta.update({"ok": True, "pista": estado["pista"],
                          "dispositivo": estado["dispositivo"]})
        return respuesta

    def _esperar_cambio(self, orden, antes=None):
        """Espera a que el estado tras el mando sea el que ese mando produce."""
        limite = time.time() + self.ESPERA_MANDO
        while time.time() < limite:
            try:
                estado = self.sonando()
            except ErrorSpotify as e:
                print(f"[spotify] No pude comprobar el mando ({e}).")
                estado = None
            if estado and estado["pista"]:
                if orden == "pausar" and not estado["suena"]:
                    return estado
                if orden == "reanudar" and estado["suena"]:
                    return estado
                if orden in ("siguiente", "anterior"):
                    pista_antes = ((antes or {}).get("pista") or {}).get("uri", "")
                    if estado["pista"]["uri"] and estado["pista"]["uri"] != pista_antes:
                        return estado
                    # «Anterior» también puede ser volver a empezar la misma canción.
                    if orden == "anterior" and estado["progreso_ms"] <= 3000:
                        return estado
            time.sleep(1)
        return None
def main(argumentos=None):
    """Consola del módulo: conectar, ver dispositivos, poner una canción o salir.

        python -m modules.spotify entrar          # pega el Client ID y autoriza
        python -m modules.spotify probar          # cuenta, dispositivos y qué suena
        python -m modules.spotify dispositivos    # altavoces y equipos disponibles
        python -m modules.spotify poner "Junior H Las noches"
        python -m modules.spotify salir
    """
    argumentos = list(sys.argv[1:] if argumentos is None else argumentos)
    orden = argumentos[0].strip().lower() if argumentos else "probar"
    resto = " ".join(argumentos[1:]).strip()
    cliente = Spotify()
    try:
        if orden in ("entrar", "conectar"):
            ok, mensaje = cliente.entrar(cliente_id=resto or None)
            print(mensaje)
            return 0 if ok else 1

        if orden in ("salir", "desconectar", "olvidar"):
            print(cliente.salir()[1])
            return 0

        if orden in ("dispositivos", "equipos", "altavoces"):
            if not cliente.disponible():
                print("Todavía no he conectado Spotify: conéctalo una vez con "
                      "`python -m modules.spotify entrar`.")
                return 1
            lista = cliente.dispositivos()
            if not lista:
                print("Ahora mismo no hay ningún dispositivo de Spotify disponible.")
                return 0
            print("Dispositivos de Spotify:")
            for dispositivo in lista:
                marcas = []
                if dispositivo["activo"]:
                    marcas.append("sonando ahora")
                if dispositivo["restringido"]:
                    marcas.append("no acepta órdenes")
                if dispositivo["volumen"] is not None:
                    marcas.append(f"volumen {dispositivo['volumen']}%")
                extra = f" ({', '.join(marcas)})" if marcas else ""
                print(f"  - {dispositivo['nombre']} "
                      f"[{dispositivo['tipo']}]{extra}")
            return 0

        if orden in ("poner", "reproducir", "play"):
            if not resto:
                print('Dime qué canción: python -m modules.spotify poner '
                      '"Junior H Las noches"')
                return 1
            pista = cliente.buscar_pista(resto)
            if pista is None:
                print(f"No encuentro «{resto}» en Spotify.")
                return 1
            resultado = cliente.poner_pista(pista["uri"], pista["titulo"])
            if resultado["ok"]:
                print(f"Poniendo «{pista['titulo']}» de {pista['artista']} en "
                      f"Spotify ({resultado['dispositivo']}).")
                return 0
            print(resultado["motivo"])
            return 1

        if orden in ("probar", "estado"):
            if not cliente.disponible():
                print("Todavía no he conectado Spotify: conéctalo una vez con "
                      "`python -m modules.spotify entrar`.")
                return 1
            perfil = cliente._perfil()
            print(f"Cuenta: {perfil['nombre'] or perfil['id']} "
                  f"({'Premium' if perfil['premium'] else 'sin Premium'})")
            lista = cliente.dispositivos()
            print(f"Dispositivos disponibles: {len(lista)}")
            for dispositivo in lista:
                activo = " (sonando ahora)" if dispositivo["activo"] else ""
                print(f"  - {dispositivo['nombre']} "
                      f"[{dispositivo['tipo']}]{activo}")
            estado = cliente.sonando()
            if estado and estado["pista"]:
                pausa = "" if estado["suena"] else " (en pausa)"
                print(f"Suena: {estado['pista']['titulo']} de "
                      f"{estado['pista']['artista']} en "
                      f"«{estado['dispositivo']}»{pausa}")
            else:
                print("Ahora mismo no está sonando nada.")
            return 0
    except ErrorSpotify as e:
        print(str(e))
        return 1

    print('Uso: python -m modules.spotify entrar | probar | dispositivos | '
          'poner "canción" | salir')
    return 1


if __name__ == "__main__":
    sys.exit(main())
