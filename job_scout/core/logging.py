# job_scout/core/logging.py
"""
Thin structured-logging helper.

Uses stdlib logging so output works in both Docker/terminal and Streamlit.
Call `get_logger(__name__)` in each module instead of using print().
"""

import logging
import os
import sys


_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=_LOG_LEVEL,
    format=_FMT,
    datefmt=_DATE_FMT,
    stream=sys.stdout,
    force=False,  # Don't override if already configured (e.g., by Streamlit)
)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Usage: logger = get_logger(__name__)"""
    return logging.getLogger(name)
