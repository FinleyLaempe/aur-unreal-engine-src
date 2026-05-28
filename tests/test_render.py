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


from render import sha256_hex


def test_sha256_hex_empty() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_hex_known_string() -> None:
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


from render import derive_values


def test_derive_values_5_6() -> None:
    v = derive_values(minor="5.6", pkgver="5.6.1", pkgrel=1, sdk_override="")
    assert v["PKGNAME"] == "unreal-engine-src-5.6"
    assert v["MINOR"] == "5.6"
    assert v["MINOR_UNDERSCORE"] == "5_6"
    assert v["PKGVER"] == "5.6.1"
    assert v["PKGREL"] == "1"
    assert v["SDK_VERSION_OVERRIDE"] == ""
    assert v["INSTALL_DIR"] == "opt/unreal-engine-src-5.6"
    assert v["LAUNCHER_BIN"] == "unreal-engine-5.6"
    assert v["SYMLINKS"] == "ue5.6 UE5.6"


def test_derive_values_5_0_with_sdk_override() -> None:
    v = derive_values(
        minor="5.0",
        pkgver="5.0.3",
        pkgrel=2,
        sdk_override="v22_clang-16.0.6-centos7",
    )
    assert v["MINOR_UNDERSCORE"] == "5_0"
    assert v["PKGREL"] == "2"
    assert v["SDK_VERSION_OVERRIDE"] == "v22_clang-16.0.6-centos7"
    assert v["LAUNCHER_BIN"] == "unreal-engine-5.0"


def test_derive_values_rejects_bad_minor() -> None:
    import pytest

    with pytest.raises(ValueError, match="invalid minor"):
        derive_values(minor="5", pkgver="5.0.0", pkgrel=1, sdk_override="")
    with pytest.raises(ValueError, match="invalid minor"):
        derive_values(minor="5.6.1", pkgver="5.6.1", pkgrel=1, sdk_override="")


from render import generate_srcinfo


def test_generate_srcinfo_minimal() -> None:
    fields = {
        "pkgbase": "unreal-engine-src-5.6",
        "pkgdesc": "A 3D game engine by Epic Games.",
        "pkgver": "5.6.1",
        "pkgrel": "1",
        "url": "https://www.unrealengine.com/",
        "arch": ["x86_64", "aarch64"],
        "license": ["custom:UnrealEngine", "GPL3"],
        "depends": ["sdl3", "python"],
        "source": ["unreal-engine.sh", "ue5_6editor.svg"],
        "sha256sums": ["aaa", "bbb"],
        "pkgname": "unreal-engine-src-5.6",
    }
    out = generate_srcinfo(fields)
    expected = (
        "pkgbase = unreal-engine-src-5.6\n"
        "\tpkgdesc = A 3D game engine by Epic Games.\n"
        "\tpkgver = 5.6.1\n"
        "\tpkgrel = 1\n"
        "\turl = https://www.unrealengine.com/\n"
        "\tarch = x86_64\n"
        "\tarch = aarch64\n"
        "\tlicense = custom:UnrealEngine\n"
        "\tlicense = GPL3\n"
        "\tdepends = sdl3\n"
        "\tdepends = python\n"
        "\tsource = unreal-engine.sh\n"
        "\tsource = ue5_6editor.svg\n"
        "\tsha256sums = aaa\n"
        "\tsha256sums = bbb\n"
        "\n"
        "pkgname = unreal-engine-src-5.6\n"
    )
    assert out == expected


from render import RenderedFiles, render


def test_render_5_6_produces_expected_filenames(
    repo_root: Path, tmp_path: Path
) -> None:
    # Caller-supplied template_sha is opaque to render() — it doesn't go into
    # output files, just gets passed through state. This test confirms the
    # function shape, not output contents (golden test handles that).
    out = render(
        repo=repo_root,
        minor="5.6",
        pkgver="5.6.1",
        template_sha="deadbeefcafe",
    )
    assert isinstance(out, RenderedFiles)
    assert out.pkgname == "unreal-engine-src-5.6"
    assert out.pkgver == "5.6.1"
    assert out.pkgrel == 1
    names = set(out.files.keys())
    assert "PKGBUILD" in names
    assert ".SRCINFO" in names
    assert "unreal-engine-5.6.sh" in names
    assert "com.unrealengine.UE5_6Editor.desktop" in names
    assert "unreal-engine-src-5.6-pacman-cache.hook" in names
    assert "ue5_6editor.svg" in names
    assert "0001-override-shared-target-build.patch" in names
    assert "0002-suppress-scriptbuild-warnings-for-5-6.patch" in names
    # All values must be bytes (binary-safe for svg)
    for name, content in out.files.items():
        assert isinstance(content, bytes), f"{name} content not bytes"


def test_render_5_0_omits_patches_and_renames_assets(repo_root: Path) -> None:
    out = render(
        repo=repo_root, minor="5.0", pkgver="5.0.3", template_sha="abc"
    )
    names = set(out.files.keys())
    assert "unreal-engine-5.0.sh" in names
    assert "com.unrealengine.UE5_0Editor.desktop" in names
    assert "unreal-engine-src-5.0-pacman-cache.hook" in names
    assert "ue5_0editor.svg" in names
    # No patches for 5.0 (meta.toml has patches=[])
    assert not any(n.endswith(".patch") for n in names)


import subprocess
import sys


def test_cli_writes_output_directory(repo_root: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out-5.6"
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "render.py"),
            "5.6",
            "--pkgver",
            "5.6.1",
            "--template-sha",
            "testsha",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "PKGBUILD").is_file()
    assert (out_dir / ".SRCINFO").is_file()
