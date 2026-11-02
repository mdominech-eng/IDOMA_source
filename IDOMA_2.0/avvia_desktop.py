from __future__ import annotations

import os
import sys
from pathlib import Path

RELEASE_DIR = Path(__file__).resolve().parent
os.chdir(RELEASE_DIR)
sys.path.insert(0, str(RELEASE_DIR))

from idoma_v2.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
