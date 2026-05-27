from __future__ import annotations

from pathlib import Path

import pytest

from render import MinorMeta, load_minor_meta


def test_load_minor_meta_5_6(templates_dir: Path) -> None:
    meta = load_minor_meta(templates_dir / "5.6")
    assert meta == MinorMeta(
        sdk_version_override="",
        pkgrel=1,
        patches=[
            "0001-override-shared-target-build.patch",
            "0002-suppress-scriptbuild-warnings-for-5-6.patch",
        ],
        notes="5.6.x patches inherited from upstream maintainer (Alexis Belmonte). Verified against 5.6.1-release.",
    )


def test_load_minor_meta_5_0_empty_patches(templates_dir: Path) -> None:
    meta = load_minor_meta(templates_dir / "5.0")
    assert meta.patches == []
    assert meta.pkgrel == 1
    assert meta.sdk_version_override == ""


def test_load_minor_meta_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_minor_meta(tmp_path / "5.99")
