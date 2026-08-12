import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "LOG_DIRECTORY",
    str(Path(tempfile.gettempdir()) / "kis-auto-trading-pytest-logs"),
)
