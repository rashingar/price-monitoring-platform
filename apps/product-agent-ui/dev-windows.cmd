@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-windows.ps1" %*
