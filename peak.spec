# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("aiosqlite")
hiddenimports += collect_submodules("openpyxl")
hiddenimports += [
    "main",
    "auth",
    "config",
    "database",
    "models",
    "routers",
    "routers.custom_tasks",
    "routers.dashboard",
    "routers.file_compare",
    "routers.me",
    "routers.settings",
    "routers.studies",
    "routers.todos",
    "routers.tracker",
    "routers.user",
]

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("PEAK logo.png", "."),
    ("manifest.json", "."),
]

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "webview", "pywebview", "pythonnet", "clr", "clr_loader",
        "torch", "torchvision", "torchaudio",
        "transformers", "tokenizers", "safetensors", "huggingface_hub",
        "cv2", "av",
        "scipy", "sklearn",
        "faiss", "faiss_cpu",
        "onnxruntime",
        "jieba",
        "pandas",
        "PIL", "Pillow",
        "matplotlib",
        "tkinter", "_tkinter",
        "IPython", "notebook", "jupyter", "jupyter_client", "jupyter_core",
        "test", "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PEAK",
    icon="peak.ico",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="PEAK",
)
