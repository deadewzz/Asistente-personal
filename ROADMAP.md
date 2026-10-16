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
| 0.9 | **Clasificar archivos de SharePoint sin Graph** | ✅ | `modules/sharepoint.py` + `modules/navegador_cdp.py` + acción `CLASIFICAR_ARCHIVOS|origen;;destino;;regla`: controla Brave por CDP (sin descifrar cookies) para listar con la sesión del usuario, clasifica con la IA y mueve por la API `_api` de SharePoint. Acepta la URL tal cual la copia SharePoint (`.../Forms/AllItems.aspx?viewid=...`: se queda con la carpeta, y respeta `RootFolder=`/`id=`). Antes de fiarse de un listado comprueba que la carpeta/archivo existen de verdad, porque `_api` responde **200 con lista vacía** a rutas que no existen: con eso, una carpeta mal escrita parecía vacía y un choque de nombres podía pasar inadvertido. Nunca pisa el destino y, si no puede comprobarlo, no mueve. |
| 0.10 | **Copiar archivos entre sitios (bajar y subir)** | ✅ | `SharePoint.descargar` / `subir` / `copiar` / `borrar_archivo` en `modules/sharepoint.py`: la API de SharePoint solo sabe mover o copiar **dentro del mismo sitio** (`MoveTo`/`CopyTo`), así que para llevar archivos a tu OneDrive se baja el archivo por `$value` (base64, tope de 25 MB por archivo) y se vuelve a subir con `Files/add` (respaldo `AddUsingPath` para nombres con `#`, `%`, `&`), con el `X-RequestDigest` de la sesión de Brave. `CLASIFICAR_ARCHIVOS` decide solo: mismo sitio → **mueve**; sitios distintos → **copia** y avisa en el resumen de que los originales siguen donde estaban. Y `resolver` acepta la URL del sitio «a secas»: le pregunta a SharePoint el nombre de su biblioteca (cambia con el idioma del sitio) y traduce `https://empresa-my.sharepoint.com/` a **tu unidad** (`/personal/<usuario>/Documents`, vía `GetMyProperties`). Validado en vivo con `tests/pruebas_copia_en_vivo.py` (baja y sube de verdad y borra su archivo de prueba). |
| 0.11 | **Recuperarse de una pestaña de Brave muerta** | ✅ | Brave contesta **500** (`Invalid response status`) en el *handshake* cuando el id de la pestaña ya no existe: pasa si el usuario cierra la pestaña, si se reinicia Brave o si el ahorro de memoria la descarta, y dejaba `CLASIFICAR_ARCHIVOS` tirado al copiar entre sitios. `modules/navegador_cdp.py` reconoce ese caso (`ErrorPestana`, que salta **antes** de ejecutar nada, así que reintentar es seguro hasta en las escrituras), insiste un par de veces y abre una pestaña nueva en la misma URL; el mensaje dice qué pasó de verdad (500 = pestaña inexistente, 403 = origen rechazado, sin respuesta = Brave cerrado). `SharePoint._pestana` revalida su caché antes de reutilizarla y `asegurar_navegador` la vacía cuando Brave se reinicia. Se valida con el paso 5 de `tests/diagnostico_brave.py` (en vivo) y con las 14 comprobaciones de «Pestañas muertas y reintentos» en `tests/pruebas_sharepoint.py`. |
| 0.12 | **Copiar entre sitios: acertar con el sitio de la carpeta** | ✅ | `parsear_url` se quedaba con el sitio de la **ruta de la vista** y no con el de la carpeta que trae `id=`/`RootFolder=`. Con la URL de 'Mi unidad' de OneDrive (`https://empresa-my.sharepoint.com/my?id=/personal/<usuario>/Documents/Propuestas`) eso apuntaba a la **raíz** del host `-my`, y ahí una ruta `/personal/...` no existe: SharePoint respondía **403** (`-2147024891, System.UnauthorizedAccessException`) al subir. Ahora `SharePoint._web_de` saca el sitio de la propia carpeta (`/sites/X`, `/teams/X`, `/personal/usuario`), así que `CLASIFICAR_ARCHIVOS` copia al sitio personal de verdad; también arregla un `id=` que apunte a otra biblioteca. Encontrado y validado **en vivo**: 6 comprobaciones nuevas en `tests/pruebas_sharepoint.py` (102 en total, 0 fallos) y camino completo contra el tenant real en `tests/pruebas_copia_en_vivo.py` (`/sites/Preventa-Solutions/Oportunidad/Colombia` → `.../Documents/Propuestas`): baja un PDF de 2,3 MB, lo copia, la copia se lee idéntica al original y se borra; el original no se toca. La prueba en vivo ahora enseña el sitio y la carpeta resueltos, busca el archivo un par de niveles abajo (`$expand=Files`) cuando la carpeta solo tiene carpetas, y prueba `copiar` de punta a punta. |
| 0.13 | **Clasificar entrando en las subcarpetas** | ✅ | `CLASIFICAR_ARCHIVOS` ya no necesita la carpeta exacta: con la carpeta «de arriba» (`/sites/.../Oportunidad/Colombia`, la que solo tiene una carpeta por cliente) `listar_archivos(url, profundidad)` baja `PROFUNDIDAD_BUSQUEDA = 2` niveles. Cada nivel se pide en **una sola llamada** con `$expand=Files` (`_subcarpetas_con_archivos`) en vez de una por carpeta, y todo el listado va **paginado** (`__next` / `$skiptoken`), porque antes un listado de más de 100 elementos se cortaba en silencio. Con topes (`MAXIMO_CARPETAS = 300`, `MAXIMO_ARCHIVOS = 400`) y aviso en `nota_listado` cuando la búsqueda se queda a medias. Ahora cada archivo lleva su `subruta` (`AXA/2024/informe.pdf`), que es lo que se usa como **origen** y lo que ve la IA, mientras que al destino va **solo el nombre** dentro de su subcarpeta (`Actas/informe.pdf`): así dos clientes con un `acta.pdf` cada uno no chocan. La IA clasifica **por tandas** (`TANDA_ARCHIVOS = 30`) y, como puede haber nombres repetidos (`acta.pdf` de varios clientes), `_parsear_clasificacion` solo acepta un nombre corto si es **único**. Y como el mismo encargo puede arrastrar cientos de archivos, con **más de 25** (`UMBRAL_CLASIFICAR`) `_vista_previa_clasificacion` enseña el plan (`AXA/acta.pdf → Actas`) y **no toca nada** hasta que se responda `;;confirmar`. 121 comprobaciones en `tests/pruebas_sharepoint.py` y 20 nuevas en `tests/pruebas_accion_clasificar.py` (SharePoint y la IA simulados: comprueban que se pide el listado con profundidad, que el plan lleva la ruta de cada archivo y que sin confirmación no se mueve nada). (Hoy son 166 y 37 con las de la 0.15). |
| 0.14 | **El chat va diciendo lo que se está haciendo** | ✅ | Con una biblioteca por clientes la clasificación tarda minutos: antes el chat solo enseñaba «Jarvis está escribiendo…» y parecía colgado. Ahora `SharePoint`, `SystemActions` y `APIBrain` tienen un canal de avisos (`on_aviso`, un `(texto)` que pone la ventana) y un `_aviso(texto)` que **siempre** imprime en consola (`[sharepoint]` / `[accion]`), de modo que el trabajo también se puede seguir desde la terminal. `SystemActions._clasificar_archivos` enlaza `sharepoint.on_aviso = self._aviso`, así que **un solo cable** (`system.on_aviso` y `brain.on_aviso`, en `app_gui.py`) recorre toda la cadena. `AppGUI._aviso_progreso` llega desde el **hilo que trabaja** y pinta el paso con `after(0, ...)` en el indicador que ya existía: `_animar_pensando` toma el paso como base (y le sigue animando los puntos) y `_pintar_aviso` **no** baja la conversación si el usuario está leyendo mensajes anteriores; al terminar el aviso se borra y uno que llegue tarde **no** reabre la burbuja. Los pasos que se cuentan son los que explican la espera: el sitio traducido a su biblioteca (`resolver`), Brave abierto o reiniciado, «leyendo la carpeta y bajando a sus subcarpetas», cada nivel («nivel 1 de 2»), cada 25 carpetas, las páginas siguientes del listado (`$skiptoken`), cuántos archivos encontró, las tandas de la IA («clasificando con la IA: 60 de 180»), el plan listo (cuántos van y a qué subcarpetas), el recordatorio de que con muchos archivos **no se ha tocado nada** y cada archivo que pasa («Moviendo 12 de 350: AXA/acta.pdf → Actas»), más los que ya existían, los que no se pudieron comprobar y los que fallaron. Si el canal de avisos se rompe (o no hay ventana), la tarea termina igual. 135 comprobaciones en `tests/pruebas_sharepoint.py` (+14, sección «Avisos de progreso»), 33 en `tests/pruebas_accion_clasificar.py` (+13, sección «El chat va diciendo lo que se hace») y el nuevo `tests/pruebas_gui_progreso.py` (17 comprobaciones, abre la ventana de verdad: el aviso llega desde otro hilo, la animación no lo pisa, no se mueve la vista y al terminar no queda ninguna burbuja colgada). |
| 0.15 | **Archivos grandes: bajarlos a tu PC y subirlos por trozos** | ✅ | SharePoint deja a medias los `MoveTo`/`CopyTo` de unos pocos MB (en este tenant, pasados ~4 MB) y un archivo grande tampoco cabe en un mensaje a la pestaña de Brave, así que a partir de `TAMANO_POR_DISCO = 10 MB` el archivo **se baja a tu PC y se sube al destino**. Bajada: `descargar_a_disco` pide el `$value` **por rangos** (`_api_rango`, `Range: bytes=…`, trozos de `TAMANO_TROZO = 2 MB`) y los va escribiendo en `Jarvis\temp\sharepoint`; si al final no cuadran los bytes con el `Length` que dice SharePoint, se planta en vez de subir algo cortado. Subida: `subir_desde_disco` usa la **subida por trozos** de SharePoint (`_crear_para_trozos` + `StartUpload`/`ContinueUpload(uploadId=guid'…',fileOffset=N)`/`FinishUpload`, `_subir_por_trozos`), con respaldo a `Files/add` de una vez para los que no pasan de 2 MB (y, si la subida por trozos no funciona y el archivo cabe, también). Los pequeños siguen con `MoveTo`/`CopyTo` y, si SharePoint los rechaza con un 400/500, **se reintenta por disco**; un 401/403/404 no se reintenta (ahí bajar tampoco va a dejar) porque se prefiere el error que explica el problema. El movimiento por disco borra el original **solo después de comprobar** que lo que quedó en el destino pesa lo mismo (y si no se puede comprobar, lo deja duplicado y lo dice); si algo falla, **no borra nada** y el mensaje indica la ruta del archivo que quedó en tu PC. `clasificar_y_mover`/`CLASIFICAR_ARCHIVOS` le pasan los `tamanos` que ya venían del listado (sin preguntar `Length` uno a uno) y el plan avisa («2 pasan de 10 MB: esos van bajándolos a tu PC y subiéndolos»), y los avisos del chat cuentan los trozos («bajando informe.pdf a tu PC: 12,0 MB de 23,4 MB…», «subiendo informe.pdf al destino: 6,0 de 23,4 MB…»). De paso: `copiar` entre sitios ya no se rinde con los que pasan de 25 MB (antes avisaba «no cabe»), porque ahora se pasan por disco. 166 comprobaciones en `tests/pruebas_sharepoint.py` (+31, sección «Archivos grandes»), 37 en `tests/pruebas_accion_clasificar.py` (+4) y `tests/pruebas_copia_en_vivo.py` admite un tercer argumento (`gordo`) para probar el camino por disco contra el tenant de verdad (baja el archivo más pesado del origen, lo sube, comprueba el peso y borra la copia). |

| 0.16 | **De esas carpetas solo salen documentos de oficina (los vídeos ni se listan)** | ✅ | En una biblioteca de verdad hay de todo (vídeos de reuniones, fotos, zip, PDF) mezclado con las actas y los informes, y bajar un vídeo de 1,5 GB para clasificarlo es tirar disco y tiempo. `SharePoint.EXTENSIONES_UTILES = (".ppt", ".pptx", ".doc", ".docx")` es ahora la única lista que se pasa: `listar_archivos` y la búsqueda dentro de las subcarpetas (`_solo_utiles`) dejan fuera lo demás **diciendo dónde está** («Me salté 2 archivo(s) que no son ppt, pptx, doc y docx (vídeos y demás: no los bajo ni los muevo). Están en: /sites/Tech/Colombia, AXA»), con las **carpetas y su ruta** en `descartados` y en `nota_listado` (que `CLASIFICAR_ARCHIVOS` ya enseñaba por el chat); los archivos sueltos en la carpeta pedida se apuntan con la ruta de esa carpeta, no con el nombre del archivo. El filtro es además la **red de seguridad**: `_exigir_util` planta `descargar`, `descargar_a_disco`, `mover` y `copiar` si el nombre no es de los suyos (aunque lo pidan por su nombre o venga en un plan viejo, y sin pedirle nada a SharePoint: ni `MoveTo`/`CopyTo` ni `$value`), y `_solo_del_plan` parte el plan en (los que sí, los que no) para decirlo en el resumen («No los toqué (solo ppt, pptx, doc y docx): …») sin bajar ni uno; si el plan era todo vídeos, contesta «No moví nada…» y los deja donde estaban. La extensión sale de `os.path.splitext` en minúsculas (`Informe 2024.12.DOCX` → `.docx`; `informe.docx.exe` no cuela) y `EXTENSIONES_UTILES = ()` pasa todo, que es la forma de quitar el filtro. `probar()` (el diagnóstico de `diagnostico_brave.py`) también añade `nota_listado`, para que una carpeta llena de vídeos no parezca vacía. 189 comprobaciones en `tests/pruebas_sharepoint.py` (+23, nueva sección «Solo documentos de oficina (ppt, pptx, doc y docx)»), 37 en `tests/pruebas_accion_clasificar.py` (trabaja con dobles, así que sigue igual) y `tests/pruebas_copia_en_vivo.py` sube su archivo de prueba con extensión `.docx`, que es lo único que el módulo baja. |
| 0.17 | **Dos niveles de carpeta (rama y subrama) y lo que la regla deja fuera no se toca** | ✅ | La regla puede pedir **dos niveles** ('Assessment/Data': una rama por tipo de entregable y una subrama por el tipo de dato) y el plan los lleva juntos en un solo campo. `SharePoint.limpiar_subcarpeta` respeta '/' como separador y limpia cada nivel por su cuenta (comillas, '|', los `**` de la IA y demás adornos: un nombre con '|' hacía que la carpeta no se pudiera crear), y `_asegurar_carpetas` las crea **nivel a nivel** (madre antes que hija) porque SharePoint no crea una carpeta si su carpeta madre no está: pedirle de golpe '/Destino/Assessment/Data' con 'Assessment' sin crear no creaba nada (`crear_carpeta` se traga ese error) y el archivo se quedaba sin destino; las rutas que ya trae el listado del destino (más las de la misma tanda) no se vuelven a pedir. Y lo que la regla **deja fuera** (una transcripción de reunión, una Consultoría, algo 'por revisar') ya no acaba en un cajón de 'Otros': `SharePoint.PALABRAS_OMITIR` + `es_omitir` reconocen la excusa escrita de cualquier forma ('omitir', 'SE OMITE', '[REVISAR]', 'revisar: falta el alcance', 'no aplica', 'no es propuesta'), `separar_omitidos` parte el plan en (los que van, los que no) **antes** de contar —así no cuentan para `UMBRAL_CLASIFICAR` ni para el resumen— y `_solo_del_plan` los aparta (junto a los que no son ppt/pptx/doc/docx) para decirlo en el resumen («No los toqué (tu regla los deja fuera): …»); los omitidos **no se mueven, no se copian y ni se bajan**, aunque sean grandes, y al aprobar el plan en la vista previa salen en un apartado propio. Si la regla los deja fuera **a todos**, contesta «No hay nada que pasar: tu regla deja fuera a los N archivo(s) que encontré» en vez de inventarse un destino. El archivo que la IA **no contesta** también se omite ahora (antes se mandaba a 'Otros' y acababa copiado), y `_parsear_clasificacion` entiende además tablas de Markdown, viñetas y flechas (`->`, `→`, `=>`), descartando cabeceras ('| Archivo | Rama | Subrama |') y celdas vacías ('ninguno', 'sin subrama', '?'), así que el formato libre del modelo ya no colapsa el plan entero en una sola carpeta. 229 comprobaciones en `tests/pruebas_sharepoint.py` (+40: subcarpetas anidadas y lo que la regla deja fuera), 46 en `tests/pruebas_accion_clasificar.py` (+9: el umbral no cuenta los omitidos y el caso de que la regla deje fuera a todos) y el nuevo `tests/pruebas_clasificacion_ia.py` (38 comprobaciones: formato, tabla, flechas, nombres abreviados, 'omitir', sin respuesta, tandas y el texto del prompt). |
| 0.18 | **Reusar las carpetas que ya existen en el destino** | ✅ | Clasificar mirando solo el ORIGEN tenía un final previsible: la IA no sabía qué carpetas estaban hechas al otro lado y, cuando la regla pedía una rama parecida a una que ya existía ('Assessment/Data Analysis' al lado de la 'Assessment/Data' de siempre, o 'assessment/data' con otras mayúsculas), creaba una carpeta nueva cada vez y la biblioteca acababa con tres 'Assessment'. `SharePoint.catalogo_carpetas(url, profundidad=PROFUNDIDAD_BUSQUEDA)` lee el **DESTINO** hasta dos niveles y devuelve rutas relativas ('Assessment', 'Assessment/Data'); si el destino todavía no existe devuelve una lista vacía (no es un error: se creará al pasar los archivos). Como una biblioteca de verdad tiene cientos de carpetas, se corta (`MAXIMO_CARPETAS`, `MAXIMO_CARPETAS_CATALOGO = 120`) y **se avisa** en `nota_catalogo` en vez de dar el catálogo por completo: «Ya te enseñé 120 carpetas del destino: no miré más a fondo (puede haber más)» si el tope se llena al acabar un nivel, «El destino tiene más carpetas: te enseño las primeras N» si se llena a media lista y «Me quedé en N carpetas del destino…» si se agotan las miradas del recorrido; el chat lo va contando («Mirando las carpetas que ya hay en el destino (nivel 1 de 2)...»). Esa lista entra en el prompt de la IA en su propia sección (`_seccion_carpetas`, tope `MAXIMO_CARPETAS_PROMPT = 150` y «… y N carpeta(s) más con el mismo estilo» para no esconder que hay más), con la instrucción de meter cada archivo en una de esas carpetas cuando encaje; `clasificar_archivos`/`_clasificar_tanda` y el canal `on_clasificar` pasan a llevar `carpetas` (los dobles de antes, con dos argumentos, siguen valiendo: `_clasificar_con_ia` reintenta sin él). Y no todo se fía a que la IA obedezca: `SharePoint.alinear_carpeta` escribe cada nivel como lo tiene el destino cuando la clave coincide ('assessment/data' → 'Assessment/Data'; `_clave_nivel` quita mayúsculas, espacios, guiones y adornos, así que 'Assessment / DATA' también cae en la carpeta que ya está), deja el nivel tal cual si el destino no lo tiene (puede ser nueva de verdad) y, si hay dos carpetas distintas con la misma clave, tampoco adivina (mejor dejarlo que meter el archivo en la que no es); `ajustar_plan(plan, archivos, catalogo)` la aplica al arreglar el plan y `clasificar_y_mover` la vuelve a aplicar aunque nadie le pase el catálogo, con las carpetas de primer nivel que ya lista del destino (`_catalogo_de_existentes`, que ignora lo que no cuelga de la raíz ni lo que está a más de dos niveles) como red de seguridad; cuando cambia algo lo dice («El destino ya tiene esas carpetas: uso las que están hechas, no creo otras que se parezcan») y el resumen del plan lo cuenta («N van a carpetas que ya estaban en el destino»). 260 comprobaciones en `tests/pruebas_sharepoint.py` (+31, sección «Las carpetas que ya existen en el destino»), 60 en `tests/pruebas_accion_clasificar.py` (+14, sección del mismo nombre) y 48 en `tests/pruebas_clasificacion_ia.py` (+10, sección «Las carpetas que ya existen en el destino (prompt)»). |
| 0.19 | **Clasificar por lo que dice el documento (los nombres de hash)** | ✅ | Una propuesta como *'PROPUESTA COMERCIAL bfddfa36 RFI Soporte y-o administración.pptx'* no dice de qué disciplina es, así que la IA no podía clasificarla: se refugiaba en 'omitir' (el archivo se quedaba quieto y el usuario no entendía por qué) o la mandaba a la raíz del destino (todo amontonado en la misma carpeta). Ahora el plan tiene un tercer final, `SharePoint.DUDOSO` ('sin clasificar'), que **no** es lo mismo que lo que la regla deja fuera: es una duda del programa y tiene arreglo. `modules/pistas.py` (`pista_de(datos, nombre, maximo)`, tope `MAXIMO = 700`) saca de los **bytes** del archivo —sin escribirlo en disco y sin abrir Word— el título que el documento guarda en sus propiedades y las primeras líneas (`PARRAFOS = 25`) o diapositivas (`DIAPOSITIVAS = 3`); los formatos viejos (.ppt, .doc), los protegidos y los corruptos devuelven '' sin lanzar, y de esos se decide por el nombre como antes. `SharePoint.pistas_de(origen, nombres)` los lee solo de los archivos que se le piden, y `SystemActions._reintentar_dudosos` lee el documento **solo a los que la IA dejó sin clasificar** y le vuelve a preguntar **solo por esos** (`_clasificar_con_ia` ahora pasa `pistas`, reintentando 4→3→2 argumentos para los dobles viejos; y el plan del segundo intento se arregla con la lista de esos archivos, así que un nombre devuelto a medias se completa con su ruta). Lo que siga sin carpeta **se queda donde está** y se dice con la verdad («no supe a qué carpeta van ni leyendo el documento por dentro, así que se quedan donde están»), sin echarle la culpa a la regla cuando la regla no dijo eso: `regla_deja_fuera`/`regla_pide_la_raiz` (que miran el texto de la regla) y `_partir_omitidos` separan las decisiones de la regla («tu regla los deja fuera») de las dudas del programa. El prompt (`SISTEMA_CLASIFICACION` + `_prompt_clasificacion` con su sección `_seccion_pistas`, 'LO QUE DICE CADA DOCUMENTO POR DENTRO') pide carpeta para CADA archivo y prohíbe 'omitir'/'raíz' por duda (solo si la regla los manda), y si la IA deja sin carpeta a todos se le insiste una vez (`_no_clasifico_nada`, que no insiste si el 'no sé' es honrado: todos 'sin clasificar'). Y nunca se pasa un dudoso ni por error: `es_dudoso` se mira antes que `es_omitir` (que también reconoce 'sin clasificar') y `separar_omitidos`/`_solo_del_plan` lo tratan como 'no tocar' — mejor un archivo quieto que uno en la carpeta equivocada. 289 comprobaciones en `tests/pruebas_sharepoint.py` (+29, sección «Lo que la IA no supo clasificar»), 78 en `tests/pruebas_accion_clasificar.py` (+18), 72 en `tests/pruebas_clasificacion_ia.py` (+24) y el nuevo `tests/pruebas_pistas.py` (29: .docx y .pptx de verdad fabricados en memoria, formatos viejos, corrupción y recorte). |


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
2. **Reuniones** (fase 2) — hecho: acta con responsables, agenda previa y envío del acta
3. Cimientos: **lectura de archivos por ruta** (0.3), memoria (0.4) y auditoría (0.5)
4. Calendario y tareas (fase 3)
5. Mensajería Teams/Slack
6. Automatización y tareas programadas (0.7 y fase 10)
7. Gestión (fase 7), entorno (fase 9) y personal (fase 12)

