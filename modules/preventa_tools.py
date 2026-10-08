import os
from datetime import datetime

from modules import rutas


class PreventaTools:
    """Herramientas para preventa en análisis de software: genera documentos a partir
    de requerimientos (propuesta, matriz de requisitos, historias de usuario, glosario, etc.)."""

    TIPOS = {
        "propuesta": "propuesta técnica",
        "requisitos": "matriz de requisitos",
        "historias": "historias de usuario",
        "glosario": "glosario de términos",
        "resumen": "resumen ejecutivo",
        "estimacion": "estimación de esfuerzo",
    }

    def __init__(self, dir_salida=rutas.PREVENTA):
        self.dir_salida = dir_salida
        os.makedirs(self.dir_salida, exist_ok=True)
        self.on_generar = None  # callback (tipo, contenido) -> texto generado por la IA

    def generar(self, tipo, contenido):
        if not contenido or not contenido.strip():
            return "No hay contenido. Copia los requerimientos al portapapeles primero."
        tipo = (tipo or "").strip().lower()
        if tipo not in self.TIPOS:
            return f"Tipo de documento no reconocido: {tipo}. Usa: {', '.join(self.TIPOS.keys())}."
        nombre = self.TIPOS[tipo]
        if self.on_generar:
            try:
                texto = self.on_generar(tipo, contenido)
            except Exception as e:
                return f"Error generando el documento: {e}"
        else:
            texto = contenido
        fecha = datetime.now().strftime("%Y-%m-%d_%H%M")
        ruta = os.path.join(self.dir_salida, f"{fecha}_{tipo}.md")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(f"# {nombre.capitalize()}\n\n")
            f.write(f"**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(texto + "\n")
        return f"Documento de {nombre} creado: {ruta}"
