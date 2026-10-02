from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def templates_dir(repo_root: Path) -> Path:
    return repo_root / "templates"


@pytest.fixture
def upstream_patches_5_6(repo_root: Path) -> dict[str, bytes]:
    patch_dir = repo_root / "tests" / "fixtures" / "upstream" / "5.6"
    return {p.name: p.read_bytes() for p in sorted(patch_dir.glob("*.patch"))}


@dataclass
class FakeUpstream:
    path: Path
    commits: dict[str, str]  # label -> full commit sha


def _git(repo: Path, *args: str, author: str = "Nobody") -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": "nobody@example.com",
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": "nobody@example.com",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


@pytest.fixture
def fake_upstream(
    tmp_path: Path, upstream_patches_5_6: dict[str, bytes]
) -> FakeUpstream:
    """A tiny stand-in for aur.archlinux.org/unreal-engine.git.

    History, oldest first:
      v5.4    5.4.4 by Neko-san with the opt-in use_system_clang.patch
      v5.6.0  5.6.0 with an older 0001
      v5.6.1  5.6.1 with the real 5.6 patches (0001, 0002)
      v5.8    5.8.2: 0002 dropped, 0003 added
      srcinfo .SRCINFO-only commit (must not move the 5.8 snapshot)
    """
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    commits: dict[str, str] = {}

    def commit(label: str, author: str, pkgver: str | None, files: dict[str, bytes]):
        if pkgver is not None:
            (repo / "PKGBUILD").write_text(f"pkgname=unreal-engine\npkgver={pkgver}\npkgrel=1\n")
        for name in [p.name for p in repo.glob("*.patch")]:
            if name not in files:
                (repo / name).unlink()
        for name, content in files.items():
            (repo / name).write_bytes(content)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", label, author=author)
        commits[label] = _git(repo, "rev-parse", "HEAD")

    p0001 = "0001-override-shared-target-build.patch"
    p0002 = "0002-suppress-scriptbuild-warnings-for-5-6.patch"
    commit("v5.4", "Neko-san", "5.4.4", {"use_system_clang.patch": b"clang\n"})
    commit("v5.6.0", "Alexis Belmonte", "5.6.0", {p0001: b"old 0001\n"})
    commit("v5.6.1", "Alexis Belmonte", "5.6.1", dict(upstream_patches_5_6))
    commit(
        "v5.8",
        "Alexis Belmonte",
        "5.8.2",
        {p0001: b"new 0001\n", "0003-disable-lumen.patch": b"lumen\n"},
    )
    (repo / ".SRCINFO").write_text("pkgbase = unreal-engine\n")
    commit(
        "srcinfo",
        "Alexis Belmonte",
        None,
        {p0001: b"new 0001\n", "0003-disable-lumen.patch": b"lumen\n"},
    )
    return FakeUpstream(path=repo, commits=commits)
