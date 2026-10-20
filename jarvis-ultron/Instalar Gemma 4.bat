@echo off
title Instalar Gemma 4 (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "gemma\instalar_gemma.ps1"
if errorlevel 1 pause
