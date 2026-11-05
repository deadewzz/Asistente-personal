"""Aprender programación: las bases, la corrección en vivo y las respuestas.

El apartado «Aprender programación» de la ventana no es un chat: es un taller.
Aquí el alumno escribe código Java, lo ve revisado **mientras escribe** y pide
las explicaciones que necesite. Este módulo es todo lo que hay detrás:

1. **Corrección en vivo** (``revisar``): dos analizadores que se complementan.
   - Uno **propio y local** que no gasta IA ni necesita internet: llaves,
     paréntesis y corchetes sin cerrar, puntos y coma que faltan, cadenas sin
     terminar, ``=`` donde iba ``==``, ``string`` en minúscula, ``printline``...
     Cada fallo se devuelve con su **línea y su columna** y con lo que hay que
     hacer para arreglarlo.
   - El **compilador de verdad** (``javac``) cuando el JDK está instalado: sus
     mensajes se leen y se convierten al mismo formato (línea, columna,
     mensaje), así el editor puede marcar el renglón exacto. Si no hay JDK, todo
     lo demás sigue funcionando y se avisa de que solo se revisa lo básico.
   ``ejecutar`` compila y corre el programa con un tope de tiempo, para que el
   alumno vea lo que sale por pantalla sin salir de la ventana.
2. **Las bases** (``bases`` y ``leccion``): un temario de Java escrito aquí,
   tema por tema (variables, condiciones, bucles, métodos, arrays, clases,
   herencia, colecciones, excepciones, entrada por teclado y cómo leer un error
   de compilación), con su sintaxis, un ejemplo comentado, los errores típicos y
   un ejercicio. No hace falta IA: se lee sin conexión.
3. **La documentación** (``documentacion``): una guía de consulta de la API que
   más se usa al empezar (``String``, ``ArrayList``, ``HashMap``, ``Scanner``...)
   con la firma, un ejemplo, las trampas y el enlace a la documentación oficial
   de Oracle; y si lo que se busca no está en la guía, se le pide a la IA.
4. **¿Por qué este y no el otro?** (``comparar``): comparaciones razonadas de
   los pares que más dudas generan (``==`` frente a ``equals``, ``+`` frente a
   ``StringBuilder``, ``ArrayList`` frente a ``LinkedList``...), con cuándo usar
   cada uno, ejemplos y el error típico; si el par no está en la tabla, se le
   pide a la IA con ese mismo esquema.
5. **El avance** (``registrar`` y ``progreso``): nivel, prácticas y los fallos
   que más se repiten, en ``Jarvis/programacion/estado.json``.

Las tareas que sí necesitan la IA devuelven ``MARCA_PROFE + encargo`` (como el
tutor de inglés con ``__TUTOR__``). El apartado de la ventana pide el encargo
al cerebro con ``APIBrain.SISTEMA_PROGRAMADOR``: respuesta larga, en Markdown y
sin leer comandos de acción. Lo local (revisar, bases, documentación y
comparaciones conocidas) se queda en el módulo y no gasta ninguna llamada.

Java es el primer lenguaje (``LENGUAJES``); el resto del módulo está separado
por lenguaje para poder añadir otro sin tocar la ventana.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime

from modules import rutas


#: Marca con la que el módulo señala «esto es el encargo para la IA, no el
#: resultado». El apartado de la ventana pide solo lo primero al cerebro, con el
#: mensaje de sistema del profesor de programación (``SISTEMA_PROGRAMADOR``).
MARCA_PROFE = "__PROFE__"

#: Lenguajes que entiende el apartado. Java es el primero; de momento es el
#: único, y es lo que se muestra en la ventana.
LENGUAJE = "Java"
LENGUAJES = ("Java",)

#: Niveles del alumno (se guardan en el estado y viajan en el encargo).
NIVELES = ("Principiante", "Intermedio", "Avanzado")
NIVEL_POR_DEFECTO = "Principiante"
NIVELES_EN_PALABRAS = {
    "desde cero": "Principiante", "principiante": "Principiante",
    "basico": "Principiante", "básico": "Principiante", "inicial": "Principiante",
    "intermedio": "Intermedio", "medio": "Intermedio",
    "avanzado": "Avanzado", "experto": "Avanzado",
}

#: Límites de tamaño (lo que viaja al prompt o se guarda se recorta).
MAX_CODIGO = 8000            # caracteres de código que se analizan
MAX_PISTAS = 8               # fallos detectados que se le pasan a la IA
MAX_MEMORIA = 6              # fallos repetidos que se recuerdan a la IA
MAX_EVENTOS = 20             # últimas prácticas guardadas en el estado
MAX_EJERCICIOS = 10          # techo de ejercicios pedidos de una vez
MAX_SALIDA = 6000            # caracteres de salida del programa que se enseñan
MAX_TURNOS_CHAT = 8          # turnos del chat del taller que se le pasan a la IA
MAX_HILO_CHAT = 4000         # caracteres del hilo del chat que caben en el encargo
TIEMPO_COMPILAR = 40         # segundos que se espera a javac
TIEMPO_EJECUTAR = 12         # segundos que se deja correr al programa

#: Para que javac y java no abran una consola al ejecutarse desde la ventana.
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# Utilidades pequeñas
# ---------------------------------------------------------------------------
def _normalizar(texto):
    """Texto en minúsculas y sin acentos, para buscar sin pelearse con tildes."""
    limpio = str(texto or "").lower()
    for acentuada, llana in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"),
                             ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        limpio = limpio.replace(acentuada, llana)
    return " ".join(limpio.split())


def _linea_columna(codigo, indice):
    """Convierte una posición del texto en (línea, columna), ambas desde 1."""
    indice = max(0, min(len(codigo), int(indice)))
    linea = codigo.count("\n", 0, indice) + 1
    comienzo = codigo.rfind("\n", 0, indice) + 1
    return linea, indice - comienzo + 1


def _error(linea, columna, regla, mensaje, sugerencia, gravedad="error"):
    """Un fallo con el mismo formato lo detecte quien lo detecte."""
    return {"linea": max(1, int(linea or 1)), "columna": max(0, int(columna or 0)),
            "regla": str(regla), "mensaje": str(mensaje).strip(),
            "sugerencia": str(sugerencia).strip(), "gravedad": gravedad}


def _numero(texto, defecto, minimo=3, maximo=MAX_EJERCICIOS):
    """Número pedido por el usuario ('5', 'cinco ejercicios') con topes."""
    coincidencia = re.search(r"\b(\d{1,2})\b", str(texto or ""))
    if not coincidencia:
        return defecto
    return max(minimo, min(maximo, int(coincidencia.group(1))))


def _cantidad(numero, singular, plural):
    """'1 ejercicio' / '3 ejercicios': el encargo también se lee bien en singular."""
    return f"{numero} {singular if int(numero) == 1 else plural}"


def _bloque(texto, lenguaje="java"):
    """Texto dentro de un bloque de código Markdown (la ventana lo pinta mono)."""
    return f"```{lenguaje}\n{str(texto).strip()}\n```"


def _decodificar(datos):
    """Convierte la salida de javac/java en texto (Windows no siempre usa UTF-8)."""
    if isinstance(datos, bytes):
        for codificacion in ("utf-8", "cp1252", "latin-1"):
            try:
                return datos.decode(codificacion)
            except UnicodeDecodeError:
                continue
        return datos.decode("utf-8", errors="replace")
    return str(datos or "")


# ---------------------------------------------------------------------------
# Analizador local: comentarios, textos y estructura del código
# ---------------------------------------------------------------------------
#: Fallos de estructura que dejan el código tan roto que el compilador de verdad
#: solo añadiría errores en cascada (ver ``_es_estructural``).
REGLAS_ESTRUCTURALES = frozenset({
    "comentario_sin_cerrar", "texto_sin_cerrar", "cadena_sin_cerrar", "caracter_sin_cerrar",
    "llave_sin_cerrar", "llave_sobrante", "parentesis_sin_cerrar", "parentesis_sobrante",
    "corchete_sin_cerrar", "corchete_sobrante",
})


def _limpiar_codigo(codigo):
    """Vacía comentarios y textos dejando las posiciones intactas.

    Devuelve ``(texto, problemas)``. En ``texto`` todo sigue en su sitio (misma
    línea y misma columna), pero lo que hay dentro de comentarios, cadenas y
    caracteres se cambia por espacios: así las llaves o los puntos y coma que
    aparecen dentro de un texto no se cuentan como código. ``problemas`` trae
    las posiciones de las comillas o los comentarios que se quedaron sin cerrar.
    """
    texto = "" if codigo is None else str(codigo)
    resultado = list(texto)
    problemas = []
    total = len(texto)
    indice = 0

    def blanquear(desde, hasta):
        for posicion in range(max(0, desde), min(hasta, total)):
            if resultado[posicion] not in "\r\n":
                resultado[posicion] = " "

    while indice < total:
        if texto.startswith("//", indice):
            fin = texto.find("\n", indice)
            fin = total if fin == -1 else fin
            blanquear(indice, fin)
            indice = fin
        elif texto.startswith("/*", indice):
            fin = texto.find("*/", indice + 2)
            if fin == -1:
                problemas.append((indice, "comentario_sin_cerrar"))
                blanquear(indice, total)
                indice = total
            else:
                blanquear(indice, fin + 2)
                indice = fin + 2
        elif texto.startswith('"""', indice):
            fin = texto.find('"""', indice + 3)
            if fin == -1:
                problemas.append((indice, "texto_sin_cerrar"))
                blanquear(indice, total)
                indice = total
            else:
                blanquear(indice, fin + 3)
                indice = fin + 3
        elif texto[indice] in "\"'":
            comilla = texto[indice]
            cierre = "cadena_sin_cerrar" if comilla == '"' else "caracter_sin_cerrar"
            posicion = indice + 1
            cerrada = False
            while posicion < total and texto[posicion] != "\n":
                if texto[posicion] == "\\":
                    posicion += 2
                    continue
                if texto[posicion] == comilla:
                    cerrada = True
                    break
                posicion += 1
            if not cerrada:
                problemas.append((indice, cierre))
                blanquear(indice + 1, posicion)
                indice = posicion
            else:
                blanquear(indice + 1, posicion)
                indice = posicion + 1
        else:
            indice += 1
    return "".join(resultado), problemas


def _posiciones_sueltas(texto, abre, cierra):
    """Índices de los símbolos que abren sin cerrar y de los que cierran de más."""
    pila = []
    sueltas = []
    for indice, caracter in enumerate(texto):
        if caracter == abre:
            pila.append(indice)
        elif caracter == cierra:
            if pila:
                pila.pop()
            else:
                sueltas.append((indice, "sobra"))
    for indice in pila:
        sueltas.append((indice, "falta"))
    return sueltas


def _siguiente_continua(lineas, numero):
    """¿La instrucción sigue en la línea de abajo? (llamadas y cuentas largas)."""
    for siguiente in lineas[numero:]:
        limpia = siguiente.strip()
        if not limpia:
            continue
        return limpia[0] in ".+-*/%&|?:)=]" or limpia.startswith("instanceof")
    return False


RE_CONDICION = re.compile(r"\b(if|while)\s*\(([^()]*)\)")
RE_CADENA_COMPARADA = re.compile(r'"[^"\n]*"\s*(?:==|!=)|(?:==|!=)\s*"[^"\n]*"')
RE_STRING_MINUSCULA = re.compile(r"\bstring\b")
RE_SYSTEM_MINUSCULA = re.compile(r"\bsystem\s*\.")
RE_PRINTLINE = re.compile(r"\bSystem\s*\.\s*out\s*\.\s*printline\b")
RE_IF_SIN_PARENTESIS = re.compile(r"^[ \t]*(if|while)[ \t]+(?![(])", re.M)
RE_SALTO = re.compile(r"^\s*(return|break|continue|throw)\b[^;{}]*$")
RE_IMPORT = re.compile(r"^\s*(?:import|package)\s+[\w.*]+\s*$")
RE_DECLARACION = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|transient|volatile)\s+)*"
    r"(?:int|double|float|long|short|byte|char|boolean|String|var|Integer|Double|"
    r"Long|Float|Short|Byte|Character|Boolean)\b[^;{}]*$")
RE_ASIGNACION_TIPO = re.compile(
    r"^\s*[A-Za-z_$][\w$]*(?:<[^;{}]*>)?(?:\[\])?\s+[A-Za-z_$][\w$]*\s*=\s*[^=].*$")
RE_ASIGNACION_SUELTA = re.compile(
    r"^\s*[A-Za-z_$][\w$.\[\]]*\s*[+\-*/%]?=\s*[^=].*$")
RE_LLAMADA = re.compile(r"^\s*[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+\s*\(.*\)\s*$")
RE_CONTINUA = re.compile(r"[+\-*/%&|^=<>?:,(\[]\s*$")
RE_IMPORT_UTIL = re.compile(
    r"import\s+java\.util\.(?:Scanner|ArrayList|HashMap|HashSet|List|Map|Set|\*)\s*;")

def _analizar_local(codigo):
    """Revisa el código sin compilarlo: devuelve la lista de fallos con línea y columna."""
    texto = "" if codigo is None else str(codigo)
    limpio, problemas = _limpiar_codigo(texto)
    errores = []

    for indice, tipo in problemas:
        linea, columna = _linea_columna(texto, indice)
        if tipo == "comentario_sin_cerrar":
            errores.append(_error(
                linea, columna, tipo, "Comentario sin cerrar",
                "Este `/*` no tiene su `*/`: ciérralo o todo lo que venga detrás "
                "quedará comentado."))
        elif tipo == "texto_sin_cerrar":
            errores.append(_error(
                linea, columna, tipo, "Texto en bloque sin cerrar",
                'Un texto de varias líneas se abre y se cierra con `"""`: falta el cierre.'))
        elif tipo == "cadena_sin_cerrar":
            errores.append(_error(
                linea, columna, tipo, "Texto sin cerrar",
                'Falta la comilla doble de cierre (`"`) en esta línea.'))
        elif tipo == "caracter_sin_cerrar":
            errores.append(_error(
                linea, columna, tipo, "Carácter sin cerrar",
                "Un `char` va entre comillas simples y con un solo carácter: `'a'`."))

    for indice, tipo in _posiciones_sueltas(limpio, "{", "}"):
        linea, columna = _linea_columna(limpio, indice)
        if tipo == "falta":
            errores.append(_error(
                linea, columna, "llave_sin_cerrar", "Falta cerrar una llave `}`",
                "Esta `{` abre un bloque (la clase, un método, un `if`, un bucle...) "
                "y nunca se cierra."))
        else:
            errores.append(_error(
                linea, columna, "llave_sobrante", "Sobra una llave `}`",
                "Esta `}` no cierra ningún bloque abierto: revisa las llaves de arriba."))

    for indice, tipo in _posiciones_sueltas(limpio, "(", ")"):
        linea, columna = _linea_columna(limpio, indice)
        if tipo == "falta":
            errores.append(_error(
                linea, columna, "parentesis_sin_cerrar", "Falta cerrar un paréntesis `)`",
                "Cuenta los paréntesis de la línea: se abren y se cierran por parejas."))
        else:
            errores.append(_error(
                linea, columna, "parentesis_sobrante", "Sobra un paréntesis `)`",
                "Este `)` no tiene su `(`: revisa las condiciones y las llamadas."))

    for indice, tipo in _posiciones_sueltas(limpio, "[", "]"):
        linea, columna = _linea_columna(limpio, indice)
        if tipo == "falta":
            errores.append(_error(
                linea, columna, "corchete_sin_cerrar", "Falta cerrar un corchete `]`",
                "En los arrays se abre y se cierra con corchetes: `int[] numeros`."))
        else:
            errores.append(_error(
                linea, columna, "corchete_sobrante", "Sobra un corchete `]`",
                "Este `]` no tiene su `[`: revisa los arrays y los índices."))

    # Un solo `=` dentro de una condición casi siempre es un descuido.
    for coincidencia in RE_CONDICION.finditer(limpio):
        condicion = coincidencia.group(2)
        for posicion, caracter in enumerate(condicion):
            if caracter != "=":
                continue
            anterior = condicion[posicion - 1] if posicion else ""
            siguiente = condicion[posicion + 1] if posicion + 1 < len(condicion) else ""
            if anterior in "=!<>+-*/%&|^" or siguiente == "=":
                continue
            linea, columna = _linea_columna(limpio, coincidencia.start(2) + posicion)
            errores.append(_error(
                linea, columna, "asignacion_en_condicion",
                "Dentro de una condición, un solo `=` asigna; para comparar es `==`",
                "Si querías comparar, cambia `=` por `==`; si de verdad querías "
                "asignar, sácalo fuera del `if`.", gravedad="aviso"))
            break

    # Con textos, `==` compara «el mismo objeto», no «el mismo contenido».
    for coincidencia in RE_CADENA_COMPARADA.finditer(texto):
        linea, _ = _linea_columna(texto, coincidencia.start())
        cruda = texto.split("\n")[linea - 1].strip()
        if cruda.startswith("//") or cruda.startswith("*"):
            continue
        columna = coincidencia.start() - texto.rfind("\n", 0, coincidencia.start())
        errores.append(_error(
            linea, columna, "cadena_con_igualdad",
            "Un texto se compara con `equals()`, no con `==`",
            'Usa `texto1.equals(texto2)`. `==` solo mira si son el mismo objeto '
            "en memoria y a veces falla sin avisar.", gravedad="aviso"))

    for coincidencia in RE_STRING_MINUSCULA.finditer(limpio):
        linea, columna = _linea_columna(limpio, coincidencia.start())
        errores.append(_error(
            linea, columna, "string_minuscula", "En Java se escribe `String`, con mayúscula",
            'Los nombres de tipo empiezan por mayúscula: `String nombre = "Ana";`.'))

    for coincidencia in RE_SYSTEM_MINUSCULA.finditer(limpio):
        linea, columna = _linea_columna(limpio, coincidencia.start())
        errores.append(_error(
            linea, columna, "system_minuscula", "En Java se escribe `System`, con mayúscula",
            'Para imprimir: `System.out.println("Hola");`'))

    for coincidencia in RE_PRINTLINE.finditer(limpio):
        linea, columna = _linea_columna(limpio, coincidencia.start())
        errores.append(_error(
            linea, columna, "printline_mal_escrito", "El método es `println`, no `printline`",
            'Escribe `System.out.println("...");`'))

    for coincidencia in RE_IF_SIN_PARENTESIS.finditer(limpio):
        linea, columna = _linea_columna(limpio, coincidencia.start(1))
        errores.append(_error(
            linea, columna, "condicion_sin_parentesis",
            f"`{coincidencia.group(1)}` necesita la condición entre paréntesis",
            f"Escribe `{coincidencia.group(1)} (condición) {{ ... }}`."))

    # Punto y coma que falta: solo en líneas que parecen una instrucción completa.
    lineas = limpio.split("\n")
    for numero, linea in enumerate(lineas, start=1):
        instruccion = linea.strip()
        if not instruccion or instruccion.endswith((";", "{", "}", ":", "->", ",")):
            continue
        if RE_CONTINUA.search(instruccion) or _siguiente_continua(lineas, numero):
            continue
        motivo = None
        if RE_DECLARACION.match(instruccion) or RE_ASIGNACION_TIPO.match(instruccion) \
                or RE_ASIGNACION_SUELTA.match(instruccion) or RE_LLAMADA.match(instruccion):
            motivo = ("Cada instrucción de Java termina en `;`: a esta le falta",
                      "Añade el punto y coma al final de la línea.")
        elif RE_SALTO.match(instruccion):
            motivo = ("Falta el punto y coma `;`",
                      "`return`, `break`, `continue` y `throw` también terminan en `;`.")
        elif RE_IMPORT.match(instruccion):
            motivo = ("Falta el punto y coma `;`",
                      "`import` y `package` también terminan en `;`.")
        if motivo:
            errores.append(_error(numero, len(linea.rstrip()) + 1, "punto_y_coma", *motivo))

    # Clases de java.util que se usan sin importar (javac también lo diría).
    if limpio.strip() and not RE_IMPORT_UTIL.search(limpio):
        for clase in ("Scanner", "ArrayList", "HashMap", "HashSet"):
            coincidencia = re.search(r"\b%s\b" % clase, limpio)
            if not coincidencia:
                continue
            linea, columna = _linea_columna(limpio, coincidencia.start())
            errores.append(_error(
                linea, columna, "import_faltante", f"`{clase}` necesita un `import`",
                f"Añade arriba `import java.util.{clase};`.", gravedad="aviso"))
    errores.sort(key=lambda fallo: (fallo["linea"], fallo["columna"]))
    return errores


# ---------------------------------------------------------------------------
# El compilador de verdad (javac) cuando el JDK está instalado
# ---------------------------------------------------------------------------
RE_ERROR_JAVAC = re.compile(
    r"^(?P<archivo>.+?\.java):(?P<linea>\d+):\s*(?P<tipo>error|warning|aviso):\s*(?P<mensaje>.*)$")

#: Traducciones de los mensajes de javac que más se ven al empezar.
SUGERENCIAS_JAVAC = (
    ("';' expected", "Falta un punto y coma: javac esperaba `;` justo ahí."),
    ("cannot find symbol",
     "Java no conoce ese nombre: revisa que la variable esté declarada antes, "
     "que el método exista y que el `import` esté puesto."),
    ("reached end of file while parsing",
     "Falta cerrar alguna llave `}`: el archivo se acaba dentro de un bloque."),
    ("incompatible types",
     "Los tipos no encajan: mira si guardas un decimal en un `int` o un número en un `String`."),
    ("possible lossy conversion",
     "Estás metiendo un valor más grande en un tipo más pequeño: usa `double` o un cast explícito."),
    ("missing return statement",
     "A la función le falta un `return` en algún camino (todo `if` necesita su salida)."),
    ("class, interface, enum, or record expected",
     "Sobra o falta una llave: el compilador esperaba el final de un bloque."),
    ("class, interface, or enum expected",
     "Sobra o falta una llave: el compilador esperaba el final de un bloque."),
    ("unclosed string literal", "Un texto se quedó sin la comilla doble de cierre."),
    ("illegal start of expression",
     "Hay un símbolo donde no toca: casi siempre una llave o un paréntesis mal puesto."),
    ("method does not override",
     "La firma no coincide con la del padre: revisa el nombre, los parámetros y el tipo de retorno."),
    ("non-static", "Estás usando algo de instancia desde `main` (que es `static`): crea el objeto con `new`."),
    ("cannot find symbol - class", "Esa clase no está importada o el nombre está mal escrito."),
    ("nullpointer", "Algo vale `null`: comprueba que el objeto esté creado antes de usarlo."),
    ("does not exist", "Ese paquete no está en el classpath: revisa el `import`."),
    ("array required", "Para sacar un valor de un array/lista usa corchetes o `get()`."),
    ("else without if", "Hay un `else` que no tiene su `if` justo antes."),
)


def _sugerencia_javac(mensaje):
    """Qué hacer con un mensaje de javac, en palabras del profesor."""
    texto = str(mensaje or "").lower()
    for trozo, sugerencia in SUGERENCIAS_JAVAC:
        if trozo in texto:
            return sugerencia
    return "Lee el mensaje: javac suele decir exactamente qué esperaba y dónde."


def _errores_de_javac(salida):
    """Convierte la salida de javac en fallos con línea y columna.

    javac escribe el diagnóstico así::

        Main.java:4: error: ';' expected
                int x = 5
                         ^

    La línea del ``^`` dice la columna exacta, así que se aprovecha cuando está.
    """
    errores = []
    lineas = str(salida or "").replace("\r\n", "\n").split("\n")
    for numero, linea in enumerate(lineas):
        coincidencia = RE_ERROR_JAVAC.match(linea.strip())
        if not coincidencia:
            continue
        mensaje = coincidencia.group("mensaje").strip()
        columna = 0
        if numero + 2 < len(lineas) and "^" in lineas[numero + 2]:
            columna = lineas[numero + 2].index("^") + 1
        gravedad = "error" if coincidencia.group("tipo") == "error" else "aviso"
        errores.append(_error(int(coincidencia.group("linea")), columna, "javac",
                              mensaje, _sugerencia_javac(mensaje), gravedad))
    return errores


def _nombre_de_clase(codigo):
    """Nombre de la clase pública (o de la primera que haya); ``Main`` si no hay."""
    texto = str(codigo or "")
    patrones = (
        r"\bpublic\s+(?:final\s+|abstract\s+|sealed\s+)?"
        r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)",
        r"\b(?:final\s+|abstract\s+|sealed\s+)?"
        r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)",
    )
    for patron in patrones:
        coincidencia = re.search(patron, texto)
        if coincidencia:
            return coincidencia.group(1)
    return "Main"


def _paquete_de(codigo):
    """Paquete declarado (para crear las carpetas que javac espera)."""
    coincidencia = re.search(r"^\s*package\s+([\w.]+)\s*;", str(codigo or ""), re.M)
    return coincidencia.group(1) if coincidencia else ""


# ---------------------------------------------------------------------------
# Las bases: el temario, escrito aquí y sin necesidad de IA
# ---------------------------------------------------------------------------
BASES = [
    {
        "clave": "primer_programa",
        "icono": "🚀",
        "titulo": "Tu primer programa",
        "nivel": "Principiante",
        "alias": ("primer programa", "hola mundo", "hola", "main", "estructura",
                  "println", "empezar", "empezar de cero"),
        "resumen": "Un programa Java vive dentro de una clase y arranca por el método `main`. "
                   "Con eso y `System.out.println` ya se puede saludar al mundo.",
        "conceptos": [
            "**La clase**: todo el código va dentro de una clase. El nombre del archivo "
            "tiene que ser igual al de la clase pública: `public class Main` va en `Main.java`.",
            "**El método `main`**: es la puerta de entrada. `java` busca exactamente "
            "`public static void main(String[] args)` y empieza ahí. Si cambias una palabra, "
            "el programa compila pero no arranca.",
            "**Las llaves `{ }`**: abren y cierran bloques (la clase, el método, un `if`, un bucle). "
            "Cada `{` necesita su `}`.",
            "**El punto y coma `;`**: marca el final de cada instrucción. Las líneas que abren "
            "bloque (`class ... {`) no lo llevan.",
            "**`System.out.println(...)`**: escribe en la consola y baja de línea. "
            "`print(...)` escribe sin bajar.",
        ],
        "sintaxis": 'public class Main {\n'
                    '    public static void main(String[] args) {\n'
                    '        System.out.println("Hola, mundo");\n'
                    '    }\n'
                    '}',
        "ejemplo": 'public class Main {\n'
                   '    public static void main(String[] args) {\n'
                   '        // Esto es un comentario: Java lo ignora.\n'
                   '        System.out.println("Hola, mundo");\n'
                   '        System.out.println("Estoy aprendiendo Java");\n'
                   '    }\n'
                   '}',
        "errores": [
            "`System.out.printline` no existe: es `println` (print + line).",
            "Escribir `system` o `string` en minúscula: las clases van con mayúscula.",
            "Olvidar el `;` al final de `println`.",
            "Llamar al archivo `Main.java` pero declarar `public class Hola`: tienen que coincidir.",
        ],
        "ejercicio": "Escribe un programa que imprima tu nombre, tu ciudad y el año, cada cosa "
                     "en su línea. Después cambia un `println` por `print` y mira la diferencia.",
        "url": "https://dev.java/learn/getting-started/",
    },
    {
        "clave": "variables",
        "icono": "📦",
        "titulo": "Variables y tipos",
        "nivel": "Principiante",
        "alias": ("variable", "variables", "tipos", "tipo de dato", "int", "double",
                  "string", "boolean", "constante", "final", "camelcase"),
        "resumen": "Una variable es una caja con nombre y tipo. Java es de tipos fijos: "
                   "la caja solo guarda lo que dice su etiqueta.",
        "conceptos": [
            "**Primitivos**: `int` (enteros), `double` (decimales), `boolean` (`true`/`false`), "
            "`char` (un carácter entre comillas simples), `long`, `float`.",
            "**`String`** no es un primitivo: es una clase, y va con comillas dobles. "
            "Se escribe con mayúscula.",
            "**Declarar y dar valor**: `int edad = 30;` (se puede separar en dos pasos: "
            "`int edad;` y luego `edad = 30;`).",
            "**`final`** convierte la variable en constante: no se puede volver a asignar. "
            "Por convenio se escribe en MAYÚSCULAS: `final double IVA = 0.21;`.",
            "**Nombres**: `camelCase` para variables y métodos (`nombreCompleto`), "
            "`PascalCase` para clases (`CuentaBancaria`). Sin acentos ni espacios.",
            "**`var`** deja que Java deduzca el tipo: `var nombre = \"Ana\";`. Solo desde Java 10 "
            "y solo cuando el valor se ve a la derecha.",
        ],
        "sintaxis": 'tipo nombre = valor;\n'
                    'final tipo CONSTANTE = valor;',
        "ejemplo": 'int edad = 30;\n'
                   'double precio = 19.99;\n'
                   'boolean activo = true;\n'
                   'char inicial = \'A\';\n'
                   'String nombre = "Ana";\n'
                   'final int DIAS_SEMANA = 7;\n'
                   '\n'
                   'System.out.println(nombre + " tiene " + edad + " años");\n'
                   'System.out.println("Precio: " + precio);',
        "errores": [
            "Guardar un decimal en un `int`: `int precio = 19.99;` no compila.",
            "`String` con comillas simples (`'Ana'`) o `char` con dobles (`\"A\"`).",
            "Usar una variable local sin darle valor: Java no la inicializa por ti.",
            "Reasignar una constante `final`.",
        ],
        "ejercicio": "Crea variables para tu nombre, tu edad y tu altura, y muestra una frase "
                     "con las tres. Añade una constante `final` con el año actual.",
        "url": "https://dev.java/learn/language-basics/",
    },
    {
        "clave": "operadores",
        "icono": "➗",
        "titulo": "Operadores y cuentas",
        "nivel": "Principiante",
        "alias": ("operador", "operadores", "aritmetica", "suma", "resta", "modulo",
                  "division", "incremento", "precedencia"),
        "resumen": "Sumar, comparar y combinar condiciones. Dos trampas al empezar: "
                   "la división entera y el `+`, que también pega textos.",
        "conceptos": [
            "**Aritméticos**: `+ - * / %`. `%` es el resto: `7 % 2` da `1`. Sirve para saber "
            "si un número es par (`n % 2 == 0`).",
            "**División entera**: si los dos lados son `int`, el resultado es `int`: `7 / 2` da `3`. "
            "Para que dé `3.5`, al menos uno tiene que ser `double`: `7 / 2.0`.",
            "**Comparación**: `== != < > <= >=`. Devuelven `boolean`.",
            "**Lógicos**: `&&` (y), `||` (o), `!` (no). `&&` y `||` se saltan la segunda parte "
            "si ya saben la respuesta (cortocircuito).",
            "**Asignación compuesta**: `x += 5`, `x -= 2`, `x *= 3`, `x++`, `x--`.",
            "**El `+` con textos concatena**: `\"Total: \" + 5` da `Total: 5`. Ojo con el orden: "
            "`1 + 2 + \"3\"` da `33`, y `\"3\" + 1 + 2` da `312`.",
        ],
        "sintaxis": 'int suma = a + b;\n'
                    'boolean mayor = edad >= 18;\n'
                    'boolean puede = mayor && activo;',
        "ejemplo": 'int a = 7;\n'
                   'int b = 2;\n'
                   '\n'
                   'System.out.println(a / b);      // 3  (división entera)\n'
                   'System.out.println(a / 2.0);    // 3.5\n'
                   'System.out.println(a % b);      // 1  (el resto)\n'
                   '\n'
                   'boolean par = a % 2 == 0;\n'
                   'System.out.println("¿Es par? " + par);',
        "errores": [
            "Comparar textos con `==`: se compara el objeto, no el contenido. Usa `equals`.",
            "Poner `=` donde iba `==` dentro de un `if`.",
            "Esperar decimales de una división entre enteros.",
            "`x++` dentro de una expresión más grande: primero usa el valor y luego suma, "
            "y es fácil liarse. Sácalo aparte.",
        ],
        "ejercicio": "Pide dos números enteros en variables y muestra su suma, resta, producto, "
                     "división con decimales y resto. Después di si el primero es par.",
        "url": "https://dev.java/learn/language-basics/operators/",
    },
    {
        "clave": "condicionales",
        "icono": "🔀",
        "titulo": "Condiciones: if, else y switch",
        "nivel": "Principiante",
        "alias": ("if", "else", "condicional", "condiciones", "switch", "case",
                  "ternario", "tomar decisiones"),
        "resumen": "Con `if` el programa elige un camino. `switch` es lo mismo, pero para "
                   "comparar un valor contra varias opciones fijas.",
        "conceptos": [
            "**`if`** lleva la condición entre paréntesis y el cuerpo entre llaves. "
            "La condición tiene que ser `boolean`: en Java `if (1)` no compila.",
            "**`else if`** encadena comprobaciones: se ejecuta la primera que sea verdadera.",
            "**`switch`** compara un valor con varios `case`. Cada `case` termina en `:` y, "
            "si no quieres seguir al siguiente, en `break;`.",
            "**`switch` moderno**: `case 1 -> ...;` (flecha) no necesita `break` y no se cuela al "
            "siguiente caso. Desde Java 14.",
            "**Operador ternario**: `condición ? valorSiSí : valorSiNo`. Útil para una asignación "
            "corta, no para esconder lógica.",
            "**Anidar con cabeza**: si tienes tres `if` dentro de otro `if`, probablemente "
            "convenga separarlo en un método.",
        ],
        "sintaxis": 'if (condición) {\n    // ...\n} else if (otra) {\n    // ...\n} else {\n    // ...\n}',
        "ejemplo": 'int nota = 7;\n'
                   '\n'
                   'if (nota >= 9) {\n'
                   '    System.out.println("Sobresaliente");\n'
                   '} else if (nota >= 7) {\n'
                   '    System.out.println("Notable");\n'
                   '} else if (nota >= 5) {\n'
                   '    System.out.println("Aprobado");\n'
                   '} else {\n'
                   '    System.out.println("Suspenso");\n'
                   '}\n'
                   '\n'
                   'String estado = nota >= 5 ? "aprobado" : "suspenso";',
        "errores": [
            "Olvidar las llaves y creer que entran varias líneas en el `if`.",
            "Poner `if (nota = 5)`: eso asigna, no compara.",
            "Encadenar `if` sin `else`: se ejecutan varios a la vez.",
            "Olvidar el `break` en un `switch` clásico: se ejecutan los casos siguientes.",
        ],
        "ejercicio": "Pide la edad y di si es menor, adulto o jubilado (65+). "
                     "Resuélvelo primero con `if/else` y luego con `switch` usando rangos.",
        "url": "https://dev.java/learn/language-basics/",
    },
    {
        "clave": "bucles",
        "icono": "🔁",
        "titulo": "Bucles: repetir sin copiar",
        "nivel": "Principiante",
        "alias": ("bucle", "bucles", "for", "while", "do while", "for each",
                  "repetir", "iterar", "break", "continue"),
        "resumen": "`for` cuando sabes cuántas veces, `while` cuando no, `do-while` cuando "
                   "tiene que pasar al menos una vez. Todos pueden acabar en bucle infinito.",
        "conceptos": [
            "**`for (inicio; condición; paso)`**: el clásico para contar. "
            "`for (int i = 0; i < 10; i++)` va de 0 a 9.",
            "**Los índices empiezan en 0**: un array de 5 posiciones llega hasta la 4. "
            "Pasarse da `ArrayIndexOutOfBoundsException`.",
            "**`while (condición)`**: repite mientras se cumpla. Si la condición nunca se hace "
            "falsa, el programa se cuelga.",
            "**`do { } while (condición);`**: ejecuta el cuerpo una vez y luego decide. "
            "Fíjate en el `;` del final.",
            "**`for-each`**: `for (String nombre : nombres)` recorre todos los elementos sin "
            "tocar índices. No sirve para cambiar el array ni para ir al revés.",
            "**`break`** sale del bucle; **`continue`** salta a la siguiente vuelta. "
            "Con moderación: a veces se lee mejor cambiando la condición.",
        ],
        "sintaxis": 'for (int i = 0; i < n; i++) {\n    // ...\n}\n\n'
                    'while (condición) {\n    // ...\n}\n\n'
                    'do {\n    // ...\n} while (condición);',
        "ejemplo": '// Del 1 al 5 con for\n'
                   'for (int i = 1; i <= 5; i++) {\n'
                   '    System.out.println("Vuelta " + i);\n'
                   '}\n'
                   '\n'
                   '// Sumar hasta pasar de 10 con while\n'
                   'int suma = 0;\n'
                   'int numero = 1;\n'
                   'while (suma <= 10) {\n'
                   '    suma += numero;\n'
                   '    numero++;\n'
                   '}\n'
                   'System.out.println("Suma: " + suma);',
        "errores": [
            "Bucle infinito por olvidar el `i++` o porque la condición nunca cambia.",
            "Empezar en 1 y comparar con `<=` en un array: te sales por el final.",
            "Modificar la variable del `for` dentro del cuerpo y perder la cuenta.",
            "Usar `==` para comparar textos dentro de la condición del bucle.",
        ],
        "ejercicio": "Muestra la tabla de multiplicar del 7 (del 1 al 10) con un `for`. "
                     "Después pide un número y cuenta cuántas vueltas hacen falta para que la suma "
                     "de 1+2+3... lo supere.",
        "url": "https://dev.java/learn/language-basics/",
    },
    {
        "clave": "metodos",
        "icono": "🧰",
        "titulo": "Métodos: dar nombre a un trozo de código",
        "nivel": "Intermedio",
        "alias": ("metodo", "metodos", "funcion", "funciones", "return", "parametros",
                  "static", "sobrecarga", "void"),
        "resumen": "Un método es una instrucción con nombre, para no repetir código y para "
                   "poder probarlo por partes. Recibe datos (parámetros), hace algo y "
                   "devuelve un resultado (o nada, si es `void`).",
        "conceptos": [
            "**La firma**: `modificador tipoRetorno nombre(tipo parametro)`. "
            "`public int sumar(int a, int b)`.",
            "**`return`** devuelve el valor y termina el método. Si el método devuelve algo, "
            "todos los caminos tienen que acabar en `return`.",
            "**`void`** significa «no devuelve nada»: solo hace. Ahí `return;` sirve para salir antes.",
            "**`static`**: un método `static` pertenece a la clase y se llama sin crear objeto "
            "(`Math.max(...)`). `main` es `static`, así que desde ahí no puedes llamar directamente "
            "a un método normal: crea el objeto con `new`.",
            "**Paso por valor**: Java copia el valor al entrar. Cambiar un `int` dentro no afecta "
            "fuera; con objetos se copia la referencia, así que sí se pueden modificar sus campos.",
            "**Sobrecarga**: dos métodos con el mismo nombre y distintos parámetros "
            "(`saludar()` y `saludar(String nombre)`). Java elige por los tipos.",
        ],
        "sintaxis": 'public static int sumar(int a, int b) {\n    return a + b;\n}\n\n'
                    'public static void saludar(String nombre) {\n'
                    '    System.out.println("Hola, " + nombre);\n}',
        "ejemplo": 'public static void main(String[] args) {\n'
                   '    int resultado = sumar(3, 4);\n'
                   '    System.out.println("3 + 4 = " + resultado);\n'
                   '    saludar("Ana");\n'
                   '}\n'
                   '\n'
                   'public static int sumar(int a, int b) {\n'
                   '    return a + b;\n'
                   '}\n'
                   '\n'
                   'public static void saludar(String nombre) {\n'
                   '    System.out.println("Hola, " + nombre);\n'
                   '}',
        "errores": [
            "Declarar que devuelve `int` y no poner ningún `return`.",
            "Llamar a un método de instancia desde `main` sin crear el objeto.",
            "Cambiar un parámetro y esperar que el cambio se vea fuera del método.",
            "Confundir el nombre del método con el de la variable que guarda el resultado.",
        ],
        "ejercicio": "Escribe `esPar(int n)` que devuelva `boolean`, `mayor(int a, int b)` que "
                     "devuelva el mayor y `repetir(String texto, int veces)` que lo imprima. "
                     "Úsalos desde `main`.",
        "url": "https://dev.java/learn/methods/",
    },
    {
        "clave": "arrays",
        "icono": "🗂️",
        "titulo": "Arrays: muchos valores del mismo tipo",
        "nivel": "Intermedio",
        "alias": ("array", "arrays", "arreglo", "indice", "length", "matriz"),
        "resumen": "Un array es una caja con varias casillas numeradas del mismo tipo y de "
                   "tamaño fijo. La primera casilla es la 0.",
        "conceptos": [
            "**Crear**: `int[] notas = new int[5];` (cinco casillas a 0) o "
            "`int[] notas = {7, 8, 9};` (con valores).",
            "**Tamaño fijo**: no crece ni se encoge. Para eso están las colecciones "
            "(`ArrayList`).",
            "**`length`** es una propiedad, sin paréntesis: `notas.length`. "
            "En `String` sí es un método: `texto.length()`.",
            "**Recorrer**: con `for` clásico si necesitas el índice, con `for-each` si solo "
            "quieres los valores.",
            "**Imprimir**: `System.out.println(notas)` enseña algo como `[I@1b6d3586`. "
            "Usa `Arrays.toString(notas)`.",
            "**Bidimensional**: `int[][] tablero = new int[3][3];` y se recorre con un `for` "
            "dentro de otro.",
        ],
        "sintaxis": 'tipo[] nombre = new tipo[tamaño];\n'
                    'tipo[] nombre = {valor1, valor2};\n'
                    'nombre[indice]',
        "ejemplo": 'int[] notas = {7, 8, 9, 5};\n'
                   '\n'
                   'System.out.println("Hay " + notas.length + " notas");\n'
                   'System.out.println("La primera es " + notas[0]);\n'
                   '\n'
                   'int suma = 0;\n'
                   'for (int i = 0; i < notas.length; i++) {\n'
                   '    suma += notas[i];\n'
                   '}\n'
                   'double media = (double) suma / notas.length;\n'
                   'System.out.println("Media: " + media);',
        "errores": [
            "Acceder a `notas[notas.length]`: el último índice es `length - 1`.",
            "Poner `notas.length()` en un array (ahí no hay paréntesis).",
            "Comparar arrays con `==`: compara referencias; usa `Arrays.equals(...)`.",
            "Creer que `int[] copia = original;` copia: son el mismo array. "
            "Usa `Arrays.copyOf(original, original.length)`.",
        ],
        "ejercicio": "Guarda 6 temperaturas en un array y muestra la máxima, la mínima y la media. "
                     "Después recórrelo al revés.",
        "url": "https://dev.java/learn/language-basics/arrays/",
    },
    {
        "clave": "clases",
        "icono": "🏛️",
        "titulo": "Clases y objetos",
        "nivel": "Intermedio",
        "alias": ("clase", "clases", "objeto", "objetos", "constructor", "new", "this",
                  "poo", "encapsulacion", "getter", "setter", "tostring"),
        "resumen": "Una clase es el molde; un objeto es cada cosa hecha con ese molde. "
                   "Guardan datos (campos) y saben hacer cosas (métodos).",
        "conceptos": [
            "**La clase** describe campos y métodos. `Persona` es el molde; "
            "`new Persona(\"Ana\", 30)` crea un objeto concreto.",
            "**Constructor**: método con el mismo nombre que la clase y sin tipo de retorno. "
            "Sirve para dejar el objeto listo al nacer.",
            "**`this`** se refiere al objeto actual: `this.nombre = nombre;` distingue el campo "
            "del parámetro.",
            "**Encapsulación**: los campos van `private` y se accede con métodos públicos "
            "(getters y setters) que pueden validar.",
            "**`toString()`** devuelve el texto que se ve al imprimir el objeto. Sin él sale "
            "`Persona@1b6d3586`. Lleva `@Override`.",
            "**`static`** es de la clase (uno para todos); lo normal es que sea de cada objeto.",
        ],
        "sintaxis": 'public class Persona {\n'
                    '    private String nombre;\n'
                    '    private int edad;\n'
                    '\n'
                    '    public Persona(String nombre, int edad) {\n'
                    '        this.nombre = nombre;\n'
                    '        this.edad = edad;\n'
                    '    }\n'
                    '\n'
                    '    public String getNombre() {\n'
                    '        return nombre;\n'
                    '    }\n'
                    '\n'
                    '    @Override\n'
                    '    public String toString() {\n'
                    '        return nombre + " (" + edad + ")";\n'
                    '    }\n'
                    '}',
        "ejemplo": 'Persona ana = new Persona("Ana", 30);\n'
                   'Persona luis = new Persona("Luis", 25);\n'
                   '\n'
                   'System.out.println(ana);        // Ana (30)\n'
                   'System.out.println(luis);       // Luis (25)\n'
                   'System.out.println(ana.getNombre());',
        "errores": [
            "Llamar a `new` sin paréntesis: `new Persona;` no existe.",
            "Poner tipo de retorno al constructor (`public void Persona(...)`), que lo convierte "
            "en un método normal y deja el objeto sin inicializar.",
            "Acceder a un campo `private` desde fuera de la clase.",
            "Olvidar `this` y asignar el parámetro a sí mismo: `nombre = nombre;`.",
        ],
        "ejercicio": "Crea una clase `Libro` con título, autor y páginas, su constructor, "
                     "los getters y un `toString()`. Crea tres libros y muéstralos.",
        "url": "https://dev.java/learn/classes-objects/",
    },
    {
        "clave": "herencia",
        "icono": "🧬",
        "titulo": "Herencia e interfaces",
        "nivel": "Avanzado",
        "alias": ("herencia", "extends", "super", "override", "polimorfismo", "interfaz",
                  "interfaces", "abstract", "implements"),
        "resumen": "Una clase puede heredar de otra (`extends`) y reutilizar sus campos y métodos; "
                   "una interfaz (`implements`) define un contrato que hay que cumplir.",
        "conceptos": [
            "**`extends`**: `class Perro extends Animal` hereda todo lo público y protegido "
            "de `Animal`.",
            "**`super(...)`** llama al constructor del padre y tiene que ser la primera línea del "
            "constructor hijo.",
            "**`@Override`** avisa al compilador de que estás redefiniendo un método del padre: si te "
            "equivocas en la firma, te lo dice.",
            "**Polimorfismo**: una variable del padre puede guardar un hijo "
            "(`Animal a = new Perro();`) y al llamar a un método se ejecuta el del hijo.",
            "**`abstract`**: una clase o método sin cuerpo, que obliga a las hijas a completarlo. "
            "No se puede hacer `new` de una clase abstracta.",
            "**Interfaz**: declara métodos (y constantes) y una clase puede implementar varias. "
            "Es la forma de decir «esto sabe hacer X» sin atarse a un padre.",
        ],
        "sintaxis": 'class Animal {\n'
                    '    protected String nombre;\n\n'
                    '    public Animal(String nombre) {\n'
                    '        this.nombre = nombre;\n'
                    '    }\n\n'
                    '    public String sonido() {\n'
                    '        return "...";\n'
                    '    }\n'
                    '}\n\n'
                    'class Perro extends Animal {\n'
                    '    public Perro(String nombre) {\n'
                    '        super(nombre);\n'
                    '    }\n\n'
                    '    @Override\n'
                    '    public String sonido() {\n'
                    '        return "Guau";\n'
                    '    }\n'
                    '}',
        "ejemplo": 'Animal animal = new Perro("Toby");\n'
                   'System.out.println(animal.sonido());   // Guau (el del hijo)\n'
                   '\n'
                   'Animal otro = new Animal("Genérico");\n'
                   'System.out.println(otro.sonido());     // ... (el del padre)',
        "errores": [
            "Olvidar `super(...)` cuando el padre no tiene constructor vacío.",
            "Intentar heredar de dos clases: en Java solo hay una herencia de clase "
            "(se suple con interfaces).",
            "Marcar `@Override` y cambiar un parámetro: ya no es el mismo método.",
            "Hacer `new` de una clase `abstract`.",
        ],
        "ejercicio": "Haz una clase `Animal` con `sonido()` y dos hijas (`Perro`, `Gato`) que lo "
                     "redefinan. Mete varios animales en un array de `Animal` y recórrelo llamando "
                     "a `sonido()`.",
        "url": "https://dev.java/learn/inheritance/",
    },
    {
        "clave": "colecciones",
        "icono": "📚",
        "titulo": "Colecciones: ArrayList, HashMap y compañía",
        "nivel": "Intermedio",
        "alias": ("coleccion", "colecciones", "arraylist", "hashmap", "hashset", "list",
                  "map", "set", "genericos", "lista dinamica"),
        "resumen": "Cuando no sabes cuántos elementos habrá, usa una colección: crece sola, "
                   "tiene métodos útiles y guarda objetos (no primitivos: sus envoltorios).",
        "conceptos": [
            "**`ArrayList<T>`**: lista ordenada que crece. `add`, `get`, `set`, `remove`, "
            "`size`, `contains`.",
            "**`size()`** es con paréntesis (a diferencia de `array.length`). "
            "El último índice es `size() - 1`.",
            "**`HashMap<K, V>`**: pares clave→valor. `put`, `get`, `containsKey`, `remove`, "
            "`keySet`, `values`. El orden no está garantizado.",
            "**`HashSet<T>`**: conjunto sin repetidos y sin orden. Ideal para saber si algo ya "
            "estaba.",
            "**Genéricos**: `ArrayList<String>` dice qué guarda. Sin eso (`ArrayList` a secas) "
            "hay que hacer cast y se pierde el aviso del compilador.",
            "**Envoltorios**: `ArrayList<Integer>`, no `ArrayList<int>`. Java convierte solo "
            "(`autoboxing`) al añadir y sacar.",
            "**Recorrer**: `for (String nombre : nombres)` funciona con todas. No borres "
            "elementos dentro del `for-each`: usa `removeIf` o un `Iterator`.",
        ],
        "sintaxis": 'import java.util.ArrayList;\nimport java.util.HashMap;\n\n'
                    'ArrayList<String> nombres = new ArrayList<>();\n'
                    'nombres.add("Ana");\n'
                    'nombres.get(0);\n'
                    'nombres.size();\n\n'
                    'HashMap<String, Integer> edades = new HashMap<>();\n'
                    'edades.put("Ana", 30);\n'
                    'edades.get("Ana");',
        "ejemplo": 'ArrayList<String> tareas = new ArrayList<>();\n'
                   'tareas.add("Estudiar Java");\n'
                   'tareas.add("Hacer ejercicio");\n'
                   '\n'
                   'for (String tarea : tareas) {\n'
                   '    System.out.println("- " + tarea);\n'
                   '}\n'
                   '\n'
                   'System.out.println("Total: " + tareas.size());',
        "errores": [
            "Usar `lista.length` o `lista.size` sin paréntesis.",
            "`ArrayList<int>`: los genéricos no admiten primitivos.",
            "`remove(3)` cuando querías borrar el texto `\"3\"`: con un `int` borra por índice.",
            "Recorrer un `HashMap` por índice: no tiene índices, se recorre por claves o valores.",
        ],
        "ejercicio": "Haz una lista de la compra con `ArrayList`: añade, muestra, borra uno y "
                     "di cuántos quedan. Después guarda precios en un `HashMap<String, Double>` "
                     "y calcula el total.",
        "url": "https://dev.java/learn/api/collections-framework/",
    },
    {
        "clave": "excepciones",
        "icono": "🛟",
        "titulo": "Excepciones: qué hacer cuando algo falla",
        "nivel": "Intermedio",
        "alias": ("excepcion", "excepciones", "try", "catch", "finally", "throw", "throws",
                  "error en ejecucion", "nullpointerexception"),
        "resumen": "Una excepción es un fallo en tiempo de ejecución. Se puede atrapar "
                   "(`try/catch`), dejar que suba (`throws`) o lanzar la tuya (`throw`).",
        "conceptos": [
            "**`try { } catch (Tipo e) { }`**: intenta el código y, si falla con ese tipo, "
            "ejecuta el `catch` en vez de romper el programa.",
            "**`finally`** se ejecuta siempre (haya fallado o no): ahí se cierra un archivo o "
            "una conexión.",
            "**`throw new IllegalArgumentException(\"mensaje\")`** lanza un fallo a propósito.",
            "**`throws`** en la firma avisa de que ese método puede lanzar una excepción "
            "comprobada (por ejemplo, al leer un archivo).",
            "**Comprobadas y no comprobadas**: `IOException` obliga a `try/catch` o `throws`; "
            "`NullPointerException` o `ArrayIndexOutOfBoundsException` no.",
            "**`e.getMessage()`** da el texto del fallo y `e.printStackTrace()` la traza "
            "completa. Un `catch` vacío esconde el problema: mejor explicar o relanzar.",
        ],
        "sintaxis": 'try {\n    // código que puede fallar\n} catch (NumberFormatException e) {\n'
                    '    System.out.println("No es un número: " + e.getMessage());\n'
                    '} finally {\n    // se ejecuta siempre\n}',
        "ejemplo": 'String texto = "abc";\n'
                   '\n'
                   'try {\n'
                   '    int numero = Integer.parseInt(texto);\n'
                   '    System.out.println("Número: " + numero);\n'
                   '} catch (NumberFormatException e) {\n'
                   '    System.out.println("Eso no era un número");\n'
                   '}',
        "errores": [
            "Atrapar `Exception` para todo y no hacer nada: el fallo desaparece sin explicación.",
            "Poner código después del punto donde ya se ha lanzado la excepción (no se ejecuta).",
            "Confundir `throw` (lanzar) con `throws` (avisar en la firma).",
            "No comprobar `null` antes de usar un objeto: `NullPointerException`.",
        ],
        "ejercicio": "Pide un número por teclado y conviértelo con `Integer.parseInt` dentro de un "
                     "`try/catch`. Si no es número, muestra un aviso y vuelve a pedirlo.",
        "url": "https://dev.java/learn/exceptions/",
    },
    {
        "clave": "entrada",
        "icono": "⌨️",
        "titulo": "Leer por teclado con Scanner",
        "nivel": "Intermedio",
        "alias": ("scanner", "leer", "entrada", "teclado", "nextline", "nextint",
                  "pedir datos", "consola"),
        "resumen": "`Scanner` lee lo que el usuario escribe. Tiene una trampa clásica: "
                   "`nextInt()` deja el salto de línea y el siguiente `nextLine()` lo lee vacío.",
        "conceptos": [
            "**Crear**: `Scanner sc = new Scanner(System.in);` con `import java.util.Scanner;`.",
            "**Leer**: `nextLine()` (una línea entera), `nextInt()`, `nextDouble()`, "
            "`next()` (una palabra), `hasNextInt()` (comprobar antes de leer).",
            "**La trampa**: `nextInt()` no consume el `Enter`. Si después usas `nextLine()`, "
            "te devuelve `\"\"`. Solución: añade un `sc.nextLine();` de limpieza.",
            "**Cerrar**: `sc.close()` al terminar (o `try-with-resources`). Cerrar `System.in` "
            "impide volver a leer en el resto del programa.",
            "**Alternativas**: `BufferedReader` + `InputStreamReader` (más rápido), "
            "`JOptionPane` (ventana), argumentos de `main` (`args`).",
            "**Convertir**: si lees texto y quieres número, `Integer.parseInt(texto)` o "
            "`Double.parseDouble(texto)`.",
        ],
        "sintaxis": 'import java.util.Scanner;\n\n'
                    'Scanner sc = new Scanner(System.in);\n'
                    'System.out.print("Tu nombre: ");\n'
                    'String nombre = sc.nextLine();\n'
                    'System.out.print("Tu edad: ");\n'
                    'int edad = sc.nextInt();',
        "ejemplo": 'Scanner sc = new Scanner(System.in);\n'
                   '\n'
                   'System.out.print("¿Cómo te llamas? ");\n'
                   'String nombre = sc.nextLine();\n'
                   '\n'
                   'System.out.print("¿Cuántos años tienes? ");\n'
                   'int edad = sc.nextInt();\n'
                   '\n'
                   'System.out.println("Hola, " + nombre + ". Tienes " + edad + ".");',
        "errores": [
            "Olvidar `import java.util.Scanner;`.",
            "Mezclar `nextInt()` y `nextLine()` sin limpiar el salto de línea.",
            "Leer con `next()` y quedarse con la primera palabra de un nombre compuesto.",
            "No controlar que el usuario escriba letras donde pediste un número: "
            "`InputMismatchException`.",
        ],
        "ejercicio": "Pide nombre y edad con `Scanner` y saluda. Después pide una ciudad "
                     "con `nextLine()` justo detrás del `nextInt()` y arregla el salto de línea.",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html",
    },
    {
        "clave": "depuracion",
        "icono": "🩺",
        "titulo": "Leer los errores de Java",
        "nivel": "Principiante",
        "alias": ("error", "errores", "depurar", "depuracion", "javac", "excepcion",
                  "no compila", "cannot find symbol", "stacktrace"),
        "resumen": "Un mensaje de Java asusta por el tamaño, pero siempre dice lo mismo: "
                   "archivo, línea, qué pasó y, muchas veces, qué esperaba.",
        "conceptos": [
            "**Error de compilación**: el programa ni arranca. `Main.java:7: error: ';' expected` "
            "se lee: archivo `Main.java`, línea 7, falta un punto y coma.",
            "**`cannot find symbol`**: un nombre que Java no conoce. Casi siempre es un "
            "`import` que falta, una variable mal escrita o una declarada en otro bloque.",
            "**`incompatible types`**: estás mezclando tipos (texto con número, decimal con entero).",
            "**`reached end of file while parsing`**: falta una llave `}`.",
            "**`NullPointerException`**: usaste algo que vale `null`. La traza dice el archivo y la "
            "línea exacta: se lee de arriba abajo hasta la primera línea tuya.",
            "**`Exception in thread \"main\"`**: el programa sí compiló, pero falló mientras "
            "corría. Distinto de un error de compilación.",
            "**La línea de la traza manda**: si dice `at Main.main(Main.java:12)`, el problema "
            "está en la línea 12 de `Main.java`.",
        ],
        "sintaxis": 'Main.java:4: error: \';\' expected\n'
                    '        int x = 5\n'
                    '                 ^\n'
                    '1 error',
        "ejemplo": 'int[] numeros = {1, 2, 3};\n'
                   'System.out.println(numeros[3]);\n'
                   '\n'
                   '// Exception in thread "main" java.lang.ArrayIndexOutOfBoundsException:\n'
                   '//   Index 3 out of bounds for length 3\n'
                   '//   at Main.main(Main.java:2)   <- el fallo está AQUÍ',
        "errores": [
            "Leer solo la primera línea y no bajar a la línea del `^`.",
            "Arreglar el primer error y no volver a compilar: a veces los demás eran consecuencia.",
            "Ignorar los avisos (`warning`): no rompen, pero suelen señalar un descuido.",
            "Cambiar cosas al azar sin leer qué esperaba el compilador.",
        ],
        "ejercicio": "Rompe a propósito un programa de tres formas (quitar un `;`, cerrar mal una "
                     "llave, usar una variable sin declarar), compílalo y apunta qué dice cada "
                     "mensaje antes de arreglarlo.",
        "url": "https://dev.java/learn/",
    },
]

# ---------------------------------------------------------------------------
# La documentación de consulta: lo que más se busca al empezar (sin IA)
# ---------------------------------------------------------------------------
DOCUMENTACION = [
    {
        "clave": "string",
        "icono": "🔤",
        "titulo": "String",
        "tipo": "Clase (java.lang, no hace falta importar)",
        "alias": ("string", "texto", "cadenas", "cadena", "charat", "substring",
                  "equals", "tolowercase", "trim", "split"),
        "resumen": "El texto. Es **inmutable**: cada método devuelve un texto nuevo y el "
                   "original no cambia nunca.",
        "firmas": [
            "`length()` → número de caracteres (con paréntesis, al revés que `array.length`).",
            "`charAt(int i)` → el carácter de la posición `i` (de 0 a `length() - 1`).",
            "`substring(int inicio)` / `substring(int inicio, int fin)` → trozo; `fin` no entra.",
            "`equals(Object otro)` → si el contenido es igual (para comparar, nunca `==`).",
            "`equalsIgnoreCase(String otro)` → igual sin mirar mayúsculas.",
            "`toUpperCase()` / `toLowerCase()` → copia en mayúsculas o minúsculas.",
            "`trim()` → quita espacios del principio y del final (`strip()` es lo moderno).",
            "`contains(CharSequence)` / `startsWith` / `endsWith` → buscar dentro.",
            "`indexOf(String)` → posición de la primera aparición, `-1` si no está.",
            "`replace(String viejo, String nuevo)` → cambia todas las apariciones.",
            "`split(String regex)` → array de trozos; `String.join(\"-\", lista)` lo deshace.",
            "`isEmpty()` / `isBlank()` → vacío (`\"\"`) / vacío o solo espacios.",
            "`repeat(int n)` (Java 11) → el texto repetido `n` veces.",
            "`Integer.parseInt(texto)` / `String.valueOf(numero)` → texto ↔ número.",
        ],
        "ejemplo": 'String nombre = "  Ana López  ";\n'
                   'String limpio = nombre.trim();\n'
                   '\n'
                   'System.out.println(limpio.length());           // 9\n'
                   'System.out.println(limpio.charAt(0));          // A\n'
                   'System.out.println(limpio.substring(0, 3));    // Ana\n'
                   'System.out.println(limpio.toUpperCase());      // ANA LÓPEZ\n'
                   'System.out.println(limpio.contains("López"));  // true\n'
                   'System.out.println(nombre.equals("Ana López")); // false (espacios)',
        "trampas": [
            "`==` compara referencias: usa `equals`.",
            "`nombre.length` sin paréntesis no compila.",
            "`substring(0, 3)` devuelve 3 caracteres (0, 1 y 2); el 3 no entra.",
            "`charAt(length())` se pasa un puesto: el último es `length() - 1`.",
            "`.trim()` no arregla los espacios del medio.",
            "Los textos son inmutables: `texto.toUpperCase();` sin asignar no hace nada.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html",
    },
    {
        "clave": "arraylist",
        "icono": "📋",
        "titulo": "ArrayList",
        "tipo": "Clase (java.util) — necesita `import java.util.ArrayList;`",
        "alias": ("arraylist", "lista", "list", "coleccion", "add", "get", "size",
                  "remove", "lista dinamica"),
        "resumen": "Una lista que crece y se encoge sola. Mantiene el orden y admite repetidos. "
                   "Es la primera colección que conviene aprender.",
        "firmas": [
            "`new ArrayList<>()` → vacía (el tipo va en la variable: `ArrayList<String>`).",
            "`add(T elemento)` → añade al final; `add(int i, T elemento)` en una posición.",
            "`get(int i)` → el elemento en `i` (de 0 a `size() - 1`).",
            "`set(int i, T elemento)` → reemplaza y devuelve el anterior.",
            "`remove(int i)` / `remove(Object o)` → borra por índice o por valor.",
            "`size()` → cuántos hay (`isEmpty()` si solo quieres preguntarlo).",
            "`contains(Object o)` / `indexOf(Object o)` → si está / dónde está.",
            "`Collections.sort(lista)` / `lista.sort(...)` → ordenar.",
            "`for (T elemento : lista)` → recorrerla entera.",
        ],
        "ejemplo": 'ArrayList<String> tareas = new ArrayList<>();\n'
                   'tareas.add("Estudiar");\n'
                   'tareas.add("Practicar");\n'
                   '\n'
                   'System.out.println(tareas.size());      // 2\n'
                   'System.out.println(tareas.get(0));      // Estudiar\n'
                   'System.out.println(tareas.contains("Practicar")); // true\n'
                   '\n'
                   'tareas.remove("Estudiar");\n'
                   'System.out.println(tareas);             // [Practicar]',
        "trampas": [
            "`size` sin paréntesis no compila (no es `length`).",
            "`ArrayList<int>` no existe: usa `ArrayList<Integer>`.",
            "`remove(1)` borra por índice; para borrar el número 1 sería `remove(Integer.valueOf(1))`.",
            "Imprimirla da `[a, b]` directamente: no hace falta `Arrays.toString`.",
            "No se puede modificar mientras se recorre con `for-each`: usa `removeIf` o un `Iterator`.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html",
    },
    {
        "clave": "hashmap",
        "icono": "🗺️",
        "titulo": "HashMap",
        "tipo": "Clase (java.util) — necesita `import java.util.HashMap;`",
        "alias": ("hashmap", "map", "diccionario", "clave valor", "put", "get", "mapa"),
        "resumen": "Pares clave → valor, como un diccionario. Se busca por la clave (muy rápido) "
                   "y no hay orden ni índices.",
        "firmas": [
            "`new HashMap<K, V>()` → vacío (`HashMap<String, Integer>`).",
            "`put(K clave, V valor)` → guarda o reemplaza; devuelve el valor anterior o `null`.",
            "`get(K clave)` → el valor, o `null` si la clave no está.",
            "`getOrDefault(K clave, V porDefecto)` → el valor o el de por defecto, sin mirar `null`.",
            "`containsKey(K)` / `containsValue(V)` → si existe esa clave / ese valor.",
            "`remove(K clave)` → borra el par (devuelve el valor).",
            "`keySet()` / `values()` / `entrySet()` → claves / valores / pares para recorrer.",
            "`size()` / `isEmpty()` / `clear()` → cuántos, si está vacío, vaciarlo.",
        ],
        "ejemplo": 'HashMap<String, Integer> edades = new HashMap<>();\n'
                   'edades.put("Ana", 30);\n'
                   'edades.put("Luis", 25);\n'
                   'edades.put("Ana", 31);            // reemplaza el valor\n'
                   '\n'
                   'System.out.println(edades.get("Ana"));             // 31\n'
                   'System.out.println(edades.getOrDefault("Eva", 0)); // 0\n'
                   'System.out.println(edades.containsKey("Luis"));    // true\n'
                   '\n'
                   'for (String nombre : edades.keySet()) {\n'
                   '    System.out.println(nombre + ": " + edades.get(nombre));\n'
                   '}',
        "trampas": [
            "`get` de una clave que no existe devuelve `null`: si lo guardas en un `int`, "
            "salta `NullPointerException`. Usa `getOrDefault`.",
            "No tiene índices: `mapa.get(0)` busca la clave `0`, no la primera posición.",
            "El orden al recorrer no es el de inserción: para eso, `LinkedHashMap`.",
            "`HashMap<int, String>` no existe: usa `HashMap<Integer, String>`.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html",
    },
    {
        "clave": "scanner",
        "icono": "⌨️",
        "titulo": "Scanner",
        "tipo": "Clase (java.util) — necesita `import java.util.Scanner;`",
        "alias": ("scanner", "leer teclado", "entrada", "nextint", "nextline", "consola"),
        "resumen": "Lee lo que el usuario escribe por teclado. Se crea una vez y se reutiliza.",
        "firmas": [
            "`new Scanner(System.in)` → lee de la consola.",
            "`nextLine()` → una línea entera (hasta el `Enter`).",
            "`next()` → una sola palabra (corta por el espacio).",
            "`nextInt()` / `nextDouble()` / `nextBoolean()` → tipos concretos.",
            "`hasNextInt()` / `hasNextLine()` → comprobar antes de leer.",
            "`useDelimiter(\",\")` → cambiar el separador.",
            "`close()` → cerrar al terminar.",
        ],
        "ejemplo": 'Scanner sc = new Scanner(System.in);\n'
                   '\n'
                   'System.out.print("Nombre: ");\n'
                   'String nombre = sc.nextLine();\n'
                   '\n'
                   'System.out.print("Edad: ");\n'
                   'int edad = sc.nextInt();\n'
                   'sc.nextLine();                  // limpia el Enter que quedó\n'
                   '\n'
                   'System.out.print("Ciudad: ");\n'
                   'String ciudad = sc.nextLine();\n'
                   'System.out.println(nombre + ", " + edad + ", " + ciudad);',
        "trampas": [
            "`nextInt()` no consume el salto de línea: el siguiente `nextLine()` sale vacío. "
            "Añade un `sc.nextLine();` de limpieza.",
            "Si el usuario escribe letras donde pediste un número: `InputMismatchException`. "
            "Compruébalo con `hasNextInt()`.",
            "`next()` corta en el primer espacio: para nombres completos, `nextLine()`.",
            "Cerrar `System.in` impide volver a leer después en el mismo programa.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html",
    },
    {
        "clave": "math",
        "icono": "🧮",
        "titulo": "Math",
        "tipo": "Clase (java.lang, no hace falta importar)",
        "alias": ("math", "matematicas", "raiz", "potencia", "aleatorio", "random",
                  "redondear", "absoluto"),
        "resumen": "Cuentas de bolsillo: potencia, raíz, valor absoluto, redondeos y números "
                   "al azar. Todo es `static`: se llama `Math.algo(...)` sin crear objeto.",
        "firmas": [
            "`Math.abs(x)` → valor absoluto (sin signo).",
            "`Math.max(a, b)` / `Math.min(a, b)` → el mayor / el menor (admiten dos valores).",
            "`Math.pow(base, exponente)` → potencia, **devuelve `double`**: `Math.pow(2, 10)` → `1024.0`.",
            "`Math.sqrt(x)` → raíz cuadrada (`double`).",
            "`Math.round(x)` → entero más cercano (`long`); `Math.floor` / `Math.ceil` → abajo/arriba.",
            "`Math.random()` → decimal entre 0.0 (incluido) y 1.0 (excluido).",
            "Entero al azar entre `min` y `max`: `min + (int) (Math.random() * (max - min + 1))`.",
            "`Math.PI` y `Math.E` → constantes.",
        ],
        "ejemplo": 'System.out.println(Math.abs(-7));       // 7\n'
                   'System.out.println(Math.max(3, 9));      // 9\n'
                   'System.out.println(Math.pow(2, 10));     // 1024.0\n'
                   'System.out.println(Math.sqrt(81));       // 9.0\n'
                   'System.out.println(Math.round(3.6));     // 4\n'
                   '\n'
                   '// Dado de 1 a 6\n'
                   'int dado = 1 + (int) (Math.random() * 6);\n'
                   'System.out.println("Dado: " + dado);',
        "trampas": [
            "`Math.pow` siempre devuelve `double`: si necesitas `int`, guarda con `(int)`.",
            "`Math.random()` nunca llega a 1.0, pero sí puede dar 0.0.",
            "Para el rango `1..6` hace falta `* 6` y luego `+ 1`, no `* 5`.",
            "Redondear dinero con `Math.round` y luego dividir puede dar un céntimo de menos: "
            "para dinero, `BigDecimal`.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html",
    },
    {
        "clave": "integer",
        "icono": "🔢",
        "titulo": "Integer y las conversiones",
        "tipo": "Clase envoltorio (java.lang)",
        "alias": ("integer", "parseint", "parseo", "convertir", "valueof", "envoltorio",
                  "autoboxing", "double", "parseDouble"),
        "resumen": "Convertir texto en número y número en texto. `Integer` es el envoltorio de "
                   "`int`: es lo que se guarda dentro de un `ArrayList`.",
        "firmas": [
            "`Integer.parseInt(texto)` → `int`. Falla con `NumberFormatException` si no es número.",
            "`Double.parseDouble(texto)` → `double`; también `Long.parseLong`, `Boolean.parseBoolean`.",
            "`String.valueOf(x)` / `Integer.toString(n)` → número a texto.",
            '`Integer.MAX_VALUE` / `Integer.MIN_VALUE` → el techo y el suelo del `int`.',
            'Concatenar con `\"\" + n` también convierte, pero `String.valueOf` dice mejor la intención.',
            "`Integer.valueOf(texto)` → objeto `Integer` (cuidado: `==` entre `Integer` compara "
            "referencias; usa `equals`).",
        ],
        "ejemplo": 'String texto = "42";\n'
                   'int numero = Integer.parseInt(texto);\n'
                   'System.out.println(numero + 8);           // 50\n'
                   '\n'
                   'String deVuelta = String.valueOf(numero);\n'
                   'System.out.println(deVuelta.length());    // 2\n'
                   '\n'
                   'try {\n'
                   '    Integer.parseInt("cuarenta");\n'
                   '} catch (NumberFormatException e) {\n'
                   '    System.out.println("Eso no es un número");\n'
                   '}',
        "trampas": [
            "`parseInt(\" 42\")` con espacios falla: limpia antes con `trim()`.",
            "`parseInt(\"42.0\")` falla: para decimales, `Double.parseDouble`.",
            "Pasarse de `Integer.MAX_VALUE` da la vuelta al signo sin avisar (usa `long`).",
            "Comparar dos `Integer` con `==` solo funciona hasta 127 (caché): usa `equals`.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html",
    },
    {
        "clave": "arrays",
        "icono": "🧷",
        "titulo": "Arrays (la clase de utilidades)",
        "tipo": "Clase (java.util) — necesita `import java.util.Arrays;`",
        "alias": ("arrays", "arrays.tostring", "ordenar", "sort", "copiar", "rellenar"),
        "resumen": "Utilidades para arrays: imprimirlos, ordenarlos, copiarlos y compararlos. "
                   "El array en sí es `tipo[]`, pero los métodos viven aquí.",
        "firmas": [
            "`Arrays.toString(array)` → texto legible: `[1, 2, 3]`.",
            "`Arrays.sort(array)` → ordena en el sitio (modifica el original).",
            "`Arrays.equals(a, b)` → si tienen el mismo contenido (no `==`).",
            "`Arrays.copyOf(array, nuevoTamaño)` → copia (más larga o más corta).",
            "`Arrays.fill(array, valor)` → pone el mismo valor en todas las casillas.",
            "`Arrays.asList(1, 2, 3)` → lista de tamaño fijo a partir de valores.",
        ],
        "ejemplo": 'int[] notas = {9, 5, 7};\n'
                   '\n'
                   'System.out.println(Arrays.toString(notas)); // [9, 5, 7]\n'
                   'Arrays.sort(notas);\n'
                   'System.out.println(Arrays.toString(notas)); // [5, 7, 9]\n'
                   '\n'
                   'int[] copia = Arrays.copyOf(notas, 5);\n'
                   'System.out.println(Arrays.toString(copia)); // [5, 7, 9, 0, 0]',
        "trampas": [
            "`System.out.println(array)` imprime `[I@1b6d3586`: falta `Arrays.toString`.",
            "`Arrays.sort` no devuelve nada: ordena el array que le pasas.",
            "`Arrays.equals` compara contenido; `==` compara si es el mismo array.",
            "`Arrays.asList(...)` da una lista de tamaño fijo: `add` lanza excepción.",
        ],
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html",
    },
]


# ---------------------------------------------------------------------------
# «¿Por qué este y no el otro?»: comparaciones razonadas (sin IA)
# ---------------------------------------------------------------------------
COMPARACIONES = [
    {
        "clave": "igualdad",
        "icono": "⚖️",
        "titulo": "`==` frente a `equals()`",
        "alias": ("==", "equals", "igualdad", "comparar textos", "comparar cadenas",
                  "comparar strings", "equalsignorecase"),
        "resumen": "`==` pregunta «¿son el mismo objeto en memoria?»; `equals()` pregunta "
                   "«¿valen lo mismo?». Con textos casi siempre quieres lo segundo.",
        "opciones": [
            {"nombre": "`==`",
             "usar": "Solo con tipos primitivos (`int`, `double`, `char`, `boolean`) y con "
                     "`null`. Ahí no hay objeto y comparar el valor es justo lo que quieres.",
             "ejemplo": 'int a = 5;\nif (a == 5) { ... }           // bien\n'
                        'if (objeto == null) { ... }     // bien'},
            {"nombre": "`equals()`",
             "usar": "Con `String` y con cualquier objeto (`Integer`, `LocalDate`, tus clases). "
                     "Para ignorar mayúsculas, `equalsIgnoreCase()`.",
             "ejemplo": 'if (nombre.equals("Ana")) { ... }\n'
                        'if (nombre.equalsIgnoreCase("ana")) { ... }'},
        ],
        "regla": "Primitivos y `null` → `==`. Objetos y textos → `equals()`.",
        "error": "Con `==` en textos el programa «a veces» funciona: los literales se reutilizan "
                 "del pool y coinciden, pero un texto leído con `Scanner` o montado con `+` es "
                 "otro objeto y `==` da `false` aunque el contenido sea el mismo.",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html",
    },
    {
        "clave": "concatenacion",
        "icono": "➕",
        "titulo": "`+` frente a `StringBuilder`",
        "alias": ("+", "stringbuilder", "concatenar", "unir textos", "append", "rendimiento"),
        "resumen": "Con dos o tres trozos, `+` se lee mejor. Para pegar muchos trozos en un bucle, "
                   "`StringBuilder`.",
        "opciones": [
            {"nombre": "`+` (concatenación)",
             "usar": "Mensajes cortos, `println`, dos o tres piezas. El compilador ya lo convierte "
                     "por dentro cuando ve un `+` suelto.",
             "ejemplo": 'System.out.println("Hola, " + nombre + ". Tienes " + edad + " años.");'},
            {"nombre": "`StringBuilder`",
             "usar": "Bucles que acumulan texto, informes largos; o `String.join` para listas. "
                     "Se modifica el mismo objeto y solo se convierte al final con `toString()`.",
             "ejemplo": 'StringBuilder sb = new StringBuilder();\n'
                        'for (String tarea : tareas) {\n'
                        '    sb.append("- ").append(tarea).append("\\n");\n'
                        '}\n'
                        'System.out.println(sb.toString());'},
        ],
        "regla": "Fuera de un bucle, `+`. Acumulando dentro de un bucle, `StringBuilder`.",
        "error": "`texto += algo` dentro de un bucle crea un texto nuevo en cada vuelta: con "
                 "100 000 vueltas se nota muchísimo (es el clásico «va lentísimo»).",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html",
    },
    {
        "clave": "listas",
        "icono": "🔗",
        "titulo": "`ArrayList` frente a `LinkedList`",
        "alias": ("arraylist", "linkedlist", "listas", "colecciones", "lista"),
        "resumen": "Las dos son listas. `ArrayList` guarda los elementos seguidos en memoria (como "
                   "un array); `LinkedList` los enlaza con punteros. Al empezar, `ArrayList` casi "
                   "siempre.",
        "opciones": [
            {"nombre": "`ArrayList`",
             "usar": "El 95 % de los casos. Acceder por índice (`get(i)`) es instantáneo y recorrerla "
                     "es lo más rápido. Añadir al final también. Solo cuesta caro insertar o borrar "
                     "por el principio.",
             "ejemplo": 'ArrayList<String> lista = new ArrayList<>();\n'
                        'lista.add("Ana");\n'
                        'System.out.println(lista.get(0));   // instantáneo'},
            {"nombre": "`LinkedList`",
             "usar": "Cuando de verdad insertas y borras mucho por el principio o por el final y casi "
                     "nunca accedes por índice. También sirve como cola (`Queue`).",
             "ejemplo": 'LinkedList<String> cola = new LinkedList<>();\n'
                        'cola.addLast("primero");\n'
                        'System.out.println(cola.removeFirst());'},
        ],
        "regla": "Si dudas, `ArrayList`. Solo cambia a `LinkedList` si mides y de verdad lo necesitas.",
        "error": "Usar `LinkedList` y llamar a `get(i)` dentro de un bucle: cada `get` recorre la "
                 "lista desde el principio y el bucle se vuelve lentísimo.",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html",
    },
    {
        "clave": "arrays_listas",
        "icono": "📦",
        "titulo": "Array frente a `ArrayList`",
        "alias": ("array", "arraylist", "arrays", "lista", "tamano fijo", "size"),
        "resumen": "El array es la estructura básica: tamaño fijo y rapidísimo. `ArrayList` es un "
                   "array por dentro que crece solo y trae métodos cómodos.",
        "opciones": [
            {"nombre": "Array (`int[]`)",
             "usar": "Cuando sabes el tamaño desde el principio y no cambia: una semana de 7 días, "
                     "las notas de 30 alumnos. Ocupa menos y se accede con `[]`.",
             "ejemplo": 'int[] notas = new int[5];\n'
                        'notas[0] = 7;\n'
                        'System.out.println(notas.length);   // 5'},
            {"nombre": "`ArrayList`",
             "usar": "Cuando no sabes cuántos elementos habrá o van a entrar y salir: la lista de la "
                     "compra, los resultados de una búsqueda.",
             "ejemplo": 'ArrayList<Integer> notas = new ArrayList<>();\n'
                        'notas.add(7);\n'
                        'System.out.println(notas.size());   // 1'},
        ],
        "regla": "Tamaño conocido y fijo → array. Tamaño variable → `ArrayList`.",
        "error": "Usar `length` en la lista o `size()` en el array: `array.length` (sin paréntesis) "
                 "y `lista.size()` (con paréntesis).",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html",
    },
    {
        "clave": "int_integer",
        "icono": "🧱",
        "titulo": "`int` frente a `Integer`",
        "alias": ("int", "integer", "primitivo", "envoltorio", "wrapper", "autoboxing",
                  "null"),
        "resumen": "`int` es un valor puro; `Integer` es un objeto que envuelve un `int`. Las "
                   "colecciones y los genéricos solo aceptan objetos, y ahí entra `Integer`.",
        "opciones": [
            {"nombre": "`int` (primitivo)",
             "usar": "Variables normales, cuentas, contadores, parámetros. Es más rápido y no puede "
                     "ser `null`. En un campo de clase vale `0` por defecto.",
             "ejemplo": 'int vidas = 3;\nvidas--;\nSystem.out.println(vidas);'},
            {"nombre": "`Integer` (envoltorio)",
             "usar": "Dentro de `ArrayList<Integer>`, `HashMap<String, Integer>` o cuando necesitas "
                     "distinguir «no hay valor» (`null`). Java convierte solo al meter y sacar "
                     "(`autoboxing`).",
             "ejemplo": 'ArrayList<Integer> notas = new ArrayList<>();\n'
                        'notas.add(7);            // int → Integer\n'
                        'int primera = notas.get(0);  // Integer → int'},
        ],
        "regla": "Para trabajar, `int`. Para guardar en colecciones o admitir «vacío», `Integer`.",
        "error": "Hacer una cuenta con un `Integer` que vale `null` da `NullPointerException` al "
                 "descomprimirlo. Y comparar dos `Integer` con `==` solo acierta hasta 127.",
        "url": "https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html",
    },
    {
        "clave": "for_while",
        "icono": "🔄",
        "titulo": "`for` frente a `while`",
        "alias": ("for", "while", "do while", "bucle", "bucles", "iterar", "for each"),
        "resumen": "Los dos repiten. `for` es para «un número conocido de vueltas»; `while`, para "
                   "«mientras pase algo».",
        "opciones": [
            {"nombre": "`for`",
             "usar": "Cuando sabes cuántas veces (o recorres un array de principio a fin): el "
                     "contador, la condición y el paso están en la misma línea y no se te olvidan.",
             "ejemplo": 'for (int i = 0; i < notas.length; i++) {\n'
                        '    System.out.println(notas[i]);\n'
                        '}'},
            {"nombre": "`while`",
             "usar": "Cuando no sabes cuántas vueltas harán falta: leer hasta que el usuario escriba "
                     "«fin», insistir hasta que el número sea válido.",
             "ejemplo": 'int numero = -1;\n'
                        'while (numero <= 0) {\n'
                        '    System.out.print("Dime un número positivo: ");\n'
                        '    numero = sc.nextInt();\n'
                        '}'},
        ],
        "regla": "¿Sabes cuántas vueltas? `for`. ¿Depende de lo que pase dentro? `while`.",
        "error": "Un `while` en el que la condición no cambia nunca (o un `for` sin `i++`) cuelga el "
                 "programa: si se queda pensando para siempre, mira primero el bucle.",
        "url": "https://dev.java/learn/language-basics/",
    },
]




#: Rutas de la documentación oficial que se citan cuando la guía no tiene el tema.
URL_JAVA = "https://docs.oracle.com/en/java/javase/17/docs/api/"


def _es_estructural(errores):
    """¿Hay fallos tan gordos (comillas o llaves sin cerrar) que javac solo añadiría ruido?

    Cuando una cadena o un bloque no se cierra, el compilador se pierde y suelta
    decenas de errores en cascada que no son el problema de verdad: en ese caso se
    enseña solo lo que ha visto el analizador propio, que sí señala la línea exacta.
    """
    for fallo in errores:
        if fallo["regla"] in REGLAS_ESTRUCTURALES:
            return True
    return False


#: Reglas del analizador propio que javac cuenta igual (o peor): si el compilador
#: ya ha avisado en esa línea, se queda con su mensaje y no se duplica.
REGLAS_QUE_JAVAC_REPITE = frozenset({"punto_y_coma"})


def _combinar_errores(locales, compilador):
    """Junta lo que ve el analizador propio con lo que dice javac, sin repetirse.

    Manda javac (ha compilado de verdad), pero lo que el analizador propio explica
    mejor —`printline` en vez de `println`, `string` en minúscula, el `import` que
    falta— se conserva aunque el compilador también se queje en esa misma línea:
    el mensaje del compilador señala el síntoma y el nuestro, el arreglo.
    """
    if not compilador:
        return locales
    finales = list(compilador)
    lineas = {fallo["linea"] for fallo in compilador if fallo["gravedad"] == "error"}
    for fallo in locales:
        if fallo["regla"] in REGLAS_QUE_JAVAC_REPITE and fallo["linea"] in lineas:
            continue
        finales.append(fallo)
    finales.sort(key=lambda fallo: (fallo["linea"], fallo["columna"]))
    return finales



def _buscar_en(entrada, tabla):
    """Busca un tema de ``tabla`` por su clave o por sus alias, sin acentos ni mayúsculas.

    Devuelve el diccionario del tema o ``None``. Se aceptan las dos direcciones
    («array» encuentra «arrays» y «¿por qué no funciona mi arraylist?» encuentra
    «ArrayList»), y siempre gana el alias más largo para que «array list» no se
    quede en «array».
    """
    buscado = _normalizar(entrada)
    if not buscado:
        return None
    for tema in tabla:
        if buscado == _normalizar(tema["clave"]) or buscado == _normalizar(tema["titulo"]):
            return tema
    mejor, largo = None, 0
    for tema in tabla:
        for alias in tema.get("alias", ()):
            nombre = _normalizar(alias)
            if not nombre or len(nombre) <= largo:
                continue
            if re.search(r"\b%s\b" % re.escape(nombre), buscado) or (
                    len(buscado) >= 3 and buscado in nombre):
                mejor, largo = tema, len(nombre)
    return mejor


def _texto_errores(errores, maximo=MAX_PISTAS):
    """Los fallos en líneas de Markdown: línea, columna, qué pasa y qué hacer."""
    if not errores:
        return ""
    lineas = []
    for fallo in errores[:maximo]:
        icono = "⚠️" if fallo["gravedad"] == "aviso" else "❌"
        donde = f"línea {fallo['linea']}"
        if fallo.get("columna"):
            donde += f", columna {fallo['columna']}"
        lineas.append(f"{icono} **{donde}** · {fallo['mensaje']}")
        if fallo.get("sugerencia"):
            lineas.append(f"   → {fallo['sugerencia']}")
    return "\n".join(lineas)


class ProgrammingTutor:
    """Taller de programación: corrige en local, enseña las bases y pide lo demás a la IA.

    La corrección (``revisar`` y ``ejecutar``) es **local y gratis**: primero el
    analizador propio, después el ``javac`` de verdad si hay JDK. Las bases, la
    documentación y las comparaciones conocidas también están escritas aquí, así
    que se leen sin conexión. Solo cuando se pide algo que no está en las tablas
    (una explicación larga, unos ejercicios, una duda suelta) se devuelve
    ``MARCA_PROFE + encargo`` para que el apartado de la ventana lo pida al
    cerebro con ``APIBrain.SISTEMA_PROGRAMADOR``.
    """

    def __init__(self, config_path=rutas.CONFIG_USUARIO, carpeta=rutas.PROGRAMACION):
        self.config_path = config_path
        self.carpeta = carpeta
        os.makedirs(self.carpeta, exist_ok=True)

    # ------------------------------------------------------------------
    # Estado (nivel, prácticas y fallos repetidos)
    # ------------------------------------------------------------------
    def _ruta_estado(self):
        """Archivo donde se guarda el avance del alumno."""
        return os.path.join(self.carpeta, "estado.json")

    def _leer_estado(self):
        """Estado del alumno con los valores por defecto ya rellenados."""
        estado = {"nivel": NIVEL_POR_DEFECTO, "practicas": 0, "desde": "",
                  "errores": {}, "temas": []}
        try:
            with open(self._ruta_estado(), "r", encoding="utf-8") as archivo:
                guardado = json.load(archivo)
            if isinstance(guardado, dict):
                estado.update({clave: valor for clave, valor in guardado.items()
                               if valor is not None})
        except (OSError, ValueError):
            pass  # Sin estado previo (o ilegible): se empieza de cero
        if estado.get("nivel") not in NIVELES:
            estado["nivel"] = NIVEL_POR_DEFECTO
        if not isinstance(estado.get("errores"), dict):
            estado["errores"] = {}
        if not isinstance(estado.get("temas"), list):
            estado["temas"] = []
        return estado

    def _guardar_estado(self, estado):
        """Guarda el avance (a prueba de fallos: nunca rompe la ventana)."""
        try:
            os.makedirs(self.carpeta, exist_ok=True)
            with open(self._ruta_estado(), "w", encoding="utf-8") as archivo:
                json.dump(estado, archivo, ensure_ascii=False, indent=2)
        except OSError as error:
            print(f"No se pudo guardar el progreso de programación: {error}")

    def nivel(self):
        """Nivel actual del alumno (Principiante, Intermedio o Avanzado)."""
        return self._leer_estado()["nivel"]

    def fijar_nivel(self, texto):
        """Fija el nivel a partir de lo que diga el usuario ('nivel avanzado')."""
        texto = (texto or "").strip()
        buscado = ""
        for nivel in NIVELES:
            if re.search(rf"\b{nivel}\b", texto, re.IGNORECASE):
                buscado = nivel
                break
        if not buscado:
            minusculas = _normalizar(texto)
            for palabra, nivel in NIVELES_EN_PALABRAS.items():
                if _normalizar(palabra) in minusculas:
                    buscado = nivel
                    break
        if not buscado:
            return ("No sé con qué nivel quedarme. Dime uno entre Principiante, Intermedio y "
                    "Avanzado (por ejemplo: 'nivel intermedio') y explico con esa dificultad.")
        estado = self._leer_estado()
        anterior = estado["nivel"]
        estado["nivel"] = buscado
        self._guardar_estado(estado)
        if anterior == buscado:
            return f"Ya estabas en {buscado}: lo dejo así."
        return (f"Nivel actualizado: {anterior} → {buscado}.\n\n"
                f"A partir de ahora las explicaciones y los ejercicios van con la dificultad de "
                f"{buscado}. La corrección es la misma para todos los niveles: los errores de "
                "compilación no entienden de niveles.")

    def _registrar_practica(self, estado, resumen):
        """Apunta una práctica nueva y guarda solo los últimos eventos."""
        estado["practicas"] = int(estado.get("practicas") or 0) + 1
        if not estado.get("desde"):
            estado["desde"] = datetime.now().strftime("%Y-%m-%d")
        eventos = estado["temas"]
        eventos.append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "resumen": str(resumen)[:120]})
        estado["temas"] = eventos[-MAX_EVENTOS:]

    def registrar(self, errores, resumen="práctica"):
        """Suma los fallos encontrados al historial y cuenta la práctica.

        ``errores`` son los diccionarios que devuelve ``revisar`` (con ``regla``,
        ``mensaje`` y ``sugerencia``); al historial solo van los que se repiten,
        que es lo que luego se recuerda en el progreso.
        """
        estado = self._leer_estado()
        for fallo in errores or []:
            clave = str(fallo.get("regla") or "error")
            datos = estado["errores"].get(clave) or {"veces": 0}
            datos["veces"] = int(datos.get("veces") or 0) + 1
            datos["titulo"] = fallo.get("mensaje") or clave
            datos["sugerencia"] = str(fallo.get("sugerencia") or "")[:160]
            datos["linea"] = int(fallo.get("linea") or 0)
            datos["fecha"] = datetime.now().strftime("%Y-%m-%d")
            estado["errores"][clave] = datos
        self._registrar_practica(estado, resumen)
        self._guardar_estado(estado)

    def frecuentes(self, cuantos=MAX_MEMORIA):
        """Fallos más repetidos: ``[(clave, datos), ...]`` de más a menos."""
        errores = self._leer_estado()["errores"]
        ordenados = sorted(errores.items(),
                           key=lambda elemento: (-int(elemento[1].get("veces") or 0), elemento[0]))
        return ordenados[:cuantos]

    def resumen(self):
        """Cabecera del alumno en datos sueltos: nivel, prácticas y repetidos."""
        estado = self._leer_estado()
        return {
            "nivel": estado["nivel"],
            "practicas": int(estado.get("practicas") or 0),
            "desde": estado.get("desde") or "",
            "repetidos": self.frecuentes(),
            "jdk": self.hay_jdk(),
        }

    # ------------------------------------------------------------------
    # Corrección: analizador local + javac de verdad
    # ------------------------------------------------------------------
    def hay_jdk(self):
        """¿Está instalado el JDK? (sin él se corrige lo básico y no se compila)."""
        if getattr(self, "_jdk", None) is None:
            self._jdk = bool(shutil.which("javac") and shutil.which("java"))
        return self._jdk

    def revisar(self, codigo, compilar=True):
        """Revisa el código y devuelve los fallos con su línea y su columna.

        Devuelve un diccionario con ``ok``, ``errores`` (la lista, ya ordenada por
        línea), ``compilado`` (si javac lo aceptó), ``jdk`` (si hay compilador),
        ``total`` y ``texto`` (el mismo resultado en Markdown, listo para el panel).
        Sin JDK se revisa solo lo básico y se avisa en el texto.
        """
        texto = str(codigo or "")[:MAX_CODIGO]
        hay_jdk = self.hay_jdk()
        datos = {"ok": True, "errores": [], "compilado": False, "jdk": hay_jdk,
                 "total": 0, "texto": ""}
        if not texto.strip():
            datos["texto"] = ("Escribe tu programa en el editor y lo reviso mientras escribes: "
                              "cada aviso sale con su línea y su columna.")
            return datos

        errores = _analizar_local(texto)
        if compilar and hay_jdk and not _es_estructural(errores):
            resultado = self._compilar(texto)
            datos["compilado"] = resultado["ok"]
            errores = _combinar_errores(errores, resultado["errores"])
            try:
                shutil.rmtree(resultado["carpeta"], ignore_errors=True)
            except OSError:
                pass
        datos["errores"] = errores
        datos["total"] = len(errores)
        datos["ok"] = not any(fallo["gravedad"] == "error" for fallo in errores)

        if not errores:
            if hay_jdk and compilar:
                datos["texto"] = "✅ **Todo bien**: el código compila y no veo nada que corregir."
            elif hay_jdk:
                datos["texto"] = "✅ **Todo bien** en la revisión rápida (pulsa «Corregir» para compilarlo)."
            else:
                datos["texto"] = ("✅ **Nada que corregir en la revisión básica.** No hay JDK instalado, "
                                  "así que no puedo compilarlo: reviso llaves, paréntesis, puntos y coma "
                                  "y los errores típicos de empezar.")
            return datos

        cabecera = ("🔎 **{n} aviso(s)**: lo primero que hay que arreglar es lo de la línea más "
                    "alta.").format(n=len(errores))
        if not hay_jdk:
            cabecera += ("\n\n_(Sin JDK solo se revisa lo básico: para que el compilador de verdad "
                         "avise de todo, instala un JDK y reinicia la ventana.)_")
        elif datos["compilado"]:
            cabecera = f"🔎 **{len(errores)} aviso(s)** (el código compila, pero hay cosas que "
            cabecera += "conviene cambiar):"
        datos["texto"] = cabecera + "\n\n" + _texto_errores(errores)
        return datos

    def _compilar(self, codigo, carpeta=None):
        """Compila el código con javac en una carpeta temporal.

        Devuelve ``dict`` con ``ok``, ``errores`` (los que ha visto javac, con línea
        y columna), ``carpeta`` (donde quedan las clases; la borra quien llama),
        ``clase``, ``paquete`` y ``salida`` (el texto crudo del compilador). El
        archivo se llama como la clase pública —si no, javac ni empieza— y se
        guarda en la carpeta de su paquete. Se fuerza el idioma inglés de javac
        para poder traducir sus mensajes con ``SUGERENCIAS_JAVAC``.
        """
        base = carpeta or tempfile.mkdtemp(prefix="jarvis_java_")
        paquete = _paquete_de(codigo)
        clase = _nombre_de_clase(codigo)
        datos = {"ok": False, "errores": [], "carpeta": base, "clase": clase,
                 "paquete": paquete, "salida": ""}
        destino = os.path.join(base, "src")
        if paquete:
            destino = os.path.join(destino, *paquete.split("."))
        try:
            os.makedirs(destino, exist_ok=True)
            archivo = os.path.join(destino, clase + ".java")
            with open(archivo, "w", encoding="utf-8") as salida:
                salida.write(codigo)
            clases = os.path.join(base, "classes")
            os.makedirs(clases, exist_ok=True)
            orden = [shutil.which("javac") or "javac",
                     "-J-Duser.language=en", "-J-Duser.country=US",
                     "-encoding", "UTF-8", "-d", clases, archivo]
            proceso = subprocess.run(orden, capture_output=True, timeout=TIEMPO_COMPILAR,
                                     creationflags=_SIN_VENTANA)
        except subprocess.TimeoutExpired:
            datos["errores"] = [_error(
                1, 0, "javac", "El compilador no terminó a tiempo",
                f"javac tardó más de {TIEMPO_COMPILAR} s: prueba con menos código a la vez.")]
            return datos
        except OSError as error:
            datos["errores"] = [_error(
                1, 0, "javac", "No pude ejecutar javac",
                f"Revisa la instalación del JDK: {error}")]
            return datos
        datos["salida"] = _decodificar(proceso.stdout) + _decodificar(proceso.stderr)
        datos["errores"] = _errores_de_javac(datos["salida"])
        datos["ok"] = proceso.returncode == 0
        if not datos["ok"] and not datos["errores"]:
            datos["errores"] = [_error(
                1, 0, "javac", "javac rechazó el código pero no dijo dónde",
                "Mira la salida del compilador: suele ser un archivo que no se pudo "
                "escribir o un nombre de clase que no coincide.")]
        return datos

    def ejecutar(self, codigo, entrada=""):
        """Compila y ejecuta el programa, y devuelve lo que sale por pantalla.

        ``entrada`` es lo que el programa leerá por teclado (lo que se escribiría
        línea a línea). Devuelve ``dict`` con ``ok``, ``salida``, ``errores``,
        ``compilado``, ``jdk`` y ``texto`` (Markdown listo para el panel). Se corta
        a los ``TIEMPO_EJECUTAR`` segundos para que un bucle infinito no cuelgue
        la ventana.
        """
        texto = str(codigo or "")[:MAX_CODIGO]
        datos = {"ok": False, "salida": "", "errores": [], "compilado": False,
                 "jdk": self.hay_jdk(), "texto": ""}
        if not texto.strip():
            datos["texto"] = ("Escribe el programa en el editor y pulsa «Probar» para "
                              "ejecutarlo y ver lo que imprime.")
            return datos
        if not datos["jdk"]:
            datos["texto"] = ("Para **ejecutar** el programa hace falta el JDK de Java (el "
                              "`javac` y el `java`). Instálalo (por ejemplo, Adoptium Temurin), "
                              "reinicia la ventana y podrás probar el código aquí mismo.")
            return datos

        resultado = self._compilar(texto)
        datos["errores"] = _combinar_errores(_analizar_local(texto), resultado["errores"])
        try:
            if not resultado["ok"]:
                datos["texto"] = ("❌ **Primero tiene que compilar**: todavía no se puede "
                                  "ejecutar.\n\n" + _texto_errores(datos["errores"]))
                return datos
            datos["compilado"] = True
            clases = os.path.join(resultado["carpeta"], "classes")
            principal = resultado["clase"]
            if resultado["paquete"]:
                principal = resultado["paquete"] + "." + principal
            orden = [shutil.which("java") or "java",
                     "-Duser.language=en", "-Dfile.encoding=UTF-8",
                     "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
                     "-Dstdin.encoding=UTF-8",
                     "-cp", clases, principal]
            try:
                proceso = subprocess.run(orden, input=str(entrada or "").encode("utf-8"),
                                         capture_output=True, timeout=TIEMPO_EJECUTAR,
                                         creationflags=_SIN_VENTANA)
            except subprocess.TimeoutExpired:
                datos["texto"] = (f"⏱ **El programa no terminó en {TIEMPO_EJECUTAR} s** y lo he "
                                  "parado. Casi siempre es un bucle que no acaba (`while` con la "
                                  "condición siempre verdadera) o un `Scanner` esperando un dato "
                                  "más: revisa el bucle y escribe en «Entrada» lo que tenga que leer.")
                return datos
            except OSError as error:
                datos["texto"] = f"No pude lanzar el programa: {error}"
                return datos
        finally:
            shutil.rmtree(resultado["carpeta"], ignore_errors=True)

        salida = _decodificar(proceso.stdout)
        errores_salida = _decodificar(proceso.stderr).strip()
        datos["ok"] = proceso.returncode == 0
        if len(salida) > MAX_SALIDA:
            salida = salida[:MAX_SALIDA] + "\n… (salida recortada: el programa imprime mucho)"
        datos["salida"] = salida
        trozos = []
        if salida.strip():
            trozos.append("▶️ **Salida del programa**\n" + _bloque(salida.rstrip()))
        else:
            trozos.append("▶️ El programa terminó sin imprimir nada.")
        if errores_salida:
            trozos.append(f"💥 **Terminó con un error** (código {proceso.returncode})\n"
                          + _bloque(errores_salida))
            if "NoSuchElementException" in errores_salida:
                trozos.append("_El programa pidió un dato por teclado y no lo tenía: escribe lo "
                              "que vaya a leer en el campo «Entrada» y vuelve a probar._")
        elif datos["ok"]:
            trozos.append("_Terminó bien (código 0). Tiempo máximo permitido: "
                          f"{TIEMPO_EJECUTAR} s._")
        datos["texto"] = "\n\n".join(trozos)
        return datos

    # ------------------------------------------------------------------
    # Las bases: temario y lecciones (escritas aquí, sin IA)
    # ------------------------------------------------------------------
    def bases(self):
        """El temario completo de Java, en Markdown y por niveles."""
        if not BASES:
            return "Todavía no hay temario."
        trozos = [f"## 📚 Las bases de {LENGUAJE}",
                  "Los {n} temas del curso, de menos a más. Escribe el nombre de uno en «Tema» "
                  "y pulsa **Lección**, o pídeme cualquiera que no esté.".format(n=len(BASES))]
        for nivel in NIVELES:
            temas = [tema for tema in BASES if tema.get("nivel") == nivel]
            if not temas:
                continue
            trozos.append(f"### {nivel}")
            for tema in temas:
                trozos.append(f"- {tema['icono']} **{tema['titulo']}** (`{tema['clave']}`) — "
                              f"{tema['resumen']}")
        trozos.append(f"\n📖 Documentación oficial de Java: {URL_JAVA}")
        return "\n".join(trozos)

    def _formatear_leccion(self, tema):
        """Una entrada de ``BASES`` en Markdown: conceptos, sintaxis, ejemplo y ejercicio."""
        trozos = [f"## {tema['icono']} {tema['titulo']}",
                  f"**Nivel:** {tema.get('nivel', 'Principiante')}",
                  tema["resumen"]]
        if tema.get("conceptos"):
            trozos.append("### 🧩 Lo que hay que entender")
            trozos.extend(f"- {concepto}" for concepto in tema["conceptos"])
        if tema.get("sintaxis"):
            trozos.append("### ⌨️ La sintaxis")
            trozos.append(_bloque(tema["sintaxis"]))
        if tema.get("ejemplo"):
            trozos.append("### 💡 Un ejemplo comentado")
            trozos.append(_bloque(tema["ejemplo"]))
        if tema.get("errores"):
            trozos.append("### ⚠️ Los errores típicos")
            trozos.extend(f"- {fallo}" for fallo in tema["errores"])
        if tema.get("ejercicio"):
            trozos.append("### ✍️ Tu ejercicio")
            trozos.append(tema["ejercicio"])
        if tema.get("url"):
            trozos.append(f"📖 {tema['url']}")
        return "\n\n".join(trozos)

    def leccion(self, tema=""):
        """La lección de un tema del temario; si no está, se le pide a la IA."""
        consulta = str(tema or "").strip()
        if not consulta:
            lista = "\n".join(f"- {t['icono']} {t['titulo']} (`{t['clave']}`)" for t in BASES)
            return ("Dime de qué tema quieres la lección: escríbelo en «Tema» (por ejemplo "
                    "`bucles`, `arrays` o `clases`) y vuelve a pulsar **Lección**. Estos son "
                    "los que tengo preparados:\n\n" + lista)
        encontrado = _buscar_en(consulta, BASES)
        if encontrado:
            return self._formatear_leccion(encontrado)
        return self._pedir(
            f"Da una lección de Java sobre «{consulta}», que no está en el temario básico.",
            "Estructura: qué es y para qué sirve, la sintaxis, un ejemplo comentado que "
            "compile, los errores típicos y un ejercicio. Si el tema no es de Java, dilo y "
            "propón el equivalente más cercano.")

    # ------------------------------------------------------------------
    # Documentación y comparaciones (guía de consulta, sin IA)
    # ------------------------------------------------------------------
    def _formatear_documentacion(self, entrada):
        """Una entrada de ``DOCUMENTACION``: qué es, firmas, ejemplo y trampas."""
        trozos = [f"## {entrada['icono']} {entrada['titulo']}",
                  f"**Qué es:** {entrada.get('tipo', '')}",
                  entrada["resumen"]]
        if entrada.get("firmas"):
            trozos.append("### 📎 Lo que más se usa")
            trozos.extend(f"- {firma}" for firma in entrada["firmas"])
        if entrada.get("ejemplo"):
            trozos.append("### 💡 Ejemplo")
            trozos.append(_bloque(entrada["ejemplo"]))
        if entrada.get("trampas"):
            trozos.append("### ⚠️ Trampas")
            trozos.extend(f"- {trampa}" for trampa in entrada["trampas"])
        if entrada.get("url"):
            trozos.append(f"📖 {entrada['url']}")
        return "\n\n".join(trozos)

    def documentacion(self, tema=""):
        """La guía de consulta de una clase o método; si no está, se le pide a la IA."""
        consulta = str(tema or "").strip()
        if not consulta:
            lista = "\n".join(f"- {e['icono']} {e['titulo']}" for e in DOCUMENTACION)
            return ("¿De qué quieres la documentación? Escríbelo en «Tema» (por ejemplo `String`, "
                    "`ArrayList` o `Scanner`) y pulsa **Documentación**. Tengo preparado:\n\n"
                    + lista + f"\n\n📖 La oficial, completa: {URL_JAVA}")
        encontrado = _buscar_en(consulta, DOCUMENTACION)
        if encontrado:
            return self._formatear_documentacion(encontrado)
        return self._pedir(
            f"Explica la documentación de «{consulta}» en Java, que no está en mi guía rápida.",
            "Estructura: qué es y de qué paquete viene (con el `import` si hace falta), las "
            "firmas de los métodos que más se usan, un ejemplo completo que compile, las "
            "trampas habituales y el enlace a la documentación oficial de Oracle. Si esa "
            "clase no existe en la API de Java, dilo claramente y propón la que sí existe.")

    def _formatear_comparacion(self, entrada):
        """Una entrada de ``COMPARACIONES``: las opciones, la regla y el error típico."""
        trozos = [f"## {entrada['icono']} {entrada['titulo']}", entrada["resumen"]]
        for opcion in entrada.get("opciones", ()):
            trozos.append(f"### {opcion['nombre']}")
            trozos.append(f"**Cuándo:** {opcion['usar']}")
            if opcion.get("ejemplo"):
                trozos.append(_bloque(opcion["ejemplo"]))
        if entrada.get("regla"):
            trozos.append("### 🎯 La regla, en una línea")
            trozos.append(f"**{entrada['regla']}**")
        if entrada.get("error"):
            trozos.append("### 🐛 El error típico")
            trozos.append(entrada["error"])
        if entrada.get("url"):
            trozos.append(f"📖 {entrada['url']}")
        return "\n\n".join(trozos)

    def comparar(self, consulta=""):
        """«¿Por qué este y no el otro?»: comparación razonada; si no está, se pide a la IA."""
        consulta = str(consulta or "").strip()
        if not consulta:
            lista = "\n".join(f"- {e['icono']} {e['titulo']}" for e in COMPARACIONES)
            return ("Dime qué quieres comparar en «Tema» (por ejemplo `== o equals`, "
                    "`ArrayList o LinkedList`) y pulsa **¿Por qué…?**. Tengo preparado:\n\n"
                    + lista)
        encontrado = _buscar_en(consulta, COMPARACIONES)
        if encontrado:
            return self._formatear_comparacion(encontrado)
        return self._pedir(
            f"Compara «{consulta}» en Java y razona cuál usar en cada caso.",
            "Estructura: qué hace cada opción, cuándo conviene cada una (con el porqué y el "
            "coste), un ejemplo de cada una que compile, la regla para decidirse en una línea "
            "y el error típico de elegir mal. Si la comparación no tiene sentido en Java, dilo "
            "y plantea la que sí lo tenga.")

    # ------------------------------------------------------------------
    # Lo que sí necesita la IA: dudas, explicaciones y ejercicios
    # ------------------------------------------------------------------
    def _pistas(self, errores, maximo=MAX_PISTAS):
        """Los fallos en una línea cada uno, para pasárselos a la IA en el encargo."""
        if not errores:
            return "- (ninguno: tal como está, el código compila)"
        return "\n".join(
            f"- línea {fallo['linea']}, columna {fallo['columna']}: {fallo['mensaje']} "
            f"[{fallo['regla']}]" for fallo in errores[:maximo])

    def _memoria(self):
        """Nivel del alumno y fallos que más se le repiten, para el encargo."""
        datos = self.resumen()
        trozos = [f"Nivel del alumno: {datos['nivel']}.",
                  f"Prácticas corregidas hasta ahora: {datos['practicas']}."]
        if datos["repetidos"]:
            lineas = [f"- {info.get('titulo') or clave} (×{info.get('veces')})"
                      for clave, info in datos["repetidos"]]
            trozos.append("Fallos que más se le repiten:\n" + "\n".join(lineas))
        return "\n".join(trozos)

    def _pedir(self, tarea, detalle=""):
        """Envuelve el encargo para la IA con el nivel y la memoria del alumno."""
        partes = [f"Tarea: {tarea}"]
        if detalle:
            partes.append(detalle)
        partes.append(self._memoria())
        partes.append(f"Lenguaje: {LENGUAJE} (17 o posterior). Responde en español y con "
                      "ejemplos que compilen tal cual.")
        return MARCA_PROFE + "\n\n".join(partes)

    def preguntar(self, pregunta="", codigo=""):
        """Una duda suelta del alumno (con su código delante, si lo hay)."""
        duda = str(pregunta or "").strip()
        if not duda:
            return ("Escríbeme la duda en «Tema» (por ejemplo: «¿por qué mi `while` no termina?») "
                    "y pulsa **Preguntar**. Si quieres que mire tu código, que esté en el editor.")
        detalle = f"Duda del alumno: {duda}"
        texto = str(codigo or "")[:MAX_CODIGO].strip()
        if texto:
            detalle += "\n\nSu código:\n" + _bloque(texto)
            detalle += ("\n\nFallos que ha detectado el analizador:\n"
                        + self._pistas(self.revisar(texto, compilar=False)["errores"]))
        return self._pedir("Contesta a la duda, con el porqué y con un ejemplo mínimo.",
                           detalle)

    def conversar(self, pregunta="", codigo="", hilo=None):
        """Un turno del chat del taller: la duda, lo ya hablado y el código delante.

        Es el hermano conversador de ``preguntar``: el chat del apartado guarda su
        propio hilo (``[(quién, texto)]``) y aquí se le pasa a la IA para que la
        segunda pregunta se conteste con lo que ya se dijo, como en una
        conversación normal. Sin duda que contestar devuelve la pista sin gastar IA.
        """
        duda = str(pregunta or "").strip()
        if not duda:
            return ("Escríbeme la duda aquí abajo (por ejemplo: «¿por qué mi `while` no "
                    "termina?») y te la contesto con tu código delante.")
        detalle = f"Duda del alumno: {duda}"
        conversacion = self._hilo_en_texto(hilo)
        if conversacion:
            detalle = conversacion + "\n\n" + detalle
        texto = str(codigo or "")[:MAX_CODIGO].strip()
        if texto:
            detalle += "\n\nSu código (el que tiene ahora en el editor):\n" + _bloque(texto)
            detalle += ("\n\nFallos que ha detectado el analizador:\n"
                        + self._pistas(self.revisar(texto, compilar=False)["errores"]))
        return self._pedir(
            "Contesta a la duda del chat como en una conversación: directo al grano, con el "
            "porqué y con un ejemplo mínimo que compile. Si la duda va sobre su código, cita "
            "la línea y di qué cambiar.", detalle)

    @staticmethod
    def _hilo_en_texto(hilo, maximo=MAX_TURNOS_CHAT, maximo_caracteres=MAX_HILO_CHAT):
        """La conversación hasta ahora en texto llano (lo último, al final).

        Se queda con los últimos turnos y se para cuando el texto ya no cabe en el
        encargo: es contexto para la IA, no la conversación entera.
        """
        turnos = [(str(quien or "").strip(), str(texto or "").strip())
                  for quien, texto in (hilo or [])]
        turnos = [(quien, texto) for quien, texto in turnos if texto]
        if not turnos:
            return ""
        trozos = []
        total = 0
        for quien, texto in reversed(turnos[-maximo:]):
            trozo = f"{quien}: {texto}"
            if total + len(trozo) > maximo_caracteres:
                break
            trozos.insert(0, trozo)
            total += len(trozo)
        if not trozos:
            return ""
        return ("Lo que ya se han dicho en este chat (lo último, al final):\n"
                + "\n\n".join(trozos))

    def explicar(self, codigo="", errores=None):
        """«¿Por qué falla esto?»: explicación razonada de los fallos del código."""
        texto = str(codigo or "")[:MAX_CODIGO].strip()
        if not texto:
            return ("Pon tu programa en el editor y pulsa **¿Por qué…?**: te explico el porqué de "
                    "cada fallo y cómo arreglarlo, no solo dónde está.")
        if errores is None:
            errores = self.revisar(texto)["errores"]
        detalle = ("Fallos detectados (línea, columna y qué pasa):\n" + self._pistas(errores)
                   + "\n\nSu código:\n" + _bloque(texto))
        return self._pedir(
            "Explica por qué falla este programa: el motivo de fondo de cada fallo, cómo "
            "arreglarlo (con la línea corregida) y qué conviene recordar para no repetirlo.",
            detalle)

    def ejercicios(self, tema="", cuantos=MAX_EJERCICIOS // 2):
        """Ejercicios para practicar un tema (o los fallos que más se repiten)."""
        cantidad = _numero(cuantos, MAX_EJERCICIOS // 2)
        consulta = str(tema or "").strip()
        encontrado = _buscar_en(consulta, BASES) if consulta else None
        if encontrado:
            asunto = f"el tema «{encontrado['titulo']}» ({encontrado['clave']})"
        elif consulta:
            asunto = f"el tema «{consulta}»"
        elif self.frecuentes():
            asunto = "los fallos que más se le repiten"
        else:
            asunto = "lo básico de Java: variables, condiciones y bucles"
        detalle = (f"Prepara {_cantidad(cantidad, 'ejercicio', 'ejercicios')} de Java sobre "
                   f"{asunto}, de menos a más dificultad.")
        detalle += ("\n\nPara cada uno: el enunciado, un ejemplo de entrada y salida si hace "
                    "falta, y una pista. Al final, las soluciones en un bloque aparte.")
        return self._pedir("Ejercicios para practicar (no los resuelvas al principio).", detalle)

    # ------------------------------------------------------------------
    # El avance del alumno
    # ------------------------------------------------------------------
    def progreso(self, accion=""):
        """Nivel, prácticas y fallos repetidos; con ``accion='borrar'`` empieza de cero."""
        if str(accion or "").strip().lower() == "borrar":
            estado = self._leer_estado()
            self._guardar_estado({"nivel": estado["nivel"], "practicas": 0, "desde": "",
                                  "errores": {}, "temas": []})
            return ("He borrado el avance (prácticas y fallos). El nivel lo dejo en "
                    f"{estado['nivel']}: cámbialo arriba a la derecha si quieres otra cosa.")
        datos = self.resumen()
        trozos = ["## 📊 Tu avance en programación",
                  f"**Nivel:** {datos['nivel']}",
                  f"**Prácticas corregidas:** {datos['practicas']}"]
        if datos["desde"]:
            trozos.append(f"**Empezaste el:** {datos['desde']}")
        trozos.append("**Compilador:** " + ("JDK instalado: se compila y se ejecuta de verdad."
                                           if datos["jdk"] else
                                           "sin JDK: solo se revisa lo básico (instálalo para "
                                           "compilar y probar el código)."))
        if datos["repetidos"]:
            trozos.append("### 🔁 Lo que más se te repite")
            for clave, info in datos["repetidos"]:
                trozos.append(f"- **{info.get('titulo') or clave}** — {info.get('veces')} "
                              f"vez/veces. {info.get('sugerencia') or ''}"
                              .rstrip())
            trozos.append("_Pulsa **Ejercicios** con «Tema» vacío: te los preparo sobre esto._")
        else:
            trozos.append("### 🔁 Lo que más se te repite\n- Todavía nada: corrige algún programa "
                          "y aquí saldrá lo que más te cueste.")
        eventos = self._leer_estado()["temas"][-5:]
        if eventos:
            trozos.append("### 🕘 Últimas prácticas")
            for evento in reversed(eventos):
                trozos.append(f"- {evento.get('fecha', '')} · {evento.get('resumen', '')}")
        return "\n\n".join(trozos)






