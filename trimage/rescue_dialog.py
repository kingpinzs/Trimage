#!/usr/bin/env python3
"""Rescue dialog for Trimage — file carving and image recovery."""

import os
from os import path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QCheckBox, QLineEdit, QPushButton, QLabel,
    QProgressBar, QTableWidget, QTableWidgetItem, QFileDialog,
    QHeaderView, QAbstractItemView
)


class RescueWorker(QThread):
    """Background thread for file carving operations."""

    progress_signal = pyqtSignal(str)       # status message
    result_signal = pyqtSignal(dict)        # single extracted file info
    finished_signal = pyqtSignal(int)       # total extracted count

    def __init__(self, source_path, output_dir, formats, recursive):
        super().__init__()
        self.source_path = source_path
        self.output_dir = output_dir
        self.formats = formats
        self.recursive = recursive

    def run(self):
        from repair import carve_file, scan_directory
        total = 0

        if path.isfile(self.source_path):
            self.progress_signal.emit(f"Scanning {self.source_path}...")
            extracted = carve_file(self.source_path, self.output_dir, self.formats)
            for fpath in extracted:
                self.result_signal.emit({
                    "source": self.source_path,
                    "path": fpath,
                    "format": path.splitext(fpath)[1].lstrip('.'),
                    "size": path.getsize(fpath) if path.isfile(fpath) else 0,
                })
                total += 1

        elif path.isdir(self.source_path):
            self.progress_signal.emit(f"Scanning directory {self.source_path}...")
            results = scan_directory(self.source_path, self.output_dir,
                                     self.recursive, self.formats)
            for source, extracted_list in results.items():
                self.progress_signal.emit(f"Found {len(extracted_list)} images in {source}")
                for fpath in extracted_list:
                    self.result_signal.emit({
                        "source": source,
                        "path": fpath,
                        "format": path.splitext(fpath)[1].lstrip('.'),
                        "size": path.getsize(fpath) if path.isfile(fpath) else 0,
                    })
                    total += 1

        self.finished_signal.emit(total)


class RescueDialog(QDialog):
    """Dialog for file carving / rescue operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Rescue")
        self.setMinimumSize(700, 500)
        self._extracted_files = []
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QHBoxLayout(source_group)
        self.source_path = QLineEdit()
        self.source_path.setPlaceholderText("File or directory to scan for images...")
        browse_file_btn = QPushButton("File...")
        browse_file_btn.clicked.connect(self._browse_source_file)
        browse_dir_btn = QPushButton("Directory...")
        browse_dir_btn.clicked.connect(self._browse_source_dir)
        source_layout.addWidget(self.source_path)
        source_layout.addWidget(browse_file_btn)
        source_layout.addWidget(browse_dir_btn)
        layout.addWidget(source_group)

        # Options
        opts_group = QGroupBox("Options")
        opts_layout = QFormLayout(opts_group)
        self.recursive_check = QCheckBox("Scan subdirectories recursively")
        self.recursive_check.setChecked(True)
        opts_layout.addRow(self.recursive_check)

        formats_layout = QHBoxLayout()
        self.format_checks = {}
        for fmt in ["jpeg", "png", "gif", "webp"]:
            cb = QCheckBox(fmt.upper())
            cb.setChecked(True)
            self.format_checks[fmt] = cb
            formats_layout.addWidget(cb)
        opts_layout.addRow("Formats:", formats_layout)
        layout.addWidget(opts_group)

        # Output directory
        output_group = QGroupBox("Output Directory")
        output_layout = QHBoxLayout(output_group)
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Where to save extracted images...")
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self._browse_output)
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_browse)
        layout.addWidget(output_group)

        # Status and progress
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(
            ["Source File", "Extracted Path", "Format", "Size"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.results_table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._start_scan)
        self.compress_btn = QPushButton("Compress Selected")
        self.compress_btn.setToolTip("Add selected rescued images to the compression queue")
        self.compress_btn.clicked.connect(self._accept_selected)
        self.compress_btn.setEnabled(False)
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.compress_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_source_file(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Select file to scan")
        if fpath:
            self.source_path.setText(fpath)

    def _browse_source_dir(self):
        dpath = QFileDialog.getExistingDirectory(self, "Select directory to scan")
        if dpath:
            self.source_path.setText(dpath)

    def _browse_output(self):
        dpath = QFileDialog.getExistingDirectory(self, "Select output directory")
        if dpath:
            self.output_path.setText(dpath)

    def _start_scan(self):
        source = self.source_path.text().strip()
        output = self.output_path.text().strip()

        if not source:
            self.status_label.setText("Please select a source file or directory.")
            return
        if not output:
            # Default output directory
            output = path.join(path.dirname(source) if path.isfile(source) else source,
                               "rescued_images")
            self.output_path.setText(output)

        os.makedirs(output, exist_ok=True)

        # Gather selected formats
        formats = [fmt for fmt, cb in self.format_checks.items() if cb.isChecked()]
        if not formats:
            self.status_label.setText("Please select at least one format.")
            return

        # Clear previous results
        self.results_table.setRowCount(0)
        self._extracted_files.clear()
        self.compress_btn.setEnabled(False)

        # Start scanning
        self.scan_btn.setEnabled(False)
        self.progress.setVisible(True)

        self._worker = RescueWorker(source, output, formats,
                                     self.recursive_check.isChecked())
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.result_signal.connect(self._on_result)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, message):
        self.status_label.setText(message)

    def _on_result(self, info):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        self.results_table.setItem(row, 0, QTableWidgetItem(
            path.basename(info["source"])))
        self.results_table.setItem(row, 1, QTableWidgetItem(
            path.basename(info["path"])))
        self.results_table.setItem(row, 2, QTableWidgetItem(
            info["format"].upper()))
        size_str = f"{info['size']:,}" if info['size'] else "?"
        self.results_table.setItem(row, 3, QTableWidgetItem(size_str))
        self._extracted_files.append(info["path"])

    def _on_finished(self, total):
        self.scan_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText(f"Scan complete. Found {total} images.")
        if total > 0:
            self.compress_btn.setEnabled(True)
            self.results_table.selectAll()

    def _accept_selected(self):
        """Accept dialog with selected files for compression."""
        self.accept()

    def get_extracted_files(self):
        """Return list of extracted file paths (for the caller)."""
        # Return all files for now; could filter by selection later
        return list(self._extracted_files)
