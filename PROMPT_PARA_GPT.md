# Prompt para continuar Feria Transcriber con GPT

Trabajas sobre **Feria Transcriber 2.0**, aplicación Windows local para transcripción con Whisper en GPU/CPU. Dos modos: web (grabar/subir archivos) y agente de dictado global push-to-talk.

## Cómo levantar el proyecto

```batch
instalar.bat   # Crea .venv + pip install -r requirements.txt + CUDA si hay GPU
iniciar.bat    # Lanza servidor Flask+Waitress en http://127.0.0.1:5000 y abre navegador
```

**Requisitos**: Windows 10/11, Python 3.10-3.12 (64-bit), GPU NVIDIA opcional.

Sin GPU: funciona en CPU (int8). FFmpeg embebido vía `imageio-ffmpeg`.

## Estructura de archivos

```
Feria-Transcriber/
├── app.py                    # Flask + Waitress. API REST, supervisor agente, único proceso Whisper
├── audio_pipeline.py         # Conversión FFmpeg: mono 16kHz + filtros
├── config_manager.py         # Carga/validación/escritura atómica de config.json
├── diagnostics.py            # Diagnóstico completo + paquete ZIP de soporte
├── logging_setup.py          # Logs rotativos por capa (app, agent, frontend, install...)
├── model_service.py          # Modelo compartido, warmup async, inferencia thread-safe, fallback GPU→CPU
├── text_utils.py             # Unión y deduplicación de fragmentos de transcripción
├── self_test.py              # Autopruebas: imports, FFmpeg, CUDA, audio, E/S
├── agent/
│   ├── dictation_agent.py    # Hotkey global, captura PCM, fragmentación, HTTP al servidor
│   ├── overlay.py            # Cápsula flotante topmost que no roba el foco
│   └── windows_integration.py# Ventana activa, portapapeles Unicode, Ctrl+V simulado
├── static/
│   ├── css/styles.css        # CSS minificado (tema oscuro, responsive)
│   └── js/app.js             # Frontend JS: grabación, upload, dictado, diagnóstico, logs
├── templates/
│   └── index.html            # Jinja2 template: 3 vistas (dictado, transcripción, diagnóstico)
├── scripts/
│   ├── install.ps1           # PowerShell: detecta Python, venv, pip, CUDA, autopruebas
│   └── launch.ps1            # PowerShell: verifica venv, setea env, lanza app.py
├── instalar.bat              # → scripts/install.ps1 (con CRLF y CALL)
├── iniciar.bat               # → scripts/launch.ps1 (con CRLF)
├── requirements.txt          # Dependencias (Flask, waitress, faster-whisper, etc.)
├── config.example.json       # Ejemplo de configuración
├── PROMPT_PARA_GPT.md        # Este archivo
├── README.md                 # Documentación de usuario
├── CHANGELOG.md              # Historial de cambios
├── VALIDATION.md             # Lista de validación pre-entrega
└── VERSION                   # Versión actual (2.0.0)
```

## API REST (todas en 127.0.0.1:5000)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | HTML de la web |
| GET | `/api/status` | Estado: servidor, modelo, agente, config |
| GET | `/api/config` | Configuración actual |
| PUT | `/api/config` | Guardar configuración (reinicia agente si activo) |
| POST | `/api/transcribe` | Transcribir audio (multipart: audio + model + language + device + mode) |
| POST | `/api/export/txt` | Exportar texto a TXT |
| POST | `/api/export/pdf` | Exportar a PDF (via fpdf2, Helvetica) |
| POST | `/api/export/docx` | Exportar a Word (via python-docx) |
| POST | `/api/agent/{start,stop,restart}` | Control del agente de dictado |
| POST | `/api/model/warmup` | Precargar modelo en background |
| GET | `/api/audio-devices` | Listar micrófonos disponibles |
| GET | `/api/diagnostics` | Ejecutar diagnóstico completo |
| GET | `/api/logs?name=X&limit=N` | Cola de logs (app, agent, frontend, install) |
| POST | `/api/client-log` | Log desde el navegador |
| GET | `/api/support-bundle` | Descargar ZIP con logs + diagnóstico |
| POST | `/api/open-logs` | Abrir carpeta de logs en Explorer |

## Funcionalidades clave

- **Dictado global**: tecla F8 (configurable). Mantener = grabar (suena tono ascendente), soltar = transcribir + copiar + pegar (tono descendente). Cápsula flotante sin robar foco.
- **Live web**: grabación por fragmentos de 6s, solape y deduplicación, transcripción progresiva.
- **Subir archivo**: audio/video hasta 1.5GB, FFmpeg lo convierte a WAV 16kHz mono.
- **Exportar**: TXT, PDF (con fpdf2), Word (con python-docx). Barra de progreso con porcentaje.
- **Modelos**: tiny, base, small, medium, large-v2, large-v3, large-v3-turbo (default). GPU float16, CPU int8.
- **Idioma default**: español (`es`). **Dispositivo default**: `cuda` (GPU).
- **Sonidos**: tono ascendente al pulsar F8 (inicio dictado), tono descendente al soltar (fin dictado). WAVs en `agent/sounds/`.
- **Diagnóstico**: chequea Python, Whisper, CUDA, FFmpeg, micrófono, espacio, imports.
- **Logs**: rotativos por capa, visor en web, paquete de soporte.

## Reglas al modificar

1. Mantener nombre **Feria Transcriber** y modelo default **large-v3-turbo**.
2. No cargar Whisper desde el agente (siempre vía HTTP al server).
3. No enviar datos a APIs externas. Todo local en 127.0.0.1.
4. No guardar transcripciones completas en logs.
5. Usar hotkey tipo F8/F9, no letras sueltas (evita escribir accidentales).
6. Escritura atómica de config.json y agent_state.json.
7. Toda excepción debe loguearse con contexto y traceback.
8. Errores API: código, mensaje, request_id.
9. Nuevas dependencias → requirements.txt + diagnóstico.
10. .bat con CRLF, .ps1 con encoding UTF-8. Probar CALL para .cmd anidados.
11. `iniciar.bat` es la entrada normal. Python 3.10-3.12 64-bit.

## Validación pre-entrega

- `python -m compileall -q .`
- `python -m unittest discover -s tests -v` (si existen tests)
- Verificar que IDs de JS existen en index.html
- Sin `__pycache__`, `.pyc`, `.venv`, logs reales, modelos descargados en el ZIP
- Entregar ZIP listo para descomprimir y ejecutar

## Próximo cambio solicitado

[Describe aquí el cambio concreto.]
