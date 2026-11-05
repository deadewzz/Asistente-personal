# Roadmap de Jarvis — estado y plan de implementación

Cada punto indica: **estado** (✅ hecho · 🟡 parcial · ❌ pendiente), **cómo se
implementa** (módulo + acción + dependencia) y la fase en la que se aborda.
Convenciones que se mantienen en todo el proyecto:

- Las órdenes del modelo son comandos `[ACCION: TIPO|PARAMETRO]` al final del
  mensaje, enrutadas por `SystemActions.ejecutar_comando`.
- El texto libre (cuerpos largos) viaja con `|` y `;;` como separadores propios
  y se lee siempre con `parametro_libre` (nunca rebanando por `|`).
- Si una acción necesita que la IA interprete datos, devuelve
  `"__CONTEXTO__" + instrucción + datos` y la GUI lo reinyecta al cerebro.
- Si necesita una **respuesta larga** de la IA (una clase, no un comando), el tutor
  de inglés (`modules/english_tutor.py`) devuelve `"__TUTOR__" + encargo` y su
  **apartado** en la ventana (botón «🎓 Inglés» de la barra lateral) la pide con
  `APIBrain.SISTEMA_TUTOR`: se responde completo y en Markdown, sin recortar y sin
  leer comandos de acción dentro del texto. El chat no reparte clases de inglés:
  eso es cosa de ese apartado.
- Todo se degrada con elegancia: si falta una librería o un permiso, se devuelve
  un mensaje claro y no se lanza la excepción al usuario.
- Nada que envíe correo, publique o gaste dinero ocurre sin pedido explícito.

---

## Fase 0 — cimientos (prerrequisitos de casi todo)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 0.1 | Registro de acciones y extractor robusto de comandos | ✅ | `modules/api_brain.py` (`_extraer_accion`) + `modules/system_actions.py` |
| 0.2 | Carpetas y rutas centralizadas | ✅ | `modules/rutas.py` (`JARVIS_HOME`, migración) |
| 0.3 | **Leer archivos existentes por ruta** | 🟡 | Hoy solo al adjuntarlos en el chat (`_extraer_contenido`). Falta la acción `LEER_ARCHIVO|ruta` para PDF/Word/Excel/CSV/PPTX (reutiliza `pypdf`, `python-docx`, `openpyxl`, `python-pptx`). |
| 0.4 | **Memoria de contexto persistente** (proyectos, rutas, personas) | ❌ | `modules/memoria.py` + `memoria.md` en `rutas.CONFIG`; se inyecta en el prompt como las reglas. |
| 0.5 | **Registro/auditoría de acciones** | ❌ | `modules/auditoria.py` → `Jarvis/auditoria/AAAAMM.md`: qué se pidió, cuándo y con qué resultado. |
| 0.6 | **Permisos por tarea** | ❌ | `permisos.json`: acciones que exigen confirmación (enviar correo, borrar, apagar, publicar). |
| 0.7 | **Tareas programadas** | ❌ | `modules/programador.py` con hilo propio (`schedule` no está instalado): diario/semanal/mensual. Base de informes periódicos y del modo no molestar. |
| 0.8 | **Explorador de archivos y mover/copiar** | ✅ | `modules/archivos.py` + mini-explorador (📁) y acciones `LISTAR_CARPETA`, `BUSCAR_EN_CARPETA`, `MOVER_ARCHIVOS`, `COPIAR_ARCHIVOS` (mover/copiar piden confirmación). |
| 0.9 | **Clasificar archivos de SharePoint sin Graph** | ✅ | `modules/sharepoint.py` + `modules/navegador_cdp.py` + acción `CLASIFICAR_ARCHIVOS|origen;;destino;;regla`: controla Brave por CDP (sin descifrar cookies) para listar con la sesión del usuario, clasifica con la IA y mueve por la API `_api` de SharePoint. Acepta la URL tal cual la copia SharePoint (`.../Forms/AllItems.aspx?viewid=...`: se queda con la carpeta, y respeta `RootFolder=`/`id=`). Antes de fiarse de un listado comprueba que la carpeta/archivo existen de verdad, porque `_api` responde **200 con lista vacía** a rutas que no existen: con eso, una carpeta mal escrita parecía vacía y un choque de nombres podía pasar inadvertido. Ahora revisa también **dentro de las subcarpetas** (`listar_documentos`: una petición por carpeta, siguiendo los `__next` de las colecciones grandes, con tope de 6 niveles/500 documentos y saltando las carpetas técnicas como `Forms`) y solo clasifica **Word y PowerPoint** (`.docx`, `.doc`, `.pptx`, `.ppt`); Excel, PDF, vídeo e imágenes se quedan donde están y se informan. Una subcarpeta sin permiso ya no tira el listado entero: se avisa y se sigue. Antes de mover nada se puede pedir solo el **listado** con `LISTAR_SHAREPOINT|url` (numerado, con su subcarpeta, sin tocar nada) y luego elegir uno; tanto el listado como la clasificación aceptan un **filtro** por nombre o subcarpeta tras `;;` (`;;acta`, `;;2026, informe`), y la clasificación con `;;` solo mueve esos. Nunca pisa el destino y, si no puede comprobarlo, no mueve. |
| 0.10 | **El chat dice qué está haciendo (progreso en vivo)** | ✅ | `modules/progreso.py`: canal `Progreso` (`paso`/`hecho`/`aviso`, silencioso sin receptor y seguro desde cualquier hilo) que las acciones lentas usan para contar lo que hacen; la ventana conecta el suyo (`AppGUI._progreso_gui`) y lo pinta en el indicador del chat, que pasa de un «Jarvis está escribiendo» mudo a «Jarvis está trabajando (0:12)» con los últimos pasos («Leyendo 2026/Viejo (3ª carpeta · 6 documentos)», «Moviendo 2 de 12: Acta.docx → Actas», «No pude entrar en 2026; sigo con el resto»). `SystemActions.PROGRESO_ACCIONES` describe cada acción larga antes de ejecutarla (red, navegador, IA, Office, terminal), `SharePoint` cuenta cada carpeta leída, cada movimiento, los pasos del puente entre sitios y las ramas sin permiso, y `app_gui` cuenta la IA del chat, la clasificación y las actas. Vale igual para los mensajes por voz. |
| 0.11 | Enlaces de Teams/OneDrive: se entiende la carpeta **y el sitio** | ✅ | `SharePoint.parsear_url` deduce el sitio de la ruta del parámetro (`.../my?id=%2Fpersonal%2Fana%2FDocuments%2FPropuestas`): antes el sitio quedaba en la **raíz del host**, SharePoint respondía ahí 200 con lista vacía y una carpeta con 7 subcarpetas y 75 documentos salía como «vacía» al intentar usarla de destino. También entiende los atajos `/:w:/r/...` y la portada `.../my`; si el destino acaba siendo la raíz del host (que en un tenant real contesta `ServerRelativeUrl: '/'` y lista `/personal` como vacía), `clasificar_y_mover` pide el enlace de la carpeta en vez de mover a ciegas. Cubierto por `tests/pruebas_sharepoint.py`. |
| 0.12 | **Dejar archivos donde están al clasificar** (`dejar`) | ✅ | `SharePoint.es_dejar` reconoce la marca que el clasificador devuelve como «carpeta» cuando la regla pide que ese archivo no se mueva (`dejar`, `no lo muevas`, `(dejar)`, `- dejar -`, `dejar.`, `déjalo donde estaba`…) y `clasificar_y_mover` la salta: los que se quedan no cuentan en «Moviendo N de M» ni en «Movidos X de N», se avisa en vivo («3 archivo(s) se quedan donde están») y se nombran aparte en el resumen («Se quedan donde estaban (la regla lo pide)»); si la regla deja todo, no dice «Movidos 0 de 0». Un nombre de carpeta real (`Dejar constancia`) no se confunde: se compara la frase completa. Además, si la carpeta asignada es la que el archivo **ya tenía** (lo normal al clasificar dentro de la misma biblioteca) tampoco cuenta como movimiento: se informa aparte («Ya estaban en su carpeta (no había nada que mover)») en vez de salir como choque de nombres. `api_brain.clasificar_archivos` recibe la instrucción de contestar `dejar` y el prompt de acciones explica que la regla puede pedir dejar el resto quieto, así que una sola regla («deja 1 Word y 1 PowerPoint por carpeta») reparte y deja el resto sin enumerar antes los que sí se mueven. Cubierto por `tests/pruebas_sharepoint.py`. |
| 0.13 | **Clasificar copiando y sin dejar nada suelto** | ✅ | Dos cosas que pedía el caso real de la carpeta `Propuestas`: (1) **copiar en vez de mover** — si la orden dice «copia», «duplica» o «sin mover el original» (o se añade `;;copiar` al final), `clasificar_y_mover(copiar=True)` usa `CopyTo` dentro del sitio (la copia la hace SharePoint de una pieza, sin bajar el archivo) y, entre sitios, el *puente* con `conservar_origen=True` para **no reciclar** el original; el progreso pasa a «Copiando N de M», el resumen a «Copiados X de N» y se cierra con «Son COPIAS: los originales siguen donde estaban». (2) **nada suelto en la raíz** — antes de clasificar, la acción lee **las carpetas que ya existen en el destino** (`_carpetas_destino`, sin las técnicas como `Forms`) y se las pasa a la IA como candidatas (`clasificar_archivos(nombres, regla, carpetas)`), así elige entre las de verdad en vez de inventarse una segunda `QA` al lado de la existente; después `SharePoint.normalizar_carpeta` encaja la respuesta con la carpeta real (nombre exacto, prefijo por palabras —`soporte` → `Soporte y-o administración`— o siglas —`QA` → `Quality Assurance`—) y `SharePoint.encajar_plan` decide lo demás: `dejar` se respeta, la carpeta inventada se crea pero **se avisa** («no son ninguna de las que ya hay»), y lo que llegue sin carpeta (`''`, `(raíz)`, `sin clasificar`) va a `FALLBACK_CARPETA` (`Otros`) con su aviso. La clasificación de respaldo sin IA sigue mandando todo a la raíz y lo dice. Cubierto por `tests/pruebas_sharepoint.py` (`pruebas_copiar_archivos`, `pruebas_carpetas_destino`). |
| 0.14 | **Clasificar por el contenido, no solo por el nombre** | ✅ | El clasificador solo veía nombres: un `Documento1.docx` (o `Assessment final v3`) acababa en `Otros` aunque dentro pusiera a qué cliente y de qué iba. Ahora se **lee el documento antes de colocarlo**: `modules/documentos.py` (nuevo) saca el texto de un `.docx` (párrafos y **tablas**, que es donde van cliente/tipo/mes) y de un `.pptx` (formas —incluidas las agrupadas—, tablas y notas) **desde los bytes en memoria**, porque el archivo no está en disco: se baja con la pestaña de Brave del propio sitio (`SharePoint.leer_textos`, sin pasar por el disco ni por Graph), hasta `LIMITE_LECTURA` (16 MB) y 3 fallos seguidos como mucho (si se cayó la sesión, no insiste 70 veces). El extracto son 900 caracteres de **una línea** (`MAX_TEXTO_DOCUMENTO`, cortado por un espacio, no a media palabra) y viaja pegado a su nombre en el prompt (`api_brain.clasificar_archivos(nombres, regla, carpetas, extractos)` con la línea `> texto del documento: …`), así la IA decide por el contenido y sigue contestando el **nombre** del archivo. Lo que no se puede leer por dentro no se baja en balde: `.doc`/`.ppt` antiguos, archivos enormes (se ve ya en el listado) o uno sin texto se clasifican por su nombre, y el resumen dice cuáles y por qué («leí 12 de 15»). La orden puede pedir ir por el nombre (`;;sin leer`, «clasifícalos sin leerlos», «solo por el nombre»: `SharePoint.quiere_sin_leer` / `MARCAS_SIN_LEER`, y `es_bandera` evita que `;;sin leer` se cuele como filtro de nombres). Con muchos documentos la IA va **por lotes** de 25 (`SystemActions.LOTE_IA`) para que una llamada gigante no se corte a medias. Cubierto por `tests/pruebas_sharepoint.py` (`pruebas_leer_contenido`). |
| 0.15 | **Clasificar de verdad cuando la URL viene «sucia»** | ✅ | El caso real de Oportunidad → `Propuestas` se quedaba en el chat: el modelo contestaba «no puedo, las URLs llevan `id=`, `viewid=`, `sdata=`, `ovuser=` y la de origen es una vista `Forms/AllItems.aspx`» y, cuando no se negaba, **listaba** con `LISTAR_SHAREPOINT` y el listado terminaba en «dime cuál quieres clasificar»: tantos ida y vueltas que la acción no llegaba nunca. El parser ya entendía esas URLs (`SharePoint.parsear_url` se queda con la carpeta de la vista, del `id=`/`RootFolder=` y del camino, y saca el sitio de la propia ruta: comprobado con la URL exacta del caso), así que el fallo era del prompt y del cierre del listado. Ahora el prompt de acciones (`modules/api_brain.py`) dice que **las URLs van TAL CUAL las da SharePoint/OneDrive** (con sus parámetros, los enlaces de Teams y los `Forms/AllItems.aspx`) y que **no pida enlaces «limpios» ni se niegue por eso**; que `CLASIFICAR_ARCHIVOS` **se emite en el mismo mensaje** en que el usuario la pide (sin listar antes, sin preguntar cuál y sin pedir permiso: «todos» = la carpeta entera, y el filtro `;;` solo si el usuario elige un número del listado); que `LISTAR_SHAREPOINT` **no es un paso previo a clasificar** (clasificar sin listar); y las acciones que tocan archivos entran en la regla de «responde SOLO con la acción, sin texto adicional ni preguntas» (el asistente ya enseña el resultado). En `system_actions._listar_sharepoint` el cierre mantiene la opción de elegir uno y añade la de **«clasifícalos todos»** de golpe, para que un listado ya no sea un callejón sin salida. Comprobado con el **modelo real** (DeepSeek): con la URL del caso contesta `CLASIFICAR_ARCHIVOS|…Forms/AllItems.aspx?id=…&viewid=…&sdata=…&ovuser=…;;…/Documents/Propuestas;;…'dejar'…;;copiar`. Cubierto por `tests/pruebas_sharepoint.py` (`pruebas_acciones_documentadas`, `pruebas_accion_listar`). |




## Fase 1 — correo bidireccional (prioridad 1)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 1.1 | Leer, resumir y clasificar correos | ✅ | `LEER_CORREOS` / `RESUMEN_CORREOS`: remitente, hora, cuerpo, no leídos y clasificación por urgencia. |
| 1.2 | Buscar correos | ✅ | `BUSCAR_CORREOS|consulta` (asunto, remitente y cuerpo). |
| 1.3 | Responder correos | ✅ | `RESPONDER_CORREO|clave;;texto[;;enviar]`: guarda borrador y **solo envía si se pide**. |
| 1.4 | Etiquetar, archivar y marcar | ✅ | `ETIQUETAR_CORREO`, `ARCHIVAR_CORREO`, `MARCAR_CORREO`. |
| 1.5 | Pendientes y acciones automáticos | ✅ | `CORREO_PENDIENTES|n` → la IA extrae compromisos, responsables y fechas. |
| 1.6 | Leer un correo completo | ✅ | `LEER_CORREO|clave` (admite número del último listado o parte del asunto/remitente). |
| 1.7 | Adjuntos de un correo | ❌ | Guardarlos en `rutas.ADJUNTOS` y analizarlos (enlaza con 0.3). |
| 1.8 | Correo con Outlook cerrado o el Outlook nuevo | ✅ | `modules/correo_nube.py`: Microsoft Graph con OAuth2 de **código de dispositivo** (un código, sin contraseña ni registrar apps) y botón **«Conectar correo»** en Ajustes. Token cifrado con DPAPI. |

*Se implementa con **dos caminos** y la app elige sola (`modules/correo.py`):
- **Outlook de escritorio** vía COM (`pywin32`, ya en uso) cuando está instalado y abierto.
- **Microsoft Graph** (`modules/correo_nube.py`) cuando no lo está o es el **Outlook
  nuevo** (`olk.exe`), que no tiene API local. El buzón solo acepta `AUTH=XOAUTH2`,
  así que OAuth2 de código de dispositivo es el único camino (y no necesita
  registrar ninguna aplicación: se usa un cliente público de Microsoft).*

## Fase 2 — reuniones (prioridad 2)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 2.1 | Grabar y transcribir | ✅ | `modules/meeting_assistant.py` (audio del sistema + micrófono, Whisper local). |
| 2.2 | Acta con responsables, fechas y tareas | ✅ | `MeetingAssistant.analizar_transcripcion`: acta con resumen ejecutivo, participantes, temas con datos concretos, decisiones, tareas con responsable/fecha/prioridad, información rescatada (cifras, fechas, versiones, sistemas), riesgos, preguntas abiertas y próxima reunión. Las grabaciones largas se analizan por trozos, y la cabecera lleva título, fecha, duración y asistentes. |
| 2.3 | Agenda previa de la reunión | ✅ | `AGENDA_REUNION`: lee el calendario (`modules/calendario_tools.py`) y la IA redacta la agenda. |
| 2.4 | Resumen ejecutivo y envío a asistentes | ✅ | `ENVIAR_ACTA`: correo con el acta a los asistentes del acta, a los de la reunión grabada o a los invitados del calendario; borrador salvo pedido explícito. |
| 2.5 | **Aviso de escritorio cuando el acta está lista** | ✅ | `modules/notificaciones.py`: toast del centro de notificaciones de Windows por WinRT (PowerShell 5.1 con el script en `-EncodedCommand` y el texto por variables de entorno, para que acentos, comillas y saltos no rompan la orden), sin dependencias nuevas y en su propio hilo (`avisar` devuelve al momento). El nombre «Jarvis» con el que se firma el aviso se registra en `HKCU\Software\Classes\AppUserModelId\Jarvis.Asistente` la primera vez (idempotente y sin permisos de administrador); si PowerShell falta o falla, se apunta en la consola y la tarea sigue. `MeetingAssistant` avisa por `on_notificar`, que la ventana conecta en `AppGUI._notificar_reunion` (toast **y** burbuja en el chat, donde se pregunta «¿ya?»): «Reunión detectada» al empezar a grabar, «Reunión terminada» al empezar a transcribir (una reunión larga tarda minutos), «Acta lista · acta_…md» al guardarla y un aviso honrado si no hubo audio o no se pudo transcribir. Cubierto por `tests/pruebas_reunion.py` con PowerShell simulado (no muestra toasts ni toca el registro). |
| 2.6 | **Grabar sin cortes (`data discontinuity`)** | ✅ | El audio del sistema se grababa con el búfer de WASAPI por defecto (el periodo mínimo, ~10 ms): el hilo de Python no llegaba a vaciarlo y soundcard marcaba cada bloque como discontinuo, perdiendo trozos de la reunión y llenando la consola. Ahora `MeetingAssistant.BUFFER_LOOPBACK` (5 s a 16 kHz) le da a WASAPI sitio de sobra para esperar al hilo y los avisos que queden se cuentan y se resumen en una línea al terminar, en vez de repetirse cada bloque. Se lee a trozos de 1/4 s (así la grabación se para en cuanto se pide) y lo que queda en el búfer al cerrar se recupera con `rec.flush()`, para no perder el final de la reunión. |

Acciones de reuniones añadidas en la fase 2 (además de grabar y terminar):

| Acción | Para qué |
|---|---|
| `REUNIONES\|n` | Lista las actas guardadas, numeradas para poder pedirlas. |
| `LEER_ACTA\|clave` | La IA presenta el acta (acuerdos y tareas). La clave es el número del listado o parte del título. |
| `REHACER_ACTA\|clave` | Vuelve a generar el acta desde la transcripción y conserva cabecera y transcripción. |
| `ASISTENTES_REUNION\|clave` | Asistentes del acta o, si no hay, invitados del calendario. |
| `ENVIAR_ACTA[|correos][;;clave][;;enviar]` | Correo con el acta (borrador salvo `;;enviar`). |
| `AGENDA_REUNION[|días o asunto]` | Agenda previa a partir de las próximas reuniones del calendario. |

## Fase 3 — calendario y tiempo (prioridad 4)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 3.1 | Leer calendario y proponer huecos | 🟡 | `modules/calendario_tools.py` ya lee la reunión en curso, las próximas e invitados (fase 2). Falta detectar huecos libres. |
| 3.2 | Crear, mover y reprogramar eventos | ❌ | `AppointmentItem`: `Start`, `End`, `Subject`, `Invitees`, `Save`/`Send`. |
| 3.3 | Bloqueo de tiempo de foco | ❌ | Evento "Foco" + aviso al empezar y terminar. |
| 3.4 | Recordatorios, tareas y hábitos | ❌ | `olFolderTasks` + `modules/habitos.py` con seguimiento semanal. |
| 3.5 | Modo "no molestar" según calendario | ❌ | Hilo del programador (0.7) que consulta el calendario y silencia avisos. |

## Fase 4 — documentos (prioridad 3)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 4.1 | Leer PDF/Word/Excel/CSV existentes | 🟡 | Falta la acción directa de 0.3 (hoy solo funciona adjuntando el archivo al chat). |
| 4.2 | Editar documentos existentes | ❌ | `python-docx`/`openpyxl`/`python-pptx` permiten reescribir: buscar y reemplazar y edición por secciones. |
| 4.3 | Comparar versiones | ❌ | `difflib` sobre el texto extraído de dos rutas. |
| 4.4 | Firmar, exportar y convertir | 🟡 | `fpdf2` y `python-docx` ya crean; para convertir se puede usar Word/Excel por COM (exportar a PDF). |
| 4.5 | Plantillas reutilizables | 🟡 | Ya hay plantilla `.pptx` y documentos de preventa; faltan plantilla de acta e informe. |
| 4.6 | Documentos de preventa | ✅ | `GENERAR_PREVENTA` (propuesta, requisitos, historias, glosario, resumen, estimación). |

## Fase 5 — datos y análisis

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 5.1 | Consultar bases de datos en lenguaje natural | ❌ | `sqlite3` (incluido en Python) para empezar; SQL Server/PostgreSQL con `pyodbc`. |
| 5.2 | Gráficos, tableros y KPIs | ❌ | `matplotlib` (no instalado) o tablero `.html` autocontenido con Chart.js. |
| 5.3 | Informes periódicos | ❌ | Programador (0.7) + generador de informe + correo (fase 1). |
| 5.4 | Llenado de matrices (Excel/OneDrive/SharePoint/Azure DevOps) | ✅ | `modules/cloud_matrix.py` (`MATRIZ_NUBE`, `MATRIZ_EXCEL`, `MATRIZ_AZURE`). |

## Fase 6 — código y desarrollo

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 6.1 | Revisar PRs, leer diffs y comentar | ❌ | `git` local ya está; GitHub/Azure Repos necesitan token personal. |
| 6.2 | Explicar y refactorizar código | ❌ | Acción `REVISAR_CODIGO|ruta`: leer archivos (0.3) y analizarlos con la IA. |
| 6.3 | Ejecutar pipelines y avisar de fallos | ❌ | `EJECUTAR_PIPELINE` con `docker`/`git` locales; CI remoto necesita token. |
| 6.4 | Mensajes de commit | ✅ | `GENERAR_COMMIT` (Conventional Commits desde el diff). |
| 6.5 | Documentar automáticamente | ❌ | Generar README/docstrings por archivo o carpeta. |
| 6.6 | Comandos de terminal seguros | 🟡 | `COMANDOS_SEGUROS` ya existe; conviene ampliarlo desde la config y añadir lista de bloqueo. |


## Fase 7 — gestión del trabajo

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 7.1 | Azure DevOps: crear, mover y cerrar tareas | 🟡 | Hoy crea work items desde la matriz; faltan consultar, mover y cerrar (mismo PAT de la config). |
| 7.2 | Jira / Trello | ❌ | API REST con `urllib` (no hay `requests`): token + correo (Jira) o key/token (Trello). |
| 7.3 | Seguimiento de sprints y métricas | ❌ | Consultas a la API + informe (5.3). |
| 7.4 | Resumen diario hecho/pendiente | ❌ | Notas + auditoría (0.5) + reuniones + correo. |

## Fase 8 — preventa y cliente

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 8.1 | Investigar cuentas y preparar briefs | ❌ | Búsqueda web (`BUSCAR`) + IA; sin API adicional. |
| 8.2 | Propuestas y estimaciones desde requerimientos | 🟡 | `GENERAR_PREVENTA` cubre el grueso; falta la estimación por horas/equipo desde una tabla. |
| 8.3 | Seguimiento de oportunidades y recordatorios | ❌ | Almacén SQLite (5.1) + programador (0.7). |

## Fase 9 — entorno de trabajo

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 9.1 | Control de ventanas y monitores | 🟡 | Ya hay segundo monitor, minimizar, maximizar, foco y cerrar; faltan dividir pantalla y mover a monitor 2/3 por nombre. |
| 9.2 | Abrir/cerrar apps, pantalla completa | ✅ | `ABRIR_APP`, `CERRAR_APP`, `SISTEMA|*`. |
| 9.3 | Volumen del sistema y por app | ✅ | `VOLUMEN`, `VOLUMEN_APP`. |
| 9.4 | VPN y entornos de prueba | ❌ | Lanzar el cliente VPN y esperar la conexión; `docker compose` ya está disponible. |
| 9.5 | Perfiles de entorno | 🟡 | `PERFIL` existe (desarrollo/oficina/cierre); conviene definirlos en la config (apps, webs, carpetas). |

## Fase 10 — automatización

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 10.1 | Flujos encadenados | ❌ | `[ACCION: FLUJO|paso1 ;; paso2 ;; paso3]` en orden, pasando el resultado de cada paso al siguiente. |
| 10.2 | Tareas programadas y recurrentes | ❌ | Programador (0.7). |
| 10.3 | Voz en segundo plano y palabra clave | ❌ | Modo continuo en `voice_engine.py` con palabra de activación. |
| 10.4 | Dictado de texto | ✅ | `DICTADO_ON` / `DICTADO_OFF`. |

## Fase 11 — memoria y contexto (base: 0.4)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 11.1 | Recordar proyectos, rutas y personas | ❌ | `memoria.md` estructurado + acción `RECORDAR|clave: valor`, inyectado en el prompt. |
| 11.2 | Historial de actividad ("retomemos lo de ayer") | ❌ | Auditar (0.5) y resumir por fecha. |
| 11.3 | Reglas permanentes configurables | ✅ | `RECORDAR_REGLA`, `LEER_REGLAS`, `BORRAR_REGLAS` y editor en Ajustes. |

## Fase 12 — personal

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 12.1 | Finanzas básicas y recordatorios de pago | ❌ | SQLite + programador. |
| 12.2 | Viajes: itinerarios, check-in y reservas | ❌ | Correo (fase 1) + calendario (fase 3) + IA. |
| 12.3 | Resumir artículos, papers y vídeos | 🟡 | `yt-dlp` ya trae subtítulos; faltan `RESUMIR_VIDEO|url` y `RESUMIR_ARTICULO|url`. |
| 12.4 | Generación de imágenes y diagramas | ❌ | Diagramas con Mermaid (`node` está instalado) o Graphviz; imágenes con API externa. |
| 12.5 | Clima y briefing matutino | ✅ | `CLIMA`, `BRIEFING`. |
| 12.6 | **Tutor de inglés** (corregir, explicar, practicar, hablar y llevar el avance) | ✅ | `modules/english_tutor.py` + **apartado propio** en la ventana (botón «🎓 Inglés» de la barra lateral; el chat ya no reparte clases). Detección **local** de los fallos típicos de un hispanohablante (concordancia, 3.ª persona, `did` + pasado, calcos como *explain me* o *I have 30 years*, incontables, ortografía, preguntas mal montadas): sin IA y sin internet, con el «por qué» de cada regla. La clase completa la escribe la IA con `APIBrain.SISTEMA_TUTOR` (marca `__TUTOR__`), que responde en Markdown sin recortar y sin leer comandos de acción. Estado en `Jarvis/ingles/estado.json` (nivel A1-C2, prácticas y errores repetidos, con tope de 20 eventos). **«🗣 Speaking»**: `speaking()` prepara la charla hablada (su respuesta va en su propio apartado, «💬 Lo que digo yo», para que sea lo único que suena), el apartado pone el micrófono en inglés (`VoiceEngine.escuchar_ingles`, sin palabra de activación y con las mayúsculas arregladas) y la réplica se lee en voz alta con voz inglesa (`VoiceEngine.voz_ingles` / `hablar(..., idioma="en")`). Cubierto por `tests/pruebas_ingles.py` y `tests/pruebas_gui_ingles.py`. |
| 12.7 | **Aspecto de la ventana** (paleta en capas, tarjetas con iconos, acento, Markdown en el chat y caja expansible) | ✅ | Rediseño visual de la ventana (hoy repartido entre `ui/tema.py` y `views/`, ver 12.12). **Paleta en capas** (`COLOR_FONDO` < `COLOR_PANEL` < `COLOR_TARJETA` < `COLOR_TARJETA_ALTA`), un acento único (turquesa `COLOR_ACENTO`, con `COLOR_ACENTO_2` para el degradado de la barra superior que se genera con PIL) y texto oscuro sobre el acento (`COLOR_ACENTO_TEXTO`, contraste ≥ 4.5:1). Los paneles son **tarjetas** (`_tarjeta()`, radio 16, borde suave) que se encienden con el acento cuando están activas: la caja de escritura al escribir en ella (`_glow_input`), el apartado abierto en la barra lateral y la tarjeta de la versión corregida. La clase del tutor llega como **una tarjeta por apartado** con su icono (`_secciones_de_clase` / `_tarjeta_clase`), con los bloques de código y las tablas en monoespaciada sobre fondo propio y las negritas en el acento; el historial del chat lleva avatar y nombre, y las conversaciones de la barra lateral son tarjetas con icono, fecha y resumen. **Los mensajes del asistente se ven con su formato**: el Markdown se pinta de verdad en la burbuja (`_area_markdown_burbuja` + `_crear_area_markdown`, el mismo `tk.Text` sin marco que usan las tarjetas: títulos, negritas en el acento, listas, citas, tablas y código en monoespaciada; el clic ahí selecciona texto, no marca el mensaje) y el alto se mide con `count(..., "end", "displaylines")` —con «end-1c» Tk no cuenta el último renglón partido y se recortaba el final—. La **caja de escritura crece hacia abajo** de una a siete líneas (`_ajustar_alto_input`, `ALTO_INPUT_*`; `Enter` envía y `Shift+Enter` salta de línea) con su aviso escrito a mano (`AVISO_INPUT`, un `CTkTextbox` no trae placeholder) y su altura de línea en gris al escribir encima. El pie de la barra lateral enseña **tu nombre** (`_pintar_usuario`, campo «Tu nombre» de Ajustes → `usuario` en `config_usuario.json`): el nombre de la sesión de Windows ya no se usa, y `APIBrain._prompt_usuario()` lo inyecta en el mensaje de sistema para que lo recuerde. Micrófono redondo en la caja de entrada (`btn_mic` + `marco_mic`) con anillo que late mientras escucha (`_pulso_mic`), y lo mismo en el apartado de inglés (`btn_ingles_mic` + `_pulso_ingles`) para el speaking. Tipografía elegida entre las instaladas (Inter/Poppins → *Segoe UI Variable Text* → *Segoe UI*) con `_resolver_fuentes()`. Cubierto por `tests/pruebas_gui_estilo.py` y `tests/pruebas_gui_perfil.py`. |
| 12.8 | **Atajos de teclado de las cajas de escribir** (`Ctrl+Supr` para la línea entera, `Ctrl+A`, deshacer…) | ✅ | Tk trae en las cajas de texto pocos atajos (los de Emacs: `Ctrl+K`, `Ctrl+D`…) y le faltan justo los que se dan por hechos en Windows; ahora los pone la ventana: `ATAJOS_CAJA` (cajas de escribir, con `_atajos_caja()`) y `ATAJOS_CAMPO` (campos de una línea, con `_atajos_en_campos()`, que recorre los `CTkEntry` de todas las vistas al montar la interfaz). **Cajas** (chat, «Tu inglés» y reglas permanentes, las tres con `undo=True`): `Ctrl+Supr` borra la línea entera con su salto (`_borrar_linea_caja` + `_quitar_lineas`: con algo seleccionado se lleva las líneas que toca la selección, y en la última línea quita también el salto de la anterior para no dejar un renglón en blanco), `Ctrl+Mayús+Supr` del cursor al final de la línea (y si ya está al final, junta con la siguiente), `Ctrl+Retroceso` la palabra anterior (`_borrar_palabra_caja`, sin salirse de la línea: al principio de una línea junta las dos sin comerse la de arriba), `Ctrl+A` el mensaje entero (`_seleccionar_todo_caja`: el `<<SelectAll>>` de Tk se llevaba también el salto de línea del final, y en una caja vacía dejaba algo seleccionado), `Ctrl+Z` deshacer y `Ctrl+Y` rehacer (y `Ctrl+Mayús+Z`, que también queda enlazado) con el `undo` de Tk —el historial se reinicia (`edit_reset`) al dejar el aviso de la caja vacía (`_poner_fantasma`) y al cargar las reglas guardadas, para que `Ctrl+Z` no devuelva ni el aviso ni el mensaje ya enviado— y `Ctrl+←`/`Ctrl+→` (con `Mayús`, ir seleccionando) mueven de palabra delegando en los eventos virtuales del propio Tk (`<<PrevWord>>`, `<<SelectNextWord>>`…). Editar con un atajo pasa por `_despertar_caja()` (se lleva el aviso del chat si estaba) y `_tras_editar_caja()` (revisa el aviso y recalcula el alto de la caja). **Campos** (`CTkEntry`: tu nombre, la API Key, el tema de inglés…): `Ctrl+A`, `Ctrl+Retroceso` y `Ctrl+Supr`, resueltos mirando el texto porque los `Entry` no entienden el `wordstart` ni el `insert -1c` de Tk. Cubierto por `tests/pruebas_gui_atajos.py`, que pulsa las teclas de verdad. |
| 12.9 | **Música en Spotify** (poner la canción de verdad, no dejar una búsqueda abierta en el navegador) | ✅ | `REPRODUCIR_MUSICA\|artista canción`: resuelve la **pista exacta** sin claves de API (el buscador devuelve el enlace de Spotify y la ficha pública `oembed` confirma el título) y la abre en el reproductor, que es lo que suena. Después **comprueba** que esa canción está sonando —con música sonando la ventana de Spotify se titula con la canción, así que `_sonando_en_spotify` compara títulos— y solo entonces dice «poniendo»: si no puede comprobarlo, lo dice. Si Brave está abierto con depuración, pulsa el play del reproductor web por CDP (`JS_REPRODUCIR` sobre `navegador_cdp.pestana_de`), igual que se hace con SharePoint; si no, deja la pista cargada (Brave bloquea el autoplay). La consulta se normaliza (`_consulta_legible`: la IA a veces manda «Junior+H+Las+noches»). Sin la aplicación instalada deja la búsqueda en el reproductor web y lo dice. `MUSICA\|pausa`, `MUSICA\|siguiente` y `MUSICA\|anterior` pulsan el mando del reproductor web cuando se controla por CDP y, si no, mandan las teclas multimedia al reproductor que esté sonando. **Ya no se pulsa ninguna tecla a ciegas**: entre la comprobación del foco y el teclazo el foco podía cambiar y el `Enter` acababa escribiendo en otra ventana (visto en este equipo). El prompt de `api_brain.py` manda la música a `REPRODUCIR_MUSICA`, prohíbe ponerla con `BUSCAR` (de ahí salía el «Buscando … en Brave» que no suena nada) y hace que la acción se repita si el usuario dice que no ha sonado. Cubierto por `tests/pruebas_musica.py`. |
| 12.10 | **Música por la API de Spotify** (poner la canción sin abrir ni enfocar nada) | ✅ | `modules/spotify.py`: OAuth2 con **PKCE** (solo el *Client ID* de una app propia, **sin secreto**; redirección local `http://127.0.0.1:8888/callback`), token de refresco **cifrado con DPAPI** en `config_usuario.json` → `spotify` y renovación perezosa con reintento si la API contesta 401. `SystemActions.reproducir_en_spotify` intenta **primero la API** (buscar la pista exacta y mandarla al dispositivo con `/me/player/play`; prefiere un `computer` activo o el de `spotify.dispositivo`) y solo dice «poniendo» cuando Spotify confirma que suena; si no hay sesión, no hay dispositivo o la cuenta no es **Premium** —Spotify no deja controlar la reproducción desde fuera— se cae al camino anterior (resolver la pista y dejarla cargada) contando el motivo. `control_musica` manda `pausa`, `reanudar`, `siguiente` y `anterior` por la API (`_controlar_con_api`) y, si no, usa el reproductor web o la tecla multimedia. Ajustes: **«Conectar Spotify»**, «Client ID» (diálogo con el Redirect URI exacto y el dispositivo preferido) y «Desconectar», con el estado de la cuenta a la vista; consola propia (`python -m modules.spotify entrar\|probar\|dispositivos\|poner\|salir`). Cubierto por `tests/pruebas_musica.py` con el cliente de la API simulado (`SpotifyFalso`) y `tests/pruebas_gui_spotify.py` (la sección de música de Ajustes: botones, estado de la cuenta y aviso de Premium). |
| 12.11 | **Aprender programación: taller de Java con revisión en vivo** (corregir, compilar y ejecutar sin salir de la ventana) | ✅ | `modules/programming_tutor.py` + apartado propio (botón «💻 Programar»), con `revisar` en dos capas: un **analizador propio y local** (llaves, paréntesis y corchetes sin cerrar, `;` que faltan, comillas sin terminar, `=` donde iba `==`, `string` en minúscula, `printline`, `if` sin paréntesis, comparar textos con `==`…) que devuelve cada fallo con su **línea, su columna, el mensaje y la pista**, y el **`javac` de verdad** cuando hay JDK (salida forzada en inglés para poder leerla, `CREATE_NO_WINDOW`, tope de `TIEMPO_COMPILAR`); `_combinar_errores` une las dos listas sin repetir y `_es_estructural` calla el ruido en cascada del compilador cuando el fallo es una llave sin cerrar. La ventana revisa **al dejar de teclear** (700 ms, `_revision_diferida` → `_revisar_programacion(compilar=False)`) y pinta los avisos en su panel (`_avisos_de_revision`: cabecera con el recuento, un aviso por línea con `línea N, columna M` y «→ pista», `MAX_AVISOS_PANTALLA` y «… y N más»), sin gastar IA; *Corregir* repite con `compilar=True`, apunta la práctica (`registrar`) y refresca la cabecera, y *Probar* compila y ejecuta el programa con su entrada por teclado en un hilo aparte (`ejecutar`, `TIEMPO_EJECUTAR`, `MAX_SALIDA`). El temario (`BASES`, 12 temas con sintaxis, ejemplo comentado, errores típicos y ejercicio), la guía de la API (`DOCUMENTACION`), las comparaciones (`COMPARACIONES`) y el avance se leen **sin conexión**; solo ejercicios, dudas y los temas que no están en las tablas se piden a la IA con `APIBrain.SISTEMA_PROGRAMADOR` (encargo con `MARCA_PROFE`, como el `__TUTOR__` del inglés). El centro tiene **dos caras** (`PANEL_PROG_CLASE` / `PANEL_PROG_CHAT`, dos pestañas de botón que se pintan como el resto de la ventana: la puesta de acento y la otra en tarjeta): la clase en tarjetas y un **chat propio del taller**, una conversación independiente de la de Jarvis (*Preguntar* lleva ahí la duda de «Tema»; `enviar_chat_programacion` → `ProgrammingTutor.conversar`, que mete en el encargo el código, los fallos que se le repiten y **el hilo** de lo ya hablado —`_hilo_en_texto`, últimos `MAX_TURNOS_CHAT` turnos y `MAX_HILO_CHAT` caracteres—; la respuesta vuelve en un hilo aparte con `_pedir_chat_prog`/`_mostrar_chat_prog` y se pinta con el mismo Markdown de las tarjetas, `Enter` envía y `Mayús+Enter` salta de línea). Cada conversación se guarda aparte, en `Jarvis/programacion/chat_taller_<fecha>.md` (`_apuntar_turno_chat`), y *Nuevo* (`nuevo_chat_programacion`) empieza otra sin borrar la anterior. Nivel (Principiante/Intermedio/Avanzado), prácticas y fallos repetidos en `Jarvis/programacion/estado.json` (`MAX_EVENTOS`, `MAX_CODIGO`). Cubierto por `tests/pruebas_programacion.py` y `tests/pruebas_gui_programacion.py` (revisión al entrar y al teclear, *Corregir* con su práctica, *Probar* con lo que imprime el programa, las tablas sin IA, el nivel, el borrado confirmado y la vuelta al chat sin tocar la conversación; y el chat del taller: las pestañas Clase/Chat, `Enter` y `Mayús+Enter`, la memoria del hilo dentro del encargo, que no se cuela en el chat de Jarvis y su `.md` guardado). |


| 12.12 | **La ventana, en apartados independientes** (cada apartado es una vista con su módulo) | ✅ | `app_gui.py` vuelve a ser el armazón —barra lateral, barra superior, cambio de apartado (`_mostrar_vista`), historial de conversaciones, escucha por voz (dictado) y los servicios compartidos (`APIBrain`, `SystemActions`, `VoiceEngine`, `VoiceOutput`)— y cada apartado vive en su módulo de `views/` como una **vista** propia: `views/base.py` (`Vista`, un `CTkFrame` que recibe la ventana en `self.app`, con el estado en `_preparar` y los widgets en `_construir`), `views/chat.py` (`VistaChat`), `views/ingles.py` (`VistaIngles`), `views/programacion.py` (`VistaProgramacion`) y `views/ajustes.py` (`VistaAjustes`). Lo que se repite está en la base (atajos de las cajas, Markdown de burbujas y tarjetas, `crear_documento_txt`, un único bucle de `after` en la ventana) y el estilo en `ui/tema.py` (paleta, fuentes y medidas; `FUENTE_UI`/`FUENTE_MONO` se resuelven al montar la ventana y se leen como `tema.FUENTE_UI`). Los diálogos y el explorador cuelgan de la ventana, no del marco del apartado. La ventana ya no guarda widgets de ningún apartado: los monta, los enseña y los esconde (`pack`/`pack_forget`) y conserva `app.<widget>` con un puente (`__getattr__`/`__setattr__`) para no romper las pruebas ni los callbacks antiguos. Cubierto por las pruebas de la GUI, que ahora miran el módulo de cada apartado (`tests/pruebas_ingles.py` y `tests/pruebas_programacion.py` incluidos). |

El tutor de inglés **no usa acciones del chat**: tiene su apartado, con un botón por
tarea (`views/ingles.py` → `TAREAS_INGLES`) y su propio panel para la clase:

| Botón | Para qué |
|---|---|
| Corregir | Corrige el texto de la caja «Tu inglés»: pistas locales + corrección de la IA. |
| Conversar | Conversación en inglés: contesta, corrige, traduce y cede el turno. |
| Speaking | Charla **hablada**: el micrófono escucha en inglés, la IA contesta y la réplica se lee en voz alta (voz inglesa). |
| Ejercicios | Ejercicios con soluciones (tema y cuántos, con techo de 10). |
| Explicar | Clase paso a paso de gramática o uso (*for* y *since*, presente perfecto…). |
| Vocabulario | Vocabulario con pronunciación para hispanohablantes. |
| Repaso | Repaso de lo que más se le repite, tirando de los errores guardados. |
| Mi avance | Resumen del avance (sin IA, respuesta lista). |
| Borrar | Borra el historial de errores (pide confirmación la segunda vez). |

Y en la cabecera del apartado: el **nivel** (A1-C2 en un desplegable, con el botón en
el color de acento), el resumen del alumno (`EnglishTutor.resumen()`, en su tarjeta de
estado) y los botones de **copiar** y **guardar** la clase en documentos.

La clase **no se enseña como un bloque de texto**: `_escribir_clase()` trocea la
respuesta por sus títulos de Markdown y pinta una tarjeta por apartado (con el icono
que manda la IA delante), las listas con su viñeta, las negritas en el acento y los
bloques de código y tablas en monoespaciada sobre fondo oscuro. La tarjeta de la
«Versión corregida» lleva el borde encendido: es lo que el alumno se lleva.

El **Speaking** es el único botón que no prepara una clase escrita: enciende el
micrófono del apartado (`_toggle_speaking` → hilo propio con
`VoiceEngine.escuchar_ingles`), pasa lo oído a `EnglishTutor.speaking()` y pinta el
turno (`«🗣 Tú has dicho»` + la clase). De esa clase solo se lee en voz alta la
réplica en inglés (`_resumir_en_voz()` saca el apartado «💬 Lo que digo yo» y limpia
el Markdown), con la voz inglesa de `VoiceEngine`; la corrección, la pronunciación y
el turno siguiente quedan por escrito. Se apaga pulsando otra vez, al encender el
micrófono del chat o al salir del apartado.

El **taller de programación** (Java) tampoco usa acciones del chat: tiene su apartado
(botón «💻 Programar») y un botón por tarea (`app_gui.TAREAS_PROGRAMACION`):

| Botón | Para qué |
|---|---|
| Corregir | Revisa el programa del editor y apunta los fallos al avance: analizador propio + `javac`. |
| Bases | El temario del curso, tema por tema (tabla `BASES`), sin IA. |
| Lección | El tema que se escriba en «Tema» (tabla `BASES`), sin IA. |
| Ejercicios | Ejercicios con soluciones del tema o de los fallos que más se repiten (IA). |
| Documentación | Guía de las clases que más se usan al empezar (tabla `DOCUMENTACION`); si no está, IA. |
| ¿Por qué…? | Comparaciones razonadas (`==` frente a `equals`…, tabla `COMPARACIONES`); si no está, IA. |
| Preguntar | Una duda suelta, con el código delante (IA). |
| Probar | Compila y ejecuta el programa con su entrada por teclado, en un hilo aparte. |
| Mi avance | Nivel, prácticas y fallos repetidos (`ProgrammingTutor.progreso()`), sin IA. |
| Borrar | Borra el avance (pide confirmación la segunda vez). |

En la cabecera: el **nivel** (Principiante, Intermedio, Avanzado, en un desplegable) y
el resumen del alumno (`ProgrammingTutor.resumen()`), que cuenta las prácticas y el
fallo que más se repite; al lado de la revisión se dice si hay **JDK** o si solo se
revisa lo básico. La **revisión en vivo** no es un botón: el editor la lanza al dejar
de teclear (700 ms, `_revision_diferida`) y pinta los avisos en su propio panel
(`_pintar_avisos`), un aviso por línea con su **línea, su columna y su pista**, que es
lo que se lee para arreglar el programa de arriba abajo (`MAX_AVISOS_PANTALLA` y «… y
N más»); no gasta IA. *Corregir* repite la revisión con `compilar=True` (y `javac` si
está), apunta los fallos con `registrar()` y enseña el texto de `revisar()` en las
tarjetas. *Probar* va en un hilo (`_probar_programacion`) para que la ventana no se
congele y enseña la salida en las tarjetas. El avance se guarda en
`Jarvis/programacion/estado.json` y lo que se ve se puede copiar o guardar como `.md`.
Todo esto se cubre con `tests/pruebas_programacion.py` (el módulo) y
`tests/pruebas_gui_programacion.py` (el apartado: revisión al entrar y al teclear,
*Corregir*, *Probar* con lo que imprime el programa, las tablas sin IA, el nivel, el
borrado confirmado y la vuelta al chat).

## Fase 13 — seguridad y control (base: 0.5 y 0.6)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 13.1 | Autenticación y permisos por tarea | ❌ | 0.6. |
| 13.2 | Registro y auditoría de acciones | ❌ | 0.5. |
| 13.3 | Modo privado | ❌ | Marca de sesión que no guarda historial ni adjuntos y limita las acciones a solo lectura. |

---

## Credenciales que harán falta más adelante

| Función | Qué se necesita |
|---|---|
| Correo y calendario | Nada para el Outlook de escritorio (COM, perfil MAPI ya configurado). Para el **Outlook nuevo o con Outlook cerrado**: conectarlo una vez con el código de Microsoft (*Ajustes → Conectar correo*), sin contraseña ni registrar aplicaciones. |
| Teams / Slack / WhatsApp | Token de Slack (`chat:write`, `channels:history`) o app de Azure para Teams. |
| Jira / Trello | API token + correo (Jira) o key/token (Trello). |
| Azure DevOps (consultar y mover) | El mismo PAT que ya se usa para la matriz. |
| GitHub / Azure Repos | Token personal para revisar PRs. |
| Generación de imágenes | Clave de la API que se elija (DeepSeek no genera imágenes). |

## Orden de trabajo

1. **Correo bidireccional** (fase 1) — hecho: Outlook COM y, si no está, el correo por la nube (Graph)
2. **Reuniones** (fase 2) — hecho: acta con responsables, agenda previa, envío del acta y aviso de escritorio al terminar
3. Cimientos: **lectura de archivos por ruta** (0.3), memoria (0.4) y auditoría (0.5)
4. Calendario y tareas (fase 3)
5. Mensajería Teams/Slack
6. Automatización y tareas programadas (0.7 y fase 10)
7. Gestión (fase 7), entorno (fase 9) y personal (fase 12)
8. **Tutor de inglés** (12.6) — hecho: tiene su apartado en la ventana (no el chat),
   detecta los fallos en local, explica, pone ejercicios, mantiene la conversación,
   **habla contigo** («🗣 Speaking»: micrófono en inglés y réplica en voz alta) y
   lleva el avance del alumno
9. **Aspecto de la ventana** (12.7) — hecho: paleta oscura en capas con el acento
   turquesa, tarjetas con icono en el chat, en la barra lateral y en la clase del
   tutor, bordes que se encienden cuando algo está activo, micrófono con su onda,
   los mensajes del asistente con su **Markdown** de verdad, la **caja de escritura
   que crece hacia abajo** y tu **nombre** guardado en Ajustes para que el asistente
   lo recuerde
10. **Atajos de las cajas de escribir** (12.8) — hecho: `Ctrl+Supr` borra la línea
    entera, `Ctrl+Retroceso` la palabra anterior, `Ctrl+A` el mensaje, `Ctrl+Z`/`Ctrl+Y`
    deshacen y rehacen y `Ctrl+←`/`Ctrl+→` saltan de palabra a palabra; los campos de
    Ajustes llevan `Ctrl+A`, `Ctrl+Retroceso` y `Ctrl+Supr`
11. **Música en Spotify** (12.9) — hecho: «pon *Las noches* de Junior H» resuelve esa
    pista, la abre en el reproductor y **comprueba** que suena (el título de la ventana
    de Spotify es el de la canción) antes de decir que la ha puesto; si no puede
    comprobarlo lo dice, y si Brave está abierto con depuración le da al play él mismo
    por CDP. `pausa`, `siguiente` y `anterior` van al mando del reproductor web o a las
    teclas multimedia, y la IA ya no puede resolverlo con una búsqueda en Brave que no
    suena
12. **Música por la API de Spotify** (12.10) — hecho: con la cuenta conectada en Ajustes
    (OAuth2 con PKCE: solo el *Client ID* de una app propia, sin secretos), «pon *Las
    noches* de Junior H» se pone por la API oficial —buscar la pista y mandarla al
    dispositivo— **sin abrir ni enfocar ninguna ventana**, y `pausa`, `reanudar`,
    `siguiente` y `anterior` van igual de directos. Sin sesión conectada, sin dispositivo
    a la vista o sin cuenta Premium se sigue por el camino de siempre (resolver la pista y
    dejarla cargada) y se cuenta por qué; el token se guarda cifrado con DPAPI

