@echo off
setlocal
cd /d "%~dp0"
title Feria Transcriber 2.0 - Instalacion
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install.ps1"
if not "%~1"=="/nopause" pause
exit /b %errorlevel%
