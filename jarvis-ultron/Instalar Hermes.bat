@echo off
title Instalar Hermes (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\instalar_hermes.ps1"
if errorlevel 1 pause
