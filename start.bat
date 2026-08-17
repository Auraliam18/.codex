@echo off
chcp 65001 >nul
title Aura Trade Panel
echo.
echo   ⚡ Aura Trade Panel
echo.
where python >nul 2>nul || (echo Python پیدا نشد — از python.org نصبش کنید & pause & exit /b 1)
python -m pip install -q -r "%~dp0requirements.txt"
start "" http://127.0.0.1:8420
python "%~dp0run.py"
pause
