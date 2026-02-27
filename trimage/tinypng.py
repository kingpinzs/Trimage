#!/usr/bin/env python3
"""TinyPNG API integration for Trimage.

This module is optional. If the tinify package is not installed,
all functions gracefully return failure indicators.
"""

import logging
from os import path

logger = logging.getLogger(__name__)

try:
    import tinify
    TINIFY_AVAILABLE = True
except ImportError:
    TINIFY_AVAILABLE = False
    logger.info("tinify package not installed. TinyPNG integration disabled.")


# Supported file types (TinyPNG does NOT support GIF)
SUPPORTED_TYPES = {"jpeg", "png", "webp"}


def is_available():
    """Check if the tinify library is installed."""
    return TINIFY_AVAILABLE


def set_api_key(key):
    """Set the TinyPNG API key."""
    if not TINIFY_AVAILABLE:
        return False
    tinify.key = key
    return True


def validate_key():
    """Validate the current API key.

    Returns:
        (valid, error_message): Tuple of (bool, str or None).
    """
    if not TINIFY_AVAILABLE:
        return False, "tinify package not installed"
    if not tinify.key:
        return False, "No API key set"
    try:
        tinify.validate()
        return True, None
    except tinify.AccountError as e:
        return False, f"Invalid API key: {e}"
    except tinify.ConnectionError as e:
        return False, f"Connection error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"


def get_compressions_this_month():
    """Return the number of compressions used this month.

    Returns:
        (count, error): Tuple of (int or None, str or None).
    """
    if not TINIFY_AVAILABLE or not tinify.key:
        return None, "Not configured"
    try:
        tinify.validate()
        return tinify.compression_count, None
    except Exception as e:
        return None, str(e)


def compress_file(filepath, filetype):
    """Compress a file via TinyPNG API.

    Args:
        filepath: Path to the file to compress.
        filetype: One of 'jpeg', 'png', 'webp'.

    Returns:
        (success, result_path, error): Tuple of (bool, str or None, str or None).
        On success, result_path is a temp file with the compressed data.
    """
    if not TINIFY_AVAILABLE:
        return False, None, "tinify not installed"
    if not tinify.key:
        return False, None, "No API key configured"
    if filetype not in SUPPORTED_TYPES:
        return False, None, f"Unsupported type: {filetype}"

    result_path = filepath + ".tinypng_tmp"
    try:
        source = tinify.from_file(filepath)
        source.to_file(result_path)
        return True, result_path, None
    except tinify.AccountError as e:
        return False, None, f"Account error (check API key or quota): {e}"
    except tinify.ClientError as e:
        return False, None, f"Client error: {e}"
    except tinify.ServerError as e:
        return False, None, f"TinyPNG server error: {e}"
    except tinify.ConnectionError as e:
        return False, None, f"Network error: {e}"
    except Exception as e:
        return False, None, f"Unexpected error: {e}"
    finally:
        # Clean up temp file on failure
        if not path.exists(result_path):
            pass  # No cleanup needed
