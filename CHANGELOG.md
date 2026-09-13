# Changelog

Todos los cambios notables de Feria Transcriber se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y el proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [3.0.1] - 2026-09-13

### Corregido
- **500 en `/api/audio-devices`**: `sd.default.device` devuelve
  `_InputOutputPair` (no serializable por JSON). Ahora se expone como
  `{"input": ..., "output": ...}`. El frontend solo usaba `devices[]`, así
  que no hay cambio de contrato.
- **CSP bloqueaba el bootstrap de la UI**: el script inline
  (`window.FERIA_BOOTSTRAP`/`FERIA_CSRF`) violaba `script-src 'self'`, así
  que la UI arrancaba con la configuración por defecto en vez de la del
  servidor. Se eliminó el script inline; `app.js` carga `/api/config` al
  iniciar. Eliminadas las variables `csrf_token`/`csrf_header`/`csrf_field`
  de `index()` y el import de `CSRF_HEADER`/`CSRF_FIELD` en `app.py`.
- **`self_test.py --quick` no hacía nada**: ignoraba `args.quick`. Ahora
  omite los checks de micrófono (`include_audio=False`), pensado para CI.

### Añadido
- **`tests/e2e_api.py`**: e2e HTTP de toda la API (37 checks): cabeceras de
  seguridad, CSRF (sin token 403), allowlist de extensiones (415), modelo
  inválido (400), transcripción real, historial, export PDF/DOCX, sanado de
  config, rate limit (429) y token interno del agente. El nombre del modelo
  se configura con `FERIA_E2E_MODEL` y el check de texto con
  `FERIA_E2E_EXPECT_TEXT` (útil en CI sin voz de prueba).
- **Jobs CI**: `selftest` (self_test --quick) y `e2e` (arranca el servidor
  con modelo `tiny` en CPU y corre `tests/e2e_api.py`).

## [3.0.0] - 2026-07-23

### Añadido
- **Tema claro/oscuro** con toggle y persistencia en localStorage
- **Historial completo** de transcripciones con búsqueda y eliminación
- **Monitor de GPU** en tiempo real (VRAM, temperatura, % uso)
- **Endpoint `/api/gpu-stats`** para estadísticas de la GPU
- **Endpoint `/api/history`** con GET/POST/DELETE
- **Endpoint `/api/languages`** con 30+ idiomas soportados
- **Endpoint `/api/notify`** para notificaciones del sistema
- **Selector de micrófono en la web** (no solo en dictado global)
- **Notificación del sistema** al terminar cada transcripción
- **Atajos de teclado**: Ctrl+Enter, Esc, Ctrl+B, Ctrl+T, Ctrl+L
- **Búsqueda** en el panel de historial
- **GPU pill** en la barra superior
- **Página de GitHub** con CI workflow, templates de issues y PR

### Cambiado
- **Diseño completamente nuevo** sin scroll vertical, layout en grid 2 columnas
- **Texto más grande y legible** en toda la UI (12-18px)
- **Espaciado compacto** para que todo quepa en pantalla
- **Sidebar más estrecha** (200px en vez de 250px)
- **Defaults**: idioma `es`, dispositivo `cuda`, modelo `large-v3-turbo`
- **Parámetros de Whisper optimizados**: beam_size=10, best_of=10, patience=2.0
- **CUDA DLLs en PATH** del proceso agente (fix cublas64_12.dll)
- **Voz española, GPU, mejor calidad** sin necesidad de configurar

### Eliminado
- Sonidos de inicio/fin de dictado (peticiones del usuario)

### Corregido
- Bug `xhr.ok` no existe en XMLHttpRequest (era propiedad de fetch)
- Error 200 al transcribir archivos grandes
- Agente fallaba con cublas64_12.dll no encontrada

## [2.2.0] - 2026-07-22

### Añadido
- Sonidos de inicio/fin al pulsar F8 (tono ascendente y descendente)
- Barra de progreso con porcentaje
- Botón Cancelar con AbortController
- Animación de descarga del modelo

## [2.0.0] - 2026-07-15

### Añadido
- Dictado global push-to-talk con F8
- Cápsula flotante sin robar foco
- Hotkey configurable
- Selección de dispositivo automático/CUDA/CPU
- Fallback automático GPU → CPU

## [1.0.0] - 2026-06-01

### Añadido
- Versión inicial con Tkinter GUI
- Transcripción de archivos de audio
- Export a TXT
- Soporte para modelos tiny a large-v3
- Whisper local con faster-whisper
- Interfaz gráfica en Python con tkinter
