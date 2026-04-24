# jarvis.spec
# pyinstaller jarvis.spec --clean --noconfirm
import os
SRC = os.path.abspath("src")

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=[],
    datas=[
        (os.path.join(SRC, "templates"), "templates"),
        (os.path.join(SRC, "static"),    "static"),
    ],
    hiddenimports=[
        # Core
        "faster_whisper", "obsidian_integration",
        # Flask core
        "flask", "flask.templating", "flask.json",
        "flask_sock", "flask_cors", "simple_websocket",
        "werkzeug", "werkzeug.serving", "werkzeug.routing",
        "werkzeug.middleware.proxy_fix",
        "jinja2", "jinja2.ext",
        "click",
        # Networking
        "websocket", "websocket._http", "websocket._socket",
        "websocket._ssl_compat", "websocket._utils",
        "requests", "urllib3", "certifi",
        # System
        "psutil", "psutil._pswindows",
        # Tray
        "pystray", "pystray._win32",
        "PIL", "PIL.Image", "PIL.ImageDraw",
        # Keyboard
        "keyboard",
        # Std extras
        "sqlite3", "configparser", "hashlib",
        "threading", "socket", "json",
        # wsproto (flask-sock dependency)
        "wsproto", "wsproto.utilities", "wsproto.connection",
        "wsproto.events", "wsproto.frame_protocol",
        "wsproto.extensions", "wsproto.handshake",
        "h11",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # No console window
    onefile=True,       # Single exe
    icon=None,          # Set to "jarvis.ico" if you add one
)
