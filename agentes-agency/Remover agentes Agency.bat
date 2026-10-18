@echo off
title Remover agentes Agency (Claude Code)
cd /d "%~dp0"
echo Isto remove SO os agentes Agency. Os seus outros agentes continuam.
echo.
choice /c SN /m "Remover os agentes Agency"
if errorlevel 2 goto fim
powershell -NoProfile -ExecutionPolicy Bypass -File "instalar_agency.ps1" -Remover
:fim
echo.
pause
