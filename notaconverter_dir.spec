# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

excluded_modules = [
    'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore',
    'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets',
    'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
    'PyQt6.QtNetwork', 'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtXml',
    'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtPositioning',
    'PyQt6.QtSensors', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtRemoteObjects', 'PyQt6.QtSpatialAudio', 'PyQt6.QtDesigner',
    'tkinter', 'tkinterdnd2', 'unittest', 'pydoc', 'email', 'http',
    'xmlrpc', 'sqlite3', 'distutils', 'setuptools', 'pip', 'asyncio'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('notaconverter/assets', 'notaconverter/assets'),
        ('assets', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

def should_exclude_binary(name: str) -> bool:
    name_lower = name.lower()
    excluded_names = [
        'qt6qml', 'qt6quick', 'qt6pdf', 'qt6network', 'qt6sql',
        'qt6test', 'qt6xml', 'qt6opengl', 'qt6virtualkeyboard',
        'qt6sensors', 'qt6positioning', 'qt6bluetooth', 'qt6nfc',
        'd3dcompiler', 'opengl32sw',
        '_avif', 'libcrypto', 'libssl', '_imagingtk', 'qpdf.dll'
    ]
    return any(ex in name_lower for ex in excluded_names)

a.binaries = [x for x in a.binaries if not should_exclude_binary(x[0])]
a.datas = [x for x in a.datas if not ('translations' in x[0].lower() and x[0].lower().endswith('.qm'))]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NotAconverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/app.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NotAconverter_app'
)
