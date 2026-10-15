"""Pruebas del explorador de archivos (listar, buscar, mover y copiar).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_archivos.py

No toca archivos reales: trabaja siempre dentro de carpetas temporales de usar y
tirar.
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.archivos import Explorador

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


def pruebas_navegacion():
    print("\n== Navegación y listado ==")
    ex = Explorador()
    with tempfile.TemporaryDirectory() as raiz:
        os.makedirs(os.path.join(raiz, "carpeta B"))
        os.makedirs(os.path.join(raiz, "carpeta a"))
        open(os.path.join(raiz, "b.txt"), "w").write("hola")
        open(os.path.join(raiz, "A.txt"), "w").write("hola")
        entradas = ex.listar(raiz)
        comprobar(entradas is not None, "listar devuelve contenido")
        nombres = [e["nombre"] for e in entradas]
        comprobar(nombres[:2] == ["carpeta a", "carpeta B"],
                  "directorios primero y ordenados")
        comprobar(nombres[2:] == ["A.txt", "b.txt"], "archivos después y ordenados")
        comprobar(entradas[0]["es_carpeta"] is True
                  and entradas[2]["es_carpeta"] is False,
                  "distingue carpetas de archivos")
        comprobar(ex.listar(os.path.join(raiz, "no existe")) is None,
                  "carpeta inexistente devuelve None")


def pruebas_buscar():
    print("\n== Búsqueda recursiva ==")
    ex = Explorador()
    with tempfile.TemporaryDirectory() as raiz:
        os.makedirs(os.path.join(raiz, "sub", "profundo"))
        os.makedirs(os.path.join(raiz, "node_modules"))
        open(os.path.join(raiz, "sub", "profundo", "factura_2026.pdf"), "w").write("x")
        open(os.path.join(raiz, "sub", "nota.txt"), "w").write("x")
        open(os.path.join(raiz, "node_modules", "factura_dep.pdf"), "w").write("x")
        r = ex.buscar(raiz, "factura")
        comprobar(len(r) == 1 and r[0].endswith("factura_2026.pdf"),
                  "encuentra en subcarpetas y excluye node_modules")
        comprobar(ex.buscar(raiz, "") == [], "sin nombre no busca")


def pruebas_mover():
    print("\n== Mover ==")
    ex = Explorador()
    with tempfile.TemporaryDirectory() as raiz:
        origen = os.path.join(raiz, "origen")
        destino = os.path.join(raiz, "destino")
        os.makedirs(origen)
        os.makedirs(destino)
        f1 = os.path.join(origen, "a.txt")
        f2 = os.path.join(origen, "b.txt")
        open(f1, "w").write("1")
        open(f2, "w").write("2")
        res = ex.mover(f"{f1};{f2}", destino)
        comprobar(res["confirmado"] is False and len(res["plan"]) == 2,
                  "sin confirmar solo muestra la vista previa")
        comprobar(os.path.exists(f1), "sin confirmar no se mueve nada")
        res = ex.mover(f"{f1};{f2}", destino, confirmado=True)
        comprobar(len(res["hechos"]) == 2 and not os.path.exists(f1),
                  "confirmado mueve los archivos")
        comprobar(os.path.exists(os.path.join(destino, "a.txt")),
                  "los deja en el destino")
        open(os.path.join(origen, "a.txt"), "w").write("otro")
        res = ex.mover(os.path.join(origen, "a.txt"), destino, confirmado=True)
        comprobar(os.path.basename(res["hechos"][0]) == "a (2).txt",
                  "ante choque de nombres renombra")


def pruebas_copiar():
    print("\n== Copiar ==")
    ex = Explorador()
    with tempfile.TemporaryDirectory() as raiz:
        origen = os.path.join(raiz, "origen")
        destino = os.path.join(raiz, "destino")
        os.makedirs(origen)
        os.makedirs(destino)
        f1 = os.path.join(origen, "a.txt")
        open(f1, "w").write("1")
        res = ex.copiar(f1, destino, confirmado=True)
        comprobar(len(res["hechos"]) == 1 and os.path.exists(f1),
                  "copiar conserva el original")
        comprobar(os.path.exists(os.path.join(destino, "a.txt")),
                  "y crea la copia en el destino")


def pruebas_utilidades():
    print("\n== Utilidades ==")
    ex = Explorador()
    comprobar(ex.normalizar('"C:\\Temp\\x"').endswith("x"), "normalizar quita comillas")
    comprobar(os.path.isabs(ex.normalizar(".")), "normalizar devuelve ruta absoluta")
    raices = ex.raices()
    comprobar(os.path.expanduser("~") in raices, "la raíz incluye la carpeta del usuario")
    resumen = ex.resumen(ex.mover("nada", os.path.expanduser("~")))
    comprobar("no existe" in resumen, "el resumen avisa de lo que no existe")


def main_pruebas():
    pruebas_navegacion()
    pruebas_buscar()
    pruebas_mover()
    pruebas_copiar()
    pruebas_utilidades()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
