#!/usr/bin/env python3

import re
from setuptools import setup, find_packages


def _read_version():
    with open("trimage/_version.py") as f:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
        if match:
            return match.group(1)
        raise RuntimeError("Unable to find version string in trimage/_version.py")


setup(
    name="trimage",
    version=_read_version(),
    description="Trimage image compressor - A cross-platform tool for optimizing PNG, JPG, GIF, and WEBP files",
    long_description=(
        "Trimage is a cross-platform GUI and command-line interface to optimize "
        "image files via bundled compression tools for PNG, JPG, GIF, and WEBP "
        "formats. It was inspired by imageoptim. All image files are losslessly "
        "compressed on the highest available compression levels. Trimage gives you "
        "various input functions to fit your own workflow: a regular file dialog, "
        "dragging and dropping, and various command line options."
    ),
    author="Kilian Valkhof, Paul Chaplin, Jeremy King, and others",
    author_email="help@trimage.org",
    url="http://trimage.org",
    license="MIT",
    python_requires=">=3.8",
    packages=find_packages(exclude=["*.env", "*.env.*"]),
    package_data={
        "trimage": [
            "pixmaps/*.*",
            "tools/**/*",
        ],
    },
    data_files=[
        ("share/icons/hicolor/scalable/apps", ["desktop/trimage.svg"]),
        ("share/applications", ["desktop/trimage.desktop"]),
        ("share/man/man1", ["doc/trimage.1"]),
    ],
    scripts=["bin/trimage"],
    install_requires=[
        "PyQt5",
        "Pillow",
    ],
    extras_require={
        "tinypng": ["tinify"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Graphics",
    ],
)
