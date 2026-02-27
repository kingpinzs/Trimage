#!/usr/bin/env python3
"""Build a Debian .deb package for Trimage.

Steps:
1. Build the PyInstaller binary using trimage.spec
2. Prepare the debian package structure
3. Build the .deb with dpkg-deb
"""

import os
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _read_version():
    version_file = os.path.join(PROJECT_ROOT, "trimage", "_version.py")
    with open(version_file) as f:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
        if match:
            return match.group(1)
        raise RuntimeError("Unable to find version string in trimage/_version.py")


VERSION = _read_version()
PACKAGE_NAME = "trimage"
DEB_DIR = os.path.join(PROJECT_ROOT, "deb_build")


def check_dependencies():
    """Check that required build tools are available."""
    for tool in ["pyinstaller", "dpkg-deb"]:
        if shutil.which(tool) is None:
            print(f"[error] {tool} not found. Please install it first.", file=sys.stderr)
            sys.exit(1)
    print("[ok] Build dependencies found.")


def build_binary():
    """Build the PyInstaller onefile binary using trimage.spec."""
    spec_file = os.path.join(PROJECT_ROOT, "trimage.spec")
    if not os.path.isfile(spec_file):
        print(f"[error] {spec_file} not found.", file=sys.stderr)
        sys.exit(1)

    print("[build] Running PyInstaller...")
    subprocess.run(
        ["pyinstaller", "--clean", "--noconfirm", spec_file],
        cwd=PROJECT_ROOT,
        check=True,
    )

    binary = os.path.join(PROJECT_ROOT, "dist", "trimage")
    if not os.path.isfile(binary):
        print(f"[error] Expected binary not found at {binary}", file=sys.stderr)
        sys.exit(1)

    print(f"[ok] Binary built: {binary}")
    return binary


def prepare_deb_structure(binary_path):
    """Create the debian package directory structure."""
    # Clean previous build
    if os.path.exists(DEB_DIR):
        shutil.rmtree(DEB_DIR)

    pkg_root = os.path.join(DEB_DIR, PACKAGE_NAME)

    # Create directory structure
    dirs = [
        os.path.join(pkg_root, "DEBIAN"),
        os.path.join(pkg_root, "usr", "bin"),
        os.path.join(pkg_root, "usr", "share", "applications"),
        os.path.join(pkg_root, "usr", "share", "icons", "hicolor", "scalable", "apps"),
        os.path.join(pkg_root, "usr", "share", "man", "man1"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # Copy binary
    dest_bin = os.path.join(pkg_root, "usr", "bin", "trimage")
    shutil.copy2(binary_path, dest_bin)
    os.chmod(dest_bin, 0o755)

    # Copy desktop file
    desktop_src = os.path.join(PROJECT_ROOT, "desktop", "trimage.desktop")
    if os.path.isfile(desktop_src):
        shutil.copy2(desktop_src, os.path.join(pkg_root, "usr", "share", "applications"))

    # Copy icon
    icon_src = os.path.join(PROJECT_ROOT, "desktop", "trimage.svg")
    if os.path.isfile(icon_src):
        shutil.copy2(icon_src, os.path.join(
            pkg_root, "usr", "share", "icons", "hicolor", "scalable", "apps"))

    # Copy man page
    man_src = os.path.join(PROJECT_ROOT, "doc", "trimage.1")
    if os.path.isfile(man_src):
        shutil.copy2(man_src, os.path.join(pkg_root, "usr", "share", "man", "man1"))

    # Get installed size in KB
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(pkg_root):
        for f in filenames:
            total_size += os.path.getsize(os.path.join(dirpath, f))
    installed_size_kb = total_size // 1024

    # Write DEBIAN/control
    control_content = f"""Package: {PACKAGE_NAME}
Version: {VERSION}
Section: graphics
Priority: optional
Architecture: amd64
Installed-Size: {installed_size_kb}
Maintainer: Kilian Valkhof <kilian@kilianvalkhof.com>
Description: GUI and command-line interface to optimize image files
 Trimage is a cross-platform GUI and command-line interface to optimize
 image files for PNG, JPG, GIF, and WEBP formats. All compression tools
 are bundled — no external dependencies required.
Homepage: http://trimage.org
"""
    with open(os.path.join(pkg_root, "DEBIAN", "control"), "w") as f:
        f.write(control_content)

    print(f"[ok] Debian package structure prepared in {pkg_root}")
    return pkg_root


def build_deb(pkg_root):
    """Build the .deb package using dpkg-deb."""
    output_deb = os.path.join(DEB_DIR, f"{PACKAGE_NAME}_{VERSION}_amd64.deb")

    print("[build] Building .deb package...")
    subprocess.run(
        ["dpkg-deb", "--build", pkg_root, output_deb],
        check=True,
    )

    print(f"[ok] Deb package built: {output_deb}")
    return output_deb


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    check_dependencies()
    binary = build_binary()
    pkg_root = prepare_deb_structure(binary)
    deb_path = build_deb(pkg_root)
    print(f"\nDone! Install with: sudo dpkg -i {deb_path}")
