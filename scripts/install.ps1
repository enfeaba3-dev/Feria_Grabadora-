#requires -Version 5.1
<#
.SYNOPSIS
    Instalador de Feria Transcriber 3.0.
.DESCRIPTION
    Crea un entorno virtual (.venv), instala las dependencias de requirements.txt
    y verifica que el sistema está listo. Es idempotente: si .venv ya existe, lo
    reutiliza y solo actualiza las dependencias que falten.
.NOTES
    - Requiere PowerShell 5.1+ (incluido en Windows 10/11).
    - Requiere Python 3.10, 3.11 o 3.12 en PATH.
    - Logs: %USERPROFILE%\AppData\Local\Temp\feria-install.log
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$NoBrowser,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "Continue"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$VenvDir     = Join-Path $RepoRoot ".venv"
$VenvPython  = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $RepoRoot "requirements.txt"
$LogDir      = Join-Path $RepoRoot "logs"
$LogFile     = Join-Path $LogDir "install.log"

# --- Helpers ---------------------------------------------------------------
function Write-Step {
    param([string]$Message, [string]$Color = "Cyan")
    if (-not $Quiet) {
        Write-Host ""
        Write-Host "==> $Message" -ForegroundColor $Color
    }
}

function Write-Ok   { param($m) if (-not $Quiet) { Write-Host "  [OK] $m" -ForegroundColor Green } }
function Write-Warn { param($m) if (-not $Quiet) { Write-Host "  [!]  $m" -ForegroundColor Yellow } }
function Write-Fail { param($m) Write-Host "  [X]  $m" -ForegroundColor Red }

function Test-PythonVersion {
    param([int]$Major, [int]$Minor)
    return ($Major -eq 3 -and $Minor -ge 10 -and $Minor -le 12)
}

function Find-Python {
    $candidates = @("py", "python", "python3", "python3.12", "python3.11", "python3.10")
    foreach ($cmd in $candidates) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exe) {
            try {
                $versionOutput = & $exe.Path -c "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
                if ($versionOutput -and (Test-PythonVersion -Major 3 -Minor ([int]($versionOutput.Split('.')[1])))) {
                    return @{ Path = $exe.Path; Version = $versionOutput }
                }
            } catch { }
        }
    }
    return $null
}

# --- Inicio ----------------------------------------------------------------
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

Write-Host ""
Write-Host "  FERIA TRANSCRIBER 3.0 - INSTALADOR" -ForegroundColor White -BackgroundColor DarkBlue
Write-Host "  ====================================" -ForegroundColor White -BackgroundColor DarkBlue
Write-Host ""
Write-Host "  Carpeta: $RepoRoot"
Write-Host "  Log:     $LogFile"
Write-Host ""

# --- 1. Comprobar Python ---------------------------------------------------
Write-Step "Comprobando Python 3.10 / 3.11 / 3.12" "Cyan"
$python = Find-Python
if (-not $python) {
    Write-Fail "No se encontro Python 3.10, 3.11 o 3.12 en PATH."
    Write-Host ""
    Write-Host "  Descarga Python desde https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Marca la casilla 'Add Python to PATH' durante la instalacion." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}
Write-Ok ("Python {0} encontrado en {1}" -f $python.Version, $python.Path)

# --- 2. Crear o reutilizar venv -------------------------------------------
if (Test-Path $VenvPython) {
    if ($Force) {
        Write-Step "Eliminando entorno virtual existente (-Force)" "Yellow"
        Remove-Item -Path $VenvDir -Recurse -Force
    } else {
        Write-Step "Reutilizando entorno virtual existente en .venv" "Yellow"
    }
}

if (-not (Test-Path $VenvPython)) {
    Write-Step "Creando entorno virtual en .venv" "Cyan"
    & $python.Path -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "No se pudo crear el entorno virtual."
        exit 1
    }
    Write-Ok "Entorno virtual creado"
}

# --- 3. Actualizar pip ----------------------------------------------------
Write-Step "Actualizando pip, setuptools y wheel" "Cyan"
& $VenvPython -m pip install --upgrade --quiet pip setuptools wheel 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "No se pudo actualizar pip (continuando con la version actual)"
} else {
    Write-Ok "pip actualizado"
}

# --- 4. Instalar dependencias ---------------------------------------------
Write-Step "Instalando dependencias desde requirements.txt" "Cyan"
Write-Host "      (esto puede tardar unos minutos la primera vez)" -ForegroundColor Gray

$pipArgs = @("-m", "pip", "install", "--disable-pip-version-check", "-r", $Requirements)
if ($Quiet) { $pipArgs += "--quiet" }
$pipLog = & $VenvPython @pipArgs 2>&1
$pipExit = $LASTEXITCODE

"$(Get-Date -Format o) | install start | python=$($python.Version)" | Out-File -FilePath $LogFile -Append
$pipLog | Out-File -FilePath $LogFile -Append

if ($pipExit -ne 0) {
    Write-Fail "Error instalando dependencias. Ultimas lineas del log:"
    $pipLog | Select-Object -Last 15 | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "  Log completo: $LogFile" -ForegroundColor Yellow
    exit 1
}
Write-Ok "Dependencias instaladas"

# --- 5. Verificar imports criticos ----------------------------------------
Write-Step "Verificando imports criticos" "Cyan"
$verifyScript = @"
import importlib, sys
mods = ['flask','waitress','faster_whisper','ctranslate2','imageio_ffmpeg',
        'sounddevice','requests','keyboard','docx','fpdf']
fail = 0
for m in mods:
    try:
        importlib.import_module(m)
        print('  [OK]', m)
    except Exception as e:
        print('  [X] ', m, '->', e)
        fail += 1
# Comprobar DLLs de CUDA 12 que necesita CTranslate2 en GPU.
# Si tu sistema solo tiene CUDA 13, los paquetes nvidia-cublas-cu12 /
# nvidia-cuda-nvrtc-cu12 (incluidos en requirements.txt) los aportan.
import os
from pathlib import Path
sp = Path(sys.executable).parent.parent / 'Lib' / 'site-packages' / 'nvidia'
needed = ['cublas/bin/cublas64_12.dll', 'cublas/bin/cublasLt64_12.dll',
          'cuda_nvrtc/bin/nvrtc64_120_0.dll']
for rel in needed:
    p = sp / rel
    if p.exists():
        print('  [OK]', rel)
    else:
        print('  [!]  Falta', rel, '(solo afecta inferencia GPU)')
sys.exit(0 if fail == 0 else 1)
"@
$verifyOut = & $VenvPython -c $verifyScript 2>&1
$verifyOut | ForEach-Object { Write-Host $_ }
"$(Get-Date -Format o) | verify" | Out-File -FilePath $LogFile -Append
$verifyOut | Out-File -FilePath $LogFile -Append

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Faltan modulos criticos. Revisa $LogFile"
    exit 1
}
Write-Ok "Todos los imports funcionan"

# --- 6. Pre-descarga opcional del modelo ----------------------------------
Write-Step "Pre-descarga del modelo por defecto (opcional)" "Cyan"
$prefetch = $false
if (-not $Quiet) {
    $resp = Read-Host "      Descargar ahora large-v3-turbo? (s/N)"
    $prefetch = ($resp -match '^[sSyY]')
}
if ($prefetch) {
    $prefetchScript = @"
from faster_whisper import WhisperModel
print('Descargando large-v3-turbo...')
m = WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')
print('OK')
"@
    & $VenvPython -c $prefetchScript
    if ($LASTEXITCODE -eq 0) { Write-Ok "Modelo pre-descargado" }
    else { Write-Warn "No se pudo pre-descargar (la app lo hara al primer uso)" }
} else {
    Write-Host "      Se descargara al primer uso (~1.6 GB)" -ForegroundColor Gray
}

# --- 7. Resumen -----------------------------------------------------------
Write-Host ""
Write-Host "  INSTALACION COMPLETADA" -ForegroundColor Green
Write-Host "  =====================" -ForegroundColor Green
Write-Host "  Doble click en iniciar.bat para arrancar la aplicacion." -ForegroundColor White
Write-Host ""
exit 0
