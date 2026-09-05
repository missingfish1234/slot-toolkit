from __future__ import annotations

import os
import sys
from pathlib import Path


def restart_in_project_venv() -> None:
    """Use the bundled development environment even when launched with `python run.py`."""
    if getattr(sys, "frozen", False):
        return

    manager_dir = Path(__file__).resolve().parent
    relative_python = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    venv_python = manager_dir / ".venv" / relative_python
    if not venv_python.is_file():
        return

    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    os.execv(
        str(venv_python),
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )


restart_in_project_venv()

if __name__ == "__main__":
    try:
        from toolkit_manager.app import main
        main()
    except Exception:
        if "--smoke-test" in sys.argv:
            import traceback
            diagnostic = os.environ.get("TOOLKIT_SMOKE_REPORT")
            if diagnostic:
                Path(diagnostic).write_text(traceback.format_exc(), encoding="utf-8")
            sys.exit(1)
        raise
