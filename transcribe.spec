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
        'transcribe.calendars',
        'transcribe.cli',
        'transcribe.config',
        'transcribe.daemon',
        'transcribe.diarize',
        'transcribe.gdrive',
        'transcribe.llm',
        'transcribe.media',
        'transcribe.notes',
        'transcribe.processing',
        'transcribe.render',
        'transcribe.segmentation',
        'transcribe.segments',
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
        # Optional extras are intentionally NOT bundled. Each is imported
        # inside the function that needs it and degrades to a printed note, so
        # listing them here would only produce build ERRORs:
        #   gdrive   -> google.auth, googleapiclient  (falls back to file:// links)
        #   diarize  -> sherpa_onnx, numpy            (falls back to no speakers)
        #   calendar -> EventKit                      (falls back to inferred titles)
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
