"""Puerta de entrada al correo: elige el mejor cliente disponible en este equipo.

- Si ya conectaste el correo por la nube (`python -m modules.correo_nube entrar`),
  se usa ese: funciona con el **Outlook nuevo**, que no expone ninguna API local.
- Si no, y el equipo tiene **Outlook clásico** registrado, se usa por COM como antes.
- Si no hay ninguna de las dos cosas, se devuelve el cliente de nube sin sesión: sus
  métodos no fallan, explican cómo conectar el correo.

Así el resto del asistente (`system_actions`, `api_brain`) no necesita saber de qué
forma se está hablando con el buzón.
"""

from modules import rutas
from modules.correo_nube import CorreoNube
from modules.outlook_tools import OutlookTools


def crear_cliente_correo(config_path=rutas.CONFIG_USUARIO):
    """Devuelve el cliente de correo utilizable en este equipo (nunca falla)."""
    nube = CorreoNube(config_path)
    if nube.disponible():
        return nube
    if OutlookTools.com_disponible():
        return OutlookTools(config_path)
    return nube
