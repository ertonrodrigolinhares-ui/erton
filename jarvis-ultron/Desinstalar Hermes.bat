@echo off
title Desinstalar Hermes (Jarvis Ultron)
echo.
echo Isto remove o Hermes e TODAS as configuracoes dele:
echo login do Nous, conexao do Metricool, perfil jarvis e rotina das 8h.
echo Depois voce reinstala do zero com o "Instalar Hermes".
echo.
set "OK="
set /p "OK=Digite SIM e aperte Enter para continuar: "
if /i not "%OK%"=="SIM" (echo Cancelado. Nada foi removido. & pause & exit /b)
set "H=%LOCALAPPDATA%\hermes\bin\hermes.exe"
if not exist "%H%" (echo O Hermes nao foi encontrado neste computador. Nada para remover. & pause & exit /b)
"%H%" gateway stop
"%H%" gateway uninstall
"%H%" uninstall --full --yes
echo.
echo Pronto. Agora, na pasta nova do Jarvis, rode o "Instalar Hermes".
pause
