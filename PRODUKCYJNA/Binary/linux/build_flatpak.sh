#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
MANIFEST="$SCRIPT_DIR/org.ksefinvoice.json"
DIST_DIR="$SCRIPT_DIR/dist/KsefInvoice"

echo "========================================================"
echo "KSeF Invoice - Budowanie wersji Flatpak"
echo "========================================================"

if ! command -v flatpak-builder &> /dev/null; then
    echo "BŁĄD: Nie znaleziono polecenia 'flatpak-builder'."
    echo "Zainstaluj je (np. sudo apt install flatpak-builder) i spróbuj ponownie."
    exit 1
fi

if [ ! -d "$DIST_DIR" ]; then
    echo "BŁĄD: Nie znaleziono zbudowanej aplikacji w $DIST_DIR"
    echo "Uruchom najpierw skrypt 'build.sh', aby wygenerować binaria PyInstaller."
    exit 1
fi

echo "[1/3] Czyszczenie poprzednich budowań..."
rm -rf "$SCRIPT_DIR/flatpak-build"
rm -rf "$SCRIPT_DIR/repo"

echo "[2/3] Budowanie Flatpak (flatpak-builder)..."
# --repo=repo eksportuje od razu do lokalnego repozytorium
flatpak-builder --force-clean --repo="$SCRIPT_DIR/repo" "$SCRIPT_DIR/flatpak-build" "$MANIFEST"

echo "[3/3] Generowanie pliku paczki (.flatpak)..."
flatpak build-bundle "$SCRIPT_DIR/repo" "$SCRIPT_DIR/KsefInvoice.flatpak" pl.ksefinvoice.app

echo "Sprzątanie plików tymczasowych..."
rm -rf "$SCRIPT_DIR/flatpak-build"
rm -rf "$SCRIPT_DIR/repo"
rm -rf "$SCRIPT_DIR/.flatpak-builder"
rm -rf "$SCRIPT_DIR/dist"

echo "========================================================"
echo "SUKCES! Utworzono: $SCRIPT_DIR/KsefInvoice.flatpak"
echo "Aby zainstalować: flatpak install KsefInvoice.flatpak"
echo "========================================================"
