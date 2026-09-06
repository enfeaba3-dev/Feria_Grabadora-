# Politica de seguridad de Feria Transcriber

## Compromiso

Feria Transcriber se ejecuta **solo en local** (`127.0.0.1:5000`) y
nunca expone datos a internet. Aun asi, aplicamos varias capas de
defensa para que un visitante malicioso en el navegador, un script
local o un microfono espia no puedan abusar de la aplicacion.

## Versiones soportadas

| Version | Soporte |
|---------|---------|
| 3.0.x   | Activo  |
| 2.x     | Solo parches criticos |
| 1.x     | Sin soporte |

## Reporte de vulnerabilidades

**No abras un issue publico.** Envia un correo a
`enfeaba3 (arroba) gmail.com` con:

- Asunto: `[SECURITY] Feria Transcriber <version>`
- Pasos para reproducir (PoC)
- Logs relevantes (sanitiza cualquier dato personal)
- Impacto estimado

Recibiras acuse de recibo en **72 horas** y un parche o mitigacion
en un plazo razonable segun la gravedad (CVSS):

- Critica (>=9.0): 7 dias
- Alta (7.0-8.9): 30 dias
- Media (4.0-6.9): 90 dias
- Baja (<4.0): siguiente release

## Modelo de amenaza

### Activos

- Audio capturado del microfono del usuario
- Transcripciones guardadas en `transcripciones/`
- Configuracion del usuario en `config.json`
- Token interno del agente en `runtime/internal_token`
- Modelo Whisper (1-3 GB en disco, descarga bajo demanda)
- Recursos del sistema (CPU, GPU, RAM)

### Sujetos

- **Usuario legitimo**: arranca la app, dicta, transcribe, configura.
- **Visitante web malicioso**: pagina abierta en otra pestana.
- **Script local malicioso**: malware que ya esta en la maquina.
- **Aplicacion de red**: otra app en el mismo PC (LAN, no internet).

### Amenazas y mitigaciones

#### T1 - Llamada CSRF desde otra pestana

**Escenario**: una web maliciosa intenta `PUT /api/config` o
`POST /api/transcribe` hacia `127.0.0.1:5000`.

**Mitigacion**:
- Cookie `feria_sid` con `SameSite=Strict` (no se envia en
  navegaciones cross-site).
- Token CSRF (`X-CSRF-Token`) generado por sesion y requerido en
  todos los metodos `POST/PUT/PATCH/DELETE`. La web maliciosa no
  puede leerlo por la politica del navegador.
- Cabecera `Content-Security-Policy` estricta para evitar XSS que
  robe el token.
- `X-Frame-Options: DENY` evita que otra web incruste la UI.

#### T2 - Exfiltracion del audio

**Escenario**: una web pide acceso al microfono sin permiso.

**Mitigacion**:
- `Permissions-Policy: microphone=(self)` en todas las respuestas.
- El navegador siempre muestra el dialogo de permiso al acceder
  al `getUserMedia`.
- La app no envia audio a ningun servidor remoto.

#### T3 - DoS por uploads repetidos

**Escenario**: el usuario (o un script) sube archivos de 1.5 GB
en bucle hasta llenar el disco.

**Mitigacion**:
- `MAX_CONTENT_LENGTH = 1536 MB` (Flask rechaza con 413).
- Rate limit por IP+ruta: `/api/transcribe` se limita a 20/min.
- Disco minimo recomendado: 8 GB libres (chequeado por
  `diagnostics.py`).

#### T4 - Subida de archivos maliciosos

**Escenario**: el usuario arrastra un `.exe` o un script.

**Mitigacion**:
- Allowlist de extensiones (`.wav .mp3 .m4a .mp4 .flac .ogg
  .aac .wma .mov .mkv .webm .opus .amr .3gp .bin`).
- `secure_filename` de Werkzeug elimina separadores y caracteres
  especiales.
- FFmpeg es invocado con argumentos **fijos** y solo procesa
  archivos locales temporales; no se invoca con el nombre del
  archivo como flag (eso seria command injection).

#### T5 - Hijack de la sesion del navegador

**Escenario**: alguien con acceso fisico al PC quiere usar la UI
sin permiso.

**Mitigacion**:
- Cookie `feria_sid` HttpOnly (no accesible a JS).
- Token CSRF rotado por sesion (no por peticion para no romper
  pestañas concurrentes, pero caduca a las 8h).
- No se almacena nada en `localStorage` que sea sensible (solo
  el tema claro/oscuro).
- Para "bloquear" la sesion, cierra el navegador.

#### T6 - Acceso LAN no deseado

**Escenario**: el usuario abre el puerto 5000 en el firewall
porque la app no arranca.

**Mitigacion**:
- La app **solo** escucha en `127.0.0.1`, nunca en `0.0.0.0`.
- El firewall de Windows no es necesario para uso local.
- Documentacion: `README.md` lo deja explicito.

#### T7 - Sobrescritura de archivos via path traversal

**Escenario**: una API acepta una ruta y la usa para escribir
fuera de la carpeta esperada.

**Mitigacion**:
- Los uploads se guardan en `tempfile.TemporaryDirectory()`
  con nombre generado (`entrada{suffix}`).
- `HISTORY_DIR` es siempre `APP_DIR / "transcripciones"` (ruta
  absoluta, no configurable).
- `LOG_DIR` y `RUNTIME_DIR` se crean al arranque y no se
  reescriben con input del usuario.

#### T8 - Robo del token interno del agente

**Escenario**: un script lee `runtime/internal_token` y se hace
pasar por el agente.

**Mitigacion**:
- El token vive en `runtime/`, que en Windows hereda los ACL
  del usuario que creo la carpeta (denegado a otros usuarios).
- El token solo sirve para el endpoint del API; el archivo
  fisico sigue siendo el activo sensible.
- `hmac.compare_digest` evita timing attacks al comparar.
- Rotacion manual: borrar `runtime/internal_token` fuerza uno
  nuevo en el siguiente arranque (los procesos hijos existentes
  dejan de autenticarse).

## Decisiones explicitas

- **No usamos HTTPS en local.** El servidor escucha en loopback,
  no en una IP alcanzable. TLS no aporta nada y rompe `mkcert`
  casero.
- **No usamos autenticacion con password.** No hay cuentas, no
  hay multi-tenant. El "quien" se resuelve a "el usuario que
  arranco la app en este PC".
- **CSRF es por sesion, no por peticion.** Para no romper
  peticiones concurrentes (live + dictation + export). El
  token se rota al cerrar todas las pestañas (cookie expira).
- **El agente usa token interno, no CSRF.** Porque no tiene
  cookies de navegador. El secreto se genera una vez y vive
  en `runtime/`.
- **Logs NO contienen audio ni transcripciones.** Solo metadatos
  (nombre del microfono, idioma, modelo, contadores, latencia).
  Si necesitas compartir logs en un issue, mandame los `.log`
  directamente.

## Cambios en esta politica

Cualquier cambio se anuncia en `CHANGELOG.md` con la etiqueta
`[SECURITY]`. Los CVEs publicos se listaran aqui cuando ocurran.
