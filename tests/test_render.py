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


from render import substitute


def test_substitute_single_token() -> None:
    out = substitute("hello {{NAME}}", {"NAME": "world"})
    assert out == "hello world"


def test_substitute_multiple_tokens() -> None:
    out = substitute(
        "{{PKGNAME}}-{{PKGVER}}",
        {"PKGNAME": "unreal-engine-src-5.6", "PKGVER": "5.6.1"},
    )
    assert out == "unreal-engine-src-5.6-5.6.1"


def test_substitute_unreplaced_token_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="unsubstituted token"):
        substitute("hello {{NAME}}", {})


def test_substitute_no_tokens_passthrough() -> None:
    assert substitute("plain text", {}) == "plain text"


def test_substitute_empty_value_allowed() -> None:
    out = substitute("sdk={{SDK_VERSION_OVERRIDE}}", {"SDK_VERSION_OVERRIDE": ""})
    assert out == "sdk="
