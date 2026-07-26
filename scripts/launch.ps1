$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path 'logs','runtime' | Out-Null
$logPath=Join-Path (Get-Location) 'logs\launcher.log'
Start-Transcript -Path $logPath -Append | Out-Null
try{
  Write-Host '============================================================'
  Write-Host ' FERIA TRANSCRIBER 2.0'
  Write-Host '============================================================'
  if(-not (Test-Path '.venv\Scripts\python.exe')){
    Write-Host 'Primera ejecuci?n: instalando componentes...' -ForegroundColor Yellow
    & powershell -NoProfile -ExecutionPolicy Bypass -File 'scripts\install.ps1'
    if($LASTEXITCODE -ne 0){throw 'La instalaci?n no se complet?.'}
  }
  $env:HF_HUB_DISABLE_XET='1'
  $env:KMP_DUPLICATE_LIB_OK='TRUE'
  $cublas=Join-Path (Get-Location) '.venv\Lib\site-packages\nvidia\cublas\bin'
  $cudnn=Join-Path (Get-Location) '.venv\Lib\site-packages\nvidia\cudnn\bin'
  if(Test-Path $cublas){$env:PATH="$cublas;$env:PATH"}
  if(Test-Path $cudnn){$env:PATH="$cudnn;$env:PATH"}
  Write-Host "Launcher log: $logPath"
  & '.venv\Scripts\python.exe' app.py
  $exitCode=$LASTEXITCODE
  if($exitCode -ne 0){
    Write-Host "`nFeria Transcriber termin? con c?digo $exitCode." -ForegroundColor Red
    Write-Host 'Ejecuta diagnostico.bat y revisa logs\app.log.' -ForegroundColor Yellow
    Read-Host 'Pulsa Enter para cerrar'
  }
  Stop-Transcript | Out-Null
  exit $exitCode
}catch{
  Write-Host $_.Exception.ToString() -ForegroundColor Red
  Write-Host "Revisa $logPath" -ForegroundColor Yellow
  try{Stop-Transcript | Out-Null}catch{}
  Read-Host 'Pulsa Enter para cerrar'
  exit 1
}
