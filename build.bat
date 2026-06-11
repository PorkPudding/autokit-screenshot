@echo off
REM Build AutoKitScreenshot.exe (single file, GUI app) into dist\
REM Requires: pip install -r requirements.txt pyinstaller
pyinstaller --onefile --noconsole --name AutoKitScreenshot --distpath dist --workpath build ^
  --icon assets\icon.ico ^
  --add-data "assets\logo.png;assets" ^
  --add-data "assets\icon.ico;assets" ^
  autokit.py
echo.
echo Done. Exe is at dist\AutoKitScreenshot.exe
pause
