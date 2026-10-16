@echo off
title Voltar para o Gemini (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "gemma\voltar_gemini.ps1"
if errorlevel 1 pause
