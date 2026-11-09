@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto local
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 auto_dino.py %*
  goto done
)
python auto_dino.py %*
goto done
:local
".venv\Scripts\python.exe" auto_dino.py %*
:done
pause
