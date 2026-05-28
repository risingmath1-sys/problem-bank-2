@echo off
cd /d "%~dp0"
echo === PYTHON VERSION === > debug.log 2>&1
python --version >> debug.log 2>&1
echo. >> debug.log
echo === PYTHON PATH === >> debug.log
where python >> debug.log 2>&1
echo. >> debug.log
echo === RUN MAIN_GUI === >> debug.log
python backend\main_gui.py >> debug.log 2>&1
echo. >> debug.log
echo === EXIT CODE: %ERRORLEVEL%% === >> debug.log
echo Done. Check debug.log
pause
