"""Shared pytest setup.

Backend modules import each other as top-level modules (e.g. `import financial_engine`),
so put backend/ on sys.path. Tests only touch pure calculation modules: no server,
no network, no GROQ_API_KEY required.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
