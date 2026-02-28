import sys
import platform
import os
import requests
from PySide6.QtCore import QThread, Signal
from packaging import version

class UpdateCheckerThread(QThread):
    update_available = Signal(str, str) # new_version, download_url

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version
        self.system = platform.system()
        # Sprawdzamy czy to dystrybucja binarna (PyInstaller)
        self.frozen = getattr(sys, 'frozen', False)

    def run(self):
        # 1. Sprawdź czy uruchomione jako binary (Windows .exe lub Linux AppImage)
        if not self.frozen:
            return

        check_url = None
        download_url = None

        if self.system == "Windows":
             check_url = "https://www.ksefinvoice.pl/KSEF/version.txt"
             download_url = "https://www.ksefinvoice.pl/KSEF"
        
        elif self.system == "Linux":
             # Sprawdź czy to AppImage
             if "APPIMAGE" in os.environ:
                 check_url = "https://www.ksefinvoice.pl/KSEF/version.txt"
                 download_url = "https://www.ksefinvoice.pl/KSEF"
             else:
                 # Jeśli Flatpak lub inne źródła - pomijamy
                 return
        else:
            return

        if not check_url:
            return

        try:
            # Timeout 5s, żeby nie wisiało w razie problemów z siecią
            response = requests.get(check_url, timeout=5)
            
            if response.status_code == 200:
                server_version_str = response.text.strip()
                
                if self._is_newer(self.current_version, server_version_str):
                    self.update_available.emit(server_version_str, download_url)
                    
        except Exception:
            # Fail silently - nie zgłaszamy błędów sieci/połączenia
            pass

    def _is_newer(self, current, remote):
        """
        Proste porównanie wersji.
        Obsługuje formaty: "1.0.0", "1.0.0 (Beta)", "1.0.1"
        """
        try:
            # Czyścimy stringi (bierzemy tylko pierwszą część przed spacją, np. "1.0.0")
            v_curr = current.split(' ')[0]
            v_remote = remote.split(' ')[0]
            
            # Używamy parse z packaging.version dla poprawnego porównania (1.10 > 1.9)
            return version.parse(v_remote) > version.parse(v_curr)
        except Exception:
            return False
