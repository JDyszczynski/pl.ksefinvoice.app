#!/bin/sh
# Wymuś na Qt używanie portali dla dialogów i motywów
export QT_QPA_PLATFORM="wayland;xcb"
export QT_QPA_PLATFORMTHEME=xdg-desktop-portal

# Prostszy wrapper bez LD_LIBRARY_PATH
DATA_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/KsefInvoice"
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"
exec /app/bin/KsefInvoice "$@"
