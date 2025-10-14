from __future__ import annotations

import re
from pathlib import Path
from typing import List

from . import project_paths

CRY_RE = re.compile(r"cry(?:_reverse)?\s+(Cry_[A-Za-z0-9_]+)")


def load_available_cries() -> List[str]:
    text = project_paths.CRY_TABLE_PATH.read_text(encoding="utf-8")
    cries = sorted(set(match.group(1) for match in CRY_RE.finditer(text)))
    return cries
