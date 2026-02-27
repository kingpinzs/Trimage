#!/usr/bin/env python3

import sys
import errno
from os import path, access, X_OK
from subprocess import call, PIPE


def check_dependencies(tool_paths=None):
    """Check if the required compression tools exist.

    If tool_paths dict is provided, checks bundled tool paths.
    Otherwise returns True for backward compatibility.
    """
    if tool_paths is None:
        return True

    status = True
    for name, tool_path in tool_paths.items():
        if tool_path is None or not path.isfile(tool_path):
            status = False
            print(f"[error] {name} not found at {tool_path}", file=sys.stderr)
        elif not access(tool_path, X_OK):
            status = False
            print(f"[error] {name} at {tool_path} is not executable", file=sys.stderr)

    return status


import shutil
import subprocess as _subprocess
import logging

_logger = logging.getLogger(__name__)


def detect_imagemagick():
    """Detect system ImageMagick installation.

    Checks for ImageMagick 7 ('magick') first, then ImageMagick 6 ('convert')
    with version string verification to avoid name collision with other
    'convert' utilities (e.g., the 'units' package on some Linux distros).

    Returns:
        (path, version): Tuple of (executable_path, version_int) or (None, None).
    """
    # ImageMagick 7 uses 'magick' as the primary command
    magick_path = shutil.which('magick')
    if magick_path:
        _logger.info("ImageMagick 7 detected at %s", magick_path)
        return magick_path, 7

    # ImageMagick 6 uses 'convert' directly
    convert_path = shutil.which('convert')
    if convert_path:
        try:
            result = _subprocess.run(
                [convert_path, '--version'],
                capture_output=True, text=True, timeout=5
            )
            if 'ImageMagick' in result.stdout:
                _logger.info("ImageMagick 6 detected at %s", convert_path)
                return convert_path, 6
        except (_subprocess.TimeoutExpired, OSError):
            pass

    _logger.info("ImageMagick not found (optional)")
    return None, None


def safe_call(command):
    """Cross-platform command-line check."""
    while True:
        try:
            return call(command, shell=True, stdout=PIPE)
        except OSError as e:
            if e.errno == errno.EINTR:
                continue
            else:
                raise


def human_readable_size(num, suffix="B"):
    """Bytes to a readable size format"""
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Y", suffix)
