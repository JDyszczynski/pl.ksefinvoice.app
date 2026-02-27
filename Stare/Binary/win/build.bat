@echo off
echo ========================================================
echo KSeF Invoice - Budowanie wersji binarnej dla Windows
echo ========================================================

:: Ustawienie kodowania na UTF-8 (rozwiązuje problemy z polskimi znakami)
chcp 65001 >nul

:: Pobierz sciezke i przejdz do katalogu glownego
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\.."

echo Katalog roboczy projektu: "%CD%"

echo [1/3] Sprawdzanie srodowiska Python...
if exist "venv\Scripts\python.exe" goto :venv_exists

echo Tworzenie wirtualnego srodowiska (venv)...
python -m venv venv
if %ERRORLEVEL% neq 0 (
    echo BLAD: Nie udalo sie utworzyc venv.
    pause
    exit /b 1
)

:venv_exists
echo Srodowisko venv wykryte.

echo [2/3] Instalacja zaleznosci...
:: Cudzyslowy sa kluczowe przy sciezce z OneDrive
call "venv\Scripts\activate.bat"

echo Aktualizacja pip i instalacja bibliotek...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [3/3] Generowanie pliku .exe (PyInstaller)...
if not exist "Binary\win\ksef_invoice.spec" (
    echo BLAD: Brak pliku Binary\win\ksef_invoice.spec
    pause
    exit /b 1
)

:: UZYWAMY PELNEJ SCIEZKI DO PYTHONA Z VENV
:: To gwarantuje, ze uzyjemy wlasciwych bibliotek
".\venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --distpath "Binary/win/dist" --workpath "Binary/win/build" "Binary/win/ksef_invoice.spec"

if %ERRORLEVEL% equ 0 (
    echo ========================================================
    echo SUKCES! Aplikacja zbudowana w Binary\win\dist\KsefInvoice
    echo ========================================================
) else (
    echo BLAD: PyInstaller napotkal bledy.
)

popd
pause