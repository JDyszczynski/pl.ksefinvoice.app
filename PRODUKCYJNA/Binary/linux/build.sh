#!/bin/bash
set -e

APP_NAME="KsefInvoice"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# SCRIPT_DIR is .../{ENV}/Binary/linux

# PROJECT_ROOT points to .../{ENV} (e.g. PRODUKCYJNA or TESTOWA)
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
# DEPLOY_ROOT points to .../KsefInvoice/DEPLOY
DEPLOY_ROOT="$(dirname "$PROJECT_ROOT")/DEPLOY"

echo "========================================================"
echo "KSeF Invoice - Budowanie wersji Linux (AppImage)"
echo "========================================================"

# 1. Środowisko Budowania (w katalogu tymczasowym, by nie śmiecić w PRODUKCYJNA)
BUILD_TEMP_DIR="/tmp/KsefInvoice_Build_Lin_$(date +%s)"
SRC_DIR="$BUILD_TEMP_DIR/src"

echo "[1/6] Przygotowanie izolowanego środowiska w $BUILD_TEMP_DIR..."
rm -rf "$BUILD_TEMP_DIR"
mkdir -p "$SRC_DIR"

# Kopiowanie źródeł do katalogu tymczasowego (aby nie tworzyć __pycache__ w PRODUKCYJNA)
echo "Kopiowanie źródeł..."
# Kopiujemy wszystko z PRODUKCYJNA z wyłączeniem venv i zbędnych rzeczy
rsync -av --exclude 'venv' --exclude 'Binary/linux/build' --exclude 'Binary/linux/dist' --exclude 'Binary/linux/AppDir' --exclude '__pycache__' --exclude '*.pyc' "$PROJECT_ROOT/" "$SRC_DIR/" > /dev/null

cd "$SRC_DIR"
echo "Katalog roboczy (temp): $(pwd)"

# Tworzenie venv w temp
python3 -m venv "$BUILD_TEMP_DIR/venv"
source "$BUILD_TEMP_DIR/venv/bin/activate"

pip install --upgrade pip > /dev/null
echo "Instalacja zależności..."
pip install -r requirements.txt > /dev/null
pip install pyinstaller > /dev/null

# 2. PyInstaller
echo "[2/6] Budowanie pliku binarnego (PyInstaller)..."
# Spec file must be relative to new SRC_DIR or copied there.
# It was copied with rsync (Binary/linux/ksef_invoice.spec).
SPEC_FILE="$SRC_DIR/Binary/linux/ksef_invoice.spec"

if [ ! -f "$SPEC_FILE" ]; then
    echo "BŁĄD: Nie znaleziono pliku spec w nowej lokalizacji: $SPEC_FILE"
    exit 1
fi

# Konfiguracja ścieżek wyjściowych (DEPLOY pozostaje w oryginalnej lokalizacji)
LINUX_DEPLOY="$DEPLOY_ROOT/linux"
APPIMAGE_DIR="$LINUX_DEPLOY/AppImage"
FLATPAK_DIR="$LINUX_DEPLOY/Flatpak"

# Czyszczenie starych plików w DEPLOY
rm -rf "$LINUX_DEPLOY"
mkdir -p "$APPIMAGE_DIR"
mkdir -p "$FLATPAK_DIR"

# Tymczasowe katalogi builda PyInstallera
WORK_PATH="$BUILD_TEMP_DIR/build"
DIST_PATH="$BUILD_TEMP_DIR/dist"

pyinstaller --clean --noconfirm --distpath "$DIST_PATH" --workpath "$WORK_PATH" "$SPEC_FILE"

if [ ! -d "$DIST_PATH/$APP_NAME" ]; then
    echo "BŁĄD: Nie znaleziono katalogu wyjściowego PyInstaller."
    exit 1
fi

# 3. Przygotowanie AppDir
echo "[3/6] Przygotowanie struktury AppDir..."
APP_DIR="$BUILD_TEMP_DIR/AppDir"
mkdir -p "$APP_DIR/usr/bin"

# Kopiowanie binariów
cp -r "$DIST_PATH/$APP_NAME" "$APP_DIR/usr/bin/"

# Kopiowanie plików metadanych (z SRC_DIR)
cp "$SRC_DIR/Binary/linux/AppRun" "$APP_DIR/"
chmod +x "$APP_DIR/AppRun"
cp "$SRC_DIR/Binary/linux/$APP_NAME.desktop" "$APP_DIR/"

# Kopiowanie manifestu Flatpak do katalogu Flatpak (z SRC_DIR)
cp "$SRC_DIR/Binary/linux/org.ksefinvoice.json" "$FLATPAK_DIR/"
cp "$SRC_DIR/Binary/linux/ksef_wrapper.sh" "$FLATPAK_DIR/"

# Ikona
if command -v convert &> /dev/null; then
    echo "Konwersja ikony logo.ico -> ksef_invoice.png..."
    convert "logo.ico" -flatten -resize 256x256 "$APP_DIR/ksef_invoice.png"
else
    echo "OSTRZEŻENIE: Brak 'imagemagick'. Kopiuję logo.ico jako logo.png."
    cp "logo.ico" "$APP_DIR/ksef_invoice.png"
fi

# 4. Pobieranie appimagetool (jeśli brak w temp)
echo "[4/6] Weryfikacja narzędzia appimagetool..."
TOOL_PATH="$BUILD_TEMP_DIR/appimagetool-x86_64.AppImage"

if [ ! -f "$TOOL_PATH" ]; then
    echo "Pobieranie appimagetool z GitHub..."
    wget -q "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$TOOL_PATH"
    chmod +x "$TOOL_PATH"
fi

# 5. Budowanie AppImage
echo "[5/6] Generowanie pliku .AppImage..."
ARCH=x86_64 "$TOOL_PATH" "$APP_DIR" "$APPIMAGE_DIR/KsefInvoice-Linux-x86_64.AppImage"

# Kopiujemy surowe binaria do katalogu Flatpak (żeby prepare_release mogło zrobić tar.gz)
mkdir -p "$FLATPAK_DIR/dist/KsefInvoice"
cp -r "$DIST_PATH/$APP_NAME"/* "$FLATPAK_DIR/dist/KsefInvoice/"

# 6. Przygotowanie Release (Wersjonowanie, Flatpak archive)
echo "[6/6] Generowanie paczki Flatpak i version.txt..."
# Uruchamiamy prepare_release.py z SRC_DIR, ale wskazujemy DEPLOY root
python3 "$SRC_DIR/Binary/prepare_release.py" linux "$DEPLOY_ROOT"

# Sprzątanie po dist w Flatpak
rm -rf "$FLATPAK_DIR/dist"

# Sprzątanie środowiska budowania
echo "Sprzątanie plików tymczasowych..."
rm -rf "$BUILD_TEMP_DIR"

# Finalne czyszczenie PRODUKCYJNA ze śmieci (jeśli jakieś powstały przez pomyłkę)
echo "Czyszczenie katalogu PRODUKCYJNA..."
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$PROJECT_ROOT/venv"
rm -rf "$PROJECT_ROOT/build"
rm -rf "$PROJECT_ROOT/dist"

echo "========================================================"
echo "SUKCES! Gotowe pliki w: $LINUX_DEPLOY"
echo "  - $APPIMAGE_DIR (Plik .AppImage)"
echo "  - $FLATPAK_DIR  (Pliki dla serwera: tar.gz, json, txt)"
echo "========================================================"
