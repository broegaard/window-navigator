@echo off
set STAMP_FILE=%~dp0.pip.stamp

:loop
call :maybe_install
py -m windows_navigator
echo [%TIME%] Restarting...
goto loop

:maybe_install
set CURRENT_TS=
for %%F in ("pyproject.toml") do set CURRENT_TS=%%~tF
set STORED_TS=
if exist "%STAMP_FILE%" set /p STORED_TS=<"%STAMP_FILE%"
if "%CURRENT_TS%" neq "%STORED_TS%" (
    py -m pip install -e ".[windows,dev]"
    echo %CURRENT_TS%>"%STAMP_FILE%"
)
exit /b
