@echo off
title Voltar para o Gemini (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "gemma\voltar_gemini.ps1"
if errorlevel 1 pause
