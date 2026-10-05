"""Where the framework keeps its files.

Everything lives under one home directory (default ``~/osloquant-home``), which can be moved with the
``OSLOQUANT_HOME`` environment variable or by calling :func:`init_env`. Tests point it at a temp directory.
"""

from __future__ import annotations

import os
from pathlib import Path

oq_env: dict[str, str] = {}


def init_env(home: str | os.PathLike | None = None) -> dict[str, str]:
    """Create the home directory layout and remember it in ``oq_env``."""
    from osloquant.contract import storage

    if home is None:
        home = os.environ.get("OSLOQUANT_HOME") or Path.home() / "osloquant-home"
    home = Path(home).expanduser().resolve()

    data_path = home / "data"
    log_path = home / "logs"
    for path in (data_path, log_path):
        path.mkdir(parents=True, exist_ok=True)

    # engines are bound to files under the old home
    storage.dispose_engines()

    oq_env.clear()
    oq_env.update({"home": str(home), "data_path": str(data_path), "log_path": str(log_path)})
    return oq_env


def data_path() -> Path:
    if not oq_env:
        init_env()
    return Path(oq_env["data_path"])
