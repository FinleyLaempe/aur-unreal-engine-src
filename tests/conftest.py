from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def templates_dir(repo_root: Path) -> Path:
    return repo_root / "templates"
