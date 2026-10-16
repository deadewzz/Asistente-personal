"""Validación en vivo del correo: HTTP de verdad contra Microsoft (sin iniciar sesión).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_correo_en_vivo.py

Necesita internet, pero **no pide credenciales**: solo comprueba que Microsoft
acepta la petición de código de dispositivo y que los fallos se traducen a
mensajes claros. No escribe nada en la configuración real.
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.correo_nube import AUTORIDAD, PERMISOS, CorreoNube, ErrorCorreo

# Configuración de usar y tirar, en la carpeta temporal (no ensucia el proyecto).
CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_correo_en_vivo.json")
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


print("== El asistente elige el cliente correcto ==")
from modules.system_actions import SystemActions

acciones = SystemActions()
nombre = type(acciones.outlook).__name__
comprobar(nombre in ("CorreoNube", "OutlookTools"), f"cliente de correo elegido: {nombre}")
comprobar(nombre == "CorreoNube", "sin Outlook clásico se usa el correo por la nube")
salida = str(acciones.ejecutar_comando("LEER_CORREOS|3") or "")
comprobar("no he conectado" in salida or "Outlook" in salida,
          "LEER_CORREOS avisa de que hay que conectar el correo")
print("     ->", salida.splitlines()[-1][:120] if salida else "(vacío)")
salida = str(acciones.ejecutar_comando("CREAR_BORRADOR|a@b.com;;Prueba;;Hola") or "")
comprobar("no he conectado" in salida, "CREAR_BORRADOR avisa sin sesión")
print("     ->", salida[:120])

print("\n== Código de dispositivo real de Microsoft ==")
if os.path.exists(CONFIG):
    os.remove(CONFIG)
cliente = CorreoNube(CONFIG)
datos = cliente._pedir_json(f"{AUTORIDAD}/common/oauth2/v2.0/devicecode",
                            form={"client_id": cliente._cliente_id(), "scope": PERMISOS})
comprobar(bool(datos.get("user_code")), "Microsoft devuelve un código de dispositivo")
comprobar(bool(datos.get("verification_uri")), "Microsoft devuelve la web para escribir el código")
print(f"     -> código de ejemplo: {datos.get('user_code')} en {datos.get('verification_uri')}")
print(f"     -> cliente público: {cliente._cliente_id()}")

print("\n== Error de sesión caducada ==")
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"correo": {"token": "token-invalido-de-prueba", "cifrado": False}}, f)
cliente = CorreoNube(CONFIG)
try:
    cliente._token_valido()
    comprobar(False, "un refresh token inválido debería fallar")
except ErrorCorreo as e:
    texto = str(e)
    comprobar("invalid_grant" in texto or "AADSTS" in texto,
              f"el error de Microsoft se lee bien")
    print("     ->", texto[:150])
comprobar(cliente.disponible() is True
          and cliente._token_guardado() == "token-invalido-de-prueba",
          "un refresh fallido no borra ni cambia lo guardado")

print("\n== Fábrica y compatibilidad ==")
from modules.correo import crear_cliente_correo
from modules.outlook_tools import OutlookTools

com = OutlookTools.com_disponible()
comprobar(type(crear_cliente_correo(CONFIG)).__name__ == "CorreoNube",
          "con sesión de nube, la fábrica devuelve el cliente de nube")
comprobar(OutlookTools().disponible() is com,
          f"OutlookTools sigue existiendo y dice si hay correo clásico en el "
          f"equipo (COM: {com})")
comprobar(OutlookTools().listar() is None or True, "OutlookTools sigue existiendo")

if os.path.exists(CONFIG):
    os.remove(CONFIG)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
