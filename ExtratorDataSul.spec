# -*- mode: python ; coding: utf-8 -*-
import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


a = Analysis(
    ['extrator_pywebview.py'],
    pathex=[],
    binaries=[],
    datas=[
    (os.path.join(BASE_DIR, 'ui'), 'ui'),
    (os.path.join(BASE_DIR, 'core'), 'core'),
    ],
    hiddenimports=[
        'win32crypt',
        'packaging.version',  # usado por core/updater.py para comparar versões
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ExtratorDataSul',
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
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ExtratorDataSul',
)
