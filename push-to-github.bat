@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Feria Transcriber - Script para subir a GitHub
REM ============================================================

echo.
echo ==========================================================
echo   FERIA TRANSCRIBER - SUBIR A GITHUB
echo ==========================================================
echo.

REM Verificar que estamos en el directorio correcto
if not exist "app.py" (
  echo ERROR: No se encontro app.py. Ejecuta este script desde la carpeta del proyecto.
  pause
  exit /b 1
)

REM Pedir URL del repositorio
set "REPO_URL="
set /p "REPO_URL=URL del repositorio GitHub (ej: https://github.com/usuario/feria-transcriber.git): "

if "!REPO_URL!"=="" (
  echo ERROR: Debes proporcionar una URL de repositorio.
  pause
  exit /b 1
)

REM Verificar que git esta instalado
where git >nul 2>nul
if errorlevel 1 (
  echo ERROR: Git no esta instalado. Descargalo de https://git-scm.com/
  pause
  exit /b 1
)

echo.
echo Verificando estado de git...
echo.

REM Inicializar si no existe
if not exist ".git" (
  echo Inicializando repositorio...
  git init
  git branch -M main
)

REM Verificar remote
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo Anadiendo remote origin...
  git remote add origin "!REPO_URL!"
) else (
  echo Actualizando remote origin...
  git remote set-url origin "!REPO_URL!"
)

REM Limpiar archivos que no deberian estar
echo.
echo Limpiando archivos temporales...
if exist ".venv" rmdir /s /q ".venv" 2>nul
if exist "logs" rmdir /s /q "logs" 2>nul
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
if exist "agent\__pycache__" rmdir /s /q "agent\__pycache__" 2>nul
if exist "runtime" rmdir /s /q "runtime" 2>nul
if exist "config.json" del /q "config.json" 2>nul
if exist "transcripciones" rmdir /s /q "transcripciones" 2>nul

REM Hacer commit
echo.
echo Preparando commit...

git add .

git status --short

set "CONFIRM="
set /p "CONFIRM=Continuar y hacer push? (S/N): "
if /I not "!CONFIRM!"=="S" (
  echo Cancelado.
  pause
  exit /b 0
)

set "COMMIT_MSG="
set /p "COMMIT_MSG=Mensaje del commit (Enter = usar mensaje por defecto): "

if "!COMMIT_MSG!"=="" (
  set "COMMIT_MSG=Update Feria Transcriber 3.0"
)

git commit -m "!COMMIT_MSG!"

REM Verificar rama actual
for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%i"

if "!CURRENT_BRANCH!"=="" set "CURRENT_BRANCH=main"

echo.
echo Subiendo a GitHub en rama !CURRENT_BRANCH!...
echo.

git push -u origin !CURRENT_BRANCH!

if errorlevel 1 (
  echo.
  echo ==========================================================
  echo   ERROR AL SUBIR
  echo ==========================================================
  echo.
  echo Posibles soluciones:
  echo   1. Si pide autenticacion, usa un Personal Access Token
  echo      https://github.com/settings/tokens
  echo   2. Si el remoto no existe, verifica la URL
  echo   3. Si hay conflicto, ejecuta: git pull origin main --rebase
  echo.
) else (
  echo.
  echo ==========================================================
  echo   SUBIDO CORRECTAMENTE
  echo ==========================================================
  echo.
  echo Tu proyecto ya esta en: !REPO_URL!
)

pause
