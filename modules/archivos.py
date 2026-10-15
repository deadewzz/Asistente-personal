"""Explorador de archivos locales (OneDrive incluido) y operaciones de mover/copiar.

Da la lógica de archivos a Jarvis: listar carpetas, buscar dentro de ellas y mover
o copiar archivos de una carpeta a otra. No depende de la interfaz gráfica ni de
tokens: OneDrive es una carpeta local sincronizada, así que todo se hace con `os`
y `shutil`.

Se usa desde dos sitios:
- El mini-explorador de la ventana (`app_gui.py`) consume `listar`, `buscar`,
  `mover` y `copiar`.
- Las acciones del asistente (`LISTAR_CARPETA`, `BUSCAR_EN_CARPETA`,
  `MOVER_ARCHIVOS`, `COPIAR_ARCHIVOS`) llaman a estos mismos métodos.

Seguridad: `mover` y `copiar` nunca hacen nada sin `confirmado=True`; sin
confirmación solo devuelven la vista previa (qué se movería y a dónde).
"""

import os
import shutil

# Carpetas que se ignoran al buscar de forma recursiva (aceleran la búsqueda y
# evitan ruido de cachés, entornos virtuales, repositorios o papeleras).
EXCLUIDAS = {"AppData", "node_modules", ".git", "venv", "__pycache__", ".cache",
             "Library", "$Recycle.Bin", "System Volume Information"}


class Explorador:
    """Navegación y movimiento de archivos sobre el disco local."""

    def raices(self):
        """Carpetas raíz sugeridas para empezar a navegar (OneDrive, usuario...).

        Devuelve una lista de rutas existentes sin duplicados: primero OneDrive
        (si está sincronizado) y luego las carpetas habituales del usuario.
        """
        candidatas = []
        for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
            valor = os.environ.get(variable)
            if valor and os.path.isdir(valor):
                candidatas.append(valor)
        hogar = os.path.expanduser("~")
        for nombre in ("Documents", "Desktop", "Downloads"):
            ruta = os.path.join(hogar, nombre)
            if os.path.isdir(ruta):
                candidatas.append(ruta)
        candidatas.append(hogar)
        vistas = []
        for ruta in candidatas:
            clave = os.path.normcase(ruta)
            if clave not in {os.path.normcase(v) for v in vistas}:
                vistas.append(ruta)
        return vistas

    @staticmethod
    def normalizar(ruta):
        """Limpia y resuelve una ruta escrita por el usuario o por la IA.

        Quita comillas, expande variables de entorno y '~', y la convierte en una
        ruta absoluta y sin separadores redundantes.
        """
        ruta = (ruta or "").strip().strip('"').strip("'").strip("`")
        if not ruta:
            return ""
        ruta = os.path.expandvars(os.path.expanduser(ruta))
        ruta = os.path.normpath(ruta)
        if not os.path.isabs(ruta):
            ruta = os.path.abspath(ruta)
        return ruta

    def listar(self, carpeta):
        """Contenido de una carpeta: directorios primero y luego archivos.

        Devuelve una lista de dicts {nombre, ruta, es_carpeta, tamano} o None si
        la carpeta no existe o no se puede leer.
        """
        carpeta = self.normalizar(carpeta)
        if not carpeta or not os.path.isdir(carpeta):
            return None
        try:
            entradas = os.listdir(carpeta)
        except OSError:
            return None
        directorios, archivos = [], []
        for nombre in entradas:
            ruta = os.path.join(carpeta, nombre)
            try:
                if os.path.isdir(ruta):
                    directorios.append({"nombre": nombre, "ruta": ruta,
                                        "es_carpeta": True, "tamano": 0})
                else:
                    archivos.append({"nombre": nombre, "ruta": ruta,
                                     "es_carpeta": False,
                                     "tamano": os.path.getsize(ruta)})
            except OSError:
                continue
        directorios.sort(key=lambda d: d["nombre"].lower())
        archivos.sort(key=lambda d: d["nombre"].lower())
        return directorios + archivos

    def buscar(self, carpeta, nombre, max_resultados=60):
        """Archivos cuyo nombre contiene 'nombre' dentro de 'carpeta' (recursivo).

        Devuelve una lista de rutas absolutas (solo archivos). Ignora las carpetas
        de EXCLUIDAS para no arrastrar cachés ni repositorios.
        """
        carpeta = self.normalizar(carpeta)
        nombre = (nombre or "").strip().lower()
        if not carpeta or not os.path.isdir(carpeta) or not nombre:
            return []
        resultados = []
        for base, dirs, files in os.walk(carpeta):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d not in EXCLUIDAS]
            for archivo in files:
                if nombre in archivo.lower():
                    resultados.append(os.path.join(base, archivo))
                    if len(resultados) >= max_resultados:
                        return resultados
        return resultados

    def _separar(self, origen):
        """Normaliza una lista de rutas o una cadena separada por ';'."""
        if isinstance(origen, (list, tuple)):
            items = list(origen)
        else:
            items = str(origen).split(";")
        rutas = []
        for item in items:
            ruta = self.normalizar(item)
            if ruta:
                rutas.append(ruta)
        return rutas

    def _plan(self, origenes, destino):
        """Valida orígenes y destino y calcula la ruta final de cada elemento.

        Devuelve (plan, errores): 'plan' es una lista de (origen, destino_final)
        y 'errores' los problemas encontrados.
        """
        destino = self.normalizar(destino)
        plan, errores = [], []
        if not destino or not os.path.isdir(destino):
            errores.append(f"destino no válido o inexistente: {destino or '(vacío)'}")
        for origen in origenes:
            if not os.path.exists(origen):
                errores.append(f"no existe: {origen}")
                continue
            if destino and os.path.isdir(destino):
                plan.append((origen, os.path.join(destino, os.path.basename(origen))))
        return plan, errores

    @staticmethod
    def _sin_colision(ruta):
        """Si 'ruta' ya existe, añade ' (2)', ' (3)'... antes de la extensión."""
        if not os.path.exists(ruta):
            return ruta
        base, extension = os.path.splitext(ruta)
        i = 2
        while os.path.exists(f"{base} ({i}){extension}"):
            i += 1
        return f"{base} ({i}){extension}"

    def mover(self, origen, destino, confirmado=False):
        """Mueve archivos/carpetas de 'origen' a 'destino'.

        'origen' puede ser una ruta, varias separadas por ';' o una lista.
        Sin `confirmado=True` solo devuelve la vista previa; con confirmación
        ejecuta el movimiento. Nunca sobrescribe: ante un choque de nombres
        renombra automáticamente ('archivo (2).ext').
        """
        origenes = self._separar(origen)
        plan, errores = self._plan(origenes, destino)
        resultado = {"accion": "mover", "confirmado": confirmado,
                     "plan": plan, "errores": errores, "hechos": [], "fallos": []}
        if not confirmado:
            return resultado
        for origen, destino_final in plan:
            try:
                destino_final = self._sin_colision(destino_final)
                shutil.move(origen, destino_final)
                resultado["hechos"].append(destino_final)
            except Exception as e:
                resultado["fallos"].append(f"{origen}: {e}")
        return resultado

    def copiar(self, origen, destino, confirmado=False):
        """Igual que `mover`, pero copiando (conserva el original)."""
        origenes = self._separar(origen)
        plan, errores = self._plan(origenes, destino)
        resultado = {"accion": "copiar", "confirmado": confirmado,
                     "plan": plan, "errores": errores, "hechos": [], "fallos": []}
        if not confirmado:
            return resultado
        for origen, destino_final in plan:
            try:
                destino_final = self._sin_colision(destino_final)
                if os.path.isdir(origen):
                    shutil.copytree(origen, destino_final)
                else:
                    shutil.copy2(origen, destino_final)
                resultado["hechos"].append(destino_final)
            except Exception as e:
                resultado["fallos"].append(f"{origen}: {e}")
        return resultado

    # ---------------- Texto legible (para las acciones y la ventana) ----------------
    def resumen(self, resultado):
        """Convierte el resultado de `mover`/`copiar` en un texto claro."""
        accion = resultado["accion"]
        gerundio = "mover" if accion == "mover" else "copiar"
        participio = "Movidos" if accion == "mover" else "Copiados"
        plan = resultado["plan"]
        lineas = []
        if not plan:
            lineas.append(f"No hay nada que {gerundio}.")
        elif not resultado["confirmado"]:
            lineas.append(f"Voy a {gerundio} {len(plan)} elemento(s):")
            for origen, destino_final in plan:
                lineas.append(f"  {os.path.basename(origen)}  →  {destino_final}")
            lineas.append("Confirma si quieres que lo haga.")
        else:
            lineas.append(f"{participio} {len(resultado['hechos'])} "
                          f"de {len(plan)} elemento(s):")
            for ruta in resultado["hechos"]:
                lineas.append(f"  ✓ {ruta}")
        if resultado["fallos"]:
            lineas.append("Fallos:")
            lineas.extend(f"  ✗ {f}" for f in resultado["fallos"])
        if resultado["errores"]:
            lineas.append("Problemas:")
            lineas.extend(f"  ✗ {e}" for e in resultado["errores"])
        return "\n".join(lineas)

    def listar_texto(self, carpeta):
        """Listado legible de una carpeta, listo para mostrar al usuario."""
        entradas = self.listar(carpeta)
        if entradas is None:
            return f"No pude abrir la carpeta: {carpeta}"
        if not entradas:
            return f"La carpeta está vacía: {carpeta}"
        lineas = [f"Contenido de {carpeta} ({len(entradas)}):"]
        for entrada in entradas:
            icono = "📁" if entrada["es_carpeta"] else "📄"
            lineas.append(f"{icono} {entrada['nombre']}")
        return "\n".join(lineas)

