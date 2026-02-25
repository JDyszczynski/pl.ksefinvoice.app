INSTRUKCJA BUDOWANIA APLIKACJI NA WINDOWS
=========================================

Ponieważ kod źródłowy znajduje się na systemie Linux, wygenerowany plik binarny (.exe) musi zostać zbudowany w środowisku Windows.

Kroki do wykonania na systemie Windows:

1. Przenieś cały katalog projektu "KsefInvoice" na komputer z Windows 10/11.
2. Upewnij się, że masz zainstalowany Python (wersja 3.10 lub nowsza).
   Podczas instalacji zaznacz opcję "Add Python to PATH".
3. Wejdź do katalogu `Binary\win`.
4. Uruchom plik `build.bat` (dwukrotne kliknięcie).
5. Skrypt automatycznie:
   - Utworzy środowisko wirtualne (venv).
   - Zainstaluje wymagane biblioteki (w tym PySide6 i PyInstaller).
   - Zbuduje wersję wykonywalną aplikacji.

Gotowa aplikacja będzie znajdować się w:
`Binary\win\dist\KsefInvoice\KsefInvoice.exe`

Możesz przenieść cały katalog `KsefInvoice` (ten z plikiem .exe) na inny komputer. Pamiętaj, aby przenosić cały folder, a nie tylko plik .exe.

UWAGI:
- Jeśli zmienisz kod aplikacji, musisz uruchomić `build.bat` ponownie.
- Aplikacja korzysta z pliku bazy danych `ksef_invoice.db`. Jeśli nie istnieje, zostanie utworzony przy pierwszym uruchomieniu w tym samym katalogu co plik .exe.
