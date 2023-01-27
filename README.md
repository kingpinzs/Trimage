# Trimage image compressor

A cross-platform tool for optimizing PNG, JPG, GIF, and WEBP files.

Trimage is a cross-platform GUI and command-line interface(WIP) to optimize image files via 

[advpng](http://advancemame.sourceforge.net/comp-readme.html)
[jpegoptim](http://www.kokkonen.net/tjko/projects.html)
[jpegtran](https://www.jpegclub.org/jpegtran/)
[mozjpeg](https://github.com/mozilla/mozjpeg)
[guetzli](https://github.com/google/guetzli)
[optipng](http://optipng.sourceforge.net)
[pngcrush](https://pmt.sourceforge.io/pngcrush) 

depending on the filetype (currently, PNG, JPG, GIF, and WEBP files are supported).

It was inspired by
[imageoptim](http://imageoptim.pornel.net).

All image files are losslessly
compressed on the highest available compression levels. Trimage gives you
various input functions to fit your own workflow: a regular file dialog,
dragging and dropping and various command line options.

## Installation instructions

Visit [Trimage.org](http://trimage.org) to install the original Trimage as a package.

## Building instructions

### Prerequisites to be already installed on system
   Will be adding an automated way to pull them in at a later time

##### For UI
- PyQt5
- PyQt5-Tools

##### For Jpeg 
- jpegoptim
- jpegtran
- guetzli

##### For Png
- advpng
- optipng
- pngcrush

#### For Gif
- gifsicle

#### WEBP
- cwebp

##### ?
- butteraugli

##### For GUI Design
- pip install pyqt5 pyqt5-tools
- sudo apt install qttools5-dev-tools

### Build from source

Build and install by running:

    python setup.py build
    sudo python setup.py install


CREDIT
### Originally Made by [@kilianvalkhof](https://twitter.com/kilianvalkhof)
### FlatPack started by [@phillipsj](https://github.com/phillipsj)