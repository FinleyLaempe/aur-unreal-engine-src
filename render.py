"""Renderer for per-minor UE5 AUR templates.

Public surface (must match the JS port embedded in n8n Code node 7):
- render(repo: Path, minor: str, pkgver: str, template_sha: str) -> RenderedFiles
- load_minor_meta(minor_dir: Path) -> MinorMeta
"""

from __future__ import annotations

import hashlib
import re
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


_TOKEN_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def substitute(template: str, values: dict[str, str]) -> str:
    """Replace {{TOKEN}} with values[TOKEN]. Raises if any token is unmatched.

    Empty string values are allowed (used for optional placeholders like
    SDK_VERSION_OVERRIDE which defaults to empty).
    """

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in values:
            raise ValueError(f"unsubstituted token: {{{{{token}}}}}")
        return values[token]

    return _TOKEN_RE.sub(_replace, template)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_MINOR_RE = re.compile(r"^(\d+)\.(\d+)$")


def derive_values(
    minor: str, pkgver: str, pkgrel: int, sdk_override: str
) -> dict[str, str]:
    if not _MINOR_RE.match(minor):
        raise ValueError(f"invalid minor (expected 'X.Y'): {minor!r}")
    minor_underscore = minor.replace(".", "_")
    pkgname = f"unreal-engine-src-{minor}"
    launcher_bin = f"unreal-engine-{minor}"
    symlinks = f"ue{minor} UE{minor}"
    return {
        "PKGNAME": pkgname,
        "MINOR": minor,
        "MINOR_UNDERSCORE": minor_underscore,
        "PKGVER": pkgver,
        "PKGREL": str(pkgrel),
        "SDK_VERSION_OVERRIDE": sdk_override,
        "INSTALL_DIR": f"opt/{pkgname}",
        "LAUNCHER_BIN": launcher_bin,
        "SYMLINKS": symlinks,
    }
