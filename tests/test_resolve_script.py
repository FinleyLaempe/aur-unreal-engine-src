from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from render import resolve_upstream


def _run_script(repo_root: Path, upstream: Path, cache: Path) -> dict:
    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "resolve-upstream.sh"), str(upstream), str(cache)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_script_matches_python_resolver(repo_root: Path, tmp_path: Path, fake_upstream) -> None:
    out = _run_script(repo_root, fake_upstream.path, tmp_path / "cache")
    expected = resolve_upstream(fake_upstream.path)

    assert out["head"] == fake_upstream.commits["srcinfo"]
    assert [s["minor"] for s in out["snapshots"]] == ["5.8", "5.6", "5.4"]
    for snap in out["snapshots"]:
        py = expected[snap["minor"]]
        assert snap["commit"] == py.commit
        assert snap["pkgver"] == py.pkgver
        assert snap["author"] == py.author
        assert {n: base64.b64decode(b) for n, b in snap["patches"].items()} == py.patches
        assert list(snap["patches"]) == sorted(py.patches)


def test_script_reuses_cache_and_picks_up_new_commits(
    repo_root: Path, tmp_path: Path, fake_upstream
) -> None:
    cache = tmp_path / "cache"
    _run_script(repo_root, fake_upstream.path, cache)

    (fake_upstream.path / "PKGBUILD").write_text("pkgname=unreal-engine\npkgver=5.8.3\npkgrel=1\n")
    subprocess.run(
        ["git", "-C", str(fake_upstream.path), "-c", "user.name=Alexis Belmonte",
         "-c", "user.email=a@example.com", "commit", "-qam", "Bump"],
        check=True,
    )
    out = _run_script(repo_root, fake_upstream.path, cache)
    assert out["snapshots"][0]["minor"] == "5.8"
    assert out["snapshots"][0]["pkgver"] == "5.8.3"
