"""
Code Optimization Package

This package provides modular code optimization functionality for Python and SQL code.
"""

from .core import generate_optimized_code
from .language_detection import detect_language

__all__ = [
    "generate_optimized_code",
    "detect_language", 
]
