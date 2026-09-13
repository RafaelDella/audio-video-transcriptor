@echo off
setlocal
set "APP=%~dp0.venv\Scripts\transcreve-gui.exe"

if not exist "%APP%" (
    echo A interface ainda nao esta instalada nesta pasta.
    echo Instale o Python e execute no PowerShell, dentro da pasta do projeto:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -e ".[gui]"
    pause
    exit /b 1
)

start "" /D "%~dp0" "%APP%"
if errorlevel 1 (
    echo Nao foi possivel abrir a interface.
    pause
    exit /b 1
)
