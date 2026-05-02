@echo off
:loop
py -m pip install -e ".[windows,dev]"
py -m windows_navigator
goto loop
