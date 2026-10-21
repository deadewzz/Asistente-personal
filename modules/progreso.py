"""Lo que el asistente está haciendo, contado en vivo a quien lo esté mirando.

Las tareas de verdad tardan: abrir Brave con la sesión de SharePoint, recorrer las
subcarpetas de una biblioteca, pedirle a la IA que coloque cada documento, mover
decenas de archivos... Antes la ventana solo sabía decir "Jarvis está escribiendo",
así que no había manera de distinguir "está leyendo" de "se ha atascado".

Este módulo es el canal por el que esas tareas cuentan sus pasos:

- ``paso(texto)``: empieza un paso (es lo que está haciendo ahora mismo).
- ``hecho(texto)``: cierra el paso en curso con su resultado.
- ``aviso(texto)``: algo que conviene mirar (una rama sin permiso, un archivo que
  no se pudo mover) aunque el trabajo siga.

Quién escucha lo pone quien dibuja: la ventana conecta un receptor que salta al
hilo de Tk (``after``), y los diagnósticos de consola usan ``a_consola``. Sin
receptor no se hace nada, así que las pruebas y los módulos usados sueltos se
quedan en silencio.
"""

#: Marca de cada tipo de línea, para pintarla igual en la ventana y en consola.
MARCAS = {"paso": "→", "hecho": "✓", "aviso": "!"}


class Progreso:
    """Canal de pasos en vivo. Se puede llamar desde cualquier hilo."""

    def __init__(self, receptor=None):
        self._receptor = receptor

    def conectar(self, receptor):
        """Fija quién recibe los pasos: ``receptor(texto, tipo)``."""
        self._receptor = receptor

    def desconectar(self):
        """Deja de informar (sin receptor no se hace nada)."""
        self._receptor = None

    def paso(self, texto):
        self._emitir("paso", texto)

    def hecho(self, texto):
        self._emitir("hecho", texto)

    def aviso(self, texto):
        self._emitir("aviso", texto)

    def _emitir(self, tipo, texto):
        # Una sola línea: los nombres vienen de SharePoint o del disco y pueden
        # traer saltos o espacios de más que rompen el rótulo de la ventana.
        limpio = " ".join(str(texto or "").split())
        if not limpio or self._receptor is None:
            return
        try:
            self._receptor(limpio, tipo)
        except Exception as e:
            # Informar de un paso no puede tumbar el trabajo de verdad.
            print(f"[progreso] no pude informar del paso: {e}")


def a_consola(texto, tipo="paso"):
    """Receptor sencillo para consola (diagnósticos y ejecuciones sin ventana)."""
    print(f"  {MARCAS.get(tipo, '·')} {texto}")
