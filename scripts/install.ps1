$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
$logPath=Join-Path (Get-Location) 'logs\install.log'
Start-Transcript -Path $logPath -Append | Out-Null

function Write-Step([string]$Message){
  Write-Host "`n==> $Message" -ForegroundColor Cyan
}
function Fail([string]$Message){
  Write-Host "`nERROR: $Message" -ForegroundColor Red
  Write-Host "Revisa: $logPath" -ForegroundColor Yellow
  Stop-Transcript | Out-Null
  exit 1
}

try{
  Write-Host '============================================================'
  Write-Host ' FERIA TRANSCRIBER 2.0 - INSTALACION Y VERIFICACION'
  Write-Host '============================================================'
  Write-Host "Log: $logPath"

  $launcher=$null
  $launcherArgs=@()
  $candidates=@(
    @{Command='py';Args=@('-3.12')},
    @{Command='py';Args=@('-3.11')},
    @{Command='py';Args=@('-3.10')},
    @{Command='python';Args=@()}
  )
  foreach($candidate in $candidates){
    try{
      $probeArgs=@($candidate.Args)+@('-c',"import sys;print('.'.join(map(str,sys.version_info[:3])));raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) and sys.maxsize>2**32 else 1)")
      $version=& $candidate.Command @probeArgs 2>$null
      if($LASTEXITCODE -eq 0){$launcher=$candidate.Command;$launcherArgs=@($candidate.Args);break}
    }catch{}
  }
  if(-not $launcher){Fail 'Necesitas Python de 64 bits 3.10, 3.11 o 3.12. Inst?lalo marcando Add Python to PATH.'}
  Write-Host "Python elegido: $launcher $($launcherArgs -join ' ') ($version)" -ForegroundColor Green

  if(Test-Path '.venv\Scripts\python.exe'){
    $venvOk=& '.venv\Scripts\python.exe' -c "import sys;raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) and sys.maxsize>2**32 else 1)"
    if($LASTEXITCODE -ne 0){
      $backup=".venv_incompatible_$(Get-Date -Format yyyyMMdd_HHmmss)"
      Write-Step "El entorno existente no es compatible; se mueve a $backup"
      Move-Item '.venv' $backup
    }
  }

  if(-not (Test-Path '.venv\Scripts\python.exe')){
    Write-Step 'Creando entorno virtual aislado'
    & $launcher @launcherArgs -m venv .venv
    if($LASTEXITCODE -ne 0){Fail 'No se pudo crear el entorno virtual.'}
  }

  $python=Resolve-Path '.venv\Scripts\python.exe'
  Write-Step 'Actualizando pip, setuptools y wheel'
  & $python -m pip install --upgrade pip setuptools wheel
  if($LASTEXITCODE -ne 0){Fail 'No se pudo actualizar pip.'}

  Write-Step 'Instalando dependencias principales'
  & $python -m pip install --upgrade -r requirements.txt
  if($LASTEXITCODE -ne 0){Fail 'Fall? la instalaci?n de dependencias. Comprueba Internet, antivirus y el log.'}

  if(Get-Command nvidia-smi -ErrorAction SilentlyContinue){
    Write-Step 'GPU NVIDIA detectada; instalando bibliotecas CUDA opcionales'
    & $python -m pip install --upgrade nvidia-cublas-cu12 nvidia-cudnn-cu12
    if($LASTEXITCODE -ne 0){
      Write-Host 'AVISO: CUDA no pudo instalarse. La aplicaci?n seguir? funcionando con CPU.' -ForegroundColor Yellow
    }
  }else{
    Write-Host 'No se detect? nvidia-smi. Se utilizar? CPU autom?ticamente.' -ForegroundColor Yellow
  }

  Write-Step 'Verificando imports cr?ticos'
  & $python -c "import flask,waitress,faster_whisper,ctranslate2,imageio_ffmpeg,sounddevice,requests,keyboard;print('Imports OK')"
  if($LASTEXITCODE -ne 0){Fail 'Alguna dependencia no se puede importar.'}

  Write-Step 'Ejecutando autopruebas de configuraci?n, audio, FFmpeg y sistema'
  & $python self_test.py --quick
  if($LASTEXITCODE -ne 0){
    Write-Host 'AVISO: alguna autoprueba fall?. Abre diagnostico.bat para ver el detalle.' -ForegroundColor Yellow
  }

  Write-Host "`n============================================================" -ForegroundColor Green
  Write-Host ' INSTALACION COMPLETADA' -ForegroundColor Green
  Write-Host ' Ejecuta iniciar.bat' -ForegroundColor Green
  Write-Host '============================================================' -ForegroundColor Green
  Stop-Transcript | Out-Null
  exit 0
}catch{
  Write-Host $_.Exception.ToString() -ForegroundColor Red
  Fail $_.Exception.Message
}
