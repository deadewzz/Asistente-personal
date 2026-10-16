"""Correo de Outlook de escritorio (Windows, vía COM).

Lee el buzón, lo resume y clasifica, extrae pendientes y permite responder,
etiquetar, archivar y marcar correos usando el Outlook que ya está configurado
en el equipo (perfil MAPI): no hacen falta credenciales ni registrar ninguna
aplicación en la nube.

Reglas de seguridad:
- Ninguna acción envía correo por su cuenta: 'responder' guarda un BORRADOR en
  Outlook y solo se envía si se pide explícitamente (o con 'enviar_borrador').
- Si Outlook no está instalado, no hay perfil o falla la conexión, los métodos
  devuelven un mensaje claro en lugar de lanzar una excepción.
"""

import re
import time
import unicodedata
from datetime import datetime

from modules import rutas


class OutlookTools:
    """Lectura y gestión del correo a través de Outlook de escritorio (COM)."""

    # Carpetas estándar de Outlook (valores de olDefaultFolders)
    ELIMINADOS = 3
    ENVIADOS = 5
    BANDEJA = 6
    BORRADORES = 16

    # Cuántos correos recientes se revisan como máximo al listar o buscar
    LIMITE_BARRIDO = 80
    # Caracteres de cuerpo que se muestran por correo en un listado
    LARGO_EXTRACTO = 300
    # Caracteres de cuerpo que se pasan a la IA al leer un correo completo
    LARGO_CUERPO = 4000
    # Nombres habituales de la carpeta de archivo (por orden de preferencia)
    NOMBRES_ARCHIVO = ("archivo", "archive", "archivados", "historico")

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path
        self.outlook = None
        # Correos del último listado mostrado: permiten referirse a ellos por número
        self._ultimo_listado = []
        # Último borrador preparado por el asistente (para poder enviarlo después)
        self._ultimo_borrador = ""
        # True cuando Outlook está abierto pero aún sin sesión con la cuenta
        self._sin_sesion = False

    # ------------------------------------------------------------------ Conexión
    # Se recuerda si el equipo tiene Outlook clásico registrado (chequeo barato)
    _com_cache = None

    @classmethod
    def com_disponible(cls):
        """True si hay Outlook clásico registrado en el equipo (sin llegar a abrirlo).

        El Outlook nuevo (`olk.exe`) NO expone este COM: en esos equipos el correo
        se usa a través de `modules.correo_nube` (Microsoft Graph).
        """
        if cls._com_cache is None:
            cls._com_cache = cls._com_registrado()
        return cls._com_cache

    def disponible(self):
        """True si en este equipo se puede leer el correo (con Outlook clásico).

        Es el mismo contrato que ``CorreoNube.disponible()``, para que el resto
        del asistente pueda preguntarle '¿tienes correo?' al cliente que tenga
        delante sin saber de qué forma se habla con el buzón (``modules.correo``
        elige uno u otro según el equipo).
        """
        return self.com_disponible()

    @staticmethod
    def _com_registrado():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"):
                return True
        except Exception:
            return False

    def _conectar(self):
        """Conecta con Outlook. Es idempotente: reutiliza la conexión abierta."""
        if self.outlook is not None:
            return True
        try:
            import win32com.client
            self.outlook = win32com.client.Dispatch("Outlook.Application")
            return True
        except Exception:
            self.outlook = None
            return False

    def _namespace(self):
        if not self._conectar():
            return None
        try:
            return self.outlook.GetNamespace("MAPI")
        except Exception as e:
            print(f"[outlook] No pude acceder al buzón: {e}")
            return None

    def _carpeta(self, carpeta=None):
        """Carpeta estándar de Outlook por su número (por defecto, la bandeja).

        Si Outlook acaba de arrancar puede tardar un instante en conectar con la
        cuenta ('no está conectado'), así que se reintenta un par de veces antes
        de darse por vencido.
        """
        ns = self._namespace()
        if ns is None:
            return None
        numero = self.BANDEJA if carpeta is None else carpeta
        ultimo_error = None
        for intento in range(3):
            try:
                self._sin_sesion = False
                return ns.GetDefaultFolder(numero)
            except Exception as e:
                ultimo_error = e
                if "conectad" in str(e).lower():
                    self._sin_sesion = True
                if intento < 2:
                    time.sleep(1.5)
        print(f"[outlook] No pude abrir la carpeta {numero}: {ultimo_error}")
        return None

    def _items(self, carpeta=None, solo_no_leidos=False):
        """Ítems de una carpeta, del más reciente al más antiguo."""
        contenedor = self._carpeta(carpeta)
        if contenedor is None:
            return None
        try:
            items = contenedor.Items
        except Exception as e:
            print(f"[outlook] No pude leer los ítems de la carpeta: {e}")
            return None
        if solo_no_leidos:
            try:
                items = items.Restrict("[UnRead] = True")
            except Exception:
                pass
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:
            pass
        return items

    def _sin_outlook(self):
        if self._sin_sesion:
            return ("Outlook está abierto pero todavía no ha conectado con la cuenta "
                    "(muestra 'No está conectado'). Abre Outlook, comprueba que ves "
                    "tus correos y pídemelo otra vez.")
        return ("No pude conectar con el Outlook clásico. Comprueba que está instalado y "
                "con la cuenta configurada (si acabas de abrirlo, vuelve a intentarlo). "
                "Si usas el Outlook nuevo, conecta el correo por la nube una sola vez con "
                "'python -m modules.correo_nube entrar' y pídemelo otra vez.")

    # ------------------------------------------------------------------ Utilidades
    @staticmethod
    def _fecha(valor):
        """Formatea una fecha de Outlook como 'AAAA-MM-DD HH:MM'."""
        try:
            if hasattr(valor, "strftime"):
                return valor.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        return str(valor or "")[:16]

    @staticmethod
    def _fecha_dia(valor):
        """Devuelve el día de una fecha de Outlook, o None si no se puede leer."""
        try:
            if hasattr(valor, "date"):
                return valor.date()
            if hasattr(valor, "year"):
                return datetime(valor.year, valor.month, valor.day).date()
        except Exception:
            pass
        return None

    @staticmethod
    def _limpiar(texto, largo, colapsar=True):
        """Normaliza el cuerpo de un correo y lo recorta a 'largo' caracteres."""
        cadena = str(texto or "")
        if colapsar:
            # Las líneas decorativas del HTML (____, ----, ====) no aportan nada.
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

    def _resumen(self, item, indice=None):
        """Extrae de un correo los datos que se muestran y se recuerdan."""
        try:
            asunto = (item.Subject or "(sin asunto)").strip()
        except Exception:
            asunto = "(sin asunto)"
        try:
            remitente = (item.SenderName or "").strip()
        except Exception:
            remitente = ""
        try:
            fecha = self._fecha(item.ReceivedTime)
        except Exception:
            fecha = "sin fecha"
        try:
            no_leido = bool(item.UnRead)
        except Exception:
            no_leido = False
        try:
            cuerpo = self._limpiar(item.Body, self.LARGO_EXTRACTO)
        except Exception:
            cuerpo = ""
        try:
            entry_id = str(item.EntryID)
        except Exception:
            entry_id = ""
        return {
            "indice": indice,
            "asunto": asunto,
            "de": remitente or "(remitente desconocido)",
            "fecha": fecha,
            "no_leido": no_leido,
            "cuerpo": cuerpo,
            "entry_id": entry_id,
        }

    @classmethod
    def _coincide(cls, datos, termino):
        """True si 'termino' aparece en el asunto, el remitente o el cuerpo."""
        buscado = cls._sin_acentos(termino)
        if not buscado:
            return True
        texto = cls._sin_acentos(f"{datos['asunto']} {datos['de']} {datos['cuerpo']}")
        return buscado in texto

    # ------------------------------------------------------------------ Listado
    def listar(self, n=8, solo_no_leidos=False, desde_hoy=False, termino=None):
        """Lista los correos más recientes de la bandeja de entrada.

        Devuelve una lista de diccionarios (indice, asunto, de, fecha, no_leido,
        cuerpo, entry_id), o None si no se pudo conectar con Outlook. Los correos
        listados se recuerdan para poder referirse a ellos por su número después.
        """
        items = self._items(solo_no_leidos=solo_no_leidos)
        if items is None:
            return None
        try:
            total = int(items.Count)
        except Exception:
            total = 0
        hoy = datetime.now().date()
        limite = max(1, int(n))
        resultados = []
        for i in range(1, min(total, self.LIMITE_BARRIDO) + 1):
            if len(resultados) >= limite:
                break
            try:
                item = items.Item(i)
            except Exception:
                continue
            if desde_hoy:
                dia = self._fecha_dia(getattr(item, "ReceivedTime", None))
                if dia is not None and dia < hoy:
                    continue
            datos = self._resumen(item, indice=len(resultados) + 1)
            if termino and not self._coincide(datos, termino):
                continue
            resultados.append(datos)
        self._ultimo_listado = resultados
        return resultados

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

    def leer_correos(self, n=5):
        """Lista los correos más recientes: remitente, asunto, hora y extracto."""
        correos = self.listar(n=n)
        if correos is None:
            return self._sin_outlook()
        if not correos:
            return "No hay correos en la bandeja de entrada."
        return self._formatear_lista(correos, f"Tus últimos {len(correos)} correos:")

    def resumen(self, criterio="", n=10):
        """Listado según criterio ('hoy', 'no leídos', un número) para resumirlo."""
        texto = self._sin_acentos(criterio)
        solo_no_leidos = ("no le" in texto or "sin leer" in texto
                          or "unread" in texto)
        desde_hoy = "hoy" in texto or "today" in texto
        numero = re.search(r"\d+", texto)
        if numero:
            n = int(numero.group())
        correos = self.listar(n=n, solo_no_leidos=solo_no_leidos, desde_hoy=desde_hoy)
        if correos is None:
            return self._sin_outlook()
        if not correos:
            if solo_no_leidos:
                return "No tienes correos sin leer en la bandeja de entrada."
            if desde_hoy:
                return "No has recibido correos hoy."
            return "No hay correos en la bandeja de entrada."
        etiqueta = "sin leer" if solo_no_leidos else ("de hoy" if desde_hoy else "recientes")
        return self._formatear_lista(correos, f"Correos {etiqueta} ({len(correos)}):")

    def buscar(self, consulta, n=10):
        """Busca en asunto, remitente y cuerpo de los correos más recientes."""
        consulta = (consulta or "").strip()
        if not consulta:
            return "¿Qué quieres que busque en el correo?"
        correos = self.listar(n=n, termino=consulta)
        if correos is None:
            return self._sin_outlook()
        if not correos:
            return f"No encontré correos que mencionen '{consulta}'."
        return self._formatear_lista(correos, f"Correos que mencionan '{consulta}':")

    def detalle(self, clave):
        """Cuerpo completo de un correo (o el motivo por el que no se encontró)."""
        item, error = self._resolver(clave)
        if item is None:
            return error
        datos = self._resumen(item)
        try:
            cuerpo = self._limpiar(item.Body, self.LARGO_CUERPO, colapsar=False)
        except Exception:
            cuerpo = ""
        return (f"De {datos['de']} ({datos['fecha']})\n"
                f"Asunto: {datos['asunto']}\n\n{cuerpo or '(sin cuerpo)'}")

    # ------------------------------------------------------------------ Localizar un correo
    def _por_entry_id(self, entry_id):
        """Recupera un correo por su identificador interno de Outlook."""
        if not entry_id:
            return None
        ns = self._namespace()
        if ns is None:
            return None
        try:
            return ns.GetItemFromID(str(entry_id))
        except Exception as e:
            print(f"[outlook] No pude recuperar el correo: {e}")
            return None

    def _resolver(self, clave):
        """Localiza un correo por su número del último listado o por su texto.

        Devuelve (item, mensaje) donde 'mensaje' explica el motivo cuando el
        correo no se encontró (item es None en ese caso).
        """
        texto = str(clave or "").strip()
        if not texto:
            return None, ("¿A qué correo te refieres? Pídeme primero 'lee mis correos' "
                          "y dime el número o el nombre del remitente.")
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
                    item = self._por_entry_id(registro.get("entry_id"))
                    if item is not None:
                        return item, ""
                    return None, (f"El correo {numero} ya no está en el buzón (¿lo moviste o "
                                  "lo borraste?). Pídeme 'lee mis correos' otra vez.")
            return None, (f"En la última lista que te mostré no había un correo número "
                          f"{numero}. Pídeme primero 'lee mis correos'.")
        correos = self.listar(n=15, termino=texto)
        if correos is None:
            return None, self._sin_outlook()
        if not correos:
            return None, (f"No encontré ningún correo que coincida con '{texto}'. "
                          "Pídeme 'lee mis correos' y dime su número.")
        item = self._por_entry_id(correos[0].get("entry_id"))
        if item is None:
            return None, "Ese correo ya no está en el buzón."
        return item, ""

    # ------------------------------------------------------------------ Carpetas
    def _carpetas_raiz(self):
        """Nombres de las carpetas de primer nivel del buzón (para poder elegir)."""
        nombres = []
        ns = self._namespace()
        if ns is None:
            return nombres
        try:
            almacenes = ns.Folders
            total_almacenes = almacenes.Count
        except Exception:
            return nombres
        for i in range(1, total_almacenes + 1):
            try:
                carpetas = almacenes.Item(i).Folders
                total = carpetas.Count
            except Exception:
                continue
            for j in range(1, total + 1):
                try:
                    nombres.append(str(carpetas.Item(j).Name))
                except Exception:
                    continue
        return nombres

    def _carpeta_por_nombre(self, nombre):
        """Busca una carpeta del buzón por su nombre (ignora acentos y mayúsculas)."""
        buscado = self._sin_acentos(nombre)
        if not buscado:
            return None
        ns = self._namespace()
        if ns is None:
            return None
        try:
            almacenes = ns.Folders
            total_almacenes = almacenes.Count
        except Exception:
            return None
        for i in range(1, total_almacenes + 1):
            try:
                carpetas = almacenes.Item(i).Folders
                total = carpetas.Count
            except Exception:
                continue
            for j in range(1, total + 1):
                try:
                    carpeta = carpetas.Item(j)
                    if self._sin_acentos(carpeta.Name) == buscado:
                        return carpeta
                except Exception:
                    continue
        return None

    def _carpeta_archivo(self, nombre=None):
        """Carpeta donde archivar un correo (None si no existe ninguna)."""
        if nombre:
            return self._carpeta_por_nombre(nombre)
        for candidato in self.NOMBRES_ARCHIVO:
            carpeta = self._carpeta_por_nombre(candidato)
            if carpeta is not None:
                return carpeta
        return None

    # ------------------------------------------------------------------ Responder
    def responder(self, clave, texto, enviar=False):
        """Responde a un correo (por defecto deja la respuesta en Borradores).

        Solo envía si 'enviar' es True, algo que el asistente activa únicamente
        cuando el usuario lo pide de forma explícita. El texto de la respuesta se
        coloca encima del correo original citado.
        """
        if not str(texto or "").strip():
            return "No me diste el texto de la respuesta."
        item, error = self._resolver(clave)
        if item is None:
            return error
        datos = self._resumen(item)
        try:
            respuesta = item.Reply()
        except Exception as e:
            return f"No pude preparar la respuesta: {e}"
        try:
            original = str(respuesta.Body or "")
        except Exception:
            original = ""
        try:
            respuesta.Body = str(texto).strip() + ("\n\n" + original if original else "")
        except Exception as e:
            return f"No pude escribir la respuesta: {e}"
        try:
            if enviar:
                respuesta.Send()
                return f"Respuesta enviada a {datos['de']} (Re: {datos['asunto']})."
            respuesta.Save()
        except Exception as e:
            return f"No pude {'enviar' if enviar else 'guardar'} la respuesta: {e}"
        try:
            self._ultimo_borrador = str(respuesta.EntryID)
        except Exception:
            self._ultimo_borrador = ""
        return (f"Dejé la respuesta preparada en la carpeta Borradores para {datos['de']} "
                f"(Re: {datos['asunto']}). Dime 'envía ese correo' para mandarla.")

    def _buscar_borrador(self, clave=None):
        """Localiza un borrador por texto de asunto, número o el más reciente."""
        items = self._items(self.BORRADORES)
        if items is None:
            return None
        try:
            total = int(items.Count)
        except Exception:
            total = 0
        texto = self._sin_acentos(clave)
        mas_reciente = None
        for i in range(1, total + 1):
            try:
                item = items.Item(i)
            except Exception:
                continue
            if mas_reciente is None:
                mas_reciente = item
            if not texto:
                continue
            if texto.isdigit() and i == int(texto):
                return item
            if texto in self._sin_acentos(getattr(item, "Subject", "")):
                return item
        return mas_reciente

    def enviar_borrador(self, clave=None):
        """Envía el borrador que se acaba de preparar (o uno que coincida)."""
        item = None
        if not str(clave or "").strip() and self._ultimo_borrador:
            item = self._por_entry_id(self._ultimo_borrador)
        if item is None:
            item = self._buscar_borrador(clave)
        if item is None:
            return "No encontré ese borrador en Outlook. Pídeme 'lee mis correos' y lo revisamos."
        try:
            asunto = str(getattr(item, "Subject", "") or "(sin asunto)")
            destinatarios = ""
            try:
                destinatarios = str(item.To or "")
            except Exception:
                pass
            item.Send()
        except Exception as e:
            return f"No pude enviar el borrador: {e}"
        self._ultimo_borrador = ""
        return (f"Borrador enviado: '{asunto}'"
                + (f" a {destinatarios}." if destinatarios else "."))

    def crear_borrador(self, destinatario, asunto, cuerpo):
        """Crea un correo nuevo y lo guarda en Borradores (sin enviarlo)."""
        destinatario = str(destinatario or "").strip()
        if not destinatario:
            return "¿A quién le mando el correo? Dime el destinatario."
        if not self._conectar():
            return self._sin_outlook()
        try:
            mail = self.outlook.CreateItem(0)  # 0 = MailItem
            mail.To = destinatario
            mail.Subject = str(asunto or "").strip()
            mail.Body = str(cuerpo or "")
            mail.Save()  # queda en la carpeta Borradores
        except Exception as e:
            return f"No pude crear el borrador: {e}"
        self._ultimo_borrador = str(getattr(mail, "EntryID", "") or "")
        return (f"Borrador creado para {destinatario} con asunto '{asunto}'. "
                "Está en Borradores; dime 'envía ese correo' para mandarlo.")

    # ------------------------------------------------------------------ Organizar
    def etiquetar(self, clave, etiqueta):
        """Pone (o quita, con '-etiqueta') una categoría de Outlook al correo."""
        etiqueta = str(etiqueta or "").strip()
        if not etiqueta:
            return "¿Con qué etiqueta quieres marcar el correo?"
        item, error = self._resolver(clave)
        if item is None:
            return error
        try:
            actuales = str(getattr(item, "Categories", "") or "")
        except Exception:
            actuales = ""
        lista = [c.strip() for c in actuales.split(",") if c.strip()]
        quitar = etiqueta.startswith("-")
        nombre = etiqueta[1:].strip() if quitar else etiqueta
        if quitar:
            lista = [c for c in lista
                     if self._sin_acentos(c) != self._sin_acentos(nombre)]
        elif not any(self._sin_acentos(c) == self._sin_acentos(nombre) for c in lista):
            lista.append(nombre)
        try:
            item.Categories = ", ".join(lista)
            item.Save()
        except Exception as e:
            return f"No pude etiquetar el correo: {e}"
        datos = self._resumen(item)
        return (f"Etiqueta {'quitada' if quitar else 'puesta'}: '{datos['asunto']}' "
                f"ahora tiene: {', '.join(lista) if lista else '(ninguna)'}.")

    def archivar(self, clave, carpeta=None):
        """Mueve un correo a una carpeta del buzón (por defecto, la de archivo)."""
        item, error = self._resolver(clave)
        if item is None:
            return error
        datos = self._resumen(item)
        destino = self._carpeta_archivo(carpeta)
        if destino is None:
            disponibles = self._carpetas_raiz()
            return (f"No encontré la carpeta '{carpeta or 'Archivo'}'. Carpetas "
                    f"disponibles: {', '.join(disponibles[:12]) if disponibles else '(ninguna legible)'}. "
                    "Dime a cuál lo muevo o créala en Outlook.")
        try:
            nombre_destino = str(destino.Name)
            item.Move(destino)
        except Exception as e:
            return f"No pude archivar el correo: {e}"
        return f"Correo '{datos['asunto']}' movido a la carpeta {nombre_destino}."

    def marcar(self, clave, leido=True):
        """Marca un correo como leído o como no leído."""
        item, error = self._resolver(clave)
        if item is None:
            return error
        datos = self._resumen(item)
        try:
            item.UnRead = not bool(leido)
            item.Save()
        except Exception as e:
            return f"No pude cambiar el estado del correo: {e}"
        return (f"Correo '{datos['asunto']}' marcado como "
                f"{'leído' if leido else 'no leído'}.")

    def eliminar(self, clave):
        """Mueve un correo a Elementos eliminados (Outlook lo permite recuperar)."""
        item, error = self._resolver(clave)
        if item is None:
            return error
        datos = self._resumen(item)
        try:
            item.Delete()
        except Exception as e:
            return f"No pude eliminar el correo: {e}"
        return f"Correo '{datos['asunto']}' movido a Elementos eliminados."
