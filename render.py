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


_SCALAR_KEYS = ("pkgbase", "pkgdesc", "pkgver", "pkgrel", "url")
_ARRAY_KEYS = (
    "arch",
    "license",
    "makedepends",
    "depends",
    "optdepends",
    "options",
    "source",
    "sha256sums",
)


def generate_srcinfo(fields: dict[str, object]) -> str:
    """Build .SRCINFO from a flat field map.

    Format mirrors `makepkg --printsrcinfo`: pkgbase first, then indented
    scalar/array fields (one line per array element), blank line, pkgname.
    """
    lines: list[str] = []
    lines.append(f"pkgbase = {fields['pkgbase']}")
    for key in _SCALAR_KEYS:
        if key == "pkgbase":
            continue
        value = fields.get(key)
        if value is None:
            continue
        lines.append(f"\t{key} = {value}")
    for key in _ARRAY_KEYS:
        values = fields.get(key) or []
        if not isinstance(values, list):
            raise TypeError(f"{key} must be a list, got {type(values).__name__}")
        for item in values:
            lines.append(f"\t{key} = {item}")
    lines.append("")
    lines.append(f"pkgname = {fields['pkgname']}")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class RenderedFiles:
    pkgname: str
    pkgver: str
    pkgrel: int
    template_sha: str
    files: dict[str, bytes]


def _read_bytes(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read()


def _read_text(path: Path) -> str:
    return _read_bytes(path).decode("utf-8")


def render(
    *, repo: Path, minor: str, pkgver: str, template_sha: str
) -> RenderedFiles:
    minor_dir = repo / "templates" / minor
    common_dir = repo / "templates" / "_common"
    meta = load_minor_meta(minor_dir)
    values = derive_values(
        minor=minor,
        pkgver=pkgver,
        pkgrel=meta.pkgrel,
        sdk_override=meta.sdk_version_override,
    )

    # Output filenames derived from values
    launcher_name = f"{values['LAUNCHER_BIN']}.sh"
    desktop_name = f"com.unrealengine.UE5_{values['MINOR_UNDERSCORE']}Editor.desktop"
    hook_name = f"{values['PKGNAME']}-pacman-cache.hook"
    icon_name = f"ue5_{values['MINOR_UNDERSCORE']}editor.svg"

    files: dict[str, bytes] = {}

    # Templated common assets
    files[launcher_name] = substitute(
        _read_text(common_dir / "unreal-engine.sh.tmpl"), values
    ).encode("utf-8")
    files[desktop_name] = substitute(
        _read_text(common_dir / "com.unrealengine.UE5Editor.desktop.tmpl"), values
    ).encode("utf-8")
    files[hook_name] = substitute(
        _read_text(common_dir / "unreal-engine-5-pacman-cache.hook.tmpl"), values
    ).encode("utf-8")
    # Binary asset, copied verbatim with renamed filename
    files[icon_name] = _read_bytes(common_dir / "ue5editor.svg")

    # Per-minor patches (copied verbatim, included in source=())
    patch_filenames: list[str] = []
    for patch in meta.patches:
        patch_path = minor_dir / "patches" / patch
        if not patch_path.is_file():
            raise FileNotFoundError(
                f"patch listed in meta.toml not found: {patch_path}"
            )
        files[patch] = _read_bytes(patch_path)
        patch_filenames.append(patch)

    # Build source=() and sha256sums=() in lockstep
    source_order: list[tuple[str, bytes]] = [
        (launcher_name, files[launcher_name]),
        (desktop_name, files[desktop_name]),
    ]
    for p in patch_filenames:
        source_order.append((p, files[p]))
    source_order.append((hook_name, files[hook_name]))
    source_order.append((icon_name, files[icon_name]))

    quoted_sources = "\n        ".join(f"'{name}'" for name, _ in source_order)
    quoted_hashes = "\n            ".join(
        f"'{sha256_hex(content)}'" for _, content in source_order
    )
    values["PATCH_SOURCES"] = quoted_sources
    values["NON_TOOLCHAIN_SHA256_LIST"] = quoted_hashes

    # Render PKGBUILD
    pkgbuild_tmpl = _read_text(repo / "PKGBUILD.tmpl")
    files["PKGBUILD"] = substitute(pkgbuild_tmpl, values).encode("utf-8")

    # Generate .SRCINFO from extracted PKGBUILD fields
    files[".SRCINFO"] = _build_srcinfo(
        pkgname=values["PKGNAME"],
        pkgver=pkgver,
        pkgrel=meta.pkgrel,
        source_filenames=[name for name, _ in source_order],
        source_hashes=[sha256_hex(content) for _, content in source_order],
    ).encode("utf-8")

    return RenderedFiles(
        pkgname=values["PKGNAME"],
        pkgver=pkgver,
        pkgrel=meta.pkgrel,
        template_sha=template_sha,
        files=files,
    )


def _build_srcinfo(
    *,
    pkgname: str,
    pkgver: str,
    pkgrel: int,
    source_filenames: list[str],
    source_hashes: list[str],
) -> str:
    fields: dict[str, object] = {
        "pkgbase": pkgname,
        "pkgdesc": "A 3D game engine by Epic Games which can be used non-commercially for free.",
        "pkgver": pkgver,
        "pkgrel": str(pkgrel),
        "url": "https://www.unrealengine.com/",
        "arch": ["x86_64", "x86_64_v2", "x86_64_v3", "x86_64_v4", "aarch64"],
        "license": ["custom:UnrealEngine", "GPL3"],
        "makedepends": ["git", "openssh", "sed", "grep", "glibc", "wget", "rsync"],
        "depends": [
            "sdl3",
            "python",
            "dotnet-runtime",
            "dotnet-sdk",
            "vulkan-icd-loader",
            "lld",
            "xdg-user-dirs",
            "dos2unix",
            "openssl",
            "steam",
            "coreutils",
            "findutils",
        ],
        "optdepends": [
            "polly: for potentially increased performance",
            "qt5-base: qmake build system for projects",
            "cmake: build system for projects",
            "qtcreator: IDE for projects",
            "codelite: IDE for projects",
            "kdevelop: IDE for projects",
            "clion: IDE for projects",
            "rider: IDE for projects",
            "code: IDE for projects",
            "pacman-contrib: for the paccache cleaning hook",
            'fake-ms-fonts: Font support for "demo/free/sample/example/tutorial" projects',
            'ttf-ms-fonts: Font support for "demo/free/sample/example/tutorial" projects',
        ],
        "options": ["!strip", "staticlibs"],
        "source": source_filenames,
        "sha256sums": source_hashes,
        "pkgname": pkgname,
    }
    return generate_srcinfo(fields)
