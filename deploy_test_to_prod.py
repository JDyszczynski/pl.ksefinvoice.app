import os
import shutil
import sys
import logging

import re

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_DIR = os.path.join(os.getcwd(), 'TESTOWA')
DEST_DIR = os.path.join(os.getcwd(), 'PRODUKCYJNA')

def increment_version(file_path):
    """
    Automatycznie podbija wersję w pliku main_qt.py.
    Działa dla formatów: "1.0.2", "1.0.2 (Beta)" -> "1.0.3", "1.0.3 (Beta)"
    """
    if not os.path.exists(file_path):
        logger.error(f"Nie znaleziono pliku wersji: {file_path}")
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    version_pattern = r'APP_VERSION\s*=\s*"([^"]+)"'
    match = re.search(version_pattern, content)
    
    if not match:
        logger.error("Nie znaleziono zmiennej APP_VERSION w pliku.")
        return None

    current_version_full = match.group(1)
    logger.info(f"Obecna wersja: {current_version_full}")

    # Rozdzielamy wersję od sufiksu (np. " (Beta)")
    version_parts = current_version_full.split(' ')
    version_number = version_parts[0]
    suffix = " " + " ".join(version_parts[1:]) if len(version_parts) > 1 else ""

    # Parsujemy X.Y.Z
    try:
        mayor, minor, patch = map(int, version_number.split('.'))
        new_patch = patch + 1
        new_version_number = f"{mayor}.{minor}.{new_patch}"
        new_version_full = f"{new_version_number}{suffix}"
        
        # Podmieniamy w treści
        new_content = content.replace(f'APP_VERSION = "{current_version_full}"', f'APP_VERSION = "{new_version_full}"')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        logger.info(f"Zaktualizowano wersję: {current_version_full} -> {new_version_full}")
        return new_version_full
    except ValueError:
        logger.error(f"Nieznany format wersji: {version_number}. Oczekiwano X.Y.Z")
        return None

# Foldery do skopiowania (cała zawartość)
DIRS_TO_SYNC = [
    'database',
    'gui_qt',
    'gus',
    'ksef',
    'logic',
    'mf_whitelist',
    'nbp',
    'vies',
    'templates',
    'Binary'
]

# Pliki do skopiowania z głównego katalogu
FILES_TO_SYNC = [
    'main_qt.py',
    'requirements.txt',
    'logo.ico',
    'QR_buycoffee.png',
    'USEFUL_LINKS.md',
    # Skrypty migracyjne mogą się przydać
    'migrate_auth_config.py',
    'migrate_db_pubkeys.py',
    'migrate_invoice_env.py',
    'migrate_ksef_env.py',
    'migrate_schema.py',
    'migrate_signing_cert.py',
    'migrate_upo_xml.py',
    'migrate_snapshots.py',
    'update_db_jpk_2026.py'
]

def main():
    if not os.path.exists(SOURCE_DIR):
        logger.error(f"Katalog źródłowy nie istnieje: {SOURCE_DIR}")
        return

    if not os.path.exists(DEST_DIR):
        logger.warning(f"Katalog docelowy nie istnieje, tworzenie: {DEST_DIR}")
        os.makedirs(DEST_DIR)

    logger.info(f"Rozpoczynanie synchronizacji z {SOURCE_DIR} do {DEST_DIR}")

    # 1. Automatyczne podbicie wersji w TESTOWA/main_qt.py
    main_qt_path = os.path.join(SOURCE_DIR, 'main_qt.py')
    new_version = increment_version(main_qt_path)
    
    if new_version:
        logger.info(f"Pomyślnie zaktualizowano wersję do: {new_version}")

    # 2. Kopiowanie folderów
    for dir_name in DIRS_TO_SYNC:
        src_path = os.path.join(SOURCE_DIR, dir_name)
        dst_path = os.path.join(DEST_DIR, dir_name)

        if os.path.exists(src_path):
            # Usuwamy stary folder w PRODUKCJI aby usunąć usunięte pliki
            # (Clean sync dla folderów kodu)
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            
            # Kopiujemy ignorując pycache oraz pliki/katalogi testowe i tymczasowe
            shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns(
                '__pycache__', '*.pyc', '.git*', '.vscode', 'venv', '.env',
                'tests', 'test_*', '*_test.py',  # Pliki testowe
                '*.log', '*.tmp', '*.bak',       # Pliki tymczasowe
                'dist', 'build', 'AppDir', 'release', # Katalogi kompilacji (dla Binary)
                'flatpak-build', 'repo' # Inne build folders
            ))
            
            # Jeśli kopiujemy Binary, musimy dodatkowo posprzątać w środku, bo ignore nie zawsze łapie zagnieżdżone specyficzne struktury
            if dir_name == 'Binary':
                # Usuwamy Linux build files z produkcji (są w DEPLOY)
                linux_build_path = os.path.join(dst_path, 'linux')
                for trash in ['build', 'dist', 'AppDir', 'release', 'repo', 'flatpak-build', 'venv']:
                    trash_path = os.path.join(linux_build_path, trash)
                    if os.path.exists(trash_path):
                        shutil.rmtree(trash_path)
                
                # Usuwamy Windows build files (jeśli jakieś zostały)
                win_build_path = os.path.join(dst_path, 'win')
                for trash in ['build', 'dist', 'release']:
                    trash_path = os.path.join(win_build_path, trash)
                    if os.path.exists(trash_path):
                        shutil.rmtree(trash_path)

            logger.info(f"Zaktualizowano folder: {dir_name}")
        else:
            logger.warning(f"Folder źródłowy pominięty (nie istnieje): {dir_name}")

    # 2. Kopiowanie pojedynczych plików
    for file_name in FILES_TO_SYNC:
        src_path = os.path.join(SOURCE_DIR, file_name)
        dst_path = os.path.join(DEST_DIR, file_name)

        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            logger.info(f"Zaktualizowano plik: {file_name}")
        else:
            logger.warning(f"Plik źródłowy pominięty (nie istnieje): {file_name}")

    # 3. Post-procesing (Usuwanie "TEST" z nazw i plików w PRODUKCYJNA)
    logger.info("Dostosowywanie plików dla środowiska PRODUKCYJNA...")
    
    # Function helper
    def replace_in_file(filepath, replacements):
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            new_content = content
            changed = False
            for old, new in replacements.items():
                if old in new_content:
                    new_content = new_content.replace(old, new)
                    changed = True
            
            if changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info(f"Zmodyfikowano pod produkcję: {os.path.basename(filepath)}")
        except Exception as e:
            logger.error(f"Błąd modyfikacji pliku {filepath}: {e}")

    # A: main_qt.py - tytuł okna
    replace_in_file(os.path.join(DEST_DIR, 'main_qt.py'), {
        'KSeF Invoice (TEST)': 'KSeF Invoice',
        'KSeF Invoice (TEST)': 'KSeF Invoice' # Duplicate just in case 
    })
    
    # B: Binary/win/build.bat - katalogi i skróty
    replace_in_file(os.path.join(DEST_DIR, 'Binary', 'win', 'build.bat'), {
        'KsefInvoice_TEST': 'KsefInvoice',       # Katalog instalacji
        'KsefInvoice TEST.lnk': 'KsefInvoice.lnk', # Skrót na pulpicie
        'KSeF Invoice (TEST)': 'KSeF Invoice (PROD)' # Nagłówek skryptu
    })

    logger.info("Synchronizacja zakończona pomyślnie.")
    logger.info("Pamiętaj, że plik bazy danych 'ksef_invoice.db' w PRODUKCYJNA nie został nadpisany (co jest prawidłowe).")
    logger.info("Przy następnym uruchomieniu aplikacji w folderze PRODUKCYJNA, wbudowany system migracji zaktualizuje strukturę bazy.")

if __name__ == "__main__":
    main()
