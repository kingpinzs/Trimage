#!/usr/bin/env python3
"""Image validation, diagnosis, and repair for Trimage.

Detects corruption types and attempts repair using bundled tools
and PIL/Pillow capabilities. Follows the tinypng.py pattern —
standalone module with clear functions and graceful fallbacks.
"""

import logging
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import IntEnum
from os import path
from shutil import copy, move
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image as PILImage
from PIL import ImageFile

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────

# Magic byte signatures for format detection and file carving
SIGNATURES = {
    "jpeg":    b'\xff\xd8\xff',
    "png":     b'\x89PNG\r\n\x1a\n',
    "gif":     b'GIF8',
    "bmp":     b'BM',
    "tiff_le": b'\x49\x49\x2a\x00',
    "tiff_be": b'\x4d\x4d\x00\x2a',
}

# RIFF-based formats need two-part check
WEBP_RIFF = b'RIFF'
WEBP_MARKER = b'WEBP'  # at offset 8

# End-of-image markers
JPEG_EOI = b'\xff\xd9'
JPEG_SOI = b'\xff\xd8'
PNG_IEND = b'IEND'
GIF_TRAILER = b'\x3b'

# File carving chunk size (64 MB) with overlap for cross-boundary signatures
CARVE_CHUNK_SIZE = 64 * 1024 * 1024
CARVE_OVERLAP = 64 * 1024


class Severity(IntEnum):
    """Corruption severity levels."""
    NONE = 0       # File is healthy
    METADATA = 1   # Metadata issue only (EXIF, ICC) — compressible as-is
    MINOR = 2      # Minor data issue, repairable with high confidence
    MODERATE = 3   # Significant damage, repairable with possible data loss
    SEVERE = 4     # Major corruption, partial recovery possible
    FATAL = 5      # Unrecoverable


@dataclass
class DiagnosisResult:
    """Result of diagnosing an image file."""
    filepath: str
    detected_format: Optional[str] = None   # actual format from magic bytes
    declared_format: Optional[str] = None    # format from file extension
    is_valid: bool = True
    severity: Severity = Severity.NONE
    issues: List[str] = field(default_factory=list)
    repair_actions: List[str] = field(default_factory=list)
    can_repair: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────
# Phase 1: Diagnosis Functions
# ──────────────────────────────────────────────────────────

def check_magic_bytes(filepath: str) -> Tuple[Optional[str], bool]:
    """Identify actual format from magic bytes.

    Returns:
        (detected_format, matches_extension): detected format string
        and whether it matches the file extension.
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(12)
    except (IOError, OSError) as e:
        logger.warning("Cannot read file header: %s — %s", filepath, e)
        return None, False

    if len(header) < 3:
        return None, False

    # Check each signature
    detected = None
    if header[:3] == SIGNATURES["jpeg"]:
        detected = "jpeg"
    elif header[:8] == SIGNATURES["png"]:
        detected = "png"
    elif header[:4] == SIGNATURES["gif"]:
        detected = "gif"
    elif header[:4] == WEBP_RIFF and len(header) >= 12 and header[8:12] == WEBP_MARKER:
        detected = "webp"
    elif header[:2] == SIGNATURES["bmp"]:
        detected = "bmp"
    elif header[:4] in (SIGNATURES["tiff_le"], SIGNATURES["tiff_be"]):
        detected = "tiff"

    if detected is None:
        return None, False

    # Check extension match
    ext = path.splitext(filepath)[1].lower().lstrip('.')
    if ext == "jpg":
        ext = "jpeg"
    matches = (ext == detected)

    return detected, matches


def verify_with_pil(filepath: str) -> Tuple[bool, List[str]]:
    """Use PIL verify() and load() to detect corruption.

    Returns:
        (is_valid, list_of_issues).
    """
    issues = []

    # First pass: verify() — lightweight structural check
    try:
        img = PILImage.open(filepath)
        img.verify()
    except Exception as e:
        issues.append(f"PIL verify failed: {e}")

    # Second pass: load() — full pixel decode (requires re-open after verify)
    try:
        img = PILImage.open(filepath)
        img.load()
    except Exception as e:
        issues.append(f"PIL load failed: {e}")

    return (len(issues) == 0, issues)


def check_jpeg_integrity(filepath: str) -> List[str]:
    """Check JPEG-specific structure: SOI, EOI, markers.

    Returns list of issues found.
    """
    issues = []
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except (IOError, OSError):
        issues.append("Cannot read file")
        return issues

    if len(data) < 3:
        issues.append("File too small to be a valid JPEG")
        return issues

    # Check SOI marker
    if data[:2] != JPEG_SOI:
        issues.append("Missing JPEG SOI marker (FF D8)")

    # Check EOI marker
    if data[-2:] != JPEG_EOI:
        issues.append("Missing JPEG EOI marker (FF D9) — file may be truncated")
        # Estimate truncation
        # Try to find where data actually ends
        last_ff_pos = data.rfind(b'\xff')
        if last_ff_pos > 0:
            pct = (last_ff_pos / len(data)) * 100
            issues.append(f"Data ends at ~{pct:.0f}% of file")

    # Check for corrupted markers (FF followed by 00 is escaped, others should be valid)
    marker_count = 0
    i = 2  # skip SOI
    while i < len(data) - 1:
        if data[i] == 0xff and data[i + 1] != 0x00:
            marker = data[i + 1]
            if marker == 0xd9:  # EOI
                break
            marker_count += 1
            # Skip marker segment
            if marker not in (0xd0, 0xd1, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0x01):
                if i + 3 < len(data):
                    seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
                    i += 2 + seg_len
                    continue
            i += 2
        else:
            i += 1

    if marker_count == 0 and len(data) > 100:
        issues.append("No valid JPEG markers found in file body")

    return issues


def check_png_integrity(filepath: str, optipng_path: str = None) -> List[str]:
    """Check PNG structure using optipng -simulate if available, else basic checks.

    Returns list of issues found.
    """
    issues = []

    # Basic header check
    try:
        with open(filepath, 'rb') as f:
            header = f.read(8)
            if header != SIGNATURES["png"]:
                issues.append("Invalid PNG header")
                return issues
            # Try to read IHDR chunk
            chunk_len_data = f.read(4)
            if len(chunk_len_data) < 4:
                issues.append("File truncated before first chunk")
                return issues
            chunk_type = f.read(4)
            if chunk_type != b'IHDR':
                issues.append(f"First chunk is {chunk_type!r}, expected IHDR")
    except (IOError, OSError):
        issues.append("Cannot read file")
        return issues

    # Check for IEND
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        if PNG_IEND.encode() if isinstance(PNG_IEND, str) else PNG_IEND not in data:
            # Search for the actual bytes
            if b'IEND' not in data:
                issues.append("Missing PNG IEND chunk — file may be truncated")
    except (IOError, OSError):
        pass

    # Use optipng for deeper analysis if available
    if optipng_path and path.isfile(optipng_path):
        try:
            result = subprocess.run(
                [optipng_path, '-simulate', '-fix', filepath],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if stderr:
                    issues.append(f"optipng reports: {stderr[:200]}")
        except (subprocess.TimeoutExpired, OSError):
            pass  # Tool unavailable, skip

    return issues


def check_webp_integrity(filepath: str, webpinfo_path: str = None) -> List[str]:
    """Check WebP structure using webpinfo -diag if available.

    Returns list of issues found.
    """
    issues = []

    if webpinfo_path and path.isfile(webpinfo_path):
        try:
            result = subprocess.run(
                [webpinfo_path, '-diag', filepath],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                stdout = result.stdout.strip()
                msg = stderr or stdout
                if msg:
                    issues.append(f"webpinfo reports: {msg[:200]}")
                else:
                    issues.append("webpinfo returned error (corrupt WebP)")
        except (subprocess.TimeoutExpired, OSError):
            pass
    else:
        # Basic RIFF check
        try:
            with open(filepath, 'rb') as f:
                header = f.read(12)
            if header[:4] != WEBP_RIFF or header[8:12] != WEBP_MARKER:
                issues.append("Invalid WebP RIFF header")
        except (IOError, OSError):
            issues.append("Cannot read file")

    return issues


def check_gif_integrity(filepath: str, gifsicle_path: str = None) -> List[str]:
    """Check GIF structure.

    Returns list of issues found.
    """
    issues = []

    try:
        with open(filepath, 'rb') as f:
            header = f.read(6)
            data = f.read()
    except (IOError, OSError):
        issues.append("Cannot read file")
        return issues

    if header[:4] != SIGNATURES["gif"]:
        issues.append("Invalid GIF header")
        return issues

    version = header[4:6]
    if version not in (b'7a', b'9a'):
        issues.append(f"Unknown GIF version: {version!r}")

    # Check for trailer
    full_data = header + data
    if full_data[-1:] != GIF_TRAILER:
        issues.append("Missing GIF trailer byte — file may be truncated")

    # Use gifsicle for deeper analysis if available
    if gifsicle_path and path.isfile(gifsicle_path):
        try:
            result = subprocess.run(
                [gifsicle_path, '--info', filepath],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if stderr:
                    issues.append(f"gifsicle reports: {stderr[:200]}")
        except (subprocess.TimeoutExpired, OSError):
            pass

    return issues


def check_icc_profile(filepath: str) -> Tuple[bool, Optional[str]]:
    """Check ICC profile validity using PIL.

    Returns:
        (is_valid, issue_description or None).
    """
    try:
        img = PILImage.open(filepath)
        icc = img.info.get('icc_profile')
        if icc is None:
            return True, None  # No ICC profile is fine
        # Basic validation: ICC profile should start with profile size (4 bytes)
        if len(icc) < 128:
            return False, "ICC profile too short (corrupt)"
        # Check profile size matches
        profile_size = struct.unpack('>I', icc[:4])[0]
        if profile_size != len(icc):
            return False, f"ICC profile size mismatch (header says {profile_size}, actual {len(icc)})"
        return True, None
    except Exception as e:
        return False, f"Cannot check ICC profile: {e}"


def check_exif_integrity(filepath: str) -> Tuple[bool, Optional[str]]:
    """Check EXIF data for corruption using PIL.

    Returns:
        (is_valid, issue_description or None).
    """
    try:
        img = PILImage.open(filepath)
        exif_data = img.getexif()
        if not exif_data:
            return True, None  # No EXIF is fine
        # Try to iterate all tags — corrupt tags will raise
        for tag_id in exif_data:
            try:
                _ = exif_data[tag_id]
            except Exception:
                return False, f"Corrupt EXIF tag ID: {tag_id}"
        return True, None
    except Exception as e:
        return False, f"Cannot read EXIF: {e}"


def diagnose(filepath: str, tool_paths: dict = None) -> DiagnosisResult:
    """Full diagnosis pipeline — main entry point for Phase 1.

    Args:
        filepath: Path to image file.
        tool_paths: Dict of tool name → path (optipng, pngcrush, webpinfo, gifsicle).

    Returns:
        DiagnosisResult with all findings.
    """
    if tool_paths is None:
        tool_paths = {}

    result = DiagnosisResult(filepath=filepath)

    # Step 1: Check magic bytes
    detected_fmt, ext_matches = check_magic_bytes(filepath)
    result.detected_format = detected_fmt

    ext = path.splitext(filepath)[1].lower().lstrip('.')
    if ext == "jpg":
        ext = "jpeg"
    result.declared_format = ext

    if detected_fmt is None:
        result.is_valid = False
        result.severity = Severity.FATAL
        result.issues.append("Cannot identify file format from magic bytes")
        result.can_repair = False
        return result

    if not ext_matches:
        result.issues.append(f"Extension mismatch: .{ext} but content is {detected_fmt}")
        result.repair_actions.append("Rename file to correct extension")
        result.details["extension_mismatch"] = True
        if result.severity < Severity.MINOR:
            result.severity = Severity.MINOR

    # Step 2: Format-specific checks
    fmt_issues = []
    if detected_fmt == "jpeg":
        fmt_issues = check_jpeg_integrity(filepath)
    elif detected_fmt == "png":
        fmt_issues = check_png_integrity(filepath, tool_paths.get("optipng"))
    elif detected_fmt == "gif":
        fmt_issues = check_gif_integrity(filepath, tool_paths.get("gifsicle"))
    elif detected_fmt == "webp":
        fmt_issues = check_webp_integrity(filepath, tool_paths.get("webpinfo"))

    if fmt_issues:
        result.issues.extend(fmt_issues)
        # Classify severity
        truncated = any("truncat" in i.lower() for i in fmt_issues)
        missing_header = any("missing" in i.lower() and ("soi" in i.lower() or "header" in i.lower()) for i in fmt_issues)

        if truncated:
            result.details["truncated"] = True
            result.repair_actions.append("Recover truncated data with PIL")
            if detected_fmt == "jpeg":
                result.repair_actions.append("Append JPEG EOI marker")
            if result.severity < Severity.MODERATE:
                result.severity = Severity.MODERATE

        if missing_header:
            result.details["header_damaged"] = True
            result.repair_actions.append("Reconstruct file header")
            if result.severity < Severity.SEVERE:
                result.severity = Severity.SEVERE

        if detected_fmt == "png":
            result.repair_actions.append("Repair with optipng -fix")
            result.repair_actions.append("Repair with pngcrush -fix")

        if not truncated and not missing_header:
            if result.severity < Severity.MINOR:
                result.severity = Severity.MINOR

    # Step 3: PIL verification
    pil_valid, pil_issues = verify_with_pil(filepath)
    if not pil_valid:
        result.issues.extend(pil_issues)
        if result.severity < Severity.MINOR:
            result.severity = Severity.MINOR
        result.repair_actions.append("Re-encode with PIL")

    # Step 4: Metadata checks
    icc_valid, icc_issue = check_icc_profile(filepath)
    if not icc_valid:
        result.issues.append(icc_issue)
        result.details["corrupt_icc"] = True
        result.repair_actions.append("Strip or replace ICC profile")
        if result.severity < Severity.METADATA:
            result.severity = Severity.METADATA

    exif_valid, exif_issue = check_exif_integrity(filepath)
    if not exif_valid:
        result.issues.append(exif_issue)
        result.details["corrupt_exif"] = True
        result.repair_actions.append("Strip corrupt EXIF data")
        if result.severity < Severity.METADATA:
            result.severity = Severity.METADATA

    # Final validity assessment
    result.is_valid = (result.severity == Severity.NONE)

    # Can we repair?
    result.can_repair = (result.severity < Severity.FATAL)

    # Always suggest ImageMagick re-encode as fallback
    if not result.is_valid and result.can_repair:
        result.repair_actions.append("Re-encode via ImageMagick (fallback)")

    return result


# ──────────────────────────────────────────────────────────
# Phase 2: Repair Functions
# ──────────────────────────────────────────────────────────

def repair_truncated_with_pil(filepath: str) -> Tuple[bool, Optional[str]]:
    """Recover truncated image using PIL LOAD_TRUNCATED_IMAGES.

    Opens the truncated file with tolerance enabled, loads available
    pixel data, and re-saves to produce a valid file.

    Returns:
        (success, error_message).
    """
    original_flag = ImageFile.LOAD_TRUNCATED_IMAGES
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        img = PILImage.open(filepath)
        img.load()  # Force decode of available data

        # Re-save to produce a clean file
        fmt = img.format or _pil_format_from_ext(filepath)
        if fmt == "JPEG":
            # Convert RGBA/LA to RGB for JPEG
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(filepath, format="JPEG", quality=95)
        elif fmt == "PNG":
            img.save(filepath, format="PNG")
        elif fmt == "GIF":
            img.save(filepath, format="GIF")
        else:
            img.save(filepath)

        logger.info("Repaired truncated image: %s", filepath)
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = original_flag


def repair_jpeg_eoi(filepath: str) -> Tuple[bool, Optional[str]]:
    """Append missing JPEG EOI marker (FF D9) if absent.

    Returns:
        (success, error_message).
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()

        if data[-2:] == JPEG_EOI:
            return True, None  # Already has EOI

        with open(filepath, 'ab') as f:
            f.write(JPEG_EOI)

        logger.info("Appended JPEG EOI marker to: %s", filepath)
        return True, None
    except Exception as e:
        return False, str(e)


def repair_jpeg_header(filepath: str) -> Tuple[bool, Optional[str]]:
    """Reconstruct missing/damaged JPEG SOI marker.

    Scans for first valid JPEG marker and prepends SOI if missing.

    Returns:
        (success, error_message).
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()

        if data[:2] == JPEG_SOI:
            return True, None  # SOI present

        # Scan for first valid JPEG marker (FF C0-FF FE range)
        for i in range(min(len(data) - 1, 65536)):  # Search first 64KB
            if data[i] == 0xff and 0xc0 <= data[i + 1] <= 0xfe:
                repaired = JPEG_SOI + data[i:]
                with open(filepath, 'wb') as f:
                    f.write(repaired)
                logger.info("Reconstructed JPEG SOI marker at offset %d: %s", i, filepath)
                return True, None

        return False, "No valid JPEG markers found in first 64KB"
    except Exception as e:
        return False, str(e)


def repair_png_with_optipng(filepath: str, optipng_path: str) -> Tuple[bool, Optional[str]]:
    """Run optipng -fix on a PNG file for error recovery.

    Returns:
        (success, error_message).
    """
    if not optipng_path or not path.isfile(optipng_path):
        return False, "optipng not available"
    try:
        result = subprocess.run(
            [optipng_path, '-fix', '-force', '-o0', filepath],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            logger.info("Repaired PNG with optipng -fix: %s", filepath)
            return True, None
        return False, result.stderr.strip()[:200]
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)


def repair_png_with_pngcrush(filepath: str, pngcrush_path: str) -> Tuple[bool, Optional[str]]:
    """Run pngcrush -fix to salvage a damaged PNG.

    Returns:
        (success, error_message).
    """
    if not pngcrush_path or not path.isfile(pngcrush_path):
        return False, "pngcrush not available"
    repaired_path = filepath + ".pngcrush_fix"
    try:
        result = subprocess.run(
            [pngcrush_path, '-fix', filepath, repaired_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and path.isfile(repaired_path):
            move(repaired_path, filepath)
            logger.info("Repaired PNG with pngcrush -fix: %s", filepath)
            return True, None
        # Cleanup on failure
        if path.isfile(repaired_path):
            os.remove(repaired_path)
        return False, result.stderr.strip()[:200]
    except (subprocess.TimeoutExpired, OSError) as e:
        if path.isfile(repaired_path):
            os.remove(repaired_path)
        return False, str(e)


def repair_with_imagemagick(filepath: str, im_path: str, im_version: int = 7) -> Tuple[bool, Optional[str]]:
    """Re-encode image through ImageMagick to fix structural issues.

    This is the universal fallback — works for any format ImageMagick supports.

    Returns:
        (success, error_message).
    """
    if not im_path or not path.isfile(im_path):
        return False, "ImageMagick not available"

    repaired_path = filepath + ".im_repair"
    try:
        if im_version >= 7:
            cmd = [im_path, 'convert', filepath, repaired_path]
        else:
            cmd = [im_path, filepath, repaired_path]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and path.isfile(repaired_path):
            # Verify the repaired file is valid
            try:
                img = PILImage.open(repaired_path)
                img.verify()
            except Exception:
                os.remove(repaired_path)
                return False, "ImageMagick output failed validation"

            move(repaired_path, filepath)
            logger.info("Repaired via ImageMagick re-encode: %s", filepath)
            return True, None

        if path.isfile(repaired_path):
            os.remove(repaired_path)
        return False, result.stderr.strip()[:200]
    except (subprocess.TimeoutExpired, OSError) as e:
        if path.isfile(repaired_path):
            os.remove(repaired_path)
        return False, str(e)


# ──────────────────────────────────────────────────────────
# Phase 3: Advanced Repair — Metadata
# ──────────────────────────────────────────────────────────

def strip_corrupt_metadata(filepath: str) -> Tuple[bool, Optional[str]]:
    """Strip ALL metadata using PIL: open → extract pixels → save clean.

    Removes EXIF, ICC profiles, comments — the nuclear option for
    metadata corruption.

    Returns:
        (success, error_message).
    """
    try:
        img = PILImage.open(filepath)
        data = list(img.getdata())
        clean_img = PILImage.new(img.mode, img.size)
        clean_img.putdata(data)

        fmt = img.format or _pil_format_from_ext(filepath)
        if fmt == "JPEG" and clean_img.mode in ("RGBA", "LA", "P"):
            clean_img = clean_img.convert("RGB")
        clean_img.save(filepath, format=fmt)
        logger.info("Stripped all metadata from: %s", filepath)
        return True, None
    except Exception as e:
        return False, str(e)


def strip_icc_profile(filepath: str) -> Tuple[bool, Optional[str]]:
    """Remove only the ICC profile using PIL.

    Returns:
        (success, error_message).
    """
    try:
        img = PILImage.open(filepath)
        if 'icc_profile' not in img.info:
            return True, None  # Nothing to strip

        # Re-save without ICC profile
        info = img.info.copy()
        info.pop('icc_profile', None)
        fmt = img.format or _pil_format_from_ext(filepath)
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(filepath, format=fmt, **{k: v for k, v in info.items()
                                          if k not in ('icc_profile',)})
        logger.info("Stripped ICC profile from: %s", filepath)
        return True, None
    except Exception as e:
        return False, str(e)


def repair_icc_profile(filepath: str) -> Tuple[bool, Optional[str]]:
    """Replace corrupt ICC profile with standard sRGB.

    Returns:
        (success, error_message).
    """
    try:
        from PIL import ImageCms
        img = PILImage.open(filepath)
        srgb_profile = ImageCms.createProfile("sRGB")
        srgb_icc = ImageCms.ImageCmsProfile(srgb_profile).tobytes()

        fmt = img.format or _pil_format_from_ext(filepath)
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(filepath, format=fmt, icc_profile=srgb_icc)
        logger.info("Replaced ICC profile with sRGB: %s", filepath)
        return True, None
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────────────────
# Phase 2: Main Repair Pipeline
# ──────────────────────────────────────────────────────────

def repair(filepath: str, diagnosis: DiagnosisResult, tool_paths: dict,
           settings: dict) -> Tuple[bool, List[str]]:
    """Main repair pipeline — chooses strategy based on diagnosis.

    Args:
        filepath: Path to the image file.
        diagnosis: DiagnosisResult from diagnose().
        tool_paths: Dict of tool name → path.
        settings: Dict of repair/* settings.

    Returns:
        (success, list_of_actions_taken).
    """
    actions = []

    if diagnosis.is_valid:
        return True, []

    # 1. Header reconstruction (JPEG only)
    if diagnosis.details.get("header_damaged") and settings.get("repair/headerReconstruction"):
        if diagnosis.detected_format == "jpeg":
            ok, err = repair_jpeg_header(filepath)
            if ok:
                actions.append("Reconstructed JPEG header")

    # 2. Truncation recovery
    if diagnosis.details.get("truncated") and settings.get("repair/truncationRecovery"):
        if diagnosis.detected_format == "jpeg":
            ok, err = repair_jpeg_eoi(filepath)
            if ok:
                actions.append("Appended missing JPEG EOI marker")
        # PIL truncation recovery for all formats
        ok, err = repair_truncated_with_pil(filepath)
        if ok:
            actions.append("Recovered truncated image data via PIL")

    # 3. Format-specific tool repair (PNG)
    if diagnosis.detected_format == "png":
        optipng = tool_paths.get("optipng")
        if optipng:
            ok, err = repair_png_with_optipng(filepath, optipng)
            if ok:
                actions.append("Repaired PNG with optipng -fix")

        pngcrush = tool_paths.get("pngcrush")
        if pngcrush and not actions:  # Only if optipng didn't fix it
            ok, err = repair_png_with_pngcrush(filepath, pngcrush)
            if ok:
                actions.append("Repaired PNG with pngcrush -fix")

    # 4. Metadata repair
    if settings.get("repair/stripCorruptMetadata"):
        if diagnosis.details.get("corrupt_icc"):
            icc_strategy = settings.get("repair/iccProfileStrategy", "strip")
            if icc_strategy == "replace_srgb":
                ok, err = repair_icc_profile(filepath)
                if ok:
                    actions.append("Replaced ICC profile with sRGB")
            else:  # "strip" (default)
                ok, err = strip_icc_profile(filepath)
                if ok:
                    actions.append("Stripped corrupt ICC profile")

        if diagnosis.details.get("corrupt_exif"):
            meta_strategy = settings.get("repair/metadataStrategy", "strip_corrupt")
            if meta_strategy == "strip_all":
                ok, err = strip_corrupt_metadata(filepath)
                if ok:
                    actions.append("Stripped all metadata")
            else:  # "strip_corrupt" — strip only EXIF via re-save
                ok, err = strip_corrupt_metadata(filepath)
                if ok:
                    actions.append("Stripped corrupt EXIF data")

    # 5. Universal fallback: ImageMagick re-encode
    if not actions:
        im_path = tool_paths.get("imagemagick")
        im_ver = tool_paths.get("imagemagick_version", 7)
        if im_path:
            ok, err = repair_with_imagemagick(filepath, im_path, im_ver)
            if ok:
                actions.append("Re-encoded via ImageMagick")

    return (len(actions) > 0, actions)


# ──────────────────────────────────────────────────────────
# Phase 4: File Carving / Raw Data Recovery
# ──────────────────────────────────────────────────────────

def scan_for_signatures(data: bytes, max_results: int = 100) -> List[Dict]:
    """Scan binary data for image file signatures.

    Returns list of dicts with keys: format, offset, estimated_size, confidence.
    """
    results = []
    sigs_to_check = [
        ("jpeg", SIGNATURES["jpeg"]),
        ("png", SIGNATURES["png"]),
        ("gif", SIGNATURES["gif"]),
    ]

    for fmt, sig in sigs_to_check:
        offset = 0
        while offset < len(data):
            idx = data.find(sig, offset)
            if idx == -1:
                break
            est_size = _estimate_image_size(data, idx, fmt)
            confidence = _estimate_confidence(data, idx, fmt, est_size)
            if confidence > 0.3:  # Skip very low confidence matches
                results.append({
                    "format": fmt,
                    "offset": idx,
                    "estimated_size": est_size,
                    "confidence": confidence,
                })
            offset = idx + 1
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    # Check for WebP (two-part signature)
    offset = 0
    while offset < len(data) - 12:
        idx = data.find(WEBP_RIFF, offset)
        if idx == -1 or idx + 12 > len(data):
            break
        if data[idx + 8:idx + 12] == WEBP_MARKER:
            # RIFF size is at offset 4
            if idx + 8 <= len(data):
                riff_size = struct.unpack('<I', data[idx + 4:idx + 8])[0] + 8
                results.append({
                    "format": "webp",
                    "offset": idx,
                    "estimated_size": min(riff_size, len(data) - idx),
                    "confidence": 0.9,
                })
        offset = idx + 1
        if len(results) >= max_results:
            break

    return sorted(results, key=lambda r: r["offset"])


def _estimate_image_size(data: bytes, offset: int, fmt: str) -> int:
    """Estimate the size of an image starting at offset."""
    remaining = len(data) - offset

    if fmt == "jpeg":
        # Scan for EOI marker (FF D9)
        eoi_pos = data.find(JPEG_EOI, offset + 2)
        if eoi_pos != -1:
            return eoi_pos - offset + 2
        return remaining  # Truncated

    elif fmt == "png":
        # Scan for IEND chunk
        iend_pos = data.find(b'IEND', offset + 8)
        if iend_pos != -1:
            # IEND chunk: 4 bytes length + 4 bytes type + 4 bytes CRC
            return iend_pos - offset + 12
        return remaining  # Truncated

    elif fmt == "gif":
        # Scan for trailer byte (0x3B)
        trailer_pos = data.find(GIF_TRAILER, offset + 6)
        if trailer_pos != -1:
            return trailer_pos - offset + 1
        return remaining

    return remaining


def _estimate_confidence(data: bytes, offset: int, fmt: str, est_size: int) -> float:
    """Estimate confidence that data at offset is a real image."""
    if est_size < 100:
        return 0.1  # Too small to be a real image

    if fmt == "jpeg":
        # Check for APP0 (JFIF) or APP1 (EXIF) marker after SOI
        if offset + 4 <= len(data):
            marker = data[offset + 2:offset + 4]
            if marker in (b'\xff\xe0', b'\xff\xe1', b'\xff\xee', b'\xff\xdb'):
                return 0.95
            if marker[0:1] == b'\xff':
                return 0.7
        return 0.4

    elif fmt == "png":
        # Check for IHDR after signature
        if offset + 16 <= len(data):
            chunk_type = data[offset + 12:offset + 16]
            if chunk_type == b'IHDR':
                return 0.95
        return 0.5

    elif fmt == "gif":
        # Check version string
        if offset + 6 <= len(data):
            version = data[offset + 4:offset + 6]
            if version in (b'7a', b'9a'):
                return 0.9
        return 0.4

    return 0.5


def extract_image(data: bytes, offset: int, fmt: str,
                  estimated_size: int, output_dir: str,
                  index: int = 0) -> Optional[str]:
    """Extract a single image from binary data at the given offset.

    Returns path to extracted file or None.
    """
    ext_map = {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp"}
    ext = ext_map.get(fmt, ".bin")
    output_path = path.join(output_dir, f"rescued_{index:04d}{ext}")

    end = min(offset + estimated_size, len(data))
    image_data = data[offset:end]

    try:
        with open(output_path, 'wb') as f:
            f.write(image_data)

        # Validate the extracted file
        try:
            img = PILImage.open(output_path)
            img.verify()
            logger.info("Extracted %s image (%d bytes) → %s", fmt, len(image_data), output_path)
            return output_path
        except Exception:
            # Try loading with truncation tolerance
            original_flag = ImageFile.LOAD_TRUNCATED_IMAGES
            try:
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                img = PILImage.open(output_path)
                img.load()
                logger.info("Extracted truncated %s image (%d bytes) → %s", fmt, len(image_data), output_path)
                return output_path
            except Exception:
                os.remove(output_path)
                return None
            finally:
                ImageFile.LOAD_TRUNCATED_IMAGES = original_flag

    except (IOError, OSError) as e:
        logger.warning("Failed to extract image at offset %d: %s", offset, e)
        if path.isfile(output_path):
            os.remove(output_path)
        return None


def carve_file(filepath: str, output_dir: str,
               formats: List[str] = None) -> List[str]:
    """Scan a file for embedded images and extract them.

    Reads in chunks for memory efficiency on large files.

    Args:
        filepath: Path to file to scan.
        output_dir: Directory to write extracted images.
        formats: List of format names to look for (None = all).

    Returns:
        List of extracted file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    extracted = []
    file_size = path.getsize(filepath)
    extract_idx = 0

    if file_size <= CARVE_CHUNK_SIZE:
        # Small file — read all at once
        with open(filepath, 'rb') as f:
            data = f.read()
        sigs = scan_for_signatures(data)
        for sig in sigs:
            if formats and sig["format"] not in formats:
                continue
            result = extract_image(data, sig["offset"], sig["format"],
                                   sig["estimated_size"], output_dir, extract_idx)
            if result:
                extracted.append(result)
                extract_idx += 1
    else:
        # Large file — chunked reading with overlap
        with open(filepath, 'rb') as f:
            chunk_start = 0
            while chunk_start < file_size:
                f.seek(chunk_start)
                chunk = f.read(CARVE_CHUNK_SIZE + CARVE_OVERLAP)

                sigs = scan_for_signatures(chunk)
                for sig in sigs:
                    if formats and sig["format"] not in formats:
                        continue
                    # Adjust offset to absolute file position
                    abs_offset = chunk_start + sig["offset"]
                    # Only process signatures in the main chunk area (not overlap)
                    if sig["offset"] < CARVE_CHUNK_SIZE:
                        result = extract_image(chunk, sig["offset"], sig["format"],
                                               sig["estimated_size"], output_dir, extract_idx)
                        if result:
                            extracted.append(result)
                            extract_idx += 1

                chunk_start += CARVE_CHUNK_SIZE

    logger.info("Carved %d images from %s", len(extracted), filepath)
    return extracted


def scan_directory(dirpath: str, output_dir: str,
                   recursive: bool = True,
                   formats: List[str] = None) -> Dict[str, List[str]]:
    """Scan all files in a directory for recoverable images.

    Returns:
        Dict of {source_file: [extracted_file_paths]}.
    """
    results = {}

    if recursive:
        for root, dirs, files in os.walk(dirpath):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                fpath = path.join(root, fname)
                try:
                    extracted = carve_file(fpath, output_dir, formats)
                    if extracted:
                        results[fpath] = extracted
                except Exception as e:
                    logger.warning("Error scanning %s: %s", fpath, e)
    else:
        for fname in os.listdir(dirpath):
            fpath = path.join(dirpath, fname)
            if path.isfile(fpath):
                try:
                    extracted = carve_file(fpath, output_dir, formats)
                    if extracted:
                        results[fpath] = extracted
                except Exception as e:
                    logger.warning("Error scanning %s: %s", fpath, e)

    return results


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _pil_format_from_ext(filepath: str) -> str:
    """Map file extension to PIL format name."""
    ext = path.splitext(filepath)[1].lower()
    return {
        '.jpg': 'JPEG', '.jpeg': 'JPEG',
        '.png': 'PNG',
        '.gif': 'GIF',
        '.webp': 'WEBP',
        '.bmp': 'BMP',
        '.tiff': 'TIFF', '.tif': 'TIFF',
    }.get(ext, 'PNG')
