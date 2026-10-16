"""Prueba EN VIVO de la copia entre sitios (bajar de uno y subir a otro).

Se ejecuta desde la raíz del proyecto, con las dos URLs:

    python tests/pruebas_copia_en_vivo.py "URL_ORIGEN" "URL_DESTINO" [gordo]

Ejemplo (llevar archivos de un sitio de equipo a tu unidad):

    python tests/pruebas_copia_en_vivo.py ^
      "https://empresa.sharepoint.com/sites/Preventa-Solutions" ^
      "https://empresa-my.sharepoint.com/"

Con ``gordo`` (tercer argumento) prueba además el camino de los archivos
GRANDES: el más pesado del origen se baja a tu PC por trozos y se sube al
destino con la subida por trozos de SharePoint. Es lo que hace Jarvis con los
que pasan de ``TAMANO_POR_DISCO`` (10 MB) porque SharePoint deja a medias los
``MoveTo``/``CopyTo`` de unos pocos MB.

Prueba el camino que NO puede hacer SharePoint solo: mover o copiar entre
sitios distintos (la API solo sabe `MoveTo`/`CopyTo` dentro del mismo sitio),
o sea: bajar el archivo con la sesión de Brave y volverlo a subir. Es el paso
que se rompe si el token de escritura (`X-RequestDigest`) o el cuerpo binario
están mal, así que merece una prueba de verdad contra el tenant.

Paso a paso:
1. Brave controlable por CDP (se abre o se reinicia si hace falta).
2. Resuelve las dos URLs y ENSEÑA el sitio y la carpeta con los que se queda (la
   raíz de un sitio -> su biblioteca de documentos; en OneDrive, 'Mi unidad' =
   `/personal/<usuario>/Documents`). Si algo va mal, aquí se ve el porqué.
3. Lista el origen (bajando también a sus subcarpetas) y baja el archivo MÁS
   PEQUEÑO; si la carpeta no tiene archivos (las hay que solo tienen carpetas,
   una por cliente) los busca un par de niveles más abajo, y comprueba que
   llegan bytes. Solo mira los **documentos de oficina** (ppt, pptx, doc y
   docx): los vídeos y demás que haya en esas carpetas se saltan, y el módulo
   dice en qué carpetas están.
4. Sube un archivo de prueba al destino (con extensión de oficina, que es lo
   único que el módulo baja), lo vuelve a bajar y compara: si coincide, subir y
   bajar funcionan.
5. Copia de verdad entre sitios con `SharePoint.copiar` (el camino que usa
   `CLASIFICAR_ARCHIVOS` cuando origen y destino son sitios distintos) y compara
   la copia con el original, byte a byte.
6. Borra TODO lo suyo: el archivo de prueba y la copia. Del origen no se borra
   nada nunca.
7. Con ``gordo``: baja el archivo MÁS GRANDE del origen a tu PC (por rangos) y
   lo sube al destino con la subida por trozos de SharePoint, comprueba que lo
   que llegó pesa lo mismo y borra la copia. Del origen no toca nada.

No imprime cookies ni tokens: Brave firma las peticiones por su cuenta.
"""
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import navegador_cdp
from modules.sharepoint import ErrorSharePoint, SharePoint

fallos = []
ERRORES = (ErrorSharePoint, navegador_cdp.ErrorNavegador)


def paso(texto, ok, detalle=""):
    marca = "  ok  " if ok else "  FALLO  "
    print(f"{marca}{texto}" + (f"  [{detalle}]" if detalle else ""))
    if not ok:
        fallos.append(texto)


def buscar_archivos(sp, url, niveles=3):
    """Archivos bajables del origen, mirando dentro de las subcarpetas.

    Muchas carpetas solo contienen subcarpetas (una por cliente, por ejemplo) y
    los archivos están un par de niveles más abajo: de eso se encarga
    ``profundidad`` (cada nivel se pide de una vez con ``$expand=Files``, así que
    no hay que ir carpeta por carpeta: aquí hay 180 clientes). Los archivos
    vuelven con su ``subruta`` dentro de la carpeta pedida.
    """
    archivos = sp.listar_archivos(url, profundidad=niveles)
    if sp.nota_listado:
        print(f"  --  {sp.nota_listado}")
    return archivos


def probar_gordo(sp, info_origen, info_destino, archivos):
    """Baja el archivo más grande del origen a tu PC y lo sube por trozos.

    Es el camino que usa Jarvis con los archivos de más de ``TAMANO_POR_DISCO``
    (10 MB): se baja a disco (``$value`` por rangos) y desde ahí se sube con la
    subida por trozos de SharePoint. Del origen NO se borra nada: se pasa con
    ``borrar_origen=False``, que es como lo hace la copia.
    """
    elegido = max(archivos, key=lambda a: a.get("tamano") or 0)
    peso = elegido.get("tamano") or 0
    print(f"  --  el más grande: {elegido['subruta']} ({peso / 1048576:.1f} MB)")
    copia = (f"jarvis_gordo_{datetime.now():%Y%m%d_%H%M%S}_"
             + (elegido["nombre"] or "archivo")[:60])
    ruta_copia = info_destino["carpeta_rel"].rstrip("/") + "/" + copia
    try:
        sp._pasar_por_disco(info_origen["sitio"], elegido["ruta_rel"],
                            info_destino["sitio"], info_destino["carpeta_rel"],
                            copia, tamano=peso or None)
        paso("bajo el archivo a tu PC y lo subí al destino por trozos", True,
             f"{peso / 1048576:.1f} MB")
    except ERRORES as e:
        paso("bajo el archivo a tu PC y lo subí al destino por trozos", False,
             str(e))
        return
    puesto = None
    try:
        puesto = sp.tamano_de(info_destino["sitio"], ruta_copia)
    except ERRORES as e:
        print(f"  --  no pude preguntar cuánto pesa la copia: {e}")
    if puesto is not None:
        paso("la copia que quedó en el destino pesa lo mismo",
             puesto == peso, f"{puesto} bytes de {peso}")
    try:
        sp.borrar_archivo(info_destino["sitio"], ruta_copia)
        paso("borro la copia de prueba (del origen no toqué nada)", True)
    except ERRORES as e:
        paso("borro la copia de prueba (del origen no toqué nada)", False,
             f"{e} (quítala a mano: {ruta_copia})")


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else ""
    destino = sys.argv[2] if len(sys.argv) > 2 else ""
    gordo = len(sys.argv) > 3 and sys.argv[3].strip().lower() in (
        "gordo", "grande", "-g")
    if not origen or not destino:
        print(__doc__)
        return 2

    sp = SharePoint()

    print("== 1. Brave controlable por CDP ==")
    try:
        print("  --  " + sp.asegurar_navegador(origen))
        paso("Brave queda controlable", True)
    except ERRORES as e:
        paso("Brave queda controlable", False, str(e))
        return 1

    print("\n== 2. Las URLs que voy a usar ==")
    try:
        origen = sp.resolver(origen)
        destino = sp.resolver(destino)
        paso("entiendo las dos URLs", True)
    except ERRORES as e:
        paso("entiendo las dos URLs", False, str(e))
        return 1
    print(f"  --  origen:  {origen}")
    print(f"  --  destino: {destino}")
    info_origen = sp.parsear_url(origen)
    info_destino = sp.parsear_url(destino)
    # Esto es lo que de verdad usa la API. Si algún día falla una copia, aquí se
    # ve al instante si el sitio o la carpeta no son los que uno cree.
    print(f"      sitio de origen:   {info_origen['sitio']}")
    print(f"      carpeta de origen: {info_origen['carpeta_rel']}")
    print(f"      sitio de destino:  {info_destino['sitio']}")
    print(f"      carpeta de destino:{info_destino['carpeta_rel']}")

    print("\n== 3. Listar el origen y bajar el archivo más pequeño ==")
    try:
        archivos = buscar_archivos(sp, origen)
        paso("leo la carpeta de origen", True, f"{len(archivos)} archivo(s)")
    except ERRORES as e:
        paso("leo la carpeta de origen", False, str(e))
        sp.cerrar()
        return 1
    bajado, elegido = None, None
    if not archivos:
        print("  --  no encontré ningún archivo que bajar: me salto la descarga")
    else:
        elegido = min(archivos, key=lambda a: a.get("tamano") or 0)
        print(f"  --  el más pequeño: {elegido['subruta']} "
              f"({(elegido.get('tamano') or 0) / 1024:.0f} KB)")
        try:
            bajado = sp.descargar(info_origen["sitio"], elegido["ruta_rel"])
            esperado = elegido.get("tamano") or len(bajado)
            paso("bajo el archivo de origen", len(bajado) == esperado,
                 f"{len(bajado)} bytes de {esperado}")
        except ErrorSharePoint as e:
            paso("bajo el archivo de origen", False, str(e))

    print("\n== 4. Subir y volver a bajar un archivo de prueba ==")
    nombre = f"jarvis_prueba_{datetime.now():%Y%m%d_%H%M%S}.docx"
    contenido = ("Prueba de copia de Jarvis: si ves este archivo es que se "
                 "puede escribir en esta carpeta.\n").encode("utf-8")
    ruta = info_destino["carpeta_rel"].rstrip("/") + "/" + nombre
    try:
        sp.subir(info_destino["sitio"], info_destino["carpeta_rel"], nombre,
                 contenido)
        paso("subo un archivo al destino", True, nombre)
    except ErrorSharePoint as e:
        paso("subo un archivo al destino", False, str(e))
        print(f"  --  no hay nada que borrar: {ruta}")
    else:
        igual, detalle = False, ""
        try:
            vuelto = sp.descargar(info_destino["sitio"], ruta)
            igual = vuelto == contenido
            detalle = f"{len(vuelto)} bytes"
        except ErrorSharePoint as e:
            detalle = str(e)
        paso("el archivo subido se lee igual (ida y vuelta)", igual, detalle)
        try:
            sp.borrar_archivo(info_destino["sitio"], ruta)
            paso("borro el archivo de prueba", True)
        except ErrorSharePoint as e:
            paso("borro el archivo de prueba", False,
                 f"{e} (quítalo a mano: {ruta})")

    print("\n== 5. Copiar de verdad entre sitios (bajar de A y subir a B) ==")
    if not bajado:
        print("  --  sin archivo de origen no puedo copiar: me lo salto")
    else:
        # Se le pone sufijo y prefijo para no pisar nada y poder reconocerlo.
        copia = (f"jarvis_copia_{datetime.now():%Y%m%d_%H%M%S}_"
                 + (elegido["nombre"] or "archivo")[:60])
        ruta_copia = info_destino["carpeta_rel"].rstrip("/") + "/" + copia
        try:
            sp.copiar(info_origen["sitio"], elegido["ruta_rel"],
                      info_destino["sitio"], info_destino["carpeta_rel"], copia)
            paso(f"copio '{elegido['nombre']}' de un sitio a otro", True,
                 f"{len(bajado)} bytes")
        except ErrorSharePoint as e:
            paso(f"copio '{elegido['nombre']}' de un sitio a otro", False, str(e))
        else:
            igual, detalle = False, ""
            try:
                vuelto = sp.descargar(info_destino["sitio"], ruta_copia)
                igual = vuelto == bajado
                detalle = f"{len(vuelto)} bytes"
            except ErrorSharePoint as e:
                detalle = str(e)
            paso("la copia del destino es idéntica al original", igual, detalle)
            try:
                sp.borrar_archivo(info_destino["sitio"], ruta_copia)
                paso("borro la copia", True)
            except ErrorSharePoint as e:
                paso("borro la copia", False,
                     f"{e} (quítala a mano: {ruta_copia})")

    print("\n== 6. Un archivo gordo: bajarlo a tu PC y subirlo por trozos ==")
    if not gordo:
        print("  --  se salta (pásame 'gordo' como tercer argumento para probarlo)")
    elif not archivos:
        print("  --  no encontré archivos en el origen: me lo salto")
    else:
        probar_gordo(sp, info_origen, info_destino, archivos)

    sp.cerrar()
    print(f"\nTOTAL: {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
