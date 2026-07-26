# Validación de la versión 2.0.0

Comprobaciones ejecutadas antes de crear el ZIP:

- Compilación sintáctica de todos los archivos Python con `python -m compileall -q .`.
- Sintaxis JavaScript validada con `node --check static/js/app.js`.
- 8 pruebas unitarias superadas:
  - configuración predeterminada;
  - reparación de valores inválidos;
  - hotkeys seguras;
  - escritura y lectura atómica de configuración;
  - generación WAV PCM mono de 16 kHz;
  - lectura de cola de logs;
  - deduplicación de fragmentos;
  - deduplicación tolerante a puntuación.
- Conversión real de un WAV mediante FFmpeg a mono de 16 kHz: superada.
- Comprobación de IDs HTML usados por JavaScript: 67 referencias válidas y ningún ID duplicado.
- Comprobación de llaves equilibradas en CSS, JavaScript y PowerShell.
- Revisión de secretos y claves incrustadas: no encontrados.
- Revisión de privacidad: no se guardan transcripciones completas en logs ni en el paquete de soporte.

## Prueba pendiente en el equipo Windows de destino

Este entorno de construcción no es Windows y no dispone de micrófono, hook global de teclado, portapapeles Win32, GPU NVIDIA ni las dependencias pesadas de Whisper. Por ello, la prueba física completa de mantener F8, grabar, mostrar la cápsula y pegar en Chrome debe ejecutarse en el ordenador de destino.

Para facilitarla, la aplicación incluye:

- `diagnostico.bat`;
- `ejecutar_tests.bat`;
- logs separados para launcher, instalación, servidor, agente y navegador;
- reinicio automático del agente hasta tres veces por minuto;
- centro de diagnóstico en la web;
- paquete ZIP de soporte descargable.
