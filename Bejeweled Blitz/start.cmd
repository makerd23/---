@echo off
setlocal
if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" -S "%~dp0blitz_bot.py" %*
) else (
    py -3 -S "%~dp0blitz_bot.py" %*
)
pause
