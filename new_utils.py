# -*- coding: utf-8 -*-
"""
new_utils.py - Minimal helper functions for the Quran Page Viewer component.
"""

import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # In development, use the directory of the file that calls this function.
        # This is more robust than assuming the CWD.
        # Note: This might need adjustment based on where the utils file is relative to the calling script.
        # A safer approach for general use might be to define a project root.
        # For this component, assuming it's in the project root is acceptable.
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
