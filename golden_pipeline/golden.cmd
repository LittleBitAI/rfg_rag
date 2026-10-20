@echo off
rem Golden data pipeline: passes every argument to the one CLI, python -m golden_pipeline.cli.
rem Keep this file ASCII: cmd.exe reads it in the console code page, not UTF-8.
rem The current folder stays as it is, so relative paths such as --export files resolve where you typed them.
setlocal
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%"
if "%~1"=="" (
  rem Opened by double-click: show the commands and keep the window open.
  "%ROOT%\.venv\Scripts\python" -m golden_pipeline.cli --help
  pause
  exit /b 0
)
"%ROOT%\.venv\Scripts\python" -m golden_pipeline.cli %*
