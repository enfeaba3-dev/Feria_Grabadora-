# Feria Transcriber

> Aplicación local para Windows que convierte voz en texto con Whisper. Incluye una web completa para transcribir archivos o grabaciones y un modo de **dictado global push-to-talk** para escribir mediante voz en Chrome, Word, WhatsApp Web, Notion, VS Code o cualquier otra aplicación.

![Version](https://img.shields.io/badge/version-3.0-blue)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Model](https://img.shields.io/badge/Whisper-large--v3--turbo-orange)
![Status](https://img.shields.io/badge/status-stable-brightgreen)

## Características

- **Web UI completa**: graba desde el navegador o sube archivos de audio/video
- **Dictado global push-to-talk**: mantén una tecla y habla en cualquier app de Windows
- **Modelos**: tiny, base, small, medium, large-v2, large-v3, large-v3-turbo
- **GPU/CPU automático**: usa CUDA si está disponible, fallback automático a CPU
- **Procesamiento local**: nada se envía a servicios externos
- **Idiomas**: 30+ idiomas con detección automática
- **Export**: TXT, PDF, Word con timestamps
- **Historial**: todas las transcripciones se guardan automáticamente
- **GPU monitor**: VRAM, temperatura, uso en tiempo real
- **Atajos de teclado**: Ctrl+Enter, Esc, Ctrl+B, Ctrl+T, Ctrl+L
- **Tema claro/oscuro**: toggle
- **Búsqueda**: en transcripciones e historial
- **Diagnóstico**: comprueba Python, FFmpeg, CUDA, micrófono, dependencias
- **Logs**: rotativos, visor web, paquete de soporte ZIP

## Inicio rápido

```batch
instalar.bat   :: Crea .venv + instala dependencias
iniciar.bat    :: Lanza servidor + abre navegador
```

Visita `http://127.0.0.1:5000` y empieza a transcribir.

## Requisitos

- Windows 10 u 11 (64 bits)
- Python 3.10, 3.11 o 3.12 (64 bits, añadir a PATH)
- GPU NVIDIA opcional (recomendada para modelos grandes)
- Micrófono para grabación o dictado
- 4 GB RAM mínimo (8+ GB recomendado)
- FFmpeg viene embebido con `imageio-ffmpeg`, no requiere instalación

## Estructura

```
Feria-Transcriber/
├── app.py                       # Flask + Waitress. API REST, supervisor agente
├── audio_pipeline.py            # Conversión FFmpeg
├── config_manager.py            # Configuración validada y atómica
├── diagnostics.py               # Diagnóstico + paquete de soporte
├── logging_setup.py             # Logs rotativos
├── model_service.py             # Modelo compartido, warmup, fallback GPU/CPU
├── self_test.py                 # Autopruebas
├── text_utils.py                # Unión y deduplicación
├── agent/
│   ├── dictation_agent.py       # Hotkey global push-to-talk
│   ├── overlay.py               # Cápsula flotante
│   ├── windows_integration.py   # Portapapeles, Ctrl+V, ventana activa
│   ├── audio_capture.py         # Captura de audio PCM
│   └── __init__.py
├── static/
│   ├── css/styles.css            # Tema oscuro/claro
│   └── js/app.js                # Frontend completo
├── templates/index.html         # Jinja2 template
├── scripts/
│   ├── install.ps1               # Instalación PowerShell
│   └── launch.ps1                # Lanzamiento PowerShell
├── tests/test_core.py
├── .github/
│   ├── workflows/ci.yml          # CI GitHub Actions
│   └── ISSUE_TEMPLATE/           # Templates de issues
├── iniciar.bat                   # Punto de entrada principal
├── instalar.bat                  # Instalación
├── push-to-github.bat            # Subir a GitHub
├── requirements.txt
├── config.example.json
├── PROMPT_PARA_GPT.md            # Prompt para continuar con IA
├── README.md
├── CHANGELOG.md
├── LICENSE
└── VERSION
```

## API REST

Todas las rutas escuchan en `http://127.0.0.1:5000`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/api/status` | Estado del servidor, modelo y agente |
| GET | `/api/config` | Configuración actual |
| PUT | `/api/config` | Guardar configuración |
| POST | `/api/transcribe` | Transcribir audio (form-data) |
| POST | `/api/export/txt` | Exportar a TXT |
| POST | `/api/export/pdf` | Exportar a PDF |
| POST | `/api/export/docx` | Exportar a Word |
| POST | `/api/agent/{start,stop,restart}` | Control del agente |
| GET | `/api/audio-devices` | Listar micrófonos |
| GET | `/api/history` | Historial de transcripciones |
| POST | `/api/history` | Guardar en historial |
| DELETE | `/api/history/{id}` | Eliminar del historial |
| GET | `/api/gpu-stats` | Estadísticas GPU (VRAM, temp, uso) |
| GET | `/api/diagnostics` | Ejecutar diagnóstico |
| GET | `/api/logs` | Ver logs en tiempo real |
| GET | `/api/support-bundle` | Descargar ZIP de soporte |
| GET | `/api/languages` | Idiomas soportados |

## Dictado global

- Tecla configurable (predeterminada: **F8**)
- Mantener pulsado = grabar, soltar = transcribir + copiar + pegar
- Cápsula flotante encima de otras ventanas sin robar el foco
- Solo teclas no-texto: F1-F12, Insert, Inicio, Fin, Re Pág, Av Pág, Pausa, Bloq Despl, Ctrl derecho, Alt derecho

## Atajos de teclado (web)

| Atajo | Acción |
|-------|--------|
| `Ctrl + Enter` | Iniciar transcripción (archivo o grabación) |
| `Esc` | Cancelar transcripción / parar grabación |
| `Ctrl + L` | Limpiar transcripción actual |
| `Ctrl + B` | Abrir historial |
| `Ctrl + T` | Cambiar tema claro/oscuro |
| `Ctrl + Shift + D` | Panel de debug |

## Contribuir

Las contribuciones son bienvenidas. Por favor abre un issue antes para discutir cambios grandes.

1. Fork el repositorio
2. Crea tu rama: `git checkout -b feature/mi-feature`
3. Commit: `git commit -m 'Añade mi feature'`
4. Push: `git push origin feature/mi-feature`
5. Abre un Pull Request

## Licencia

MIT — ver [LICENSE](LICENSE) para detalles.

## Créditos

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) por SYSTRAN
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) por OpenNMT
- [Flask](https://flask.palletsprojects.com/)
- [Waitress](https://waitress.readthedocs.io/)

## Privacidad

**Todo se ejecuta en tu máquina local.** No se envía audio, texto, logs ni configuración a ningún servidor externo. La única conexión de red es la descarga inicial del modelo desde Hugging Face.
