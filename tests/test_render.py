from __future__ import annotations

from pathlib import Path

import pytest

from render import MinorMeta, load_minor_meta


def test_load_minor_meta_reads_override(tmp_path: Path) -> None:
    minor_dir = tmp_path / "5.6"
    minor_dir.mkdir()
    (minor_dir / "meta.toml").write_text(
        'sdk_version_override = "v26"\npkgrel = 2\npatches = ["9001-local.patch"]\nnotes = "n"\n'
    )
    meta = load_minor_meta(minor_dir)
    assert meta == MinorMeta(
        sdk_version_override="v26", pkgrel=2, patches=["9001-local.patch"], notes="n"
    )


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


from render import (
    RenderedFiles,
    UpstreamSnapshot,
    pick_snapshot,
    render,
    resolve_upstream,
    upstream_credit,
)


def test_resolve_upstream_newest_commit_per_minor(fake_upstream) -> None:
    snaps = resolve_upstream(fake_upstream.path)
    assert sorted(snaps) == ["5.4", "5.6", "5.8"]
    assert snaps["5.6"].commit == fake_upstream.commits["v5.6.1"]
    assert snaps["5.6"].pkgver == "5.6.1"
    assert snaps["5.6"].author == "Alexis Belmonte"
    assert sorted(snaps["5.6"].patches) == [
        "0001-override-shared-target-build.patch",
        "0002-suppress-scriptbuild-warnings-for-5-6.patch",
    ]
    assert snaps["5.4"].author == "Neko-san"
    assert list(snaps["5.4"].patches) == ["use_system_clang.patch"]


def test_resolve_upstream_ignores_commits_not_touching_pkgbuild(fake_upstream) -> None:
    snaps = resolve_upstream(fake_upstream.path)
    assert snaps["5.8"].commit == fake_upstream.commits["v5.8"]
    assert snaps["5.8"].patches == {
        "0001-override-shared-target-build.patch": b"new 0001\n",
        "0003-disable-lumen.patch": b"lumen\n",
    }


def _snap(minor: str) -> UpstreamSnapshot:
    return UpstreamSnapshot(
        minor=minor, commit=minor * 8, pkgver=f"{minor}.0", author="A", patches={}
    )


def test_pick_snapshot_exact_match() -> None:
    snaps = {m: _snap(m) for m in ("5.4", "5.6", "5.8")}
    assert pick_snapshot(snaps, "5.6").minor == "5.6"


def test_pick_snapshot_unknown_new_minor_uses_newest() -> None:
    snaps = {m: _snap(m) for m in ("5.4", "5.6", "5.8")}
    assert pick_snapshot(snaps, "5.9").minor == "5.8"
    assert pick_snapshot(snaps, "5.10").minor == "5.8"


def test_pick_snapshot_gap_uses_nearest_older() -> None:
    snaps = {m: _snap(m) for m in ("5.4", "5.6", "5.8")}
    assert pick_snapshot(snaps, "5.7").minor == "5.6"


def test_pick_snapshot_older_than_all_uses_oldest() -> None:
    snaps = {m: _snap(m) for m in ("5.4", "5.6")}
    assert pick_snapshot(snaps, "5.2").minor == "5.4"


def test_upstream_credit_names_commit_version_and_author() -> None:
    snap = UpstreamSnapshot(
        minor="5.8", commit="dc9aa87e7b82", pkgver="5.8.2", author="Alexis Belmonte", patches={}
    )
    assert upstream_credit(snap) == (
        "Patches in this package: upstream commit dc9aa87 (5.8.2, Alexis Belmonte)"
    )


def test_render_5_6_produces_expected_filenames(
    repo_root: Path, fake_upstream
) -> None:
    # Caller-supplied template_sha is opaque to render() — it doesn't go into
    # output files, just gets passed through state. This test confirms the
    # function shape, not output contents (golden test handles that).
    snap = pick_snapshot(resolve_upstream(fake_upstream.path), "5.6")
    out = render(
        repo=repo_root,
        minor="5.6",
        pkgver="5.6.1",
        template_sha="deadbeefcafe",
        upstream=snap,
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


def test_render_skips_ignored_upstream_patch(repo_root: Path, fake_upstream) -> None:
    snap = pick_snapshot(resolve_upstream(fake_upstream.path), "5.4")
    out = render(
        repo=repo_root, minor="5.4", pkgver="5.4.4", template_sha="abc", upstream=snap
    )
    names = set(out.files.keys())
    assert "unreal-engine-5.4.sh" in names
    assert "com.unrealengine.UE5_4Editor.desktop" in names
    assert "unreal-engine-src-5.4-pacman-cache.hook" in names
    assert "ue5_4editor.svg" in names
    # use_system_clang.patch is listed in upstream-ignore.txt
    assert not any(n.endswith(".patch") for n in names)
    assert b"use_system_clang" not in out.files["PKGBUILD"]


def test_render_new_minor_uses_newest_upstream_patches(
    repo_root: Path, fake_upstream
) -> None:
    snap = pick_snapshot(resolve_upstream(fake_upstream.path), "5.9")
    out = render(
        repo=repo_root, minor="5.9", pkgver="5.9.0", template_sha="abc", upstream=snap
    )
    assert out.files["0003-disable-lumen.patch"] == b"lumen\n"
    pkgbuild = out.files["PKGBUILD"].decode()
    assert "pkgname=unreal-engine-src-5.9" in pkgbuild
    short = fake_upstream.commits["v5.8"][:7]
    assert f"upstream commit {short} (5.8.2, Alexis Belmonte)" in pkgbuild


def test_render_adds_local_override_patches(tmp_path: Path, repo_root: Path) -> None:
    import shutil

    repo = tmp_path / "tpl"
    shutil.copytree(repo_root, repo, ignore=shutil.ignore_patterns("venv", ".git", "tests"))
    (repo / "templates" / "5.8" / "patches").mkdir(parents=True)
    (repo / "templates" / "5.8" / "meta.toml").write_text('patches = ["9001-local.patch"]\n')
    (repo / "templates" / "5.8" / "patches" / "9001-local.patch").write_bytes(b"local\n")
    snap = UpstreamSnapshot(
        minor="5.8", commit="c" * 40, pkgver="5.8.2", author="A", patches={"0001-a.patch": b"a\n"}
    )
    out = render(repo=repo, minor="5.8", pkgver="5.8.3", template_sha="x", upstream=snap)
    pkgbuild = out.files["PKGBUILD"].decode()
    assert pkgbuild.index("'0001-a.patch'") < pkgbuild.index("'9001-local.patch'")
    assert out.files["9001-local.patch"] == b"local\n"


import subprocess
import sys


def test_cli_writes_output_directory(
    repo_root: Path, tmp_path: Path, fake_upstream
) -> None:
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
            "--upstream",
            str(fake_upstream.path),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "PKGBUILD").is_file()
    assert (out_dir / ".SRCINFO").is_file()
    assert (out_dir / "0002-suppress-scriptbuild-warnings-for-5-6.patch").is_file()
