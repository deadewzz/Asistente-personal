"""Los apartados de Jarvis: uno por módulo y cada uno una vista de la ventana."""
from views.ajustes import VistaAjustes
from views.chat import VistaChat
from views.ingles import VistaIngles
from views.programacion import VistaProgramacion

__all__ = ["VistaAjustes", "VistaChat", "VistaIngles", "VistaProgramacion"]
