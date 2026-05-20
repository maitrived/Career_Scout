@echo off
REM Command Prompt entrypoint wrapper for Scout CLI tool
set SCRIPT_DIR=%~dp0
"%SCRIPT_DIR%.venv\Scripts\python.exe" -m python.main %*
