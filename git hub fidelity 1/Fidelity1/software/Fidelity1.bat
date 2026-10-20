@echo off
REM ====================================================================
REM  Fidelity1 scanning colorimeter  --  software beta 1
REM  Double-click this file to start the instrument software.
REM  The server opens your default browser itself once it is listening,
REM  so there is no race between the page loading and the port binding.
REM  Closing this window stops the server.
REM ====================================================================

cd /d "%~dp0"
title Fidelity1 Colorimeter - server

REM --- find a usable Python -------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )

if not defined PY (
  echo.
  echo   Python was not found on this computer.
  echo.
  echo   Install it from https://www.python.org/downloads/ and tick
  echo   "Add python.exe to PATH" during setup, then run this again.
  echo.
  pause
  exit /b 1
)

REM --- make sure pyserial is present ----------------------------------
%PY% -c "import serial" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Installing pyserial ...
  echo.
  %PY% -m pip install pyserial
  if errorlevel 1 (
    echo.
    echo   pyserial could not be installed. Try running:
    echo       python -m pip install pyserial
    echo.
    pause
    exit /b 1
  )
)

REM --- run --------------------------------------------------------------
echo.
%PY% spectro_server.py %*

REM If the server exits because the port is busy or a file is missing,
REM hold the window open so the message can actually be read.
if errorlevel 1 (
  echo.
  pause
)
