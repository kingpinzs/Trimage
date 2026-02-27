#!/usr/bin/env python3
"""Comprehensive preferences dialog for Trimage."""

from multiprocessing import cpu_count
from os import path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QGridLayout,
    QCheckBox, QLineEdit, QPushButton, QLabel, QSlider, QSpinBox,
    QComboBox, QHBoxLayout, QDialogButtonBox, QTabWidget, QWidget,
    QMessageBox, QScrollArea, QSizePolicy
)

import tinypng

# ---------------------------------------------------------------------------
# Defaults registry — every configurable key with its default value.
# These match the current hardcoded behavior so existing users see no change.
# ---------------------------------------------------------------------------
DEFAULTS = {
    # General
    "general/alwaysOnTop": False,
    "general/webpEnabled": True,
    "general/combinationTesting": True,
    "general/workerThreads": cpu_count(),
    "general/maxRetries": 3,

    # jpegoptim
    "jpegoptim/enabled": True,
    "jpegoptim/quality": 0,
    "jpegoptim/stripMode": "all",
    "jpegoptim/progressive": False,
    "jpegoptim/threshold": 0,

    # Guetzli
    "guetzli/enabled": True,
    "guetzli/quality": 100,
    "guetzli/memlimit": 0,

    # MozJPEG
    "mozjpeg/enabled": True,
    "mozjpeg/optimize": True,
    "mozjpeg/progressive": False,
    "mozjpeg/copy": "none",

    # OptiPNG
    "optipng/enabled": True,
    "optipng/level": 7,
    "optipng/interlace": 0,
    "optipng/strip": True,

    # AdvPNG
    "advpng/enabled": True,
    "advpng/level": 4,
    "advpng/iterations": 0,

    # PNGCrush
    "pngcrush/enabled": True,
    "pngcrush/brute": False,
    "pngcrush/reduce": False,
    "pngcrush/rem_gAMA": True,
    "pngcrush/rem_alla": True,
    "pngcrush/rem_cHRM": True,
    "pngcrush/rem_iCCP": True,
    "pngcrush/rem_sRGB": True,
    "pngcrush/rem_time": True,

    # Gifsicle
    "gifsicle/enabled": True,
    "gifsicle/optLevel": 3,
    "gifsicle/lossy": False,
    "gifsicle/lossiness": 80,
    "gifsicle/colors": 0,
    "gifsicle/interlace": False,

    # cwebp
    "cwebp/enabled": True,
    "cwebp/quality": 90,
    "cwebp/lossless": False,
    "cwebp/method": 4,
    "cwebp/preset": "default",
    "cwebp/mt": False,
    "cwebp/metadata": "none",

    # gif2webp
    "gif2webp/enabled": True,
    "gif2webp/mode": "lossy",
    "gif2webp/quality": 75,
    "gif2webp/method": 4,
    "gif2webp/minSize": False,
    "gif2webp/mt": False,

    # ImageMagick
    "imagemagick/enabled": True,
    "imagemagick/jpegQuality": 85,
    "imagemagick/strip": True,

    # Repair & Validation
    "repair/autoValidate": True,
    "repair/autoRepair": False,
    "repair/repairBeforeCompress": True,
    "repair/stripCorruptMetadata": True,
    "repair/truncationRecovery": True,
    "repair/headerReconstruction": False,
    "repair/backupBeforeRepair": True,
    "repair/iccProfileStrategy": "strip",
    "repair/metadataStrategy": "strip_corrupt",

    # TinyPNG
    "tinypng/enabled": False,
    "tinypng/apiKey": "",
}


def get_setting(settings, key):
    """Read a setting with its default from the DEFAULTS registry."""
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return settings.value(key, default, type=bool)
    elif isinstance(default, int):
        return settings.value(key, default, type=int)
    elif isinstance(default, str):
        return settings.value(key, default, type=str)
    return settings.value(key, default)


class PreferencesDialog(QDialog):
    """Tabbed settings dialog for all compression tools."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._mappings = []  # (widget, settings_key) pairs
        self.setWindowTitle("Trimage Preferences")
        self.setMinimumSize(700, 500)
        self._setup_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def _register(self, widget, key):
        """Register a widget for automatic load/save."""
        self._mappings.append((widget, key))
        return widget

    def _make_slider(self, min_val, max_val, key, label_format=None):
        """Create a horizontal slider + value label, register it."""
        row = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        label = QLabel(str(DEFAULTS[key]))
        label.setMinimumWidth(40)

        if label_format:
            slider.valueChanged.connect(lambda v: label.setText(label_format(v)))
        else:
            slider.valueChanged.connect(lambda v: label.setText(str(v)))

        row.addWidget(slider)
        row.addWidget(label)
        self._register(slider, key)
        return row, slider

    def _make_enabled_group(self, title, key):
        """Create a group box with an Enabled checkbox that toggles contents."""
        group = QGroupBox(title)
        enabled = QCheckBox("Enabled")
        self._register(enabled, key)
        return group, enabled

    # ------------------------------------------------------------------
    # Main UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_general_tab(), "General")
        self.tabs.addTab(self._create_jpegoptim_tab(), "jpegoptim")
        self.tabs.addTab(self._create_guetzli_tab(), "Guetzli")
        self.tabs.addTab(self._create_mozjpeg_tab(), "MozJPEG")
        self.tabs.addTab(self._create_optipng_tab(), "OptiPNG")
        self.tabs.addTab(self._create_advpng_tab(), "AdvPNG")
        self.tabs.addTab(self._create_pngcrush_tab(), "PNGCrush")
        self.tabs.addTab(self._create_gifsicle_tab(), "Gifsicle")
        self.tabs.addTab(self._create_cwebp_tab(), "cwebp")
        self.tabs.addTab(self._create_gif2webp_tab(), "gif2webp")
        self.tabs.addTab(self._create_imagemagick_tab(), "ImageMagick")
        self.tabs.addTab(self._create_repair_tab(), "Repair")
        self.tabs.addTab(self._create_tinypng_tab(), "TinyPNG")
        self.tabs.addTab(self._create_about_tab(), "About")
        layout.addWidget(self.tabs)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        restore_btn = button_box.button(QDialogButtonBox.RestoreDefaults)
        restore_btn.clicked.connect(self._restore_defaults)
        layout.addWidget(button_box)

    # ------------------------------------------------------------------
    # Tab: General
    # ------------------------------------------------------------------

    def _create_general_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Keep window always on top"), "general/alwaysOnTop"))
        form.addRow(self._register(QCheckBox("Enable WebP conversion"), "general/webpEnabled"))
        form.addRow(self._register(QCheckBox("Enable combination testing (slower, more thorough)"), "general/combinationTesting"))

        threads_spin = QSpinBox()
        threads_spin.setRange(1, 32)
        self._register(threads_spin, "general/workerThreads")
        form.addRow("Worker threads:", threads_spin)

        retries_spin = QSpinBox()
        retries_spin.setRange(1, 10)
        self._register(retries_spin, "general/maxRetries")
        form.addRow("Max recompression retries:", retries_spin)

        note = QLabel("Combination testing tries all permutations of tools to find\n"
                       "the smallest file. It is thorough but significantly slower.\n\n"
                       "Max retries limits how many times a file can be recompressed\n"
                       "with the same settings before it is skipped.\n\n"
                       "Worker thread changes take effect on next app restart.")
        note.setStyleSheet("color: gray; font-style: italic;")
        form.addRow(note)
        return w

    # ------------------------------------------------------------------
    # Tab: jpegoptim
    # ------------------------------------------------------------------

    def _create_jpegoptim_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "jpegoptim/enabled"))

        row, _ = self._make_slider(0, 100, "jpegoptim/quality")
        form.addRow("Quality (0 = lossless):", row)

        strip_combo = QComboBox()
        strip_combo.addItems(["all", "exif", "icc", "com", "none"])
        self._register(strip_combo, "jpegoptim/stripMode")
        form.addRow("Strip metadata:", strip_combo)

        form.addRow(self._register(QCheckBox("Progressive mode"), "jpegoptim/progressive"))

        threshold_spin = QSpinBox()
        threshold_spin.setRange(0, 100)
        threshold_spin.setSuffix("%")
        self._register(threshold_spin, "jpegoptim/threshold")
        form.addRow("Threshold (0 = disabled):", threshold_spin)
        return w

    # ------------------------------------------------------------------
    # Tab: Guetzli
    # ------------------------------------------------------------------

    def _create_guetzli_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "guetzli/enabled"))

        note = QLabel("Guetzli is very slow but produces excellent JPEG quality.\n"
                       "Minimum quality is 84.")
        note.setStyleSheet("color: gray; font-style: italic;")
        form.addRow(note)

        row, _ = self._make_slider(84, 100, "guetzli/quality")
        form.addRow("Quality:", row)

        memlimit_spin = QSpinBox()
        memlimit_spin.setRange(0, 6000)
        memlimit_spin.setSuffix(" MB")
        memlimit_spin.setSpecialValueText("Unlimited")
        self._register(memlimit_spin, "guetzli/memlimit")
        form.addRow("Memory limit (0 = unlimited):", memlimit_spin)
        return w

    # ------------------------------------------------------------------
    # Tab: MozJPEG
    # ------------------------------------------------------------------

    def _create_mozjpeg_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "mozjpeg/enabled"))
        form.addRow(self._register(QCheckBox("Optimize coding tables"), "mozjpeg/optimize"))
        form.addRow(self._register(QCheckBox("Progressive mode"), "mozjpeg/progressive"))

        copy_combo = QComboBox()
        copy_combo.addItems(["none", "comments", "icc", "all"])
        self._register(copy_combo, "mozjpeg/copy")
        form.addRow("Copy markers:", copy_combo)
        return w

    # ------------------------------------------------------------------
    # Tab: OptiPNG
    # ------------------------------------------------------------------

    def _create_optipng_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "optipng/enabled"))

        row, _ = self._make_slider(0, 7, "optipng/level")
        form.addRow("Optimization level:", row)

        interlace_combo = QComboBox()
        interlace_combo.addItems(["0 (non-interlaced)", "1 (interlaced)"])
        self._register(interlace_combo, "optipng/interlace")
        form.addRow("Interlace type:", interlace_combo)

        form.addRow(self._register(QCheckBox("Strip metadata"), "optipng/strip"))
        return w

    # ------------------------------------------------------------------
    # Tab: AdvPNG
    # ------------------------------------------------------------------

    def _create_advpng_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "advpng/enabled"))

        advpng_labels = {0: "store", 1: "fast", 2: "normal", 3: "extra", 4: "insane (zopfli)"}
        row, _ = self._make_slider(0, 4, "advpng/level",
                                   label_format=lambda v: f"{v} ({advpng_labels.get(v, '')})")
        form.addRow("Compression level:", row)

        iter_spin = QSpinBox()
        iter_spin.setRange(0, 100)
        iter_spin.setSpecialValueText("Default")
        self._register(iter_spin, "advpng/iterations")
        form.addRow("Iterations (0 = default):", iter_spin)
        return w

    # ------------------------------------------------------------------
    # Tab: PNGCrush
    # ------------------------------------------------------------------

    def _create_pngcrush_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "pngcrush/enabled"))
        form.addRow(self._register(QCheckBox("Brute force mode (tries 176 methods, very slow)"), "pngcrush/brute"))
        form.addRow(self._register(QCheckBox("Reduce colors (lossless)"), "pngcrush/reduce"))

        # Chunks to remove
        chunks_group = QGroupBox("Chunks to remove")
        grid = QGridLayout()
        chunks = [
            ("gAMA", "pngcrush/rem_gAMA"), ("alla", "pngcrush/rem_alla"),
            ("cHRM", "pngcrush/rem_cHRM"), ("iCCP", "pngcrush/rem_iCCP"),
            ("sRGB", "pngcrush/rem_sRGB"), ("time", "pngcrush/rem_time"),
        ]
        for i, (label, key) in enumerate(chunks):
            cb = QCheckBox(label)
            self._register(cb, key)
            grid.addWidget(cb, i // 3, i % 3)
        chunks_group.setLayout(grid)
        form.addRow(chunks_group)
        return w

    # ------------------------------------------------------------------
    # Tab: Gifsicle
    # ------------------------------------------------------------------

    def _create_gifsicle_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "gifsicle/enabled"))

        row, _ = self._make_slider(1, 3, "gifsicle/optLevel")
        form.addRow("Optimization level:", row)

        lossy_cb = self._register(QCheckBox("Lossy mode"), "gifsicle/lossy")
        form.addRow(lossy_cb)

        lossiness_spin = QSpinBox()
        lossiness_spin.setRange(0, 200)
        self._register(lossiness_spin, "gifsicle/lossiness")
        lossy_cb.toggled.connect(lossiness_spin.setEnabled)
        form.addRow("Lossiness (0-200):", lossiness_spin)

        colors_spin = QSpinBox()
        colors_spin.setRange(0, 256)
        colors_spin.setSpecialValueText("No limit")
        self._register(colors_spin, "gifsicle/colors")
        form.addRow("Colors (0 = no reduction):", colors_spin)

        form.addRow(self._register(QCheckBox("Interlace"), "gifsicle/interlace"))
        return w

    # ------------------------------------------------------------------
    # Tab: cwebp
    # ------------------------------------------------------------------

    def _create_cwebp_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "cwebp/enabled"))

        row, _ = self._make_slider(0, 100, "cwebp/quality")
        form.addRow("Quality:", row)

        form.addRow(self._register(QCheckBox("Lossless mode"), "cwebp/lossless"))

        row2, _ = self._make_slider(0, 6, "cwebp/method")
        form.addRow("Compression method (0=fast, 6=best):", row2)

        preset_combo = QComboBox()
        preset_combo.addItems(["default", "photo", "picture", "drawing", "icon", "text"])
        self._register(preset_combo, "cwebp/preset")
        form.addRow("Preset:", preset_combo)

        form.addRow(self._register(QCheckBox("Multi-threading"), "cwebp/mt"))

        meta_combo = QComboBox()
        meta_combo.addItems(["none", "all", "icc", "xmp"])
        self._register(meta_combo, "cwebp/metadata")
        form.addRow("Metadata:", meta_combo)
        return w

    # ------------------------------------------------------------------
    # Tab: gif2webp
    # ------------------------------------------------------------------

    def _create_gif2webp_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        form.addRow(self._register(QCheckBox("Enabled"), "gif2webp/enabled"))

        mode_combo = QComboBox()
        mode_combo.addItems(["lossy", "lossless", "mixed"])
        self._register(mode_combo, "gif2webp/mode")
        form.addRow("Mode:", mode_combo)

        row, _ = self._make_slider(0, 100, "gif2webp/quality")
        form.addRow("Quality:", row)

        row2, _ = self._make_slider(0, 6, "gif2webp/method")
        form.addRow("Compression method (0=fast, 6=best):", row2)

        form.addRow(self._register(QCheckBox("Minimize size"), "gif2webp/minSize"))
        form.addRow(self._register(QCheckBox("Multi-threading"), "gif2webp/mt"))
        return w

    # ------------------------------------------------------------------
    # Tab: ImageMagick
    # ------------------------------------------------------------------

    def _create_imagemagick_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        # Import detection info from trimage module
        try:
            import trimage as _t
            im_path = getattr(_t, 'imagemagick_path', None)
            im_ver = getattr(_t, 'imagemagick_version', None)
        except (ImportError, AttributeError):
            im_path = None
            im_ver = None

        enabled_cb = self._register(QCheckBox("Enabled"), "imagemagick/enabled")
        form.addRow(enabled_cb)

        row, _ = self._make_slider(0, 100, "imagemagick/jpegQuality")
        form.addRow("JPEG quality:", row)

        form.addRow(self._register(QCheckBox("Strip metadata"), "imagemagick/strip"))

        # Detection info
        if im_path:
            info = QLabel(f"Detected: ImageMagick {im_ver} at {im_path}")
            info.setStyleSheet("color: green;")
        else:
            info = QLabel("Not detected (optional system tool)")
            info.setStyleSheet("color: orange; font-style: italic;")
            enabled_cb.setEnabled(False)
            enabled_cb.setChecked(False)
        form.addRow(info)
        return w

    # ------------------------------------------------------------------
    # Tab: Repair & Validation
    # ------------------------------------------------------------------

    def _create_repair_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        note = QLabel(
            "These settings control automatic image validation and repair.\n"
            "Repair uses bundled tools (optipng -fix, pngcrush -fix) and PIL\n"
            "to recover corrupted images before compression."
        )
        note.setWordWrap(True)
        form.addRow(note)

        # Validation
        form.addRow(self._register(
            QCheckBox("Validate images before compression"),
            "repair/autoValidate"))
        form.addRow(self._register(
            QCheckBox("Auto-repair detected issues"),
            "repair/autoRepair"))
        form.addRow(self._register(
            QCheckBox("Run repair before compression pipeline"),
            "repair/repairBeforeCompress"))
        form.addRow(self._register(
            QCheckBox("Backup original before repair"),
            "repair/backupBeforeRepair"))

        # Recovery options
        form.addRow(QLabel(""))  # spacer
        recovery_label = QLabel("Recovery Options")
        recovery_label.setStyleSheet("font-weight: bold;")
        form.addRow(recovery_label)

        form.addRow(self._register(
            QCheckBox("Recover truncated images (PIL)"),
            "repair/truncationRecovery"))
        form.addRow(self._register(
            QCheckBox("Reconstruct damaged JPEG headers"),
            "repair/headerReconstruction"))
        form.addRow(self._register(
            QCheckBox("Strip corrupt metadata"),
            "repair/stripCorruptMetadata"))

        # Strategy dropdowns
        form.addRow(QLabel(""))  # spacer
        strategy_label = QLabel("Repair Strategies")
        strategy_label.setStyleSheet("font-weight: bold;")
        form.addRow(strategy_label)

        icc_combo = QComboBox()
        icc_combo.addItems(["strip", "replace_srgb", "keep"])
        self._register(icc_combo, "repair/iccProfileStrategy")
        form.addRow("ICC profile handling:", icc_combo)

        meta_combo = QComboBox()
        meta_combo.addItems(["strip_corrupt", "strip_all", "keep"])
        self._register(meta_combo, "repair/metadataStrategy")
        form.addRow("Metadata handling:", meta_combo)

        return w

    # ------------------------------------------------------------------
    # Tab: TinyPNG
    # ------------------------------------------------------------------

    def _create_tinypng_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.tinypng_enabled = self._register(
            QCheckBox("Enable TinyPNG compression"), "tinypng/enabled"
        )
        form.addRow(self.tinypng_enabled)

        self.tinypng_key = QLineEdit()
        self.tinypng_key.setPlaceholderText("Enter your TinyPNG API key")
        self.tinypng_key.setEchoMode(QLineEdit.Password)
        self._register(self.tinypng_key, "tinypng/apiKey")
        form.addRow("API Key:", self.tinypng_key)

        show_key = QCheckBox("Show key")
        show_key.toggled.connect(
            lambda checked: self.tinypng_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        form.addRow("", show_key)

        # Validate button and status
        validate_row = QHBoxLayout()
        self.validate_btn = QPushButton("Validate Key")
        self.validate_btn.clicked.connect(self._validate_tinypng_key)
        validate_row.addWidget(self.validate_btn)

        self.tinypng_status = QLabel("")
        validate_row.addWidget(self.tinypng_status)
        validate_row.addStretch()
        form.addRow("", validate_row)

        self.compression_count_label = QLabel("Compressions this month: --")
        form.addRow(self.compression_count_label)

        if not tinypng.is_available():
            notice = QLabel("tinify package not installed. Run: pip install tinify")
            notice.setStyleSheet("color: orange; font-style: italic;")
            form.addRow(notice)
            self.tinypng_enabled.setEnabled(False)
            self.tinypng_key.setEnabled(False)
            self.validate_btn.setEnabled(False)

        return w

    # ------------------------------------------------------------------
    # Tab: About
    # ------------------------------------------------------------------

    def _create_about_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # App info
        title = QLabel("Trimage Image Compressor")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        try:
            import trimage as _t
            version = getattr(_t, 'VERSION', '?')
        except ImportError:
            version = '?'

        ver_label = QLabel(f"Version {version}")
        ver_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver_label)

        desc = QLabel("A cross-platform tool for losslessly optimizing\n"
                       "PNG, JPEG, GIF, and WebP images.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("margin: 10px;")
        layout.addWidget(desc)

        # Tool detection
        tools_group = QGroupBox("Detected Tools")
        tools_form = QFormLayout()

        tool_info = self._get_tool_info()
        for name, status in tool_info:
            status_label = QLabel(status)
            if "not found" in status.lower():
                status_label.setStyleSheet("color: orange;")
            else:
                status_label.setStyleSheet("color: green;")
            tools_form.addRow(f"{name}:", status_label)

        tools_group.setLayout(tools_form)
        layout.addWidget(tools_group)

        # Credits
        credits = QLabel(
            "Authors: Kilian Valkhof, Paul Chaplin, Jeremy King, and others\n"
            "URL: http://trimage.org\n"
            "License: MIT"
        )
        credits.setAlignment(Qt.AlignCenter)
        credits.setStyleSheet("margin-top: 10px; color: gray;")
        layout.addWidget(credits)

        layout.addStretch()
        return w

    def _get_tool_info(self):
        """Get detection status for all compression tools."""
        info = []
        try:
            import trimage as _t
            tool_vars = [
                ("jpegoptim", "jpegoptim_path"),
                ("Guetzli", "guetzli_path"),
                ("MozJPEG", "mozjpeg_path"),
                ("cwebp", "webp_path"),
                ("dwebp", "dwebp_path"),
                ("OptiPNG", "optipng_path"),
                ("AdvPNG", "advpng_path"),
                ("PNGCrush", "pngcrush_path"),
                ("Gifsicle", "gifsicle_path"),
                ("gif2webp", "gif2webp_path"),
            ]
            for name, var in tool_vars:
                p = getattr(_t, var, None)
                if p and path.isfile(p):
                    info.append((name, p))
                else:
                    info.append((name, "Not found"))

            im_path = getattr(_t, 'imagemagick_path', None)
            im_ver = getattr(_t, 'imagemagick_version', None)
            if im_path:
                info.append(("ImageMagick", f"v{im_ver} at {im_path}"))
            else:
                info.append(("ImageMagick", "Not found (optional)"))
        except ImportError:
            info.append(("(error)", "Could not import trimage module"))

        info.append(("tinify", "Installed" if tinypng.is_available() else "Not installed (optional)"))
        return info

    # ------------------------------------------------------------------
    # Load / Save / Restore
    # ------------------------------------------------------------------

    def _load_settings(self):
        """Load all settings into widgets."""
        for widget, key in self._mappings:
            value = get_setting(self.settings, key)
            self._set_widget_value(widget, value)

        # TinyPNG-specific refresh
        self._refresh_compression_count()

        # Sync lossy/lossiness enabled state
        for widget, key in self._mappings:
            if key == "gifsicle/lossy":
                for w2, k2 in self._mappings:
                    if k2 == "gifsicle/lossiness":
                        w2.setEnabled(widget.isChecked())

    def _load_from_defaults(self):
        """Load all widgets from DEFAULTS dict."""
        for widget, key in self._mappings:
            default = DEFAULTS.get(key)
            if default is not None:
                self._set_widget_value(widget, default)

    def _set_widget_value(self, widget, value):
        """Set a widget's value based on its type."""
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QSlider):
            widget.setValue(int(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QComboBox):
            # For interlace combo, value is int but items are strings like "0 (non-interlaced)"
            text = str(value)
            idx = widget.findText(text)
            if idx >= 0:
                widget.setCurrentIndex(idx)
            else:
                # Try matching just the prefix (for "0 (non-interlaced)" style items)
                for i in range(widget.count()):
                    if widget.itemText(i).startswith(text):
                        widget.setCurrentIndex(i)
                        break
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    def _get_widget_value(self, widget):
        """Get a widget's current value."""
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, QSlider):
            return widget.value()
        elif isinstance(widget, QSpinBox):
            return widget.value()
        elif isinstance(widget, QComboBox):
            text = widget.currentText()
            # Extract leading int for interlace-style combos ("0 (non-interlaced)" → 0)
            if text and text[0].isdigit() and " (" in text:
                return int(text.split(" ")[0])
            return text
        elif isinstance(widget, QLineEdit):
            return widget.text().strip()
        return None

    def accept(self):
        """Save all settings and close."""
        for widget, key in self._mappings:
            self.settings.setValue(key, self._get_widget_value(widget))
        super().accept()

    def _restore_defaults(self):
        """Reset all settings to defaults after confirmation."""
        reply = QMessageBox.question(
            self, "Restore Defaults",
            "Reset all settings to their default values?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._load_from_defaults()

    # ------------------------------------------------------------------
    # TinyPNG helpers (preserved from original)
    # ------------------------------------------------------------------

    def _refresh_compression_count(self):
        """Fetch and display the current month's compression count."""
        key = self.tinypng_key.text().strip()
        if key and tinypng.is_available():
            tinypng.set_api_key(key)
            count, error = tinypng.get_compressions_this_month()
            if count is not None:
                self.compression_count_label.setText(
                    f"Compressions this month: {count}/500"
                )
            else:
                self.compression_count_label.setText(
                    f"Compressions this month: (error: {error})"
                )
        else:
            self.compression_count_label.setText(
                "Compressions this month: --"
            )

    def _validate_tinypng_key(self):
        """Validate the TinyPNG API key."""
        key = self.tinypng_key.text().strip()
        if not key:
            self.tinypng_status.setText("Please enter a key")
            self.tinypng_status.setStyleSheet("color: orange;")
            return

        tinypng.set_api_key(key)
        valid, error = tinypng.validate_key()
        if valid:
            self.tinypng_status.setText("Valid!")
            self.tinypng_status.setStyleSheet("color: green;")
            self._refresh_compression_count()
        else:
            self.tinypng_status.setText(error or "Invalid")
            self.tinypng_status.setStyleSheet("color: red;")
