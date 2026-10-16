"""Pruebas de la acción CLASIFICAR_ARCHIVOS (la que lanza la IA desde el chat).

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_accion_clasificar.py

No necesita Brave, ni red, ni API Key: SharePoint y la clasificación con la IA
se sustituyen por dobles. Comprueba lo pedido: que al pasarle la carpeta de
arriba (la de los clientes) **entre en las subcarpetas** (AXA, SURA...) y
clasifique lo que hay dentro; que con muchos archivos enseñe antes qué haría,
sin tocar nada, hasta que se confirme; que mire **qué carpetas tiene ya el
destino** para dejar cada archivo en las que existen (en vez de inventarse otras
parecidas) y que la acción **vaya contando por el chat lo que hace** (avisos de
progreso) mientras trabaja.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.sharepoint import ErrorSharePoint, SharePoint
from modules.system_actions import SystemActions

ORIGEN = "https://contoso.sharepoint.com/sites/Tech/Colombia"
DESTINO = "https://contoso.sharepoint.com/sites/Tech/Archivo"

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


class SharePointFalso:
    """SharePoint de mentira: apunta lo que le piden y no habla con nadie.

    ``parsear_url``, ``ajustar_plan``, ``clasificar_naive``, ``separar_omitidos``
    y ``separar_dudosos`` son los de verdad (cálculos puros), así que lo que se
    prueba aquí es la acción y no una copia de su lógica.
    """

    PROFUNDIDAD_BUSQUEDA = 2
    TAMANO_POR_DISCO = 10 * 1024 * 1024  # el mismo umbral que el de verdad
    DUDOSO = SharePoint.DUDOSO
    parsear_url = staticmethod(SharePoint.parsear_url)
    ajustar_plan = staticmethod(SharePoint.ajustar_plan)
    clasificar_naive = staticmethod(SharePoint.clasificar_naive)
    es_omitir = staticmethod(SharePoint.es_omitir)
    es_dudoso = staticmethod(SharePoint.es_dudoso)
    regla_deja_fuera = staticmethod(SharePoint.regla_deja_fuera)
    regla_pide_la_raiz = staticmethod(SharePoint.regla_pide_la_raiz)
    separar_omitidos = staticmethod(SharePoint.separar_omitidos)
    separar_dudosos = staticmethod(SharePoint.separar_dudosos)

    def __init__(self, archivos, nota="", carpetas=None, catalogo_roto=False,
                 pistas=None, pistas_rotas=False):
        self.archivos = archivos
        self.nota_listado = nota
        self.nota_catalogo = ""
        self.on_clasificar = None
        self.on_aviso = None   # por aquí sale lo que va haciendo (chat)
        self.listados = []   # (url, profundidad) que le han pedido
        self.pedidos = []    # nombres que le pasaron a la IA
        self.plan = None     # lo que se llevó a clasificar_y_mover
        self.tamanos = None  # los tamaños que le llegaron con el plan
        self.resumen = "Hecho: movidos."
        # Las carpetas que "ya existen" en el destino y quién las pidió: así se
        # comprueba que la acción las mira y se las pasa a la IA.
        self.carpetas = list(carpetas or [])
        self.catalogo_roto = catalogo_roto
        self.catalogos_pedidos = []
        self.recibidas = []        # carpetas que le llegaron a la IA
        self.carpetas_del_pase = None  # carpetas que le llegaron al movimiento
        # Lo que "dice por dentro" cada documento: el ``pistas_de`` de verdad se
        # baja los bytes y saca el título y las primeras líneas
        # (``modules.pistas``), aquí se le da hecho. ``pistas_rotas`` hace que
        # bajarlos falle, para probar que eso no tumba la clasificación.
        self.pistas = dict(pistas or {})
        self.pistas_rotas = pistas_rotas
        self.pistas_pedidas = []    # de qué archivos se pidió el contenido
        self.pistas_recibidas = []  # pistas que le llegaron a la IA en cada intento

    def _aviso(self, texto):
        """Como el de verdad: si la acción enlazó el canal, lo usa."""
        aviso = getattr(self, "on_aviso", None)
        if aviso:
            aviso(texto)

    def resolver(self, url):
        return url

    def asegurar_navegador(self, url):
        return "Brave ya estaba abierto"

    def listar_archivos(self, url, profundidad=0):
        self.listados.append((url, profundidad))
        if profundidad:
            self._aviso(f"Buscando archivos dentro de 2 carpeta(s) "
                        f"(nivel 1 de {profundidad})...")
            self._aviso(f"Encontré {len(self.archivos)} archivo(s) dentro de "
                        "las subcarpetas (2 carpeta(s) miradas).")
        return list(self.archivos)

    def catalogo_carpetas(self, url, profundidad=None):
        """Las carpetas que "ya existen" en el destino (lo de verdad es la API)."""
        self.catalogos_pedidos.append(url)
        if self.catalogo_roto:
            raise ErrorSharePoint("no pude leer el destino")
        return list(self.carpetas)

    def pistas_de(self, origen, nombres, maximo=None):
        """Lo que dicen por dentro esos documentos (el de verdad se los baja).

        Solo se piden los que la IA dejó 'sin clasificar', así que aquí se
        apunta qué se pidió (``pistas_pedidas``) y se devuelve lo que se le haya
        configurado: los nombres que no estén se quedan sin pista, como el
        documento del que no se saca nada (un .ppt viejo, uno protegido).
        """
        self.pistas_pedidas.append(list(nombres))
        if self.pistas_rotas:
            raise RuntimeError("no pude bajar el documento")
        return {nombre: self.pistas[nombre] for nombre in nombres
                if nombre in self.pistas}

    def clasificar_y_mover(self, origen, destino, plan, copiar=None,
                           tamanos=None, carpetas=None):
        self.plan = plan
        self.tamanos = tamanos
        self.carpetas_del_pase = carpetas
        for numero, (nombre, subcarpeta) in enumerate(plan, 1):
            self._aviso(f"Moviendo {numero} de {len(plan)}: {nombre} → "
                        f"{subcarpeta or '(raíz)'}")
        return self.resumen


class Sistema(SystemActions):
    """SystemActions sin arrancar Outlook, correo ni nada: solo lo que se prueba."""

    def __init__(self, sharepoint):
        self.sharepoint = sharepoint


def sistema_con(archivos, clasificador=None, nota="", carpetas=None,
                catalogo_roto=False, pistas=None, pistas_rotas=False):
    """Acción lista para probar, con IA de mentira si le pasan `clasificador`.

    ``carpetas`` son las que "ya existen" en el destino y ``catalogo_roto`` hace
    que leerlas falle (sin permiso, destino sin crear): con eso se prueba que la
    acción sigue clasificando cuando ese atajo no está. ``pistas`` es lo que
    "dice por dentro" cada documento (lo que el segundo intento le enseña a la
    IA) y ``pistas_rotas`` hace que bajarlos falle.
    """
    fake = SharePointFalso(archivos, nota, carpetas, catalogo_roto, pistas,
                           pistas_rotas)
    if clasificador:
        def con_registro(nombres, regla, carpetas=None, pistas=None):
            """Como el de verdad: apunta lo que le pasan y pide el plan."""
            fake.pedidos.append(list(nombres))
            fake.recibidas.append(list(carpetas or []))
            fake.pistas_recibidas.append(dict(pistas or {}))
            try:
                return clasificador(nombres, regla, carpetas, pistas)
            except TypeError as e:
                # Un clasificador de mentira de los de antes (tres argumentos).
                if "positional argument" not in str(e):
                    raise
            return clasificador(nombres, regla, carpetas)

        fake.on_clasificar = con_registro
    return Sistema(fake), fake


def archivos_en_subcarpetas():
    """Dos archivos que NO están en la carpeta pedida: están dos niveles abajo."""
    return [{"nombre": "acta.pdf", "subruta": "AXA/acta.pdf", "tamano": 10},
            {"nombre": "informe.pdf", "subruta": "AXA/2024/informe.pdf",
             "tamano": 20}]


def clasificar_por_tipo(nombres, regla, carpetas=None):
    return [(n, "Actas" if n.endswith("acta.pdf") else "Informes")
            for n in nombres]


def clasificar_todo_otros(nombres, regla, carpetas=None):
    return [(n, "Otros") for n in nombres]


def pruebas_busqueda_en_subcarpetas():
    print("\n== Pasar la carpeta de arriba y que entre en las subcarpetas ==")
    sistema, fake = sistema_con(archivos_en_subcarpetas(), clasificar_por_tipo)
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.listados == [(ORIGEN, 2)],
              "pide el listado con profundidad (entra en las subcarpetas)")
    comprobar(fake.pedidos == [["AXA/acta.pdf", "AXA/2024/informe.pdf"]],
              "la IA recibe los archivos con su carpeta, no solo el nombre")
    comprobar(fake.plan == [("AXA/acta.pdf", "Actas"),
                            ("AXA/2024/informe.pdf", "Informes")],
              "el plan lleva la ruta de cada archivo y su subcarpeta de destino")
    comprobar(respuesta == fake.resumen,
              "con pocos archivos lo hace a la primera (sin pedir permiso)")

    # La IA puede acortar el nombre: el plan se arregla con la ruta real.
    sistema, fake = sistema_con(
        archivos_en_subcarpetas(),
        lambda nombres, regla, carpetas=None: [("informe.pdf", "Informes")])
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.plan == [("AXA/2024/informe.pdf", "Informes")],
              "si la IA devuelve un nombre suelto, se completa con su ruta")
    comprobar(respuesta == fake.resumen, "y se ejecuta igual")


def pruebas_confirmacion_con_muchos():
    print("\n== Con muchos archivos: primero lo enseña, luego lo hace ==")
    muchos = [{"nombre": f"f{i}.pdf", "subruta": f"Cliente{i}/f{i}.pdf",
               "tamano": i} for i in range(30)]

    sistema, fake = sistema_con(muchos, clasificar_todo_otros)
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.plan is None, "no toca nada sin confirmación")
    comprobar("Encontré 30 archivo(s)" in respuesta, "dice cuántos encontró")
    comprobar("Todavía NO he tocado nada" in respuesta,
              "avisa de que no ha tocado nada")
    comprobar("Cliente0/f0.pdf → Otros" in respuesta,
              "enseña de qué carpeta sale cada archivo y a dónde iría")
    comprobar(";;confirmar" in respuesta, "y dice cómo se confirma")

    respuesta = sistema._clasificar_archivos(
        f"{ORIGEN};;{DESTINO};;por tipo;;confirmar")
    comprobar(len(fake.plan or []) == 30, "con ';;confirmar' lo hace de verdad")
    comprobar(respuesta == fake.resumen, "y responde con el resumen del trabajo")

    sistema, fake = sistema_con(muchos, clasificar_todo_otros)
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo;;mover")
    comprobar(len(fake.plan or []) == 30, "';;mover' también vale para confirmar")

    # El corte está en 'más de 25': con 25 justos no pregunta.
    sistema, fake = sistema_con(muchos[:25], clasificar_todo_otros)
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(len(fake.plan or []) == 25 and respuesta == fake.resumen,
              "con 25 archivos justos no pregunta (el corte es 'más de 25')")


def pruebas_avisos():
    print("\n== Avisos: carpeta vacía y búsqueda a medias ==")
    sistema, fake = sistema_con([])
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar("ni dentro de sus subcarpetas" in respuesta,
              "si no hay nada ni dentro, lo dice claro")
    comprobar(fake.pedidos == [], "y no molesta a la IA para nada")

    sistema, fake = sistema_con(archivos_en_subcarpetas(),
                                lambda nombres, regla, carpetas=None:
                                [(n, "") for n in nombres],
                                nota="Me quedé en 300 carpetas: puede haber más.")
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar("Me quedé en 300 carpetas" in respuesta,
              "avisa si la búsqueda se quedó a medias (puede faltar alguno)")

    sistema, fake = sistema_con(archivos_en_subcarpetas())
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.plan == [("AXA/acta.pdf", ""), ("AXA/2024/informe.pdf", "")],
              "sin IA deja todo en la raíz, pero con la ruta correcta de cada uno")

    sistema, fake = sistema_con([])
    respuesta = sistema._clasificar_archivos(";;")
    comprobar("Necesito la URL de origen" in respuesta,
              "sin URLs, pide las URLs en vez de liarse")


def pruebas_avisos_de_progreso():
    """Mientras trabaja, la acción va diciendo por el chat lo que hace.

    Es lo que evita que el chat parezca colgado: listar una biblioteca por
    clientes y pasar cientos de archivos tarda minutos, así que cada paso
    (qué va a hacer, cuántos encontró, el plan, cada archivo) sale como aviso.
    """
    print("\n== El chat va diciendo lo que se hace (avisos de progreso) ==")
    avisos = []
    sistema, fake = sistema_con(archivos_en_subcarpetas(), clasificar_por_tipo)
    comprobar(fake.on_aviso is None, "el canal de avisos empieza sin oyente")

    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")

    comprobar(fake.on_aviso == sistema._aviso,
              "la acción enlaza los avisos de SharePoint con el chat")
    comprobar(avisos and avisos[0].startswith("Clasificando los archivos de"),
              "lo primero que cuenta es qué va a hacer")
    comprobar(any("Leyendo la carpeta" in a for a in avisos),
              "avisa de que va a leer la carpeta y sus subcarpetas")
    comprobar(any("nivel 1 de 2" in a for a in avisos),
              "y de los avisos del propio módulo de SharePoint")
    comprobar(any("Encontré 2 archivo(s)" in a for a in avisos),
              "dice cuántos archivos encontró")
    comprobar(any(a.startswith("Plan listo: 2 archivo(s) a 2 subcarpeta(s)")
                  for a in avisos),
              "resume el plan: cuántos van y a qué subcarpetas")
    pasos = [a for a in avisos if a.startswith("Moviendo")]
    comprobar(pasos == ["Moviendo 1 de 2: AXA/acta.pdf → Actas",
                        "Moviendo 2 de 2: AXA/2024/informe.pdf → Informes"],
              "va diciendo cada archivo que pasa y por cuál va")
    comprobar(avisos.index(pasos[0]) > avisos.index(
        next(a for a in avisos if a.startswith("Plan listo"))),
        "primero cuenta el plan y después el trasiego")
    comprobar(respuesta == fake.resumen, "y el resumen final sigue llegando")

    # Con muchos archivos, el aviso importante es que NO ha tocado nada.
    avisos = []
    muchos = [{"nombre": f"f{i}.pdf", "subruta": f"Cliente{i}/f{i}.pdf",
               "tamano": i} for i in range(30)]
    sistema, fake = sistema_con(muchos, clasificar_todo_otros)
    sistema.on_aviso = avisos.append
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(any("no toco nada hasta que me confirmes" in a for a in avisos),
              "con muchos archivos avisa de que no ha tocado nada")
    comprobar(not [a for a in avisos if a.startswith("Moviendo")],
              "y no cuenta movimientos, porque no ha movido nada")

    # Si el chat se rompe (o no hay ventana), la clasificación termina igual.
    sistema, fake = sistema_con(archivos_en_subcarpetas(), clasificar_por_tipo)

    def aviso_roto(texto):
        raise RuntimeError("el chat se ha caído")

    sistema.on_aviso = aviso_roto
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(respuesta == fake.resumen,
              "un fallo al avisar no tumba la clasificación")


def pruebas_archivos_grandes():
    """Los archivos de más de 10 MB se avisan en el plan y van por tu PC.

    La acción le pasa a SharePoint los tamaños que ya traía el listado: así el
    módulo no tiene que preguntar cuánto pesa cada archivo y el chat puede decir
    cuántos van a ir por disco (bajándolos a tu PC y subiéndolos), que es mucho
    más lento que un MoveTo.
    """
    print("\n== Archivos grandes (más de 10 MB) ==")
    archivos = [{"nombre": "acta.pdf", "subruta": "AXA/acta.pdf", "tamano": 100},
                {"nombre": "video.mp4", "subruta": "AXA/2024/video.mp4",
                 "tamano": 30 * 1024 * 1024}]
    avisos = []
    sistema, fake = sistema_con(archivos, clasificar_por_tipo)
    sistema.on_aviso = avisos.append
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.tamanos == {"AXA/acta.pdf": 100,
                               "AXA/2024/video.mp4": 30 * 1024 * 1024},
              "la acción le pasa a SharePoint los tamaños del listado")
    comprobar(any("1 pasan de 10 MB" in a for a in avisos),
              "y el plan avisa de que uno de ellos va por tu PC")
    comprobar(any("bajándolos a tu PC" in a for a in avisos),
              "diciendo que ese se baja y se sube (así no sorprende lo que tarda)")

    # Con archivos normales no se habla de discos: no hace falta.
    avisos = []
    sistema, fake = sistema_con(
        [{"nombre": "acta.pdf", "subruta": "AXA/acta.pdf", "tamano": 2048}],
        clasificar_por_tipo)
    sistema.on_aviso = avisos.append
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(not [a for a in avisos if "pasan de" in a],
              "con archivos normales no se habla de bajar nada a tu PC")


def clasificar_omitidos(nombres, regla, hasta=6, carpetas=None):
    """Regla de mentira: los 'f1..f{hasta}' se omiten y el resto va a 'Actas'."""
    fuera = {f"f{i}.pdf" for i in range(1, hasta + 1)}
    return [(n, "omitir" if n.rsplit("/", 1)[-1] in fuera else "Actas")
            for n in nombres]


def clasificar_todo_omitir(nombres, regla, carpetas=None):
    """Regla de mentira que deja fuera a todos (nada que pasar)."""
    return [(n, "omitir") for n in nombres]


# La regla de mentira que SÍ habla de dejar archivos fuera ('no se tocan' es una
# de las formas en que lo escribe el usuario): con ella los mensajes tienen que
# decir "tu regla los deja fuera". Con una regla que no dice eso, un archivo sin
# carpeta es una duda del programa y así hay que contarlo (para eso está la
# prueba de los 'sin clasificar').
REGLA_CON_OMITIDOS = "por tipo; las transcripciones no se tocan"


def pruebas_lo_que_la_regla_deja_fuera():
    """La regla manda omitir: esos archivos no se pasan ni piden confirmación.

    Con la regla de propuestas (transcripciones, anexos técnicos, Consultoría y
    lo que hay que revisar fuera) la acción no debe contar esos archivos para el
    umbral de confirmación ni pasarlos por tu PC. Y si la regla deja fuera a
    todos, tiene que decirlo, en vez de responder "0 archivo(s)".
    """
    print("\n== Lo que la regla deja fuera (omitir) ==")
    tres = [{"nombre": f"f{i}.pdf", "subruta": f"AXA/f{i}.pdf", "tamano": i}
            for i in range(1, 4)]

    sistema, fake = sistema_con(
        tres, lambda nombres, regla, carpetas=None:
        clasificar_omitidos(nombres, regla, 1))
    avisos = []
    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(
        f"{ORIGEN};;{DESTINO};;{REGLA_CON_OMITIDOS}")
    comprobar([n for n, _ in fake.plan] == ["AXA/f2.pdf", "AXA/f3.pdf"],
              "el omitido no llega al plan (no se copia ni se baja a tu PC)")
    comprobar(any("1 se quedan sin tocar" in a and "tu regla los deja fuera" in a
                  for a in avisos),
              "el aviso del plan dice cuántos se quedan sin tocar y por qué")
    comprobar(respuesta == fake.resumen,
              "y el trabajo sigue con el resto, sin pedir confirmación por él")

    # Muchos archivos: el umbral (25) cuenta solo los que se pasan de verdad.
    treinta = [{"nombre": f"f{i}.pdf", "subruta": f"AXA/f{i}.pdf", "tamano": i}
               for i in range(1, 31)]
    sistema, fake = sistema_con(
        treinta, lambda nombres, regla, carpetas=None:
        clasificar_omitidos(nombres, regla, 6))
    respuesta = sistema._clasificar_archivos(
        f"{ORIGEN};;{DESTINO};;{REGLA_CON_OMITIDOS}")
    comprobar(len(fake.plan or []) == 24 and respuesta == fake.resumen,
              "24 que van + 6 que se omiten no pasan del umbral (no pregunta)")

    # 28 que van + 2 que se omiten: sí pregunta, y la vista previa los enseña.
    sistema, fake = sistema_con(
        treinta, lambda nombres, regla, carpetas=None:
        clasificar_omitidos(nombres, regla, 2))
    respuesta = sistema._clasificar_archivos(
        f"{ORIGEN};;{DESTINO};;{REGLA_CON_OMITIDOS}")
    comprobar(fake.plan is None and "Encontré 30 archivo(s)" in respuesta,
              "con muchos, primero lo enseña (y cuenta los omitidos como vistos)")
    comprobar("Y estos NO los tocaría (tu regla los deja fuera):" in respuesta
              and "AXA/f1.pdf → omitir" in respuesta,
              "la vista previa dice cuáles no se tocarían y por qué")

    # Si la regla deja fuera a todos: nada que pasar, y se dice.
    sistema, fake = sistema_con(tres, clasificar_todo_omitir)
    sistema.on_aviso = lambda texto: None
    respuesta = sistema._clasificar_archivos(
        f"{ORIGEN};;{DESTINO};;{REGLA_CON_OMITIDOS}")
    comprobar(fake.plan is None, "si no pasa ninguno, no se llama a mover nada")
    comprobar("No hay nada que pasar" in respuesta
              and "deja fuera a los 3 archivo(s)" in respuesta,
              "y se dice claro, en vez de hablar de '0 archivo(s)'")
    comprobar("AXA/f1.pdf → omitir" in respuesta
              and "Los dejé donde estaban." in respuesta,
              "contando cuáles son y que no se tocaron")


def pruebas_carpetas_que_ya_existen():
    """Antes de clasificar se mira qué carpetas tiene ya el destino.

    Sin eso la IA clasificaba a ciegas: no sabía qué había hecho al otro lado y
    creaba 'Assessment/Data Analysis' al lado de la 'Assessment/Data' de
    siempre. Aquí se prueba que la acción lee esas carpetas, se las pasa a la
    IA, que el archivo acaba en la carpeta que ya existe (aunque la IA la
    escriba de otra forma) y que si no se pueden leer se clasifica igual.
    """
    print("\n== Las carpetas que ya existen en el destino ==")
    dos = [{"nombre": "dato.pdf", "subruta": "AXA/dato.pdf", "tamano": 10},
           {"nombre": "acta.pdf", "subruta": "AXA/acta.pdf", "tamano": 10}]

    def clasificar_con_subrama(nombres, regla, carpetas=None):
        """De mentira: el dato a la subrama (en minúsculas) y el acta a 'Nueva'."""
        return [(n, "assessment/data" if "dato" in n else "Informes/Nueva")
                for n in nombres]

    sistema, fake = sistema_con(dos, clasificar_con_subrama,
                                carpetas=["Assessment", "Assessment/Data"])
    avisos = []
    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.catalogos_pedidos == [DESTINO],
              "mira qué carpetas tiene ya el destino antes de clasificar")
    comprobar(fake.recibidas == [["Assessment", "Assessment/Data"]],
              "y se las pasa a la IA, con sus dos niveles (rama y subrama)")
    comprobar(any("El destino ya tiene 2 carpeta(s)" in a for a in avisos),
              "avisando de que va a usar esas cuando el archivo encaje")
    comprobar(fake.plan == [("AXA/dato.pdf", "Assessment/Data"),
                            ("AXA/acta.pdf", "Informes/Nueva")],
              "el que encaja cae en la carpeta que YA existe y solo se estrena "
              "la que de verdad es nueva")
    comprobar(fake.carpetas_del_pase == ["Assessment", "Assessment/Data"],
              "y al pasar los archivos va el catálogo (para alinear igual ahí)")
    comprobar(any("1 van a carpetas que ya estaban en el destino; 1 estrenan "
                  "carpeta." in a for a in avisos),
              "el plan dice cuántos reutilizan carpeta y cuántos la estrenan")
    comprobar(respuesta == fake.resumen, "y el trabajo sigue igual")

    # Destino sin subcarpetas: no hay nada que reutilizar, y se dice.
    sistema, fake = sistema_con(dos, clasificar_por_tipo)
    avisos = []
    sistema.on_aviso = avisos.append
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.recibidas == [[]],
              "un destino sin subcarpetas manda a la IA una lista vacía")
    comprobar(any("todavía no tiene subcarpetas" in a for a in avisos),
              "y lo dice, en vez de callarse")

    # Si no se puede leer el destino (sin permiso, sin crear...), no pasa nada.
    sistema, fake = sistema_con(dos, clasificar_por_tipo, catalogo_roto=True)
    avisos = []
    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(respuesta == fake.resumen,
              "si no se pueden leer, clasifica igual (el atajo no es requisito)")
    comprobar(any("clasifico sin esa lista" in a for a in avisos),
              "diciendo por qué va sin esa lista")
    comprobar(fake.recibidas == [[]],
              "y la IA recibe una lista vacía en vez de un catálogo inventado")

    # Con muchos archivos (vista previa): se enseña qué carpetas ya hay.
    muchos = [{"nombre": f"f{i}.pdf", "subruta": f"AXA/f{i}.pdf", "tamano": i}
              for i in range(30)]
    sistema, fake = sistema_con(muchos, clasificar_todo_otros,
                                carpetas=["Assessment/Data"])
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.plan is None, "con muchos no toca nada sin confirmar")
    comprobar("En el destino ya hay 1 carpeta(s) (Assessment/Data)" in respuesta,
              "y la vista previa enseña las carpetas que ya existen ahí")


def pruebas_lo_que_no_se_supo_clasificar():
    """Los que la IA deja 'sin clasificar' se rescatan leyendo el documento.

    El caso real: 'PROPUESTA COMERCIAL bfddfa36 RFI Soporte y-o
    administración.pptx' no dice de qué disciplina es, así que la IA no puede
    saber a qué carpeta va y (antes) esos archivos acababan en la raíz del
    destino o, peor, en cualquier sitio. Aquí se prueba el segundo intento: se le
    lee el documento por dentro (título y primeras líneas) solo a esos, se le
    vuelve a preguntar solo por esos, y con eso la propuesta acaba en su carpeta.
    Si de dentro no se saca nada, el archivo se queda **quieto** y se dice con
    la verdad (no se le echa la culpa a la regla, que no dijo eso).
    """
    print("\n== Los que la IA deja 'sin clasificar' (propuestas de nombre hash) ==")
    propuesta = ("AXA/PROPUESTA COMERCIAL bfddfa36 RFI Soporte "
                 "y-o administración.pptx")
    archivos = [{"nombre": propuesta.rsplit("/", 1)[-1], "subruta": propuesta,
                 "tamano": 10},
                {"nombre": "acta.pptx", "subruta": "AXA/acta.pptx",
                 "tamano": 10}]
    pista = ("Título: Propuesta Comercial Portales. Cliente: Banco X "
             "(RFI Soporte).")

    def clasificar_con_pista(nombres, regla, carpetas=None, pistas=None):
        """De mentira: la propuesta sin pista es duda; con pista, a Portales.

        La segunda vez devuelve el nombre **sin la carpeta**, como haría la IA
        con un nombre de hash: el plan tiene que completarlo con la ruta real.
        """
        plan = []
        for nombre in nombres:
            archivo = nombre.rsplit("/", 1)[-1]
            if "PROPUESTA" not in archivo:
                plan.append((nombre, "Actas"))
            elif pistas and nombre in pistas:
                plan.append((archivo, "portales"))
            else:
                plan.append((nombre, SharePoint.DUDOSO))
        return plan

    sistema, fake = sistema_con(archivos, clasificar_con_pista,
                                carpetas=["Portales", "Assessment"],
                                pistas={propuesta: pista})
    avisos = []
    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")

    comprobar(fake.pistas_recibidas == [{}, {propuesta: pista}],
              "el primer intento va sin pistas y el segundo con la del documento")
    comprobar(fake.pistas_pedidas == [[propuesta]],
              "solo se le lee el documento al que se quedó sin clasificar")
    comprobar(fake.pedidos[-1] == [propuesta],
              "y solo se le vuelve a preguntar por ese")
    comprobar(any("1 archivo(s) se quedaron sin clasificar" in a for a in avisos),
              "se avisa de que hay uno que no supo clasificar")
    comprobar(any("Leí el contenido de 1 de 1 archivo(s)" in a for a in avisos),
              "y de que se le leyó el documento por dentro")
    comprobar(fake.plan == [("AXA/acta.pptx", "Actas"), (propuesta, "Portales")],
              "con la pista, la propuesta acaba en su carpeta (no en la raíz) y "
              "con la ruta completa, aunque la IA la devolviera a medias")
    comprobar(respuesta == fake.resumen, "y el trabajo termina igual")
    # Si de dentro del documento no se saca nada, se queda quieto y se dice.
    sistema, fake = sistema_con(archivos, clasificar_con_pista, pistas={})
    avisos = []
    sistema.on_aviso = avisos.append
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar([n for n, _ in fake.plan] == ["AXA/acta.pptx"],
              "el que sigue sin clasificar no se pasa (mejor quieto que mal puesto)")
    comprobar(any("No saqué nada de dentro" in a for a in avisos),
              "y se dice que no se pudo rescatar")
    comprobar(any("se quedaron 'sin clasificar'" in a
                  and "ni leyendo el documento por dentro" in a
                  for a in avisos),
              "el plan avisa de que ese se quedó sin clasificar")

    # Y si el único archivo es el dudoso: nada que pasar, y con la verdad por
    # delante (la regla no dijo que se dejara fuera; lo que pasó es que no se
    # supo dónde ponerlo).
    sistema, fake = sistema_con(archivos[:1], clasificar_con_pista, pistas={})
    sistema.on_aviso = lambda texto: None
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.plan is None, "no se llama a mover nada")
    comprobar("No hay nada que pasar" in respuesta
              and "ninguno tiene carpeta en el plan" in respuesta,
              "y se cuenta que no se supo clasificar, no que la regla lo dejara "
              "fuera")
    comprobar(f"{propuesta} → sin clasificar (no supe dónde va)" in respuesta
              and "Los dejé donde estaban." in respuesta,
              "enseñando cuál es y que no se tocó")
    comprobar("tu regla deja fuera" not in respuesta,
              "sin echarle la culpa a la regla, que no dijo eso")

    # Si los documentos no se pueden ni bajar, la clasificación sigue igual.
    sistema, fake = sistema_con(archivos, clasificar_con_pista,
                                pistas_rotas=True)
    avisos = []
    sistema.on_aviso = avisos.append
    respuesta = sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(any("No pude leer esos documentos por dentro" in a
                  for a in avisos),
              "un fallo leyendo los documentos se avisa y no tumba nada")
    comprobar([n for n, _ in fake.plan] == ["AXA/acta.pptx"],
              "y el resto se pasa igual")
    comprobar(respuesta == fake.resumen, "con su resumen de siempre")

    # Y si la IA sabe dónde va todo, no se le abre el documento a nadie.
    sistema, fake = sistema_con(archivos, clasificar_por_tipo)
    sistema._clasificar_archivos(f"{ORIGEN};;{DESTINO};;por tipo")
    comprobar(fake.pistas_pedidas == [],
              "si no hay dudas, no se lee ningún documento")


def main_pruebas():
    pruebas_busqueda_en_subcarpetas()
    pruebas_confirmacion_con_muchos()
    pruebas_avisos()
    pruebas_avisos_de_progreso()
    pruebas_archivos_grandes()
    pruebas_lo_que_la_regla_deja_fuera()
    pruebas_carpetas_que_ya_existen()
    pruebas_lo_que_no_se_supo_clasificar()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
