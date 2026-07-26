# Changelog

Todos los cambios notables de Feria Transcriber se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
y el proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

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
