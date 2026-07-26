@echo off
setlocal
cd /d "%~dp0"
title Feria Transcriber 2.0
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\launch.ps1"
exit /b %errorlevel%
