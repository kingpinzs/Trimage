#!/usr/bin/env python3

import logging
import time
import sys
import os
from os import listdir, path, remove, access, W_OK, rename, makedirs
from pathlib import Path
import tempfile
from shutil import copy, rmtree
import subprocess
import mimetypes
import platform
from itertools import combinations

from argparse import ArgumentParser
from multiprocessing import cpu_count
from queue import Queue

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from ThreadPool import ThreadPool
from ui import Ui_trimage, DropZoneWidget
from tools import *

from PIL import Image as PILImage

logger = logging.getLogger(__name__)

from _version import __version__ as VERSION

# Verbosity levels for CLI mode
VERBOSITY_QUIET = 0
VERBOSITY_NORMAL = 1
VERBOSITY_VERBOSE = 2

# Determine the OS
os_type = platform.system()

# Determine base path (handles PyInstaller frozen bundles and normal execution)
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    base_path = path.dirname(sys.executable)
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS  # PyInstaller onefile extracts here
else:
    # Running as normal Python script
    base_path = path.dirname(path.realpath(__file__))

# Define the command strings based on the OS
if os_type == "Windows":
    tool_path = path.join(base_path, "tools", "windows")
    exe_ext = ".exe"
    move_cmd = "move"
else:
    tool_path = path.join(base_path, "tools")
    exe_ext = ""
    move_cmd = "mv"

# Pixmap/resource paths (absolute)
compressing_icon_path = path.join(base_path, "pixmaps", "compressing.gif")
trimage_icon_path = path.join(base_path, "pixmaps", "trimage-icon.png")
list_add_path = path.join(base_path, "pixmaps", "list-add.png")
view_refresh_path = path.join(base_path, "pixmaps", "view-refresh.png")
clear_table_path = path.join(base_path, "pixmaps", "clear_table.png")

# Compression tool paths (absolute, OS independent)
jpegoptim_path = path.join(tool_path, "jpegoptim", f"jpegoptim{exe_ext}")
guetzli_path = path.join(tool_path, "guetzli", f"guetzli{exe_ext}")
mozjpeg_path = path.join(tool_path, "mozjpeg", f"jpegtran-static{exe_ext}")
webp_path = path.join(tool_path, "webp", f"cwebp{exe_ext}")
optipng_path = path.join(tool_path, "optipng", f"optipng{exe_ext}")
advpng_path = path.join(tool_path, "advpng", f"advpng{exe_ext}")
pngcrush_path = path.join(tool_path, "pngcrush", f"pngcrush{exe_ext}")
gifsicle_path = path.join(tool_path, "gifsicle", f"gifsicle{exe_ext}")
gif2webp_path = path.join(tool_path, "webp", f"gif2webp{exe_ext}")
dwebp_path = path.join(tool_path, "webp", f"dwebp{exe_ext}")
webpinfo_path = path.join(tool_path, "webp", f"webpinfo{exe_ext}")

# Detect optional system ImageMagick
imagemagick_path, imagemagick_version = detect_imagemagick()


# Get the platform-independent temp directory
#temp_dir = tempfile.gettempdir() #will add this back once the combination tests are working
#temp_dir = getcwd()

class AnimatedIconDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, imagelist=None):
        super(AnimatedIconDelegate, self).__init__(parent)
        self.movies = {}
        self.imagelist = imagelist

    def paint(self, painter, option, index):
        super(AnimatedIconDelegate, self).paint(painter, option, index)
        if index.column() == 0:  # check if the column is 0
            gif_movie = index.data(Qt.DecorationRole)
            if gif_movie is not None:
                if index.row() not in self.movies:
                    self.movies[index.row()] = gif_movie
                    gif_movie.frameChanged.connect(lambda: self.update(index))
                if gif_movie.state() == QMovie.Running:  # check if the movie is running
                    pixmap = gif_movie.currentPixmap()
                    # adjust the size and position of the pixmap
                    pixmap = pixmap.scaled(16, 16, Qt.KeepAspectRatio)
                    pixmap_rect = QRect(option.rect.topLeft(), pixmap.size())
                    # center the pixmap horizontally in the cell
                    pixmap_rect.moveLeft(int(5))
                    pixmap_rect.moveTop(int(option.rect.center().y() - pixmap.height() / 2))
                    painter.drawPixmap(pixmap_rect, pixmap)

    def stopAnimation(self, row):
        if row in self.movies:
            self.movies[row].stop()
            del self.movies[row]
            self.parent().update()

    def update(self, index):
        # Emit the dataChanged signal for the cell
        self.parent().update(index)


class StartQt(QMainWindow):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.ui = Ui_trimage()
        self.ui.setupUi(self)

        self.showapp = True
        self.verbose = VERBOSITY_NORMAL
        self.imagelist = []

        # set application name and organization
        QCoreApplication.setOrganizationName("Kilian Valkhof")
        QCoreApplication.setOrganizationDomain("trimage.org")
        QCoreApplication.setApplicationName("Trimage")

        self.settings = QSettings()

        # Migrate old settings keys to new namespaced keys
        if self.settings.contains("alwaysOnTop") and not self.settings.contains("general/alwaysOnTop"):
            self.settings.setValue("general/alwaysOnTop", self.settings.value("alwaysOnTop", False, type=bool))
            self.settings.remove("alwaysOnTop")

        # if there is a previously saved geometry, restore it
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))

        # check if dependencies are installed
        tool_paths = {
            "jpegoptim": jpegoptim_path,
            "guetzli": guetzli_path,
            "mozjpeg": mozjpeg_path,
            "cwebp": webp_path,
            "dwebp": dwebp_path,
            "optipng": optipng_path,
            "advpng": advpng_path,
            "pngcrush": pngcrush_path,
            "gifsicle": gifsicle_path,
            "gif2webp": gif2webp_path,
        }
        if not check_dependencies(tool_paths):
            quit()

        # add quit shortcut
        if hasattr(QKeySequence, "Quit"):
            self.quit_shortcut = QShortcut(QKeySequence(QKeySequence.Quit),
                self)
        else:
            self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)

        # disable recompress button initially
        self.ui.recompress.setEnabled(False)

        # make a worker thread
        from preferences import get_setting
        max_workers = get_setting(self.settings, "general/workerThreads")
        self.thread = Worker(max_workers=max_workers)

        # connect signals with slots
        self.ui.addfiles.clicked.connect(self.file_dialog)
        self.ui.recompress.clicked.connect(self.recompress_files)
        self.ui.clearTable.clicked.connect(self.clear_table)
        self.quit_shortcut.activated.connect(self.close)
        self.ui.processedfiles.drop_event_signal.connect(self.file_drop)
        self.thread.finished.connect(self.update_table)
        self.thread.update_ui_signal.connect(self.update_table)
        self.ui.alwaysOnTop.clicked.connect(self.toggle_always_on_top)
        self.ui.settingsBtn.clicked.connect(self.open_preferences)
        self.ui.rescueBtn.clicked.connect(self.open_rescue_dialog)

        # Restore "always on top" preference
        if get_setting(self.settings, "general/alwaysOnTop"):
            self.ui.alwaysOnTop.setChecked(True)
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # Initialize TinyPNG with saved settings
        self._init_tinypng()

        """Has to be a label and not an icon"""
        #self.compressing_icon = QIcon(QPixmap(self.ui.get_image("pixmaps/compressing.gif")))
   
        # create a QLabel for the compressing icon
        self.compressing_icon = QLabel(self)
        self.compressing_icon.setFixedSize(16, 16)
        # set the size and position of the label
        #self.compressing_icon.setGeometry(QRect(0, 0, 16, 16))
        # self.compressing_icon.setStyleSheet("border: 1px solid black;")
        # create a QMovie for the gif animation
        self.compressing_icon_gif = QMovie(compressing_icon_path)
        # set the gif animation on the label
        self.compressing_icon.setMovie(self.compressing_icon_gif)
        # hide the label initially
        self.compressing_icon.hide()

        # activate command line options
        self.commandline_options()

        # check if system tray is available and not in cli mode
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.cli:
            self.systemtray = Systray(self)

        # Floating drop zone widget
        if not self.cli:
            self.drop_zone = DropZoneWidget(self)
            self.drop_zone.files_dropped.connect(self.file_drop)
            # Restore saved position
            dz_pos = self.settings.value("dropzone/position")
            if dz_pos:
                self.drop_zone.move(dz_pos)
            # Restore visibility state
            if self.settings.value("dropzone/visible", False, type=bool):
                self.drop_zone.show()
            # Alt+D shortcut to toggle
            self.dropzone_shortcut = QShortcut(QKeySequence("Alt+D"), self)
            self.dropzone_shortcut.activated.connect(self.toggle_drop_zone)

        # create and set the delegate for the column where you want to display the animated icon
        delegate = AnimatedIconDelegate(self.ui.processedfiles, self.imagelist)
        self.ui.processedfiles.setItemDelegateForColumn(0, delegate)  # replace 4 with the column number where you want to display the animated icon

    def commandline_options(self):
        """Set up the command line options."""
        self.cli = False
        parser = ArgumentParser(
            description="GUI front-end to compress png and jpg images via "
                "advpng, jpegoptim, optipng and pngcrush")

        parser.add_argument("--version", action="version",
            version=f"%(prog)s {VERSION}")
        parser.add_argument("-v", "--verbose", action="store_const",
            const=VERBOSITY_VERBOSE, dest="verbosity",
            help="Verbose mode: show per-file stats and tool output")
        parser.add_argument("-q", "--quiet", action="store_const",
            const=VERBOSITY_QUIET, dest="verbosity",
            help="Quiet mode: suppress all output")
        parser.set_defaults(verbosity=VERBOSITY_NORMAL)

        parser.add_argument("-f", "--file",
            dest="filename", nargs='+',
            help="compress one or more image files and exit")
        parser.add_argument("-d", "--directory",
            dest="directory", help="compress images in directory and exit")
        parser.add_argument("-r", "--recursive", action="store_true",
            default=False, dest="recursive",
            help="recursively process subdirectories (use with -d)")

        options = parser.parse_args()

        # make sure we quit after processing finished if using cli
        if options.filename or options.directory:
            self.thread.finished.connect(quit)
            self.cli = True

        # send to correct function
        if options.filename:
            self.file_from_cmd(options.filename)
        if options.directory:
            self.dir_from_cmd(options.directory, recursive=options.recursive)

        self.verbose = options.verbosity

    """
    Input functions
    """

    def dir_from_cmd(self, directory, recursive=False):
        """Read the files in the directory and send them to compress_file."""
        self.showapp = False
        dirpath = path.abspath(directory)
        if recursive:
            # Pass the directory itself; delegator() calls walk() for recursion
            self.delegator([dirpath])
        else:
            imagedir = listdir(directory)
            filelist = [path.join(dirpath, image) for image in imagedir]
            self.delegator(filelist)

    def file_from_cmd(self, images):
        """Get file(s) from -f flag and send them to compress_file."""
        self.showapp = False
        filelist = [path.abspath(img) for img in images]
        self.delegator(filelist)

    def file_drop(self, images):
        """
        Get a file from the drag and drop handler and send it to compress_file.
        """
        self.delegator(images)

    def file_dialog(self):
        """Open a file dialog and send the selected images to compress_file."""
        fd = QFileDialog(self)
        if (self.settings.value("fdstate")):
            fd.restoreState(self.settings.value("fdstate"))
        directory = self.settings.value("directory", "")
        fd.setDirectory(directory)

        images, _ = fd.getOpenFileNames(self,
            "Select one or more image files to compress",
            directory,
            # this is a fix for file dialog differentiating between cases
            "Image files (*.png *.jpg *.jpeg *.PNG *.JPG *.JPEG *.gif *.GIF)")

        self.settings.setValue("fdstate", fd.saveState())
        if images:
            self.settings.setValue("directory", path.dirname(images[0]))
            self.delegator([fullpath for fullpath in images])

    def recompress_files(self):
        """Send each file in the current file list to compress_file again."""
        self.delegator([row.image.fullpath for row in self.imagelist])

    """
    Compress functions
    """
    def delegator(self, images):
        """
        Receive all images, check them and send them to the worker thread.
        """
        delegatorlist = []
        for fullpath in images:
            try: # recompress images already in the list
                image = next(i.image for i in self.imagelist
                    if i.image.fullpath == fullpath)
                if image.compressed:
                    should_skip, reason = image.should_skip_recompression()
                    if should_skip:
                        image.skip_reason = reason
                        logger.info("Skipping %s: %s", image.fullpath, reason)
                        continue
                    image.reset()
                    image.recompression = True
                    delegatorlist.append(image)
            except StopIteration:
                if not path.isdir(fullpath):
                    self.add_image(fullpath, delegatorlist, compressing_icon_path)
                else:
                    self.walk(fullpath, delegatorlist)

        # update the table view
        self.update_table()
        # send the images to the worker thread for compression
        self.thread.compress_file(delegatorlist, self.showapp, self.verbose,
            self.imagelist)

    def walk(self, dir, delegatorlist):
        """
        Walks a directory, and executes a callback on each file.
        """
        dir = path.abspath(dir)
        for file in [file for file in listdir(dir) if not file in [".","..",".svn",".git",".hg",".bzr",".cvs"]]:
            nfile = path.join(dir, file)

            if path.isdir(nfile):
                self.walk(nfile, delegatorlist)
            else:
                self.add_image(nfile, delegatorlist, compressing_icon_path)

    def add_image(self, fullpath, delegatorlist, compressing_icon_path):
        """
        Adds an image file to the delegator list and update the tray and the title of the window.
        """
        image = Image(fullpath, self)
        image.row = len(self.imagelist)

        # Run validation if enabled
        from preferences import get_setting
        if image.valid and get_setting(self.settings, "repair/autoValidate"):
            image.validate()

        imageRow = ImageRow(image, compressing_icon_path)

        # Check if the image is valid
        if image.valid:
            # Append the image to the delegatorlist and imagelist
            delegatorlist.append(image)
            self.imagelist.append(imageRow)
            
            # Check if the system tray is available and if the application is not running on CLI
            if QSystemTrayIcon.isSystemTrayAvailable() and not self.cli:
                # Update the tool tip of the system tray icon with the number of files
                self.systemtray.trayIcon.setToolTip("Trimage image compressor (" + str(len(self.imagelist)) + " files)")
                # Update the title of the window with the number of files
                self.setWindowTitle("Trimage image compressor (" + str(len(self.imagelist)) + " files)")
        else:
            # Print error message if the image is not valid
            logger.warning("Not a supported image file and/or not writable: %s", image.fullpath)

    """
    UI Functions
    """

    def update_table(self):
        """Update the table view with the latest file data."""
        tview = self.ui.processedfiles
        # set table model
        tmodel = TriTableModel(self, self.imagelist,
            ["Filename", "Old Size", "New Size", "Compressed", "Health"])
        tview.setModel(tmodel)

        # set minimum size of table
        vh = tview.verticalHeader()
        vh.setVisible(False)

        # set horizontal header properties
        hh = tview.horizontalHeader()
        hh.setStretchLastSection(True)

        # set all row heights
        nrows = len(self.imagelist)
        for row in range(nrows):
            tview.setRowHeight(row, 25)

        # set the second column to be longest
        tview.setColumnWidth(0, 300)

        # enable recompress button
        self.enable_recompress()

    def remove_row(self, row):
        """Remove a single row from the image list and refresh the table."""
        if 0 <= row < len(self.imagelist):
            self.imagelist.pop(row)
            # Re-index remaining rows
            for i, image_row in enumerate(self.imagelist):
                image_row.image.row = i
            self.update_table()

    def clear_table(self):
        self.imagelist.clear()  # Assuming imagelist is a list. Adjust accordingly.
        self.update_table()  # Refresh the table view.



    def enable_recompress(self):
        """Enable the recompress button."""
        self.ui.recompress.setEnabled(True)
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.cli:
            self.systemtray.recompress.setEnabled(True)

    def hide_main_window(self):
        if self.isVisible():
            self.hide()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.systemtray.hideMain.setText("&Show window")
        else:
            self.show()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.systemtray.hideMain.setText("&Hide window")

    def closeEvent(self, event):
      self.settings.setValue("geometry", self.saveGeometry())
      # Save drop zone state
      if hasattr(self, 'drop_zone'):
          self.settings.setValue("dropzone/position", self.drop_zone.pos())
          self.settings.setValue("dropzone/visible", self.drop_zone.isVisible())
          self.drop_zone.close()
      event.accept()

    def toggle_always_on_top(self, checked):
        """Toggle the WindowStaysOnTopHint flag and save to settings."""
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.settings.setValue("general/alwaysOnTop", checked)
        self.show()  # Required — Qt hides window after setWindowFlags change

    def toggle_drop_zone(self):
        """Toggle the floating drop zone widget visibility."""
        if not hasattr(self, 'drop_zone'):
            return
        if self.drop_zone.isVisible():
            self.drop_zone.hide()
        else:
            self.drop_zone.show()
        # Update systray menu check state if available
        if hasattr(self, 'systemtray') and hasattr(self.systemtray, 'dropZoneAction'):
            self.systemtray.dropZoneAction.setChecked(self.drop_zone.isVisible())

    def open_preferences(self):
        """Open the preferences dialog."""
        from preferences import PreferencesDialog, get_setting
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            self._init_tinypng()
            # Re-sync always-on-top state from settings
            on_top = get_setting(self.settings, "general/alwaysOnTop")
            self.ui.alwaysOnTop.setChecked(on_top)
            if on_top:
                self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            else:
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()

    def open_rescue_dialog(self):
        """Open the image rescue/file carving dialog."""
        from rescue_dialog import RescueDialog
        dialog = RescueDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            extracted = dialog.get_extracted_files()
            if extracted:
                self.delegator(extracted)

    def _init_tinypng(self):
        """Initialize TinyPNG API with saved settings."""
        try:
            import tinypng
            if tinypng.is_available():
                enabled = self.settings.value("tinypng/enabled", False, type=bool)
                key = self.settings.value("tinypng/apiKey", "")
                if enabled and key:
                    tinypng.set_api_key(key)
                    logger.info("TinyPNG integration enabled")
                else:
                    logger.info("TinyPNG integration disabled")
            else:
                logger.info("TinyPNG not available (tinify not installed)")
        except ImportError:
            logger.info("TinyPNG module not found")


class TriTableModel(QAbstractTableModel):
    def __init__(self, parent, imagelist, header, *args):
        """
        @param parent Qt parent object.
        @param imagelist A list of tuples.
        @param header A list of strings.
        """
        QAbstractTableModel.__init__(self, parent, *args)
        self.imagelist = imagelist
        self.header = header

        # Connect the frameChanged signal of each QMovie to the update method
        for imageRow in self.imagelist:
            imageRow.compressing_icon_gif.frameChanged.connect(self.update)

    def update(self):
        # Emit the dataChanged signal for all cells in the 'icon' column
        top_left = self.index(0, 0)  # Replace 4 with the column number of the 'icon' column
        bottom_right = self.index(self.rowCount() - 1, 0)
        self.dataChanged.emit(top_left, bottom_right)

    def flags(self, index):
        """Return item flags, including drop-enabled for drag-and-drop support."""
        default_flags = super().flags(index)
        return default_flags | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        """Allow copy drop actions for file drag-and-drop."""
        return Qt.CopyAction

    def rowCount(self, parent=QModelIndex()):
        """Count the number of rows."""
        return len(self.imagelist)

    def columnCount(self, parent):
        """Count the number of columns."""
        return len(self.header)

    def data(self, index, role):
        """Fill the table with data."""
        if not index.isValid():
            return None
        elif role == Qt.DisplayRole:
            data = self.imagelist[index.row()][index.column()]
            return data
        elif index.column() == 0 and role == Qt.DecorationRole:
            gif_movie = self.imagelist[index.row()].compressing_icon_gif
            return gif_movie
        else:
            return None

    def headerData(self, col, orientation, role):
        """Fill the table headers."""
        if orientation == Qt.Horizontal and (role == Qt.DisplayRole or
        role == Qt.DecorationRole):
            return self.header[col]
        return None


class ImageRow:
    def __init__(self, image, compressing_icon_path):
        """Build the information visible in the table image row."""
        self.image = image
        self.compressing_icon_gif = QMovie(compressing_icon_path)
        self.compressing_icon_gif.start() 
        
        """Having the gif play in the row"""
        d = {
            'filename_w_ext': lambda i: self.statusStr().format(i.filename_w_ext),
            'oldfilesizestr': lambda i: human_readable_size(i.oldfilesize)
                if i.compressed else "",
            'newfilesizestr': lambda i: human_readable_size(i.newfilesize)
                if i.compressed else "",
            'ratiostr': lambda i:
                "%.1f%%" % (100 - (float(i.newfilesize) / i.oldfilesize * 100))
                if i.compressed and i.oldfilesize > 0 else "",
            'icon': lambda i: self.compressing_icon_gif if not i.compressed else i.icon,
            'fullpath': lambda i: i.fullpath, #only used by cli
            'diagnosis': lambda i: self._diagnosis_str(),
        }
        names = ['filename_w_ext', 'oldfilesizestr', 'newfilesizestr',
                      'ratiostr', 'diagnosis']
        for i, n in enumerate(names):
            d[i] = d[n]

        self.d = d

    def updateIcon(self):
        # Get the current frame of the animation as a QPixmap
        pixmap = QPixmap.fromImage(self.compressing_icon_gif.currentImage())
        # Create an icon from the pixmap
        icon = QIcon(pixmap)
        # Update the icon in the model
        self.d['icon'] = lambda i: icon

    def animateIcon(self, waitingIcon, compressing_icon_gif, index ):
        logger.debug("animateIcon index: %s", index)
        #waitingIcon.setGeometry(5, 70+32, 16, 16)
        waitingIcon.movie().start()
        compressing_icon_gif.start()

        self.updateIcon()  # update the icon in the model

        return waitingIcon

    def stopAnimationIcon(self, icon, waitingIcon):
        waitingIcon.hide()
        waitingIcon.movie().stop() 
        waitingIcon.setVisible(False)

        self.updateIcon()  # update the icon in the model

        return icon

    def _diagnosis_str(self):
        """Return human-readable diagnosis string for Health column."""
        if self.image.repaired:
            return "Repaired"
        if self.image.diagnosis is None:
            return ""
        d = self.image.diagnosis
        if d.is_valid:
            return "OK"
        severity = d.severity.name if hasattr(d.severity, 'name') else str(d.severity)
        top_issues = ", ".join(d.issues[:2])
        if top_issues:
            return f"{severity}: {top_issues[:60]}"
        return severity

    def statusStr(self):
        """Set the status message."""
        if self.image.skip_reason:
            return "{0} (" + self.image.skip_reason + ")"
        if self.image.failed:
            return "ERROR: {0}"
        if self.image.compressing:
            message = "Compressing {0}..."
            return message
        if self.image.repaired and not self.image.compressed:
            return "Repaired {0}, queued..."
        if not self.image.compressed and self.image.recompression:
            return "Queued for recompression {0}..."
        if not self.image.compressed:
            return "Queued {0}..."
        if self.image.repaired:
            return "{0} (repaired)"
        return "{0}"

    def __getitem__(self, key):
        return self.d[key](self.image)


class CompressionContext:
    """Context manager for atomic image compression with rollback.

    Handles backup, temp directory creation, and cleanup. On error,
    restores the original file and cleans up. On success, the caller
    is responsible for replacing the original with the best result
    before exiting the context.
    """

    def __init__(self, image):
        self.image = image
        self.temp_dir = None
        self.backup_path = None
        self.original_path = image.fullpath

    def __enter__(self):
        # Create temp working directory next to the original file
        file_path = Path(self.original_path)
        temp_dir_name = f"{self.image.filename}_tmp"
        self.temp_dir = file_path.parent / temp_dir_name
        makedirs(self.temp_dir, exist_ok=True)

        # Backup original file into temp dir
        self.backup_path = path.join(self.temp_dir, self.image.filename_w_ext)
        copy(self.original_path, self.backup_path)

        self.image.compressing = True
        logger.debug("Compression context entered for %s", self.original_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                # Error occurred — rollback: restore original from backup
                if self.backup_path and path.exists(self.backup_path):
                    copy(self.backup_path, self.original_path)
                logger.error("Compression failed for %s: %s", self.original_path, exc_val)
        finally:
            # Always reset compressing flag and clean up temp dir
            self.image.compressing = False
            if self.temp_dir and path.exists(str(self.temp_dir)):
                rmtree(str(self.temp_dir), ignore_errors=True)
            logger.debug("Compression context exited for %s", self.original_path)
        # Suppress exceptions to prevent crashing the worker thread
        return True


class RepairContext:
    """Context manager for atomic image repair with rollback.

    Same pattern as CompressionContext but for repair operations.
    """

    def __init__(self, image):
        self.image = image
        self.temp_dir = None
        self.backup_path = None
        self.original_path = image.fullpath

    def __enter__(self):
        file_path = Path(self.original_path)
        temp_dir_name = f"{self.image.filename}_repair_tmp"
        self.temp_dir = file_path.parent / temp_dir_name
        makedirs(self.temp_dir, exist_ok=True)
        self.backup_path = path.join(self.temp_dir, self.image.filename_w_ext)
        copy(self.original_path, self.backup_path)
        logger.debug("Repair context entered for %s", self.original_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                if self.backup_path and path.exists(self.backup_path):
                    copy(self.backup_path, self.original_path)
                logger.error("Repair failed for %s: %s", self.original_path, exc_val)
        finally:
            if self.temp_dir and path.exists(str(self.temp_dir)):
                rmtree(str(self.temp_dir), ignore_errors=True)
            logger.debug("Repair context exited for %s", self.original_path)
        return True


class Image:
    def __init__(self, fullpath, parent=None):
        """Gather image information."""
        self.valid = False
        self.reset()
        self.fullpath = path.normpath(fullpath)
        self.filename_w_ext = path.basename(self.fullpath)
        self.filename, self.filetype = path.splitext(self.filename_w_ext)
        self.file_base = self.filename+'.webp'
        self.parent = parent
        self.row = None
        self.compress_count = 0
        self.last_ratio = None
        self.optimization_hash = None
        self.skip_reason = None
        self.diagnosis = None
        self.repaired = False
        self.repair_log = []
        if path.isfile(self.fullpath) and access(self.fullpath, W_OK):
            self.filetype = self.filetype[1:].lower()
            # Get the actual file type based on the file contents
            actual_type = self.get_file_type(self.fullpath)
            logger.debug("Detected file type: %s", actual_type)
            if actual_type is not None:
                # If the actual extension doesn't match the current file type, update it
                if actual_type != self.filetype:
                    logger.debug("Updating file type from %s to %s", self.filetype, actual_type)
                        # Change the file extension
                    new_name = self.change_file_extension(self.fullpath, actual_type)
                    if new_name is None:
                        self.failed = True
                        return
                    # Update the file path to the new name
                    self.fullpath = new_name
                    self.filetype = actual_type
                    logger.debug("New file name: %s (type: %s)", new_name, actual_type)
            if self.filetype == "jpg":
                self.filetype = "jpeg"
            if self.filetype == "webp":
                # Convert the WebP image to JPEG
                retcode = subprocess.call([dwebp_path, self.fullpath, '-o', f'{self.fullpath}.png'])
                if retcode != 0:
                    logger.error("Failed to convert %s from WebP to PNG", self.fullpath)
                    self.failed = True
                    return
                # Update the file path and type to the new JPEG image
                self.fullpath = f'{self.fullpath}.png'
                self.filetype = 'png'
                # Check if the PNG image has an alpha channel
                if not self.has_alpha_channel(self.fullpath):
                    # Convert the PNG image to JPEG
                    jpg_file = self.convert_png_to_jpg(self.fullpath)
                    if jpg_file is None:
                        self.failed = True
                        return
                    # Update the file path and type to the new JPEG image
                    self.fullpath = jpg_file
                    self.filetype = 'jpeg'
            if self.filetype not in ["jpeg", "png", "gif"]:
                self.valid = False
                return
            oldfile = QFileInfo(self.fullpath)
            self.oldfilesize = oldfile.size()
            self.icon = QIcon(self.fullpath)
            self.valid = True

    def reset(self):
        self.failed = False
        self.compressed = False
        self.compressing = False
        self.recompression = False
        self.skip_reason = None
        self.diagnosis = None
        self.repaired = False
        self.repair_log = []

    def _compute_settings_hash(self):
        """Compute a hash of the current compression settings for this file type."""
        import hashlib
        from preferences import get_setting, DEFAULTS
        s = self.parent.settings

        settings_data = []
        settings_data.append(str(get_setting(s, "general/webpEnabled")))
        settings_data.append(str(get_setting(s, "general/combinationTesting")))

        if self.filetype == "jpeg":
            prefixes = ("jpegoptim/", "guetzli/", "mozjpeg/", "cwebp/", "imagemagick/")
        elif self.filetype == "png":
            prefixes = ("optipng/", "advpng/", "pngcrush/", "cwebp/", "imagemagick/")
        elif self.filetype == "gif":
            prefixes = ("gifsicle/", "gif2webp/", "imagemagick/")
        else:
            prefixes = ()

        for key in sorted(k for k in DEFAULTS if k.startswith(prefixes)):
            settings_data.append(f"{key}={get_setting(s, key)}")

        return hashlib.md5("|".join(settings_data).encode()).hexdigest()

    def should_skip_recompression(self):
        """Check whether this file should be skipped during recompression.

        Returns (should_skip, reason) tuple.
        """
        from preferences import get_setting

        if not self.compressed:
            return False, ""

        max_retries = get_setting(self.parent.settings, "general/maxRetries")

        # Check retry limit
        if self.compress_count >= max_retries:
            return True, "Max retries reached"

        # Check if settings are unchanged and last compression had no savings
        current_hash = self._compute_settings_hash()
        if self.optimization_hash == current_hash:
            if self.last_ratio is not None and self.last_ratio <= 0.0:
                return True, "Already optimized"

        return False, ""

    def validate(self):
        """Run diagnosis on this image file.

        Returns the DiagnosisResult.
        """
        from repair import diagnose
        tool_paths = {
            "optipng": optipng_path,
            "pngcrush": pngcrush_path,
            "webpinfo": webpinfo_path,
            "gifsicle": gifsicle_path,
            "imagemagick": imagemagick_path,
            "imagemagick_version": imagemagick_version,
        }
        self.diagnosis = diagnose(self.fullpath, tool_paths)
        return self.diagnosis

    def do_repair(self):
        """Attempt to repair this image based on diagnosis results.

        Must be called after validate(). Uses RepairContext for atomic safety.
        """
        if self.diagnosis is None:
            self.validate()
        if self.diagnosis.is_valid:
            return True

        from repair import repair as run_repair
        from preferences import get_setting

        tool_paths = {
            "optipng": optipng_path,
            "pngcrush": pngcrush_path,
            "webpinfo": webpinfo_path,
            "gifsicle": gifsicle_path,
            "imagemagick": imagemagick_path,
            "imagemagick_version": imagemagick_version,
        }

        settings = {}
        if self.parent and self.parent.settings:
            s = self.parent.settings
            for key in ("repair/truncationRecovery", "repair/stripCorruptMetadata",
                        "repair/headerReconstruction", "repair/iccProfileStrategy",
                        "repair/metadataStrategy"):
                settings[key] = get_setting(s, key)

        with RepairContext(self) as ctx:
            success, actions = run_repair(self.fullpath, self.diagnosis,
                                          tool_paths, settings)
            self.repair_log = actions
            self.repaired = success
            if success:
                # Re-validate after repair
                self.validate()
                # Update file size
                self.oldfilesize = path.getsize(self.fullpath)
                logger.info("Repaired %s: %s", self.fullpath, actions)
            else:
                logger.warning("Repair failed for %s", self.fullpath)

        return self.repaired

    def get_file_type(self, filepath):
        if os.name == 'posix':
        # Unix/Linux/macOS
            try:
                output = subprocess.check_output(['file', '--mime', '-b', filepath])
                output = output.decode('utf-8').split(';')[0].strip()
                _, mime_type = output.split('/', 1)  # Extract the part after the slash
                return mime_type
            except subprocess.CalledProcessError as e:
                logger.warning("Failed to determine file type of %s: %s", filepath, e)
                return None
        else:
            # Windows
            mime_type, _ = mimetypes.guess_type(filepath)
            if mime_type:
                return mime_type.split('/')[-1]  # Extract the part after the slash
            else:
                logger.warning("Failed to determine file type of %s", filepath)
                return None
        
    def change_file_extension(self, filename, new_extension):
        base_name, _ = path.splitext(filename)
        new_name = base_name + '.' + new_extension
        try:
            rename(filename, new_name)
        except OSError as e:
            logger.error("Failed to change file extension of %s to %s: %s", filename, new_extension, e)
            return None
        return new_name

    def convert_png_to_jpg(self, png_file):
        img = PILImage.open(png_file)
        rgb_img = img.convert('RGB')
        jpg_file = png_file.rsplit('.', 1)[0] + '.jpg'
        rgb_img.save(jpg_file)
        return jpg_file

    def has_alpha_channel(self, image_file):
        img = PILImage.open(image_file)
        return img.mode in ('RGBA', 'LA')


    def _build_run_commands(self):
        """Build compression command lists dynamically from QSettings."""
        from preferences import get_setting
        s = self.parent.settings

        jpeg_commands = []
        png_commands = []
        gif_commands = []

        # --- JPEG pipeline ---
        if get_setting(s, "jpegoptim/enabled"):
            cmd = f'{jpegoptim_path} -f'
            strip = get_setting(s, "jpegoptim/stripMode")
            if strip == "all":
                cmd += ' --strip-all'
            elif strip == "exif":
                cmd += ' --strip-exif'
            elif strip == "icc":
                cmd += ' --strip-icc'
            elif strip == "com":
                cmd += ' --strip-com'
            quality = get_setting(s, "jpegoptim/quality")
            if quality > 0:
                cmd += f' --max={quality}'
            if get_setting(s, "jpegoptim/progressive"):
                cmd += ' --all-progressive'
            threshold = get_setting(s, "jpegoptim/threshold")
            if threshold > 0:
                cmd += f' -T{threshold}'
            cmd += ' "%(file)s"'
            jpeg_commands.append(cmd)

        if get_setting(s, "guetzli/enabled"):
            quality = get_setting(s, "guetzli/quality")
            cmd = f'{guetzli_path} --verbose --quality {quality}'
            memlimit = get_setting(s, "guetzli/memlimit")
            if memlimit == 0:
                cmd += ' --nomemlimit'
            else:
                cmd += f' --memlimit {memlimit}'
            cmd += ' "%(file)s" "%(file)s.bak"'
            jpeg_commands.append(cmd)
            jpeg_commands.append(f'{move_cmd} "%(file)s".bak "%(file)s"')

        if get_setting(s, "mozjpeg/enabled"):
            cmd = f'{mozjpeg_path}'
            if get_setting(s, "mozjpeg/optimize"):
                cmd += ' -optimize'
            if get_setting(s, "mozjpeg/progressive"):
                cmd += ' -progressive'
            copy_mode = get_setting(s, "mozjpeg/copy")
            cmd += f' -copy {copy_mode}'
            cmd += ' "%(file)s" > "%(file)s".bak'
            jpeg_commands.append(cmd)
            jpeg_commands.append(f'{move_cmd} "%(file)s".bak "%(file)s"')

        if imagemagick_path and get_setting(s, "imagemagick/enabled"):
            im_cmd = f'{imagemagick_path} convert' if imagemagick_version == 7 else imagemagick_path
            quality = get_setting(s, "imagemagick/jpegQuality")
            strip_flag = ' -strip' if get_setting(s, "imagemagick/strip") else ''
            jpeg_commands.append(
                f'{im_cmd} "%(file)s"{strip_flag} -quality {quality} '
                f'"%(file)s".im_bak && {move_cmd} "%(file)s".im_bak "%(file)s"')

        if get_setting(s, "general/webpEnabled") and get_setting(s, "cwebp/enabled"):
            jpeg_commands.append(self._build_cwebp_command(s))

        # --- PNG pipeline ---
        if get_setting(s, "optipng/enabled"):
            level = get_setting(s, "optipng/level")
            cmd = f'{optipng_path} -force -o{level}'
            interlace = get_setting(s, "optipng/interlace")
            cmd += f' -i {interlace}'
            if get_setting(s, "optipng/strip"):
                cmd += ' -strip all'
            cmd += ' "%(file)s"'
            png_commands.append(cmd)

        if get_setting(s, "advpng/enabled"):
            level = get_setting(s, "advpng/level")
            cmd = f'{advpng_path} -z{level}'
            iterations = get_setting(s, "advpng/iterations")
            if iterations > 0:
                cmd += f' -i {iterations}'
            cmd += ' "%(file)s"'
            png_commands.append(cmd)

        if get_setting(s, "pngcrush/enabled"):
            cmd = f'{pngcrush_path}'
            if get_setting(s, "pngcrush/brute"):
                cmd += ' -brute'
            if get_setting(s, "pngcrush/reduce"):
                cmd += ' -reduce'
            for chunk in ['gAMA', 'alla', 'cHRM', 'iCCP', 'sRGB', 'time']:
                if get_setting(s, f"pngcrush/rem_{chunk}"):
                    cmd += f' -rem {chunk}'
            cmd += ' "%(file)s" "%(file)s.bak"'
            png_commands.append(cmd)
            png_commands.append(f'{move_cmd} "%(file)s".bak "%(file)s"')

        if imagemagick_path and get_setting(s, "imagemagick/enabled"):
            im_cmd = f'{imagemagick_path} convert' if imagemagick_version == 7 else imagemagick_path
            strip_flag = ' -strip' if get_setting(s, "imagemagick/strip") else ''
            png_commands.append(
                f'{im_cmd} "%(file)s"{strip_flag} '
                f'"%(file)s".im_bak && {move_cmd} "%(file)s".im_bak "%(file)s"')

        if get_setting(s, "general/webpEnabled") and get_setting(s, "cwebp/enabled"):
            png_commands.append(self._build_cwebp_command(s))

        # --- GIF pipeline ---
        if get_setting(s, "gifsicle/enabled"):
            level = get_setting(s, "gifsicle/optLevel")
            cmd = f'{gifsicle_path} -O{level}'
            if get_setting(s, "gifsicle/lossy"):
                lossiness = get_setting(s, "gifsicle/lossiness")
                cmd += f' --lossy={lossiness}'
            colors = get_setting(s, "gifsicle/colors")
            if colors > 0:
                cmd += f' --colors {colors}'
            if get_setting(s, "gifsicle/interlace"):
                cmd += ' --interlace'
            cmd += ' "%(file)s" -o "%(file)s".bak'
            gif_commands.append(cmd)
            gif_commands.append(f'{move_cmd} "%(file)s".bak "%(file)s"')

        if imagemagick_path and get_setting(s, "imagemagick/enabled"):
            im_cmd = f'{imagemagick_path} convert' if imagemagick_version == 7 else imagemagick_path
            gif_commands.append(
                f'{im_cmd} "%(file)s" -layers Optimize '
                f'"%(file)s".im_bak && {move_cmd} "%(file)s".im_bak "%(file)s"')

        if get_setting(s, "general/webpEnabled") and get_setting(s, "gif2webp/enabled"):
            gif_commands.append(self._build_gif2webp_command(s))

        return {"jpeg": jpeg_commands, "png": png_commands, "gif": gif_commands}

    def _build_cwebp_command(self, settings):
        """Build cwebp command string from settings."""
        from preferences import get_setting
        s = settings
        quality = get_setting(s, "cwebp/quality")
        cmd = f'{webp_path}'
        if get_setting(s, "cwebp/lossless"):
            cmd += ' -lossless'
        else:
            cmd += f' -q {quality}'
        method = get_setting(s, "cwebp/method")
        cmd += f' -m {method}'
        preset = get_setting(s, "cwebp/preset")
        if preset != "default":
            cmd += f' -preset {preset}'
        if get_setting(s, "cwebp/mt"):
            cmd += ' -mt'
        metadata = get_setting(s, "cwebp/metadata")
        if metadata != "none":
            cmd += f' -metadata {metadata}'
        cmd += ' "%(file)s" -o "%(webp_file)s"'
        return cmd

    def _build_gif2webp_command(self, settings):
        """Build gif2webp command string from settings."""
        from preferences import get_setting
        s = settings
        cmd = f'{gif2webp_path}'
        mode = get_setting(s, "gif2webp/mode")
        if mode == "lossy":
            cmd += ' -lossy'
        elif mode == "mixed":
            cmd += ' -mixed'
        quality = get_setting(s, "gif2webp/quality")
        cmd += f' -q {quality}'
        method = get_setting(s, "gif2webp/method")
        cmd += f' -m {method}'
        if get_setting(s, "gif2webp/minSize"):
            cmd += ' -min_size'
        if get_setting(s, "gif2webp/mt"):
            cmd += ' -mt'
        cmd += ' "%(file)s" -o "%(file)s.webp"'
        return cmd

    def compress(self):
        """Compress the image and return it to the thread.

        Uses CompressionContext for atomic operation with automatic
        rollback on failure and guaranteed cleanup of temp files.
        """
        if not self.valid:
            raise ValueError(f"Tried to compress invalid image: {self.fullpath}")
        self.reset()

        # Pre-compression repair step
        from preferences import get_setting
        if self.parent and self.parent.settings:
            s = self.parent.settings
            if get_setting(s, "repair/repairBeforeCompress") and get_setting(s, "repair/autoRepair"):
                if self.diagnosis is None and get_setting(s, "repair/autoValidate"):
                    self.validate()
                if self.diagnosis and not self.diagnosis.is_valid and self.diagnosis.can_repair:
                    logger.info("Auto-repairing %s before compression", self.fullpath)
                    self.do_repair()

        logger.debug("Compressing: %s", self.fullpath)

        directory, filename = path.split(self.fullpath)
        output_filename = path.join(directory, self.file_base)

        # Build compression commands dynamically from settings
        runString = self._build_run_commands()

        retcode = 0

        with CompressionContext(self) as ctx:
            backup_file = ctx.backup_path
            original_file = self.fullpath

            # Track the best compression result
            best_file = None
            best_size = float('inf')
            best_combo = None
            overall_retcode = 0

            # Determine subprocess output based on verbosity
            stdout_target = None if self.parent.verbose >= VERBOSITY_VERBOSE else subprocess.PIPE

            # Loop through each command sequentially
            for command in runString[self.filetype]:
                formatted_command = command % {"file": backup_file, "webp_file": output_filename}
                if self.parent.verbose >= VERBOSITY_VERBOSE:
                    print(f"  [cmd] {formatted_command}")
                try:
                    retcode = call(formatted_command, shell=True, stdout=stdout_target)
                    if retcode != 0:
                        logger.warning("Command failed with return code %d", retcode)
                        overall_retcode = retcode
                        break
                    else:
                        newfilesize = path.getsize(backup_file)
                        if newfilesize < best_size:
                            best_size = newfilesize
                            # Save sequential result to a separate file so combo loop doesn't overwrite it
                            best_file = path.join(str(ctx.temp_dir), f"sequential_best.{self.filetype}")
                            copy(backup_file, best_file)
                except OSError as e:
                    logger.error("Failed to execute command: %s", e)
                    overall_retcode = -1
                    break

            # Restore backup_file to original state before running combinations
            copy(original_file, backup_file)

            # Try combinations of compression commands (if enabled)
            from preferences import get_setting
            if get_setting(self.parent.settings, "general/combinationTesting"):
                for r in range(2, len(runString[self.filetype]) + 1):
                    for combo in combinations(runString[self.filetype], r):
                        combo_commands = " && ".join(combo) % {"file": backup_file, "webp_file": output_filename}
                        if self.parent.verbose >= VERBOSITY_VERBOSE:
                            print(f"  [combo] {combo_commands}")
                        try:
                            retcode = subprocess.call(combo_commands, shell=True, stdout=stdout_target)
                            if retcode == 0:
                                new_size = path.getsize(backup_file)
                                if new_size < best_size:
                                    best_size = new_size
                                    best_file = path.join(str(ctx.temp_dir), f"combo_{r}.{self.filetype}")
                                    copy(backup_file, best_file)
                                    best_combo = combo
                        except OSError as e:
                            logger.error("Command failed: %s", e)

                        # Restore backup for next combination test
                        copy(original_file, backup_file)

            # Apply the best result or rollback
            if best_file and path.exists(best_file):
                copy(best_file, self.fullpath)
                self.newfilesize = path.getsize(self.fullpath)

                if best_combo:
                    logger.info("Best compression combo: %s", best_combo)

                # Remove WebP if larger than best compressed
                if path.exists(output_filename) and path.getsize(output_filename) > self.newfilesize:
                    remove(output_filename)
            else:
                # No improvement — restore original from backup
                copy(ctx.backup_path, self.fullpath)
                self.newfilesize = path.getsize(self.fullpath)

            if overall_retcode == 0:
                self.newfilesize = path.getsize(self.fullpath)
                self.compressed = True

            # TinyPNG step — compare cloud compression against local best
            try:
                import tinypng
                if tinypng.is_available() and self.parent:
                    tinypng_enabled = self.parent.settings.value(
                        "tinypng/enabled", False, type=bool
                    )
                    if tinypng_enabled and self.filetype in tinypng.SUPPORTED_TYPES:
                        success, result_path, error = tinypng.compress_file(
                            self.fullpath, self.filetype
                        )
                        if success and result_path:
                            tinypng_size = path.getsize(result_path)
                            current_size = path.getsize(self.fullpath)
                            if tinypng_size < current_size:
                                copy(result_path, self.fullpath)
                                self.newfilesize = tinypng_size
                                logger.info(
                                    "TinyPNG improved %s: %d -> %d bytes",
                                    self.fullpath, current_size, tinypng_size
                                )
                            else:
                                logger.info(
                                    "TinyPNG result not smaller for %s",
                                    self.fullpath
                                )
                            # Clean up temp file
                            if path.exists(result_path):
                                remove(result_path)
                        elif error:
                            logger.warning("TinyPNG failed for %s: %s",
                                          self.fullpath, error)
            except ImportError:
                pass  # tinypng module not available

            # If result is larger than original, revert
            if self.newfilesize >= self.oldfilesize:
                copy(ctx.backup_path, self.fullpath)
                self.newfilesize = self.oldfilesize

        # Stop the animation (after context manager cleanup)
        delegate = self.parent.ui.processedfiles.itemDelegateForColumn(0)
        if isinstance(delegate, AnimatedIconDelegate):
            delegate.stopAnimation(self.row)

        # Track compression metadata for intelligent recompression
        self.compress_count += 1
        if self.compressed and self.oldfilesize > 0:
            self.last_ratio = round(100 - (float(self.newfilesize) / self.oldfilesize * 100), 1)
        else:
            self.last_ratio = 0.0
        self.optimization_hash = self._compute_settings_hash()

        self.retcode = retcode
        return self


class Worker(QThread):
    update_ui_signal = pyqtSignal()

    def __init__(self, max_workers=None, parent=None):
        QThread.__init__(self, parent)
        self.toDisplay = Queue()
        if max_workers is None or max_workers < 1:
            max_workers = cpu_count()
        self.threadpool = ThreadPool(max_workers=max_workers)

    def compress_file(self, images, showapp, verbose, imagelist):
        """Start the worker thread."""
        for image in images:
            #FIXME:http://code.google.com/p/pythonthreadpool/issues/detail?id=5
            time.sleep(0.05)
            self.threadpool.add_job(image.compress, None,
                                    return_callback=self.toDisplay.put)
        self.showapp = showapp
        self.verbose = verbose
        self.imagelist = imagelist
        self.start()

    def run(self):
        """Compress the given file, get data from it and call update_table."""
        tp = self.threadpool
        while self.showapp or not (tp._ThreadPool__active_worker_count == 0 and
                                   tp._ThreadPool__jobs.empty()):
            image = self.toDisplay.get()

            self.update_ui_signal.emit()

            if not self.showapp and self.verbose >= VERBOSITY_NORMAL:
                if image.retcode == 0:
                    ir = ImageRow(image, compressing_icon_path)
                    print("File: " + ir['fullpath'] + ", Old Size: "
                        + ir['oldfilesizestr'] + ", New Size: "
                        + ir['newfilesizestr'] + ", Ratio: " + ir['ratiostr'])
                else:
                    print("[error] {} could not be compressed".format(image.fullpath), file=sys.stderr)


class Systray(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.createActions()
        self.createTrayIcon()
        self.trayIcon.show()

    def createActions(self):
        self.quitAction = QAction(self.tr("&Quit"), self)
        self.quitAction.triggered.connect(QCoreApplication.quit)

        self.addFiles = QAction(self.tr("&Add and compress"), self)
        icon = QIcon()
        icon.addPixmap(QPixmap(self.parent.ui.get_image((list_add_path))),
            QIcon.Normal, QIcon.Off)
        self.addFiles.setIcon(icon)
        self.addFiles.triggered.connect(self.parent.file_dialog)

        self.recompress = QAction(self.tr("&Recompress"), self)
        icon2 = QIcon()
        icon2.addPixmap(QPixmap(self.parent.ui.get_image((view_refresh_path))),
            QIcon.Normal, QIcon.Off)
        self.recompress.setIcon(icon2)
        self.recompress.setDisabled(True)

        self.addFiles.triggered.connect(self.parent.recompress_files)

        self.hideMain = QAction(self.tr("&Hide window"), self)
        self.hideMain.triggered.connect(self.parent.hide_main_window)

        self.dropZoneAction = QAction(self.tr("&Drop Zone"), self)
        self.dropZoneAction.setCheckable(True)
        if hasattr(self.parent, 'drop_zone'):
            self.dropZoneAction.setChecked(self.parent.drop_zone.isVisible())
        self.dropZoneAction.triggered.connect(self.parent.toggle_drop_zone)

        self.rescueAction = QAction(self.tr("Resc&ue..."), self)
        self.rescueAction.triggered.connect(self.parent.open_rescue_dialog)

    def createTrayIcon(self):
        self.trayIconMenu = QMenu(self)
        self.trayIconMenu.addAction(self.addFiles)
        self.trayIconMenu.addAction(self.recompress)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.dropZoneAction)
        self.trayIconMenu.addAction(self.rescueAction)
        self.trayIconMenu.addAction(self.hideMain)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.quitAction)

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.trayIcon = QSystemTrayIcon(self)
            self.trayIcon.activated.connect(lambda reason: self.hideMain.activate(QAction.Trigger))
            self.trayIcon.setContextMenu(self.trayIconMenu)
            self.trayIcon.setToolTip("Trimage image compressor")
            self.trayIcon.setIcon(QIcon(self.parent.ui.get_image(trimage_icon_path)))


def main():
    """Main entry point for Trimage."""
    app = QApplication(sys.argv)
    myapp = StartQt()

    if myapp.showapp:
        myapp.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
