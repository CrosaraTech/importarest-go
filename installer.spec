# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec do instalador ImportaREST.

Gera SetupImportaREST.exe (onefile, GUI Tk, com UAC manifest).
Baixa o zip mais recente do GitHub Releases e instala em C:\\ImportaREST\\.
"""
import os

block_cipher = None
PROJECT_DIR = os.path.abspath('.')

_env_local = os.path.join(PROJECT_DIR, '.env')
_datas = [('assets/logo_importarest.ico', 'assets')]
if os.path.isfile(_env_local):
    # .env embutido no installer (analistas nao veem plaintext no repo publico).
    _datas.append((_env_local, '.'))

a = Analysis(
    ['installer.py'],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'matplotlib', 'PIL',
        'customtkinter', 'ttkbootstrap',
        'openpyxl',
    ],
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
    name='SetupImportaREST',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='assets/logo_importarest.ico',
    # Manifest embutido pra pedir UAC automaticamente na abertura.
    uac_admin=True,
)
