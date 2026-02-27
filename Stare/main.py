import os

# Konfiguracja środowiska dla Linuxa - eliminacja problemów z grafiką i "szumem" w logach
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"  # Wymuś renderowanie programowe
os.environ["GDK_BACKEND"] = "x11"          # Preferuj X11 zamiast Wayland (często stabilniejsze dla Flet)
os.environ["GTK_CSD"] = "0"                # Wyłącz dekoracje po stronie klienta (Client Side Decorations)

# Konfiguracja logowania PRZED importem Flet, aby przechwycić wszystko
import logging
import sys

# Logger piszący na stdout/stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("KsefApp")

import flet as ft
import traceback
from gui.app_layout import main

def main_wrapper(page: ft.Page):
    try:
        logger.info("Uruchamianie aplikacji KSeF Invoice...")
        main(page)
        logger.info("Aplikacja uruchomiona pomyślnie.")
    except Exception as e:
        logger.error("Wystąpił nieoczekiwany błąd podczas działania aplikacji:")
        logger.error(traceback.format_exc())
        
        # Próba wyświetlenia błędu w oknie aplikacji (jeśli możliwe)
        try:
            page.clean()
            page.add(
                ft.Column([
                    ft.Text("Wystąpił krytyczny błąd aplikacji:", color=ft.Colors.RED, size=20, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Text(traceback.format_exc(), color=ft.Colors.RED, font_family="Consolas, monospace"),
                        bgcolor=ft.Colors.RED_50,
                        padding=10,
                        border_radius=5
                    )
                ], scroll=ft.ScrollMode.AUTO)
            )
            page.update()
        except:
            print("Nie udało się wyświetlić błędu w GUI.")

if __name__ == "__main__":
    try:
        # Używamy main_wrapper do przechwytywania błędów wewnątrz sesji Flet
        # Note: ft.app is deprecated in newer versions, use ft.app as entry point or ft.run
        # We will suppress warnings or just use ft.app for now if ft.run is not standard yet in this context
        # But user asked to remove warning.
        # "app() is deprecated since version 0.80.0. Use run() instead."
        # Assuming ft.run is available.
        if hasattr(ft, "run"):
             ft.run(main_wrapper)
        else:
             ft.app(target=main_wrapper)
    except Exception as e:
        logger.critical("Krytyczny błąd uruchomienia procesu Flet:")
        logger.critical(traceback.format_exc())
