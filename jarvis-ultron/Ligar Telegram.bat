@echo off
title Ligar Telegram (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ligar_telegram.ps1"
