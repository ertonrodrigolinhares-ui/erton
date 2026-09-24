@echo off
title Ativar Agentes (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ativar_agentes.ps1"
