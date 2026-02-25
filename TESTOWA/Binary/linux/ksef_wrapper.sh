#!/bin/sh
# Launcher dla Flatpak
# Uruchamia binarkę 'KsefInvoice' (z PyInstaller) znajdującą się w /app/lib/ksef
# (lub gdziekolwiek ją skopiowaliśmy w manifeście)

export LE_LIBRARY_PATH=/app/lib/ksef:$LD_LIBRARY_PATH
exec /app/lib/ksef/KsefInvoice "$@"
