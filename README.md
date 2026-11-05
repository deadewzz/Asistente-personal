emp# 🎙️ Jarvis — Asistente personal

Asistente de escritorio para **Windows** que combina **voz, chat y automatización del
sistema**. Escucha comandos por micrófono (o por texto), razona con un modelo de lenguaje
(DeepSeek) y ejecuta acciones reales: abrir programas, controlar el volumen, resumir el
portapapeles, leer correos, grabar reuniones, generar documentos y presentaciones,
buscar en la web, darte clase de inglés (en su propio apartado) y mucho más.

> Estado: **funcional**, en desarrollo activo.

---

## ✨ Características

### 🗣️ Voz
- **Reconocimiento de voz** con `SpeechRecognition` y **Whisper local**
  (`faster-whisper`) para mayor precisión offline.
- **Síntesis de voz** con `edge-tts` (voces neuronales) y `pyttsx3` (respaldo offline).
- **Clonación de voz** opcional mediante RVC.
- **Dictado**: escribe en cualquier aplicación lo que vas diciendo.

### 💬 Interfaz
- GUI moderna y oscura con `customtkinter`.
- **Aspecto cuidado**: paleta oscura **en capas** (fondo → panel → tarjeta → tarjeta
  elevada) con un único color de acento (turquesa neón) para los botones de acción,
  el nivel y los iconos; los paneles son tarjetas redondeadas con borde suave, y el
  panel activo —la caja de escritura, el apartado abierto, la tarjeta de la
  corrección— se enciende con un borde de brillo en el color de acento.
- **Todo con su icono**: cada mensaje del chat lleva su avatar y su nombre, cada
  conversación de la barra lateral su tarjeta (icono, fecha y resumen) y cada
  apartado de la clase su tarjeta con el icono que manda la IA.
- **Los mensajes del asistente se ven con su formato**: las respuestas llegan en
  Markdown y el chat las pinta de verdad —títulos y **negritas** en el color de
  acento, listas con su viñeta, citas, tablas y los bloques de código en
  monoespaciada sobre fondo oscuro—, así que ya no se leen los asteriscos. El texto
  de esa burbuja se puede seleccionar y copiar.
- **La caja de escritura crece hacia abajo**: el mensaje largo se lee entero en
  varias líneas (de una a siete; luego se desplaza por dentro) en lugar de irse
  hacia el lado. `Enter` envía y `Shift+Enter` hace un salto de línea.
- **Atajos de edición donde escribes**: `Ctrl+Supr` borra la línea entera (con su
  salto, sin dejar un renglón en blanco), `Ctrl+Mayús+Supr` del cursor al final de
  la línea, `Ctrl+Retroceso` la palabra anterior, `Ctrl+A` selecciona el mensaje,
  `Ctrl+Z`/`Ctrl+Y` deshacen y rehacen, y `Ctrl+←`/`Ctrl+→` (con `Mayús`, ir
  seleccionando) saltan de palabra en palabra. Valen en la caja del chat, en la de
  *Tu inglés* y en las reglas permanentes; los campos de una línea de Ajustes
  llevan `Ctrl+A`, `Ctrl+Retroceso` y `Ctrl+Supr`. Tk no los trae puestos: los pone
  la ventana (`ATAJOS_CAJA` / `ATAJOS_CAMPO`).
- **Tu nombre, lo primero**: se escribe en *Ajustes → Tu nombre* y Jarvis lo
  recuerda (viaja en el mensaje de sistema de cada consulta) para dirigirse a ti.
  Aparece en el pie de la barra lateral, que además abre Ajustes con un clic; el
  nombre de la sesión de Windows no se usa.
- **Micrófono a mano**: botón redondo en la caja de escritura (🎤) con un anillo
  alrededor que late —onda de sonido— mientras está escuchando.
- Tipografía moderna y elegida entre las instaladas (Inter/Poppins, o *Segoe UI
  Variable Text*), con la monoespaciada (*Cascadia Mono*) para los bloques de código.
- **El chat dice qué está haciendo**: mientras trabaja (SharePoint, IA, correo,
  Office...) aparece una lista de pasos en vivo —«Leyendo 2026/Viejo (3ª carpeta ·
  6 documentos)», «Moviendo 2 de 12: Acta.docx → Actas»— con el tiempo
  transcurrido, en lugar del antiguo «Jarvis está escribiendo» a secas.
- Historial de conversación por sesión (archivos `.md` en la carpeta de Jarvis).
- Selección y exportación de mensajes.
- Adjuntos de imágenes/texto y detección de rutas y URLs clicables.
- Mini-explorador de archivos (botón 📁 del chat): navegar OneDrive y carpetas,
  buscar y **mover/copiar** archivos de una carpeta a otra.
- **Apartado «Clase de inglés»** (botón 🎓 de la barra lateral): el tutor no se usa
  desde el chat, sino en su propia vista, con su caja de texto, un botón por tarea,
  el nivel en la cabecera y su panel para la clase (con copiar y guardar). La clase
  llega en **tarjetas**: una por apartado («✅ Versión corregida», «🔍 Punto por
  punto», «📚 Para entenderlo», «✍️ Practica»), con su icono, los ejemplos y
  ejercicios en monoespaciada y las soluciones listas para copiar.


### 🧠 Inteligencia
- Cerebro basado en **DeepSeek** (API compatible con OpenAI).
- **Reglas permanentes** del usuario que se inyectan en cada consulta.
- Normalización de comandos de voz y corrección de nombres propios.

### ⚙️ Control del sistema
- Abrir, cerrar y minimizar aplicaciones (Valorant, Discord, Spotify, navegadores,
  VS Code, OBS…).
- Gestión de **ventanas** y del **volumen** (global y por aplicación).
- Enviar aplicaciones al **segundo monitor**.

### 🧰 Productividad
- **Notas** rápidas y lectura en voz alta.
- **Resumir el portapapeles** y **explicar errores** copiados.
- **Pomodoro**, **perfiles** de entorno y **búsqueda de archivos**.
- **Clima** y **briefing** diario.
- **Crear documentos** (`.txt`, `.md`, `.csv`, `.docx`, `.pdf`).
- **Clasificar archivos de SharePoint/OneDrive** según una regla, usando tu sesión
  de Brave (sin Microsoft Graph): el asistente controla Brave por CDP (DevTools),
  así que es el propio navegador el que firma las peticiones. Si Brave estaba
  cerrado lo abre, y si estaba abierto sin acceso de depuración lo reinicia (no
  pierdes el inicio de sesión). Puedes pegar la dirección tal cual te la copia
  SharePoint, incluida la de la vista (`.../Oportunidad/Forms/AllItems.aspx?
  viewid=...&FolderCTID=...`): el asistente se queda con la carpeta de la que
  cuelga. También entiende los enlaces que comparte **Teams** o el correo
  (`.../my?id=%2Fpersonal%2Ftu%5Fcuenta%2FDocuments%2FPropuestas&viewid=...`):
  de ellos saca la carpeta **y el sitio**, que es lo que evita que una carpeta
  llena de subcarpetas te la dé por vacía. Revisa también **dentro de sus
  subcarpetas** y solo cuenta con los
  documentos de **Word y PowerPoint** (`.docx`, `.doc`, `.pptx`, `.ppt`): Excel,
  PDF, vídeo e imágenes se quedan donde están (no se tocan) y te dice cuáles
  ignoró. Te resume cuántas carpetas miró y, si una rama no se puede leer (por
  ejemplo sin permiso), sigue con el resto y te avisa de esa carpeta. Un árbol
  enorme se corta a los 6 niveles o 500 documentos, y también te lo dice.
  Antes de mover nada puedes pedirle solo el **listado** («¿qué hay en esta
  carpeta?», «listálalo»): te lo enseña **numerado** con su subcarpeta, sin
  tocar nada, y de ahí puedes elegir uno (`LISTAR_SHAREPOINT`) o decirle
  «clasifícalos todos con esta regla» y los reparte de golpe. Y al contrario:
  clasificar **no** necesita listado previo, el asistente mira las subcarpetas
  él solo, así que puedes pedirlo directamente. Tanto el listado
  como la clasificación aceptan un **filtro por nombre o subcarpeta** tras `;;`
  (`;;acta`, `;;2026, informe`), para trabajar solo con esos documentos.
  También puedes pedirle que mueva unos cuantos y **deje el resto quieto**
  («deja un Word y un PowerPoint en cada carpeta y no toques los demás»): esos
  se quedan donde estaban, te los nombra en el resumen y no cuentan como
  pendientes. Así se reparte sin tener que sacar antes la lista de los que sí se
  mueven.
  Y si le pides **copiar** («copia cada documento en la carpeta que le
  corresponda», «clasifícalos pero sin mover el original»), deja una copia en su
  carpeta y **los originales se quedan donde estaban** (nada va a la papelera):
  te lo avisa mientras trabaja y el resumen lo dice («Son COPIAS: los originales
  siguen donde estaban»). Sin decirlo, sigue moviendo como siempre.
  Al clasificar, el asistente lee **las carpetas que ya existen en el destino** y
  se las pasa a la IA para que elija entre ellas: así un *assessment* de QA cae
  en la carpeta `QA` que ya tienes, en vez de crearse una segunda con otro
  nombre. La respuesta se encaja con la carpeta real aunque venga en minúsculas,
  sin acentos o a medias (`soporte` → `Soporte y-o administración`, `QA` →
  `Quality Assurance`). **Nada se queda suelto**: lo que no encaje en ninguna va
  a `Otros`, y si la IA propone una carpeta que no existe se crea, pero te lo
  dice para que veas que no es un nombre repetido con otro.
  Y para acertar de verdad, **lee lo que hay dentro**: antes de clasificar baja
  cada documento con tu sesión de Brave (sin pasar por el disco) y le manda a la
  IA un extracto corto de su texto pegado a su nombre. Así un `Documento1.docx`
  se coloca por lo que pone dentro (el cliente, el tipo, el mes) y no por cómo se
  llame, que era lo que lo mandaba a `Otros`. Lo que no se pueda abrir por dentro
  (un `.doc` o `.ppt` antiguo, uno enorme, uno sin texto) se clasifica por su
  nombre y el resumen te dice cuáles y por qué. Si prefieres ir rápido y sin
  bajadas, pídelo: «clasifícalos sin leerlos», «solo por el nombre» o `;;sin leer`
  al final — entonces solo mira el nombre, como antes.
  Nunca pisa un archivo que ya exista en el destino (te avisa y lo deja
  donde estaba) y, si no puede comprobar el destino (por ejemplo, sin permiso),
  tampoco lo mueve: antes no mover que pisar. También vale si el destino está en
  **otro sitio** (pasar del sitio de equipo a tu OneDrive, o al revés): SharePoint
  no deja mover entre sitios, así que el asistente lo copia con tu sesión de Brave
  (descarga por la pestaña del origen y sube por la del destino) y, **solo si el
  tamaño cuadra**, manda el original a la papelera de SharePoint (recuperable). Si
  pegas la dirección de tu OneDrive sin carpeta (`...-my.sharepoint.com/personal/tu
  _cuenta`), entiende que el destino es `Documentos`; y si pegas una dirección que
  no es una carpeta (la raíz del host, `.../my`), te pide el enlace de la carpeta
  en vez de mover a ciegas a la raíz.
  Los archivos de más de 64 MB no los copia así: te avisa y te dice cómo moverlos
  a mano.

### 📧 Correo y reuniones
- **Leer y resumir el correo** (Outlook de escritorio o, cuando no está, el **Outlook
  nuevo / Microsoft 365** por la nube): lista los correos numerados (remitente,
  hora, asunto, extracto y marca de no leído) y los clasifica por urgencia.
- **Buscar correos** por asunto, remitente o contenido, y **leer uno completo**.
- **Sacar pendientes**: extrae de los correos las tareas, responsables y fechas.
- **Responder**: prepara la respuesta (con el correo citado debajo) y la deja en
  **Borradores**; solo se envía si se lo pides explícitamente.
- **Etiquetar** (categorías de Outlook), **archivar** en una carpeta, **marcar**
  leído/no leído y **eliminar** (a Elementos eliminados).
- **Grabar reuniones** (audio del sistema) y generar el **acta** al terminar con un
  análisis que rescata la información útil: resumen ejecutivo, participantes, temas
  con sus datos concretos, decisiones, tareas con responsable/fecha/prioridad,
  información rescatada (cifras, fechas, versiones, sistemas), riesgos, preguntas
  abiertas y próxima reunión. La reunión se contextualiza con el título, la fecha,
  la duración y los asistentes del calendario (si Jarvis puede leerlo), y las
  grabaciones largas se analizan por trozos para que no se pierda nada.
- **Avisos de escritorio**: al detectar la reunión, al empezar a transcribir y
  cuando el acta está lista, Jarvis deja un **aviso de Windows** en el centro de
  notificaciones («Acta lista · acta_2026-10-19_…md») además de decirlo en voz
  alta: no hay que quedarse mirando la ventana ni preguntar «¿ya?».
- **Actas guardadas**: pídele «mis reuniones» para verlas numeradas, «lee el acta
  de la reunión 2» para que te la resuma y «rehaz el acta» para regenerarla desde
  la transcripción.
- **Mandar el acta**: «envía el acta a los asistentes» deja el correo en
  **Borradores** (con el acta dentro) y solo lo envía si dices «envíalo».
- **Preparar la próxima reunión**: «prepara la agenda de mi próxima reunión» lee
  el calendario de Outlook y redacta la agenda.

Jarvis tiene **dos caminos** para el correo y elige solo, sin que tengas que hacer nada:
- **Outlook de escritorio** (COM): si lo tienes instalado y abierto, ya funciona.
- **Correo por la nube** (Microsoft Graph): para el **Outlook nuevo** (`olk.exe`),
  que no se puede controlar por COM, o cuando el Outlook clásico está cerrado.
  Se conecta **una sola vez** desde *Ajustes → «Conectar correo»*: Jarvis te da un
  código, abre la web de Microsoft y tú lo escribes ahí. **Nunca le das tu
  contraseña a Jarvis.** El token se guarda **cifrado con DPAPI** (solo lo puede
  descifrar tu usuario de Windows en este equipo) y lo puedes olvidar cuando
  quieras con *Desconectar*.

Consecuencia práctica: **el correo sigue funcionando con Outlook cerrado**, y las
respuestas y actas siguen quedando en **Borradores** (nada se envía solo).
Si no hay ninguno de los dos caminos, Jarvis te lo dice y no hace nada.

### ☁️ Matriz en la nube
- **Llenar una matriz** en **Excel (OneDrive/SharePoint)** y en **Azure DevOps** de una
  sola vez, a partir de los datos copiados en el portapapeles.
- El **Excel** se sube solo si está en una carpeta sincronizada (sin API key) y en
  **Azure DevOps** se crean **work items** con un PAT personal.

### 📊 Oficina y preventa
- **Generar presentaciones** de PowerPoint a partir de un archivo `.md`, respetando la
  **plantilla corporativa** (fondo, línea de cabecera y logo de la marca).
- Reemplazo masivo de **logos** en archivos `.pptx`.
- Documentos de **preventa** (propuesta, requisitos, historias de usuario, glosario,
  resumen y estimación).

### 🔍 Búsqueda y multimedia
- Búsqueda web en **Brave** (YouTube, Google, Wikipedia, GitHub, Spotify, etc.).
- Búsqueda y reproducción de **vídeos de YouTube** (`yt-dlp`).
- **Música en Spotify**: «pon *Las noches* de Junior H». Con la cuenta conectada en
  Ajustes (**Conectar Spotify**, OAuth2 con PKCE: solo hace falta el *Client ID* de tu
  app, sin claves secretas) la canción se pone por la **API oficial**: se busca la pista
  exacta y se le manda al dispositivo (`/me/player/play`), **sin abrir ni enfocar ninguna
  ventana** —así se puede pedir una canción con un juego en primer plano— y solo se dice
  «poniendo» cuando Spotify confirma que suena. Eso necesita cuenta **Premium**; con una
  cuenta gratuita, o sin sesión conectada, se usa el camino de siempre, que no necesita
  ninguna clave: resolver **esa pista** (buscador y ficha pública del tema), abrirla en el
  reproductor y luego **comprobar** en el título de la ventana de Spotify que lo que suena
  es esa canción: solo entonces contesta «poniendo» (si no puede comprobarlo, lo dice en
  vez de prometerlo). Si Brave está abierto con depuración (como cuando se trabaja con
  SharePoint) le da al play él mismo por CDP; si no, deja la pista cargada y lo avisa
  (Brave bloquea el autoplay por su cuenta). Para lo que esté sonando, «pausa»,
  «siguiente canción» y «anterior»: también por la API cuando hay sesión, y si no con la
  tecla multimedia de siempre.
- **OCR** de imágenes con Tesseract o RapidOCR.

### 👨💻 Desarrollo
- Mensajes de **commit** en formato *Conventional Commits* a partir del diff de Git.
- **Ejecución de comandos de terminal** con resumen del resultado.

### 🎓 Clase de inglés (apartado propio)
- **No pasa por el chat**: se entra con el botón **«🎓 Inglés»** de la barra lateral
  y todo ocurre en su apartado (a la izquierda escribes, a la derecha sale la clase).
- **Corrige y enseña** lo que escribes o dictas en inglés: no traduce, explica.
- **Los fallos típicos de un hispanohablante se detectan en local**, sin gastar IA
  ni necesitar internet: concordancia (*people is*), tercera persona (*she work*),
  `did` + pasado (*didn't went*), calcos (*explain me*, *say me*, *I have 30 years*,
  *depend of*, *listen me*, *ask to him*), plurales que no existen (*informations*,
  *advices*), ortografía (*recieved*, *definately*, *seperated*) y las preguntas mal
  montadas (*How I can…*, *How is called…*). Cada fallo dice qué escribiste, cómo se
  dice y **por qué**.
- La corrección llega con sus apartados: **versión corregida**, punto por punto,
  qué hay detrás y una **práctica** al final. Lo que no cuadre con ninguna regla
  también se le pasa a la IA junto al texto, para que no se quede nada sin corregir.
- **La clase se lee en tarjetas**: cada apartado de la respuesta llega como una
  tarjeta con su icono (✅ la versión corregida, 🔍 el punto por punto, 📚 la
  explicación, ✍️ la práctica…), las listas con su viñeta, las negritas en el color
  de acento y los ejemplos y ejercicios en monoespaciada sobre fondo oscuro. La
  tarjeta de la versión corregida lleva el borde encendido: es lo que te llevas.
- **Un botón por tarea**: *Corregir* (el texto de la caja «Tu inglés»), *Conversar*
  (te contesta en inglés, te corrige, te da alternativas y la traducción), **🗣
  Speaking** (hablas tú: ver abajo), *Ejercicios* y *Vocabulario* (del campo «Tema»
  y del número que elijas), *Explicar* (el tema, paso a paso), *Repaso* (lo que más
  se te repite), *Mi avance* y *Borrar*.
- **🗣 Speaking: hablar en inglés de verdad**. El micrófono del apartado (botón
  redondo junto a la clase, con su anillo que late) escucha en inglés sin palabra de
  activación —lo que digas es la práctica—, la IA responde con la corrección por
  escrito (cómo lo has dicho, pronunciación para hispanohablantes y tu turno) y la
  **réplica se lee en voz alta** con voz inglesa; el botón *Repetir* la vuelve a
  decir. Se enciende con el botón *Speaking* de la rejilla o con ese micrófono, y se
  apaga pulsando otra vez (o al salir del apartado). Mientras habla no escucha: si
  no, se oiría a sí mismo.
- **Lleva tu avance**: el **nivel** (A1-C2, «avanzado» → C1) se cambia en el
  desplegable de la cabecera, cuenta las prácticas y apunta los errores que se te
  repiten para insistir en ellos. Todo se guarda en
  `Documentos\Jarvis\ingles\estado.json`.
- **Lo único que gasta IA es la clase final**: el avance, el nivel y la detección de
  fallos funcionan aunque no haya API Key. La clase se pide a la IA en segundo plano
  (el apartado no se queda colgado) y, cuando está lista, se puede **copiar** al
  portapapeles o **guardar** como `.md` en `Documentos\Jarvis\documentos`.

### ☕ Aprender programación (apartado propio)
- **Tampoco pasa por el chat**: se entra con el botón **«💻 Programar»** de la barra
  lateral. Es un **taller de Java**: a la izquierda el editor (con su «Entrada» para
  el teclado y el campo «Tema»), a la derecha la **revisión en vivo** y lo que se te
  enseña, en tarjetas.
- **Se revisa mientras escribes, y es gratis**: el analizador propio ve llaves,
  paréntesis y corchetes sin cerrar, `;` que faltan, comillas sin terminar, `=` donde
  iba `==`, `string` en minúscula, `printline`, `if` sin paréntesis, comparar textos
  con `==`… Cada aviso sale con su **línea y su columna** y con la pista de qué
  arreglar, sin gastar IA ni necesitar internet. La revisión se lanza **una sola vez
  al dejar de teclear** (700 ms), para que el editor no se note pesado.
- **Compila de verdad, si tienes JDK**: *Corregir* pasa además `javac` (con su salida
  en inglés, para leer los mensajes) y traduce cada error al mismo formato; si el
  fallo es estructural (una llave sin cerrar) no se repite el ruido en cascada que
  suelta el compilador. Sin JDK todo lo demás sigue funcionando y el panel lo dice:
  `JDK instalado: compila y ejecuta de verdad` o `sin JDK: revisión básica`.
- **▶ Probar ejecuta tu programa**: lo compila y lo corre con un tope de tiempo (en
  un hilo aparte, así la ventana no se congela) y enseña lo que ha impreso; lo que
  el programa lea por teclado se escribe antes en «Entrada», un dato por línea.
- **Las bases, lección por lección**: *Bases* trae el temario del curso (primer
  programa, variables, condicionales, bucles, métodos, arrays, clases, herencia,
  colecciones, excepciones, entrada por teclado y cómo leer un error de
  compilación), cada tema con su sintaxis, un ejemplo comentado, los errores típicos
  y un ejercicio; *Lección* trae el tema que escribas en «Tema».
- ***Documentación***, *¿Por qué…?* y *Ejercicios*: la guía de consulta de las clases
  que más se usan al empezar (`String`, `ArrayList`, `HashMap`, `Scanner`…, con la
  firma, un ejemplo, las trampas y el enlace a la documentación de Oracle), las
  comparaciones razonadas que más dudas generan (`==` frente a `equals`, `+` frente a
  `StringBuilder`, `ArrayList` frente a `LinkedList`…) y ejercicios con soluciones
  del tema que pidas o de los fallos que más se te repitan.
- **Su propio chat, aparte del de Jarvis**: el centro del taller tiene dos caras,
  **Clase** (todas esas tarjetas) y **Chat**, una conversación independiente donde
  preguntar lo que quieras sin ensuciar el chat de siempre. *Preguntar* lleva la duda
  de «Tema» a ese chat; si escribes ahí, `Enter` la manda y `Mayús+Enter` salta de
  línea. Cada pregunta va con **tu programa delante** y con **lo que ya habéis
  hablado**, así que se puede seguir indagando («¿y entonces cómo lo comparo?»), y la
  respuesta se lee con su formato: código en monoespaciada, negritas y listas. *Nuevo*
  empieza otra conversación. Cada chat se guarda en
  `Documentos\Jarvis\programacion\chat_taller_<fecha>.md`, nunca en tus conversaciones.
- **Todo lo que ya está escrito se lee sin conexión**: el temario, las lecciones, la
  documentación, las comparaciones y el avance salen de las tablas del módulo y no
  gastan ni una llamada. Solo los ejercicios, la duda suelta y los temas que no están
  en las tablas se le piden a la IA, con el mensaje de sistema del profesor de
  programación (`APIBrain.SISTEMA_PROGRAMADOR`).
- **Lleva tu avance**: el **nivel** (Principiante, Intermedio, Avanzado) se cambia en
  el desplegable de la cabecera; cada corrección cuenta como práctica y apunta los
  fallos para insistir en ellos («lo que más se te repite»). Se guarda en
  `Documentos\Jarvis\programacion\estado.json`, y *Mi avance* / *Borrar* lo enseñan y
  lo reinician (borrar pide confirmación la segunda vez).
- **Nada de esto escribe en el chat**: ni la revisión, ni la salida del programa, ni
  las clases. Lo que se ve se puede **copiar** al portapapeles o **guardar** como
  `.md` en `Documentos\Jarvis\documentos`.

---

## 📋 Requisitos

- **Windows 10/11**
- **Python 3.10+**
- *(Opcional)* **Tesseract OCR** para leer texto dentro de imágenes (si no está, se usa
  el motor OCR en Python `rapidocr-onnxruntime`):
  ```powershell
  winget install -e --id UB-Mannheim.TesseractOCR
  ```
- *(Opcional)* **JDK 17+** para que el taller de programación **compile y ejecute** los
  programas de verdad (`javac` y `java` en el `PATH`, que es lo que busca
  `ProgrammingTutor.hay_jdk`). Sin JDK el taller sigue funcionando —revisa llaves,
  paréntesis, `;` y los errores típicos de empezar, y explica lo que pidas— pero no
  compila ni ejecuta, y lo dice en el panel:
  ```powershell
  winget install -e --id Microsoft.OpenJDK.17
  ```

---

## 🚀 Instalación

```powershell
# 1. Clona el repositorio
git clone https://github.com/deadewzz/Asistente-personal.git
cd Asistente-personal

# 2. Crea y activa un entorno virtual
python -m venv venv
.\venv\Scripts\activate

# 3. Instala las dependencias
pip install -r requirements.txt
```

---

## 🔧 Configuración

1. Copia la plantilla de variables de entorno y añade tu clave de API:
   ```powershell
   Copy-Item .env.example .env
   ```
   ```env
   DEEPSEEK_API_KEY=tu_api_key_aqui
   ```

2. El archivo de configuración del usuario se genera automáticamente en el primer
   arranque, en `Documentos\Jarvis\config\config_usuario.json`:
   ```json
   {
       "api_key": "",
       "nombre_asistente": "jarvis",
       "usuario": "",
       "modelo_rvc_path": "",
       "programas": {
           "discord": "discord://",
           "spotify": "spotify:",
           "vscode": "code"
       }
   }
   ```

   `usuario` es **tu nombre** (el del campo «Tu nombre» de *Ajustes*): el asistente
   lo recuerda en cada conversación y se dirige a ti así. Se cambia desde la ventana
   y solo hay que pulsar *Guardar*.

3. (Opcional) **Matriz en la nube** (Excel + Azure DevOps). Lo más fácil es usar los
   botones **«Excel (archivo o URL)»** y **«Configurar Azure DevOps»** de la pestaña
   *Ajustes*: cada uno abre su propio diálogo y guarda solo esa parte (el botón
   *Guardar configuración* no toca esta sección). En el diálogo del Excel puedes pegar el
   enlace del documento de SharePoint y, si quieres que los cambios se suban solos a la
   nube, indicar la **carpeta sincronizada** de esa biblioteca (*Sincronizar* en
   SharePoint). También puedes escribir estas claves a mano en `config_usuario.json`:
   ```json
   {
       "matriz": {
           "excel_path": "C:/Users/tu_usuario/OneDrive - Empresa/Matriz_Requerimientos.xlsx",
           "hoja": "Matriz",
           "columnas": ["ID", "Requisito", "Tipo", "Prioridad", "Estado", "Responsable", "Observaciones"]
       },
       "azure_devops": {
           "org": "https://dev.azure.com/MiOrganizacion",
           "project": "MiProyecto",
           "pat": "",
           "tipo_item": "Requirement"
       }
   }
   ```
   - **Excel (OneDrive/SharePoint):** hay tres formas de indicarlo:
     - `excel_path`: ruta completa de un archivo dentro de una carpeta sincronizada con
       OneDrive/SharePoint → se sube a la nube automáticamente.
     - `excel_url`: enlace (URL) del Excel publicado. Se descarga una copia local a
       `matrices/` y ahí se van acumulando las filas; el botón *Descargar URL ahora* del
       diálogo trae la última versión de la nube. **Ojo:** con URL sola los cambios se
       quedan en la copia local y **NO** llegan a SharePoint.
     - `excel_url` + `excel_sync_dir`: además indicas la carpeta sincronizada de esa
       biblioteca de SharePoint (*Excel → Sincronizar* en SharePoint copia la carpeta al
       equipo). La copia se baja y se edita *dentro* de esa carpeta con el mismo nombre
       que el documento remoto, así que OneDrive sube los cambios al Excel de SharePoint
       solo, sin credenciales de ningún tipo.

     **No hace falta ninguna API key.**
   - **Azure DevOps:** configúralo con el botón **«Configurar Azure DevOps»** (incluye
     *Probar conexión*) o a mano: genera un **PAT** (Personal Access Token) en
     `https://dev.azure.com/<tu-organizacion>/_usersSettings/tokens` con permiso
     *Work Items (Read & Write)* y pégalo en `azure_devops.pat` o en la variable de
     entorno `AZURE_DEVOPS_PAT`. **No necesitas un API key de administrador.**
   - Uso: copia los datos (columnas separadas por tabulador, `;` o `,`) y pide
     «llena la matriz de la nube». También puedes usar `[ACCION: MATRIZ_EXCEL]` o
     `[ACCION: MATRIZ_AZURE]` para un solo destino.

4. (Muy recomendado) **Conectar el correo** (para el Outlook nuevo o con Outlook
   cerrado). Abre la pestaña *Ajustes* y pulsa **«Conectar correo»**: Jarvis te
   muestra un código en la ventana, abre solo la web de Microsoft y tú escribes ahí
   el código. **No hace falta contraseña ni registrar ninguna aplicación en Azure.**
   Los permisos que se conceden son solo los que usa Jarvis (`Mail.ReadWrite`,
   `Mail.Send`, `User.Read`) y los puedes revocar con *Desconectar* o desde
   <https://myaccount.microsoft.com/consent>.
   También puedes hacerlo desde la consola:
   ```powershell
   python -m modules.correo_nube entrar    # conectar (una sola vez)
   python -m modules.correo_nube probar    # comprobar la conexión y listar 3 correos
   python -m modules.correo_nube salir     # olvidar la sesión guardada
   ```
   Se guarda en `config_usuario.json` → `correo`, con el token **cifrado con DPAPI**
   (es decir, atado a tu usuario de Windows de este equipo):
   ```json
   {
       "correo": {
           "token": "<token cifrado>",
           "cifrado": true,
           "cuenta": "tu.correo@empresa.com",
           "cliente_id": "14d82eec-204b-4c2f-b7e8-296a70dab67e",
           "tenant": "common"
       }
   }
   ```
   > Se usa un cliente público de Microsoft preautorizado para Graph (*"Microsoft
   > Graph Command Line Tools"*), así que no hay que crear ninguna app en Azure. Si tu
   > empresa exige una app propia, cambia `cliente_id` (y `tenant` si hay un inquilino
   > concreto) por la tuya, con los mismos permisos. El cliente de *Office* (`d3590ed6-…`)
   > no sirve para Graph: Microsoft lo rechaza con el error `AADSTS65002`.

5. (Opcional) **Música en Spotify**. Con la cuenta conectada, las canciones se ponen por
   la **API oficial**: sin abrir ni enfocar ninguna ventana (así se puede pedir una canción
   con un juego en primer plano) y solo contesta «poniendo» cuando Spotify confirma que
   suena. Se configura una sola vez:
   1. Entra en <https://developer.spotify.com/dashboard>, pulsa **Create app**, marca
      *Web API* y añade como **Redirect URI** exactamente
      `http://127.0.0.1:8888/callback`.
   2. En *Ajustes* → sección de música, pulsa **«Client ID»** y pega el *Client ID* de esa
      app (no es la contraseña de tu cuenta: con PKCE **no hace falta ningún secreto**).
      En ese mismo diálogo puedes fijar el **dispositivo** donde quieres que suene (parte
      del nombre, por ejemplo un altavoz; vacío = el PC que esté activo).
   3. Pulsa **«Conectar Spotify»** y acepta en el navegador: se abre una página local
      (`127.0.0.1:8888`) que solo recibe la autorización.
   Controlar la reproducción desde fuera requiere cuenta **Premium** (es una regla de
   Spotify); con una cuenta gratuita, o sin conectar nada, Jarvis resuelve la pista y **te
   la deja cargada** avisándote, que es lo que hacía antes. Los permisos se revocan con
   *Desconectar* o desde <https://www.spotify.com/account/apps/>. También desde la consola:
   ```powershell
   python -m modules.spotify entrar          # conectar (una sola vez)
   python -m modules.spotify probar          # sesión, dispositivos y qué está sonando
   python -m modules.spotify dispositivos    # equipos y altavoces disponibles
   python -m modules.spotify poner "Junior H Las noches"
   python -m modules.spotify salir           # olvidar la sesión guardada
   ```
   Se guarda en `config_usuario.json` → `spotify`, con el token de refresco **cifrado con
   DPAPI** (atado a tu usuario de Windows de este equipo):
   ```json
   {
       "spotify": {
           "cliente_id": "tu-client-id",
           "redireccion": "http://127.0.0.1:8888/callback",
           "dispositivo": "",
           "token": "<token cifrado>",
           "cifrado": true,
           "cuenta": "tu.usuario",
           "premium": true
       }
   }
   ```

> ⚠️ El archivo `.env` y `config/config_usuario.json` están en `.gitignore` porque
> pueden contener tu clave de API. **Nunca** los subas al repositorio.

---

## ▶️ Uso

```powershell
python main.py
```

- Habla por el micrófono o escribe en el chat de la interfaz.
- El botón **🎤** de la caja de escritura arranca y para la escucha (su anillo late
  mientras escucha); en *Ajustes* está el mismo botón con el estado de la voz.
- Al escribir valen los atajos de siempre: `Ctrl+Supr` borra la línea entera de la
  caja, `Ctrl+Retroceso` la palabra anterior, `Ctrl+A` selecciona el mensaje y
  `Ctrl+Z`/`Ctrl+Y` deshacen y rehacen (también en «Tu inglés», en las reglas y en
  los campos de *Ajustes*).
- El tutor de inglés tiene su propio apartado: se entra con el botón **🎓 Inglés** de
  la barra lateral y ahí se escribe, se piden las clases y se guarda el avance.
- El taller de programación (Java), igual: **💻 Programar** en la barra lateral. Se
  escribe el programa, se revisa solo mientras escribes (con línea y columna, sin
  gastar IA), *Corregir* pasa el compilador y *Probar* lo ejecuta.
- Para una acción, el asistente responde con un comando en el formato
  `[ACCION: TIPO|PARAMETRO]` que se ejecuta automáticamente. Algunos ejemplos:

  | Pides… | Comando |
  | --- | --- |
  | «Abre Discord» | `[ACCION: ABRIR_APP|discord]` |
  | «Busca en YouTube música lo-fi» | `[ACCION: BUSCAR|youtube:musica lo-fi]` |
  | «Pon *Las noches* de Junior H» | `[ACCION: REPRODUCIR_MUSICA|Junior H Las noches]` |
  | «Pausa la música» | `[ACCION: MUSICA|pausa]` |
  | «Siguiente canción» / «Vuelve a la anterior» | `[ACCION: MUSICA|siguiente]`, `[ACCION: MUSICA|anterior]` |
  | «Haz una presentación con presentacion.md» | `[ACCION: CREAR_PRESENTACION|presentacion.md]` |
  | «Resume lo que tengo copiado» | `[ACCION: RESUMIR_PORTAPAPELES]` |
  | «Lee mis últimos correos» | `[ACCION: LEER_CORREOS|5]` |
  | «Resume el correo de hoy» | `[ACCION: RESUMEN_CORREOS|hoy]` |
  | «Saca los pendientes del correo» | `[ACCION: CORREO_PENDIENTES|10]` |
  | «Respóndele al 2 que sigo pendiente» | `[ACCION: RESPONDER_CORREO|2;;texto de la respuesta]` |
  | «Envía ese correo» | `[ACCION: ENVIAR_BORRADOR]` |
  | «Archiva el 3 en Proyectos» | `[ACCION: ARCHIVAR_CORREO|3;;Proyectos]` |
  | «Graba la reunión» | `[ACCION: GRABAR_REUNION]` |
  | «Termina la reunión» | `[ACCION: TERMINAR_REUNION]` |
  | «¿Qué reuniones tengo guardadas?» | `[ACCION: REUNIONES|8]` |
  | «Lee el acta de la reunión 1» | `[ACCION: LEER_ACTA|1]` |
  | «Rehaz el acta de ayer» | `[ACCION: REHACER_ACTA|2026-10-07]` |
  | «¿Quiénes asistieron a la reunión?» | `[ACCION: ASISTENTES_REUNION]` |
  | «Envía el acta a los asistentes» | `[ACCION: ENVIAR_ACTA]` |
  | «Manda el acta del 2 a ana@empresa.com» | `[ACCION: ENVIAR_ACTA|ana@empresa.com;;2;;enviar]` |
  | «Prepara la agenda de mi próxima reunión» | `[ACCION: AGENDA_REUNION]` |
  | «Llena la matriz de la nube» | `[ACCION: MATRIZ_NUBE]` |
   | «Lista la carpeta de OneDrive» | `[ACCION: LISTAR_CARPETA|C:\Users\tu\OneDrive\Proyectos]` |
   | «¿Qué hay en esta carpeta de SharePoint?» / «Listálalo» | `[ACCION: LISTAR_SHAREPOINT|https://.../sites/Sitio/Carpeta]` (solo algunos: `[ACCION: LISTAR_SHAREPOINT|url;;acta]`) |
   | «Busca facturas en Proyectos» | `[ACCION: BUSCAR_EN_CARPETA|C:\...\Proyectos;;factura]` |
   | «Mueve factura.pdf a Pagadas» | `[ACCION: MOVER_ARCHIVOS|C:\...\factura.pdf;;C:\...\Pagadas;;mover]` |
   | «Clasifica esta carpeta en subcarpetas por tipo» | `[ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;regla]` (para probar con uno: `[ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;por tipo;;acta]`) — las dos URLs van **tal cual** las copia SharePoint/OneDrive, con sus `?id=…&viewid=…&sdata=…&ovuser=…`, los enlaces de Teams o el `Forms/AllItems.aspx`: el asistente saca de ahí la carpeta y el sitio de cada una, no hay que «limpiarlas» |
   | «Cada documento del assessment en la carpeta que le toque (sin mover los originales)» | `[ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;copia cada uno en la carpeta que le corresponda]` (o la bandera `;;copiar` al final) |
   | «Colócalos por lo que pone dentro, no por el nombre» | `[ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;cada uno en la carpeta que le corresponda]` — antes de mover, el asistente **lee** cada Word/PowerPoint; para ir solo por el nombre (más rápido, sin bajadas): `[ACCION: CLASIFICAR_ARCHIVOS|url_origen;;url_destino;;por tipo;;sin leer]` |
   | Clase de inglés (corregir, explicar, ejercicios, conversar…) | Ya **no** se pide por el chat: tiene su apartado propio, con el botón «🎓 Inglés» de la barra lateral y un botón por tarea |
   | Aprender a programar en Java (revisar mi código, un tema, un ejercicio…) | Tampoco: taller propio, con el botón «💻 Programar» de la barra lateral, la revisión en vivo, un botón por tarea y su propio chat (aparte del de siempre) |

---

## 📁 Estructura del proyecto

```
Asistente/
├── main.py                 # Punto de entrada: entorno, .env, migración y arranque de la GUI
├── app_gui.py              # La ventana: barra lateral, cambio de apartado y servicios
├── ui/
│   └── tema.py             # Paleta, tipografía, medidas y atajos: el estilo, en un sitio
├── views/                  # Un módulo por apartado (cada uno es una vista de la ventana)
│   ├── base.py             # La base común: atajos de las cajas, Markdown y tarjetas
│   ├── chat.py             # El chat: burbujas, adjuntos, barra de escribir y pasos
│   ├── ingles.py           # «Clase de inglés»: tareas del tutor, clase y speaking
│   ├── programacion.py     # «Aprender programación»: editor, revisión en vivo y clases
│   └── ajustes.py          # Ajustes: tu nombre, la voz, la nube, el correo y Spotify
├── main.spec               # Receta de empaquetado con PyInstaller
├── requirements.txt
├── .env.example            # Plantilla de variables de entorno
├── modules/
│   ├── archivos.py         # Explorador local: listar, buscar, mover y copiar archivos
│   ├── api_brain.py        # Cerebro LLM (DeepSeek) y reglas permanentes
│   ├── voice_engine.py     # Reconocimiento de voz (Google / Whisper) en español e inglés
│   ├── voice_output.py     # Síntesis de voz (edge-tts / pyttsx3)
│   ├── system_actions.py   # Enrutador de acciones del sistema
│   ├── productivity.py     # Notas, portapapeles, pomodoro, perfiles, documentos
│   ├── office_automation.py# PowerPoint y presentaciones desde plantilla
│   ├── correo.py           # Elige el cliente de correo (Outlook COM o nube)
│   ├── correo_nube.py      # Correo por la nube (Microsoft Graph + OAuth2)
│   ├── outlook_tools.py    # Correo de Outlook por COM
│   ├── calendario_tools.py # Calendario de Outlook (reunión en curso, próximas, invitados)
│   ├── meeting_assistant.py# Grabación, transcripción y acta de reuniones
│   ├── notificaciones.py   # Avisos de Windows (centro de notificaciones), sin dependencias
│   ├── spotify.py          # Música por la API de Spotify (OAuth2 + PKCE, sin claves secretas)
│   ├── preventa_tools.py   # Documentos de preventa
│   ├── cloud_matrix.py     # Matriz en la nube (Excel + Azure DevOps)
│   ├── dev_tools.py        # Commits de Git y comandos de terminal
│   ├── english_tutor.py    # Tutor de inglés: fallos, clases y la charla del «Speaking»
│   ├── programming_tutor.py# Taller de Java: revisión con línea y columna, javac, temario y avance
│   ├── ocr_engine.py       # OCR (Tesseract / RapidOCR)
│   ├── progreso.py         # Lo que está haciendo, contado en vivo a la ventana
│   └── rutas.py            # Rutas centralizadas de la carpeta de Jarvis
├── tests/
│   ├── pruebas_correo_nube.py    # Pruebas del correo en la nube (Graph simulado)
│   ├── pruebas_correo_en_vivo.py # Comprobación real contra Microsoft (sin credenciales)
│   ├── pruebas_musica.py         # Pruebas de la música: la pista, el play (API y web) y el control
│   ├── pruebas_gui_correo.py     # Pruebas de la sección de correo de la ventana
│   ├── pruebas_ingles.py         # Pruebas del tutor de inglés (detección, clases, speaking y apartado)
│   ├── pruebas_gui_ingles.py     # Pruebas del apartado de inglés: botón, panel, avance y speaking
│   ├── pruebas_programacion.py   # Pruebas del taller de Java (revisión con línea y columna, javac, ejecutar y apartado)
│   ├── pruebas_gui_programacion.py # Pruebas del apartado de programación: revisión en vivo, corrección, ejecutar y avance
│   ├── pruebas_gui_estilo.py     # Pruebas del aspecto: paleta, tarjetas, acento, caja expansible y micrófono
│   ├── pruebas_gui_perfil.py     # Pruebas de «Tu nombre»: se guarda y el asistente lo recuerda
│   ├── pruebas_gui_atajos.py     # Pruebas de los atajos de las cajas (Ctrl+Supr, Ctrl+A, deshacer...)
│   ├── pruebas_gui_chat.py       # Pruebas del chat: los pasos que cuenta el indicador
│   └── pruebas_gui_spotify.py    # Pruebas del apartado de música de Ajustes (Spotify)
└── assets/
    ├── plantillas/         # Plantillas .pptx corporativas
    └── tools/tessdata/     # Modelos de idioma de Tesseract (spa/eng)
```

### Cada apartado es una vista

La ventana (`app_gui.py`) es solo el armazón: la barra lateral, el cambio de
apartado y los servicios que comparten todos (el cerebro, las acciones del
sistema, la voz y el historial). Cada apartado vive en su módulo de `views/` y
es una **vista** independiente —un `CTkFrame` con sus widgets, su estado y sus
métodos—:

| Vista | Apartado | Qué trae |
| --- | --- | --- |
| `views/chat.py` | Chat | Burbujas, adjuntos, barra de escribir, pasos del indicador y explorador |
| `views/ingles.py` | 🎓 Inglés | Texto del alumno, tareas del tutor, clase en tarjetas y speaking |
| `views/programacion.py` | 💻 Programar | Editor, revisión en vivo, ejecutar, la clase del profesor de Java y su chat aparte |
| `views/ajustes.py` | ⚙ Ajustes | Tu nombre, la voz, la nube, el correo y Spotify |

La ventana las monta en `_crear_interfaz`, las enseña y las esconde
(`pack`/`pack_forget`) y les pasa lo común en `self.app`; no entra en lo que hay
dentro de cada una. Lo que se repite (atajos de las cajas, Markdown de los
paneles y tarjetas con icono) está en `views/base.py`, y el estilo —paleta,
tipografía y medidas— en `ui/tema.py`, así que un cambio de color se hace en un
sitio y se ve en todos los apartados.

---

## 🧪 Pruebas

No hacen falta librerías extra: cada archivo se ejecuta solo y termina diciendo
cuántas comprobaciones ha pasado (salida `0` si todo va bien). Ninguna toca tu
configuración real ni tu buzón (usan una configuración temporal).

```powershell
python tests\pruebas_archivos.py         # explorador, mover/copiar y rutas (sin red)
python tests\pruebas_sharepoint.py       # SharePoint sin Graph: URLs, llamadas _api, clasificación y progreso
python tests\pruebas_ingles.py           # tutor de inglés: detección local, avance, speaking y apartado (sin IA)
python tests\pruebas_programacion.py    # taller de Java: revisión con línea y columna, javac, ejecutar y apartado (sin IA)
python tests\pruebas_correo_nube.py      # correo por la nube, con Microsoft simulado
python tests\pruebas_musica.py           # la música: pista, play (API de Spotify y reproductor web) y control
python tests\pruebas_reunion.py          # el acta al terminar, los avisos de escritorio y el búfer de grabación
python tests\pruebas_gui_correo.py       # botones y avisos de Ajustes (abre la ventana)
python tests\pruebas_gui_ingles.py       # el apartado de inglés: botón, panel, nivel, avance y speaking (abre la ventana)
python tests\pruebas_gui_programacion.py # el taller de Java: revisión en vivo, corregir, probar, tablas y avance (abre la ventana)
python tests\pruebas_gui_estilo.py       # el aspecto: paleta, tarjetas, acento, Markdown del chat y caja expansible
python tests\pruebas_gui_perfil.py       # «Tu nombre»: se guarda, se ve y el asistente lo recuerda
python tests\pruebas_gui_atajos.py       # los atajos de las cajas: Ctrl+Supr, Ctrl+Retroceso, Ctrl+A y deshacer
python tests\pruebas_gui_chat.py         # el indicador del chat (abre la ventana)
python tests\pruebas_gui_spotify.py      # el apartado de música de Ajustes: botones, estado y aviso de Premium
python tests\pruebas_correo_en_vivo.py   # HTTP real contra Microsoft (necesita internet)
```

`tests\diagnostico_brave.py` merece un apartado propio: **abre Brave** con el
puerto de depuración y va diciendo, paso a paso, si el navegador está, si la
pestaña responde y si la sesión sirve para leer SharePoint. Con una URL de
carpeta comprueba además el listado real, recorre las subcarpetas buscando
Word/PowerPoint (lo mismo que hacen `LISTAR_SHAREPOINT` y `CLASIFICAR_ARCHIVOS`,
con el filtro opcional del segundo argumento) y enseña con qué carpeta me quedo
(útil para verificar que una dirección copiada de SharePoint apunta donde crees):

```powershell
python tests\diagnostico_brave.py
python tests\diagnostico_brave.py "https://empresa.sharepoint.com/sites/MiSitio/Documentos compartidos"
python tests\diagnostico_brave.py "https://empresa.sharepoint.com/sites/MiSitio/Docs/Forms/AllItems.aspx?viewid=...&FolderCTID=..."
python tests\diagnostico_brave.py "https://empresa.sharepoint.com/sites/MiSitio/Docs" "acta"
```

---

## 🗂️ Carpeta de datos de Jarvis

Todos los archivos que genera el asistente se guardan en una carpeta raíz única
(por defecto `Documentos\Jarvis`), organizada por tipo. Se puede cambiar con la
variable de entorno `JARVIS_HOME`.

```
Jarvis/
├── config/           # config_usuario.json y reglas.md (memoria del asistente)
├── conversaciones/   # Historiales de chat (.md)
├── notas/            # Notas rápidas (.md)
├── reuniones/        # Actas de reunión por mes (.md), con transcripción
├── matrices/         # Matrices (.xlsx) para subir a la nube (OneDrive/SharePoint)
├── documentos/       # Documentos creados (.txt, .md, .csv, .docx, .pdf)
├── ingles/           # Apartado «Clase de inglés»: estado.json (nivel, prácticas y errores repetidos)
├── adjuntos/         # Imágenes y textos pegados o adjuntos
├── presentaciones/   # Fuentes .md para generar PowerPoint
├── preventa/         # Documentos de preventa (.md)
├── plantillas/       # Plantillas .pptx
├── modelos/          # Modelos locales (p. ej. voz RVC)
└── temp/             # Archivos temporales (audio, capturas)
```

En el primer arranque se migran automáticamente los datos de la estructura antigua
(`assets/` y `config/`) a esta carpeta. La migración es idempotente y no sobrescribe
archivos existentes.

---

## 📦 Compilar el ejecutable

El proyecto incluye una receta de PyInstaller (`main.spec`):

```powershell
pyinstaller main.spec
```

El ejecutable resultante se genera en `dist/`.

---

## 📝 Notas

- Requiere **Windows** (usa `pywin32`, `pycaw`, `pyautogui`, etc.).
- La clave de `DeepSeek` se lee desde `.env` o desde `config_usuario.json`.
- Las dependencias opcionales (Whisper, OCR, RVC, Outlook) degradan con elegancia si
  no están instaladas.
- Proyecto personal en evolución; algunas funciones están en fase de pruebas.
- El **plan de funciones pendientes** (estado, módulo y dependencias de cada una)
  está en [`ROADMAP.md`](ROADMAP.md).

