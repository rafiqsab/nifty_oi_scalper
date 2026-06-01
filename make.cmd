@echo off
setlocal

set "PYTHON=.\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=install"

if /I "%TARGET%"=="all" goto install
if /I "%TARGET%"=="install" goto install
if /I "%TARGET%"=="auth" goto auth
if /I "%TARGET%"=="ui" goto ui
if /I "%TARGET%"=="run" goto ui
if /I "%TARGET%"=="test" goto test
if /I "%TARGET%"=="render" goto render

echo Unknown target: %TARGET%
echo Available targets: install, auth, ui, run, test, render
exit /b 1

:install
"%PYTHON%" -m pip install -r requirements.txt
exit /b %ERRORLEVEL%

:auth
"%PYTHON%" auth.py
exit /b %ERRORLEVEL%

:ui
if not defined PORT set "PORT=8501"
"%PYTHON%" -m streamlit run dashboard\streamlit_app.py --server.address 0.0.0.0 --server.port %PORT%
exit /b %ERRORLEVEL%

:test
"%PYTHON%" -m pytest tests -v
exit /b %ERRORLEVEL%

:render
if not defined PORT set "PORT=10000"
"%PYTHON%" -m streamlit run dashboard\streamlit_app.py --server.address 0.0.0.0 --server.port %PORT% --server.headless true
exit /b %ERRORLEVEL%
