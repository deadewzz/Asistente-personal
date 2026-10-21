"""Pruebas del tutor de inglés: detección local, memoria y encargos a la IA.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_ingles.py

No gasta ninguna llamada a la IA: aquí se prueba justo lo que el tutor decide
*antes* de llamarla (qué errores ve, qué recuerda de las prácticas anteriores y
qué le pide al modelo). El nivel y el historial se guardan siempre en carpetas
temporales de usar y tirar, así que no toca nada del usuario.
"""
import inspect
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import english_tutor as ingles
from modules.api_brain import APIBrain
from modules.english_tutor import MARCA_TUTOR, EnglishTutor
from modules.progreso import Progreso
from modules.system_actions import SystemActions

fallos = []
total = [0]


def comprobar(condicion, texto):
    total[0] += 1
    if condicion:
        print(f"  ok  {texto}")
    else:
        print(f"  FALLO  {texto}")
        fallos.append(texto)


def tutor_temporal(carpeta, nivel=""):
    """Tutor de verdad con todo su estado dentro de una carpeta temporal."""
    tutor = EnglishTutor(carpeta=carpeta)
    if nivel:
        tutor.fijar_nivel(nivel)
    return tutor


#: Cada frase lleva uno de los calcos que el analizador local tiene que ver.
CASOS = (
    ("I have 30 years and two kids", "verbo_be_edad"),
    ("I have hungry after the meeting", "estado_con_have"),
    ("People is very kind in this office", "people_concordancia"),
    ("She work in a bank", "tercera_persona_s"),
    ("He don't like the new plan", "tercera_negacion"),
    ("I didn't went to the party", "did_pasado"),
    ("I didn't was at home yesterday", "did_was"),
    ("I don't know nothing about it", "doble_negacion"),
    ("How I can fix this error?", "how_i_can"),
    ("Can you explain me the rule, please?", "explain_me"),
    ("They say me that it's ready", "say_me"),
    ("Listen me for a second", "listen_me"),
    ("Wait me here, please", "wait_me"),
    ("I asked to him for help", "ask_to"),
    ("It depends of the weather", "depend_of"),
    ("She is married with a doctor", "married_with"),
    ("I will see you in Friday", "in_dia"),
    ("I am tired in the weekend", "in_fin_semana"),
    ("We will travel on January", "on_mes"),
    ("I have worked here since three years", "since_duracion"),
    ("I went to my house for to study", "for_to"),
    ("I want to go to home now", "go_to_home"),
    ("I must to call the client", "modal_to"),
    ("There were so much people at the fair", "much_people"),
    ("I very like this song", "very_verbo"),
    ("This hotel is more better than the other", "doble_comparativo"),
    ("It was the most best film of the year", "doble_superlativo"),
    ("I go to the gym everyday", "everyday"),
    ("I am agree with you", "i_agree"),
    ("I am interesting in the offer", "interesting_in"),
    ("I am boring in this class", "bored_estar"),
    ("How is called this in English?", "how_called"),
    ("I want to make a question", "make_question"),
    ("My boss told me to take a decision", "take_decision"),
    ("The news are not good today", "news_singular"),
    ("I need some informations about prices", "incontables"),
    ("I recieved the package yesterday", "ortografia"),
    ("Its a big problem for the team", "its_it_is"),
    ("Thanks, and your welcome", "your_welcome"),
    ("i am from Colombia", "i_mayuscula"),
)


def pruebas_deteccion():
    print("\n== Detección local de errores (sin IA) ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        for frase, esperada in CASOS:
            claves = [deteccion["clave"] for deteccion in tutor.detectar(frase)]
            comprobar(esperada in claves, f"«{frase}» → {esperada}")

        detecciones = tutor.detectar("I have 30 years and I have hungry")
        comprobar(all({"clave", "titulo", "encontrado", "sugerencia", "explicacion", "aviso"} <= set(d)
                      for d in detecciones),
                  "cada aviso trae qué se escribió, cómo se dice y por qué")

        ejemplos = {d["clave"]: d for d in tutor.detectar("I am working here since a few months")}
        comprobar(ejemplos["since_duracion"]["sugerencia"] == "for a few months",
                  "y la corrección se escribe sola ('since a few months' → 'for a few months')")
        ortografia = tutor.detectar("I recieved the message")[0]
        comprobar(ortografia["sugerencia"] == "received", "'recieved' se corrige por 'received'")

        repetido = tutor.detectar("He don't like it and he don't want it")
        comprobar(sum(1 for d in repetido if d["clave"] == "tercera_negacion") == 1,
                  "un fallo repetido se avisa una sola vez (el patrón se arregla de una)")

        limpio = tutor.detectar("I went home yesterday and my boss said the report was ready.")
        comprobar(limpio == [], "una frase bien escrita no inventa errores")
        comprobar(tutor.detectar("") == [], "y sin texto no hay nada que corregir")

        texto_largo = ("I have 30 years. " * 400) + "I have hungry."
        claves_largo = [d["clave"] for d in tutor.detectar(texto_largo)]
        comprobar(len(texto_largo) > ingles.MAX_TEXTO and "estado_con_have" not in claves_largo,
                  f"por encima de {ingles.MAX_TEXTO} caracteres se ignora el resto (no se cuelga)")
        comprobar("verbo_be_edad" in claves_largo, "pero lo que sí entra en el límite se analiza")


def pruebas_pistas():
    print("\n== Los errores que se le pasan a la IA ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        texto = ("I have 30 years. People is nice. He don't call me. I didn't went. "
                 "How I can help? I very like it. It depends of you. I am boring today.")
        detecciones = tutor.detectar(texto)
        comprobar(len(detecciones) >= ingles.MAX_PISTAS,
                  f"el texto de prueba acumula fallos de sobra ({len(detecciones)})")

        encargo = tutor.corregir(texto)
        bloque = encargo.split("ERRORES DETECTADOS POR EL ANALIZADOR LOCAL")[-1]
        pistas = [linea for linea in bloque.splitlines() if re.match(r"^\d+\. \(", linea)]
        comprobar(len(pistas) == ingles.MAX_PISTAS,
                  f"solo viajan {ingles.MAX_PISTAS} pistas (el resto las ve la IA)")
        comprobar(encargo.index("TEXTO DEL ALUMNO") <
                  encargo.index("ERRORES DETECTADOS POR EL ANALIZADOR LOCAL"),
                  "las pistas van después del texto del alumno")
        comprobar("(error)" in pistas[0] and "Motivo:" in pistas[0],
                  "cada pista dice qué falla y por qué, ya comprobado en local")

        sin_errores = tutor.corregir("She is a very good teacher and I like her classes.")
        comprobar("ERRORES DETECTADOS POR EL ANALIZADOR LOCAL" not in sin_errores,
                  "sin errores localizados no se le pasa ningún bloque de pistas")
        comprobar("## ✅ Versión corregida" in sin_errores,
                  "y aun así se le pide la corrección (por si ve algo que el analizador no)")


def pruebas_estado():
    print("\n== Nivel, prácticas y memoria de lo que falla ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        comprobar(tutor.nivel() == ingles.NIVEL_POR_DEFECTO,
                  f"de estreno el nivel es {ingles.NIVEL_POR_DEFECTO}")
        comprobar(tutor.frecuentes() == [], "de estreno no hay errores apuntados")
        comprobar("Prácticas: 0" in tutor.progreso() and "Nivel: B1" in tutor.progreso(),
                  "y el progreso arranca en cero")

        comprobar(tutor.fijar_nivel("nivel B2").startswith("Nivel actualizado")
                  and tutor.nivel() == "B2", "«nivel B2» fija el nivel y lo confirma")
        comprobar(tutor.fijar_nivel("b2").startswith("Tu nivel ya era"),
                  "repetir el mismo nivel se avisa sin cambiar nada")
        comprobar(tutor.fijar_nivel("avanzado").startswith("Nivel actualizado")
                  and tutor.nivel() == "C1",
                  "el nivel también se entiende dicho con palabras («avanzado» → C1)")
        comprobar(tutor.fijar_nivel("no tengo ni idea").startswith("No sé con qué nivel")
                  and tutor.nivel() == "C1",
                  "sin nivel claro pide uno de la lista y no lo cambia")

        tutor.fijar_nivel("B2")
        tutor.registrar(tutor.detectar("I have 30 years"), "práctica uno")
        tutor.registrar(tutor.detectar("I have 30 years and I have hungry"), "práctica dos")
        repetidos = dict(tutor.frecuentes())
        comprobar(repetidos["verbo_be_edad"]["veces"] == 2,
                  "un fallo que se repite se cuenta (dos veces)")
        comprobar(repetidos["verbo_be_edad"]["titulo"] and repetidos["verbo_be_edad"]["ejemplo"]
                  and repetidos["verbo_be_edad"]["correccion"],
                  "y se guarda con su título, su ejemplo y su corrección")
        comprobar([clave for clave, _ in tutor.frecuentes()][0] == "verbo_be_edad",
                  "lo que más se repite va primero")

        resumen = tutor.progreso()
        comprobar("Tutor de inglés" in resumen and "Nivel: B2" in resumen,
                  "el progreso enseña el nivel del alumno")
        comprobar("Prácticas: 2" in resumen, "y cuántas prácticas lleva")
        comprobar("La edad va con" in resumen and "2 vez/veces" in resumen,
                  "nombra el fallo que se repite, con su título y sus veces")
        comprobar("práctica dos" in resumen and "Atajos:" in resumen,
                  "apunta las últimas prácticas y los atajos para seguir")

        comprobar(tutor.progreso("borrar").startswith("He borrado") and tutor.frecuentes() == [],
                  "«borrar» limpia el historial de errores")
        comprobar(tutor.nivel() == "B2" and "Prácticas: 2" in tutor.progreso(),
                  "pero ni el nivel ni la cuenta de prácticas se pierden")

        # Lo que se repite es lo que hace distinto el repaso de unos ejercicios nuevos.
        tutor.registrar(tutor.detectar("He don't call me"), "práctica tres")
        repaso = tutor.repaso("4")
        comprobar("ERRORES QUE ESTE ALUMNO REPITE" in repaso and "he don't" in repaso.lower(),
                  "el repaso le recuerda a la IA los fallos que se le repiten")
        comprobar("ERRORES QUE ESTE ALUMNO REPITE" in tutor.corregir("I very like it"),
                  "y una corrección nueva también los tiene en cuenta")

    # Un estado ilegible no puede romper el tutor: se empieza de cero.
    with tempfile.TemporaryDirectory() as carpeta:
        with open(os.path.join(carpeta, "estado.json"), "w", encoding="utf-8") as archivo:
            archivo.write("{esto no es un JSON")
        tutor = tutor_temporal(carpeta)
        comprobar(tutor.nivel() == ingles.NIVEL_POR_DEFECTO and tutor.frecuentes() == [],
                  "con el estado ilegible vuelve a los valores por defecto")
        comprobar("Tutor de inglés" in tutor.progreso(), "y el progreso sigue respondiendo")

    # Y el historial no crece sin freno.
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        for numero in range(ingles.MAX_EVENTOS + 5):
            tutor.registrar([], f"práctica {numero}")
        comprobar(len(tutor._leer_estado()["temas"]) == ingles.MAX_EVENTOS,
                  f"solo se guardan las últimas {ingles.MAX_EVENTOS} prácticas")
        comprobar(f"Prácticas: {ingles.MAX_EVENTOS + 5}" in tutor.progreso(),
                  "aunque la cuenta total no se pierde")
        comprobar("Lo que más se te repite" not in tutor.progreso(),
                  "y sin errores no se inventa una lista de fallos")


def pruebas_prompt():
    print("\n== Lo que el tutor le pide a la IA ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta, "B2")

        for respuesta, empieza in ((tutor.corregir(""), "Escribe en inglés"),
                                   (tutor.explicar(""), "Dime qué punto de inglés"),
                                   (tutor.conversar(""), "Escríbeme algo en inglés")):
            comprobar(respuesta.startswith(empieza) and MARCA_TUTOR not in respuesta,
                      f"sin datos pide lo que falta y no gasta IA («{empieza}…»)")

        encargo = tutor.corregir("I have 30 years and I am agree with you")
        comprobar(encargo.startswith(MARCA_TUTOR), "el encargo se marca para que la ventana lo reconozca")
        comprobar("su nivel actual de inglés es B2" in encargo, "y lleva el nivel del alumno")
        comprobar("TEXTO DEL ALUMNO" in encargo and "I have 30 years and I am agree" in encargo,
                  "el texto del alumno viaja entero")
        apartados = [encargo.index(titulo) for titulo in
                     ("## ✅ Versión corregida", "## 🔍 Punto por punto",
                      "## 📚 Para entenderlo", "## ✍️ Practica")]
        comprobar(apartados == sorted(apartados),
                  "con los apartados que se le piden y en ese orden")
        comprobar("No inventes errores" in encargo, "y la orden de no inventar errores")

        largo = tutor.corregir("x" * (ingles.MAX_TEXTO + 50))
        comprobar("x" * ingles.MAX_TEXTO in largo and "x" * (ingles.MAX_TEXTO + 1) not in largo,
                  f"un texto enorme se recorta a {ingles.MAX_TEXTO} caracteres")

        comprobar("TAREA: preparar 3 ejercicios para practicar esto: «presente simple»" in
                  tutor.practicar("presente simple", "3"),
                  "practicar respeta el tema y la cantidad pedidos")
        generico = tutor.practicar("", "99")
        comprobar("10 ejercicios" in generico and "sobre lo que más le falla" in generico,
                  f"sin tema pide ejercicios de lo que falla, con {ingles.MAX_EJERCICIOS} de techo")
        comprobar("1 ejercicio sobre lo que más le falla" in tutor.practicar("", "0"),
                  "y con uno solo se escribe en singular")

        comprobar("5 ejercicios cortos" in tutor.repaso("")
                  and "8 ejercicios cortos" in tutor.repaso("8"),
                  "el repaso acepta cuántos ejercicios (5 si no se dice nada)")
        comprobar("1 ejercicio corto" in tutor.repaso("1"), "y con uno se escribe en singular")
        repaso = tutor.repaso("")
        comprobar(all(apartado in repaso for apartado in
                      ("## 🔁 Repaso", "## ✍️ Ejercicios", "## ✅ Soluciones", "## 📌 Reglas de bolsillo")),
                  "el repaso pide regla, ejercicios, soluciones y reglas de bolsillo")

        vocabulario = tutor.vocabulario("viajes", "12")
        comprobar("TAREA: enseñar vocabulario útil sobre «viajes»" in vocabulario
                  and "12 palabras o expresiones" in vocabulario
                  and "## 📖 Vocabulario: viajes" in vocabulario,
                  "el vocabulario acepta tema y cantidad")
        general = tutor.vocabulario("", "40")
        comprobar(f"{ingles.MAX_PALABRAS} palabras" in general
                  and "Vocabulario del día a día" in general,
                  f"sin tema es vocabulario del día a día, con {ingles.MAX_PALABRAS} palabras de techo")
        comprobar("1 palabra o expresión" in tutor.vocabulario("", "1"),
                  "y con una sola se escribe en singular")
        comprobar("Cómo se pronuncia" in general,
                  "pide la pronunciación aproximada para un hispanohablante")

        explicar = tutor.explicar("presente perfecto")
        comprobar("TAREA: explicar paso a paso este punto de inglés: «presente perfecto»" in explicar
                  and "## 🧩 Qué es y para qué sirve" in explicar
                  and "## 🏗️ Cómo se forma" in explicar
                  and "## ⚠️ Los errores típicos de un hispanohablante" in explicar,
                  "explicar pide la clase desde cero, con los errores típicos de un hispanohablante")

        conversacion = tutor.conversar("Yesterday I go to a meeting and my boss say me hello")
        comprobar(conversacion.startswith(MARCA_TUTOR)
                  and "LO QUE HA DICHO EL ALUMNO" in conversacion
                  and "Yesterday I go to a meeting" in conversacion,
                  "conversar arranca de lo que acaba de decir el alumno")
        comprobar(all(apartado in conversacion for apartado in
                      ("## 💬 Mi respuesta", "## 🔍 Cómo lo has dicho", "## 🗣️ Cómo decirlo mejor",
                       "## 🇪🇸 Traducción", "## ➡️ Tu turno")),
                  "y pide respuesta en inglés, corrección, alternativas, traducción y su turno")

        tareas = (tutor.corregir("I am agree"), tutor.explicar("for y since"), tutor.practicar("", ""),
                  tutor.conversar("I am agree"), tutor.repaso(""), tutor.vocabulario("", ""))
        comprobar(all(tarea.startswith(MARCA_TUTOR) for tarea in tareas),
                  "las seis clases se marcan para que la ventana las mande al cerebro")
        comprobar(all(len(tarea) > 500 for tarea in tareas),
                  "y todas van con el encargo completo (no una frase suelta)")

    with tempfile.TemporaryDirectory() as carpeta:
        estrenado = tutor_temporal(carpeta, "B2")
        comprobar("No hay errores registrados todavía" in estrenado.repaso(""),
                  "sin historial el repaso tira de los fallos típicos del nivel")
        estrenado.corregir("I have 30 years and I am agree")
        comprobar("No hay errores registrados todavía" not in estrenado.repaso("")
                  and "30 years" in estrenado.repaso(""),
                  "y en cuanto hay fallos apuntados, el repaso arranca de ellos")


class AsistenteFalso(SystemActions):
    """Solo el tutor y el canal de progreso: no monta Office, correo ni navegador."""

    def __init__(self, carpeta):
        self.ingles = EnglishTutor(carpeta=carpeta)
        self.progreso = Progreso()


def pruebas_sin_chat():
    print("\n== El tutor ya no se usa desde el chat ==")
    with tempfile.TemporaryDirectory() as carpeta:
        asistente = AsistenteFalso(carpeta)
        # Estas ocho acciones existían en el despachador del chat. Ahora el tutor
        # tiene su apartado en la ventana, así que la IA no puede repartir clases:
        # escribir «corrige mi inglés» en el chat no dispara nada.
        for comando in ("INGLES_CORREGIR|I have 30 years", "INGLES_EXPLICAR|for y since",
                        "INGLES_PRACTICAR|presente simple;;4", "INGLES_CONVERSAR|hello",
                        "INGLES_REPASO|8", "INGLES_VOCABULARIO|viajes", "INGLES_NIVEL|B2",
                        "INGLES_PROGRESO"):
            comprobar(asistente.ejecutar_comando(comando) is None,
                      f"{comando.split('|')[0]} ya no es una acción del chat")
        comprobar(not [clave for clave in SystemActions.PROGRESO_ACCIONES
                       if clave.startswith("INGLES_")],
                  "tampoco quedan mensajes de inglés en el canal de progreso")
        comprobar(not hasattr(SystemActions, "_tema_y_cantidad"),
                  "y el separador ';;' del tutor ya no hace falta en el despachador")

        # El apartado llama al tutor directamente: lo que se comprueba es que sigue
        # devolviendo lo mismo (el encargo, o el aviso si no hay texto).
        comprobar(asistente.ingles.nivel() == "B1",
                  "el tutor sigue montado en el asistente, con su nivel por defecto")
        comprobar(str(asistente.ingles.corregir("I have 30 years")).startswith(MARCA_TUTOR),
                  "y el apartado puede pedirle la corrección como siempre")
        comprobar(str(asistente.ingles.corregir("")).startswith("Escribe en inglés"),
                  "sin texto, el tutor avisa al alumno en vez de llamar a la IA")


def pruebas_apartado():
    """El tutor tiene su apartado en la ventana y ya no cuelga del chat.

    Evita el fallo de fondo: que el apartado prometa algo que el módulo ya no da
    (o que el chat siga repartiendo clases de inglés por su cuenta).
    """
    print("\n== Apartado «Clase de inglés» de la ventana ==")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def leer(*partes):
        with open(os.path.join(raiz, *partes), encoding="utf-8") as archivo:
            return archivo.read()

    prompt = leer("modules", "api_brain.py")
    sistema = leer("modules", "system_actions.py")
    ventana = leer("app_gui.py")
    codigo_tutor = leer("modules", "english_tutor.py")

    def metodo(nombre):
        """El trozo de código de un método de la ventana, para poder mirarlo."""
        trozo = ventana[ventana.index(f"def {nombre}(self"):]
        siguiente = trozo.find("\n    def ", 10)
        return trozo[:siguiente] if siguiente > 0 else trozo

    # --- El chat ya no reparte clases de inglés
    comprobar(not re.findall(r"ACCION:\s*INGLES_[A-Z_]+", prompt),
              "el prompt del chat ya no ofrece acciones de inglés")
    comprobar("ACCION: MATRIZ_NUBE" in prompt and "ACCION: LEER_REGLAS" in prompt,
              "y las demás acciones siguen anunciadas en su sitio")
    comprobar("INGLES_" not in sistema and "def _tema_y_cantidad" not in sistema,
              "el despachador no atiende ninguna acción de inglés")

    # --- La ventana tiene el apartado, con su botón
    comprobar("self.vista_ingles = ctk.CTkFrame" in ventana
              and "def _crear_vista_ingles(self, parent):" in ventana,
              "la ventana monta el apartado de inglés como una vista propia")
    comprobar('command=lambda: self._mostrar_vista("ingles")' in ventana
              and 'elif vista == "ingles":' in ventana,
              "con su botón en la barra lateral y su rama en _mostrar_vista")
    comprobar("self.btn_ingles.configure" in ventana and "COLOR_TARJETA if vista" in ventana,
              "y el apartado queda marcado en la barra lateral mientras está abierto")
    comprobar("TAREAS_INGLES" in ventana and "AYUDA_INGLES" in ventana
              and "from modules.english_tutor import MARCA_TUTOR, NIVELES" in ventana,
              "las tareas, la ayuda de entrada y los niveles están conectados")
    comprobar("def _accion_ingles(self, tarea):" in ventana
              and "def _pedir_clase(self, encargo):" in ventana,
              "las tareas del tutor se lanzan desde el apartado")
    comprobar("threading.Thread(target=self._pedir_clase" in ventana,
              "y la clase se pide a la IA en un hilo aparte (la ventana no se cuelga)")
    comprobar("APIBrain.SISTEMA_TUTOR" in ventana,
              "con el mensaje de sistema del profesor (respuesta larga en Markdown)")
    comprobar("def _escribir_clase(self, texto):" in ventana
              and "def _actualizar_ingles(self):" in ventana
              and "def _cambiar_nivel_ingles(self, nivel):" in ventana,
              "el panel de la clase, la cabecera del avance y el nivel son suyos")

    # --- Y el chat no sabe nada del tutor
    chat = metodo("_procesar_mensaje")
    comprobar("MARCA_TUTOR" not in chat and "ingles" not in chat,
              "el chat no mira la marca del tutor ni prepara clases")
    comprobar("def _clase_ingles(self, encargo):" not in ventana,
              "ni queda el método que redactaba la clase para el chat")
    comprobar("texto_voz" not in ventana,
              "tampoco el aviso de voz que se leía en su lugar")

    # --- El cerebro sigue teniendo lo que el apartado necesita
    comprobar(hasattr(APIBrain, "SISTEMA_TUTOR") and "profesor" in APIBrain.SISTEMA_TUTOR,
              "el cerebro tiene el mensaje de sistema del profesor (SISTEMA_TUTOR)")
    parametros = inspect.signature(APIBrain.analizar_documento).parameters
    comprobar("sistema" in parametros and parametros["sistema"].default is None,
              "analizar_documento acepta cambiar el mensaje de sistema")
    comprobar("sistema or self.SISTEMA_ANALISIS" in prompt,
              "y sin indicarlo sigue usando el de los análisis (actas, informes)")
    comprobar("self.ingles = EnglishTutor(config_path)" in sistema,
              "el asistente monta el tutor con la configuración del usuario")
    comprobar("def resumen(self):" in codigo_tutor,
              "y el tutor ofrece su resumen para la cabecera del apartado")

    with tempfile.TemporaryDirectory() as carpeta:
        estrenado = tutor_temporal(carpeta, "A2")
        estrenado.corregir("I have 30 years and I am agree")
        datos = estrenado.resumen()
        comprobar(datos["nivel"] == "A2" and datos["practicas"] == 1
                  and len(datos["repetidos"]) >= 2,
                  "resumen() da nivel, prácticas y los fallos repetidos del alumno")


def pruebas_speaking():
    """El modo hablado del tutor: la charla, la pronunciación y el dictado en inglés."""
    print("\n== Speaking: la charla hablada ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta, "B2")

        arranque = tutor.speaking("", "viajes")
        comprobar(arranque.startswith(MARCA_TUTOR),
                  "el speaking también vuelve marcado para que la ventana lo reconozca")
        comprobar("su nivel actual de inglés es B2" in arranque
                  and "TEMA DE LA CHARLA: «viajes»" in arranque,
                  "y lleva el nivel del alumno y el tema de la charla")
        comprobar("TODAVÍA NO HA DICHO NADA" in arranque,
                  "sin nada oído, la IA abre ella la conversación")
        apartados = [arranque.index(titulo) for titulo in
                     ("## \U0001F4AC Lo que digo yo", "## \U0001F50D Cómo lo has dicho",
                      "## \U0001F50A Pronunciación", "## \U0001F1EA\U0001F1F8 Qué te he dicho",
                      "## ➡️ Te toca")]
        comprobar(apartados == sorted(apartados),
                  "con los apartados de una clase de speaking, en ese orden")
        comprobar("en inglés y solo en inglés" in arranque,
                  "y el apartado que se lee en voz alta se pide solo en inglés")

        turno = tutor.speaking("i am go to the office yesterday")
        comprobar("LO QUE ACABA DE DECIR EL ALUMNO" in turno
                  and "i am go to the office yesterday" in turno,
                  "cuando el alumno habla, su frase viaja a la IA tal cual se oyó")
        comprobar("errata" in turno.lower() and "pronunciación" in turno.lower(),
                  "y se le avisa de que el dictado puede traer erratas, pidiendo pronunciación")
        resumen = tutor.resumen()
        comprobar(resumen["practicas"] == 2 and bool(resumen["repetidos"]),
                  "cada turno hablado cuenta como práctica y apunta los fallos que ve")
        comprobar(tutor.speaking("x" * (ingles.MAX_TEXTO + 50)).count("x" * ingles.MAX_TEXTO) == 1
                  and "x" * (ingles.MAX_TEXTO + 1) not in tutor.speaking("x" * (ingles.MAX_TEXTO + 50)),
                  f"un dictado enorme se recorta a {ingles.MAX_TEXTO} caracteres")

    # El dictado en inglés recupera las mayúsculas (si no, el tutor contaría fallos
    # que el alumno no ha cometido y la frase se vería mal).
    from modules.voice_engine import VoiceEngine
    comprobar(VoiceEngine._arreglar_mayusculas("i am from spain. i'll be there.")
              == "I am from spain. I'll be there.",
              "el dictado recupera el «I» y la mayúscula de cada frase")
    comprobar(VoiceEngine._arreglar_mayusculas("") == ""
              and VoiceEngine._arreglar_mayusculas("hello there") == "Hello there",
              "y sin texto no inventa nada")
    with tempfile.TemporaryDirectory() as carpeta:
        motor = VoiceEngine(config_path=os.path.join(carpeta, "config.json"),
                            temp_folder=carpeta)
        comprobar("en-US" in motor.voz_ingles and "es-" in motor.voz_tts
                  and motor.voz_ingles != motor.voz_tts,
                  "el motor de voz tiene una voz inglesa aparte de la española")
        comprobar(callable(getattr(motor, "escuchar_ingles", None))
                  and "_contiene_activacion" not in inspect.getsource(VoiceEngine.escuchar_ingles),
                  "y un modo de escuchar en inglés que no busca palabra de activación")


def main_pruebas():
    pruebas_deteccion()
    pruebas_pistas()
    pruebas_estado()
    pruebas_prompt()
    pruebas_speaking()
    pruebas_sin_chat()
    pruebas_apartado()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
