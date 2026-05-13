# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for glean standalone binary."""

import os
import sys

block_cipher = None

a = Analysis(
    ['src/glean/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Source plugins (loaded dynamically via registry)
        'glean.sources.rss',
        'glean.sources.scraper',
        'glean.sources.hn',
        'glean.sources.reddit',
        'glean.sources.search',
        # LLM provider plugins (loaded dynamically via registry)
        'glean.llm.ollama_provider',
        'glean.llm.anthropic_provider',
        'glean.llm.openai_provider',
        # Dependencies with dynamic imports
        'aiosqlite',
        '_ruamel_yaml',
        'pydantic_core',
        'trafilatura',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='glean',
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
