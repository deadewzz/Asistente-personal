"""Calendario de Outlook por COM (primera parte de la fase 3: solo lectura).

Permite saber qué reunión está en curso, listar los próximos eventos y obtener
los invitados de un evento, que es lo que hace falta para la agenda previa (2.3)
y para enviar el acta a los asistentes (2.4).

Funciona con el Outlook de escritorio que ya está configurado (`pywin32`), así
que no necesita credenciales ni registrar aplicaciones. Si Outlook no está
abierto o está sin conexión, todos los métodos lo dicen y no lanzan el error.
"""

import time
from datetime import datetime, timedelta

try:
    import win32com.client
except ImportError:
    win32com = None


class CalendarioTools:
    """Lee el calendario de Outlook (eventos, reunión en curso e invitados)."""

    CALENDARIO = 9          # olFolderCalendar
    MAX_REVISION = 200      # eventos como máximo que se miran por consulta
    HORAS_ATRAS = 24        # hasta cuántas horas atrás se busca la reunión en curso

    def __init__(self):
        self.outlook = None
        self._ns = None
        self._sin_sesion = False
        self._mios = None

    # ------------------------------------------------------------ Conexión
    def _conectar(self):
        if win32com is None:
            return False
        if self.outlook is not None:
            return True
        try:
            self.outlook = win32com.client.Dispatch("Outlook.Application")
            return True
        except Exception as e:
            print(f"[calendario] No pude abrir Outlook: {e}")
            self.outlook = None
            return False

    def _namespace(self):
        if not self._conectar():
            return None
        if self._ns is not None:
            return self._ns
        try:
            self._ns = self.outlook.GetNamespace("MAPI")
        except Exception as e:
            print(f"[calendario] No pude abrir la sesión de Outlook: {e}")
            self._ns = None
        return self._ns

    def _sin_outlook(self):
        if self._sin_sesion:
            return ("Outlook está abierto pero todavía no ha conectado con la cuenta "
                    "(muestra 'No está conectado'). Abre Outlook, comprueba que ves tu "
                    "calendario y pídemelo otra vez.")
        return ("No pude leer el calendario de Outlook. Comprueba que Outlook está "
                "abierto y con la cuenta configurada.")

    def _items_calendario(self):
        """Elementos (citas) de la carpeta Calendario, con reintentos."""
        ns = self._namespace()
        if ns is None:
            return None
        for intento in range(3):
            try:
                self._sin_sesion = False
                return ns.GetDefaultFolder(self.CALENDARIO).Items
            except Exception as e:
                if "conectad" in str(e).lower():
                    self._sin_sesion = True
                if intento < 2:
                    time.sleep(1.5)
        return None

    def _iterar(self, items, limite=None):
        """Genera las citas de más nueva a más vieja a partir de la colección.

        Outlook no garantiza el orden de `Items.Item(i)` tras ordenar, así que se
        usa GetFirst/GetNext, que sí respeta el criterio de Sort. Empezar por las
        citas más nuevas permite cortar en cuanto se sale del rango de fechas que
        interesa, sin recorrer años de calendario.
        """
        try:
            items.Sort("[Start]", True)   # True = descendente
        except Exception:
            pass
        maximo = limite or self.MAX_REVISION
        try:
            cita = items.GetFirst()
        except Exception:
            cita = None
        revisados = 0
        while cita is not None and revisados < maximo:
            revisados += 1
            yield cita
            try:
                cita = items.GetNext()
            except Exception:
                cita = None

    # ------------------------------------------------------------ Utilidades
    @staticmethod
    def _fecha(valor):
        """Convierte un campo de fecha de Outlook a datetime (o None)."""
        if valor is None:
            return None
        try:
            return datetime(valor.year, valor.month, valor.day,
                            valor.hour, valor.minute)
        except Exception:
            return None

    def _mi_correo(self):
        """Direcciones propias, para no enviarse el acta a uno mismo."""
        if self._mios is not None:
            return self._mios
        direcciones = set()
        ns = self._namespace()
        if ns is not None:
            try:
                cuentas = ns.Accounts
                for i in range(1, cuentas.Count + 1):
                    try:
                        smtp = str(cuentas.Item(i).SmtpAddress or "").strip().lower()
                        if smtp:
                            direcciones.add(smtp)
                    except Exception:
                        continue
            except Exception:
                pass
        self._mios = direcciones
        return direcciones

    def _correo_de(self, destinatario):
        """Correo SMTP de un invitado (resuelve las direcciones de Exchange)."""
        entrada = None
        try:
            entrada = destinatario.AddressEntry
        except Exception:
            entrada = None
        if entrada is not None:
            # 0 = olExchangeUserAddressEntry: resuelve el SMTP real del usuario
            try:
                if int(getattr(entrada, "AddressEntryUserType", -1)) == 0:
                    usuario = entrada.GetExchangeUser()
                    if usuario is not None:
                        smtp = str(usuario.PrimarySmtpAddress or "").strip()
                        if smtp:
                            return smtp
            except Exception:
                pass
        direccion = str(getattr(destinatario, "Address", "") or "").strip()
        if "@" in direccion:
            return direccion
        nombre = str(getattr(destinatario, "Name", "") or "").strip()
        return nombre if "@" in nombre else ""

    def _invitados(self, cita):
        """(correos, nombres sin correo) de los invitados de la cita."""
        correos, sin_correo = [], []
        mios = self._mi_correo()
        try:
            destinatarios = cita.Recipients
            total = int(destinatarios.Count)
        except Exception:
            return correos, sin_correo
        for i in range(1, total + 1):
            try:
                destinatario = destinatarios.Item(i)
                correo = self._correo_de(destinatario)
                nombre = str(getattr(destinatario, "Name", "") or "").strip()
            except Exception:
                continue
            if correo:
                if correo.strip().lower() in mios:
                    continue
                if correo not in correos:
                    correos.append(correo)
            elif nombre and nombre not in sin_correo:
                sin_correo.append(nombre)
        return correos, sin_correo

    def datos(self, cita):
        """Datos legibles de una cita del calendario."""
        datos = {
            "asunto": str(getattr(cita, "Subject", "") or "(sin asunto)").strip(),
            "inicio": self._fecha(getattr(cita, "Start", None)),
            "fin": self._fecha(getattr(cita, "End", None)),
            "lugar": str(getattr(cita, "Location", "") or "").strip(),
            "organizador": str(getattr(cita, "Organizer", "") or "").strip(),
            "todo_el_dia": bool(getattr(cita, "AllDayEvent", False)),
        }
        datos["correos"], datos["sin_correo"] = self._invitados(cita)
        return datos

    # ------------------------------------------------------------ Consultas
    def evento_en_curso(self, margen_min=15):
        """Reunión que está ocurriendo ahora (o que empieza en 'margen_min').

        Devuelve (datos, mensaje): los datos de la cita, o (None, mensaje) si no
        hay ninguna o si Outlook no responde.
        """
        items = self._items_calendario()
        if items is None:
            return None, self._sin_outlook()
        ahora = datetime.now()
        limite_atras = ahora - timedelta(hours=self.HORAS_ATRAS)
        margen = timedelta(minutes=max(0, int(margen_min)))
        mejor = None
        for cita in self._iterar(items):
            datos = self.datos(cita)
            inicio, fin = datos["inicio"], datos["fin"]
            if inicio is None:
                continue
            if inicio < limite_atras:
                break            # ya estamos en citas demasiado antiguas
            if fin is None:
                fin = inicio + timedelta(hours=1)
            if inicio <= ahora + margen and fin >= ahora - margen:
                if mejor is None or inicio > mejor["inicio"]:
                    mejor = datos
        if mejor is None:
            return None, "No veo ninguna reunión en el calendario en este momento."
        return mejor, ""

    def proximos(self, dias=7, limite=15):
        """Próximas citas dentro de 'dias' (de la más próxima a la última)."""
        items = self._items_calendario()
        if items is None:
            return None, self._sin_outlook()
        ahora = datetime.now()
        tope = ahora + timedelta(days=max(1, int(dias)))
        limite_atras = ahora - timedelta(hours=self.HORAS_ATRAS)
        encontradas = []
        for cita in self._iterar(items):
            datos = self.datos(cita)
            inicio = datos["inicio"]
            if inicio is None:
                continue
            if inicio < limite_atras:
                break
            if ahora <= inicio <= tope:
                encontradas.append(datos)
        encontradas.sort(key=lambda d: d["inicio"])
        return encontradas[:limite], ""

    def invitados(self, asunto=None, margen_min=20):
        """Invitados de una reunión concreta (por asunto) o de la que está en curso.

        Devuelve (datos, mensaje): datos con asunto, inicio, correos y nombres sin
        correo, o (None, mensaje) si no encuentra la reunión.
        """
        items = self._items_calendario()
        if items is None:
            return None, self._sin_outlook()
        buscado = str(asunto or "").strip().lower()
        ahora = datetime.now()
        margen = timedelta(minutes=max(0, int(margen_min)))
        candidatas = []
        for cita in self._iterar(items):
            datos = self.datos(cita)
            inicio, fin = datos["inicio"], datos["fin"]
            if inicio is None:
                continue
            if inicio < ahora - timedelta(hours=self.HORAS_ATRAS) and not buscado:
                break
            if buscado:
                if buscado in datos["asunto"].lower():
                    candidatas.append(datos)
                    if len(candidatas) >= 3:
                        break
            elif inicio <= ahora + margen and (fin or inicio) >= ahora - margen:
                candidatas.append(datos)
        if not candidatas:
            if buscado:
                return None, f"No encontré ninguna reunión en el calendario con '{asunto}'."
            return None, "No veo ninguna reunión en el calendario ahora mismo."
        candidatas.sort(key=lambda d: abs((d["inicio"] - ahora).total_seconds()))
        return candidatas[0], ""

    def texto_evento(self, datos, con_invitados=True):
        """Línea legible de una cita (para el prompt de la IA o para la voz)."""
        inicio = datos["inicio"].strftime("%Y-%m-%d %H:%M") if datos.get("inicio") else "?"
        texto = f"{inicio} — {datos.get('asunto', '(sin asunto)')}"
        if datos.get("lugar"):
            texto += f" (lugar: {datos['lugar']})"
        if datos.get("organizador"):
            texto += f" [organiza: {datos['organizador']}]"
        if con_invitados:
            correos = datos.get("correos") or []
            if correos:
                texto += " — invitados: " + ", ".join(correos)
            sin_correo = datos.get("sin_correo") or []
            if sin_correo:
                texto += " — sin correo en la cita: " + ", ".join(sin_correo)
        return texto

