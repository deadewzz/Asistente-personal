"""Prueba de la parte de correo de la ventana (Ajustes), sin efectos reales.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_gui_correo.py

- La app se crea con una configuración temporal (no toca la tuya).
- Se usa el `entrar()` DE VERDAD; lo único simulado es la capa HTTP (Microsoft) y
  la orden de abrir el navegador. Así se prueba también el token cifrado con DPAPI
  y el texto real del código de dispositivo.
- Se usa el `mainloop` de verdad, porque la ventana se actualiza con `after()`
  desde un hilo de fondo (igual que en la app en marcha).
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG = os.path.join(tempfile.gettempdir(), "jarvis_prueba_gui_correo.json")
fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    print(("  ok  " if condicion else "  FALLO  ") + texto)
    if not condicion:
        fallos.append(texto)


if os.path.exists(CONFIG):
    os.remove(CONFIG)
with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump({"nombre_asistente": "jarvis"}, f)

import app_gui
from modules.correo_nube import CorreoNube, ErrorCorreo

app = app_gui.AppGUI(config_path=CONFIG)
navegador = []
pasos = []

# Con qué cliente de correo arrancó el asistente. En un equipo con Outlook
# clásico registrado (COM), `crear_cliente_correo` usa ese y no el de la nube
# (ver `modules/correo.py`): en ese caso no se le puede pedir al cliente del
# asistente que refleje la sesión de la nube, y las comprobaciones de abajo se
# ciñen a lo que de verdad se puede afirmar en cada equipo.
ASISTENTE_EN_LA_NUBE = isinstance(app.system.outlook, CorreoNube)


def ejecutar(paso):
    """Corre un paso y sigue con el siguiente aunque falle (sin colgar la ventana)."""
    try:
        paso()
    except Exception as e:
        comprobar(False, f"el paso {paso.__name__} no debe fallar ({e!r})")
        avanzar(100)


def avanzar(retardo=300):
    """Ejecuta el siguiente paso (o cierra la ventana si ya no hay más)."""
    if pasos:
        app.after(retardo, lambda: ejecutar(pasos.pop(0)))
    else:
        app.after(retardo, app.quit)


def buscar_toplevel():
    for widget in app.winfo_children():
        if isinstance(widget, app_gui.ctk.CTkToplevel):
            return widget
    return None


def buscar_boton(contenedor, texto):
    for widget in contenedor.winfo_children():
        if (isinstance(widget, app_gui.ctk.CTkButton)
                and widget.cget("text") == texto):
            return widget
        dentro = buscar_boton(widget, texto)
        if dentro is not None:
            return dentro
    return None


def paso_1_arranque():
    print("== La ventana arranca con la sección de correo ==")
    comprobar(hasattr(app, "lbl_correo") and hasattr(app, "btn_conectar_correo")
              and hasattr(app, "btn_desconectar_correo"),
              "existen el botón 'Conectar correo' y la etiqueta de estado")
    comprobar("sin conectar" in app.lbl_correo.cget("text"),
              "al arrancar pone 'Correo: sin conectar'")
    comprobar(app.btn_conectar_correo.cget("text") == "Conectar correo",
              "el botón está listo para conectar")
    avanzar()


def paso_2_sesion_ajena():
    print("\n== Un asistente ya abierto ve la conexión hecha después ==")
    CorreoNube(CONFIG)._guardar_ajustes({"token": "t-temporal", "cifrado": False,
                                         "cuenta": "yo@acme.com"})
    if ASISTENTE_EN_LA_NUBE:
        comprobar(app.system.outlook.disponible() is True,
                  "el módulo de correo del asistente ya ve la sesión")
    else:
        comprobar(app.system.outlook.disponible() is True,
                  "con Outlook clásico en el equipo, el asistente ya tiene "
                  "correo y no necesita la sesión de la nube")
    app._actualizar_estado_correo()
    comprobar("Correo conectado: yo@acme.com" in app.lbl_correo.cget("text"),
              "Ajustes muestra la cuenta conectada")
    comprobar("nunca envía" in app.lbl_correo.cget("text"),
              "y recuerda que no envía nada solo")
    avanzar()


def paso_3_conectar():
    print("\n== Conectar correo (módulo real, Microsoft simulado) ==")
    CorreoNube(CONFIG).salir()
    app_gui.webbrowser.open = lambda url: navegador.append(url)

    def pedir_json_falso(self, url, metodo="POST", form=None, json_cuerpo=None,
                         cabeceras=None):
        if "devicecode" in url:
            return {"user_code": "B7RK9R6ND", "interval": 0, "expires_in": 900,
                    "verification_uri": "https://microsoft.com/devicelogin"}
        return {"access_token": "token-de-prueba", "refresh_token": "refresco-1",
                "expires_in": 3600}

    CorreoNube._pedir_json = pedir_json_falso       # sin red
    CorreoNube._graph = lambda self, metodo, ruta, json_cuerpo=None, params=None, \
        reintentar=True: {"mail": "yo@acme.com", "displayName": "Yo"}
    app._conectar_correo()
    comprobar(app.btn_conectar_correo.cget("text") == "Esperando el código..."
              and app.btn_conectar_correo.cget("state") == "disabled",
              "mientras espera, el botón queda desactivado")
    avanzar(800)


def paso_4_esperando():
    texto = app.lbl_correo.cget("text")
    comprobar(navegador == ["https://microsoft.com/devicelogin"],
              "se abre el navegador de Microsoft una sola vez")
    comprobar("B7RK9R6ND" in texto,
              "el código real del módulo se ve en la ventana")
    comprobar("minutos" in texto, "y también cuánto tiempo tienes para escribirlo")
    comprobar("Preparando" not in texto, "la línea de 'preparando' desaparece")
    avanzar(6500)                       # el módulo espera entre 3 y 5 s antes de preguntar


def paso_5_resultado():
    comprobar("Correo conectado: yo@acme.com" in app.lbl_correo.cget("text")
              and app.btn_conectar_correo.cget("state") == "normal",
              "al terminar, el mensaje de éxito y el botón rearmado")
    comprobar(app.system.outlook.disponible() is True,
              "y el asistente ya puede leer el correo")
    guardado = CorreoNube(CONFIG).ajustes()
    comprobar(guardado.get("cuenta") == "yo@acme.com" and guardado.get("cifrado") is True,
              "la cuenta y el token cifrado quedan guardados")
    comprobar(CorreoNube(CONFIG)._token_guardado() == "refresco-1",
              "el token se descifra bien (DPAPI) al volver a leerlo")
    avanzar()


def paso_6_errores():
    print("\n== Errores y desconexión ==")
    app._correo_resuelto(False, "Se acabó el tiempo para escribir el código.")
    comprobar("Se acabó el tiempo" in app.lbl_correo.cget("text"),
              "un fallo se enseña tal cual")

    def pedir_json_caido(self, url, metodo="POST", form=None, json_cuerpo=None,
                         cabeceras=None):
        raise ErrorCorreo("no hay conexión con Microsoft")

    CorreoNube._pedir_json = pedir_json_caido
    app._conectar_correo()
    avanzar(800)


def paso_7_error_de_red():
    comprobar("No pude iniciar la conexión con tu correo"
              in app.lbl_correo.cget("text"),
              "un fallo de red se explica en la ventana")
    comprobar(app.btn_conectar_correo.cget("state") == "normal",
              "y el botón vuelve a estar disponible")

    def entrar_roto(self, avisar=None, tiempo_max=900):
        raise RuntimeError("sin red")

    CorreoNube.entrar = entrar_roto
    app._conectar_correo()
    avanzar(800)


def paso_8_error_inesperado():
    comprobar("No pude conectar tu correo" in app.lbl_correo.cget("text"),
              "un error inesperado tampoco cuelga la ventana")
    CorreoNube(CONFIG)._guardar_ajustes({"token": "temporal", "cifrado": False,
                                         "cuenta": "yo@acme.com"})
    app._desconectar_correo()           # con sesión: pide confirmación
    avanzar(500)


def paso_9_dialogo():
    dialogo = buscar_toplevel()
    textos = ([w.cget("text") for w in dialogo.winfo_children()
               if isinstance(w, app_gui.ctk.CTkLabel)] if dialogo else [])
    comprobar(any("¿Olvidar la sesión" in str(t) for t in textos),
              "con sesión, desconectar pide confirmación")
    cancelar = buscar_boton(dialogo, "Cancelar") if dialogo else None
    confirmar = buscar_boton(dialogo, "Desconectar") if dialogo else None
    comprobar(cancelar is not None and confirmar is not None,
              "el diálogo tiene 'Desconectar' y 'Cancelar'")
    if confirmar is not None:
        confirmar.invoke()
    comprobar("Correo desconectado" in app.lbl_correo.cget("text"),
              "al confirmar, la ventana lo dice")
    comprobar(CorreoNube(CONFIG).disponible() is False,
              "y el token se borra del disco")
    comprobar(not ASISTENTE_EN_LA_NUBE or app.system.outlook.disponible() is False,
              "el cliente de la nube del asistente lo ve desconectado al momento")
    avanzar()


def paso_10_contrato():
    print("\n== Contrato del listado sin sesión ==")
    cliente = CorreoNube(CONFIG)
    comprobar(cliente.listar() is None, "sin sesión, listar() devuelve None")
    comprobar(str(cliente.leer_correos()).strip() != "",
              "y pedirlos nunca lanza excepción")
    avanzar()


pasos.extend([paso_1_arranque, paso_2_sesion_ajena, paso_3_conectar, paso_4_esperando,
              paso_5_resultado, paso_6_errores, paso_7_error_de_red,
              paso_8_error_inesperado, paso_9_dialogo, paso_10_contrato])
app.after(500, avanzar)
app.mainloop()
app.destroy()

if os.path.exists(CONFIG):
    os.remove(CONFIG)
print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
for fallo in fallos:
    print("  - " + fallo)
raise SystemExit(1 if fallos else 0)
