# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hidden = [
    "client_admin_ui",
    "client_auth_ui",
    "client_config",
    "client_dashboard",
    "client_device",
    "client_payments_ui",
    "client_theme",
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
]
hidden += collect_submodules("tkinter")

a = Analysis(
    ["client.py"],
    pathex=[],
    binaries=[],
    datas=[("client.settings.json", ".")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "uvicorn", "fastapi", "sqlalchemy", "bcrypt"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OdiBetsClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
