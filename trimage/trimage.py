#!/usr/bin/env python3

import time
import sys
from os import listdir, path, remove, access, W_OK, getcwd, rename
from shutil import copy
import subprocess

from optparse import OptionParser
from multiprocessing import cpu_count
from queue import Queue

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from ThreadPool import ThreadPool
from ui import Ui_trimage
from tools import *

from PIL import Image as PILImage
import mimetypes

from pprint import pprint

VERSION = "1.1.0"

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
        self.verbose = True
        self.imagelist = []

        # set application name and organization
        QCoreApplication.setOrganizationName("Kilian Valkhof")
        QCoreApplication.setOrganizationDomain("trimage.org")
        QCoreApplication.setApplicationName("Trimage")

        self.settings = QSettings()

        # if there is a previously saved geometry, restore it
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))

        # check if dependencies are installed
        if not check_dependencies():
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
        self.thread = Worker()

        # connect signals with slots
        self.ui.addfiles.clicked.connect(self.file_dialog)
        self.ui.recompress.clicked.connect(self.recompress_files)
        self.quit_shortcut.activated.connect(self.close)
        self.ui.processedfiles.drop_event_signal.connect(self.file_drop)
        self.thread.finished.connect(self.update_table)
        self.thread.update_ui_signal.connect(self.update_table)

        """Has to be a label and not an icon"""
        #self.compressing_icon = QIcon(QPixmap(self.ui.get_image("pixmaps/compressing.gif")))
   
        # create a QLabel for the compressing icon
        self.compressing_icon = QLabel(self)
        self.compressing_icon.setFixedSize(16, 16)
        # set the size and position of the label
        #self.compressing_icon.setGeometry(QRect(0, 0, 16, 16))
        # self.compressing_icon.setStyleSheet("border: 1px solid black;")
        # create a QMovie for the gif animation
        self.compressing_icon_gif = QMovie("pixmaps/compressing.gif")
        # set the gif animation on the label
        self.compressing_icon.setMovie(self.compressing_icon_gif)
        # hide the label initially
        self.compressing_icon.hide()

        # activate command line options
        self.commandline_options()

        # check if system tray is available and not in cli mode
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.cli:
            self.systemtray = Systray(self)

        # create and set the delegate for the column where you want to display the animated icon
        delegate = AnimatedIconDelegate(self.ui.processedfiles, self.imagelist)
        self.ui.processedfiles.setItemDelegateForColumn(0, delegate)  # replace 4 with the column number where you want to display the animated icon

    def commandline_options(self):
        """Set up the command line options."""
        self.cli = False
        parser = OptionParser(version="%prog " + VERSION,
            description="GUI front-end to compress png and jpg images via "
                "advpng, jpegoptim, optipng and pngcrush")

        parser.set_defaults(verbose=True)
        parser.add_option("-v", "--verbose", action="store_true",
            dest="verbose", help="Verbose mode (default)")
        parser.add_option("-q", "--quiet", action="store_false",
            dest="verbose", help="Quiet mode")

        parser.add_option("-f", "--file", action="store", type="string",
            dest="filename", help="compresses image and exit")
        parser.add_option("-d", "--directory", action="store", type="string",
            dest="directory", help="compresses images in directory and exit")

        options, args = parser.parse_args()

        # make sure we quit after processing finished if using cli
        if options.filename or options.directory:
            self.thread.finished.connect(quit)
            self.cli = True

        # send to correct function
        if options.filename:
            self.file_from_cmd(options.filename)
        if options.directory:
            self.dir_from_cmd(options.directory)

        self.verbose = options.verbose

    """
    Input functions
    """

    def dir_from_cmd(self, directory):
        """
        Read the files in the directory and send all files to compress_file.
        """
        self.showapp = False
        dirpath = path.abspath(directory)
        imagedir = listdir(directory)
        filelist = [path.join(dirpath, image) for image in imagedir]
        self.delegator(filelist)

    def file_from_cmd(self, image):
        """Get the file and send it to compress_file"""
        self.showapp = False
        filelist = [path.abspath(image)]
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
        directory = self.settings.value("directory", QVariant(""))
        fd.setDirectory(directory)

        images, _ = fd.getOpenFileNames(self,
            "Select one or more image files to compress",
            directory,
            # this is a fix for file dialog differentiating between cases
            "Image files (*.png *.jpg *.jpeg *.PNG *.JPG *.JPEG *.gif *.GIF)")

        self.settings.setValue("fdstate", QVariant(fd.saveState()))
        if images:
            self.settings.setValue("directory", QVariant(path.dirname(images[0])))
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
                    image.reset()
                    image.recompression = True
                    delegatorlist.append(image)
            except StopIteration:
                if not path.isdir(fullpath):
                    self.add_image(fullpath, delegatorlist, "pixmaps/compressing.gif")
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
                self.add_image(nfile, delegatorlist, "pixmaps/compressing.gif")

    def add_image(self, fullpath, delegatorlist, compressing_icon_path):
        """
        Adds an image file to the delegator list and update the tray and the title of the window.
        """
        image = Image(fullpath, self)
        image.row = len(self.imagelist)
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
            print("[error] {} not a supported image file and/or not writable".format(image.fullpath), file=sys.stderr)

    """
    UI Functions
    """

    def update_table(self):
        """Update the table view with the latest file data."""
        tview = self.ui.processedfiles
        # set table model
        tmodel = TriTableModel(self, self.imagelist,
            ["Filename", "Old Size", "New Size", "Compressed"])
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
        self.tview.removeRow(row)

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
      self.settings.setValue("geometry", QVariant(self.saveGeometry()))
      event.accept()


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

    def rowCount(self, parent=QModelIndex()):
        """Count the number of rows."""
        return len(self.imagelist)

    def columnCount(self, parent):
        """Count the number of columns."""
        return len(self.header)

    def data(self, index, role):
        """Fill the table with data."""
        if not index.isValid():
            return QVariant()
        elif role == Qt.DisplayRole:
            data = self.imagelist[index.row()][index.column()]
            return QVariant(data)
        elif index.column() == 0 and role == Qt.DecorationRole:
            # Return the data needed by the delegate to display the icon
            # For example, if the delegate needs the QMovie of the GIF, you can return it like this:
            gif_movie = self.imagelist[index.row()].compressing_icon_gif
            return QVariant(gif_movie)
        else:
            return QVariant()

    def headerData(self, col, orientation, role):
        """Fill the table headers."""
        if orientation == Qt.Horizontal and (role == Qt.DisplayRole or
        role == Qt.DecorationRole):
            return QVariant(self.header[col])
        return QVariant()


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
                if i.compressed else "",
            'icon': lambda i: self.compressing_icon_gif if not i.compressed else i.icon,
            'fullpath': lambda i: i.fullpath, #only used by cli
        }
        names = ['filename_w_ext', 'oldfilesizestr', 'newfilesizestr',
                      'ratiostr', 'icon']
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
        print(index)
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

    def statusStr(self):
        """Set the status message."""
        if self.image.failed:
            return "ERROR: {0}"
        if self.image.compressing:
            message = "Compressing {0}..."
            return message
        if not self.image.compressed and self.image.recompression:
            return "Queued for recompression {0}..."
        if not self.image.compressed:
            return "Queued {0}..."
        return "{0}"

    def __getitem__(self, key):
        return self.d[key](self.image)


class Image:
    def __init__(self, fullpath, parent=None):
        """Gather image information."""
        self.valid = False
        self.reset()
        self.fullpath = fullpath
        self.filename_w_ext = path.basename(self.fullpath)
        self.filename, self.filetype = path.splitext(self.filename_w_ext)
        self.file_base = self.filename+'.webp'
        self.parent = parent
        self.row = None  # Add a row attribute
        if path.isfile(self.fullpath) and access(self.fullpath, W_OK):
            self.filetype = self.filetype[1:].lower()
            # Get the actual file type based on the file contents
            actual_type = self.get_file_type(self.fullpath)
            print(actual_type)
            if actual_type is not None:
                # If the actual extension doesn't match the current file type, update it
                if actual_type != self.filetype:
                    print(f'Updating file type from {self.filetype} to {actual_type}')
                        # Change the file extension
                    new_name = self.change_file_extension(self.fullpath, actual_type)
                    if new_name is None:
                        self.failed = True
                        return
                    # Update the file path to the new name
                    self.fullpath = new_name
                    self.filetype = actual_type
                    print(f'New file name: {new_name}')
                    print(actual_type)
            if self.filetype == "jpg":
                self.filetype = "jpeg"
            if self.filetype == "webp":
                # Convert the WebP image to JPEG
                retcode = subprocess.call(f'./tools/webp/dwebp {self.fullpath} -o {self.fullpath}.png', shell=True)
                if retcode != 0:
                    print(f'Failed to convert {self.fullpath} from WebP to JPEG')
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
                raise Exception("Unsupported image format")
            oldfile = QFileInfo(self.fullpath)
            self.oldfilesize = oldfile.size()
            self.icon = QIcon(self.fullpath)
            self.valid = True

    def reset(self):
        self.failed = False
        self.compressed = False
        self.compressing = False
        self.recompression = False

    def get_file_type(self, filepath):
        try:
            output = subprocess.check_output(['file', '--mime', '-b', filepath])
            output = output.decode('utf-8').split(';')[0].strip()
            _, mime_type = output.split('/', 1)  # Extract the part after the slash
            return mime_type
        except subprocess.CalledProcessError as e:
            print(f'Failed to determine file type of {filepath}: {e}')
            return None
        
    def change_file_extension(self, filename, new_extension):
        base_name, _ = path.splitext(filename)
        new_name = base_name + '.' + new_extension
        try:
            rename(filename, new_name)
        except OSError as e:
            print(f'Failed to change file extension of {filename} to {new_extension}: {e}')
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

    def compress(self):
        """Compress the image and return it to the thread."""
        if not self.valid:
            raise Exception("Tried to compress invalid image (unsupported format or not \
            file)")
        self.reset()
        self.compressing = True
        print(f'{self.fullpath}')

        # create a backup file with "original" in the filename
        backupfilename = self.filename + "_original." + self.filetype
        backupfullpath = path.join(path.dirname(self.fullpath), backupfilename)
        copy(self.fullpath, backupfullpath)

        directory, filename = path.split(self.fullpath)
        output_filename = path.join(directory, self.file_base)
        
        runString = {
            "jpeg": "./tools/jpegoptim/jpegoptim -f --strip-all '%(file)s' && ./tools/guetzli/guetzli --verbose  --quality 100 --nomemlimit '%(file)s' '%(file)s.bak' && mv '%(file)s'.bak '%(file)s' && ./tools/mozjpeg/jpegtran-static -optimize '%(file)s' > '%(file)s'.bak && mv '%(file)s'.bak '%(file)s' && ./tools/webp/cwebp -q 90 '%(file)s' -o '%(webp_file)s'",
            "png": "optipng -force -o7 '%(file)s' && advpng -z4 '%(file)s' && pngcrush -rem gAMA -rem alla -rem cHRM -rem iCCP -rem sRGB -rem time '%(file)s' '%(file)s.bak' && mv '%(file)s.bak' '%(file)s' && cwebp -q 90 '%(file)s' -o '%(webp_file)s'",
            "gif": "gifsicle -O3 '%(file)s' -o '%(file)s'.bak && mv '%(file)s'.bak '%(file)s'"
        }
        # create a backup file
        backupfullpath = '/tmp/' + self.filename_w_ext
        copy(self.fullpath, backupfullpath)
        try:
            retcode = call(runString[self.filetype] % {"file": self.fullpath, "webp_file": output_filename},
                shell=True, stdout=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(e)
            retcode = -1
        finally:  # ensure that the compressing attribute is updated regardless of whether an exception occurs
            self.compressing = False
        if retcode == 0:
            self.newfilesize = QFile(self.fullpath).size()
            self.webp_filesize = path.getsize(output_filename)
            self.compressed = True

            # # If the compressed file is smaller than the new file, replace the new file with the compressed file
            # if self.webp_filesize < self.newfilesize:
            #     remove(self.fullpath)
            #     self.fullpath = output_filename
            #     self.newfilesize = self.webp_filesize

            # If the new file is larger than the original file, replace the new file with the original file
            if self.newfilesize >= self.oldfilesize:
                remove(self.fullpath)
                copy(backupfullpath, self.fullpath)
                self.newfilesize = self.oldfilesize

            # If the new file is smaller than the original file, remove the original file
            else:
                remove(backupfullpath)

            # Stop the animation and remove the QMovie object
            delegate = self.parent.ui.processedfiles.itemDelegateForColumn(0)
            if isinstance(delegate, AnimatedIconDelegate):
                delegate.stopAnimation(self.row)

            # If the WebP file is larger than the new file, remove the WebP file
            if self.webp_filesize > self.newfilesize:
                remove(output_filename)
        else:
            self.failed = True
        self.retcode = retcode
        return self


class Worker(QThread):
    update_ui_signal = pyqtSignal()

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.toDisplay = Queue()
        self.threadpool = ThreadPool(max_workers=cpu_count())

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

            if not self.showapp and self.verbose: # we work via the commandline
                if image.retcode == 0:
                    ir = ImageRow(image)
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
        self.quitAction.triggered.connect(self.parent.close)

        self.addFiles = QAction(self.tr("&Add and compress"), self)
        icon = QIcon()
        icon.addPixmap(QPixmap(self.parent.ui.get_image(("pixmaps/list-add.png"))),
            QIcon.Normal, QIcon.Off)
        self.addFiles.setIcon(icon)
        self.addFiles.triggered.connect(self.parent.file_dialog)

        self.recompress = QAction(self.tr("&Recompress"), self)
        icon2 = QIcon()
        icon2.addPixmap(QPixmap(self.parent.ui.get_image(("pixmaps/view-refresh.png"))),
            QIcon.Normal, QIcon.Off)
        self.recompress.setIcon(icon2)
        self.recompress.setDisabled(True)

        self.addFiles.triggered.connect(self.parent.recompress_files)

        self.hideMain = QAction(self.tr("&Hide window"), self)
        self.hideMain.triggered.connect(self.parent.hide_main_window)

    def createTrayIcon(self):
        self.trayIconMenu = QMenu(self)
        self.trayIconMenu.addAction(self.addFiles)
        self.trayIconMenu.addAction(self.recompress)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.hideMain)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.quitAction)

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.trayIcon = QSystemTrayIcon(self)
            self.trayIcon.setContextMenu(self.trayIconMenu)
            self.trayIcon.setToolTip("Trimage image compressor")
            self.trayIcon.setIcon(QIcon(self.parent.ui.get_image("pixmaps/trimage-icon.png")))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    myapp = StartQt()

    if myapp.showapp:
        myapp.show()
    sys.exit(app.exec_())
