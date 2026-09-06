@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Feria Transcriber 3.0 - Instalacion
if not exist "scripts\install.ps1" (
    echo.
    echo  [ERROR] No se encontro scripts\install.ps1
    echo  El repositorio esta incompleto. Descargalo de nuevo desde GitHub.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install.ps1" %*
if not "%~1"=="/nopause" pause
exit /b %errorlevel%
