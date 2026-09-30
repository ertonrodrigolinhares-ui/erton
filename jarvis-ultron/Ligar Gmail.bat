@echo off
title Ligar Gmail (Jarvis Ultron)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ligar_gmail.ps1"
