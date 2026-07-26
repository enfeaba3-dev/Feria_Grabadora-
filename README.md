# Feria Transcriber

Convierte tu voz en texto con Whisper. Funciona en tu Windows, sin enviar nada a internet.

## Cómo empezar

1. Doble click en `instalar.bat` (solo la primera vez, tarda unos minutos)
2. Doble click en `iniciar.bat` — se abre el navegador automáticamente
3. Mantén `F8` pulsado y habla — suelta para copiar el texto a donde estés

## Qué hace

- **Web** (`http://127.0.0.1:5000`): graba desde el navegador o sube archivos de audio/video
- **Dictado global** (F8): funciona en cualquier programa (Word, Chrome, WhatsApp, etc.)
- **Idiomas**: español, inglés, francés, alemán, italiano, portugués, catalán y más
- **GPU**: usa tu tarjeta NVIDIA automáticamente; si no, CPU
- **Modelos**: desde el rápido `tiny` hasta el preciso `large-v3-turbo` (recomendado)

## Cómo transcribir un archivo

1. Abre la web (se abre sola con `iniciar.bat`)
2. Pestaña **Transcribir** → **Archivo** → arrastra o selecciona
3. Click en **Transcribir archivo**
4. Espera y descarga en TXT, PDF o Word

## Cambiar el modelo o idioma

Arriba a la derecha de la web:
- **Modelo**: `large-v3-turbo` por defecto (mejor calidad)
- **Idioma**: español por defecto

## Solución de problemas

- **No funciona F8** → ejecuta `iniciar.bat` como administrador
- **No se oye nada** → revisa Configuración de Windows → Privacidad → Micrófono
- **Va lento** → cambia a modelo `small` o `medium` en la web
- **Error con CUDA** → la app usa CPU automáticamente, no hace falta hacer nada

## Requisitos

- Windows 10 u 11
- Python 3.10, 3.11 o 3.12 ([descargar](https://www.python.org/downloads/), marca "Add to PATH" al instalar)
- Micrófono
- GPU NVIDIA opcional (recomendada)

## Privacidad

Todo se procesa en tu ordenador. El único internet que se usa es para descargar el modelo la primera vez.
