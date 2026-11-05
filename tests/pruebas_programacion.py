"""Pruebas del taller de programación: analizador local, `javac` y encargos a la IA.

Se ejecuta tal cual, desde la raíz del proyecto:

    python tests/pruebas_programacion.py

No gasta ninguna llamada a la IA: aquí se prueba justo lo que el tutor decide
*antes* de llamarla (qué fallos ve, con qué línea y columna, qué tiene escrito en
sus tablas y qué le pide al modelo). El nivel y el avance se guardan siempre en
carpetas temporales de usar y tirar, y el código se compila en carpetas
temporales, así que no toca nada del usuario.

Si el equipo tiene JDK se prueban también el compilador y la ejecución de verdad;
si no lo tiene, se comprueba que el taller avisa y sigue funcionando con la
revisión básica (que es lo que hay sin JDK).
"""
import inspect
import json
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los módulos de Jarvis viven en la raíz del proyecto: se añade al sys.path para
# poder ejecutar este archivo tal cual (sin tener que ser un paquete).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import programming_tutor as prog
from modules.api_brain import APIBrain
from modules.programming_tutor import MARCA_PROFE, ProgrammingTutor
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
    tutor = ProgrammingTutor(carpeta=carpeta)
    if nivel:
        tutor.fijar_nivel(nivel)
    return tutor


#: Cada programa lleva un fallo de los que el analizador propio tiene que ver, con
#: la regla que lo delata. Son programas de verdad (con su clase y su `main`): el
#: analizador no adivina, mira el código tal como se escribe.
CASOS = (
    ('class Hola {\n  public static void main(String[] args) {\n'
     '    System.out.println("hola")\n  }\n}', "punto_y_coma"),
    ('string nombre = "Ana";', "string_minuscula"),
    ('system.out.println("hola");', "system_minuscula"),
    ('System.out.printline("hola");', "printline_mal_escrito"),
    ("if x > 3 {\n}", "condicion_sin_parentesis"),
    ("if (x = 3) {\n}", "asignacion_en_condicion"),
    ('System.out.println("hola);', "cadena_sin_cerrar"),
    ("class Hola {\n  void f() {", "llave_sin_cerrar"),
    ("class Hola {\n}\n}", "llave_sobrante"),
    ('System.out.println("hola"));', "parentesis_sobrante"),
    ("int[] numeros = new int[3;", "corchete_sin_cerrar"),
    ('if (nombre == "Ana") {\n}', "cadena_con_igualdad"),
    ("/* comentario\nclass Hola {}", "comentario_sin_cerrar"),
)

#: Un programa que compila tal cual: sirve de plantilla y no debe dar ni un aviso.
BUENO = ('public class Hola {\n  public static void main(String[] args) {\n'
         '    System.out.println("hola");\n  }\n}')

#: Programa completo con `Scanner`: lo usa la prueba de «Probar» (ejecutar).
SUMA = ('import java.util.Scanner;\n\npublic class Suma {\n'
        '    public static void main(String[] args) {\n'
        '        Scanner lector = new Scanner(System.in);\n'
        '        int a = lector.nextInt();\n'
        '        int b = lector.nextInt();\n'
        '        System.out.println("Suma: " + (a + b));\n'
        '    }\n}\n')

#: Programa que no compila: `int` guardando un texto y una variable sin declarar.
ROTO = ('public class Roto {\n  public static void main(String[] args) {\n'
        '    int x = "texto";\n    System.out.println(y);\n  }\n}')


def pruebas_deteccion():
    """El analizador propio ve cada fallo típico, en su línea y su columna."""
    print("== El analizador local ve los fallos de empezar ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        for codigo, esperada in CASOS:
            datos = tutor.revisar(codigo, compilar=False)
            reglas = [fallo["regla"] for fallo in datos["errores"]]
            comprobar(esperada in reglas,
                      f"ve «{esperada}» y lo llama por su nombre")
            fallo = next((f for f in datos["errores"] if f["regla"] == esperada), None)
            comprobar(bool(fallo) and fallo["linea"] >= 1 and fallo["columna"] >= 1,
                      f"«{esperada}» llega con línea y columna (no un aviso suelto)")
            comprobar(bool(fallo) and fallo["mensaje"] and fallo["sugerencia"],
                      f"«{esperada}» se explica: qué pasa y cómo se arregla")
            comprobar(all(set(fallo) == {"linea", "columna", "regla", "mensaje",
                                         "sugerencia", "gravedad"}
                          for fallo in datos["errores"]),
                      f"«{esperada}» trae el mismo formato que todo lo demás")
        limpio = tutor.revisar(BUENO, compilar=False)
        comprobar(limpio["ok"] and not limpio["errores"] and limpio["total"] == 0,
                  "un programa correcto no recibe ni un aviso")
        comprobar("\u2705" in limpio["texto"],
                  "y el panel lo dice con un «todo bien», no con una lista vacía")


def pruebas_posiciones():
    """La línea y la columna son las del editor: las de verdad, no aproximadas."""
    print("\n== La línea y la columna apuntan al sitio exacto ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        codigo = ('public class Hola {\n'
                  '  public static void main(String[] args) {\n'
                  '    System.out.println("hola")\n'
                  '  }\n}')
        fallo = tutor.revisar(codigo, compilar=False)["errores"][0]
        comprobar(fallo["linea"] == 3 and fallo["columna"] == 31,
                  "el punto y coma que falta se señala en su línea, justo al final "
                  "(la columna 31 es donde va el `;`, tras los 30 caracteres de la línea)")
        codigo = 'class A {\n    int x = 1;\n    string y;\n}'
        datos = tutor.revisar(codigo, compilar=False)
        fallo = next(f for f in datos["errores"] if f["regla"] == "string_minuscula")
        comprobar(fallo["linea"] == 3 and fallo["columna"] == 5,
                  "y `string` se señala en la línea 3, donde empieza la palabra")
        comprobar("línea 3" in datos["texto"],
                  "el texto del panel repite la línea para poder ir a ella")


def pruebas_compilador():
    """Con JDK manda `javac`; sin JDK se dice y se sigue revisando lo básico."""
    print("\n== El compilador de verdad (javac) ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        hay_jdk = tutor.hay_jdk()
        comprobar(isinstance(hay_jdk, bool),
                  "el taller sabe si hay JDK (y lo responde sin romperse)")
        datos = tutor.revisar(BUENO)
        comprobar(datos["jdk"] == hay_jdk,
                  "la revisión dice si ha podido compilar o solo revisar lo básico")
        if hay_jdk:
            comprobar(datos["compilado"] and not datos["errores"],
                      "un programa correcto compila y se queda sin avisos")
            roto = tutor.revisar(ROTO)
            reglas = [fallo["regla"] for fallo in roto["errores"]]
            comprobar(not roto["compilado"] and "javac" in reglas,
                      "uno que no compila trae los fallos del compilador")
            comprobar(any(fallo["linea"] == 3 for fallo in roto["errores"])
                      and any(fallo["linea"] == 4 for fallo in roto["errores"]),
                      "con la línea de cada uno (los dos fallos, en la 3 y la 4)")
            comprobar(all(fallo["sugerencia"] for fallo in roto["errores"]),
                      "y traducidos a una pista que se entiende")
            comprobar(not roto["ok"], "el resultado no se da por bueno")
        else:
            comprobar(not datos["errores"] and "JDK" in datos["texto"]
                      and "básica" in datos["texto"],
                      "sin JDK avisa de que solo revisa lo básico (sin inventar fallos)")
        # Un fallo estructural (una comilla sin cerrar) no se le pasa a javac: el
        # compilador se perdería y soltaría decenas de errores en cascada.
        estructural = tutor.revisar('System.out.println("hola);', compilar=True)
        comprobar(not estructural["compilado"]
                  and all(fallo["regla"] != "javac" for fallo in estructural["errores"]),
                  "con una comilla sin cerrar no se compila: se enseña solo lo claro")


def pruebas_ejecutar():
    """«Probar»: compila, ejecuta y devuelve lo que imprime el programa."""
    print("\n== Probar el programa (compilar y ejecutar) ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        datos = tutor.ejecutar(SUMA, "2\n3\n")
        if tutor.hay_jdk():
            comprobar(datos["ok"] and datos["compilado"],
                      "el programa compila y termina bien")
            comprobar("Suma: 5" in datos["salida"],
                      "y lo que imprime llega tal cual (le ha leído el 2 y el 3)")
            comprobar("Salida del programa" in datos["texto"],
                      "el panel lo enseña en su apartado de salida")
            roto = tutor.ejecutar(ROTO)
            comprobar(not roto["ok"] and "compilar" in roto["texto"],
                      "si no compila, dice que primero hay que arreglarlo")
            vacio = tutor.ejecutar("")
            comprobar(not vacio["ok"] and "Escribe el programa" in vacio["texto"],
                      "y sin código pide el programa, sin lanzar nada")
        else:
            comprobar(not datos["ok"] and not datos["jdk"] and "JDK" in datos["texto"],
                      "sin JDK no se ejecuta: el taller lo explica en vez de fallar")


def pruebas_tablas():
    """El temario, la documentación y las comparaciones se leen sin conexión."""
    print("\n== Las tablas escritas: temario, documentación y comparaciones ==")
    comprobar(all({"clave", "titulo", "icono", "resumen", "nivel"} <= set(tema)
                  for tema in prog.BASES),
              "cada tema del temario trae clave, título, icono, resumen y nivel")
    comprobar(all(tema["nivel"] in prog.NIVELES for tema in prog.BASES)
              and {tema["nivel"] for tema in prog.BASES} == set(prog.NIVELES),
              "y hay temas de los tres niveles (de menos a más)")
    comprobar(len({tema["clave"] for tema in prog.BASES}) == len(prog.BASES),
              "sin claves repetidas: cada tema se puede pedir por su nombre")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        temario = tutor.bases()
        comprobar("Las bases de Java" in temario
                  and all(tema["clave"] in temario for tema in prog.BASES),
                  "«Bases» lista el temario entero, tema a tema")
        comprobar(all(nivel in temario for nivel in prog.NIVELES),
                  "agrupado por niveles")
        leccion = tutor.leccion("bucles")
        comprobar("Bucles" in leccion and "###" in leccion,
                  "«Lección» trae el tema pedido, por apartados")
        comprobar(not leccion.startswith(MARCA_PROFE),
                  "y lo saca de sus tablas: no gasta IA")
        comprobar(tutor.leccion("kotlin flows").startswith(MARCA_PROFE),
                  "un tema que no está en el temario se le pide a la IA")
        comprobar("Dime de qué tema" in tutor.leccion(""),
                  "y sin tema escrito pide cuál, en vez de inventarse uno")
        for entrada in prog.DOCUMENTACION:
            texto = tutor.documentacion(entrada["clave"])
            comprobar(texto.startswith("## ") and not texto.startswith(MARCA_PROFE),
                      f"la documentación de «{entrada['clave']}» se lee sin IA")
        comprobar("String" in tutor.documentacion("String")
                  and "inmutable" in tutor.documentacion("String"),
                  "con lo que hay que saber de verdad (`String`, por ejemplo)")
        comprobar("De qué quieres la documentación" in tutor.documentacion(""),
                  "y sin tema pide qué clase o método mirar")
        for entrada in prog.COMPARACIONES:
            texto = tutor.comparar(entrada["clave"])
            comprobar(texto.startswith("## ") and not texto.startswith(MARCA_PROFE),
                      f"la comparación «{entrada['clave']}» viene razonada, sin IA")
        equals = tutor.comparar("equals")
        comprobar("equals" in equals and "==" in equals and "regla" in equals.lower(),
                  "«¿Por qué…?» compara, razona y se queda con una regla")
        comprobar("Dime qué quieres comparar" in tutor.comparar(""),
                  "y sin tema pide qué comparar")


def pruebas_encargos():
    """Lo que sí necesita la IA: se le pide con la marca y con el nivel del alumno."""
    print("\n== Los encargos a la IA (marca del profesor y contexto) ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta, "Intermedio")
        codigo = 'class A {\n    int x = 1;\n    string y;\n}'
        for nombre, texto in (("ejercicios", tutor.ejercicios("bucles", "4")),
                              ("preguntar", tutor.preguntar("¿por qué no compila?", codigo)),
                              ("explicar", tutor.explicar(codigo))):
            comprobar(texto.startswith(MARCA_PROFE),
                      f"«{nombre}» se marca para pedírselo a la IA")
            comprobar("Nivel del alumno: Intermedio" in texto,
                      f"y «{nombre}» lleva el nivel del alumno en el encargo")
            comprobar("Java" in texto and "español" in texto,
                      f"«{nombre}» pide Java y respuesta en español")
        ejercicios = tutor.ejercicios("bucles", "4")
        comprobar("4 ejercicios" in ejercicios and "bucles" in ejercicios.lower(),
                  "los ejercicios llevan cuántos y de qué tema")
        comprobar("10 ejercicios" in tutor.ejercicios("", "99"),
                  "y el número se limita a lo razonable (ni 99 de golpe)")
        explicar = tutor.explicar(codigo)
        comprobar("línea 3" in explicar and "string_minuscula" in explicar,
                  "«¿Por qué…?» le pasa a la IA los fallos con su línea y su regla")
        comprobar("Escríbeme la duda" in tutor.preguntar(""),
                  "sin duda escrita, el tutor pide que se la escriban (sin gastar IA)")
        comprobar("Pon tu programa" in tutor.explicar(""),
                  "y sin código, «¿Por qué…?» pide el programa antes de molestar a la IA")
        tutor.registrar(tutor.revisar(codigo, compilar=False)["errores"], "práctica")
        comprobar("Fallos que más se le repiten" in tutor.ejercicios("", "3"),
                  "el encargo recuerda a la IA los fallos que se le repiten al alumno")
        largo = tutor.explicar("x" * (prog.MAX_CODIGO + 50), errores=[])
        comprobar("x" * prog.MAX_CODIGO in largo
                  and "x" * (prog.MAX_CODIGO + 1) not in largo,
                  f"un programa enorme se recorta a {prog.MAX_CODIGO} caracteres")
        # El chat del taller: cada pregunta lleva el código y lo ya hablado.
        chat = tutor.conversar("¿por qué falla mi línea 3?", codigo)
        comprobar(chat.startswith(MARCA_PROFE) and "Nivel del alumno: Intermedio" in chat,
                  "la duda del chat se marca para la IA y lleva el nivel del alumno")
        comprobar("Su código" in chat and "string_minuscula" in chat,
                  "con el programa que tiene escrito y sus fallos, para contestar de él")
        comprobar("Escríbeme la duda" in tutor.conversar("")
                  and not tutor.conversar("").startswith(MARCA_PROFE),
                  "sin duda escrita, el chat pide que se la escriban (sin gastar IA)")
        hilo = [("Tú", "¿qué es un ArrayList?"), ("Profe", "Una lista que crece sola.")]
        segundo = tutor.conversar("¿y un HashMap?", codigo, hilo)
        comprobar("Lo que ya se han dicho" in segundo and "ArrayList" in segundo,
                  "la segunda pregunta lleva el hilo de la conversación")
        comprobar("Duda del alumno: ¿y un HashMap?" in segundo
                  and segundo.startswith(MARCA_PROFE),
                  "con la duda nueva aparte, y marcada para la IA")
        comprobar(ProgrammingTutor._hilo_en_texto([]) == ""
                  and ProgrammingTutor._hilo_en_texto(None) == "",
                  "sin conversación no se le inventa contexto a la IA")
        pesado = [("Tú", "x" * 3000), ("Profe", "y" * 3000), ("Tú", "la última")]
        recortado = ProgrammingTutor._hilo_en_texto(pesado)
        comprobar("la última" in recortado
                  and len(recortado) <= prog.MAX_HILO_CHAT + 200,
                  f"el hilo se recorta a lo que cabe ({prog.MAX_HILO_CHAT} caracteres)")
        muchas = [("Tú", f"pregunta {numero}") for numero in range(20)]
        dentro = ProgrammingTutor._hilo_en_texto(muchas)
        comprobar(f"pregunta 19" in dentro and "pregunta 0" not in dentro,
                  f"y solo viajan los últimos {prog.MAX_TURNOS_CHAT} turnos")


def pruebas_estado():
    """El avance (nivel, prácticas y fallos) se guarda y se recupera tal cual."""
    print("\n== El avance del alumno se guarda en su carpeta ==")
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        datos = tutor.resumen()
        comprobar(datos["nivel"] == prog.NIVEL_POR_DEFECTO and datos["practicas"] == 0
                  and not datos["repetidos"] and not datos["desde"],
                  "de estreno: nivel por defecto, sin prácticas y sin fallos")
        codigo = 'class A {\n    int x = 1;\n    string y;\n}'
        errores = tutor.revisar(codigo, compilar=False)["errores"]
        tutor.registrar(errores, "prueba")
        datos = tutor.resumen()
        comprobar(datos["practicas"] == 1 and datos["desde"],
                  "corregir apunta la práctica y el día en que empezó")
        comprobar(bool(datos["repetidos"]) and datos["repetidos"][0][0] == "string_minuscula",
                  "y apunta el fallo: el que más se repite va primero")
        clave, info = datos["repetidos"][0]
        comprobar(info["veces"] == 1 and info["titulo"] and info["sugerencia"],
                  "con cuántas veces, qué pasó y la pista para arreglarlo")
        tutor.registrar(errores, "prueba")
        comprobar(tutor.frecuentes()[0][1]["veces"] == 2,
                  "si el mismo fallo vuelve, se cuenta otra vez")
        ruta = os.path.join(carpeta, "estado.json")
        with open(ruta, "r", encoding="utf-8") as archivo:
            guardado = json.load(archivo)
        comprobar(guardado["practicas"] == 2 and "string_minuscula" in guardado["errores"],
                  "y todo queda en estado.json, dentro de su carpeta")
        otro = ProgrammingTutor(carpeta=carpeta)
        comprobar(otro.resumen()["practicas"] == 2,
                  "al volver a abrir el taller, el avance sigue ahí")
        progreso = tutor.progreso()
        comprobar("Tu avance" in progreso and "Principiante" in progreso
                  and "2" in progreso,
                  "«Avance» cuenta el nivel y las prácticas")
        comprobar("vez/veces" in progreso and "2 vez" in progreso,
                  "y lista los fallos repetidos con cuántas veces salieron")
        comprobar("JDK" in progreso,
                  "y dice si hay compilador o si solo se revisa lo básico")
        aviso = tutor.fijar_nivel("nivel que no existe")
        comprobar(aviso.startswith("No sé con qué nivel") and tutor.nivel() ==
                  prog.NIVEL_POR_DEFECTO,
                  "un nivel que no entiende no cambia nada: lo dice y sigue igual")
        cambio = tutor.fijar_nivel("nivel avanzado")
        comprobar("Principiante → Avanzado" in cambio and tutor.nivel() == "Avanzado",
                  "«nivel avanzado» cambia el nivel de verdad")
        comprobar("Avanzado" in tutor.resumen()["nivel"],
                  "y el cambio se guarda (no se pierde al cerrar)")
        comprobar("Ya estabas en Avanzado" in tutor.fijar_nivel("Avanzado"),
                  "repetir el mismo nivel no lo toca")
        borrado = tutor.progreso("borrar")
        datos = tutor.resumen()
        comprobar(datos["practicas"] == 0 and not datos["repetidos"]
                  and datos["nivel"] == "Avanzado",
                  "«borrar» limpia prácticas y fallos, pero respeta el nivel")
        comprobar("He borrado el avance" in borrado and "Avanzado" in borrado,
                  "y lo cuenta con el nivel que deja")
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write("{esto no es json")
        comprobar(tutor.resumen()["nivel"] == prog.NIVEL_POR_DEFECTO
                  and tutor.resumen()["practicas"] == 0,
                  "un estado ilegible no rompe nada: se empieza de cero")

    # Y el historial de prácticas no crece sin freno.
    with tempfile.TemporaryDirectory() as carpeta:
        tutor = tutor_temporal(carpeta)
        for numero in range(prog.MAX_EVENTOS + 5):
            tutor.registrar([], f"práctica {numero}")
        comprobar(len(tutor._leer_estado()["temas"]) == prog.MAX_EVENTOS,
                  f"solo se guardan las últimas {prog.MAX_EVENTOS} prácticas")
        comprobar(prog.MAX_EVENTOS + 5 == tutor.resumen()["practicas"],
                  "aunque la cuenta total no se pierde")


def pruebas_apartado():
    """El taller tiene su apartado en la ventana, con todo lo que necesita.

    Evita el fallo de fondo: que el apartado prometa algo que el módulo ya no da,
    o que el editor acabe llamando a algo que no existe.
    """
    print("\n== Apartado «Aprender programación» de la ventana ==")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def leer(*partes):
        with open(os.path.join(raiz, *partes), encoding="utf-8") as archivo:
            return archivo.read()

    prompt = leer("modules", "api_brain.py")
    sistema = leer("modules", "system_actions.py")
    ventana = leer("app_gui.py")
    taller = leer("views", "programacion.py")
    apartado_chat = leer("views", "chat.py")
    codigo_tutor = leer("modules", "programming_tutor.py")

    def metodo(codigo, nombre):
        """El trozo de código de un método, para poder mirarlo."""
        trozo = codigo[codigo.index(f"def {nombre}(self"):]
        siguiente = trozo.find("\n    def ", 10)
        return trozo[:siguiente] if siguiente > 0 else trozo

    # --- El cerebro tiene el profesor de programación
    comprobar(hasattr(APIBrain, "SISTEMA_PROGRAMADOR")
              and "profesor" in APIBrain.SISTEMA_PROGRAMADOR,
              "el cerebro tiene el mensaje de sistema del profesor (SISTEMA_PROGRAMADOR)")
    comprobar("Java" in APIBrain.SISTEMA_PROGRAMADOR
              and "español" in APIBrain.SISTEMA_PROGRAMADOR,
              "que pide Java, respuesta en español y ejemplos que compilen")
    parametros = inspect.signature(APIBrain.analizar_documento).parameters
    comprobar("sistema" in parametros,
              "y analizar_documento acepta ese mensaje de sistema")
    comprobar("self.programacion = ProgrammingTutor(config_path)" in sistema,
              "el asistente monta el taller con la configuración del usuario")
    comprobar("PROGRAMACION_" not in sistema,
              "y el chat no atiende ninguna acción de programación")
    comprobar(not re.findall(r"ACCION:\s*PROGRA", prompt),
              "tampoco el prompt del chat ofrece acciones de código")

    # --- La ventana tiene el apartado, con su botón
    comprobar("self.vista_programacion = VistaProgramacion(self)" in ventana
              and "class VistaProgramacion(Vista):" in taller,
              "la ventana tiene el taller como una vista propia (views/programacion.py)")
    comprobar('command=lambda: self._mostrar_vista("programar")' in ventana
              and 'elif vista == "programar":' in ventana,
              "con su botón en la barra lateral y su rama en _mostrar_vista")
    comprobar('("programar", getattr(self, "btn_programar", None))' in ventana,
              "y el apartado queda marcado en la barra lateral mientras está abierto")
    comprobar("TAREAS_PROGRAMACION" in taller and "AYUDA_PROGRAMACION" in taller
              and "CODIGO_EJEMPLO" in taller,
              "las tareas, la ayuda de entrada y el código de ejemplo están puestos")
    comprobar("TAREA_PROG_PRINCIPAL" in taller and "TAREA_PROG_PELIGRO" in taller
              and "MAX_AVISOS_PANTALLA" in taller,
              "con la tarea principal destacada, la peligrosa aparte y un tope de avisos")
    comprobar("from modules.programming_tutor import MARCA_PROFE, NIVELES as NIVELES_JAVA"
              in taller,
              "y la marca del profesor y los niveles, importados del módulo")
    comprobar("def _accion_programacion(self, tarea):" in taller
              and "def _pedir_al_profe(self, encargo):" in taller,
              "las tareas del taller se lanzan desde el apartado")
    comprobar("threading.Thread(target=self._pedir_al_profe" in taller
              and "sistema=APIBrain.SISTEMA_PROGRAMADOR" in taller,
              "y la explicación se pide a la IA en un hilo, con el profesor de Java")
    comprobar("threading.Thread(target=self._probar_programacion" in taller,
              "ejecutar el programa también va en un hilo (no congela la ventana)")
    comprobar("def _escribir_programacion(self, texto):" in taller
              and "def _actualizar_programacion(self):" in taller
              and "def _cambiar_nivel_programacion(self, nivel):" in taller,
              "el panel, la cabecera del avance y el nivel son suyos")
    comprobar("def _revisar_programacion(self, compilar=False, apuntar=False):" in taller
              and "self.after(700, self._revision_al_escribir)" in taller,
              "y la revisión va sola al dejar de teclear, con 700 ms de espera")
    comprobar("@staticmethod\n    def _avisos_de_revision(datos):" in taller,
              "los avisos de la revisión se montan en un sitio único (y se prueban)")

    # --- El chat no sabe nada del taller
    chat = metodo(apartado_chat, "_procesar_mensaje")
    comprobar("MARCA_PROFE" not in chat and "programacion" not in chat,
              "el chat no mira la marca del profesor de programación")

    # --- El chat del taller: su propia conversación, aparte del chat de Jarvis
    comprobar("PANEL_PROG_CLASE" in taller and "PANEL_PROG_CHAT" in taller
              and 'def mostrar_panel_programacion(self, panel="clase"):' in taller,
              "el centro del taller tiene sus dos caras: la clase y su chat")
    comprobar("def _crear_panel_chat(self, parent):" in taller
              and "def enviar_chat_programacion(self, texto=None):" in taller
              and "def _agregar_burbuja_prog(self, autor, texto):" in taller,
              "y el chat tiene su tarjeta: mensajes, caja de escribir y enviar")
    comprobar("self.txt_chat_prog.bind(" in taller
              and "def _enviar_chat_prog_con_enter(self" in taller,
              "con la caja del chat enganchada al teclado (Enter manda el mensaje)")
    comprobar("self.app.system.programacion.conversar(" in taller
              and "self._hilo_prog[-MAX_TURNOS_CHAT_PROG:]" in taller
              and "threading.Thread(target=self._pedir_chat_prog" in taller,
              "las dudas se le piden a la IA en un hilo, con lo ya hablado")
    comprobar("def _apuntar_turno_chat(self, autor, texto):" in taller
              and "chat_taller_" in taller,
              "y la conversación se apunta en un .md dentro de la carpeta del taller")
    comprobar("def nuevo_chat_programacion(self):" in taller
              and "def conversacion_programacion(self):" in taller,
              "con «Nuevo» para empezar otra conversación (sin borrar la anterior)")

    # --- El módulo sigue ofreciendo lo que el apartado llama
    for nombre in ("revisar", "ejecutar", "bases", "leccion", "documentacion", "comparar",
                   "ejercicios", "preguntar", "conversar", "progreso", "resumen",
                   "fijar_nivel", "hay_jdk"):
        comprobar(f"def {nombre}(self" in codigo_tutor,
                  f"el módulo tiene `{nombre}`, que es lo que llama el apartado")
    accion = metodo(taller, "_accion_programacion")
    for tarea in ("bases", "leccion", "documentacion", "comparar", "ejercicios",
                  "preguntar", "progreso", "probar"):
        comprobar(f'"{tarea}"' in accion,
                  f"y el apartado sabe atender la tarea «{tarea}»")
    comprobar("TAREA_PROG_PRINCIPAL" in accion and "TAREA_PROG_PELIGRO" in accion,
              "con la corrección como tarea principal y el borrado confirmado aparte")
    comprobar("self.preguntar_programacion()" in accion,
              "«Preguntar» lleva la duda al chat del taller, no al de Jarvis")


def main_pruebas():
    pruebas_deteccion()
    pruebas_posiciones()
    pruebas_compilador()
    pruebas_ejecutar()
    pruebas_tablas()
    pruebas_encargos()
    pruebas_estado()
    pruebas_apartado()
    print(f"\nTOTAL: {total[0]} comprobaciones, {len(fallos)} fallos")
    for fallo in fallos:
        print(f"  - {fallo}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main_pruebas())
