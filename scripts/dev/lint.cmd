@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0lint.ps1" %*
