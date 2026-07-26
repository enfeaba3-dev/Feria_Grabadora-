@echo off
setlocal
cd /d "%~dp0"
title Feria Transcriber 2.0 - Diagnostico
if not exist ".venv\Scripts\python.exe" (
  echo No existe el entorno virtual. Ejecutando instalacion primero...
  call instalar.bat /nopause
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" self_test.py --quick
set CODE=%errorlevel%
echo.
echo Los informes estan en la carpeta logs.
pause
exit /b %CODE%
:error
pause
exit /b 1
