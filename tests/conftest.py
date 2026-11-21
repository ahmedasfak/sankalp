"""Shared test setup. Run from the repository root:  pytest -q

* Puts the repo root (for `agent.*` imports) and agent/ (the modules import each
  other as `from data import ...`) on sys.path.
* Sets a placeholder OPENROUTE_API_KEY if none is set, because rules.py imports
  llm.py, which builds the client at import. No test calls the model or the network.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
for p in (str(AGENT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("OPENROUTE_API_KEY", "test-key-not-used")


@pytest.fixture(scope="session")
def register():
    """The de-duplicated claims register, as claim_validate uses it."""
    import claim_validate as cv
    return cv.lookup()["claims"]
