from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

RELEASE_DIR = Path(__file__).resolve().parent
os.chdir(RELEASE_DIR)
sys.path.insert(0, str(RELEASE_DIR))


def _write_startup_error() -> None:
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "IDOMA"
    try:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "startup.log").open("a", encoding="utf-8") as log:
            log.write("\n" + "=" * 72 + "\n")
            log.write(traceback.format_exc())
    except OSError:
        pass


if __name__ == "__main__":
    try:
        from idoma_v2.desktop import main
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        _write_startup_error()
        raise
