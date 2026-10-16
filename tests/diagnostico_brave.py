"""Diagnóstico de la sesión de Brave para SharePoint (sin Graph).

Se ejecuta desde la raíz del proyecto:

    python tests/diagnostico_brave.py
    python tests/diagnostico_brave.py "https://empresa.sharepoint.com/sites/X/Docs"

Comprueba, paso a paso:
1. Que Brave está instalado y dónde.
2. Si hay un Brave controlable por CDP (puerto 9222).
3. Que `aiohttp` está disponible (WebSocket local).
4. Que se puede abrir una pestaña y evaluar JavaScript en ella.
5. Que el módulo se recupera si la pestaña se muere (esto daba 500).
6. Si se pasa una URL de SharePoint, lista los archivos REALES usando la
   sesión del navegador (esta es la prueba que antes daba 401).

No imprime cookies ni tokens: Brave firma las peticiones por su cuenta.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import navegador_cdp

fallos = []


def paso(texto, ok, detalle=""):
    marca = "  ok  " if ok else "  FALLO  "
    print(f"{marca}{texto}" + (f"  [{detalle}]" if detalle else ""))
    if not ok:
        fallos.append(texto)


def main():
    print("== 1. Brave instalado ==")
    ejecutable = navegador_cdp.ruta_brave()
    paso("encuentro brave.exe", bool(ejecutable), ejecutable or "no aparece")
    if not ejecutable:
        return 1

    print("\n== 2. Estado inicial de Brave ==")
    print("  --  brave escuchando en el puerto 9222: "
          + ("sí" if navegador_cdp.esta_activo() else "no"))
    print("  --  brave.exe en marcha: "
          + ("sí" if navegador_cdp.brave_en_ejecucion() else "no"))
    print("      (no es un problema: si falta, se abre con --remote-debugging-port)")

    print("\n== 3. aiohttp (WebSocket local) ==")
    paso("aiohttp importable", navegador_cdp.aiohttp is not None,
         getattr(navegador_cdp.aiohttp, "__version__", "?"))

    print("\n== 4. Pestaña controlable por CDP ==")
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        nota = navegador_cdp.asegurar(url or "about:blank")
        paso("brave queda controlable", True, nota)
    except Exception as e:
        paso("brave queda controlable", False, str(e))
        return 1

    try:
        pestana = navegador_cdp.Pestana("about:blank").abrir()
        valor = pestana.evaluar("1 + 1")
        paso("puedo abrir una pestaña y evaluar JS", valor == 2, f"1 + 1 = {valor}")
        pestana.cerrar()
    except Exception as e:
        paso("puedo abrir una pestaña y evaluar JS", False, str(e))
        return 1

    print("\n== 5. Si la pestaña se muere a mitad (el 500 de antes) ==")
    try:
        pestana = navegador_cdp.Pestana("about:blank").abrir()
        huerfana = pestana.id
        # Se imita lo que pasa cuando la pestaña desaparece (el usuario la cierra,
        # Brave se reinicia...): con un id que ya no existe, Brave contesta 500
        # 'Invalid response status', y eso antes tumbaba la operación entera.
        pestana.id = "PESTANA-QUE-YA-NO-EXISTE"
        pestana.ws_url = ("ws://127.0.0.1:9222/devtools/page/"
                          "PESTANA-QUE-YA-NO-EXISTE")
        valor = pestana.evaluar("2 + 2")
        paso("con una pestaña muerta, abre otra y sigue", valor == 4,
             f"2 + 2 = {valor}")
        navegador_cdp.cerrar_objetivo(huerfana)
        pestana.cerrar()
    except Exception as e:
        paso("con una pestaña muerta, abre otra y sigue", False, str(e))

    if not url:
        print("\nPasa una URL de SharePoint como argumento para probar la sesión.")
        print(f"\nTOTAL: 0 fallos" if not fallos else f"\nTOTAL: {len(fallos)} fallos")
        return 0 if not fallos else 1

    print("\n== 6. Sesión real contra SharePoint ==")
    from modules.sharepoint import SharePoint
    sp = SharePoint()

    # La URL puede ser la carpeta o la vista web que copia SharePoint
    # ('.../Oportunidad/Forms/AllItems.aspx?viewid=...'): esto enseña con qué
    # carpeta me quedo de verdad.
    info = sp.parsear_url(url)
    print(f"  --  carpeta que uso: {info['carpeta_rel']}")

    resultado = sp.probar(url)
    print(resultado)
    paso("leo la carpeta con la sesión de Brave",
         "No pude acceder" not in resultado)

    try:
        carpetas = sp.listar_carpetas(url)
        detalle = (": " + ", ".join(c["nombre"] for c in carpetas[:8])
                   if carpetas else "")
        print(f"  --  subcarpetas: {len(carpetas)}{detalle}")
        paso("veo las subcarpetas (la carpeta existe de verdad)", True)
    except Exception as e:
        paso("veo las subcarpetas (la carpeta existe de verdad)", False, str(e))
    sp.cerrar()

    print(f"\nTOTAL: {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
