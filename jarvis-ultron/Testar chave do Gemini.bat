@echo off
title Testar chave do Gemini (Jarvis Ultron)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Abra o "Iniciar Jarvis Ultron" uma vez antes ^(ele prepara o Jarvis^) e depois rode este teste.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m core.gemini_acesso
