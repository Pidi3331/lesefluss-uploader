@echo off
REM Build Lesefluss Uploader als single-file .exe
setlocal

cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

REM Python-Root ermitteln (fuer Tcl/Tk Data)
for /f "delims=" %%i in ('python -c "import sys;print(sys.base_prefix)"') do set PYROOT=%%i
echo Python-Root: %PYROOT%

REM Python 3.13.0 hat einen kaputten Tcl-Lookup-Pfad (sucht in 'lib\' statt 'tcl\').
REM Explizit setzen, damit PyInstaller's Tcl-Detection im Build-Subprocess klappt.
set TCL_LIBRARY=%PYROOT%\tcl\tcl8.6
set TK_LIBRARY=%PYROOT%\tcl\tk8.6
echo TCL_LIBRARY=%TCL_LIBRARY%

REM Alten Build entfernen
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Lesefluss Uploader.spec" del /q "Lesefluss Uploader.spec"

pyinstaller --noconfirm --onefile --windowed ^
    --name "Lesefluss Uploader" ^
    --collect-all tkinterdnd2 ^
    --collect-submodules tkinter ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    --hidden-import _tkinter ^
    --hidden-import serial ^
    --hidden-import serial.tools.list_ports ^
    --add-data "%PYROOT%\tcl\tcl8.6;_tcl_data" ^
    --add-data "%PYROOT%\tcl\tk8.6;_tk_data" ^
    --add-data "%PYROOT%\tcl\tcl8;tcl8" ^
    --add-binary "%PYROOT%\DLLs\tcl86t.dll;." ^
    --add-binary "%PYROOT%\DLLs\tk86t.dll;." ^
    uploader.py

echo.
echo Fertig. EXE liegt in: dist\Lesefluss Uploader.exe
pause
