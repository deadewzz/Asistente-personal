"""Pruebas de cómo se entiende la clasificación que devuelve la IA.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_clasificacion_ia.py

No necesita red ni API Key: lo que se prueba es el **texto** de la IA, que llega
como quiera (una línea por archivo, una tabla de Markdown, una lista con '->') y
que hay que convertir en el plan de verdad. Entenderle mal es lo peor que puede
pasar aquí: el plan sale vacío y TODOS los archivos acaban en un mismo sitio.

También se prueba que un archivo que la IA manda no tocar ('omitir', 'revisar',
'no es propuesta') llega marcado como tal, que el que la IA ni contesta queda
marcado igual (mejor no moverlo que inventarse el sitio), y que el que la IA deja
'sin clasificar' ('sin clasificar', 'no sé', 'duda') no se confunde con 'omitir':
ese no es una decisión de la regla, es una duda, y tiene arreglo (se le lee el
documento por dentro y se le vuelve a preguntar).
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api_brain import APIBrain
from modules.sharepoint import SharePoint

NOMBRES = ["AXA/acta.docx", "AXA/2024/informe.docx", "AXA/transcripcion.docx"]

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


class CerebroDeMentira(APIBrain):
    """APIBrain sin API Key ni red: solo la parte de armar el plan.

    ``_clasificar_tanda`` (la llamada a DeepSeek) se sustituye por lo que diga la
    prueba, así que aquí se comprueba lo que hace el cerebro con la respuesta:
    qué pasa con los archivos que la IA no contesta, si insiste cuando no
    clasifica ninguno, y cómo le llegan las pistas y las carpetas del destino.
    """

    def __init__(self, respuesta, luego=None):
        self.client = object()        # así no intenta crear el cliente de verdad
        self.api_key = "de mentira"
        self.on_aviso = None
        self.respuesta = respuesta    # {nombre: subcarpeta} o None (falla)
        self.luego = luego            # la respuesta de la 2ª vuelta, si la hay
        self.preguntas = []
        self.carpetas = []            # carpetas del destino que le llegaron
        self.pistas = []              # pistas de contenido que le llegaron
        self.insistencias = []        # ¿fue una vuelta de 'insistir'?

    def _clasificar_tanda(self, nombres, regla, carpetas=None, pistas=None,
                          insistir=False):
        self.preguntas.append(list(nombres))
        self.carpetas.append(list(carpetas or []))
        self.pistas.append(dict(pistas or {}))
        self.insistencias.append(bool(insistir))
        if insistir and self.luego is not None:
            return self.luego
        return self.respuesta


def pruebas_formato_pedido():
    print("\n== El formato que se le pide: 'nombre|destino' ==")
    plan = APIBrain._parsear_clasificacion(
        "AXA/acta.docx|Assessment/Data\n"
        "AXA/2024/informe.docx|Assessment/Reporting\n"
        "AXA/transcripcion.docx|omitir\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data",
                       "AXA/2024/informe.docx": "Assessment/Reporting",
                       "AXA/transcripcion.docx": SharePoint.OMITIR},
              "una línea por archivo, con rama/subrama y 'omitir' tal cual")

    plan = APIBrain._parsear_clasificacion(
        "AXA/acta.docx| raíz \nAXA/2024/informe.docx|.\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "", "AXA/2024/informe.docx": ""},
              "'raíz' (y '.') es la carpeta de destino tal cual, sin subcarpeta")


def pruebas_tabla_markdown():
    print("\n== Si contesta una tabla de Markdown ==")
    plan = APIBrain._parsear_clasificacion(
        "| Archivo | Rama | Subrama |\n"
        "|---|---|---|\n"
        "| **acta.docx** | Assessment | Data |\n"
        "| `informe.docx` | Assessment | — |\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data",
                       "AXA/2024/informe.docx": "Assessment"},
              "la cabecera no es un archivo, los adornos se quitan y '—' no es nivel")

    plan = APIBrain._parsear_clasificacion(
        "**Archivo** | **Rama** | **Subrama**\n"
        "acta.docx | Assessment | Data\n"
        "informe.docx | Assessment | Data\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data",
                       "AXA/2024/informe.docx": "Assessment/Data"},
              "con dos niveles iguales, cada archivo va a su rama y subrama")

    plan = APIBrain._parsear_clasificacion(
        "| 1. **acta.docx** | Assessment | Data |\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data"},
              "y una fila numerada tampoco se queda sin leer")


def pruebas_lista_con_flechas():
    print("\n== Si contesta una lista con '->' ==")
    plan = APIBrain._parsear_clasificacion(
        "- AXA/acta.docx -> Assessment/Data\n"
        "2) AXA/2024/informe.docx → Assessment/Reporting\n"
        "* AXA/transcripcion.docx => revisar: no es propuesta\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data",
                       "AXA/2024/informe.docx": "Assessment/Reporting",
                       "AXA/transcripcion.docx": SharePoint.OMITIR},
              "viñetas, numeración y flechas: todo vale si se entiende")


def pruebas_nombres_resumidos():
    print("\n== Si la IA acorta el nombre del archivo ==")
    plan = APIBrain._parsear_clasificacion(
        "acta.docx|Assessment/Data\ninforme.docx|Assessment/Reporting\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data",
                       "AXA/2024/informe.docx": "Assessment/Reporting"},
              "el nombre corto se completa con su carpeta, si es único")

    ambiguos = ["AXA/acta.docx", "SURA/acta.docx"]
    plan = APIBrain._parsear_clasificacion("acta.docx|Assessment/Data\n", ambiguos)
    comprobar(plan == {},
              "con dos 'acta.docx' no adivina: mejor no pasar un archivo por otro")

    plan = APIBrain._parsear_clasificacion("no-existe.docx|Assessment/Data\n", NOMBRES)
    comprobar(plan == {},
              "y un archivo que no estaba en el listado no entra al plan")

def pruebas_nada_utilizable_es_omitir():
    print("\n== Si no dice una carpeta utilizable, no se mueve ==")
    plan = APIBrain._parsear_clasificacion(
        "AXA/acta.docx|?\nAXA/2024/informe.docx| -\nAXA/transcripcion.docx|n/a\n",
        NOMBRES)
    comprobar(plan == {"AXA/acta.docx": SharePoint.OMITIR,
                       "AXA/2024/informe.docx": SharePoint.OMITIR,
                       "AXA/transcripcion.docx": SharePoint.OMITIR},
              "celdas vacías ('?', '-', 'n/a') no mandan nada a la raíz: se omiten")

    plan = APIBrain._parsear_clasificacion(
        "Assessment/Data\n| Assessment | Data |\n", NOMBRES)
    comprobar(plan == {},
              "una línea sin archivo (o la raya de la tabla) no inventa archivos")

    plan = APIBrain._parsear_clasificacion("", NOMBRES)
    comprobar(plan == {}, "una respuesta vacía deja el plan vacío (y se avisa)")

    plan = APIBrain._parsear_clasificacion(
        "AXA/acta.docx|Assessment/Data\nAXA/acta.docx|Assessment/Reporting\n",
        NOMBRES)
    comprobar(plan == {"AXA/acta.docx": "Assessment/Data"},
              "si insiste con el mismo archivo, vale la primera respuesta")


def pruebas_omitir_en_sus_formas():
    print("\n== 'No lo toques' dicho de todas las formas ==")
    for dicho in ("omitir", "OMITIR", "se omite", "revisar", "REVISAR",
                  "no aplica", "no es propuesta", "pendiente de revisar",
                  "descartar", "[REVISAR]"):
        plan = APIBrain._parsear_clasificacion(f"AXA/acta.docx|{dicho}\n", NOMBRES)
        comprobar(plan == {"AXA/acta.docx": SharePoint.OMITIR},
                  f"'{dicho}' llega como OMITIR (y no como carpeta)")

    for dicho in ("Assessment", "Assessment/Data", "Consultoría", "Otros"):
        plan = APIBrain._parsear_clasificacion(f"AXA/acta.docx|{dicho}\n", NOMBRES)
        comprobar(plan == {"AXA/acta.docx": dicho},
                  f"'{dicho}' sí es una carpeta de verdad")

    plan = APIBrain._parsear_clasificacion(
        "| acta.docx | omitir | no es propuesta |\n", NOMBRES)
    comprobar(plan == {"AXA/acta.docx": SharePoint.OMITIR},
              "y en una tabla, la palabra manda sobre las columnas de más")


def pruebas_plan_con_lo_que_falta():
    print("\n== Lo que la IA no contesta (o falla) no se mueve ==")
    cerebro = CerebroDeMentira({"AXA/acta.docx": "Assessment/Data"})
    plan = cerebro.clasificar_archivos(NOMBRES, "regla de propuestas")
    comprobar(plan == [("AXA/acta.docx", "Assessment/Data"),
                       ("AXA/2024/informe.docx", SharePoint.OMITIR),
                       ("AXA/transcripcion.docx", SharePoint.OMITIR)],
              "el que la IA no contestó queda como OMITIR, no en 'Otros'")
    comprobar(cerebro.preguntas == [NOMBRES],
              "y se le preguntó por todos los archivos de la tanda")

    cerebro = CerebroDeMentira(None)
    comprobar(cerebro.clasificar_archivos(NOMBRES, "regla") is None,
              "si la llamada a la IA falla, el plan es None (decide quien llama)")

    cerebro = CerebroDeMentira({})
    comprobar(cerebro.clasificar_archivos([], "regla") == [],
              "sin archivos no se llama a la IA para nada")


def pruebas_prompt_y_tandas():
    print("\n== El prompt pide una línea por archivo (y las tandas) ==")
    cerebro = CerebroDeMentira({})
    prompt = cerebro._prompt_clasificacion(["AXA/acta.docx"], "por tipo")
    comprobar("nombre_del_archivo|destino" in prompt,
              "se le enseña el formato exacto que se espera")
    comprobar("Assessment/Data" in prompt and "dos niveles" in prompt,
              "y que el destino puede llevar rama y subrama")
    comprobar("'omitir' como destino" in prompt,
              "y cómo decir que un archivo no se toca")
    comprobar("AXA/acta.docx" in prompt and "de donde SALE el archivo" in prompt,
              "avisa de que la carpeta del nombre es de origen, no el destino")
    comprobar("'nombre_del_archivo|sin clasificar'" in prompt,
              "y que, si de verdad no hay forma de saberlo, lo diga con 'sin "
              "clasificar' en vez de con 'omitir'")
    comprobar("'omitir' NO es para los que no sabes" in prompt
              and "'raíz' no vale" in prompt,
              "dejando 'omitir' y 'raíz' solo para lo que la regla mande")

    muchos = [f"AXA/f{i}.docx" for i in range(1, 65)]
    cerebro = CerebroDeMentira({})
    plan = cerebro.clasificar_archivos(muchos, "regla")
    comprobar([len(t) for t in cerebro.preguntas[:3]] == [30, 30, 4],
              "con muchos archivos se pregunta por tandas de 30 (y la última corta)")
    comprobar(len(plan) == 64 and all(sub == SharePoint.OMITIR for _, sub in plan),
              "y los planes de todas las tandas se juntan en uno")
    comprobar([len(t) for t in cerebro.preguntas[3:]] == [30, 30, 4]
              and cerebro.insistencias == [False, False, False, True, True, True],
              "si no le puso carpeta a ninguno, se le vuelve a preguntar entero "
              "(y solo una vez más)")


def pruebas_carpetas_que_ya_existen_en_el_prompt():
    """A la IA se le enseñan las carpetas que ya hay en el destino.

    Es lo que evita que se invente 'Assessment/Data Analysis' al lado de la
    'Assessment/Data' de siempre: sin esa lista clasifica a ciegas. Se le pide
    que las copie EXACTAMENTE y que solo invente cuando ninguna encaje.
    """
    print("\n== Las carpetas que ya existen en el destino (prompt) ==")
    cerebro = CerebroDeMentira({})
    prompt = cerebro._prompt_clasificacion(["AXA/acta.docx"], "por tipo",
                                           ["Assessment", "Assessment/Data"])
    comprobar("CARPETAS QUE YA EXISTEN EN EL DESTINO" in prompt,
              "el prompt trae la sección con las carpetas del destino")
    comprobar("\nAssessment\n" in prompt and "Assessment/Data" in prompt,
              "con cada carpeta tal cual (sus dos niveles incluidos)")
    comprobar("NO propongas una carpeta nueva si ya existe una que sirva" in
              prompt,
              "y la orden de reutilizarlas en vez de inventar otras")
    comprobar("'Assessment/Data', no 'Assessment/data'" in prompt,
              "pidiendo la ortografía exacta de la que ya está")
    comprobar("Solo si ninguna encaja" in prompt,
              "dejando inventar solo cuando de verdad no hay ninguna que sirva")

    # Sin catalogo (destino sin subcarpetas o sin poder leerlas) no hay sección.
    prompt = cerebro._prompt_clasificacion(["AXA/acta.docx"], "por tipo")
    comprobar("CARPETAS QUE YA EXISTEN" not in prompt,
              "sin carpetas del destino el prompt no inventa esa sección")
    prompt = cerebro._prompt_clasificacion(["AXA/acta.docx"], "por tipo", [])
    comprobar("CARPETAS QUE YA EXISTEN" not in prompt,
              "ni cuando el destino no tiene subcarpetas (lista vacía)")

    # Con muchas carpetas se corta y se dice: mejor que un prompt enorme.
    muchas = [f"Rama{i}/Subrama{i}" for i in range(1, 200)]
    prompt = cerebro._prompt_clasificacion(["AXA/acta.docx"], "por tipo", muchas)
    comprobar("Rama150/Subrama150" in prompt and "Rama151/Subrama151" not in prompt,
              f"se enseñan las primeras {APIBrain.MAXIMO_CARPETAS_PROMPT} "
              "carpetas (el tope)")
    comprobar("y 49 carpeta(s) más con el mismo estilo" in prompt,
              "y se dice cuántas quedaron fuera")

    # Y las carpetas llegan hasta la llamada a la IA (no se pierden por el camino).
    cerebro = CerebroDeMentira({"AXA/acta.docx": "Assessment/Data"})
    cerebro.clasificar_archivos(["AXA/acta.docx"], "regla",
                                ["Assessment/Data"])
    comprobar(cerebro.carpetas == [["Assessment/Data"]],
              "clasificar_archivos le pasa las carpetas del destino a la IA")


def pruebas_se_insiste_si_no_clasifica_nada():
    """Si la IA se refugia en 'omitir' con todo, se le pide otra vez.

    Es el fallo de verdad: contestaba 'omitir' hasta con 'Propuesta Arquitectura
    Cloud', el plan no movía nada y el usuario no entendía por qué. En la segunda
    vuelta se le dice a la cara, y si esta vez sí clasifica, ese plan es el bueno.
    """
    print("\n== Si no clasifica ninguno, se le insiste una vez ==")
    nombres = ["AXA/acta.docx", "AXA/informe.docx"]
    cerebro = CerebroDeMentira({n: SharePoint.OMITIR for n in nombres},
                              luego={"AXA/acta.docx": "Actas",
                                     "AXA/informe.docx": "Informes"})
    plan = cerebro.clasificar_archivos(nombres, "una carpeta por tipo")
    comprobar(plan == [("AXA/acta.docx", "Actas"),
                       ("AXA/informe.docx", "Informes")],
              "el plan que vale es el de la segunda vuelta (el que sí clasifica)")
    comprobar(cerebro.preguntas == [nombres, nombres],
              "se le pregunta dos veces por los mismos archivos")
    comprobar("en la respuesta anterior no le diste carpeta a NINGUNO"
              in cerebro._prompt_clasificacion(nombres, "regla", None, None, True),
              "y en esa vuelta se le dice que eso no es clasificar")

    # Pero si la regla manda dejar archivos fuera, eso es lo que se pidió.
    cerebro = CerebroDeMentira({n: SharePoint.OMITIR for n in nombres})
    plan = cerebro.clasificar_archivos(
        nombres, "una carpeta por tipo; las actas no se tocan")
    comprobar(len(cerebro.preguntas) == 1
              and all(sub == SharePoint.OMITIR for _, sub in plan),
              "con una regla que deja archivos fuera no se insiste: ya está bien")

    # Y si dice 'sin clasificar' a todos, también: es un 'no sé' honrado.
    cerebro = CerebroDeMentira({n: SharePoint.DUDOSO for n in nombres})
    plan = cerebro.clasificar_archivos(nombres, "una carpeta por tipo")
    comprobar(len(cerebro.preguntas) == 1
              and all(sub == SharePoint.DUDOSO for _, sub in plan),
              "si de verdad no sabe, no se le empuja a que se lo invente: el plan "
              "dice 'sin clasificar' y quien llama decide")


def pruebas_sin_clasificar_no_es_omitir():
    """'sin clasificar' es una duda, no un 'no lo toques'.

    Las dos acaban quietas, pero no son lo mismo: la duda se puede resolver
    leyendo el documento por dentro ('_reintentar_dudosos') y la decisión de la
    regla no.
    """
    print("\n== 'sin clasificar' no es lo mismo que 'omitir' ==")
    for dicho in ("sin clasificar", "SIN CLASIFICAR", "no sé", "no lo sé",
                  "no se sabe", "duda", "desconocido", "sin categoría",
                  "no se puede saber"):
        plan = APIBrain._parsear_clasificacion(f"AXA/acta.docx|{dicho}\n", NOMBRES)
        comprobar(plan == {"AXA/acta.docx": SharePoint.DUDOSO},
                  f"'{dicho}' llega como DUDOSO (no como OMITIR)")

    plan = APIBrain._parsear_clasificacion("| acta.docx | sin clasificar |\n",
                                           NOMBRES)
    comprobar(plan == {"AXA/acta.docx": SharePoint.DUDOSO},
              "y en una tabla también, aunque venga en su propia columna")
    comprobar(SharePoint.es_omitir(SharePoint.DUDOSO)
              and not SharePoint.es_dudoso("Actas")
              and not SharePoint.es_dudoso(""),
              "un dudoso nunca se pasa (es_omitir lo reconoce), pero 'Actas' (y "
              "la raíz) no son una duda: son destinos de verdad")


def pruebas_pistas_en_el_prompt():
    """Con la pista del contenido se le puede pedir la categoría a un hash.

    'PROPUESTA COMERCIAL bfddfa36 RFI...' no dice de qué disciplina es; la
    portada del documento sí, y es lo único que hace falta para clasificarlo.
    """
    print("\n== La pista del documento (para los nombres que no dicen nada) ==")
    cerebro = CerebroDeMentira({})
    nombre = "AXA/PROPUESTA COMERCIAL bfddfa36.pptx"
    pista = "Propuesta de Servicios de Pruebas - QA - Cliente: AXA"
    prompt = cerebro._prompt_clasificacion([nombre], "una carpeta por disciplina",
                                           ["QA", "Portales"], {nombre: pista})
    comprobar("LO QUE DICE CADA DOCUMENTO POR DENTRO" in prompt and pista in prompt,
              "el prompt trae lo que dice el documento por dentro")
    comprobar(f"- [{nombre}] {pista}" in prompt,
              "con el nombre del archivo delante, para saber de cuál es la pista")
    comprobar("El nombre que copias es el de la lista de ARCHIVOS" in prompt,
              "y avisando de que el nombre a copiar es el de la lista, no la pista")
    comprobar("LO QUE DICE CADA DOCUMENTO"
              not in cerebro._prompt_clasificacion(["AXA/acta.docx"], "regla"),
              "sin pistas no hay sección (ni se inventa nada)")

    # Y las pistas llegan hasta la llamada a la IA (no se pierden por el camino).
    cerebro = CerebroDeMentira({"AXA/acta.docx": "Actas"})
    cerebro.clasificar_archivos(["AXA/acta.docx"], "regla", ["Actas"],
                                {"AXA/acta.docx": pista})
    comprobar(cerebro.pistas == [{"AXA/acta.docx": pista}]
              and cerebro.carpetas == [["Actas"]],
              "clasificar_archivos le pasa las pistas y las carpetas a la IA")


def main_pruebas():
    pruebas_formato_pedido()
    pruebas_tabla_markdown()
    pruebas_lista_con_flechas()
    pruebas_nombres_resumidos()
    pruebas_nada_utilizable_es_omitir()
    pruebas_omitir_en_sus_formas()
    pruebas_plan_con_lo_que_falta()
    pruebas_prompt_y_tandas()
    pruebas_carpetas_que_ya_existen_en_el_prompt()
    pruebas_se_insiste_si_no_clasifica_nada()
    pruebas_sin_clasificar_no_es_omitir()
    pruebas_pistas_en_el_prompt()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
