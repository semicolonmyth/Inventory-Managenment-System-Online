# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# Get the project root directory
project_root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ('Icons', 'Icons'),  # Include icons folder
        ('themes', 'themes'),  # Include themes folder
        ('utils/config.json', 'utils'),  # Include config.json
    ],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.sql.default_comparator',
        'fpdf',
        'requests',
        'openpyxl',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='StoreManagementSystem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Icons\\appico.ico',  # Application icon (relative path)
    version_file=None,
)

