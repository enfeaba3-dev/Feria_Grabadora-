# Feria Transcriber 3.0

Transcripcion local de voz a texto con Whisper. Todo se procesa en tu
Windows; el unico trafico de red es la descarga inicial del modelo.

- Web local: `http://127.0.0.1:5000`
- Dictado global: manten `F8` (configurable) y suelta para pegar
- Modelos: `tiny` a `large-v3-turbo` (recomendado)
- GPU NVIDIA opcional; fallback automatico a CPU

---

## Indice

1. [Inicio rapido](#inicio-rapido)
2. [Como se usa](#como-se-usa)
3. [Requisitos](#requisitos)
4. [Privacidad](#privacidad)
5. [Seguridad](#seguridad)
6. [Licencias y componentes de terceros](#licencias-y-componentes-de-terceros)
7. [Arquitectura interna](#arquitectura-interna)
8. [Solucion de problemas](#solucion-de-problemas)
9. [Compilar desde el codigo fuente](#compilar-desde-el-codigo-fuente)
10. [Reporte de vulnerabilidades](#reporte-de-vulnerabilidades)

---

## Inicio rapido

1. Doble click en `instalar.bat` (solo la primera vez, tarda unos minutos)
2. Doble click en `iniciar.bat` -> se abre el navegador automaticamente
3. Manten `F8` pulsado y habla; suelta para copiar el texto donde estes

Si ya tienes `.venv` con las dependencias, `instalar.bat` lo detecta
y solo actualiza lo que falte. Usa `instalar.bat -Force` para empezar
desde cero.

> El instalador **no** usa internet salvo para descargar `pip` y los
> paquetes listados en `requirements.txt`. La primera ejecucion de la
> app descarga el modelo Whisper (~75 MB a ~1.6 GB).

## Como se usa

- **Web** (`http://127.0.0.1:5000`): graba desde el navegador o sube
  archivos de audio/video.
- **Dictado global** (`F8`): funciona en cualquier programa (Word,
  Chrome, WhatsApp, etc.).
- **Idiomas**: 30+ idiomas, espanol e ingles por defecto.
- **Exportar**: TXT, PDF, Word, copiar al portapapeles, pegar auto.

## Requisitos

- Windows 10 u 11 (64 bits)
- Python 3.10, 3.11 o 3.12 en PATH
  ([descargar](https://www.python.org/downloads/) - marca "Add to PATH")
- Microfono
- GPU NVIDIA opcional (recomendada para velocidad)
- 8 GB libres (los modelos grandes ocupan varios GB)

## Privacidad

- Audio **nunca sale** del ordenador. La transcripcion corre en local
  con `faster-whisper` (CTranslate2).
- El servidor escucha solo en `127.0.0.1` (loopback). No es accesible
  desde la red local ni desde internet.
- Los logs pueden contener el nombre del microfono y rutas locales,
  pero no el audio transcrito. Vive en `logs/` y rota automaticamente.
- El historial (`transcripciones/`) y la configuracion viven junto al
  ejecutable; borra la carpeta para reinstalar desde cero.

## Seguridad

Feria Transcriber sigue el principio de "minimo imprescindible". Solo
se ejecuta en local y nunca se expone a la red, pero igualmente
aplica varias capas de defensa.

### Defensa en profundidad

| Capa | Que hace | Donde |
|------|----------|-------|
| **Bind a loopback** | El servidor solo escucha `127.0.0.1`. No es alcanzable desde la LAN. | `app.py:find_available_port` + `serve(host="127.0.0.1")` |
| **CSRF (tokens de un solo uso)** | Cada sesion emite un token aleatorio; el navegador lo devuelve en `X-CSRF-Token` o `csrf_token` para metodos `POST/PUT/PATCH/DELETE`. | `security.py:_TokenStore`, `csrf_protect` |
| **Sesion de navegador** | Cookie `feria_sid` (HttpOnly, SameSite=Strict) que enlaza el token CSRF a la pestana que lo pidio. | `security.py:ensure_session` |
| **Token interno del agente** | El proceso hijo (dictado global) no tiene cookies, asi que usa un secreto compartido generado al arranque (`runtime/internal_token`) que se valida con `hmac.compare_digest`. | `security.py:init_internal_token`, `agent/dictation_agent.py:_auth_headers` |
| **Rate limiting** | Ventana deslizante por IP+ruta. `/api/transcribe` se limita a 20/min para mitigar DoS accidental. | `security.py:_RateLimiter`, `rate_limit` |
| **Allowlist de extensiones** | Solo se aceptan formatos de audio/video conocidos en `/api/transcribe`. Se rechaza con `415` cualquier otra extension. | `app.py:_ALLOWED_SUFFIXES` |
| **Limite de tamano** | `MAX_CONTENT_LENGTH = 1536 MB` (1,5 GB). | `app.py` |
| **Nombres de archivo saneados** | `secure_filename` de Werkzeug en cada upload. | `app.py:transcribe` |
| **Cabeceras de seguridad** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `CSP` restrictiva, `Permissions-Policy`. | `security.py:apply_security_headers` |
| **Validacion de config** | Whitelist de modelos, regex de idioma, regex de hotkey, clamp numerico. | `config_manager.py:validate_config` |
| **Atomic write** | `tempfile + os.replace` para que un crash a mitad de escritura no rompa la config. | `config_manager.py:save_config` |
| **Logging sanitizado** | Logs rotativos (5 MB x 5 backups). No contienen audio ni transcripciones completas. | `logging_setup.py` |
| **Diagnostico y soporte** | `GET /api/support-bundle` genera un ZIP con `diagnostico.json`, `config.json`, logs y estado del agente. | `diagnostics.py:create_support_bundle` |
| **Idempotencia de instalacion** | El instalador detecta `.venv` existente, loguea todo a `logs/install.log`, soporta `-Force`. | `scripts/install.ps1` |
| **Lockfile** | Solo una instancia del lanzador se ejecuta a la vez (`runtime/.launcher.lock`). | `scripts/launch.ps1` |

### Buenas practicas para el usuario

- No abras el puerto `5000` en el firewall de Windows. La app esta
  pensada para uso local unico.
- Ejecuta `iniciar.bat` como administrador **solo** la primera vez si
  quieres registrar `F8` como hotkey global (la libreria `keyboard`
  lo necesita).
- Si compartes el PC, la primera vez que abras la app se emite un
  CSRF nuevo; nadie podra enviarte peticiones en nombre tuyo desde
  otra pestana.
- Para desinstalar: borra la carpeta completa. No quedan rastros
  fuera de `~/.cache/huggingface` (los modelos descargados).

### Modelo de amenaza (resumen)

| Amenaza | Mitigacion |
|---------|------------|
| Aplicacion web maliciosa en otra pestana que intenta `/api/config` | Token CSRF unico por sesion; la cookie es `SameSite=Strict` |
| Microfono activado por un script externo | `Permissions-Policy: microphone=(self)` + dialogo del navegador |
| Subida de archivos ejecutables | Allowlist de extensiones y `secure_filename` |
| DoS por uploads repetidos | Rate limit por IP+ruta + `MAX_CONTENT_LENGTH` |
| Acceso LAN no deseado | Bind a `127.0.0.1` (no `0.0.0.0`) |
| Hijack de la sesion del navegador | Cookie `HttpOnly` + CSRF rotado por sesion |
| Configuracion corrupta | Validacion + atomic write + recuperacion automatica |

Para el detalle tecnico completo, vease [`SECURITY.md`](SECURITY.md).

## Licencias y componentes de terceros

Feria Transcriber se distribuye bajo **MIT License** (ver
[`LICENSE`](LICENSE)). El aviso completo de copyright es:

> Copyright (c) 2026 Enrique Feria

A continuacion se listan las dependencias declaradas en
`requirements.txt`, su proposito y la licencia bajo la que se
distribuyen. Todas son compatibles con la distribucion comercial
del binario.

| Paquete | Version | Licencia | Proposito |
|---------|---------|----------|-----------|
| [Flask](https://palletsprojects.com/p/flask/) | >=3.1 | BSD-3-Clause | Servidor HTTP y routing |
| [Werkzeug](https://palletsprojects.com/p/werkzeug/) | (transitiva de Flask) | BSD-3-Clause | Utilidades HTTP, `secure_filename` |
| [waitress](https://docs.pylonsproject.org/projects/waitress/) | >=3.0 | ZPL-2.1 | Servidor WSGI para produccion en Windows |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | >=1.1.1 | MIT | Motor de transcripcion Whisper (CTranslate2) |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | (transitiva) | MIT | Inferencia de modelos transformer |
| [ctranslate2](https://pypi.org/project/ctranslate2/) | (transitiva) | MIT | Bindings Python de CTranslate2 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | >=0.6 | BSD-2-Clause | Binario de FFmpeg empotrado para conversion de audio |
| [FFmpeg](https://ffmpeg.org/) | (empotrado) | LGPL-2.1+ / GPL-2+ (build por defecto) | Codecs y filtros de audio (`highpass`, `lowpass`, `afftdn`, `dynaudnorm`) |
| [sounddevice](http://python-sounddevice.readthedocs.io/) | >=0.5 | MIT | Captura de microfono via PortAudio |
| [PortAudio](http://www.portaudio.com/) | (transitiva) | MIT | Backend de audio multiplataforma |
| [requests](https://requests.readthedocs.io/) | >=2.32 | Apache-2.0 | HTTP client usado por el agente de dictado |
| [keyboard](https://github.com/boppreh/keyboard) | >=0.13.5 | MIT | Hotkey global y simulacion de Ctrl+V |
| [python-docx](https://github.com/python-openxml/python-docx) | >=1.1 | MIT | Exportacion a Microsoft Word (`.docx`) |
| [fpdf2](https://github.com/py-pdf/fpdf2) | >=2.8 | LGPL-3.0 | Exportacion a PDF |

> **FFmpeg** se distribuye como binario estatico via `imageio-ffmpeg`
> para evitar instalaciones externas. El binario por defecto se
> compila bajo LGPL; si necesitas GPL por algun motivo, reemplaza
> el ejecutable `imageio_ffmpeg.get_ffmpeg_exe()` con tu propio
> binario.
>
> **fpdf2** se usa solo en tiempo de ejecucion como libreria
> dinamica (se enlaza a nuestro proceso Python). LGPL-3.0 permite
> este uso sin obligar a liberar el resto del codigo bajo la misma
> licencia.

### Modelos de IA (Whisper)

Los modelos Whisper descargados provienen de
[openai/whisper](https://huggingface.co/openai/whisper-large-v3-turbo)
y derivados. Se distribuyen bajo la **licencia MIT de OpenAI** y se
bajan bajo demanda la primera vez que se usan. No se incluyen en
este repositorio.

### Iconografia y tipografias

La UI usa tipografia del sistema (`Segoe UI Variable Display`,
`Consolas`, `Inter` como fallback web). Los SVG del UI son
generados por nosotros y forman parte del proyecto (MIT).

## Arquitectura interna

```
Feria-Transcriber-3.0/
├── app.py                 # Servidor Flask + agente supervisor
├── audio_pipeline.py      # FFmpeg: limpieza y normalizacion a 16 kHz mono
├── config_manager.py      # Validacion y guardado atomico de config.json
├── config.example.json    # Plantilla de configuracion
├── diagnostics.py         # Autocomprobacion y paquete de soporte
├── logging_setup.py       # Logging rotativo en logs/
├── model_service.py       # Carga y ejecucion de faster-whisper
├── security.py            # CSRF, rate limit, headers, internal token
├── self_test.py           # Tests rapidos sin modelo
├── text_utils.py          # Union de transcripciones por solapamiento
├── agent/
│   ├── dictation_agent.py # Hotkey global + captura + envio a /api
│   ├── audio_capture.py   # Apertura robusta del microfono
│   ├── overlay.py         # Capsula flotante tkinter
│   └── windows_integration.py # Clipboard, focus, send Ctrl+V
├── scripts/
│   ├── install.ps1        # Instalador PowerShell (idempotente)
│   └── launch.ps1         # Lanzador con lockfile
├── static/                # CSS y JS de la UI
├── templates/             # Plantilla Jinja2
├── requirements.txt
├── instalar.bat           # Wrapper del instalador
├── iniciar.bat            # Wrapper del lanzador
├── LICENSE                # MIT
├── README.md              # Este archivo
├── SECURITY.md            # Modelo de amenaza y politica
└── CHANGELOG.md
```

## Solucion de problemas

| Sintoma | Causa probable | Solucion |
|---------|----------------|----------|
| `Python no encontrado` | Python no en PATH | Reinstala Python marcando "Add to PATH" |
| `No se pudo crear .venv` | Permisos o antivirus | Ejecuta `instalar.bat` como administrador |
| F8 no funciona | Falta permiso de hotkey | Ejecuta `iniciar.bat` como administrador |
| El navegador no se abre | `web.open_browser = false` | Cambialo en la UI o en `config.json` |
| `FFmpeg no esta disponible` | Fallo en `imageio-ffmpeg` | Reinstala con `pip install --force-reinstall imageio-ffmpeg` |
| `Library cublas64_12.dll is not found` | Tu sistema solo tiene CUDA 13, CTranslate2 pide CUDA 12 | `pip install nvidia-cublas-cu12 nvidia-cuda-nvrtc-cu12` (ya viene en `requirements.txt`, asi que re-ejecuta `instalar.bat`) |
| Error CUDA | Driver NVIDIA obsoleto | Actualiza el driver desde nvidia.com o usa CPU |
| Token CSRF invalido | Cookies bloqueadas o pestana antigua | Recarga la pagina (`Ctrl+Shift+R`) |
| Rate limit alcanzado | Muchas peticiones | Espera unos segundos; el limite es 20/min para `/api/transcribe` |
| Audio sin sonido | Permisos de microfono | Configuracion -> Privacidad -> Microfono |
| El instalador "no encuentra scripts\install.ps1" | Repositorio incompleto | Descarga el ZIP completo desde GitHub |

### CUDA 13 y `cublas64_12.dll`

`faster-whisper` + `CTranslate2` se compilan contra **CUDA 12** y
buscan `cublas64_12.dll` al cargar un modelo en GPU. Si tu maquina
solo tiene el toolkit de **CUDA 13** (en `C:\Program Files\NVIDIA GPU
Computing Toolkit\CUDA\v13.0\bin` solo veras `cublas64_13.dll`),
los siguientes paquetes pip incluidas en `requirements.txt`
proporcionan las DLLs correctas dentro del venv:

- `nvidia-cublas-cu12` (trae `cublas64_12.dll` + `cublasLt64_12.dll`)
- `nvidia-cuda-nvrtc-cu12` (trae `nvrtc64_120_0.dll`)

`model_service.py` ya anade
`.venv\Lib\site-packages\nvidia\cublas\bin` y
`.venv\Lib\site-packages\nvidia\cuda_nvrtc\bin` al `PATH` del
proceso automaticamente. Si aun asi falla, la app intenta CPU como
fallback y sigue funcionando, solo que mas lenta.

## Compilar desde el codigo fuente

```powershell
git clone https://github.com/enfeaba3-dev/Feria_Grabadora-.git
cd Feria_Grabadora-
.\instalar.bat
.\iniciar.bat
```

Para CI, ver [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Tests

```powershell
# Autoprueba (validacion, config, hotkeys, WAV, pipeline ffmpeg)
.venv\Scripts\python.exe self_test.py --quick

# E2E de la API (necesita el servidor arrancado y un archivo de audio
# con voz; usa FERIA_E2E_MODEL=tiny para CI rapido)
.venv\Scripts\python.exe tests\e2e_api.py http://127.0.0.1:5000 prueba.wav

# En CI sin audio de voz: omite los checks de texto transcrito
$env:FERIA_E2E_EXPECT_TEXT="0"
.venv\Scripts\python.exe tests\e2e_api.py http://127.0.0.1:5000 tono.wav
```

El CI ejecuta `self_test --quick` y el e2e de la API con el modelo `tiny`
en CPU en cada push a `main`.

## Reporte de vulnerabilidades

Si encuentras un problema de seguridad, **no abras un issue publico**.
Envia un correo a `enfeaba3 (arroba) gmail.com` con el asunto
`[SECURITY] Feria Transcriber`. Ver [`SECURITY.md`](SECURITY.md)
para tiempos de respuesta y coordinacion.
