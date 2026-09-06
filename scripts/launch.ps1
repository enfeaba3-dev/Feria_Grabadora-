#requires -Version 5.1
<#
.SYNOPSIS
    Lanzador de Feria Transcriber 3.0.
.DESCRIPTION
    Activa el venv si existe, valida que las dependencias esten instaladas
    y arranca app.py con waitress. Abre el navegador al final si la
    configuracion lo solicita.
.NOTES
    Logs: <RepoRoot>\logs\launcher.log
#>

[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$VenvDir     = Join-Path $RepoRoot ".venv"
$VenvPython  = Join-Path $VenvDir "Scripts\python.exe"
$LogDir      = Join-Path $RepoRoot "logs"
$LogFile     = Join-Path $LogDir "launcher.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log {
    param([string]$Message)
    "$(Get-Date -Format o) | $Message" | Out-File -FilePath $LogFile -Append
}

Log "launcher start | repo=$RepoRoot"

# --- 1. Validar venv e instalacion ----------------------------------------
if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "  No se encontro el entorno virtual .venv" -ForegroundColor Red
    Write-Host "  Ejecuta primero instalar.bat" -ForegroundColor Yellow
    Write-Host ""
    Log "fail: venv no encontrado"
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}

# Verificar Flask como prueba minima
$check = & $VenvPython -c "import flask, waitress, faster_whisper" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Faltan dependencias en el entorno virtual." -ForegroundColor Red
    Write-Host "  Ejecuta instalar.bat para reinstalar." -ForegroundColor Yellow
    Write-Host ""
    Log "fail: imports criticos fallaron - $check"
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}

# --- 2. Asegurar single instance (lockfile) -------------------------------
$LockFile = Join-Path $RepoRoot "runtime\.launcher.lock"
$LockDir  = Split-Path -Parent $LockFile
if (-not (Test-Path $LockDir)) { New-Item -ItemType Directory -Path $LockDir -Force | Out-Null }

$LockStream = [System.IO.File]::Open($LockFile, 'Create', 'ReadWrite', 'None')
try {
    $LockStream.Lock(0, 1)
} catch {
    Write-Host "  Ya hay otra instancia de Feria Transcriber en marcha." -ForegroundColor Yellow
    Write-Host "  Cierra la ventana anterior antes de iniciar otra." -ForegroundColor Yellow
    Log "fail: lock activo"
    $LockStream.Close()
    exit 1
}

# --- 3. Arrancar app ------------------------------------------------------
Log "arrancando app.py"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_XET = "1"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"

# Lanzar en proceso bloqueante; app.py mantiene el puerto.
try {
    & $VenvPython (Join-Path $RepoRoot "app.py")
} finally {
    Log "app.py termino"
    $LockStream.Unlock(0, 1)
    $LockStream.Close()
    Remove-Item -LiteralPath $LockFile -ErrorAction SilentlyContinue
}
exit $LASTEXITCODE
