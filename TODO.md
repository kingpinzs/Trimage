# Todo

## Completed
- [x] General refactoring (logging, imports, deprecated APIs, code quality)
- [x] sys.exit(1) for errors — replaced with proper error handling (self.valid = False)
- [x] Clear the list / add a "clear" button
- [x] Remove individual rows from table
- [x] Drag and drop folders
- [x] Figure out how to make Mac and Win versions (via PyInstaller with bundled tools)
- [x] Fix drag-and-drop (event filter on viewport for PyQt5 model-view compatibility)
- [x] Fix 19+ bugs in compression pipeline
- [x] Bundle gifsicle for Linux
- [x] Fix all installer/build infrastructure (PyInstaller, deb, setup.py, Flatpak)
- [x] Context managers for compression (CompressionContext: atomic operations with rollback)
- [x] Always on top option (Pin button with QSettings persistence)
- [x] ImageMagick integration (optional system tool, auto-detected v6/v7)
- [x] TinyPNG API integration (replaces PunyPNG; preferences dialog, optional tinify package)
- [x] Comprehensive tabbed preferences dialog (13 tabs: General, jpegoptim, Guetzli, MozJPEG, OptiPNG, AdvPNG, PNGCrush, Gifsicle, cwebp, gif2webp, ImageMagick, TinyPNG, About)
- [x] Dynamic command building from settings (replaces hardcoded compression flags)
- [x] Configurable worker threads and combination testing toggle
- [x] Settings key migration (alwaysOnTop → general/alwaysOnTop)

- [x] Single version source: `trimage/_version.py` is the sole `__version__` definition, read by setup.py and build_deb.py
- [x] `-f` accepts multiple files: `trimage -f img1.jpg img2.png img3.gif`
- [x] `-r`/`--recursive` flag for `-d`: `trimage -d ./images -r` walks subdirectories
- [x] Three-level verbosity: `-q` (quiet), default (normal file stats), `-v` (verbose tool output)
- [x] Floating drop zone widget: always-on-top translucent 64x64 widget, toggle with Alt+D or systray menu, position saved
- [x] Intelligent recompression: per-file settings hash, compress count tracking, max retries preference, skip already-optimized

## Remaining
- (none — all planned features implemented)
