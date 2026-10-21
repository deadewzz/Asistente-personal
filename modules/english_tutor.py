"""Tutor de inglés: corrige, explica cada error y enseña paso a paso.

El asistente no traduce: enseña. Cuando el usuario escribe o dicta algo en
inglés (o pregunta una duda en español), este módulo:

1. **Detecta por su cuenta** los fallos típicos de un hispanohablante
   (concordancia, tercera persona, ``did`` + pasado, doble negación, calcos como
   *explain me* o *I have 30 years*, plurales incontables, ortografía...) con
   reglas propias: no gasta ninguna llamada a la IA y funciona sin internet.
   Cada regla dice lo que se escribió, cómo se dice y **por qué**.
2. **Pide a la IA** la corrección completa con la explicación punto por punto,
   los ejercicios y las reglas de fondo. Esa petición vuelve con la marca
   ``__TUTOR__``, que distingue el *encargo* (lo que hay que pedirle al
   profesor) del *aviso* para el alumno («escribe algo y te lo corrijo»). El
   apartado «Clase de inglés» de la ventana manda los encargos al cerebro con el
   prompt de profesor (``APIBrain.SISTEMA_TUTOR``), que responde largo y en
   Markdown y **no** interpreta comandos de acción. El tutor no se usa desde el
   chat: tiene su propio apartado, con su botón en la barra lateral.
3. **Recuerda los errores**: cada regla detectada suma en ``ingles/estado.json``
   junto al nivel del alumno, cuántas prácticas lleva y qué le falla más, y de
   ahí salen el repaso y el progreso (``progreso()``).
4. **Habla contigo** (``speaking()``): las demás tareas se escriben, pero esta se
   *dice*. El apartado pone el micrófono (``VoiceEngine.escuchar_ingles``, en
   inglés) y lee en voz alta la réplica de la IA (``hablar(..., idioma="en")``),
   que va en su propio apartado —«Lo que digo yo»— para que sea lo único que
   suena; la corrección, la pronunciación y el turno siguiente quedan por
   escrito en el panel.

Sin IA configurada (sin API Key) el módulo sigue siendo útil: detecta los
errores, explica sus reglas y lleva la cuenta; lo que no puede es redactar la
corrección completa.
"""

import json
import os
import re
from datetime import datetime

from modules import rutas


#: Marca con la que el tutor señala «esto es el encargo, no la clase». Cada tarea
#: devuelve o el encargo para la IA (con esta marca delante) o un aviso para el
#: alumno (p. ej. «escríbeme algo y te lo corrijo»). El apartado «Clase de inglés»
#: de la ventana pide a la IA solo lo primero, con el prompt de profesor: así la
#: clase sale larga y en Markdown, sin recortar a tres frases (como haría
#: ``__CONTEXTO__``) y sin leer comandos de acción dentro.
MARCA_TUTOR = "__TUTOR__"

#: Niveles MCER que admite el tutor y el que se usa si el usuario no dice nada.
NIVELES = ("A1", "A2", "B1", "B2", "C1", "C2")
NIVEL_POR_DEFECTO = "B1"

#: Nivel dicho con palabras (para 'nivel intermedio', 'nivel avanzado'...).
NIVELES_EN_PALABRAS = {
    "principiante": "A1", "basico": "A1", "básico": "A1", "inicial": "A1",
    "elemental": "A2", "preintermedio": "A2", "pre-intermedio": "A2",
    "intermedio bajo": "B1", "intermedio": "B1",
    "intermedio alto": "B2", "avanzado": "C1", "advanced": "C1",
    "nativo": "C2", "bilingue": "C2", "bilingüe": "C2",
}

#: Límites de tamaño (todo lo que viaja al prompt se recorta).
MAX_TEXTO = 4000            # caracteres del texto del alumno que se analizan
MAX_PISTAS = 6              # errores detectados que se le pasan a la IA
MAX_MEMORIA = 6             # errores repetidos que se recuerdan a la IA
MAX_EVENTOS = 20            # últimas prácticas guardadas en el estado
MAX_EJERCICIOS = 10         # techo de ejercicios pedidos de una vez
EJERCICIOS_POR_DEFECTO = 5
MAX_PALABRAS = 15           # techo de palabras de vocabulario
PALABRAS_POR_DEFECTO = 8

#: Palabras que los hispanohablantes escriben mal casi siempre igual.
ORTOGRAFIA = {
    "recieve": "receive", "recieved": "received", "recieving": "receiving",
    "beleive": "believe", "beleived": "believed", "occured": "occurred",
    "occuring": "occurring", "definately": "definitely", "seperate": "separate",
    "seperated": "separated", "neccessary": "necessary",
    "necesary": "necessary", "begining": "beginning", "untill": "until",
    "wich": "which", "thier": "their", "teh": "the", "allways": "always",
    "becuase": "because", "becouse": "because", "excercise": "exercise",
    "adress": "address", "succesful": "successful", "enviroment": "environment",
    "goverment": "government", "tommorow": "tomorrow", "comunication": "communication",
}
_PATRON_ORTOGRAFIA = r"\b(" + "|".join(ORTOGRAFIA) + r")\b"

#: Plurales imposibles: en inglés estas palabras son incontables (sin 's').
INCONTABLES = {
    "informations": "information", "advices": "advice", "furnitures": "furniture",
    "equipments": "equipment", "softwares": "software", "feedbacks": "feedback",
    "homeworks": "homework", "luggages": "luggage", "knowledges": "knowledge",
    "peoples": "people", "staffs": "staff", "moneys": "money",
    "researches": "research", "trainings": "training", "news": "news",
}
_PATRON_INCONTABLES = r"\b(" + "|".join(INCONTABLES) + r")\b"

#: Pasado irregular -> infinitivo. Tras ``did``/``didn't`` el verbo va en forma
#: base, así que el error se arregla solo deshaciendo la conjugación.
IRREGULARES = {
    "went": "go", "saw": "see", "ate": "eat", "had": "have", "made": "make",
    "took": "take", "gave": "give", "came": "come", "got": "get", "said": "say",
    "told": "tell", "wrote": "write", "bought": "buy", "brought": "bring",
    "found": "find", "thought": "think", "knew": "know", "met": "meet",
    "became": "become", "began": "begin", "broke": "break", "chose": "choose",
    "drank": "drink", "drove": "drive", "fell": "fall", "felt": "feel",
    "forgot": "forget", "grew": "grow", "kept": "keep", "left": "leave",
    "lost": "lose", "paid": "pay", "ran": "run", "sang": "sing", "sat": "sit",
    "slept": "sleep", "spoke": "speak", "spent": "spend", "stood": "stand",
    "swam": "swim", "taught": "teach", "understood": "understand",
    "wore": "wear", "won": "win", "was": "be", "were": "be",
}
_PATRON_IRREGULARES = r"\b(" + "|".join(IRREGULARES) + r")\b"

#: Verbos en forma base que se conjugan solos en 3.ª persona (he works).
#: Se dejan fuera los que no cambian de forma en pasado (read, put, set, cut...)
#: para no marcar como error una frase en pasado ('he read the book yesterday').
VERBOS_TERCERA = (
    "have|do|go|want|like|need|make|take|come|work|live|study|play|say|get|know|"
    "think|look|see|eat|run|write|speak|love|help|give|find|feel|seem|start|call|"
    "turn|show|hear|tell|ask|move|believe|begin|leave|bring|watch|teach|wash|fix|"
    "pass|try|carry|worry|buy|send|spend|build|catch|choose|draw|drink|drive|fall|"
    "fight|forget|grow|keep|learn|meet|pay|sell|sing|sit|sleep|stand|swim|"
    "understand|wear|win|cost|happen"
)

#: Estados que en español van con 'tener' y en inglés con 'to be'.
ESTADOS_CON_BE = (
    "hungry", "thirsty", "sleepy", "cold", "hot", "right", "wrong", "afraid",
    "scared", "tired", "sure", "ready",
)


def _conjugar_tercera(verbo):
    """Devuelve el verbo en 3.ª persona del singular (he works, she goes...)."""
    verbo = verbo.lower()
    if verbo == "have":
        return "has"
    if verbo in ("do", "go"):
        return verbo + "es"
    if re.search(r"[^aeiou]y$", verbo):          # study -> studies
        return verbo[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh|o)$", verbo):    # watch -> watches
        return verbo + "es"
    return verbo + "s"


def _be(sujeto):
    """Conjuga 'to be' en presente para el sujeto dado (I am, he is, they are)."""
    sujeto = sujeto.lower()
    return "am" if sujeto == "i" else ("is" if sujeto in ("he", "she", "it") else "are")


def _be_pasado(sujeto):
    """Conjuga 'to be' en pasado (I/he was, we/they were)."""
    return "was" if sujeto.lower() in ("i", "he", "she", "it") else "were"


def _sugerir(regla, coincidencia):
    """Texto correcto de una regla: plantilla con ``\\1`` o función a medida.

    Si la función devuelve cadena vacía significa que la coincidencia era en
    realidad correcta (falso positivo de la regla) y no se avisa de nada.
    """
    sugerencia = regla.get("sugerencia", "")
    if callable(sugerencia):
        return (sugerencia(coincidencia) or "").strip()
    if not sugerencia:
        return ""
    return coincidencia.expand(sugerencia).strip()


# --------------------------------------------------------------------------
# Reglas de detección (fallos típicos de un hispanohablante)
# --------------------------------------------------------------------------
# Cada regla lleva: 'clave' (identificador que se guarda en el estado), 'titulo'
# (nombre del error), 'patron' (regex), 'sugerencia' (lo correcto: plantilla con
# \1 o función que devuelve '' si no era un error) y 'explicacion' (el porqué).
# Con 'aviso': True se marca como recomendación de estilo, no como error.

#: Alternativas de pasado irregular sin 'was/were' (esos van con su propia regla).
_ALT_IRREGULARES = "|".join(clave for clave in IRREGULARES if clave not in ("was", "were"))
#: Alternativas de incontables de una palabra (sin 'news', que sí es válida).
_ALT_INCONTABLES = "|".join(clave for clave in INCONTABLES if clave != "news")


def _sugerir_be_pasado(coincidencia):
    """'I didn't was there' -> 'I wasn't there' (la negación va en el propio be)."""
    base = _be_pasado(coincidencia.group(1))
    verbo = coincidencia.group(2).lower()
    negacion = "n't" if verbo.endswith("n't") else (" not" if "not" in verbo else "")
    return f"{coincidencia.group(1)} {base}{negacion}"


def _sugerir_a_vocal(coincidencia):
    """'a orange' -> 'an orange'. Devuelve '' cuando la regla se equivoca.

    'a university' o 'a euro' empiezan por vocal escrita pero por sonido
    consonántico, así que ahí no hay nada que corregir.
    """
    palabra = coincidencia.group(1)
    excepciones = ("uni", "use", "user", "usual", "euro", "one", "once", "ufo", "eu", "ut")
    if palabra[:1].lower() not in "aeiou" or palabra.lower().startswith(excepciones):
        return ""
    return f"an {palabra}"


def _cantidad(numero, singular, plural):
    """'1 ejercicio' / '3 ejercicios': el encargo también se lee bien en singular."""
    return f"{numero} {singular if int(numero) == 1 else plural}"


REGLAS = (
    {
        "clave": "verbo_be_edad",
        "titulo": "La edad va con 'to be'",
        "patron": r"\b(i|you|we|they|he|she|it)\s+(have|has|had)\s+(\d{1,2})\s+years\b(?!\s+of)",
        "sugerencia": lambda m: (f"{m.group(1)} {_be_pasado(m.group(1)) if m.group(2) == 'had' else _be(m.group(1))}"
                                 f" {m.group(3)} years old"),
        "explicacion": "En español 'tener 30 años', pero en inglés la edad se dice con 'to be': "
                       "'I am 30 years old', 'she is 25'. 'I have 30 years' solo se usa con cosas "
                       "(un coche que tiene 30 años).",
    },
    {
        "clave": "estado_con_have",
        "titulo": "Hambre, frío o sueño van con 'to be'",
        "patron": r"\b(i|you|we|they|he|she|it)\s+(have|has)\s+(" + "|".join(ESTADOS_CON_BE) + r")\b",
        "sugerencia": lambda m: f"{m.group(1)} {_be(m.group(1))} {m.group(3)}",
        "explicacion": "'I have hungry' es un calco de 'tengo hambre'. En inglés se describe con 'to be': "
                       "'I am hungry', 'I am cold', 'he is tired'. Se usa 'have' solo si es algo que se posee.",
    },
    {
        "clave": "people_concordancia",
        "titulo": "'People' es plural",
        "patron": r"\b(people|persons)\s+(is|was|has|does|doesn't|wasn't)\b",
        "sugerencia": lambda m: "people " + {"is": "are", "was": "were", "has": "have",
                                             "does": "do", "doesn't": "don't",
                                             "wasn't": "weren't"}[m.group(2).lower()],
        "explicacion": "'People' significa 'personas' y ya es plural, así que va con 'are/were/have/do': "
                       "'People are friendly'. Para una sola persona: 'a person'.",
    },
    {
        "clave": "tercera_persona_s",
        "titulo": "Falta la -s de la tercera persona",
        "patron": r"\b(he|she|it)\s+(" + VERBOS_TERCERA + r")\b",
        "sugerencia": lambda m: f"{m.group(1)} {_conjugar_tercera(m.group(2))}",
        "explicacion": "En presente simple, con he/she/it el verbo lleva -s: 'he works', 'she goes', 'it costs'. "
                       "Es el error número uno del hispanohablante porque en español el verbo casi no cambia.",
    },
    {
        "clave": "tercera_negacion",
        "titulo": "Negación con 'he/she/it'",
        "patron": r"\b(he|she|it)\s+(don't|do\s+not|donot)\b",
        "sugerencia": r"\1 doesn't",
        "explicacion": "Con he/she/it el auxiliar es 'does', así que la negación es 'doesn't': "
                       "'he doesn't work'. 'He don't work' es incorrecto aunque se oiga en canciones.",
    },
    {
        "clave": "did_pasado",
        "titulo": "Tras 'did' el verbo va en infinitivo",
        "patron": r"\b(did|didn't|did\s+not)\s+(" + _ALT_IRREGULARES + r")\b",
        "sugerencia": lambda m: f"{m.group(1)} {IRREGULARES[m.group(2).lower()]}",
        "explicacion": "'Did' ya marca el pasado, así que el verbo que le sigue vuelve a la forma base: "
                       "'I didn't go', no 'I didn't went'. El pasado se marca una sola vez.",
    },
    {
        "clave": "did_was",
        "titulo": "El pasado de 'to be' no lleva 'did'",
        "patron": r"\b(i|you|he|she|it|we|they)\s+(did|didn't|did\s+not)\s+(was|were)\b",
        "sugerencia": _sugerir_be_pasado,
        "explicacion": "'Was/were' ya son pasado y no necesitan 'did': 'I wasn't there' "
                       "(nunca 'I didn't was there').",
    },
    {
        "clave": "doble_negacion",
        "titulo": "Doble negación",
        "patron": r"\b(don't|doesn't|didn't|can't|won't|isn't|aren't|never|no)\b[^.!?;]{0,40}?"
                  r"\b(nothing|nobody|nowhere|no one|none)\b",
        "sugerencia": lambda m: (f"{m.group(1)} ... " +
                                 {"nothing": "anything", "nobody": "anybody", "nowhere": "anywhere",
                                  "no one": "anyone", "none": "any"}[m.group(2).lower()]),
        "explicacion": "En inglés basta una negación: 'I don't know anything' (no 'I don't know nothing'). "
                       "Después de don't/never la palabra es 'anything/anybody/anywhere'.",
    },
    {
        "clave": "how_i_can",
        "titulo": "Orden del auxiliar en la pregunta",
        "patron": r"\bhow\s+(i|we|you|he|she|they)\s+(can|do|should|could|would|must|will|did|are|is)\b",
        "sugerencia": lambda m: f"how {m.group(2)} {m.group(1)}",
        "explicacion": "En las preguntas el auxiliar va antes del sujeto: 'How can I help you?', "
                       "no 'How I can help you?'. El orden del español ('cómo puedo yo…') no sirve.",
    },
    {
        "clave": "explain_me",
        "titulo": "'explain' necesita 'to'",
        "patron": r"\bexplain(ed|s)?\s+(me|us|him|her|them)\b",
        "sugerencia": lambda m: f"explain{m.group(1) or ''} to {m.group(2)}",
        "explicacion": "'Explain', 'say' y 'describe' no llevan objeto indirecto directo: necesitan 'to' "
                       "('explain to me', 'say to me'). En cambio 'tell me' y 'show me' van sin 'to'.",
    },
    {
        "clave": "say_me",
        "titulo": "'dime' es 'tell me'",
        "patron": r"\bsay\s+(me|us|him|her|them)\b",
        "sugerencia": lambda m: f"tell {m.group(1)}",
        "explicacion": "'Say' no lleva persona directamente: se dice 'tell me', 'tell us', 'tell him'. "
                       "Usa 'say' cuando repites lo que alguien dijo: 'He said hello', 'she says it's fine'.",
    },
    {
        "clave": "listen_me",
        "titulo": "'listen' necesita 'to'",
        "patron": r"\blisten\s+(me|us|him|her|them)\b",
        "sugerencia": r"listen to \1",
        "explicacion": "'Listen' siempre va con 'to' cuando dices a quién escuchas: 'Listen to me', "
                       "'she listens to music'. Sin 'to' solo se usa para llamar la atención: 'Listen!'",
    },
    {
        "clave": "wait_me",
        "titulo": "'wait' necesita 'for'",
        "patron": r"\bwait(s|ed|ing)?\s+(me|us|him|her|them)\b",
        "sugerencia": lambda m: f"wait{m.group(1) or ''} for {m.group(2)}",
        "explicacion": "'Esperar a alguien' es 'wait for someone': 'Wait for me', 'I'm waiting for you'. "
                       "'Wait for' + persona; 'wait' solo, para decir 'espera un momento'.",
    },
    {
        "clave": "ask_to",
        "titulo": "'ask' no lleva 'to'",
        "patron": r"\bask(s|ed|ing)?\s+to\s+(me|us|him|her|them)\b",
        "sugerencia": lambda m: f"ask{m.group(1) or ''} {m.group(2)}",
        "explicacion": "'Preguntar a alguien' es 'ask someone': 'She asked me a question'. El 'to' solo "
                       "aparece cuando preguntas a alguien *por* algo: 'ask to speak with the manager'.",
    },
    {
        "clave": "depend_of",
        "titulo": "'depend on', no 'depend of'",
        "patron": r"\bdepend(s|ed|ing)?\s+of\b",
        "sugerencia": lambda m: f"depend{m.group(1) or ''} on",
        "explicacion": "'Depender de' se traduce con 'on': 'It depends on the weather'. Lo mismo con "
                       "'in on / concentrate on / rely on'.",
    },
    {
        "clave": "married_with",
        "titulo": "'married to', no 'married with'",
        "patron": r"\b(married|marry|marries|marrying)\s+with\b",
        "sugerencia": lambda m: f"{'married' if m.group(1) == 'married' else 'marry'} to",
        "explicacion": "'Casado con alguien' es 'married to someone': 'She is married to Tom'. "
                       "'With' se usa para acompañar: 'I went with my husband'.",
    },
    {
        "clave": "in_dia",
        "titulo": "Los días van con 'on'",
        "patron": r"\bin\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        "sugerencia": r"on \1",
        "explicacion": "Fechas y días con 'on' ('on Monday', 'on 5 May'); meses, años y partes del día con 'in' "
                       "('in January', 'in the morning'); horas con 'at' ('at 9')",
    },
    {
        "clave": "in_fin_semana",
        "titulo": "El fin de semana va con 'on'",
        "patron": r"\bin\s+the\s+weekend\b",
        "sugerencia": "on the weekend (en inglés británico: at the weekend)",
        "explicacion": "El fin de semana se dice 'on the weekend' (EE. UU.) o 'at the weekend' (Reino Unido), "
                       "nunca 'in the weekend'.",
    },
    {
        "clave": "on_mes",
        "titulo": "Los meses van con 'in'",
        "patron": r"\bon\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        "sugerencia": r"in \1",
        "explicacion": "Los meses se acompañan de 'in': 'in July', 'in December'. Con el día completo sí se usa 'on': "
                       "'on 5 July'.",
    },
    {
        "clave": "since_duracion",
        "titulo": "'for' + duración, 'since' + momento",
        "patron": (r"\bsince\s+(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                   r"a few|a couple|few|several|many)\s+"
                   r"(years?|months?|weeks?|days?|hours?|minutes?)\b"),
        "sugerencia": lambda m: f"for {m.group(1)} {m.group(2)}",
        "explicacion": "'For' mide cuánto tiempo dura ('for three years'); 'since' señala el momento en que empezó "
                       "('since 2020', 'since Monday'). 'Since three years' mezcla las dos cosas.",
    },
    {
        "clave": "for_to",
        "titulo": "El infinitivo de finalidad no lleva 'for'",
        "patron": r"\bfor\s+to\s+([a-z]+)\b",
        "sugerencia": r"to \1",
        "explicacion": "'Para hacer algo' en inglés es 'to + verbo': 'I called to ask a question'. El 'for' del "
                       "'para' español no se traduce delante del verbo; solo va con sustantivos ('for work').",
    },
    {
        "clave": "go_to_home",
        "titulo": "'home' sin 'to'",
        "patron": r"\b(go|goes|going|went|come|comes|coming|came)\s+to\s+(home|bed)\b",
        "sugerencia": r"\1 \2",
        "explicacion": "'Home' y 'bed' funcionan como adverbio con go/come: 'I go home', 'go to bed'. "
                       "Con 'to' se dice 'go to my house', 'go to the office'.",
    },
    {
        "clave": "modal_to",
        "titulo": "Los modales no llevan 'to'",
        "patron": r"\b(can|could|may|might|must|should|will|would|shall)\s+to\s+([a-z]+)\b",
        "sugerencia": r"\1 \2",
        "explicacion": "Detrás de un modal el verbo va sin 'to': 'I must go', 'she can swim'. "
                       "La única excepción es 'have to' / 'ought to'.",
    },
    {
        "clave": "much_people",
        "titulo": "'many' con lo que se cuenta",
        "patron": r"\b(so|too|very|how|as)\s+much\s+(people|things|friends|books|cars|years|days|times|"
                  r"options|ideas|questions|messages|emails)\b",
        "sugerencia": lambda m: f"{m.group(1)} many {m.group(2)}",
        "explicacion": "'Many' acompaña a lo que se cuenta ('many people', 'many books'); 'much' a lo que no se "
                       "cuenta ('much time', 'much money', 'much water').",
    },
    {
        "clave": "very_verbo",
        "titulo": "'very' no modifica verbos",
        "patron": r"\bvery\s+(like|love|want|need|hate|enjoy|miss|prefer)\b",
        "sugerencia": r"really \1",
        "explicacion": "'Very' va con adjetivos ('very good'), pero con verbos se usa 'really' o 'a lot': "
                       "'I really like it' / 'I like it a lot'.",
    },
    {
        "clave": "doble_comparativo",
        "titulo": "Comparativo doble",
        "patron": r"\bmore\s+(better|worse|bigger|smaller|easier|harder|faster|slower|cheaper|happier|"
                  r"stronger|older|younger|longer|shorter|higher|lower|nicer)\b",
        "sugerencia": r"\1",
        "explicacion": "Los comparativos cortos ya llevan '-er' ('better', 'bigger'), no necesitan 'more'. "
                       "'More' se usa con los largos: 'more expensive', 'more interesting'.",
    },
    {
        "clave": "doble_superlativo",
        "titulo": "Superlativo doble",
        "patron": r"\b(the\s+)?most\s+(best|worst)\b",
        "sugerencia": lambda m: f"the {'best' if m.group(2).lower() == 'best' else 'worst'}",
        "explicacion": "'Best' y 'worst' ya son superlativos: 'the best film', no 'the most best film'.",
    },
    {
        "clave": "everyday",
        "titulo": "'every day' (dos palabras)",
        "patron": r"\beveryday\b",
        "sugerencia": "every day",
        "explicacion": "'Every day' (dos palabras) significa 'todos los días'. 'Everyday' junto es un adjetivo "
                       "que significa 'cotidiano': 'everyday life' = la vida diaria.",
    },
    {
        "clave": "i_agree",
        "titulo": "'estar de acuerdo' es 'agree'",
        "patron": r"\b(i|we|they|you)\s+(am|is|are)\s+agree\b",
        "sugerencia": lambda m: f"{m.group(1)} agree",
        "explicacion": "'Agree' ya es el verbo, así que no lleva 'to be' delante: 'I agree with you'. "
                       "'I am agree' es un calco de 'estoy de acuerdo'.",
    },
    {
        "clave": "interesting_in",
        "titulo": "'interested in'",
        "patron": r"\b(i|he|she|we|they|you)\s+(am|is|are)\s+interesting\s+in\b",
        "sugerencia": lambda m: f"{m.group(1)} {_be(m.group(1))} interested in",
        "explicacion": "'Interested' describe cómo te sientes ('I am interested in art'); 'interesting' describe "
                       "la cosa que lo provoca ('the book is interesting').",
    },
    {
        "clave": "bored_estar",
        "titulo": "'bored' = aburrido (yo)",
        "patron": r"\b(i|he|she|we|they|you)\s+(am|is|are)\s+boring\b(?!\s+(film|book|class|meeting|task|job|"
                  r"conversation|talk|presentation|day|story|game|subject))",
        "sugerencia": lambda m: f"{m.group(1)} {_be(m.group(1))} bored",
        "explicacion": "'I am boring' significa 'soy aburrido' (aburro a los demás). Si estás aburrido tú, "
                       "es 'I am bored'.",
    },
    {
        "clave": "how_called",
        "titulo": "'¿Cómo se llama…?' es 'What is it called?'",
        "patron": r"\bhow\s+(is|are)\s+(?:(it|he|she|they|this|that)\s+)?called\b",
        "sugerencia": lambda m: f"what {m.group(1).lower()} {m.group(2) or 'it'} called",
        "explicacion": "Para preguntar el nombre se usa 'what': 'What is it called?', 'What's your name?'. "
                       "El 'how' del español ('¿cómo se llama?') es 'what' en inglés.",
    },
    {
        "clave": "make_question",
        "titulo": "'hacer una pregunta' es 'ask'",
        "patron": r"\b(make|makes|made|making|do|does|did|doing)\s+(me\s+|him\s+|her\s+|them\s+)?a\s+question\b",
        "sugerencia": lambda m: f"ask {m.group(2) or ''}a question".strip(),
        "explicacion": "Las preguntas se 'ask' en inglés ('ask a question', 'ask me a question'). "
                       "'Make a question' es un calco de 'hacer una pregunta'.",
    },
    {
        "clave": "take_decision",
        "titulo": "'tomar una decisión' es 'make'",
        "patron": r"\btake\s+(a|the|my|your|his|her)\s+decision\b",
        "sugerencia": r"make \1 decision",
        "explicacion": "Las decisiones y los errores se 'make': 'make a decision', 'make a mistake'. "
                       "'Take' se queda con 'take a photo', 'take a break', 'take a shower'.",
    },
    {
        "clave": "news_singular",
        "titulo": "'news' va en singular",
        "patron": r"\bnews\s+(are|were|have)\b",
        "sugerencia": lambda m: "news " + {"are": "is", "were": "was", "have": "has"}[m.group(1).lower()],
        "explicacion": "'News' termina en -s pero es singular: 'The news is good'. "
                       "Para una sola noticia: 'a piece of news'.",
    },
    {
        "clave": "incontables",
        "titulo": "Plural en un incontable",
        "patron": r"\b(" + _ALT_INCONTABLES + r")\b",
        "sugerencia": lambda m: INCONTABLES[m.group(1).lower()],
        "explicacion": "'Information', 'advice', 'equipment' o 'software' no se cuentan en inglés: no llevan -s "
                       "('some information', 'a piece of advice').",
    },
    {
        "clave": "ortografia",
        "titulo": "Ortografía de la palabra",
        "patron": _PATRON_ORTOGRAFIA,
        "sugerencia": lambda m: ORTOGRAFIA[m.group(1).lower()],
        "explicacion": "La palabra se escribe siempre así; se aprende por la forma, no por el sonido. "
                       "Escribirla bien un par de veces es lo más rápido para no volver a fallar.",
    },
    {
        "clave": "its_it_is",
        "titulo": "'it's' (es) frente a 'its' (su)",
        "patron": r"\bits\s+(a|an|not|very|important|good|bad|the|better|possible|time|ok|true|false|"
                  r"correct|wrong|easy|hard|difficult|my|your)\b",
        "sugerencia": r"it's \1",
        "explicacion": "'It's' = 'it is' ('it's important'); 'its' = 'su' (de una cosa): 'the dog and its ball'. "
                       "Si dudas, lee 'it is': si suena bien, lleva apóstrofo.",
    },
    {
        "clave": "your_welcome",
        "titulo": "'you're welcome'",
        "patron": r"\byour\s+welcome\b",
        "sugerencia": "you're welcome",
        "explicacion": "'You're' = 'you are' ('you're welcome' = 'de nada'); 'your' es posesivo ('your house').",
    },
    {
        "clave": "i_mayuscula",
        "titulo": "'I' siempre en mayúscula",
        "patron": r"\bi\b",
        "sensible": True,
        "aviso": True,
        "sugerencia": "I",
        "explicacion": "El pronombre 'I' se escribe siempre en mayúscula, incluso en medio de la frase: "
                       "'Yesterday I went home'. Es la única palabra del inglés que lo hace siempre.",
    },
)

#: Reglas con su expresión compilada. 'i_mayuscula' se compila sin ignorar
#: mayúsculas a propósito: solo tiene que avisar de la 'i' minúscula.
_REGLAS_COMPILADAS = tuple(
    (regla, re.compile(regla["patron"], 0 if regla.get("sensible") else re.IGNORECASE))
    for regla in REGLAS
)


class EnglishTutor:
    """Tutor de inglés: detecta fallos, prepara la clase y recuerda el avance.

    El trabajo pesado (explicar y redactar) lo hace la IA: este objeto prepara el
    prompt con el nivel del alumno, lo que ha fallado y lo que se repite, y
    devuelve ``MARCA_TUTOR + encargo`` para que el apartado «Clase de inglés» de
    la ventana lo pida al cerebro con el prompt de profesor. La detección de
    errores, en cambio, es local: así funciona aunque no haya conexión ni API Key
    y no se gasta ninguna llamada.
    """

    def __init__(self, config_path=rutas.CONFIG_USUARIO, carpeta=rutas.INGLES):
        self.config_path = config_path
        self.carpeta = carpeta
        os.makedirs(self.carpeta, exist_ok=True)

    # ------------------------------------------------------------------
    # Estado (nivel, prácticas y errores repetidos)
    # ------------------------------------------------------------------
    def _ruta_estado(self):
        """Archivo donde se guarda el avance del alumno."""
        return os.path.join(self.carpeta, "estado.json")

    def _leer_estado(self):
        """Estado del alumno con los valores por defecto ya rellenados."""
        estado = {"nivel": NIVEL_POR_DEFECTO, "practicas": 0, "desde": "", "errores": {}, "temas": []}
        try:
            with open(self._ruta_estado(), "r", encoding="utf-8") as archivo:
                guardado = json.load(archivo)
            if isinstance(guardado, dict):
                estado.update({clave: valor for clave, valor in guardado.items() if valor is not None})
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
        """Guarda el avance del alumno (a prueba de fallos: nunca rompe el chat)."""
        try:
            os.makedirs(self.carpeta, exist_ok=True)
            with open(self._ruta_estado(), "w", encoding="utf-8") as archivo:
                json.dump(estado, archivo, ensure_ascii=False, indent=2)
        except OSError as error:
            print(f"No se pudo guardar el progreso de inglés: {error}")

    def nivel(self):
        """Nivel actual del alumno (A1-C2)."""
        return self._leer_estado()["nivel"]

    def fijar_nivel(self, texto):
        """Fija el nivel a partir de lo que diga el usuario ('nivel B2', 'avanzado').

        Devuelve el mensaje de confirmación (o de ayuda si no se entiende).
        """
        texto = (texto or "").strip()
        buscado = ""
        for nivel in NIVELES:                       # 'B2', 'b2' o 'nivel b2'
            if re.search(rf"\b{nivel}\b", texto, re.IGNORECASE):
                buscado = nivel
                break
        if not buscado:
            minusculas = texto.lower()
            for palabra, nivel in NIVELES_EN_PALABRAS.items():
                if palabra in minusculas:
                    buscado = nivel
                    break
        if not buscado:
            return ("No sé con qué nivel quedarme. Dime uno entre A1, A2, B1, B2, C1 y C2 "
                    "(por ejemplo: 'nivel B2') y corrijo y explico con esa dificultad.")
        estado = self._leer_estado()
        anterior = estado["nivel"]
        estado["nivel"] = buscado
        self._guardar_estado(estado)
        if anterior == buscado:
            return (f"Tu nivel ya era {buscado}. Sigo explicando y corrigiendo con esa dificultad.\n\n"
                    f"Puedes practicar ahora con 'corrige esto: <frase en inglés>' o 'ponme ejercicios de {buscado}'.")
        return (f"Nivel actualizado: {anterior} → {buscado}.\n\n"
                f"A partir de ahora corrijo y explico con la dificultad de {buscado}. "
                "Puedes comprobarlo escribiendo cualquier frase en inglés.")

    def _registrar_practica(self, estado, resumen):
        """Apunta una práctica nueva y guarda solo los últimos eventos."""
        estado["practicas"] = int(estado.get("practicas") or 0) + 1
        if not estado.get("desde"):
            estado["desde"] = datetime.now().strftime("%Y-%m-%d")
        temas = estado["temas"]
        temas.append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "resumen": resumen[:120]})
        estado["temas"] = temas[-MAX_EVENTOS:]

    def registrar(self, detecciones, resumen="práctica"):
        """Suma los errores detectados al historial y cuenta la práctica."""
        estado = self._leer_estado()
        for deteccion in detecciones or []:
            clave = deteccion["clave"]
            datos = estado["errores"].get(clave) or {"veces": 0}
            datos["veces"] = int(datos.get("veces") or 0) + 1
            datos["titulo"] = deteccion["titulo"]
            datos["ejemplo"] = deteccion["encontrado"][:120]
            datos["correccion"] = deteccion["sugerencia"][:120]
            datos["fecha"] = datetime.now().strftime("%Y-%m-%d")
            estado["errores"][clave] = datos
        self._registrar_practica(estado, resumen)
        self._guardar_estado(estado)

    def frecuentes(self, cuantos=MAX_MEMORIA):
        """Errores más repetidos: ``[(clave, datos), ...]`` de más a menos fallos."""
        errores = self._leer_estado()["errores"]
        ordenados = sorted(errores.items(),
                           key=lambda elemento: (-int(elemento[1].get("veces") or 0), elemento[0]))
        return ordenados[:cuantos]

    def resumen(self):
        """Cabecera del alumno para el apartado de inglés, en datos sueltos.

        Devuelve ``{'nivel', 'practicas', 'desde', 'repetidos'}``: lo justo para
        enseñar en una línea cómo va (nivel, prácticas y lo que más se le repite)
        sin tener que leer el texto largo de `progreso()`.
        """
        estado = self._leer_estado()
        return {
            "nivel": estado["nivel"],
            "practicas": int(estado.get("practicas") or 0),
            "desde": estado.get("desde") or "",
            "repetidos": self.frecuentes(),
        }

    # ------------------------------------------------------------------
    # Detección local de errores (sin IA)
    # ------------------------------------------------------------------
    def detectar(self, texto):
        """Errores conocidos que hay en ``texto`` (sin IA y sin internet).

        Devuelve una lista de diccionarios con 'clave', 'titulo', 'encontrado',
        'sugerencia', 'explicacion' y 'aviso'. Se queda con la primera
        coincidencia de cada regla: así el alumno arregla el patrón de una vez en
        lugar de ver treinta veces el mismo aviso.
        """
        texto = (texto or "")[:MAX_TEXTO]
        detecciones = []
        for regla, patron in _REGLAS_COMPILADAS:
            coincidencia = patron.search(texto)
            if not coincidencia:
                continue
            sugerencia = _sugerir(regla, coincidencia)
            if not sugerencia:              # la regla se equivocaba: era correcto
                continue
            detecciones.append({
                "clave": regla["clave"],
                "titulo": regla["titulo"],
                "encontrado": coincidencia.group(0).strip(),
                "sugerencia": sugerencia,
                "explicacion": regla["explicacion"],
                "aviso": bool(regla.get("aviso")),
            })
        return detecciones

    # ------------------------------------------------------------------
    # Bloques de texto que se le pasan a la IA
    # ------------------------------------------------------------------
    def _pistas(self, detecciones):
        """Errores ya detectados en local, con su motivo, para que la IA no falle."""
        if not detecciones:
            return ""
        lineas = ["ERRORES DETECTADOS POR EL ANALIZADOR LOCAL (ya comprobados, son seguros):"]
        for numero, deteccion in enumerate(detecciones[:MAX_PISTAS], 1):
            etiqueta = "recomendación" if deteccion["aviso"] else "error"
            lineas.append(f"{numero}. ({etiqueta}) {deteccion['titulo']}: «{deteccion['encontrado']}» → "
                          f"«{deteccion['sugerencia']}». Motivo: {deteccion['explicacion']}")
        lineas.append("Trata estos puntos en la corrección y añade los que veas tú y no estén en la lista.")
        return "\n".join(lineas)

    def _memoria(self, cuantos=MAX_MEMORIA):
        """Errores que el alumno repite de prácticas anteriores."""
        repetidos = self.frecuentes(cuantos)
        if not repetidos:
            return ""
        lineas = ["ERRORES QUE ESTE ALUMNO REPITE (de sus prácticas anteriores):"]
        for clave, datos in repetidos:
            lineas.append(f"- {datos.get('titulo') or clave}: {datos.get('veces', 0)} vez/veces "
                          f"(último ejemplo: «{datos.get('ejemplo', '')}» → «{datos.get('correccion', '')}»)")
        lineas.append("Si vuelven a aparecer, dilo sin rodeos: ya se le avisó antes.")
        return "\n".join(lineas)

    def _temas(self, estado):
        """Últimas prácticas hechas, para no repetir la misma clase."""
        eventos = estado.get("temas") or []
        if not eventos:
            return ""
        return ("ÚLTIMAS PRÁCTICAS (no repitas los mismos ejercicios ni los mismos ejemplos): " +
                "; ".join(evento.get("resumen", "") for evento in eventos[-5:]))

    @staticmethod
    def _bloques(*partes):
        """Une los bloques de un prompt saltándose los vacíos."""
        return "\n\n".join(parte for parte in partes if parte)

    def _pedir(self, estado, cuerpo):
        """Devuelve el encargo con la marca del tutor y el nivel del alumno delante."""
        cabecera = (f"El alumno es hispanohablante y su nivel actual de inglés es {estado['nivel']}. "
                    "Explícale todo en español, con el inglés como idioma que practica.")
        return f"{MARCA_TUTOR}{cabecera}\n\n{cuerpo}"

    @staticmethod
    def _entero(texto, defecto, minimo=1, maximo=MAX_EJERCICIOS):
        """Número pedido por el usuario ('5', 'cinco ejercicios') con topes."""
        coincidencia = re.search(r"\b(\d{1,2})\b", str(texto or ""))
        if not coincidencia:
            return defecto
        return max(minimo, min(maximo, int(coincidencia.group(1))))

    # ------------------------------------------------------------------
    # Tareas del tutor
    # ------------------------------------------------------------------
    def corregir(self, texto):
        """Corrige lo que ha escrito el alumno y le explica cada punto."""
        texto = (texto or "").strip()
        if not texto:
            return ("Escribe en inglés la frase o el texto que quieres que te corrija y te explico cada punto "
                    "paso a paso. Puedes decir, por ejemplo: «practica con esto: yesterday i go to the office "
                    "and my boss say me that the report don't be ready».")
        estado = self._leer_estado()
        detecciones = self.detectar(texto)
        self.registrar(detecciones, f"corrección de: {texto}")
        cuerpo = self._bloques(
            "TAREA: corregir el texto que acaba de escribir el alumno y enseñarle cada error paso a paso.",
            "TEXTO DEL ALUMNO:\n««\n" + texto[:MAX_TEXTO] + "\n»»",
            self._pistas(detecciones),
            self._memoria(),
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## ✅ Versión corregida\n"
            "El texto ya bien escrito (solo el texto, sin comentarios), conservando lo que quiso decir.\n"
            "## 🔍 Punto por punto\n"
            "Un punto por error, numerado, con este formato: **N. lo que escribió → lo que se dice**, y debajo, "
            "en una o dos frases, por qué estaba mal y cuándo se usa la forma correcta. Si algo está bien pero se "
            "puede decir mejor, indícalo al final de este apartado como mejora, no como error.\n"
            "Si el texto no tiene ningún error, dilo claro y explica qué está bien y qué se puede mejorar.\n"
            "## 📚 Para entenderlo\n"
            "Las 2 o 3 reglas de fondo que fallan, una por apartado: la regla, un ejemplo nuevo y su traducción. "
            "Usa palabras llanas; si empleas un término gramatical, acláralo en una frase.\n"
            "## ✍️ Practica\n"
            "3 ejercicios cortos sobre esos mismos puntos (con un hueco para rellenar) y, debajo, las soluciones "
            "explicadas una a una.\n"
            "No inventes errores que no estén en el texto ni cambies el sentido de lo que quiso decir.",
        )
        return self._pedir(estado, cuerpo)

    def explicar(self, tema):
        """Explica un punto de inglés desde cero y paso a paso."""
        tema = (tema or "").strip()
        if not tema:
            return ("Dime qué punto de inglés quieres que te explique paso a paso (por ejemplo: «el presente "
                    "perfecto», «cuándo se usa do y cuándo make», «la diferencia entre since y for»).")
        estado = self._leer_estado()
        cuerpo = self._bloques(
            f"TAREA: explicar paso a paso este punto de inglés: «{tema}».",
            "El alumno quiere entenderlo de verdad, no una lista de reglas: explícalo como si empezara de cero y "
            "supiera poco vocabulario técnico.",
            self._memoria(4),
            self._temas(estado),
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## 🧩 Qué es y para qué sirve\n"
            "En dos o tres frases, con la traducción del concepto al español.\n"
            "## 🏗️ Cómo se forma\n"
            "La estructura paso a paso (sujeto, verbo, terminaciones...), con una tabla si ayuda a verlo.\n"
            "## 🇬🇧 Ejemplos\n"
            "5 frases en inglés de la vida diaria, cada una con su traducción. Marca en negrita la parte que "
            "enseña el punto.\n"
            "## ⚠️ Los errores típicos de un hispanohablante\n"
            "Los 3 fallos más habituales con este punto, cada uno con el porqué y su versión correcta.\n"
            "## 🧠 Cómo recordarlo\n"
            "Una regla de bolsillo o un truco para decidirlo sobre la marcha.\n"
            "## ✍️ Compruébalo\n"
            "3 ejercicios cortos ordenados de fácil a difícil y, debajo, las soluciones explicadas.",
        )
        return self._pedir(estado, cuerpo)

    def practicar(self, tema="", cantidad=""):
        """Prepara ejercicios para practicar (de un tema o de lo que más falla)."""
        tema = (tema or "").strip()
        cuantos = self._entero(cantidad, EJERCICIOS_POR_DEFECTO)
        estado = self._leer_estado()
        repetidos = self.frecuentes()
        objetivo = (f"TAREA: preparar {_cantidad(cuantos, 'ejercicio', 'ejercicios')} para practicar esto: «{tema}»."
                    if tema else
                    f"TAREA: preparar {_cantidad(cuantos, 'ejercicio', 'ejercicios')} sobre lo que más le falla y, "
                    "si no hay errores registrados, sobre lo que suele costar a un hispanohablante en ese nivel.")
        cuerpo = self._bloques(
            objetivo,
            self._memoria(),
            self._temas(estado),
            "Los ejercicios deben ser distintos entre sí y de tipos variados: completar la frase, ordenar las "
            "palabras, traducir del español, elegir la opción correcta y arreglar la frase que está mal. "
            "Indica el tipo en cada uno y usa vocabulario de la vida diaria y del trabajo.",
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## 🎯 Ejercicios\n"
            "La lista numerada, sin soluciones a la vista.\n"
            "## ✅ Soluciones explicadas\n"
            "La solución de cada ejercicio con su número y, debajo, por qué es esa y no otra (y otras formas "
            "válidas si las hay).\n"
            "## 📌 Lo que hay que recordar\n"
            "Dos o tres frases con la regla que resuelve estos ejercicios.\n"
            "## ➡️ Siguiente paso\n"
            "Una frase diciendo con qué conviene seguir.",
        )
        if repetidos:
            cuerpo = self._bloques(cuerpo, "Al menos la mitad de los ejercicios deben tocar los errores "
                                           "repetidos que aparecen arriba.")
        self.registrar([], f"ejercicios{f': {tema}' if tema else ''} ({cuantos})")
        return self._pedir(estado, cuerpo)

    def conversar(self, mensaje):
        """Mantiene una conversación en inglés y corrige lo que diga el alumno."""
        mensaje = (mensaje or "").strip()
        if not mensaje:
            return ("Escríbeme algo en inglés (una frase, una pregunta, lo que has hecho hoy...) y te contesto "
                    "en inglés para seguir la conversación, corrigiéndote y explicándote lo que cambie.")
        estado = self._leer_estado()
        detecciones = self.detectar(mensaje)
        self.registrar(detecciones, f"conversación: {mensaje}")
        cuerpo = self._bloques(
            "TAREA: mantener una conversación real en inglés con el alumno y, al mismo tiempo, enseñarle lo "
            "que ha dicho mal.",
            "LO QUE HA DICHO EL ALUMNO:\n««\n" + mensaje[:MAX_TEXTO] + "\n»»",
            self._pistas(detecciones),
            self._memoria(),
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## 💬 Mi respuesta\n"
            "En inglés, natural y del nivel del alumno (2-4 frases), y termina con una pregunta para que siga "
            "hablando. No es un examen: es una conversación.\n"
            "## 🔍 Cómo lo has dicho\n"
            "Su mensaje ya corregido en inglés y, debajo, los puntos a corregir numerados (**N. lo que escribió → "
            "lo que se dice**), cada uno con el porqué en una o dos frases. Si no hay errores, dilo.\n"
            "## 🗣️ Cómo decirlo mejor\n"
            "Dos formas más naturales de decir lo mismo, con su traducción, para ganar soltura.\n"
            "## 🇪🇸 Traducción\n"
            "La traducción de tu respuesta al español, para que quede claro qué le has dicho.\n"
            "## ➡️ Tu turno\n"
            "La pregunta que le haces, traducida, y 3 expresiones útiles para responderla (con su significado).",
        )
        return self._pedir(estado, cuerpo)

    def speaking(self, mensaje="", tema=""):
        """Prepara la charla hablada: el alumno habla y el tutor contesta en inglés.

        Es el modo «speaking» del apartado: la ventana pone el micrófono (dicta en
        inglés con `VoiceEngine.escuchar_ingles`), le pasa aquí lo que ha dicho el
        alumno y lee en voz alta la réplica —el apartado «Lo que digo yo», que va
        todo en inglés—. La corrección y la pronunciación quedan por escrito, en el
        panel, para poder verlas con calma. Sin mensaje, abre la conversación con
        una pregunta acorde al nivel (y al tema, si se escribe alguno).
        """
        mensaje = (mensaje or "").strip()
        tema = (tema or "").strip()
        estado = self._leer_estado()
        detecciones = self.detectar(mensaje)
        self.registrar(detecciones, f"speaking: {mensaje or tema or 'charla'}")
        cuerpo = self._bloques(
            "TAREA: mantener una charla HABLADA en inglés con el alumno (una clase de «speaking»): "
            "él va a hablar por el micrófono y tú le contestas en inglés y le corriges por escrito.",
            ("LO QUE ACABA DE DECIR EL ALUMNO (transcrito del micrófono, puede traer erratas del "
             "dictado):\n««\n" + mensaje[:MAX_TEXTO] + "\n»»" if mensaje else
             "EL ALUMNO TODAVÍA NO HA DICHO NADA: empieza tú la charla con una pregunta fácil, "
             "corta y de la vida diaria, para que conteste hablando."),
            (f"TEMA DE LA CHARLA: «{tema}»." if tema else ""),
            "Esto es una conversación hablada, no un examen: frases cortas, va coloquial y "
            "vocabulario del nivel del alumno (se tiene que entender de oído).",
            self._pistas(detecciones),
            self._memoria(),
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## 💬 Lo que digo yo\n"
            "Tu réplica **en inglés y solo en inglés** (2 o 3 frases), natural y de su nivel, y "
            "termina con una pregunta corta para que conteste en voz alta. Este apartado se lee "
            "en voz alta tal cual: nada de español, ni de notas, ni de asteriscos.\n"
            "## 🔍 Cómo lo has dicho\n"
            "Su frase ya corregida en inglés y, debajo, numerados (**N. lo que dijo → como se "
            "dice**), los puntos flojos con el porqué en una frase. Si no hay errores, dilo y "
            "señala una mejora para sonar más natural.\n"
            "## 🔊 Pronunciación\n"
            "Dos o tres palabras o sonidos de su frase que conviene cuidar al hablar, con una "
            "pista de pronunciación para un hispanohablante.\n"
            "## 🇪🇸 Qué te he dicho\n"
            "La traducción de tu réplica al español, para que sepa qué le has dicho.\n"
            "## ➡️ Te toca\n"
            "La pregunta que le haces, traducida, y 3 expresiones útiles para responderla (con "
            "su significado).",
        )
        return self._pedir(estado, cuerpo)

    def repaso(self, cantidad=""):
        """Repasa los errores que más se le repiten al alumno."""
        cuantos = self._entero(cantidad, EJERCICIOS_POR_DEFECTO)
        estado = self._leer_estado()
        repetidos = self.frecuentes()
        memoria = self._memoria()
        cuerpo = self._bloques(
            "TAREA: repasar con el alumno los fallos que se le repiten, sin volver a explicar la gramática "
            "desde cero: lo que necesita es fijar lo que ya le han explicado y volver a verlo por escrito.",
            memoria or ("No hay errores registrados todavía: elige los 4 fallos más típicos de un "
                        "hispanohablante en su nivel y haz un repaso general con ellos."),
            self._temas(estado),
            f"Responde con estos apartados y en este orden, en Markdown:\n"
            f"## 🔁 Repaso\n"
            f"Por cada error: el nombre del fallo, la regla en una sola frase y cómo se dice bien (con un ejemplo "
            f"corto en inglés). Máximo 6.\n"
            f"## ✍️ Ejercicios\n"
            f"{_cantidad(cuantos, 'ejercicio corto', 'ejercicios cortos')} mezclando esos fallos, sin soluciones "
            f"a la vista y numerados uno a uno.\n"
            f"## ✅ Soluciones\n"
            f"La solución de cada número con su explicación en una frase.\n"
            f"## 📌 Reglas de bolsillo\n"
            f"El resumen final, una línea por regla, con el formato «Situación → qué se dice».",
        )
        self.registrar([], f"repaso ({min(len(repetidos), 6)} errores)" )
        return self._pedir(estado, cuerpo)

    def vocabulario(self, tema="", cantidad=""):
        """Enseña vocabulario útil de un tema, con ejemplos y práctica."""
        tema = (tema or "").strip()
        cuantos = self._entero(cantidad, PALABRAS_POR_DEFECTO, maximo=MAX_PALABRAS)
        estado = self._leer_estado()
        cuerpo = self._bloques(
            (f"TAREA: enseñar vocabulario útil sobre «{tema}» apropiado para su nivel." if tema else
             "TAREA: enseñar vocabulario variado y útil del día a día apropiado para su nivel (no hace falta que "
             "sea de un tema técnico)."),
            self._temas(estado),
            f"Elige {_cantidad(cuantos, 'palabra o expresión', 'palabras o expresiones')} de uso real, evitando "
            "las demasiado básicas para su nivel.",
            "Responde con estos apartados y en este orden, en Markdown:\n"
            "## 📖 " + (f"Vocabulario: {tema}" if tema else "Vocabulario del día a día") + "\n"
            "Una tabla con estas columnas: **Inglés | Cómo se pronuncia | Significado | Ejemplo traducido**. "
            "En 'cómo se pronuncia' escribe la pronunciación aproximada para un hispanohablante entre corchetes.\n"
            "## 🧠 Cómo recordarlo\n"
            "Dos o tres trucos: palabras que van juntas (collocations) o familias de palabras que conviene "
            "aprender de una vez.\n"
            "## ✍️ Practica\n"
            "3 ejercicios cortos con ese vocabulario (uno de completar, uno de traducir y uno de escribir una "
            "frase libre) y, debajo, las soluciones.\n"
            "## ➡️ Para seguir\n"
            "5 palabras relacionadas que amplían el tema, solo con su significado.",
        )
        self.registrar([], f"vocabulario{f': {tema}' if tema else ''} ({cuantos})")
        return self._pedir(estado, cuerpo)

    def progreso(self, accion=""):
        """Resumen del avance al alumno (nivel, prácticas y errores repetidos).

        Con 'borrar' (o 'reiniciar') se limpia el historial de errores.
        """
        estado = self._leer_estado()
        if str(accion or "").strip().lower() in ("borrar", "reiniciar", "reset", "limpiar"):
            estado["errores"] = {}
            estado["temas"] = []
            self._guardar_estado(estado)
            return ("He borrado el historial de inglés (errores y prácticas); el nivel y la cuenta de prácticas "
                    "se mantienen. Empezamos de cero.")
        desde = f" (desde {estado['desde']})" if estado.get("desde") else ""
        lineas = [
            "🎓 Tutor de inglés",
            "",
            f"Nivel: {estado['nivel']} (de A1 a C2; se cambia diciendo «nivel B2»).",
            f"Prácticas: {estado.get('practicas') or 0}{desde}.",
        ]
        repetidos = self.frecuentes(8)
        if repetidos:
            lineas += ["", "Lo que más se te repite:"]
            for numero, (clave, datos) in enumerate(repetidos, 1):
                fecha = f", {datos['fecha']}" if datos.get("fecha") else ""
                lineas.append(f"{numero}. {datos.get('titulo') or clave} — {datos.get('veces', 0)} vez/veces "
                              f"(última: «{datos.get('ejemplo', '')}» → «{datos.get('correccion', '')}»{fecha})")
        else:
            lineas += ["", "Todavía no hay errores apuntados: escribe una frase en inglés («corrige: ...») o pide "
                           "ejercicios y empezamos a llevar la cuenta."]
        eventos = estado.get("temas") or []
        if eventos:
            lineas += ["", "Últimas prácticas:"]
            lineas += [f"· {evento.get('fecha', '')} · {evento.get('resumen', '')}" for evento in eventos[-5:]]
        lineas += ["", "Atajos: «repaso» (practicar lo que falla), «explícame <tema>», «ponme ejercicios de "
                       "<tema>», «hablemos en inglés» o «nivel C1»."]
        return "\n".join(lineas)
