#!/usr/bin/env python3

import sys
from os import path

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

# Determine base path (same logic as trimage.py for PyInstaller support)
if getattr(sys, 'frozen', False):
    _base_path = path.dirname(sys.executable)
    if hasattr(sys, '_MEIPASS'):
        _base_path = sys._MEIPASS
else:
    _base_path = path.dirname(path.realpath(__file__))

trimage_icon_path = path.join(_base_path, "pixmaps", "trimage-icon.png")
list_add_path = path.join(_base_path, "pixmaps", "list-add.png")
view_refresh_path = path.join(_base_path, "pixmaps", "view-refresh.png")
clear_table_path = path.join(_base_path, "pixmaps", "clear_table.png")


class TrimageTableView(QTableView):

    drop_event_signal = pyqtSignal(list)

    """Init the table drop event."""
    def __init__(self, parent=None):
        super(TrimageTableView, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        # Install event filter on viewport to intercept drag/drop
        # before Qt's model-based handling can reject them
        self.viewport().installEventFilter(self)

    def setModel(self, model):
        """Override setModel to re-install event filter on viewport."""
        super().setModel(model)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Intercept drag/drop events on the viewport."""
        if obj is self.viewport():
            if event.type() == QEvent.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.DragMove:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    filelist = []
                    for url in event.mimeData().urls():
                        filelist.append(url.toLocalFile())
                    self.drop_event_signal.emit(filelist)
                    return True
        return super().eventFilter(obj, event)


class Ui_trimage():
    def get_image(self, image):
        """Get the correct path to an image used in the UI.

        If the path is already absolute (set by base_path), return as-is.
        Otherwise resolve relative to the package directory.
        """
        if path.isabs(image):
            return image
        return path.join(_base_path, image)

    def setupUi(self, trimage):
        """Setup the entire UI."""
        trimage.setObjectName("trimage")
        trimage.resize(600, 170)

        trimageIcon = QIcon(self.get_image(trimage_icon_path))
        trimage.setWindowIcon(trimageIcon)

        self.centralwidget = QWidget(trimage)
        self.centralwidget.setObjectName("centralwidget")

        self.gridLayout_2 = QGridLayout(self.centralwidget)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_2.setSpacing(0)
        self.gridLayout_2.setObjectName("gridLayout_2")

        self.widget = QWidget(self.centralwidget)
        self.widget.setEnabled(True)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(
            self.widget.sizePolicy().hasHeightForWidth())
        self.widget.setSizePolicy(sizePolicy)
        self.widget.setObjectName("widget")

        self.verticalLayout = QVBoxLayout(self.widget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")

        self.frame = QFrame(self.widget)
        self.frame.setObjectName("frame")

        self.verticalLayout_2 = QVBoxLayout(self.frame)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setContentsMargins(10, 10, 10, 10)
        self.horizontalLayout.setObjectName("horizontalLayout")

        self.addfiles = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.addfiles.setFont(font)
        self.addfiles.setCursor(Qt.PointingHandCursor)
        icon = QIcon()
        icon.addPixmap(QPixmap(self.get_image(list_add_path)), QIcon.Normal, QIcon.Off)
        self.addfiles.setIcon(icon)
        self.addfiles.setObjectName("addfiles")
        self.addfiles.setAcceptDrops(True)
        self.horizontalLayout.addWidget(self.addfiles)

        self.label = QLabel(self.frame)
        font = QFont()
        font.setPointSize(8)
        self.label.setFont(font)
        self.label.setFrameShadow(QFrame.Plain)
        self.label.setContentsMargins(1, 1, 1, 1)
        self.label.setIndent(10)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)

        spacerItem = QSpacerItem(498, 20, QSizePolicy.Expanding,
                                 QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.recompress = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.recompress.setFont(font)
        self.recompress.setCursor(Qt.PointingHandCursor)

        icon1 = QIcon()
        icon1.addPixmap(QPixmap(self.get_image(view_refresh_path)), QIcon.Normal, QIcon.Off)

        self.recompress.setIcon(icon1)
        self.recompress.setCheckable(False)
        self.recompress.setObjectName("recompress")
        self.horizontalLayout.addWidget(self.recompress)
        self.verticalLayout_2.addLayout(self.horizontalLayout)

        self.clearTable = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.clearTable.setFont(font)
        self.clearTable.setCursor(Qt.PointingHandCursor)
        icon = QIcon()
        icon.addPixmap(QPixmap(self.get_image(clear_table_path)), QIcon.Normal, QIcon.Off)
        self.clearTable.setIcon(icon)
        self.clearTable.setObjectName("clearTable")
        self.horizontalLayout.addWidget(self.clearTable)

        self.alwaysOnTop = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.alwaysOnTop.setFont(font)
        self.alwaysOnTop.setCursor(Qt.PointingHandCursor)
        self.alwaysOnTop.setCheckable(True)
        self.alwaysOnTop.setObjectName("alwaysOnTop")
        self.horizontalLayout.addWidget(self.alwaysOnTop)

        self.settingsBtn = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.settingsBtn.setFont(font)
        self.settingsBtn.setCursor(Qt.PointingHandCursor)
        self.settingsBtn.setObjectName("settingsBtn")
        self.horizontalLayout.addWidget(self.settingsBtn)

        self.rescueBtn = QPushButton(self.frame)
        font = QFont()
        font.setPointSize(9)
        self.rescueBtn.setFont(font)
        self.rescueBtn.setCursor(Qt.PointingHandCursor)
        self.rescueBtn.setObjectName("rescueBtn")
        self.horizontalLayout.addWidget(self.rescueBtn)

        self.processedfiles = TrimageTableView(self.frame)
        self.processedfiles.setEnabled(True)
        self.processedfiles.setFrameShape(QFrame.NoFrame)
        self.processedfiles.setFrameShadow(QFrame.Plain)
        self.processedfiles.setLineWidth(0)
        self.processedfiles.setMidLineWidth(0)
        self.processedfiles.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.processedfiles.setTabKeyNavigation(True)
        self.processedfiles.setAlternatingRowColors(True)
        self.processedfiles.setTextElideMode(Qt.ElideRight)
        self.processedfiles.setShowGrid(True)
        self.processedfiles.setGridStyle(Qt.NoPen)
        self.processedfiles.setSortingEnabled(False)
        self.processedfiles.setObjectName("processedfiles")
        self.processedfiles.resizeColumnsToContents()
        self.processedfiles.setSelectionMode(QAbstractItemView.NoSelection)
        self.verticalLayout_2.addWidget(self.processedfiles)
        self.verticalLayout.addWidget(self.frame)
        self.gridLayout_2.addWidget(self.widget, 0, 0, 1, 1)
        trimage.setCentralWidget(self.centralwidget)

        self.retranslateUi(trimage)
        QMetaObject.connectSlotsByName(trimage)

    def retranslateUi(self, trimage):
        """Fill in the texts for all UI elements."""
        trimage.setWindowTitle(QApplication.translate("trimage",
            "Trimage image compressor", None))
        self.addfiles.setToolTip(QApplication.translate("trimage",
            "Add file to the compression list", None))
        self.addfiles.setText(QApplication.translate("trimage",
            "&Add and compress", None))
        self.addfiles.setShortcut(QApplication.translate("trimage",
            "Alt+A", None))
        self.label.setText(QApplication.translate("trimage",
            "Drag and drop images onto the table", None))
        self.recompress.setToolTip(QApplication.translate("trimage",
            "Recompress all images", None))
        self.recompress.setText(QApplication.translate("trimage",
            "&Recompress", None))
        self.recompress.setShortcut(QApplication.translate("trimage",
            "Alt+R", None))
        self.processedfiles.setToolTip(QApplication.translate("trimage",
            "Drag files in here", None))
        self.processedfiles.setWhatsThis(QApplication.translate("trimage",
            "Drag files in here", None))
        self.clearTable.setToolTip(QApplication.translate("trimage",
            "Clear the table", None))
        self.clearTable.setText(QApplication.translate("trimage",
                    "&Clear Table", None))
        self.clearTable.setShortcut(QApplication.translate("trimage",
            "Alt+C", None))
        self.alwaysOnTop.setToolTip(QApplication.translate("trimage",
            "Keep window always on top", None))
        self.alwaysOnTop.setText(QApplication.translate("trimage",
            "&Pin", None))
        self.alwaysOnTop.setShortcut(QApplication.translate("trimage",
            "Alt+P", None))
        self.settingsBtn.setToolTip(QApplication.translate("trimage",
            "Preferences", None))
        self.settingsBtn.setText(QApplication.translate("trimage",
            "&Settings", None))
        self.settingsBtn.setShortcut(QApplication.translate("trimage",
            "Alt+S", None))
        self.rescueBtn.setToolTip(QApplication.translate("trimage",
            "Rescue images from files", None))
        self.rescueBtn.setText(QApplication.translate("trimage",
            "Resc&ue", None))
        self.rescueBtn.setShortcut(QApplication.translate("trimage",
            "Alt+U", None))


class DropZoneWidget(QWidget):
    """Floating, always-on-top drop zone for quick drag-and-drop compression."""

    files_dropped = pyqtSignal(list)

    SIZE = 64

    def __init__(self, parent=None):
        super().__init__(None)  # No parent — independent top-level widget
        self._parent = parent
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAcceptDrops(True)
        self.setToolTip("Drop images here to compress")

        # For dragging the widget around
        self._drag_pos = None

        # Load the Trimage icon
        self._icon = QPixmap(trimage_icon_path).scaled(
            40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Semi-transparent dark rounded rectangle
        painter.setBrush(QColor(50, 50, 50, 180))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        # Draw the icon centered
        x = (self.SIZE - self._icon.width()) // 2
        y = (self.SIZE - self._icon.height()) // 2
        painter.drawPixmap(x, y, self._icon)
        painter.end()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # Highlight on hover
            self.setStyleSheet("")  # reset
            self.update()

    def dragLeaveEvent(self, event):
        self.update()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if files:
            self.files_dropped.emit(files)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
