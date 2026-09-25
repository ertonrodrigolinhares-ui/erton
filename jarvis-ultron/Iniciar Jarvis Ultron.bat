@echo off
title Jarvis Ultron
cd /d "%~dp0"

rem ---- Procura o Python 3.11 ou mais novo (de preferencia 3.12) ----
set "PY="
where py >nul 2>nul && (py -3.12 -c "" >nul 2>nul && set "PY=py -3.12")
if not defined PY where py >nul 2>nul && (py -3.13 -c "" >nul 2>nul && set "PY=py -3.13")
if not defined PY where py >nul 2>nul && (py -3.11 -c "" >nul 2>nul && set "PY=py -3.11")
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto instalar_python

rem ---- Primeira vez: cria o ambiente ----
if not exist ".venv\Scripts\python.exe" (
    echo Primeira vez: preparando o Jarvis Ultron. Isso pode levar varios minutos...
    %PY% -m venv .venv || goto erro
)

rem ---- Instala os componentes se ainda nao instalou ou se mudaram ----
fc /b requirements.txt .venv\instalado.txt >nul 2>nul
if errorlevel 1 goto instalar_pacotes
goto chave

:instalar_pacotes
echo Instalando os componentes (so na primeira vez, pode demorar)...
echo ==== %date% %time% ==== >> instalacao-log.txt
".venv\Scripts\python.exe" -m pip install --upgrade pip >> instalacao-log.txt 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> instalacao-log.txt 2>&1 || goto erro
echo Instalando o navegador usado pelas automacoes...
".venv\Scripts\python.exe" -m playwright install chromium >> instalacao-log.txt 2>&1 || echo Aviso: o navegador das automacoes nao foi instalado. O resto funciona.
copy /y requirements.txt .venv\instalado.txt >nul

:chave
rem ---- Primeira vez: pede a chave do Gemini ----
if exist ".env" goto groq
echo.
echo ============================================================
echo  Falta a chave do Gemini. Para pegar a sua, de graca:
echo  1. Vai abrir o site do Google. Entre com o seu Gmail.
echo  2. Clique em "Create API key" e copie a chave.
echo  3. Volte aqui, clique com o botao direito para colar e aperte Enter.
echo ============================================================
start https://aistudio.google.com/apikey
set /p "CHAVE=Cole a chave aqui: "
if "%CHAVE%"=="" goto chave
(
    echo GEMINI_API_KEY="%CHAVE%"
    echo GEMINI_VOICE_NAME="charon"
    echo JARVIS_EFEITO_ULTRON=1
    echo JARVIS_SKIP_CLAP_GATE=1
    echo JARVIS_PALAVRA_ATIVACAO=1
) > .env
echo Chave salva.

:groq
rem ---- Uma vez so: pergunta a chave do Groq (reserva gratis, opcional) ----
findstr /c:"GROQ_API_KEY" .env >nul 2>nul && goto iniciar
echo.
echo ============================================================
echo  OPCIONAL: chave do Groq, a IA reserva gratis.
echo  Se o Gemini cair ou atingir o limite, o Groq responde no lugar.
echo  1. Vai abrir o site do Groq. Entre com a sua conta do Google.
echo  2. Clique em "Create API Key", de o nome Jarvis e copie a chave.
echo  3. Cole aqui com o botao direito e aperte Enter.
echo  Para pular, apenas aperte Enter.
echo ============================================================
start https://console.groq.com/keys
set "GROQ="
set /p "GROQ=Chave do Groq (ou Enter para pular): "
>> .env echo.
>> .env echo GROQ_API_KEY="%GROQ%"
if "%GROQ%"=="" (echo Sem reserva por enquanto. Para colocar depois, veja o LEIA-ME.) else (echo Chave do Groq salva.)

:iniciar
rem ---- Uma vez so: prefere os modelos Gemini 3.5 (troque ou apague a linha no .env) ----
findstr /c:"JARVIS_GEMINI_VERSAO" .env >nul 2>nul && goto iniciar_jarvis
>> .env echo.
>> .env echo JARVIS_GEMINI_VERSAO=3.5
:iniciar_jarvis
echo.
echo Iniciando o Jarvis Ultron... Deixe esta janela aberta enquanto usa.
set JARVIS_CLI=1
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo O Jarvis Ultron parou com um erro. Tire um print desta tela e envie para o suporte.
    pause
)
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
    echo Python instalado! Feche esta janela e abra o "Iniciar Jarvis Ultron" de novo.
)
pause
exit /b

:erro
echo.
echo Algo deu errado na instalacao. Tire um print desta tela e envie o arquivo instalacao-log.txt.
pause
