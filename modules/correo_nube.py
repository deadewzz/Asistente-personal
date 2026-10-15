"""Correo de Microsoft 365 / Outlook.com por la nube (Microsoft Graph + OAuth2).

El **Outlook nuevo** de Windows (`olk.exe`) es un cliente web dentro de WebView2: no
expone ninguna API local (ni COM ni MAPI), así que en un equipo sin Outlook clásico
la única forma de que la IA lea y escriba el correo es hablar con el mismo servicio
de Microsoft al que se conecta ese Outlook. Este módulo lo hace con **Microsoft
Graph**: es tu buzón de verdad (mismas carpetas, mismas categorías y el mismo
Borradores que ves en el Outlook nuevo), y funciona con el Outlook abierto o cerrado.

Autenticación: OAuth2 con **código de dispositivo** (`device code`). No hay que
escribir la contraseña en el asistente ni guardarla: abres una web, escribes un
código y listo. El *refresh token* se guarda **cifrado con DPAPI** (solo tu usuario
de Windows puede descifrarlo).

  python -m modules.correo_nube entrar    # conectar el correo (una sola vez)
  python -m modules.correo_nube probar    # comprobar la conexión y listar 3 correos
  python -m modules.correo_nube salir     # olvidar la sesión guardada

Por comodidad se usa por defecto un cliente público conocido de Microsoft
(*"Microsoft Graph Command Line Tools"*), que Microsoft Graph sí admite, así que se
conecta sin registrar nada. Si tu organización exige una aplicación propia, regístrala
en Entra (Azure) y escribe su id en `correo.cliente_id` dentro de `config_usuario.json`.

Reglas de seguridad: ninguna acción envía correo por su cuenta. `responder` y
`crear_borrador` dejan el mensaje en **Borradores** y solo se envía cuando el usuario
lo pide de forma explícita (o con `enviar_borrador`).
"""

import base64
import json
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

from modules import rutas

# Cliente público conocido de Microsoft para no tener que registrar nada. Tiene que
# estar *preautorizado para Microsoft Graph*: el de "Microsoft Office" (d3590ed6-...)
# vale para Outlook/Exchange, pero Graph lo rechaza con AADSTS65002; este otro es el
# que usa la propia herramienta de Microsoft para Graph y sí admite esos permisos.
CLIENTE_PUBLICO = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
TENANT_POR_DEFECTO = "common"
AUTORIDAD = "https://login.microsoftonline.com"
GRAPH = "https://graph.microsoft.com/v1.0"
# Permisos que se piden (los mínimos que usa el módulo: solo correo y tu perfil).
# `offline_access` es lo que permite renovar la sesión sin volver a pedir el código.
PERMISOS = ("offline_access "
            "https://graph.microsoft.com/Mail.ReadWrite "
            "https://graph.microsoft.com/Mail.Send "
            "https://graph.microsoft.com/User.Read")

# Explicaciones propias para los errores de Microsoft que más se ven al conectar.
# (Los códigos AADSTS vienen dentro del texto de error que devuelve Microsoft.)
AYUDAS_ERROR = (
    ("AADSTS65002",
     "El cliente público usado no puede pedir Microsoft Graph: usa el que viene por "
     "defecto o registra una aplicación propia para 'correo.cliente_id'."),
    ("AADSTS65001",
     "Faltan permisos consentidos: pide a un administrador de tu organización que "
     "apruebe Mail.ReadWrite, Mail.Send y User.Read."),
    ("AADSTS500011",
     "La aplicación no existe en tu organización: revisa 'correo.cliente_id' y "
     "'correo.tenant'."),
    ("AADSTS700016",
     "Ese 'correo.cliente_id' no está dado de alta en tu organización."),
    ("AADSTS50020",
     "Esa cuenta no pertenece al 'tenant' configurado: revisa 'correo.tenant'."),
    ("AADSTS7000218",
     "Esa aplicación no permite el flujo de código de dispositivo: en su registro de "
     "Entra activa 'Permitir flujos de cliente público' = Sí."),
)

# Carpetas conocidas de Graph (identificadores estándar de cualquier buzón)
BANDEJA = "inbox"
BORRADORES = "drafts"
ENVIADOS = "sentitems"
ARCHIVO = "archive"


class ErrorCorreo(Exception):
    """Fallo de conexión o de la API, con un mensaje ya entendible por el usuario."""

    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo      # código HTTP, cuando lo hay (401 = sesión caducada)


class CorreoNube:
    """Lee y gestiona el correo con la misma interfaz que `OutlookTools` (COM)."""

    # Cuántos correos recientes se revisan como máximo al listar o buscar
    LIMITE_BARRIDO = 60
    # Caracteres de cuerpo que se muestran por correo en un listado
    LARGO_EXTRACTO = 300
    # Caracteres de cuerpo que se pasan a la IA al leer un correo completo
    LARGO_CUERPO = 4000
    # Nombres habituales de la carpeta de archivo (por orden de preferencia)
    NOMBRES_ARCHIVO = ("archivo", "archive", "archivados", "historico")

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self._config = self._leer_config()
        self._token = None            # token de acceso en memoria
        self._token_expira = 0.0
        self._error = ""
        # Correos del último listado mostrado: permiten referirse a ellos por número
        self._ultimo_listado = []
        # Último borrador preparado por el asistente (para poder enviarlo después)
        self._ultimo_borrador = ""
        self._carpetas_cache = None

    # ------------------------------------------------------------------ Configuración
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
        """Sección 'correo' de la configuración (dict vacío si no hay ninguna).

        Se relee del archivo para que un asistente ya abierto se entere de una
        conexión hecha después (por ejemplo desde Ajustes o desde la consola).
        """
        config = self._leer_config()
        if config or not self._config:
            self._config = config
        seccion = self._config.get("correo")
        return dict(seccion) if isinstance(seccion, dict) else {}

    def _guardar_ajustes(self, cambios):
        """Actualiza la sección 'correo' sin tocar el resto de la configuración."""
        config = self._leer_config()
        seccion = config.get("correo")
        if not isinstance(seccion, dict):
            seccion = {}
        seccion.update(cambios)
        seccion.setdefault("cliente_id", CLIENTE_PUBLICO)
        seccion.setdefault("tenant", TENANT_POR_DEFECTO)
        config["correo"] = seccion
        self._guardar_config(config)
        return seccion

    def _cliente_id(self):
        return (self.ajustes().get("cliente_id") or CLIENTE_PUBLICO).strip() or CLIENTE_PUBLICO

    def _tenant(self):
        return (self.ajustes().get("tenant") or TENANT_POR_DEFECTO).strip() or TENANT_POR_DEFECTO

    def disponible(self):
        """True si ya se inició sesión alguna vez (hay token guardado)."""
        return bool(self.ajustes().get("token"))

    # Alias para que la fábrica de `modules.correo` trate igual a ambos clientes.
    configurado = disponible

    # ------------------------------------------------------------------ Cifrado (DPAPI)
    @staticmethod
    def _cifrar(texto):
        """Cifra un texto con DPAPI. Devuelve '' si no se puede cifrar."""
        try:
            import win32crypt
            blob = win32crypt.CryptProtectData(str(texto).encode("utf-8"),
                                               "jarvis-correo", None, None, None, 0)
            if isinstance(blob, tuple):
                blob = blob[0]
            return base64.b64encode(blob).decode("ascii")
        except Exception as e:
            print(f"[correo] No pude cifrar el token de sesión: {e}")
            return ""

    @staticmethod
    def _descifrar(valor):
        """Descifra un texto guardado con `_cifrar`. Devuelve '' si no se puede."""
        if not valor:
            return ""
        try:
            import win32crypt
            datos = win32crypt.CryptUnprotectData(base64.b64decode(valor), None, None, None, 0)
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
        if seccion.get("cifrado"):
            return self._descifrar(valor)
        return valor

    def salir(self):
        """Olvida la sesión guardada (borra el token del disco)."""
        self._guardar_ajustes({"token": "", "cifrado": False, "cuenta": ""})
        self._token = None
        self._token_expira = 0.0
        return True, ("Listo: olvidé la sesión de tu correo. Usa 'entrar' para "
                      "volver a conectarlo.")

    # ------------------------------------------------------------------ OAuth2 / HTTP
    @staticmethod
    def _pista_error(texto):
        """Pista en castellano para los errores de Microsoft más habituales (o '')."""
        cadena = str(texto or "").upper()
        for codigo, ayuda in AYUDAS_ERROR:
            if codigo in cadena:
                return ayuda
        return ""

    @staticmethod
    def _mensaje_error(texto):
        """Saca el mensaje legible de un error de Microsoft (OAuth o Graph).

        Cuando reconoce un error típico de conexión (por ejemplo AADSTS65002, que
        sale al pedir Graph con un cliente no preautorizado) añade una frase que
        explica qué hacer.
        """
        base = ""
        try:
            datos = json.loads(texto or "")
        except Exception:
            base = (texto or "").strip()
        else:
            if not isinstance(datos, dict):
                base = str(datos)
            else:
                error = datos.get("error")
                if isinstance(error, dict):
                    base = str(error.get("message") or error.get("code") or "")
                elif isinstance(error, str):
                    detalle = str(datos.get("error_description") or "").strip()
                    base = error + (f": {detalle}" if detalle else "")
                else:
                    base = str(datos)
        base = base.strip()[:300]
        pista = CorreoNube._pista_error(base or texto)
        return f"{base} {pista}".strip() if pista else base

    def _pedir_json(self, url, metodo="POST", form=None, json_cuerpo=None, cabeceras=None):
        """Petición HTTP que devuelve JSON; lanza ErrorCorreo con un mensaje claro."""
        datos = None
        cabeza = dict(cabeceras or {})
        if form is not None:
            datos = urllib.parse.urlencode(form).encode("utf-8")
            cabeza.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif json_cuerpo is not None:
            datos = json.dumps(json_cuerpo).encode("utf-8")
            cabeza.setdefault("Content-Type", "application/json")
        cabeza.setdefault("Accept", "application/json")
        peticion = urllib.request.Request(url, data=datos, headers=cabeza, method=metodo)
        try:
            with urllib.request.urlopen(peticion, timeout=30,
                                        context=ssl.create_default_context()) as respuesta:
                texto = respuesta.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                texto = e.read().decode("utf-8", "replace")
            except Exception:
                texto = ""
            raise ErrorCorreo(self._mensaje_error(texto) or f"error HTTP {e.code}", e.code)
        except Exception as e:
            raise ErrorCorreo(f"No pude conectar con Microsoft ({type(e).__name__}: {e})")
        if not texto.strip():
            return {}
        try:
            return json.loads(texto)
        except Exception:
            raise ErrorCorreo("Microsoft devolvió una respuesta que no entendí.")

    def _guardar_tokens(self, token):
        """Guarda el refresh token (cifrado) y deja el de acceso en memoria."""
        self._token = token.get("access_token") or ""
        try:
            self._token_expira = time.time() + float(token.get("expires_in") or 3600)
        except Exception:
            self._token_expira = time.time() + 3600
        refresco = token.get("refresh_token") or ""
        if refresco:
            cifrado = self._cifrar(refresco)
            self._guardar_ajustes({"token": cifrado or refresco, "cifrado": bool(cifrado)})

    def _renovar(self):
        """Pide un token de acceso nuevo con el refresh token guardado."""
        refresco = self._token_guardado()
        if not refresco:
            raise ErrorCorreo("No hay ninguna sesión de correo guardada.")
        datos = self._pedir_json(f"{AUTORIDAD}/{self._tenant()}/oauth2/v2.0/token",
                                 form={"client_id": self._cliente_id(),
                                       "grant_type": "refresh_token",
                                       "refresh_token": refresco,
                                       "scope": PERMISOS})
        self._guardar_tokens(datos)
        return self._token

    def _token_valido(self):
        """Token de acceso utilizable (lo renueva cuando está a punto de caducar)."""
        if self._token and time.time() < self._token_expira - 60:
            return self._token
        return self._renovar()

    def _graph(self, metodo, ruta, json_cuerpo=None, params=None, reintentar=True):
        """Llamada a Microsoft Graph con reintento único si la sesión caducó."""
        url = ruta if ruta.startswith("http") else GRAPH + ruta
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        try:
            return self._pedir_json(url, metodo=metodo, json_cuerpo=json_cuerpo,
                                    cabeceras={"Authorization": f"Bearer {self._token_valido()}"})
        except ErrorCorreo as e:
            if reintentar and (e.codigo == 401 or "expired" in str(e).lower()):
                self._token = None
                self._token_expira = 0.0
                return self._graph(metodo, ruta, json_cuerpo, params, reintentar=False)
            raise

    def _sin_conexion(self):
        """Mensaje para el usuario cuando el correo no está disponible."""
        if not self.disponible():
            return ("Todavía no he conectado con tu correo. Pulsa 'Conectar correo' en "
                    "Ajustes (o ejecuta 'python -m modules.correo_nube entrar') una sola "
                    "vez y vuelve a pedírmelo.")
        return ("No pude hablar con tu correo"
                + (f": {self._error}" if self._error else " (revisa la conexión a internet)")
                + ".")

    # ------------------------------------------------------------------ Conectar
    def entrar(self, avisar=None, tiempo_max=900):
        """Conecta el correo con el flujo de código de dispositivo.

        `avisar` es la función con la que se le enseña al usuario el código y la web
        (la consola o la ventana del asistente). Devuelve (ok, mensaje).
        """
        avisar = avisar or (lambda texto: None)
        try:
            datos = self._pedir_json(f"{AUTORIDAD}/{self._tenant()}/oauth2/v2.0/devicecode",
                                     form={"client_id": self._cliente_id(),
                                           "scope": PERMISOS})
        except ErrorCorreo as e:
            return False, f"No pude iniciar la conexión con tu correo: {e}"
        codigo = str(datos.get("user_code") or "")
        web = str(datos.get("verification_uri") or "https://microsoft.com/devicelogin")
        minutos = max(1, int(datos.get("expires_in") or 900) // 60)
        avisar(f"Para conectar tu correo: abre {web} y escribe el código {codigo}.")
        avisar(f"Tienes {minutos} minutos para hacerlo; yo sigo esperando.")
        intervalo = max(3, int(datos.get("interval") or 5))
        limite = time.time() + min(tiempo_max, int(datos.get("expires_in") or 900))
        while time.time() < limite:
            time.sleep(intervalo)
            try:
                token = self._pedir_json(f"{AUTORIDAD}/{self._tenant()}/oauth2/v2.0/token",
                                         form={"client_id": self._cliente_id(),
                                               "grant_type": "device_code",
                                               "device_code": str(datos.get("device_code") or "")})
            except ErrorCorreo as e:
                texto = str(e)
                if "authorization_pending" in texto or "slow_down" in texto:
                    continue
                return False, f"La conexión con tu correo no se completó: {texto}"
            self._guardar_tokens(token)
            cuenta = self.cuenta()
            if cuenta:
                self._guardar_ajustes({"cuenta": cuenta})
            return True, (f"Correo conectado{': ' + cuenta if cuenta else ''}. "
                          "Ya puedo leerlo, resumirlo y preparar borradores.")
        return False, "Se acabó el tiempo para escribir el código. Pídeme conectarlo otra vez."

    def cuenta(self):
        """Dirección (o nombre) de la cuenta conectada; '' si no se puede saber."""
        try:
            datos = self._graph("GET", "/me",
                                params={"$select": "displayName,mail,userPrincipalName"})
        except ErrorCorreo:
            return ""
        return (datos.get("mail") or datos.get("userPrincipalName")
                or datos.get("displayName") or "")

    # ------------------------------------------------------------------ Utilidades
    @staticmethod
    def _fecha(valor):
        """Fecha ISO de Graph -> 'AAAA-MM-DD HH:MM' en la hora local del equipo."""
        texto = str(valor or "").strip()
        if not texto:
            return "sin fecha"
        try:
            momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=timezone.utc)
            return momento.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            return texto[:16]

    @staticmethod
    def _limpiar(texto, largo, colapsar=True):
        """Normaliza el texto de un correo y lo recorta a 'largo' caracteres."""
        cadena = str(texto or "")
        if colapsar:
            cadena = re.sub(r"[_\-=.~*]{6,}", " ", cadena)
            cadena = re.sub(r"\s+", " ", cadena)
        cadena = cadena.strip()
        if largo and len(cadena) > largo:
            return cadena[:largo].rstrip() + "..."
        return cadena

    @staticmethod
    def _sin_acentos(texto):
        """Minúsculas y sin acentos: para comparar carpetas o buscar términos."""
        plano = unicodedata.normalize("NFKD", str(texto or ""))
        return plano.encode("ascii", "ignore").decode("ascii").lower().strip()

    @classmethod
    def _html_a_texto(cls, html):
        """Convierte el HTML de un correo en texto plano legible."""
        cadena = str(html or "")
        cadena = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", cadena)
        cadena = re.sub(r"(?i)<br\s*/?>", "\n", cadena)
        cadena = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table)>", "\n", cadena)
        cadena = re.sub(r"(?i)<(p|div|tr|table|h[1-6])[^>]*>", "\n", cadena)
        cadena = re.sub(r"(?i)<li[^>]*>", "\n- ", cadena)
        cadena = re.sub(r"(?s)<[^>]+>", " ", cadena)
        cadena = unescape(cadena)
        cadena = re.sub(r"[ \t\u00a0]+", " ", cadena)
        cadena = re.sub(r"\n\s*\n\s*\n+", "\n\n", cadena)
        return cadena.strip()

    @classmethod
    def _cuerpo_texto(cls, mensaje):
        """Cuerpo de un correo ya en texto (entiende los correos en HTML)."""
        cuerpo = mensaje.get("body") or {}
        if not isinstance(cuerpo, dict):
            return str(cuerpo or "")
        contenido = str(cuerpo.get("content") or "")
        if str(cuerpo.get("contentType") or "").lower() == "html":
            return cls._html_a_texto(contenido)
        return contenido

    @staticmethod
    def _texto_a_html(texto):
        """Convierte un texto normal en HTML sencillo (para escribir correos)."""
        partes = []
        for linea in str(texto or "").replace("\r\n", "\n").split("\n"):
            escapada = linea.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            partes.append(f"<p>{escapada}</p>" if escapada.strip() else "<p></p>")
        return "".join(partes)

    @staticmethod
    def _direcciones(destinatarios):
        """Separa una lista de destinatarios ('a@x.com; Nombre <b@y.com>')."""
        texto = str(destinatarios or "").replace(";", ",")
        direcciones = []
        for trozo in texto.split(","):
            trozo = trozo.strip()
            if not trozo:
                continue
            dentro = re.search(r"<([^>]+)>", trozo)
            direccion = (dentro.group(1) if dentro else trozo).strip()
            if "@" in direccion and direccion not in direcciones:
                direcciones.append(direccion)
        return direcciones

    # ------------------------------------------------------------------ Listado
    CAMPOS_LISTA = "id,subject,from,receivedDateTime,isRead,bodyPreview"

    def _mensajes(self, carpeta=BANDEJA, tope=None):
        """Mensajes de una carpeta, del más reciente al más antiguo."""
        limite = max(1, min(int(tope or self.LIMITE_BARRIDO), 200))
        datos = self._graph("GET", f"/me/mailFolders/{carpeta}/messages",
                            params={"$top": limite, "$orderby": "receivedDateTime desc",
                                    "$select": self.CAMPOS_LISTA})
        return datos.get("value") or []

    @classmethod
    def _dia(cls, valor):
        """Día local de una fecha ISO de Graph (None si no se puede leer)."""
        try:
            momento = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=timezone.utc)
            return momento.astimezone().date()
        except Exception:
            return None

    def _resumen(self, mensaje, indice=None):
        """Extrae de un correo los datos que se muestran y se recuerdan."""
        remitente = (mensaje.get("from") or {}).get("emailAddress") or {}
        nombre = str(remitente.get("name") or "").strip()
        direccion = str(remitente.get("address") or "").strip()
        return {
            "indice": indice,
            "asunto": str(mensaje.get("subject") or "").strip() or "(sin asunto)",
            "de": nombre or direccion or "(remitente desconocido)",
            "fecha": self._fecha(mensaje.get("receivedDateTime")),
            "no_leido": not bool(mensaje.get("isRead", True)),
            "cuerpo": self._limpiar(mensaje.get("bodyPreview"), self.LARGO_EXTRACTO),
            "entry_id": str(mensaje.get("id") or ""),
        }

    @classmethod
    def _coincide(cls, datos, termino):
        """True si 'termino' aparece en el asunto, el remitente o el cuerpo."""
        buscado = cls._sin_acentos(termino)
        if not buscado:
            return True
        texto = cls._sin_acentos(f"{datos['asunto']} {datos['de']} {datos['cuerpo']}")
        return buscado in texto

    @staticmethod
    def _formatear_lista(correos, titulo):
        """Convierte el listado en el texto que se le pasa a la IA y al usuario."""
        lineas = [titulo]
        for datos in correos:
            marca = " [NO LEÍDO]" if datos["no_leido"] else ""
            lineas.append(f"{datos['indice']}. {datos['fecha']} — {datos['de']}: "
                          f"{datos['asunto']}{marca}")
            if datos["cuerpo"]:
                lineas.append(f"   {datos['cuerpo']}")
        return "\n".join(lineas)

    def listar(self, n=8, solo_no_leidos=False, desde_hoy=False, termino=None):
        """Lista los correos más recientes de la bandeja de entrada.

        Mismos datos que `OutlookTools.listar` (indice, asunto, de, fecha, no_leido,
        cuerpo, entry_id) o None si el correo no está disponible.
        """
        if not self.disponible():
            self._error = ""
            return None
        try:
            mensajes = self._mensajes()
        except ErrorCorreo as e:
            self._error = str(e)
            return None
        self._error = ""
        hoy = datetime.now().astimezone().date()
        resultados = []
        for mensaje in mensajes:
            if len(resultados) >= max(1, int(n)):
                break
            if solo_no_leidos and mensaje.get("isRead", True):
                continue
            if desde_hoy:
                dia = self._dia(mensaje.get("receivedDateTime"))
                if dia is not None and dia < hoy:
                    continue
            datos = self._resumen(mensaje, indice=len(resultados) + 1)
            if termino and not self._coincide(datos, termino):
                continue
            resultados.append(datos)
        self._ultimo_listado = resultados
        return resultados

    def leer_correos(self, n=5):
        """Lista los correos más recientes: remitente, asunto, hora y extracto."""
        correos = self.listar(n=n)
        if correos is None:
            return self._sin_conexion()
        if not correos:
            return "No hay correos en la bandeja de entrada."
        return self._formatear_lista(correos, f"Tus últimos {len(correos)} correos:")

    def resumen(self, criterio="", n=10):
        """Listado según criterio ('hoy', 'no leídos', un número) para resumirlo."""
        texto = self._sin_acentos(criterio)
        solo_no_leidos = "no le" in texto or "sin leer" in texto or "unread" in texto
        desde_hoy = "hoy" in texto or "today" in texto
        numero = re.search(r"\d+", texto)
        if numero:
            n = int(numero.group())
        correos = self.listar(n=n, solo_no_leidos=solo_no_leidos, desde_hoy=desde_hoy)
        if correos is None:
            return self._sin_conexion()
        if not correos:
            if solo_no_leidos:
                return "No tienes correos sin leer en la bandeja de entrada."
            if desde_hoy:
                return "No has recibido correos hoy."
            return "No hay correos en la bandeja de entrada."
        etiqueta = "sin leer" if solo_no_leidos else ("de hoy" if desde_hoy else "recientes")
        return self._formatear_lista(correos, f"Correos {etiqueta} ({len(correos)}):")

    def buscar(self, consulta, n=10):
        """Busca en asunto, remitente y extracto de los correos más recientes."""
        consulta = (consulta or "").strip()
        if not consulta:
            return "¿Qué quieres que busque en el correo?"
        correos = self.listar(n=n, termino=consulta)
        if correos is None:
            return self._sin_conexion()
        if not correos:
            return f"No encontré correos que mencionen '{consulta}'."
        return self._formatear_lista(correos, f"Correos que mencionan '{consulta}':")

    # ------------------------------------------------------------------ Detalle y localizar
    CAMPOS_DETALLE = ("id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
                      "isRead,body,bodyPreview,categories,hasAttachments")

    def _por_id(self, identificador):
        """Correo completo por su id (o None si ya no existe)."""
        if not identificador:
            return None
        return self._graph("GET", f"/me/messages/{identificador}",
                           params={"$select": self.CAMPOS_DETALLE})

    def detalle(self, clave):
        """Cuerpo completo de un correo (o el motivo por el que no se encontró)."""
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        datos = self._resumen(mensaje)
        cuerpo = self._limpiar(self._cuerpo_texto(mensaje), self.LARGO_CUERPO, colapsar=False)
        return (f"De {datos['de']} ({datos['fecha']})\n"
                f"Asunto: {datos['asunto']}\n\n{cuerpo or '(sin cuerpo)'}")

    def _por_id_con_error(self, identificador):
        """Mensaje por id: (mensaje, motivo). Un 404 real significa que ya no existe."""
        try:
            return self._por_id(identificador), ""
        except ErrorCorreo as e:
            if e.codigo == 404:
                return None, ""
            self._error = str(e)
            return None, self._sin_conexion()

    def _resolver(self, clave):
        """Localiza un correo por su número del último listado o por su texto.

        Devuelve (mensaje, motivo) donde 'motivo' explica por qué no se encontró
        (mensaje es None en ese caso).
        """
        texto = str(clave or "").strip()
        if not texto:
            return None, ("¿A qué correo te refieres? Pídeme primero 'lee mis correos' "
                          "y dime el número o el nombre del remitente.")
        if not self.disponible():
            self._error = ""
            return None, self._sin_conexion()
        numero = None
        if texto.isdigit():
            numero = int(texto)
        else:
            coincidencia = re.fullmatch(
                r"(?:el\s+|correo\s+|numero\s+)?(\d{1,3})", self._sin_acentos(texto))
            if coincidencia:
                numero = int(coincidencia.group(1))
        if numero is not None:
            for registro in self._ultimo_listado:
                if registro.get("indice") == numero:
                    mensaje, fallo = self._por_id_con_error(registro.get("entry_id"))
                    if mensaje is not None:
                        return mensaje, ""
                    if fallo:
                        return None, fallo
                    return None, (f"El correo {numero} ya no está en el buzón (¿lo moviste "
                                  "o lo borraste?). Pídeme 'lee mis correos' otra vez.")
            return None, (f"En la última lista que te mostré no había un correo número {numero}. "
                          "Pídeme primero 'lee mis correos'.")
        correos = self.listar(n=15, termino=texto)
        if correos is None:
            return None, self._sin_conexion()
        if not correos:
            return None, (f"No encontré ningún correo que coincida con '{texto}'. "
                          "Pídeme 'lee mis correos' y dime su número.")
        mensaje, fallo = self._por_id_con_error(correos[0].get("entry_id"))
        if mensaje is not None:
            return mensaje, ""
        if fallo:
            return None, fallo
        return None, "Ese correo ya no está en el buzón."

    # ------------------------------------------------------------------ Responder
    def responder(self, clave, texto, enviar=False):
        """Responde a un correo (por defecto deja la respuesta en Borradores).

        Solo envía si 'enviar' es True, algo que el asistente activa únicamente
        cuando el usuario lo pide de forma explícita. El texto se coloca encima del
        correo original citado, igual que hace Outlook.
        """
        texto = str(texto or "").strip()
        if not texto:
            return "No me diste el texto de la respuesta."
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        datos = self._resumen(mensaje)
        try:
            # Graph crea el borrador con el original citado debajo; se escribe encima.
            borrador = self._graph("POST", f"/me/messages/{mensaje['id']}/createReply",
                                   json_cuerpo={})
            identificador = str(borrador.get("id") or "")
            if not identificador:
                return "No pude preparar la respuesta en tu correo."
            actual = self._graph("GET", f"/me/messages/{identificador}",
                                 params={"$select": "body"})
            citado = str((actual.get("body") or {}).get("content") or "")
            self._graph("PATCH", f"/me/messages/{identificador}",
                        json_cuerpo={"body": {"contentType": "HTML",
                                              "content": self._texto_a_html(texto) + citado}})
            if enviar:
                self._graph("POST", f"/me/messages/{identificador}/send", json_cuerpo={})
                return f"Respuesta enviada a {datos['de']} (Re: {datos['asunto']})."
        except ErrorCorreo as e:
            return f"No pude {'enviar' if enviar else 'preparar'} la respuesta: {e}"
        self._ultimo_borrador = identificador
        return (f"Dejé la respuesta preparada en la carpeta Borradores para {datos['de']} "
                f"(Re: {datos['asunto']}). Dime 'envía ese correo' para mandarla.")

    def _borradores(self):
        """Borradores de la carpeta Borradores, el más reciente primero."""
        datos = self._graph("GET", f"/me/mailFolders/{BORRADORES}/messages",
                            params={"$top": 25, "$orderby": "lastModifiedDateTime desc",
                                    "$select": "id,subject,toRecipients,lastModifiedDateTime"})
        return datos.get("value") or []

    def _buscar_borrador(self, clave=None):
        """Localiza un borrador por texto de asunto, número o el más reciente."""
        borradores = self._borradores()
        texto = self._sin_acentos(clave)
        mas_reciente = borradores[0] if borradores else None
        for posicion, borrador in enumerate(borradores, start=1):
            if not texto:
                continue
            if texto.isdigit() and posicion == int(texto):
                return borrador
            if texto in self._sin_acentos(borrador.get("subject")):
                return borrador
        return mas_reciente

    def enviar_borrador(self, clave=None):
        """Envía el borrador que se acaba de preparar (o uno que coincida)."""
        if not self.disponible():
            return self._sin_conexion()
        borrador = None
        if not str(clave or "").strip() and self._ultimo_borrador:
            try:
                borrador = self._por_id(self._ultimo_borrador)
            except ErrorCorreo:
                borrador = None
        if borrador is None:
            try:
                borrador = self._buscar_borrador(clave)
            except ErrorCorreo as e:
                self._error = str(e)
                return self._sin_conexion()
        if borrador is None:
            return ("No encontré ese borrador en tu correo. Pídeme 'lee mis correos' "
                    "y lo revisamos.")
        asunto = str(borrador.get("subject") or "").strip() or "(sin asunto)"
        destinatarios = "; ".join(
            str((destino.get("emailAddress") or {}).get("address") or "")
            for destino in (borrador.get("toRecipients") or [])).strip("; ")
        try:
            self._graph("POST", f"/me/messages/{borrador['id']}/send", json_cuerpo={})
        except ErrorCorreo as e:
            return f"No pude enviar el borrador: {e}"
        self._ultimo_borrador = ""
        return (f"Borrador enviado: '{asunto}'"
                + (f" a {destinatarios}." if destinatarios else "."))

    def crear_borrador(self, destinatario, asunto, cuerpo):
        """Crea un correo nuevo y lo guarda en Borradores (sin enviarlo)."""
        destinatario = str(destinatario or "").strip()
        if not destinatario:
            return "¿A quién le mando el correo? Dime el destinatario."
        if not self.disponible():
            return self._sin_conexion()
        direcciones = self._direcciones(destinatario)
        if not direcciones:
            return f"'{destinatario}' no parece una dirección de correo."
        nuevo = {
            "subject": str(asunto or "").strip(),
            "body": {"contentType": "HTML", "content": self._texto_a_html(cuerpo)},
            "toRecipients": [{"emailAddress": {"address": d}} for d in direcciones],
        }
        try:
            creado = self._graph("POST", "/me/messages", json_cuerpo=nuevo)
        except ErrorCorreo as e:
            return f"No pude crear el borrador: {e}"
        self._ultimo_borrador = str(creado.get("id") or "")
        return (f"Borrador creado para {destinatario} con asunto '{asunto}'. "
                "Está en Borradores; dime 'envía ese correo' para mandarlo.")

    # ------------------------------------------------------------------ Organizar
    def _carpetas(self):
        """Carpetas del buzón (id, nombre), incluyendo un nivel de subcarpetas."""
        if self._carpetas_cache is not None:
            return self._carpetas_cache
        encontradas = []
        datos = self._graph("GET", "/me/mailFolders",
                            params={"$top": 200,
                                    "$select": "id,displayName,childFolderCount"})
        for carpeta in datos.get("value") or []:
            encontradas.append((str(carpeta.get("id") or ""),
                                str(carpeta.get("displayName") or "")))
            if int(carpeta.get("childFolderCount") or 0) > 0:
                try:
                    hijas = self._graph("GET",
                                        f"/me/mailFolders/{carpeta['id']}/childFolders",
                                        params={"$top": 200, "$select": "id,displayName"})
                except ErrorCorreo:
                    continue
                for hija in hijas.get("value") or []:
                    encontradas.append((str(hija.get("id") or ""),
                                        str(hija.get("displayName") or "")))
        self._carpetas_cache = encontradas
        return encontradas

    def _carpeta_por_nombre(self, nombre):
        """Busca una carpeta del buzón por su nombre (ignora acentos y mayúsculas)."""
        buscado = self._sin_acentos(nombre)
        if not buscado:
            return None
        for identificador, display in self._carpetas():
            if self._sin_acentos(display) == buscado:
                return (identificador, display)
        return None

    def _carpeta_archivo(self, nombre=None):
        """Carpeta donde archivar un correo (None si no se encuentra ninguna)."""
        if nombre:
            return self._carpeta_por_nombre(nombre)
        for candidato in self.NOMBRES_ARCHIVO:
            encontrada = self._carpeta_por_nombre(candidato)
            if encontrada:
                return encontrada
        return None

    def etiquetar(self, clave, etiqueta):
        """Pone (o quita, con '-etiqueta') una categoría al correo.

        Son las mismas categorías de color que se ven en el Outlook nuevo.
        """
        etiqueta = str(etiqueta or "").strip()
        if not etiqueta:
            return "¿Con qué etiqueta quieres marcar el correo?"
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        lista = [str(c).strip() for c in (mensaje.get("categories") or []) if str(c).strip()]
        quitar = etiqueta.startswith("-")
        nombre = etiqueta[1:].strip() if quitar else etiqueta
        if quitar:
            lista = [c for c in lista
                     if self._sin_acentos(c) != self._sin_acentos(nombre)]
        elif not any(self._sin_acentos(c) == self._sin_acentos(nombre) for c in lista):
            lista.append(nombre)
        datos = self._resumen(mensaje)
        try:
            self._graph("PATCH", f"/me/messages/{mensaje['id']}",
                        json_cuerpo={"categories": lista})
        except ErrorCorreo as e:
            return f"No pude etiquetar el correo: {e}"
        return (f"Etiqueta {'quitada' if quitar else 'puesta'}: '{datos['asunto']}' "
                f"ahora tiene: {', '.join(lista) if lista else '(ninguna)'}.")

    def archivar(self, clave, carpeta=None):
        """Mueve un correo a una carpeta del buzón (por defecto, la de archivo)."""
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        datos = self._resumen(mensaje)
        try:
            destino = self._carpeta_archivo(carpeta)
        except ErrorCorreo as e:
            self._error = str(e)
            return self._sin_conexion()
        if destino is None:
            if carpeta:
                nombres = [display for _i, display in self._carpetas()]
                return (f"No encontré la carpeta '{carpeta}'. Carpetas disponibles: "
                        f"{', '.join(nombres[:12]) if nombres else '(ninguna legible)'}. "
                        "Dime a cuál lo muevo o créala en Outlook.")
            # Carpeta de archivo estándar del buzón (la que usa el propio Outlook)
            destino = (ARCHIVO, "Archivo")
        identificador, nombre_destino = destino
        try:
            self._graph("POST", f"/me/messages/{mensaje['id']}/move",
                        json_cuerpo={"destinationId": identificador})
        except ErrorCorreo as e:
            return f"No pude archivar el correo: {e}"
        return f"Correo '{datos['asunto']}' movido a la carpeta {nombre_destino}."

    def marcar(self, clave, leido=True):
        """Marca un correo como leído o como no leído."""
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        datos = self._resumen(mensaje)
        try:
            self._graph("PATCH", f"/me/messages/{mensaje['id']}",
                        json_cuerpo={"isRead": bool(leido)})
        except ErrorCorreo as e:
            return f"No pude cambiar el estado del correo: {e}"
        return (f"Correo '{datos['asunto']}' marcado como "
                f"{'leído' if leido else 'no leído'}.")

    def eliminar(self, clave):
        """Mueve un correo a Elementos eliminados (se puede recuperar)."""
        mensaje, error = self._resolver(clave)
        if mensaje is None:
            return error
        datos = self._resumen(mensaje)
        try:
            self._graph("DELETE", f"/me/messages/{mensaje['id']}")
        except ErrorCorreo as e:
            return f"No pude eliminar el correo: {e}"
        return f"Correo '{datos['asunto']}' movido a Elementos eliminados."


def main(argumentos=None):
    """Pequeña consola para conectar y probar el correo.

      python -m modules.correo_nube entrar    # conectar (una sola vez)
      python -m modules.correo_nube probar    # comprobar la conexión
      python -m modules.correo_nube salir     # olvidar la sesión guardada
    """
    orden = (argumentos if argumentos is not None else sys.argv[1:])
    accion = (orden[0].lower() if orden else "ayuda")
    cliente = CorreoNube()
    if accion in ("entrar", "conectar"):
        ok, mensaje = cliente.entrar(avisar=lambda texto: print(texto, flush=True))
        print(mensaje)
        return 0 if ok else 1
    if accion in ("probar", "test"):
        print(f"Cuenta conectada: {cliente.cuenta() or '(no lo sé)'}")
        print(cliente.leer_correos(3))
        return 0
    if accion in ("salir", "olvidar"):
        _ok, mensaje = cliente.salir()
        print(mensaje)
        return 0
    print(__doc__)
    print("Órdenes: entrar | probar | salir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
