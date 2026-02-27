@echo off
echo ========================================================
echo KSeF Invoice (PROD) - Budowanie i Instalacja Windows
echo ========================================================

:: Ustawienie kodowania na UTF-8 dla polskich znaków
chcp 65001 >nul

:: Pobierz sciezke i przejdz do katalogu glownego projektu
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\.."

echo [1/4] Sprawdzanie srodowiska Python...
if exist "venv\Scripts\python.exe" goto :venv_exists

echo Tworzenie wirtualnego srodowiska (venv)...
python -m venv venv
if %ERRORLEVEL% neq 0 (
    echo BLAD: Nie udalo sie utworzyc venv.
    pause
    exit /b 1
)

:venv_exists
echo [OK] Srodowisko venv wykryte.

echo [2/4] Instalacja zaleznosci...
call "venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul
python -m pip install pyinstaller >nul

echo Sprawdzam aktualnie ustawiona wersje w main_qt.py...
python -c "import sys; import re; f=open('main_qt.py', encoding='utf-8').read(); m=re.search('APP_VERSION\s*=\s*\"([^\"]+)\"', f); print(f'WYKRYTA WERSJA: {m.group(1)}' if m else 'BRAK WERSJI')"

echo Czyszczenie starych plikow build/dist...
if exist "Binary\win\build" rmdir /s /q "Binary\win\build"
if exist "Binary\win\dist" rmdir /s /q "Binary\win\dist"
if exist "Binary\win\release" rmdir /s /q "Binary\win\release"

echo [3/4] Generowanie pliku .exe (PyInstaller)...

:: Uzywamy zmiennej zamiast sciezki z kropka na poczatku
set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"

"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm --distpath "Binary/win/dist" --workpath "Binary/win/build" "Binary/win/ksef_invoice.spec"

:: Sprawdzamy czy plik istnieje (bez uzycia IF z kropka na poczatku sciezki)
if not exist "Binary\win\dist\KsefInvoice\KsefInvoice.exe" (
    echo.
    echo BLAD: PyInstaller nie utworzyl pliku.
    pause
    exit /b 1
)

echo.
echo [4/4] Instalacja i tworzenie skrotu...
set "DEPLOY_DIR=%USERPROFILE%\KsefInvoice"

:: Bezpieczne pobranie pulpitu
for /f "usebackq tokens=2,*" %%a in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop`) do set "D_DIR=%%b"
call set "D_DIR=%D_DIR%"

taskkill /F /IM KsefInvoice.exe /T 2>nul

:: Kopiowanie
robocopy "Binary\win\dist\KsefInvoice" "%DEPLOY_DIR%" /MIR /XF *.db *.sqlite *.log /R:2 /W:1 >nul

:: Sekcja skrotu - tym razem bez uzycia nawiasow ( ), ktore moga powodowac blad "."
set "VBS=%TEMP%\s.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS%"
echo sL = "%D_DIR%\KsefInvoice.lnk" >> "%VBS%"
echo Set oL = oWS.CreateShortcut(sL) >> "%VBS%"
echo oL.TargetPath = "%DEPLOY_DIR%\KsefInvoice.exe" >> "%VBS%"
echo oL.WorkingDirectory = "%DEPLOY_DIR%" >> "%VBS%"
echo oL.Save >> "%VBS%"

cscript //nologo "%VBS%"
del "%VBS%"

echo.
echo [5/5] Przygotowanie paczki dystrybucyjnej (Release)...
"%PYTHON_EXE%" "Binary/prepare_release.py" win
if %ERRORLEVEL% neq 0 echo OSTRZEZENIE: Nie udalo sie utworzyc archiwum release.

echo ========================================================
echo ZAKONCZONO POMYSLNIE!
echo ========================================================
pause
