"""Let plain ``pytest test`` import the package from this source tree."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
