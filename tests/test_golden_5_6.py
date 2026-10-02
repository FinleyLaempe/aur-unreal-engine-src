from __future__ import annotations

from pathlib import Path

import pytest

from render import UpstreamSnapshot, render

GOLDEN_FILENAMES = [
    "PKGBUILD",
    ".SRCINFO",
    "unreal-engine-5.6.sh",
    "com.unrealengine.UE5_6Editor.desktop",
    "unreal-engine-src-5.6-pacman-cache.hook",
]


@pytest.mark.parametrize("filename", GOLDEN_FILENAMES)
def test_render_5_6_matches_golden(
    repo_root: Path, filename: str, upstream_patches_5_6: dict[str, bytes]
) -> None:
    # Fixed snapshot (no git) so the golden files don't depend on commit hashes.
    upstream = UpstreamSnapshot(
        minor="5.6",
        commit="6d6c25d0000000000000000000000000000000000",
        pkgver="5.6.1",
        author="Alexis Belmonte",
        patches=upstream_patches_5_6,
    )
    rendered = render(
        repo=repo_root,
        minor="5.6",
        pkgver="5.6.1",
        template_sha="golden",
        upstream=upstream,
    )
    expected = (
        repo_root / "tests" / "fixtures" / "expected" / "5.6" / filename
    ).read_bytes()
    actual = rendered.files[filename]
    if actual != expected:
        # Print first divergence for fast debugging
        for i, (a, e) in enumerate(zip(actual, expected)):
            if a != e:
                pytest.fail(
                    f"{filename} diverges at byte {i}: "
                    f"got {actual[max(0, i - 20):i + 20]!r} "
                    f"expected {expected[max(0, i - 20):i + 20]!r}"
                )
        pytest.fail(
            f"{filename} length differs: got {len(actual)}, expected {len(expected)}"
        )
