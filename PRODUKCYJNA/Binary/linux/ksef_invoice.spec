# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

# Skrypt uruchamiany z poziomu root projektu
PROJECT_DIR = os.path.abspath(os.getcwd())
sys.path.insert(0, PROJECT_DIR)

# Weryfikacja ikony
icon_path = os.path.join(PROJECT_DIR, 'logo.ico')
if not os.path.exists(icon_path):
    print(f"BŁĄD: Nie znaleziono pliku ikony: {icon_path}")
    sys.exit(1)

a = Analysis(
    [os.path.join(PROJECT_DIR, 'main_qt.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_DIR, 'templates'), 'templates'),
        (os.path.join(PROJECT_DIR, 'logo.ico'), '.'),
        (os.path.join(PROJECT_DIR, 'QR_buycoffee.png'), '.'),
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
    excludes=[],
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
    icon=os.path.join(PROJECT_DIR, 'logo.ico')
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
