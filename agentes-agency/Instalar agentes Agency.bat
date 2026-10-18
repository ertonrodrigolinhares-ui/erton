@echo off
title Instalar agentes Agency (Claude Code)
cd /d "%~dp0"
echo Instalando os agentes Agency no Claude Code deste PC...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "instalar_agency.ps1"
if errorlevel 1 (
    echo.
    echo Deu erro. Confira a internet e tente de novo.
)
echo.
pause
