@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto local
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 dino_bot.py %*
  goto done
)
python dino_bot.py %*
goto done
:local
".venv\Scripts\python.exe" dino_bot.py %*
:done
pause
