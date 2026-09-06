@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Feria Transcriber 3.0
if not exist "scripts\launch.ps1" (
    echo.
    echo  [ERROR] No se encontro scripts\launch.ps1
    echo  Ejecuta instalar.bat primero.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\launch.ps1" %*
exit /b %errorlevel%
