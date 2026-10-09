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

*Se implementa con el Outlook de escritorio vía COM (`pywin32`, ya en uso): sin
credenciales ni registro de aplicaciones. Microsoft Graph queda como opción
futura si se quiere funcionar con Outlook cerrado.*

## Fase 2 — reuniones (prioridad 2)

| # | Trabajo | Estado | Detalle |
|---|---------|--------|---------|
| 2.1 | Grabar y transcribir | ✅ | `modules/meeting_assistant.py` (audio del sistema + micrófono, Whisper local). |
| 2.2 | Acta con responsables, fechas y tareas | ✅ | Plantilla fija (objetivo, puntos, acuerdos, tareas con responsable y fecha, riesgos, próxima reunión) + cabecera con título, fecha, duración y asistentes. |
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
| Correo y calendario | Nada: el Outlook de escritorio de este equipo ya está configurado (perfil MAPI). |
| Teams / Slack / WhatsApp | Token de Slack (`chat:write`, `channels:history`) o app de Azure para Teams. |
| Jira / Trello | API token + correo (Jira) o key/token (Trello). |
| Azure DevOps (consultar y mover) | El mismo PAT que ya se usa para la matriz. |
| GitHub / Azure Repos | Token personal para revisar PRs. |
| Generación de imágenes | Clave de la API que se elija (DeepSeek no genera imágenes). |

## Orden de trabajo

1. **Correo bidireccional** (fase 1) — hecho con Outlook COM (sin credenciales)
2. **Reuniones** (fase 2) — hecho: acta con responsables, agenda previa y envío del acta
3. Cimientos: **lectura de archivos por ruta** (0.3), memoria (0.4) y auditoría (0.5)
4. Calendario y tareas (fase 3)
5. Mensajería Teams/Slack
6. Automatización y tareas programadas (0.7 y fase 10)
7. Gestión (fase 7), entorno (fase 9) y personal (fase 12)

