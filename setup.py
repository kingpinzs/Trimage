#!/usr/bin/env python3

from setuptools import setup


setup(name = "trimage",
    version = "1.1.0",
    description = "Trimage image compressor - A cross-platform tool for optimizing PNG, JPG, GIF, and WEBP files",
    author = "Kilian Valkhof, Paul Chaplin, Jeremy King, and others",
    author_email = "help@trimage.org",
    url = "http://trimage.org",
    license = "MIT license",
    packages = ["trimage",
              "trimage.ThreadPool"],
    package_data = {"trimage" : ["pixmaps/*.*"] },
    data_files=[('share/icons/hicolor/scalable/apps', ['desktop/trimage.svg']),
            ('share/applications', ['desktop/trimage.desktop']),
            ('share/man/man1', ['doc/trimage.1'])],
    scripts = ["bin/trimage"],
    long_description = """Trimage is a cross-platform GUI and command-line interface to optimize image files via advpng, jpegoptim, optipng and pngcrush, depending on the filetype (currently, PNG and JPG files are supported). It was inspired by imageoptim. All image files are losslessy compressed on the highest available compression levels. Trimage gives you various input functions to fit your own workflow: A regular file dialog, dragging and dropping and various command line options.""",
    install_requires = ["PyQt5"]
  )
