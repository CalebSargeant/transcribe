# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/transcribe/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('models', 'models'),  # Include models directory at the bundle root
    ],
    hiddenimports=[
        'transcribe',
        'transcribe.cli',
        'transcribe.config',
        'transcribe.daemon',
        'transcribe.gdrive',
        'transcribe.llm',
        'transcribe.processing',
        'transcribe.slack',
        'transcribe.tls',
        'transcribe.watch',
        'transcribe.whisper',
        'yaml',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'anthropic',
        'openai',
        'requests',
        # gdrive (google.auth / googleapiclient) is intentionally NOT bundled:
        # the release build omits the gdrive extra and falls back to file://
        # links, so listing those imports here only produces build ERRORs.
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
    name='transcribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
