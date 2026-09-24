@echo off
title Jarvis
cd /d "%~dp0"

rem ---- Procura o Python (de preferencia a versao 3.12) ----
set "PY="
where py >nul 2>nul && (py -3.12 -c "" >nul 2>nul && set "PY=py -3.12")
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto instalar_python

rem ---- Primeira vez: cria o ambiente do Jarvis ----
if not exist ".venv\Scripts\python.exe" (
    echo Primeira vez: preparando o Jarvis. Isso pode levar alguns minutos...
    %PY% -m venv .venv || goto erro
)

rem ---- Instala os componentes se ainda nao instalou ou se mudaram ----
copy /b /y requirements.txt+requirements-voz.txt .venv\pedido.txt >nul
fc /b .venv\pedido.txt .venv\instalado.txt >nul 2>nul
if errorlevel 1 goto instalar_pacotes
goto iniciar

:instalar_pacotes
echo Instalando os componentes do Jarvis...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto erro
echo Instalando os componentes de voz...
".venv\Scripts\python.exe" -m pip install -r requirements-voz.txt -q || echo Aviso: a voz nao foi instalada. O Jarvis vai funcionar so com texto.
copy /y .venv\pedido.txt .venv\instalado.txt >nul

:iniciar
start "" ".venv\Scripts\pythonw.exe" -m jarvis
exit /b

:instalar_python
echo O Python nao esta instalado. Vou instalar agora, aguarde...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo.
    echo Nao consegui instalar automaticamente.
    echo Na pagina que vai abrir, baixe o Python e marque a opcao "Add python.exe to PATH".
    start https://www.python.org/downloads/
) else (
    echo.
    echo Python instalado! Feche esta janela e abra o "Iniciar Jarvis" de novo.
)
pause
exit /b

:erro
echo.
echo Algo deu errado na instalacao. Tire um print desta tela e envie para o suporte.
pause
