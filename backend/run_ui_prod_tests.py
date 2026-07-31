import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["DJANGO_SETTINGS_MODULE"] = "backend.test_settings_sqlite"
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

import pytest

# --create-db forces fresh sqlite schema from models (no historical MySQL SQL migrations)
rc = pytest.main([
    "tests/test_ui_test_production.py",
    "-q",
    "--tb=short",
    "-o", "addopts=",
    "--nomigrations",
    "--create-db",
    "-p", "no:cacheprovider",
])
sys.exit(rc)
