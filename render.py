"""Renderer for per-minor UE5 AUR templates.

Public surface (must match the JS port embedded in n8n Code node 7):
- render(repo: Path, minor: str, pkgver: str, template_sha: str) -> RenderedFiles
- load_minor_meta(minor_dir: Path) -> MinorMeta
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MinorMeta:
    sdk_version_override: str
    pkgrel: int
    patches: list[str] = field(default_factory=list)
    notes: str = ""


def load_minor_meta(minor_dir: Path) -> MinorMeta:
    meta_path = minor_dir / "meta.toml"
    if not meta_path.is_file():
        raise FileNotFoundError(f"meta.toml not found in {minor_dir}")
    with meta_path.open("rb") as f:
        raw = tomllib.load(f)
    return MinorMeta(
        sdk_version_override=raw.get("sdk_version_override", ""),
        pkgrel=int(raw.get("pkgrel", 1)),
        patches=list(raw.get("patches", [])),
        notes=raw.get("notes", ""),
    )
