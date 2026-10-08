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
- Leer correos de **Outlook** y crear borradores.
- **Grabar reuniones** (audio del sistema) y generar un resumen al terminar.

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
  | «Graba la reunión» | `[ACCION: GRABAR_REUNION]` |

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
│   ├── outlook_tools.py    # Correo de Outlook
│   ├── meeting_assistant.py# Grabación y resumen de reuniones
│   ├── preventa_tools.py   # Documentos de preventa
│   ├── dev_tools.py        # Commits de Git y comandos de terminal
│   ├── ocr_engine.py       # OCR (Tesseract / RapidOCR)
│   └── rutas.py            # Rutas centralizadas de la carpeta de Jarvis
└── assets/
    ├── plantillas/         # Plantillas .pptx corporativas
    └── tools/tessdata/     # Modelos de idioma de Tesseract (spa/eng)
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
├── notas/            # Notas rápidas y resúmenes de reuniones (.md)
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

