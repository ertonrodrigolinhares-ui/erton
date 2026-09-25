@echo off
title Ligar Hermes (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ligar_hermes.ps1"
