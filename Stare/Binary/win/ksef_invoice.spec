# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

# Skrypt jest uruchamiany z poziomu root projektu przez build.bat "pyinstaller Binary/win/ksef_invoice.spec"
# Zatem os.getcwd() to .../PRODUKCYJNA/
# Dla pewności używamy path relative to CWD
PROJECT_DIR = os.path.abspath(os.getcwd())

# Wymuszamy dodanie katalogu projektu do ścieżki Pythona
sys.path.insert(0, PROJECT_DIR)

a = Analysis(
    [os.path.join(PROJECT_DIR, 'main_qt.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_DIR, 'templates'), 'templates'),
        (os.path.join(PROJECT_DIR, 'logo.256.ico'), '.'),
        (os.path.join(PROJECT_DIR, 'ksef', 'public_key_prod.pem'), 'ksef'),
        (os.path.join(PROJECT_DIR, 'ksef', 'public_key_test.pem'), 'ksef'),
    ],
    hiddenimports=[
        'database', 
        'database.models', 
        'database.engine', 
        'gui_qt', 
        'ksef', 
        'logic',
        'pymysql',           
        'sqlalchemy',
        'sqlalchemy.sql.default_comparator',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtPrintSupport',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['external_references'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KsefInvoice',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_DIR, 'logo.256.ico'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KsefInvoice',
)
