# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

block_cipher = None

# Paths
PROJECT_DIR = os.path.abspath('.')
CTK_DIR = os.path.join(
    os.path.dirname(sys.executable),
    'Lib', 'site-packages', 'customtkinter',
)
TTKB_DIR = os.path.join(
    os.path.dirname(sys.executable),
    'Lib', 'site-packages', 'ttkbootstrap',
)

# Fallback: try site-packages from the running Python
if not os.path.isdir(CTK_DIR):
    import customtkinter
    CTK_DIR = os.path.dirname(customtkinter.__file__)
if not os.path.isdir(TTKB_DIR):
    import ttkbootstrap
    TTKB_DIR = os.path.dirname(ttkbootstrap.__file__)

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        (CTK_DIR, 'customtkinter'),
        (TTKB_DIR, 'ttkbootstrap'),
    ],
    hiddenimports=[
        'ttkbootstrap',
        'ttkbootstrap.themes',
        'ttkbootstrap.themes.standard',
        'ttkbootstrap.localization',
        'ttkbootstrap.style',
        'ttkbootstrap.widgets',
        'ttkbootstrap.window',
        'ttkbootstrap.constants',
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'openpyxl',
        'requests',
        'dotenv',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
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
    name='ImportaREST',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='assets/logo_importarest.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ImportaREST',
)
