# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Trimage image compressor
# Build with: pyinstaller trimage.spec

import os
import platform

block_cipher = None

# Platform-specific tool selection
if platform.system() == 'Windows':
    tool_binaries = [
        ('trimage/tools/windows/advpng/advpng.exe', 'tools/windows/advpng'),
        ('trimage/tools/windows/gifsicle/gifsicle.exe', 'tools/windows/gifsicle'),
        ('trimage/tools/windows/guetzli/guetzli.exe', 'tools/windows/guetzli'),
        ('trimage/tools/windows/jpegoptim/jpegoptim.exe', 'tools/windows/jpegoptim'),
        ('trimage/tools/windows/mozjpeg/jpegtran-static.exe', 'tools/windows/mozjpeg'),
        ('trimage/tools/windows/optipng/optipng.exe', 'tools/windows/optipng'),
        ('trimage/tools/windows/pngcrush/pngcrush.exe', 'tools/windows/pngcrush'),
        ('trimage/tools/windows/pngout/pngout.exe', 'tools/windows/pngout'),
        ('trimage/tools/windows/webp/cwebp.exe', 'tools/windows/webp'),
        ('trimage/tools/windows/gif2webp.exe', 'tools/windows'),
    ]
else:
    tool_binaries = [
        ('trimage/tools/advpng/advpng', 'tools/advpng'),
        ('trimage/tools/gifsicle/gifsicle', 'tools/gifsicle'),
        ('trimage/tools/guetzli/guetzli', 'tools/guetzli'),
        ('trimage/tools/jpegoptim/jpegoptim', 'tools/jpegoptim'),
        ('trimage/tools/mozjpeg/jpegtran-static', 'tools/mozjpeg'),
        ('trimage/tools/mozjpeg/cjpeg-static', 'tools/mozjpeg'),
        ('trimage/tools/mozjpeg/djpeg-static', 'tools/mozjpeg'),
        ('trimage/tools/optipng/optipng', 'tools/optipng'),
        ('trimage/tools/pngcrush/pngcrush', 'tools/pngcrush'),
        ('trimage/tools/pngout/pngout', 'tools/pngout'),
        ('trimage/tools/webp/cwebp', 'tools/webp'),
        ('trimage/tools/webp/dwebp', 'tools/webp'),
        ('trimage/tools/webp/gif2webp', 'tools/webp'),
        ('trimage/tools/webp/webpmux', 'tools/webp'),
        ('trimage/tools/webp/webpinfo', 'tools/webp'),
        ('trimage/tools/jpeg-turbo/cjpeg', 'tools/jpeg-turbo'),
        ('trimage/tools/jpeg-turbo/djpeg', 'tools/jpeg-turbo'),
        ('trimage/tools/jpeg-turbo/jpegtran', 'tools/jpeg-turbo'),
    ]

# Filter out missing binaries (e.g., pngout on macOS, unbuilt tools)
tool_binaries = [(src, dst) for src, dst in tool_binaries if os.path.exists(src)]

a = Analysis(
    ['trimage/__main__.py'],
    pathex=['trimage'],
    binaries=tool_binaries,
    datas=[
        ('trimage/pixmaps', 'pixmaps'),
    ],
    hiddenimports=[
        'PyQt5.sip',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PIL',
        'PIL.Image',
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
    name='trimage',
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
