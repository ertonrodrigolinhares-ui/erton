@echo off
title Instalar Claude (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "claude\instalar_claude.ps1"
if errorlevel 1 pause
