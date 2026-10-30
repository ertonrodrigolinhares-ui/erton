@echo off
title Instalar voz local - Whisper (Jarvis Ultron)
cd /d "%~dp0"
rem Transcricao da sua voz no proprio PC (modo privado / Gemma 4). Nada vai para a internet.
if not exist ".venv\Scripts\python.exe" (
    echo Abra o "Iniciar Jarvis Ultron" uma vez antes ^(ele prepara o Jarvis^), feche e rode este de novo.
    pause
    exit /b 1
)
echo Instalando a transcricao local da voz (Whisper)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check faster-whisper || goto erro
echo.
echo Baixando o modelo de voz em portugues (uns 500 MB, so na primeira vez)...
".venv\Scripts\python.exe" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('ok')" || goto erro
echo.
echo Pronto! A sua voz agora e transcrita no PC. Feche o Jarvis de verdade
echo (botao direito no icone perto do relogio, Sair do Jarvis) e abra de novo.
pause
exit /b 0
:erro
echo.
echo Nao consegui instalar. Confira a internet e rode este de novo. Se continuar, mande um print.
pause
exit /b 1
