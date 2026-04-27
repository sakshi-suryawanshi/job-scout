"""pytest root conftest — ensures project root is on sys.path."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
