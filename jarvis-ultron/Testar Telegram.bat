@echo off
title Testar Telegram (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\testar_telegram.ps1"
