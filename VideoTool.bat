@echo off
setlocal
REM Double-click launcher for Video Tool. Works from any shortcut location.
cd /d "%~dp0"
set "UV_RUN_OPTIONS="
if defined VIRTUAL_ENV (
    set "UV_RUN_OPTIONS=--active"
) else if not defined UV_PROJECT_ENVIRONMENT (
    if not exist ".venv\Scripts\python.exe" (
        if exist ".venv_new\Scripts\python.exe" set "UV_PROJECT_ENVIRONMENT=%~dp0.venv_new"
    )
)
uv run %UV_RUN_OPTIONS% vtool %*
if errorlevel 1 (
    echo.
    echo Video Tool finalizo con un error. Revisa el mensaje de arriba.
    pause
)
