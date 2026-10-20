@echo off
title Ligar Gmail (Luiz Conrado)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "hermes\ligar_gmail.ps1"
