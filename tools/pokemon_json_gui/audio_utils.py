from __future__ import annotations

import re
from pathlib import Path
from typing import List

try:
    from . import project_paths
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore

CRY_RE = re.compile(r"cry(?:_reverse)?\s+(Cry_[A-Za-z0-9_]+)")


def load_available_cries() -> List[str]:
    text = project_paths.CRY_TABLE_PATH.read_text(encoding="utf-8")
    cries = sorted(set(match.group(1) for match in CRY_RE.finditer(text)))
    return cries
