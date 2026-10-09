"""Matriz en la nube: exporta a Excel (OneDrive/SharePoint) y publica en Azure DevOps.

- Excel: escribe un .xlsx con openpyxl. Si el archivo está dentro de una carpeta
  sincronizada de OneDrive/SharePoint, se sube solo a la nube (NO hace falta API key).
  Con 'excel_url' se descarga el documento publicado; si además se indica
  'excel_sync_dir' (la carpeta sincronizada de esa biblioteca de SharePoint), la copia
  se baja y se edita ahí, de modo que OneDrive sube los cambios a SharePoint solo.
- Azure DevOps: crea work items con la API REST usando un PAT (token personal).
  El PAT NO es una "API key de administrador": lo genera cada usuario en
  https://dev.azure.com/<org>/_usersSettings/tokens y sirve como contraseña básica.

La configuración vive en config_usuario.json:

    {
      "matriz": {
        "excel_path": "C:/Users/tu_usuario/OneDrive - Empresa/Matriz.xlsx",
        "excel_url": "https://empresa.sharepoint.com/sites/x/Shared Documents/Matriz.xlsx",
        "excel_sync_dir": "C:/Users/tu_usuario/OneDrive - Empresa/Shared Documents",
        "hoja": "Matriz",
        "columnas": ["ID", "Requisito", "Tipo", "Prioridad", "Estado", "Responsable", "Observaciones"]
      },
      "azure_devops": {
        "org": "https://dev.azure.com/MiOrganizacion",
        "project": "MiProyecto",
        "pat": "",
        "tipo_item": "Requirement",
        "area_path": "",
        "iteration_path": ""
      }
    }
"""

import os
import json
import base64
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from modules import rutas

# Columnas por defecto de la matriz de requisitos (se pueden cambiar en la config).
COLUMNAS_DEFECTO = ["ID", "Requisito", "Tipo", "Prioridad", "Estado", "Responsable", "Observaciones"]


class CloudMatrix:
    """Llena una matriz en Excel (nube vía OneDrive/SharePoint) y en Azure DevOps."""

    def __init__(self, config_path=rutas.CONFIG_USUARIO, dir_salida=rutas.MATRICES):
        self.config_path = config_path
        self.dir_salida = dir_salida
        self.error_ruta = ""   # último error al resolver/descargar el Excel
        os.makedirs(self.dir_salida, exist_ok=True)

    # ---------------- Configuración ----------------
    def _config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"[cloud_matrix] No pude leer la configuración: {e}")
        return {}

    def _cfg_matriz(self):
        cfg = self._config().get("matriz") or {}
        return cfg if isinstance(cfg, dict) else {}

    def _cfg_azure(self):
        cfg = self._config().get("azure_devops") or {}
        return cfg if isinstance(cfg, dict) else {}

    def config_matriz(self):
        """Configuración del Excel (para la interfaz)."""
        return self._cfg_matriz()

    def config_azure(self):
        """Configuración de Azure DevOps (para la interfaz)."""
        return self._cfg_azure()

    def columnas(self):
        cols = self._cfg_matriz().get("columnas")
        if isinstance(cols, list) and cols:
            return [str(c).strip() for c in cols]
        return list(COLUMNAS_DEFECTO)

    def hoja(self):
        return (self._cfg_matriz().get("hoja") or "Matriz").strip()

    def ruta_excel(self, ruta=None):
        """Ruta local del .xlsx de la matriz.

        Prioridad: parámetro -> 'excel_path' -> descargar de 'excel_url' -> carpeta local.
        Si el archivo está en una carpeta sincronizada de OneDrive/SharePoint, se sube solo.
        Devuelve None si no se pudo resolver (el motivo queda en self.error_ruta).
        """
        self.error_ruta = ""
        ruta = ruta or self._cfg_matriz().get("excel_path")
        if ruta:
            return os.path.expandvars(os.path.expanduser(str(ruta).strip().strip('"')))
        if self._cfg_matriz().get("excel_url"):
            return self.descargar_excel()
        return os.path.join(self.dir_salida, "Matriz.xlsx")

    def descargar_excel(self, url=None, forzar=False, carpeta_sincronizada=None):
        """Descarga el .xlsx desde una URL (p. ej. un enlace de SharePoint) y devuelve la
        ruta local donde queda la copia.

        El destino es la carpeta sincronizada de OneDrive/SharePoint si está configurada
        ('excel_sync_dir'): así OneDrive sube los cambios al documento de SharePoint solo.
        Si no, se guarda una copia local en la carpeta de matrices (no se sube).
        'carpeta_sincronizada' permite indicar esa carpeta sin guardar la configuración
        (lo usa el diálogo cuando escribes la carpeta y pulsas "Descargar URL ahora").

        Si la copia local ya se bajó de esa misma URL, se reutiliza tal cual para no
        perder las filas que se le hayan añadido (usa forzar=True para bajarla de nuevo).
        Devuelve None si falla (el motivo queda en self.error_ruta).
        """
        url = str(url or self._cfg_matriz().get("excel_url") or "").strip()
        self.error_ruta = ""
        if not url:
            self.error_ruta = "No hay ninguna URL de Excel configurada."
            return None
        destino = self._destino_descarga(url, carpeta_sincronizada)
        if not forzar and os.path.exists(destino) and self._origen_coincide(destino, url):
            return destino
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (Jarvis)")
            with urllib.request.urlopen(req, timeout=30) as resp:
                datos = resp.read()
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as f:
                f.write(datos)
        except Exception as e:
            self.error_ruta = f"No pude descargar el Excel desde la URL: {e}"
            return None
        self._registrar_origen(destino, url)
        return destino

    def carpeta_sincronizada(self):
        """Carpeta sincronizada de OneDrive/SharePoint donde dejar la copia descargada.

        Si está configurada, la copia del Excel de la URL vive dentro de esa carpeta y
        OneDrive sube los cambios a SharePoint automáticamente (sin API key ni tokens).
        Devuelve "" si no está configurada o si la carpeta no existe.
        """
        ruta = str(self._cfg_matriz().get("excel_sync_dir") or "").strip().strip('"')
        if not ruta:
            return ""
        ruta = os.path.expandvars(os.path.expanduser(ruta))
        return ruta if os.path.isdir(ruta) else ""

    def _destino_descarga(self, url, carpeta_sincronizada=None):
        """Ruta local donde se guarda la copia del Excel publicado en una URL.

        Conserva el nombre del documento remoto para que OneDrive lo reconozca como el
        mismo archivo de SharePoint (y lo actualice en vez de crear uno nuevo).
        """
        nombre = "Matriz_descargada.xlsx"
        try:
            base = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))
            if base.lower().endswith((".xlsx", ".xlsm")):
                nombre = base
        except Exception:
            pass
        if carpeta_sincronizada is None:
            carpeta = self.carpeta_sincronizada()
        else:
            ruta = str(carpeta_sincronizada).strip().strip('"')
            ruta = os.path.expandvars(os.path.expanduser(ruta)) if ruta else ""
            carpeta = ruta if os.path.isdir(ruta) else ""
        return os.path.join(carpeta or self.dir_salida, nombre)

    # ---------------- Origen de las descargas (control de copias) ----------------
    def _indice_descargas(self):
        """Fichero local con el origen de cada copia (queda fuera de la carpeta compartida
        para no ensuciar la biblioteca de SharePoint)."""
        return os.path.join(self.dir_salida, "_origenes_descargas.json")

    def _leer_indice(self):
        try:
            with open(self._indice_descargas(), "r", encoding="utf-8") as f:
                datos = json.load(f)
                return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def _registrar_origen(self, destino, url):
        """Anota de qué URL salió cada copia local y cuándo."""
        indice = self._leer_indice()
        indice[os.path.abspath(destino)] = {
            "url": url, "descargado": datetime.now().isoformat(timespec="seconds")}
        try:
            with open(self._indice_descargas(), "w", encoding="utf-8") as f:
                json.dump(indice, f, indent=2)
        except Exception as e:
            print(f"[cloud_matrix] No pude guardar el índice de descargas: {e}")

    def origen_descarga(self, destino):
        """Datos (URL y fecha) de la descarga que dio lugar a 'destino', si se conocen."""
        return self._leer_indice().get(os.path.abspath(str(destino))) or {}

    def _origen_coincide(self, destino, url):
        """True si la copia local se descargó de esta misma URL."""
        return str(self.origen_descarga(destino).get("url", "")).strip() == url

    def pat(self):
        """Token de Azure DevOps: primero la variable de entorno, luego la config."""
        return (os.environ.get("AZURE_DEVOPS_PAT", "").strip()
                or str(self._cfg_azure().get("pat", "")).strip())

    # ---------------- Datos desde el portapapeles ----------------
    def _normalizar(self, valor):
        return "".join(ch for ch in str(valor).lower() if ch.isalnum())

    def _es_encabezado(self, celdas, columnas):
        """Detecta la fila de títulos (p. ej. al pegar un rango de Excel)."""
        if len(celdas) < 2:
            return False
        n_celdas = [self._normalizar(c) for c in celdas]
        n_cols = [self._normalizar(c) for c in columnas]
        return n_celdas == n_cols[:len(n_celdas)]

    def filas_desde_texto(self, texto, columnas=None):
        """Convierte texto pegado en filas (lista de listas).

        Acepta TSV (copiado de Excel), CSV con ';' o ',' y también una celda por
        línea. Ignora la fila de encabezado si coincide con las columnas.
        """
        columnas = columnas or self.columnas()
        filas = []
        if not texto or not texto.strip():
            return filas
        for linea in texto.splitlines():
            if not linea.strip():
                continue
            if "\t" in linea:
                celdas = [c.strip() for c in linea.split("\t")]
            elif ";" in linea:
                celdas = [c.strip() for c in linea.split(";")]
            elif "," in linea:
                celdas = [c.strip() for c in linea.split(",")]
            else:
                celdas = [linea.strip()]
            if self._es_encabezado(celdas, columnas):
                continue
            filas.append(celdas)
        return filas

    def _fila_a_campos(self, fila):
        """Convierte una fila en un diccionario usando las columnas configuradas."""
        cols = self.columnas()
        datos = {}
        for i, valor in enumerate(fila):
            clave = cols[i] if i < len(cols) else f"Campo{i + 1}"
            datos[clave] = str(valor).strip()
        return datos

    # ---------------- Excel (nube vía OneDrive/SharePoint) ----------------
    def exportar_excel(self, filas, encabezados=None, ruta=None, hoja=None):
        """Añade las filas al .xlsx indicado. Crea el archivo (con encabezados) si no existe."""
        try:
            import openpyxl
        except Exception:
            return ("No se pudo exportar a Excel: falta la librería 'openpyxl' "
                    "(instálala con: pip install openpyxl).")
        encabezados = encabezados or self.columnas()
        ruta = self.ruta_excel(ruta)
        if not ruta:
            return self.error_ruta or "No pude resolver la ruta del Excel de la matriz."
        hoja = hoja or self.hoja()
        try:
            carpeta = os.path.dirname(ruta)
            if carpeta:
                os.makedirs(carpeta, exist_ok=True)
            if os.path.exists(ruta):
                wb = openpyxl.load_workbook(ruta)
                ws = wb[hoja] if hoja in wb.sheetnames else wb.create_sheet(hoja)
                if ws.cell(row=1, column=1).value is None:
                    ws.append(list(encabezados))
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = hoja
                ws.append(list(encabezados))
            for fila in filas:
                ws.append(list(fila))
            wb.save(ruta)
        except Exception as e:
            return f"No pude escribir el Excel: {e}"
        return f"Excel actualizado (+{len(filas)} fila(s)): {ruta}"

    # ---------------- Azure DevOps (REST API + PAT) ----------------
    def _descripcion_html(self, campos):
        lineas = []
        for clave, valor in campos.items():
            if valor and self._normalizar(clave) != "titulo":
                lineas.append(f"<b>{clave}:</b> {valor}")
        return "<br>".join(lineas)

    def _crear_work_item(self, org, proyecto, pat, tipo_item, campos):
        """Crea un work item y devuelve su id."""
        cfg = self._cfg_azure()
        id_val = campos.get("ID") or campos.get("Id")
        titulo = (campos.get("Titulo") or campos.get("Título") or campos.get("Requisito")
                  or id_val or "Nuevo elemento")
        # Prefija el ID para mantener la trazabilidad con la matriz (p. ej. "RF-01 - Login").
        if id_val and str(id_val) not in str(titulo):
            titulo = f"{id_val} - {titulo}"
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": titulo},
            {"op": "add", "path": "/fields/System.Description",
             "value": self._descripcion_html(campos)},
        ]
        if cfg.get("area_path"):
            patch.append({"op": "add", "path": "/fields/System.AreaPath",
                          "value": str(cfg["area_path"]).strip()})
        if cfg.get("iteration_path"):
            patch.append({"op": "add", "path": "/fields/System.IterationPath",
                          "value": str(cfg["iteration_path"]).strip()})

        url = (f"{org}/{urllib.parse.quote(proyecto)}/_apis/wit/workitems/"
               f"${urllib.parse.quote(tipo_item)}?api-version=7.0")
        credenciales = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            url, data=json.dumps(patch).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json-patch+json")
        req.add_header("Authorization", f"Basic {credenciales}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                info = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {e.code}: {detalle}") from e
        return info.get("id", "?")

    def publicar_azure_devops(self, filas, tipo_item=None):
        """Crea un work item por cada fila en el proyecto de Azure DevOps."""
        cfg = self._cfg_azure()
        org = str(cfg.get("org", "")).strip().rstrip("/")
        proyecto = str(cfg.get("project", "")).strip()
        pat = self.pat()
        if not org or not proyecto:
            return ("Azure DevOps no está configurado: añade 'azure_devops' "
                    "(org y project) en config_usuario.json.")
        if not pat:
            return ("Falta el token de Azure DevOps. Genera un PAT en "
                    "https://dev.azure.com/<tu-organizacion>/_usersSettings/tokens y "
                    "pégalo en la configuración o en la variable AZURE_DEVOPS_PAT.")
        tipo_item = (tipo_item or cfg.get("tipo_item") or "Requirement").strip()
        creados = 0
        errores = []
        for fila in filas:
            if not fila or not any(str(c).strip() for c in fila):
                continue
            try:
                wi = self._crear_work_item(org, proyecto, pat, tipo_item,
                                           self._fila_a_campos(fila))
                print(f"[cloud_matrix] Work item creado: {wi}")
                creados += 1
            except Exception as e:
                errores.append(str(e))
        msg = f"Azure DevOps ({proyecto}): {creados} work item(s) creado(s)."
        if errores:
            msg += f" {len(errores)} con error. Primer error -> {errores[0]}"
        return msg

    def probar_azure(self, org=None, project=None, pat=None):
        """Comprueba la conexión con Azure DevOps (sin crear nada). Devuelve un mensaje."""
        cfg = self._cfg_azure()
        org = str(org if org is not None else cfg.get("org", "")).strip().rstrip("/")
        project = str(project if project is not None else cfg.get("project", "")).strip()
        pat = str(pat if pat is not None else self.pat()).strip()
        if not org or not project or not pat:
            return "Faltan datos: organización, proyecto y token (PAT)."
        url = f"{org}/_apis/projects/{urllib.parse.quote(project)}?api-version=7.0"
        credenciales = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Basic {credenciales}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                info = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "Token inválido o sin permisos (HTTP 401). Revisa el PAT."
            if e.code == 404:
                return "No encontré el proyecto (HTTP 404). Revisa organización/proyecto."
            detalle = e.read().decode("utf-8", "replace")[:200]
            return f"Error HTTP {e.code}: {detalle}"
        except Exception as e:
            return f"No pude conectar con Azure DevOps: {e}"
        return f"Conexión correcta con el proyecto '{info.get('name', project)}'."

    # ---------------- Acción conjunta ----------------
    def llenar(self, texto, destino="ambos"):
        """Llena la matriz a partir de un texto (normalmente el portapapeles).

        destino: 'excel', 'azure' o 'ambos'.
        """
        filas = self.filas_desde_texto(texto)
        if not filas:
            return ("No encontré datos para llenar la matriz. Copia los datos "
                    "(columnas separadas por tabulador, ';' o ',') y vuelve a pedirlo.")
        destino = (destino or "ambos").strip().lower()
        resultados = []
        if destino in ("ambos", "excel"):
            resultados.append(self.exportar_excel(filas))
        if destino in ("ambos", "azure", "azuredevops", "devops"):
            resultados.append(self.publicar_azure_devops(filas))
        return " ".join(resultados)
