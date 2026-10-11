# 🎙️ Jarvis — Asistente personal

Asistente de escritorio para **Windows** que combina **voz, chat y automatización del
sistema**. Escucha comandos por micrófono (o por texto), razona con un modelo de lenguaje
(DeepSeek) y ejecuta acciones reales: abrir programas, controlar el volumen, resumir el
portapapeles, leer correos, grabar reuniones, generar documentos y presentaciones,
buscar en la web y mucho más.

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
- Historial de conversación por sesión (archivos `.md` en la carpeta de Jarvis).
- Selección y exportación de mensajes.
- Adjuntos de imágenes/texto y detección de rutas y URLs clicables.

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
- **Grabar reuniones** (audio del sistema) y generar el **acta** al terminar:
  objetivo, puntos tratados, acuerdos, tareas con responsable y fecha, riesgos y
  próxima reunión, con el título, la fecha, la duración y los asistentes de la
  reunión del calendario (si Jarvis puede leerlo).
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
- **OCR** de imágenes con Tesseract o RapidOCR.

### 👨💻 Desarrollo
- Mensajes de **commit** en formato *Conventional Commits* a partir del diff de Git.
- **Ejecución de comandos de terminal** con resumen del resultado.

---

## 📋 Requisitos

- **Windows 10/11**
- **Python 3.10+**
- *(Opcional)* **Tesseract OCR** para leer texto dentro de imágenes (si no está, se usa
  el motor OCR en Python `rapidocr-onnxruntime`):
  ```powershell
  winget install -e --id UB-Mannheim.TesseractOCR
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
       "modelo_rvc_path": "",
       "programas": {
           "discord": "discord://",
           "spotify": "spotify:",
           "vscode": "code"
       }
   }
   ```

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
           "cliente_id": "d3590ed6-52b3-4102-aeff-aad2292ab01c",
           "tenant": "common"
       }
   }
   ```
   > Se usa un cliente público conocido de Microsoft (*"Microsoft Office"*), así que
   > no hay que crear una app en Azure. Si tu empresa exige una app propia, cambia
   > `cliente_id` (y `tenant` si hay un inquilino concreto) con los mismos permisos.


> ⚠️ El archivo `.env` y `config/config_usuario.json` están en `.gitignore` porque
> pueden contener tu clave de API. **Nunca** los subas al repositorio.

---

## ▶️ Uso

```powershell
python main.py
```

- Habla por el micrófono o escribe en el chat de la interfaz.
- Para una acción, el asistente responde con un comando en el formato
  `[ACCION: TIPO|PARAMETRO]` que se ejecuta automáticamente. Algunos ejemplos:

  | Pides… | Comando |
  | --- | --- |
  | «Abre Discord» | `[ACCION: ABRIR_APP|discord]` |
  | «Busca en YouTube música lo-fi» | `[ACCION: BUSCAR|youtube:musica lo-fi]` |
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

---

## 📁 Estructura del proyecto

```
Asistente/
├── main.py                 # Punto de entrada: entorno, .env, migración y arranque de la GUI
├── app_gui.py              # Interfaz gráfica (customtkinter)
├── main.spec               # Receta de empaquetado con PyInstaller
├── requirements.txt
├── .env.example            # Plantilla de variables de entorno
├── modules/
│   ├── api_brain.py        # Cerebro LLM (DeepSeek) y reglas permanentes
│   ├── voice_engine.py     # Reconocimiento de voz (Google / Whisper)
│   ├── voice_output.py     # Síntesis de voz (edge-tts / pyttsx3)
│   ├── system_actions.py   # Enrutador de acciones del sistema
│   ├── productivity.py     # Notas, portapapeles, pomodoro, perfiles, documentos
│   ├── office_automation.py# PowerPoint y presentaciones desde plantilla
│   ├── correo.py           # Elige el cliente de correo (Outlook COM o nube)
│   ├── correo_nube.py      # Correo por la nube (Microsoft Graph + OAuth2)
│   ├── outlook_tools.py    # Correo de Outlook por COM
│   ├── calendario_tools.py # Calendario de Outlook (reunión en curso, próximas, invitados)
│   ├── meeting_assistant.py# Grabación, transcripción y acta de reuniones
│   ├── preventa_tools.py   # Documentos de preventa
│   ├── cloud_matrix.py     # Matriz en la nube (Excel + Azure DevOps)
│   ├── dev_tools.py        # Commits de Git y comandos de terminal
│   ├── ocr_engine.py       # OCR (Tesseract / RapidOCR)
├── tests/
│   ├── pruebas_correo_nube.py    # Pruebas del correo en la nube (Graph simulado)
│   ├── pruebas_correo_en_vivo.py # Comprobación real contra Microsoft (sin credenciales)
│   └── pruebas_gui_correo.py     # Pruebas de la sección de correo de la ventana
│   └── rutas.py            # Rutas centralizadas de la carpeta de Jarvis
└── assets/
    ├── plantillas/         # Plantillas .pptx corporativas
    └── tools/tessdata/     # Modelos de idioma de Tesseract (spa/eng)
```

---
## 🧪 Pruebas

No hacen falta librerías extra: cada archivo se ejecuta solo y termina diciendo
cuántas comprobaciones ha pasado (salida `0` si todo va bien). Ninguna toca tu
configuración real ni tu buzón (usan una configuración temporal).

```powershell
python tests\pruebas_correo_nube.py      # correo por la nube, con Microsoft simulado
python tests\pruebas_gui_correo.py       # botones y avisos de Ajustes (abre la ventana)
python tests\pruebas_correo_en_vivo.py   # HTTP real contra Microsoft (necesita internet)
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

