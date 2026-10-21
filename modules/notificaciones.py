"""Avisos de escritorio de Windows (los «toasts» del centro de notificaciones).

Las tareas que avisan tardan minutos: transcribir una reunión y redactar su acta
puede terminar cuando ya estás en otra cosa, con la ventana de Jarvis detrás de
la reunión o cerrada. La voz suena una vez y se va; este aviso se queda en el
centro de notificaciones hasta que lo descartas, así que sirve para el «avísame
cuando lo tengas».

Se usa la API de Windows desde PowerShell (Windows 10 y 11 la traen de serie)
para no añadir dependencias. Lo único que se escribe en el equipo es el nombre
con el que se firman los avisos («Jarvis»), en HKCU y sin pedir permisos. El
aviso sale en su propio hilo y, si algo falla (no hay PowerShell, las
notificaciones están desactivadas en Windows…), se apunta en la consola: un
aviso no puede romper la tarea que estaba avisando.
"""

import base64
import os
import subprocess
import threading

#: Identificador con el que Windows firma los avisos (no lleva espacios).
APP_ID = "Jarvis.Asistente"

#: Nombre que se ve en el aviso y en el centro de notificaciones.
NOMBRE_APP = "Jarvis"

# El texto va por variables de entorno (y no incrustado en el script) para que
# los acentos, las comillas o los saltos de línea no rompan la orden.
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$plantilla = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $plantilla.GetElementsByTagName('text')
$textos.Item(0).AppendChild($plantilla.CreateTextNode($env:JARVIS_AVISO_TITULO)) | Out-Null
$textos.Item(1).AppendChild($plantilla.CreateTextNode($env:JARVIS_AVISO_TEXTO)) | Out-Null
$aviso = [Windows.UI.Notifications.ToastNotification]::new($plantilla)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:JARVIS_AVISO_APPID).Show($aviso)
"""


def _registrar_nombre():
    """Registra «Jarvis» como autora de los avisos (solo la primera vez hace algo).

    Windows no enseña los avisos de un programa que no está instalado si su
    identificador no existe; con esta clave en HKCU (permisos del propio
    usuario) el aviso aparece firmado «Jarvis» en vez de «Windows PowerShell».
    Es idempotente y, si no se puede escribir, se sigue igual: como mucho sale
    con el nombre del intérprete.
    """
    try:
        import winreg
        clave = r"Software\Classes\AppUserModelId" + "\\" + APP_ID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, clave) as registro:
            if winreg.QueryValueEx(registro, "DisplayName")[0] != NOMBRE_APP:
                winreg.SetValueEx(registro, "DisplayName", 0, winreg.REG_SZ, NOMBRE_APP)
    except Exception as e:
        print(f"[avisos] no pude registrar el nombre de la app: {e}")


def _comando():
    """Orden que muestra el aviso, o ``None`` si este sistema no puede.

    Se prefiere el PowerShell de Windows (5.1) porque es el que tiene cargada
    la API de notificaciones; `pwsh` (PowerShell 7) no la expone igual.
    """
    if os.name != "nt":
        return None
    programa = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                            "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.exists(programa):
        programa = "powershell.exe"
    codificado = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    return [programa, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-EncodedCommand", codificado]


def _mostrar(titulo, texto=""):
    """Muestra el aviso ahora mismo (bloquea hasta que PowerShell termina)."""
    # Un aviso es una sola línea por campo: los saltos de línea de un mensaje
    # largo (por ejemplo, un trozo de acta) rompen la plantilla del toast.
    titulo = " ".join(str(titulo or NOMBRE_APP).split()) or NOMBRE_APP
    texto = " ".join(str(texto or "").split())
    _registrar_nombre()
    orden = _comando()
    if orden is None:
        return
    entorno = dict(os.environ, JARVIS_AVISO_TITULO=titulo,
                   JARVIS_AVISO_TEXTO=texto, JARVIS_AVISO_APPID=APP_ID)
    try:
        subprocess.run(
            orden, env=entorno, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("[avisos] este Windows no tiene PowerShell; no pude mostrar el aviso.")
    except subprocess.TimeoutExpired:
        print("[avisos] PowerShell tardó demasiado mostrando el aviso.")
    except Exception as e:
        print(f"[avisos] no pude mostrar el aviso: {e}")


def avisar(titulo, texto=""):
    """Muestra un aviso de Windows sin bloquear a quien lo pide.

    Se llama desde cualquier hilo: el aviso sale en uno propio para que la
    transcripción, el correo o lo que estuviera haciendo siga su curso.
    """
    threading.Thread(target=_mostrar, args=(titulo, texto), daemon=True).start()
