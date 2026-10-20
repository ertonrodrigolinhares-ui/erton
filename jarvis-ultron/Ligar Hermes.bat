@echo off
title Ligar Hermes (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ligar_hermes.ps1"
