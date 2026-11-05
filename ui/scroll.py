"""Cómo se mueve la rueda del ratón: un paso más largo, igual en toda la app.

CustomTkinter mueve sus paneles poco a poco (unos 20 píxeles por muesca en
Windows). Aquí se cambia ese paso por uno más cómodo —y se usa el mismo al
reenviar la rueda desde las tarjetas o las burbujas, que si no se quedaban en 3
píxeles—, así el chat, las clases, la guía y el taller avanzan al mismo ritmo.

Se instala sola al importar el paquete `ui`: no hay que tocar cada panel.
"""
import sys

from customtkinter import CTkScrollableFrame

#: Píxeles que avanza el contenido por cada muesca de la rueda (antes, 20 de
#: CustomTkinter y solo 3 al reenviarla desde una tarjeta).
PASO_RUEDA = 80

#: Delta de una muesca estándar en Windows (240 = tres muescas de golpe).
DELTA_MUESCA = 120


def paso_de(evento):
    """Los píxeles que toca desplazar con esa muesca (con su signo).

    En Windows y Linux llega un `delta` grande por muesca; en macOS los del
    trackpad son pequeños y llegan muchos seguidos, así que se escala distinto.
    Se limita a tres muescas de golpe para que una rueda rápida no dé un salto.
    """
    delta = int(getattr(evento, "delta", 0) or 0)
    if delta:
        if sys.platform == "darwin":
            return -delta * max(1, PASO_RUEDA // 10)
        muescas = min(3, max(1, abs(delta) // DELTA_MUESCA))
        return (-1 if delta > 0 else 1) * PASO_RUEDA * muescas
    numero = getattr(evento, "num", None)       # Linux manda Button-4 / Button-5
    if numero == 4:
        return -PASO_RUEDA
    if numero == 5:
        return PASO_RUEDA
    return 0


def _rueda_rapida(self, evento):
    """La rueda de un `CTkScrollableFrame`, con el paso largo de la app."""
    try:
        valida = getattr(self, "_check_if_valid_scroll", None)
        if callable(valida) and not valida(evento.widget):
            return
        paso = paso_de(evento)
        if not paso:
            return
        lienzo = self._parent_canvas
        if getattr(self, "_shift_pressed", False):
            if lienzo.xview() != (0.0, 1.0):
                lienzo.xview_scroll(paso, "units")
        elif lienzo.yview() != (0.0, 1.0):
            lienzo.yview_scroll(paso, "units")
    except Exception:
        pass


def instalar_rueda_rapida():
    """Hace que todos los paneles con scroll usen el paso largo."""
    if getattr(CTkScrollableFrame, "_rueda_rapida_jarvis", False):
        return
    CTkScrollableFrame._mouse_wheel_all = _rueda_rapida
    CTkScrollableFrame._rueda_rapida_jarvis = True


#: Líneas que avanza una caja de texto con cada muesca de la rueda.
LINEAS_CAJA = 5


def acelerar_caja(caja, lineas=LINEAS_CAJA):
    """Hace que una caja de texto avance más con la rueda.

    Los `tk.Text` de Tk se mueven de una línea por muesca: las consolas, el
    editor y las cajas del chat se leen mejor yendo de varias en varias. Sirve
    tanto para un `tk.Text` como para un `CTkTextbox` (usa el de dentro).
    """
    texto = getattr(caja, "_textbox", caja)
    if texto is None:
        return caja

    def mover(evento):
        paso = paso_de(evento)
        if not paso:
            return "break"
        muescas = min(3, max(1, abs(paso) // PASO_RUEDA))
        try:
            texto.yview_scroll((1 if paso > 0 else -1) * muescas * lineas, "units")
        except Exception:
            pass
        return "break"

    for secuencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        texto.bind(secuencia, mover)
    return caja


instalar_rueda_rapida()
