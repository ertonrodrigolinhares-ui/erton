@echo off
title Testar Telegram (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\testar_telegram.ps1"
