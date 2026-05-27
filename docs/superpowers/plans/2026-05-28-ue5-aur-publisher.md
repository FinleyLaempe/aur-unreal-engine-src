# UE5 AUR Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build template repo (Python renderer + PKGBUILD.tmpl + per-minor templates + CI) and rewrite n8n workflow `3JYJn2KCJvPUxA0k` so EpicGames/UnrealEngine releases auto-publish to `unreal-engine-src-5.X` AUR packages.

**Architecture:** Renderer (Python `render.py` + JS port embedded in n8n Code node) substitutes `{{PLACEHOLDERS}}` in `PKGBUILD.tmpl` + `templates/_common/*.tmpl` per minor, copies per-minor patches, generates `.SRCINFO`, base64-bundles for n8n push. n8n clones template repo anonymously, calls embedded JS renderer, pushes to AUR via SSH (key in container ssh-agent). Both renderer implementations must produce byte-identical output for the same inputs (verified by golden-file test).

**Tech Stack:** Python 3.11+ (stdlib `tomllib`, `hashlib`, `pathlib`, `argparse`), pytest, bash (AUR push + add-minor.sh), n8n TypeScript SDK (workflow code), GitHub Actions (CI), namcap (PKGBUILD lint).

---

## Spec reference

Full design: `docs/superpowers/specs/2026-05-28-ue5-aur-publisher-design.md`. Read it before starting Task 1.

## Working directory

All paths in this plan are relative to `/home/finley/Code/UE5/unreal-engine` (the template repo root, remote `git@github.com:FinleyLaempe/aur-unreal-engine-src.git`).

## File structure

**To create (committed):**
- `render.py` — Python renderer module + CLI entrypoint
- `tests/__init__.py` — empty marker
- `tests/conftest.py` — shared fixtures
- `tests/test_render.py` — renderer unit tests
- `tests/test_golden_5_6.py` — full-render golden file test for minor 5.6
- `tests/fixtures/expected/5.6/PKGBUILD` — golden file (rendered output)
- `tests/fixtures/expected/5.6/.SRCINFO` — golden file
- `tests/fixtures/expected/5.6/unreal-engine-5.6.sh` — golden file (rendered launcher)
- `tests/fixtures/expected/5.6/com.unrealengine.UE5_6Editor.desktop` — golden file
- `tests/fixtures/expected/5.6/unreal-engine-src-5.6-pacman-cache.hook` — golden file
- `pyproject.toml` — Python project metadata + pytest config
- `PKGBUILD.tmpl` — main PKGBUILD template
- `templates/_common/unreal-engine.sh.tmpl` — launcher template
- `templates/_common/com.unrealengine.UE5Editor.desktop.tmpl` — desktop template
- `templates/_common/unreal-engine-5-pacman-cache.hook.tmpl` — hook template
- `scripts/add-minor.sh` — scaffold helper for new minors
- `.github/workflows/test.yml` — pytest CI
- `.github/workflows/render-check.yml` — render-every-minor + namcap CI

**To modify on n8n (workflow ID `3JYJn2KCJvPUxA0k`, DataTable ID `GrWfNL8VhYWMKfWI`):**
- Add column `template_sha` (string) to DataTable
- Rewrite/add nodes 3, 5, 6, 7, 9, 10 per spec

**Reference only (uncommitted, .gitignored):**
- `templates/5.6/PKGBUILD.upstream` — Belmonte's PKGBUILD, source for `PKGBUILD.tmpl`
- `templates/_common/unreal-engine.sh.raw` — launcher reference
- `templates/_common/com.unrealengine.UE5Editor.desktop.raw`
- `templates/_common/unreal-engine-5-pacman-cache.hook.raw`

## Conventions

- Each task ends with a commit. Commit messages use Conventional Commits (`feat:`, `test:`, `fix:`, `chore:`).
- Python: 4-space indent, type hints required on public functions, `from __future__ import annotations` at top of each module.
- Bash scripts: `set -euo pipefail` at top, double-quote all variable expansions.
- All tests live under `tests/` and are pytest-discoverable.
- Run tests with `python -m pytest -v` (no venv assumption — use system Python 3.11+).

---

## Phase A — Renderer (Python, TDD)

### Task 1: Bootstrap pyproject.toml + test infrastructure

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "aur-unreal-engine-src"
version = "0.1.0"
description = "Per-minor AUR PKGBUILD template renderer"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-ra -q"

[tool.setuptools]
py-modules = ["render"]
```

- [ ] **Step 2: Write empty test marker**

Create `tests/__init__.py` as empty file (just `touch tests/__init__.py`).

- [ ] **Step 3: Write conftest.py with REPO_ROOT fixture**

```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def templates_dir(repo_root: Path) -> Path:
    return repo_root / "templates"
```

- [ ] **Step 4: Verify pytest discovers no tests yet**

Run: `python -m pytest --collect-only`
Expected: `no tests ran` (pytest exit 5)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py
git commit -m "chore: bootstrap pytest config and shared fixtures"
```

---

### Task 2: Implement TOML loading + Minor dataclass

**Files:**
- Create: `render.py`
- Create: `tests/test_render.py`

- [ ] **Step 1: Write failing test for `load_minor_meta`**

`tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: Implement minimal render.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_render.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): load per-minor meta.toml into MinorMeta dataclass"
```

---

### Task 3: Implement placeholder substitution

**Files:**
- Modify: `render.py` (add `substitute` function)
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing tests for substitution**

Append to `tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_render.py -v -k substitute`
Expected: ImportError on `substitute`.

- [ ] **Step 3: Implement substitute() in render.py**

Append to `render.py`:

```python
import re

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_render.py -v -k substitute`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): add substitute() with strict unmatched-token check"
```

---

### Task 4: Implement sha256 computation

**Files:**
- Modify: `render.py` (add `sha256_hex`)
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render.py`:

```python
from render import sha256_hex


def test_sha256_hex_empty() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_hex_known_string() -> None:
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/test_render.py -v -k sha256`
Expected: ImportError on `sha256_hex`.

- [ ] **Step 3: Implement sha256_hex**

Append to `render.py`:

```python
import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_render.py -v -k sha256`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): add sha256_hex helper for source integrity hashes"
```

---

### Task 5: Implement minor → derived values mapping

**Files:**
- Modify: `render.py` (add `derive_values`)
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/test_render.py -v -k derive_values`
Expected: ImportError on `derive_values`.

- [ ] **Step 3: Implement derive_values**

Append to `render.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_render.py -v -k derive_values`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): derive PKGNAME/INSTALL_DIR/LAUNCHER_BIN from minor"
```

---

### Task 6: Implement .SRCINFO generator

**Files:**
- Modify: `render.py` (add `generate_srcinfo`)
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/test_render.py -v -k generate_srcinfo`
Expected: ImportError on `generate_srcinfo`.

- [ ] **Step 3: Implement generate_srcinfo**

Append to `render.py`:

```python
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
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_render.py -v -k generate_srcinfo`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): generate .SRCINFO from flat field map"
```

---

### Task 7: Implement RenderedFiles + render() integration

**Files:**
- Modify: `render.py` (add `RenderedFiles`, `render`)
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_render.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/test_render.py -v -k "test_render_5"`
Expected: ImportError on `render`/`RenderedFiles`.

- [ ] **Step 3: Implement RenderedFiles + render**

Append to `render.py`:

```python
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
```

- [ ] **Step 4: This test will fail until templates exist**

Run: `python -m pytest tests/test_render.py -v -k "test_render_5"`
Expected: FileNotFoundError on `PKGBUILD.tmpl` (not yet created). This is expected. Mark these tests xfail temporarily:

```python
import pytest

pytestmark = pytest.mark.xfail(reason="templates not yet created; see Phase B", run=True, strict=False)
```

Place `pytestmark` at module level (top of file, after imports). Run again, expect XFAIL on the two render integration tests, PASS on all others.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): integrate render() pipeline (xfail until templates exist)"
```

---

### Task 8: Implement CLI entry point

**Files:**
- Modify: `render.py` (add `main()`)
- Modify: `tests/test_render.py` (CLI smoke test)

- [ ] **Step 1: Write failing CLI test**

Append to `tests/test_render.py`:

```python
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
```

This test will also xfail until templates exist — already covered by module-level xfail mark.

- [ ] **Step 2: Run test, verify it fails or xfails**

Run: `python -m pytest tests/test_render.py -v -k cli`
Expected: XFAIL (function not yet defined → triggers earlier import failure if `main` referenced elsewhere; otherwise PASS-as-xfail behaviour).

- [ ] **Step 3: Implement main()**

Append to `render.py`:

```python
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a per-minor UE5 AUR package."
    )
    parser.add_argument("minor", help="Minor version, e.g. '5.6'")
    parser.add_argument("--pkgver", required=True, help="e.g. '5.6.1'")
    parser.add_argument(
        "--template-sha",
        default="local",
        help="Template repo commit SHA (passed through to state).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Template repo root (default: dir containing render.py).",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Output directory."
    )
    args = parser.parse_args(argv)

    rendered = render(
        repo=args.repo,
        minor=args.minor,
        pkgver=args.pkgver,
        template_sha=args.template_sha,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.files.items():
        (args.out / name).write_bytes(content)
    print(
        f"Rendered {rendered.pkgname}-{rendered.pkgver}-{rendered.pkgrel} "
        f"({len(rendered.files)} files) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify CLI test still XFAILs (templates absent)**

Run: `python -m pytest tests/test_render.py -v -k cli`
Expected: XFAIL.

- [ ] **Step 5: Commit**

```bash
git add render.py tests/test_render.py
git commit -m "feat(render): add CLI entry point (python render.py <minor> --pkgver X.Y.Z)"
```

---

## Phase B — PKGBUILD.tmpl construction

Build `PKGBUILD.tmpl` by deriving from `templates/5.6/PKGBUILD.upstream` (uncommitted reference). At end of phase, remove the xfail mark from `tests/test_render.py` and confirm render tests pass.

### Task 9: Create PKGBUILD.tmpl skeleton

**Files:**
- Create: `PKGBUILD.tmpl`

- [ ] **Step 1: Copy upstream PKGBUILD to PKGBUILD.tmpl**

```bash
cp templates/5.6/PKGBUILD.upstream PKGBUILD.tmpl
```

- [ ] **Step 2: Verify file is identical to upstream**

```bash
diff templates/5.6/PKGBUILD.upstream PKGBUILD.tmpl
```

Expected: no output (files identical).

- [ ] **Step 3: Commit baseline**

```bash
git add PKGBUILD.tmpl
git commit -m "feat(pkgbuild): seed PKGBUILD.tmpl from upstream maintainer PKGBUILD"
```

---

### Task 10: Replace header block + introduce SDK override variable

**Files:**
- Modify: `PKGBUILD.tmpl` (lines 1–14)

- [ ] **Step 1: Edit lines 1–14**

Replace the existing header (lines 1–14, ending with `UE_SDK_VERSION="native-linux-v26_clang-20.1.8-rockylinux8"`) with:

```bash
# Inspired by Alexis Belmonte's <alexbelm48@gmail.com> upstream `unreal-engine` AUR
# Per-minor parallel-install variant. Templates auto-published from:
#   https://github.com/FinleyLaempe/aur-unreal-engine-src
# Maintainer: Finley Laempe <finley.laempe@web.de>

# The source is about 200 MiB, with an extra ~11 GiB of dependencies downloaded in Setup.sh, and may take several hours to compile.
# If you want additional options, there are switches below.
pkgname={{PKGNAME}}
pkgver={{PKGVER}}
pkgrel={{PKGREL}}
_uetag="${pkgver}-release"
_ueminor="{{MINOR}}"
_ueminor_us="{{MINOR_UNDERSCORE}}"
# Empty override = parse from cloned UE5 repo's Engine/Config/Linux/Linux_SDK.json at build time
_ue_sdk_override="{{SDK_VERSION_OVERRIDE}}"
```

Use the Edit tool with this `old_string`:

```
# Old Maintainer: Dylan Ferris <dylan@psilly.com>
# Old Maintainer: Michael Lojkovic <mikelojkovic@gmail.com>
# Old Maintainer: Shatur95 <genaloner@gmail.com>
# Old Maintainer: slx
# Old Co-Maintainer: Neko-san <nekoNexus at protonmail dot ch>
# Maintainer: Alexis Belmonte <alexbelm48@gmail.com>

# The source is about 200 MiB, with an extra ~11 GiB of dependencies downloaded in Setup.sh, and may take several hours to compile.
# If you want additional options, there are switches below.
pkgname=unreal-engine
pkgver=5.6.1
pkgrel=1
## Check unreal-engine/Engine/Config/Linux/Linux_SDK.json (MainVersion value) for what the below should be set to
UE_SDK_VERSION="native-linux-v26_clang-20.1.8-rockylinux8"
```

- [ ] **Step 2: Commit**

```bash
git add PKGBUILD.tmpl
git commit -m "feat(pkgbuild): templated header — pkgname/pkgver/pkgrel/minor placeholders + SDK override"
```

---

### Task 11: Replace source=() and sha256sums=() blocks

**Files:**
- Modify: `PKGBUILD.tmpl` (lines around 33–46 originally)

- [ ] **Step 1: Edit source=() and sha256sums=()**

Replace this block:

```bash
source=("${UE_SDK_VERSION}.tar.gz::https://cdn.unrealengine.com/Toolchain_Linux/${UE_SDK_VERSION}.tar.gz"
        'unreal-engine.sh'
        'com.unrealengine.UE5Editor.desktop'
        '0001-override-shared-target-build.patch'
        '0002-suppress-scriptbuild-warnings-for-5-6.patch'
        'unreal-engine-5-pacman-cache.hook'
        'ue5editor.svg')
sha256sums=('6eef42679b744cdcb50276f2d7cff0a51f7ddd632960e06bfbc3f6b9508ef615'
            '55a8ad79c2e502bc5919249b9d1804ad405795b36630ab2f23aeb99dd218e5f4'
            'aa09746f9db93713f470ef19390a89b279fd5a335835ad95eab6cdaafa1b9e99'
            'cd512e3fc08aaaa783e8df4a6dcb567a35502c32a6cedf8d4d71ebfa75272735'
            'e01efe8559076f977c44ab656432a3c8e793e4c7f2b42855f736a08b6f551cf1'
            '9386160a91594abeeaf4fe02fea562e7a4ead4c6f9a258c2a37b2e5f10e7deca'
            'b00c398b63f15084c46f3963f62a45284ecd8dae9ba6f38a2c4af370bbfdab8d')
```

With:

```bash
# Toolchain tarball is NOT in source=(); downloaded by prepare() after clone
# once SDK_VERSION is known (either from {{SDK_VERSION_OVERRIDE}} or parsed
# from the cloned UE5 repo's Engine/Config/Linux/Linux_SDK.json).
source=({{PATCH_SOURCES}})
sha256sums=({{NON_TOOLCHAIN_SHA256_LIST}})
```

- [ ] **Step 2: Commit**

```bash
git add PKGBUILD.tmpl
git commit -m "feat(pkgbuild): drop toolchain from source=(); inject templated source + sha lists"
```

---

### Task 12: Replace prepare() clone-and-SSH-check with SSH/HTTPS fallback + SDK parse

**Files:**
- Modify: `PKGBUILD.tmpl` (the prepare() function)

- [ ] **Step 1: Edit prepare() function**

Replace the existing `prepare()` block (starts `prepare() {` at line ~248, ends `}` at line ~373) with the following. **Important:** preserve the existing `_ue_commit`, `_ue_install_path`, `_ue_arch_label`, etc. summary print block from upstream lines 255–311 — it is the user-facing build configuration summary, and removing it regresses UX. The replacement below preserves it.

```bash
prepare() {
  # --- Probe GitHub access (SSH first, HTTPS fallback) ---
  local _ue_remote_ssh="git@github.com:EpicGames/UnrealEngine.git"
  local _ue_remote_https="https://github.com/EpicGames/UnrealEngine.git"
  local _ue_remote=""

  msg "Probing GitHub access to EpicGames/UnrealEngine..."
  if git ls-remote "${_ue_remote_ssh}" &>/dev/null; then
    _ue_remote="${_ue_remote_ssh}"
    msg "  -> SSH OK, using ${_ue_remote}"
  elif git ls-remote "${_ue_remote_https}" &>/dev/null; then
    _ue_remote="${_ue_remote_https}"
    msg "  -> SSH failed, HTTPS OK, using ${_ue_remote}"
  else
    error "Cannot access EpicGames/UnrealEngine via SSH or HTTPS."
    error "You must:"
    error "  1. Have a GitHub account linked to your Epic Games account:"
    error "     https://www.unrealengine.com/en-US/ue-on-github"
    error "  2. Accept the @EpicGames org invitation in your GitHub inbox."
    error "  3. Configure either:"
    error "     - SSH: 'ssh -T git@github.com' must succeed with your key"
    error "     - HTTPS: 'gh auth login' or git credential helper with PAT (repo scope)"
    error "Probed: ${_ue_remote_ssh} and ${_ue_remote_https}"
    exit 1
  fi

  # --- Build config summary (preserved from upstream lines 255–311) ---
  local _ue_commit="not-cloned"
  local _ue_install_path="/${UE_INSTALL_DIR#/}"
  local _ue_arch_label="${_ue_build_arch:-unknown}"
  local _ue_arch_detail=""
  local _ue_ddc_text="no"
  local _ue_debug_text="no"
  local _ue_default_logo_text="yes"
  local _ue_target_platforms=()
  local _ue_platforms_csv="none"

  if [[ -d "${pkgname}/.git" ]]; then
    _ue_commit="$(git -C "${pkgname}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  fi
  if [[ "${_ue_arch_label}" == "x64" ]]; then
    if [[ -n "${_ue_detected_march}" ]]; then
      _ue_arch_detail=" (${_ue_detected_march})"
    elif [[ ${CFLAGS} =~ -march=([^[:space:]]+) ]]; then
      _ue_arch_detail=" (${BASH_REMATCH[1]})"
    else
      _ue_arch_detail=" (x86_64)"
    fi
  elif [[ "${_ue_arch_label}" == "arm64" ]]; then
    if [[ ${CFLAGS} =~ -march=([^[:space:]]+) ]]; then
      _ue_arch_detail=" (${BASH_REMATCH[1]})"
    else
      _ue_arch_detail=" (aarch64)"
    fi
  fi
  [[ "${UE_WITH_DDC}" == "true" ]]                  && _ue_ddc_text="yes"
  [[ "${UE_WITH_FULL_DEBUG_INFO}" == "true" ]]      && _ue_debug_text="yes"
  [[ "${UE_USE_DEFAULT_LOGO_AT_INSTALL}" == "0" ]]  && _ue_default_logo_text="no"
  [[ "${UE_WITH_WIN64}" == "true" ]]    && _ue_target_platforms+=("Windows")
  [[ "${UE_WITH_LINUX}" == "true" ]]    && _ue_target_platforms+=("Linux")
  [[ "${UE_WITH_MAC}" == "true" ]]      && _ue_target_platforms+=("macOS")
  [[ "${UE_WITH_TVOS}" == "true" ]]     && _ue_target_platforms+=("tvOS")
  [[ "${UE_WITH_ANDROID}" == "true" ]]  && _ue_target_platforms+=("Android")
  [[ "${UE_WITH_IOS}" == "true" ]]      && _ue_target_platforms+=("iOS")
  if (( ${#_ue_target_platforms[@]} > 0 )); then
    local IFS=", "
    _ue_platforms_csv="${_ue_target_platforms[*]}"
  fi
  msg ''
  msg "Unreal Engine ${pkgver} (commit ${_ue_commit}) build options summary:"
  msg ''
  msg "- End package installation path:            ${_ue_install_path}"
  msg "- Target architecture build:                ${_ue_arch_label}${_ue_arch_detail}"
  msg "- Integrate prebuilt shader cache:          ${_ue_ddc_text}"
  msg "- Target platforms supported for export:    ${_ue_platforms_csv}"
  msg "- Game configurations:                      ${UE_GAME_CONFIGURATIONS}"
  msg "- Include full debug info:                  ${_ue_debug_text}"
  msg "- Use default logo at install:              ${_ue_default_logo_text}"
  msg ''

  # --- Clone or update UE5 source ---
  if [[ ! -d "${pkgname}" ]]; then
    git clone --depth=1 --branch="${_uetag}" "${_ue_remote}" "${pkgname}"
  else
    cd "${pkgname}"
    if [[ "$(git describe --tags 2>/dev/null)" != "${_uetag}" ]]; then
      cd .. && rm -rf "${pkgname}"
      git clone --depth=1 --branch="${_uetag}" "${_ue_remote}" "${pkgname}"
    else
      rm -f .git/index.lock
      git fetch --depth=1 origin tag "${_uetag}"
      git reset --hard "${_uetag}"
      cd ..
    fi
  fi

  # --- Apply per-minor patches (continues on failure per upstream behaviour) ---
  for patch_file in ../*.patch; do
    [[ -f "${patch_file}" ]] || continue
    msg "Applying ${patch_file}"
    if ! patch -p1 -d "${pkgname}" -i "${patch_file}"; then
      msg "Some or all of the patch at ${patch_file} failed to apply. Will still try to build."
    fi
  done

  cd "${pkgname}" || return

  # --- Qt Creator source code access (preserved from upstream) ---
  if [[ ! -d Engine/Plugins/Developer/QtCreatorSourceCodeAccess ]]; then
    git -C Engine/Plugins/Developer clone --depth=1 https://github.com/fire-archive/QtCreatorSourceCodeAccess
  fi

  # --- HaveLinuxDependencies marker (preserved from upstream) ---
  if [[ ! -f Engine/Source/ThirdParty/Linux/HaveLinuxDependencies ]]; then
    mkdir -p Engine/Source/ThirdParty/Linux/
    touch Engine/Source/ThirdParty/Linux/HaveLinuxDependencies
    sed -i "1c\This file must have no extension so that GitDeps considers it a binary dependency - it will only be pulled by the Setup script if Linux is enabled. Please do not remove this file." Engine/Source/ThirdParty/Linux/HaveLinuxDependencies
  fi

  # --- Setup.sh tweak for non-interactive UVS register (preserved) ---
  if [[ -f Setup.sh ]]; then
    sed -i 's#UnrealVersionSelector-Linux-Shipping -register > /dev/null &#UnrealVersionSelector-Linux-Shipping -register -unattended > /dev/null \&#' Setup.sh
  fi

  ./Setup.sh
  cd "${srcdir}" || return

  # --- Resolve SDK_VERSION ---
  local _sdk_ver="${_ue_sdk_override}"
  if [[ -z "${_sdk_ver}" ]]; then
    local _sdk_json="${srcdir}/${pkgname}/Engine/Config/Linux/Linux_SDK.json"
    if [[ ! -f "${_sdk_json}" ]]; then
      error "Cannot find ${_sdk_json}; cannot resolve SDK_VERSION."
      exit 1
    fi
    _sdk_ver=$(grep -oE '"MainVersion"[[:space:]]*:[[:space:]]*"[^"]+"' "${_sdk_json}" | \
               sed -E 's/.*"MainVersion"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')
  fi
  msg "Resolved SDK_VERSION=${_sdk_ver}"

  # --- Download + extract toolchain ---
  local _sdk_url="https://cdn.unrealengine.com/Toolchain_Linux/${_sdk_ver}.tar.gz"
  local _sdk_tar="${srcdir}/${_sdk_ver}.tar.gz"
  if [[ ! -f "${_sdk_tar}" ]]; then
    msg "Downloading SDK toolchain from ${_sdk_url}"
    curl -fL --retry 3 -o "${_sdk_tar}" "${_sdk_url}" || {
      error "Failed to download SDK toolchain from ${_sdk_url}"
      exit 1
    }
  fi

  mkdir -p "${srcdir}/${pkgname}/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/"
  tar -xf "${_sdk_tar}" -C "${srcdir}/${pkgname}/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/"

  # --- Build third-party + dotnet setup (preserved from upstream) ---
  "${srcdir}/${pkgname}/Engine/Build/BatchFiles/Linux/BuildThirdParty.sh"
  "${srcdir}/${pkgname}/Engine/Build/BatchFiles/Linux/SetupDotnet.sh"
  "${srcdir}/${pkgname}/Engine/Build/BatchFiles/Linux/FixDependencyFiles.sh"
}
```

- [ ] **Step 2: Lint with shellcheck (best-effort)**

```bash
shellcheck -s bash PKGBUILD.tmpl 2>&1 | head -50
```

Expected: warnings only; no errors that block (SC2086 in PKGBUILD context is fine).

- [ ] **Step 3: Commit**

```bash
git add PKGBUILD.tmpl
git commit -m "feat(pkgbuild): clone fallback + SDK parse in prepare()"
```

---

### Task 13: Templatize install dir + launcher + symlinks + desktop file + hook in package()

**Files:**
- Modify: `PKGBUILD.tmpl` (package() function and surrounding install-dir block)

- [ ] **Step 1: Edit install dir default**

Find:

```bash
if [[ "${UE_INSTALL_DIR}" == "" ]]; then
  export UE_INSTALL_DIR="opt/${pkgname}"
fi
```

Replace with:

```bash
if [[ "${UE_INSTALL_DIR}" == "" ]]; then
  export UE_INSTALL_DIR="{{INSTALL_DIR}}"
fi
```

- [ ] **Step 2: Edit desktop file handling in package()**

Find:

```bash
  # Desktop entry
  if [[ ! -f com.unrealengine.UE5Editor.desktop && -f com.unrealengine.UE4Editor.desktop ]]; then
    cp com.unrealengine.UE4Editor.desktop com.unrealengine.UE5Editor.desktop
  fi
  
  sed -i "7c\Exec=/usr/bin/unreal-engine %U" com.unrealengine.UE5Editor.desktop
  sed -i "14c\Path=/usr/bin/" com.unrealengine.UE5Editor.desktop
  install -Dm644 com.unrealengine.UE5Editor.desktop "${pkgdir}/usr/share/applications/com.unrealengine.UE5Editor.desktop"
  chmod +x "${pkgdir}/usr/share/applications/com.unrealengine.UE5Editor.desktop"
```

Replace with:

```bash
  # Desktop entry (rendered with correct Exec + Path per minor; no sed needed)
  install -Dm644 "com.unrealengine.UE5_${_ueminor_us}Editor.desktop" \
    "${pkgdir}/usr/share/applications/com.unrealengine.UE5_${_ueminor_us}Editor.desktop"
  chmod +x "${pkgdir}/usr/share/applications/com.unrealengine.UE5_${_ueminor_us}Editor.desktop"
```

- [ ] **Step 3: Edit pacman hook install**

Find:

```bash
  ## Install a pacman hook to keep old builds from compounding cache by tens of GBs - 2 builds alone can reach at least 30 GBs in pacman's cache; having one only takes up about 15 GBs
  install -Dm775 unreal-engine-5-pacman-cache.hook "${pkgdir}/etc/pacman.d/hooks/unreal-engine-5-pacman-cache.hook"
```

Replace with:

```bash
  ## Pacman hook: trim cache to one prior build per minor
  install -Dm775 "${pkgname}-pacman-cache.hook" \
    "${pkgdir}/etc/pacman.d/hooks/${pkgname}-pacman-cache.hook"
```

- [ ] **Step 4: Edit icon install**

Find:

```bash
  # Icon for Desktop entry
  if [[ "${UE_USE_DEFAULT_LOGO_AT_INSTALL}" == "1" ]]; then
    install -Dm644 ue5editor.svg "${pkgdir}/usr/share/pixmaps/ue5editor.svg"
  else
```

Replace with:

```bash
  # Icon for Desktop entry (renamed per minor to avoid pixmap collisions)
  if [[ "${UE_USE_DEFAULT_LOGO_AT_INSTALL}" == "1" ]]; then
    install -Dm644 "ue5_${_ueminor_us}editor.svg" "${pkgdir}/usr/share/pixmaps/ue5_${_ueminor_us}editor.svg"
  else
```

Then find the wget download branch a few lines later:

```bash
    mv ue5editor.svg ue5editor.svg.bak
    wget --output-document "ue5editor.svg" "https://raw.githubusercontent.com/EliverLara/candy-icons/master/apps/scalable/ue4editor.svg"
    install -Dm644 ue5editor.svg "${pkgdir}/usr/share/pixmaps/ue5editor.svg"
```

Replace with:

```bash
    mv "ue5_${_ueminor_us}editor.svg" "ue5_${_ueminor_us}editor.svg.bak"
    wget --output-document "ue5_${_ueminor_us}editor.svg" "https://raw.githubusercontent.com/EliverLara/candy-icons/master/apps/scalable/ue4editor.svg"
    install -Dm644 "ue5_${_ueminor_us}editor.svg" "${pkgdir}/usr/share/pixmaps/ue5_${_ueminor_us}editor.svg"
```

And the matching restoration lines further down:

```bash
    rm ue5editor.svg
    rm LICENSE
    mv ue5editor.svg.bak ue5editor.svg
```

Replace with:

```bash
    rm "ue5_${_ueminor_us}editor.svg"
    rm LICENSE
    mv "ue5_${_ueminor_us}editor.svg.bak" "ue5_${_ueminor_us}editor.svg"
```

- [ ] **Step 5: Edit launcher install + symlinks**

Find:

```bash
  # Launch script to initialize missing user folders for Unreal Engine
  install -Dm755 ../unreal-engine.sh "${pkgdir}/usr/bin/unreal-engine"
  chmod +x "${pkgdir}/usr/bin/unreal-engine"
  ln -s "${pkgdir}/usr/bin/unreal-engine" "${pkgdir}/usr/bin/ue5"
  ln -s "${pkgdir}/usr/bin/unreal-engine" "${pkgdir}/usr/bin/UE5"
  ln -s "${pkgdir}/usr/bin/unreal-engine" "${pkgdir}/usr/bin/unreal-engine-5"
  chmod 755 "${pkgdir}/usr/bin/ue5" "${pkgdir}/usr/bin/UE5" "${pkgdir}/usr/bin/unreal-engine-5"
```

Replace with:

```bash
  # Launcher (per-minor name avoids collision with other unreal-engine-src-5.X packages)
  install -Dm755 "../{{LAUNCHER_BIN}}.sh" "${pkgdir}/usr/bin/{{LAUNCHER_BIN}}"
  chmod +x "${pkgdir}/usr/bin/{{LAUNCHER_BIN}}"
  # Per-minor short-form symlinks (e.g. ue5.6, UE5.6); no plain ue5/UE5/unreal-engine-5 to avoid cross-minor collisions
  for _link in {{SYMLINKS}}; do
    ln -s "/usr/bin/{{LAUNCHER_BIN}}" "${pkgdir}/usr/bin/${_link}"
    chmod 755 "${pkgdir}/usr/bin/${_link}"
  done
```

- [ ] **Step 6: Edit checksum-stamp sed lines**

Find:

```bash
  DesktopFileChecksum=$(sha256sum "${pkgdir}/usr/share/applications/com.unrealengine.UE5Editor.desktop" | cut -f 1 -d ' ')
  sed -i "s|ChecksumPlaceholder|${DesktopFileChecksum}|" "${pkgdir}/usr/bin/unreal-engine"
  sed -i "s|InstalledLocationPlaceholder|/${UE_INSTALL_DIR}/Engine/Binaries|" "${pkgdir}/usr/bin/unreal-engine"
```

Replace with:

```bash
  DesktopFileChecksum=$(sha256sum "${pkgdir}/usr/share/applications/com.unrealengine.UE5_${_ueminor_us}Editor.desktop" | cut -f 1 -d ' ')
  sed -i "s|ChecksumPlaceholder|${DesktopFileChecksum}|" "${pkgdir}/usr/bin/{{LAUNCHER_BIN}}"
  sed -i "s|InstalledLocationPlaceholder|/${UE_INSTALL_DIR}/Engine/Binaries|" "${pkgdir}/usr/bin/{{LAUNCHER_BIN}}"
```

- [ ] **Step 7: Commit**

```bash
git add PKGBUILD.tmpl
git commit -m "feat(pkgbuild): templatize install-dir, launcher, symlinks, desktop, hook, icon"
```

---

## Phase C — Common asset .tmpl files

### Task 14: Create unreal-engine.sh.tmpl

**Files:**
- Create: `templates/_common/unreal-engine.sh.tmpl`

- [ ] **Step 1: Open the .raw source for reference**

Read `templates/_common/unreal-engine.sh.raw` to see current content (already in repo as uncommitted reference).

- [ ] **Step 2: Write the template**

Write to `templates/_common/unreal-engine.sh.tmpl`:

```bash
#! /usr/bin/bash 

# Launcher for {{PKGNAME}} (Unreal Engine {{MINOR}}).
# Inspired by Alexis Belmonte's upstream unreal-engine.sh.

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: Run this as an unprivileged user; not as root."
    return
fi

if [ -d "${HOME}/.steam/bin" ] && [ ! -L "${HOME}/.steampath" ]; then
    ln -s "${HOME}/.steam/bin" "${HOME}/.steampath"
elif [ ! -d "${HOME}/.steam/bin" ] && [ ! -L "${HOME}/.steampath" ]; then
    mkdir -p "${HOME}/.steam/bin"
    ln -s "${HOME}/.steam/bin" "${HOME}/.steampath"
fi

# Per-minor user-config dir
if [ ! -d "${HOME}/.config/Epic/UnrealEngine/{{MINOR}}/Intermediate/" ]; then
    mkdir -p "${HOME}/.config/Epic/UnrealEngine/{{MINOR}}/Intermediate/"
fi

# Preserve upstream typo path (.cnfig) for compatibility with anything that already wrote there
if [ ! -d "${HOME}/.cnfig/Epic/UnrealEngine/{{MINOR}}/Intermediate/" ]; then
    mkdir -p "${HOME}/.cnfig/Epic/UnrealEngine/{{MINOR}}/Intermediate/"
fi

if [ ! -f "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop" ]; then
    cp "/usr/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop" \
       "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop"
fi

UE5desktopFileChecksum="$(sha256sum "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop" | cut -f 1 -d ' ')"

if [ "${UE5desktopFileChecksum}" == "ChecksumPlaceholder" ]; then
    UE5editorLocation="$(find InstalledLocationPlaceholder -type f -iname 'UnrealEditor')"
    UE5editorPath="$(echo ${UE5editorLocation/UnrealEditor/})"

    sed -i "7c\\Exec=${UE5editorLocation} %F" "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop"
    sed -i "14c\\Path=${UE5editorPath}" "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop"
fi

gio launch "${HOME}/.local/share/applications/com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop"
```

- [ ] **Step 3: Commit**

```bash
git add templates/_common/unreal-engine.sh.tmpl
git commit -m "feat(common): per-minor unreal-engine.sh.tmpl launcher"
```

---

### Task 15: Create com.unrealengine.UE5Editor.desktop.tmpl

**Files:**
- Create: `templates/_common/com.unrealengine.UE5Editor.desktop.tmpl`

- [ ] **Step 1: Write template**

```ini
#!/usr/bin/env xdg-open

[Desktop Entry]
Categories=Development;
Comment[en_US]=Create next-generation video games
Comment=Create next-generation video games
Exec=/usr/bin/{{LAUNCHER_BIN}} %F
GenericName[en_US]=
GenericName=
Icon=ue5_{{MINOR_UNDERSCORE}}editor
MimeType=
Name[en_US]=Unreal Engine {{MINOR}} Editor
Name=Unreal Engine {{MINOR}} Editor
Path=/{{INSTALL_DIR}}/Engine/Binaries/Linux/
StartupNotify=true
Terminal=false
TerminalOptions=
Type=Application
X-DBUS-ServiceName=
X-DBUS-StartupType=
X-KDE-SubstituteUID=false
X-KDE-Username=
```

- [ ] **Step 2: Commit**

```bash
git add templates/_common/com.unrealengine.UE5Editor.desktop.tmpl
git commit -m "feat(common): per-minor desktop entry template"
```

---

### Task 16: Create pacman cache hook template

**Files:**
- Create: `templates/_common/unreal-engine-5-pacman-cache.hook.tmpl`

- [ ] **Step 1: Write template**

```ini
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = {{PKGNAME}}

[Action]
Description = Leaving only one {{PKGNAME}} package in cache to save storage space...
Depends = pacman-contrib
When = PostTransaction
Exec = /bin/sh -c '/usr/bin/paccache -rvk1 {{PKGNAME}}'
```

- [ ] **Step 2: Commit**

```bash
git add templates/_common/unreal-engine-5-pacman-cache.hook.tmpl
git commit -m "feat(common): per-minor pacman cache hook template"
```

---

### Task 17: Remove xfail mark, run renderer tests

**Files:**
- Modify: `tests/test_render.py`

- [ ] **Step 1: Remove the module-level pytestmark**

Delete the line added in Task 7 step 4:

```python
pytestmark = pytest.mark.xfail(reason="templates not yet created; see Phase B", run=True, strict=False)
```

(May need to keep `import pytest` if it's still used elsewhere; otherwise remove.)

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_render.py -v`
Expected: all tests pass (including `test_render_5_6_produces_expected_filenames`, `test_render_5_0_omits_patches_and_renames_assets`, `test_cli_writes_output_directory`).

If any fail: read the diff and fix the template files referenced by the failing assertion. Do not modify the tests.

- [ ] **Step 3: Commit**

```bash
git add tests/test_render.py
git commit -m "test(render): templates now exist, remove xfail mark, all tests green"
```

---

## Phase D — Golden file test for 5.6

### Task 18: Generate + check in golden files for 5.6 render

**Files:**
- Create: `tests/fixtures/expected/5.6/PKGBUILD`
- Create: `tests/fixtures/expected/5.6/.SRCINFO`
- Create: `tests/fixtures/expected/5.6/unreal-engine-5.6.sh`
- Create: `tests/fixtures/expected/5.6/com.unrealengine.UE5_6Editor.desktop`
- Create: `tests/fixtures/expected/5.6/unreal-engine-src-5.6-pacman-cache.hook`
- Create: `tests/test_golden_5_6.py`

- [ ] **Step 1: Generate the rendered output once**

```bash
python render.py 5.6 --pkgver 5.6.1 --template-sha golden --out /tmp/golden-5.6
ls -la /tmp/golden-5.6
```

- [ ] **Step 2: Manually inspect each text file for correctness**

```bash
grep -n 'pkgname\|pkgver\|pkgrel\|_uetag\|INSTALL_DIR' /tmp/golden-5.6/PKGBUILD | head -20
head -10 /tmp/golden-5.6/.SRCINFO
head -5 /tmp/golden-5.6/unreal-engine-5.6.sh
head -10 /tmp/golden-5.6/com.unrealengine.UE5_6Editor.desktop
cat /tmp/golden-5.6/unreal-engine-src-5.6-pacman-cache.hook
```

Expected: `pkgname=unreal-engine-src-5.6`, `pkgver=5.6.1`, `_uetag="${pkgver}-release"`, `INSTALL_DIR="opt/unreal-engine-src-5.6"`, desktop `Exec=/usr/bin/unreal-engine-5.6 %F`, hook `Target = unreal-engine-src-5.6`. If anything is off, fix the template (not the goldens) and re-run step 1.

- [ ] **Step 3: Copy text outputs into fixtures (skip patches + svg — those are byte-identical copies and not worth re-checking)**

```bash
mkdir -p tests/fixtures/expected/5.6
cp /tmp/golden-5.6/PKGBUILD tests/fixtures/expected/5.6/
cp /tmp/golden-5.6/.SRCINFO tests/fixtures/expected/5.6/
cp /tmp/golden-5.6/unreal-engine-5.6.sh tests/fixtures/expected/5.6/
cp /tmp/golden-5.6/com.unrealengine.UE5_6Editor.desktop tests/fixtures/expected/5.6/
cp /tmp/golden-5.6/unreal-engine-src-5.6-pacman-cache.hook tests/fixtures/expected/5.6/
```

- [ ] **Step 4: Write golden file test**

`tests/test_golden_5_6.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from render import render

GOLDEN_FILENAMES = [
    "PKGBUILD",
    ".SRCINFO",
    "unreal-engine-5.6.sh",
    "com.unrealengine.UE5_6Editor.desktop",
    "unreal-engine-src-5.6-pacman-cache.hook",
]


@pytest.mark.parametrize("filename", GOLDEN_FILENAMES)
def test_render_5_6_matches_golden(
    repo_root: Path, filename: str
) -> None:
    rendered = render(
        repo=repo_root,
        minor="5.6",
        pkgver="5.6.1",
        template_sha="golden",
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
```

- [ ] **Step 5: Run the golden test**

Run: `python -m pytest tests/test_golden_5_6.py -v`
Expected: 5 passed (one per golden file).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/expected/5.6 tests/test_golden_5_6.py
git commit -m "test(render): golden-file test for 5.6 full render output"
```

---

## Phase E — Helper scripts + CI

### Task 19: Create scripts/add-minor.sh

**Files:**
- Create: `scripts/add-minor.sh`

- [ ] **Step 1: Write script**

```bash
#!/usr/bin/env bash
# Scaffold templates/<minor>/ for a new UE5 minor version.
# Usage: ./scripts/add-minor.sh 5.7
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <minor>   (e.g. $0 5.7)" >&2
  exit 1
fi

MINOR="$1"
if ! [[ "${MINOR}" =~ ^[0-9]+\.[0-9]+$ ]]; then
  echo "Error: minor must look like X.Y (got: ${MINOR})" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${REPO_ROOT}/templates/${MINOR}"

if [[ -e "${TARGET}" ]]; then
  echo "Error: ${TARGET} already exists" >&2
  exit 1
fi

mkdir -p "${TARGET}/patches"
touch "${TARGET}/patches/.gitkeep"
cat > "${TARGET}/meta.toml" <<EOF
sdk_version_override = ""
pkgrel = 1
patches = []
notes = "Bootstrap stub. No patches verified for ${MINOR} yet; build likely fails until patches are added."
EOF

echo "Scaffolded ${TARGET}"
echo "Next: render to verify with"
echo "  python render.py ${MINOR} --pkgver ${MINOR}.0 --template-sha local --out out/${MINOR}"
```

- [ ] **Step 2: Make executable + test it**

```bash
chmod +x scripts/add-minor.sh
./scripts/add-minor.sh 5.99
ls templates/5.99
cat templates/5.99/meta.toml
rm -rf templates/5.99
```

Expected: dir created with meta.toml + patches/.gitkeep, then cleanly removed.

- [ ] **Step 3: Commit**

```bash
git add scripts/add-minor.sh
git commit -m "feat(scripts): add-minor.sh scaffolds templates/<minor>/"
```

---

### Task 20: Create pytest CI workflow

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Write workflow**

```yaml
name: tests

on:
  push:
    branches: [master]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dev deps
        run: pip install -e ".[dev]"
      - name: Run pytest
        run: python -m pytest -v
```

- [ ] **Step 2: Remove .gitkeep + commit**

```bash
git rm .github/workflows/.gitkeep
git add .github/workflows/test.yml
git commit -m "ci: run pytest on push and PR"
```

---

### Task 21: Create render-check CI workflow

**Files:**
- Create: `.github/workflows/render-check.yml`

- [ ] **Step 1: Write workflow**

```yaml
name: render-check

on:
  push:
    branches: [master]
  pull_request:

jobs:
  render-all-minors:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        minor: ["5.0", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Render minor ${{ matrix.minor }}
        run: |
          python render.py "${{ matrix.minor }}" \
            --pkgver "${{ matrix.minor }}.0" \
            --template-sha "ci" \
            --out "out/${{ matrix.minor }}"
      - name: Upload rendered package
        uses: actions/upload-artifact@v4
        with:
          name: rendered-${{ matrix.minor }}
          path: out/${{ matrix.minor }}

  namcap:
    needs: render-all-minors
    runs-on: ubuntu-latest
    container: archlinux:latest
    steps:
      - uses: actions/checkout@v4
      - name: Install namcap + python
        run: pacman -Sy --noconfirm namcap python
      - name: Render 5.6 (only minor with patches)
        run: python render.py 5.6 --pkgver 5.6.1 --template-sha ci --out out/5.6
      - name: Run namcap
        working-directory: out/5.6
        run: namcap PKGBUILD || true   # warnings tolerated; failures surface in log
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/render-check.yml
git commit -m "ci: render every minor + namcap-lint 5.6 PKGBUILD"
```

---

## Phase F — n8n workflow rewrite

All `mcp__claude_ai_n8n__*` tools need ToolSearch loaded first. Workflow ID: `3JYJn2KCJvPUxA0k`. DataTable ID: `GrWfNL8VhYWMKfWI`.

### Task 22: Add template_sha column to DataTable

**Files:**
- (n8n) DataTable `ue5_aur_state`

- [ ] **Step 1: Load tool schemas**

Call: `ToolSearch` with query `"select:add_data_table_column,get_sdk_reference,get_node_types,search_nodes,get_workflow_details,update_workflow,validate_workflow,test_workflow,prepare_test_pin_data,get_suggested_nodes"` max_results 10.

- [ ] **Step 2: Add the column**

Call: `mcp__claude_ai_n8n__add_data_table_column` with `dataTableId="GrWfNL8VhYWMKfWI"`, `name="template_sha"`, `type="string"`.

Expected: column appears. If it already exists: confirm via `search_data_tables` and skip.

- [ ] **Step 3: Verify**

Call: `mcp__claude_ai_n8n__search_data_tables` with `query="ue5_aur_state"`. Confirm `template_sha` column is present in the response.

- [ ] **Step 4: No commit** (n8n state change, no repo files)

---

### Task 23: Read current workflow + SDK reference

**Files:**
- (n8n read-only)

- [ ] **Step 1: Fetch SDK reference**

Call: `mcp__claude_ai_n8n__get_sdk_reference` with `sections=["overview","guidelines","design"]`.

- [ ] **Step 2: Fetch current workflow**

Call: `mcp__claude_ai_n8n__get_workflow_details` with `workflowId="3JYJn2KCJvPUxA0k"`.

- [ ] **Step 3: List node types you intend to use**

Call: `mcp__claude_ai_n8n__get_node_types` with the list of node type IDs already in the workflow (Schedule Trigger, GitHub, Code, DataTable, SplitInBatches, ExecuteCommand, Set) — copy the exact IDs from the workflow detail.

- [ ] **Step 4: No commit** — research-only step. Read the responses; they're the basis for Task 24.

---

### Task 24: Rewrite "Pick Latest Per Minor" Code node (node 3)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, node `Pick Latest Per Minor`

- [ ] **Step 1: Construct new code**

The node receives release objects from the GitHub node. Each has a `tag_name` like `5.6.1-release`. Output one item per minor.

JavaScript for the Code node body:

```javascript
const RE = /^(\d+)\.(\d+)\.(\d+)-release$/;
const byMinor = new Map();
for (const item of $input.all()) {
  const tag = item.json?.tag_name;
  if (typeof tag !== 'string') continue;
  const m = RE.exec(tag);
  if (!m) continue;
  const major = parseInt(m[1], 10);
  const minor = parseInt(m[2], 10);
  const patch = parseInt(m[3], 10);
  if (major !== 5) continue;
  const key = `${major}.${minor}`;
  const prev = byMinor.get(key);
  if (!prev || patch > prev.patch) {
    byMinor.set(key, {
      minor: key,
      pkgver: `${major}.${minor}.${patch}`,
      tag,
      patch,
    });
  }
}
return Array.from(byMinor.values())
  .sort((a, b) => a.minor.localeCompare(b.minor, undefined, { numeric: true }))
  .map((v) => ({ json: { minor: v.minor, pkgver: v.pkgver, tag: v.tag } }));
```

- [ ] **Step 2: Update the node via update_workflow**

Call `mcp__claude_ai_n8n__update_workflow` with the workflow code reflecting only this node's `jsCode` change. Use the SDK source pattern from the reference.

- [ ] **Step 3: Validate**

Call `mcp__claude_ai_n8n__validate_workflow` with the updated code.

Expected: valid.

- [ ] **Step 4: No git commit** (n8n change). Optionally add a one-line summary to a CHANGELOG file later (out of scope here).

---

### Task 25: Add "Clone Template Repo" Execute Command node (node 6)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, new node before "Render PKGBUILD"

- [ ] **Step 1: Define the node**

Node type: `n8n-nodes-base.executeCommand` (confirm exact ID from `get_node_types`).

Command:

```bash
set -euo pipefail
WORK=$(mktemp -d)
cd "$WORK"
git clone --depth=1 https://github.com/FinleyLaempe/aur-unreal-engine-src.git tpl
SHA=$(git -C tpl rev-parse HEAD)
echo "$WORK"  > /tmp/n8n-tpl-path.txt
echo "$SHA"   > /tmp/n8n-tpl-sha.txt
echo "{\"tpl_path\": \"$WORK/tpl\", \"tpl_sha\": \"$SHA\"}"
```

Parse the JSON line from stdout and emit `{ tpl_path, tpl_sha }` for downstream nodes. (n8n's ExecuteCommand emits stdout as `stdout` field; a Code node can run `JSON.parse(items[0].json.stdout.trim().split('\n').pop())`.)

- [ ] **Step 2: Insert the node into the workflow**

Use `update_workflow` to add this node between `Decide If Update Needed` and `Render PKGBUILD and SRCINFO`. Connect dataflow so each downstream item carries `tpl_path` + `tpl_sha`.

- [ ] **Step 3: Validate**

Call `validate_workflow`. Fix errors.

- [ ] **Step 4: No git commit**

---

### Task 26: Rewrite "Decide If Update Needed" Code node (node 5)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, node `Decide If Update Needed`

- [ ] **Step 1: Construct logic**

This node receives one item per minor with `{minor, pkgver, tag, stored_last_version, stored_pkgrel, stored_template_sha}` (joined from node 3 + node 4 DataTable lookup). The template SHA from node 6 is read via cross-node reference `$('Clone Template Repo').first().json.tpl_sha` rather than threading it through the dataflow.

```javascript
const tpl_sha = $('Clone Template Repo').first().json.tpl_sha;
const tpl_path = $('Clone Template Repo').first().json.tpl_path;

return $input.all()
  .map((item) => {
    const j = item.json;
    const pkgname = `unreal-engine-src-${j.minor}`;
    const stored_ver = j.stored_last_version ?? null;
    const stored_pkgrel = j.stored_pkgrel ?? 0;
    const stored_sha = j.stored_template_sha ?? null;

    let should_publish = false;
    let new_pkgrel = 1;
    if (stored_ver === null) {
      should_publish = true;
      new_pkgrel = 1;
    } else if (j.pkgver !== stored_ver) {
      should_publish = true;
      new_pkgrel = 1;
    } else if (stored_sha !== tpl_sha) {
      should_publish = true;
      new_pkgrel = stored_pkgrel + 1;
    }
    return {
      json: {
        ...j,
        pkgbase: pkgname,
        pkgname,
        tpl_sha,
        tpl_path,
        should_publish,
        new_pkgrel,
        new_template_sha: tpl_sha,
      },
    };
  })
  .filter((item) => item.json.should_publish);
```

If `$('Clone Template Repo').first()` returns undefined when the Decide node runs (n8n executes per-branch), wire node 6's output as an extra connection into the Decide node so the reference resolves. Confirm via test run; fix wiring if needed.

- [ ] **Step 2: Update + validate**

`update_workflow` → `validate_workflow`. Fix any errors.

- [ ] **Step 3: No commit**

---

### Task 27: Rewrite "Render PKGBUILD and SRCINFO" Code node (node 7)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, node `Render PKGBUILD and SRCINFO`

- [ ] **Step 1: Port Python render.py logic to JavaScript**

Inside the Code node, implement the same render logic as `render.py`. Inputs per item: `{ minor, pkgver, pkgbase, pkgname, new_pkgrel, new_template_sha, tpl_path }`. Read template files via `fs` (Node.js available in n8n Code nodes when `Run Once for All Items` is off).

Skeleton (full implementation expected — match `render.py` byte-for-byte):

```javascript
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const TOKEN_RE = /\{\{([A-Z][A-Z0-9_]*)\}\}/g;
const MINOR_RE = /^(\d+)\.(\d+)$/;

function sha256Hex(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

function substitute(template, values) {
  return template.replace(TOKEN_RE, (_, token) => {
    if (!(token in values)) throw new Error(`unsubstituted token: {{${token}}}`);
    return values[token];
  });
}

function loadMinorMeta(minorDir) {
  // Trivial TOML subset parser tailored to our meta.toml shape.
  const text = fs.readFileSync(path.join(minorDir, 'meta.toml'), 'utf8');
  const out = { sdk_version_override: '', pkgrel: 1, patches: [], notes: '' };
  let inPatches = false;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (inPatches) {
      if (line === ']') { inPatches = false; continue; }
      const m = /^"([^"]+)"\s*,?$/.exec(line);
      if (m) out.patches.push(m[1]);
      continue;
    }
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    const val = line.slice(eq + 1).trim();
    if (key === 'patches') {
      if (val === '[]') { out.patches = []; continue; }
      if (val.startsWith('[')) {
        const inline = val.slice(1, val.endsWith(']') ? -1 : undefined);
        for (const m of inline.matchAll(/"([^"]+)"/g)) out.patches.push(m[1]);
        if (!val.endsWith(']')) inPatches = true;
      }
    } else if (key === 'pkgrel') {
      out.pkgrel = parseInt(val, 10);
    } else if (key === 'sdk_version_override' || key === 'notes') {
      out[key] = val.replace(/^"(.*)"$/, '$1');
    }
  }
  return out;
}

function deriveValues({ minor, pkgver, pkgrel, sdkOverride }) {
  if (!MINOR_RE.test(minor)) throw new Error(`invalid minor: ${minor}`);
  const minorUs = minor.replace('.', '_');
  const pkgname = `unreal-engine-src-${minor}`;
  return {
    PKGNAME: pkgname,
    MINOR: minor,
    MINOR_UNDERSCORE: minorUs,
    PKGVER: pkgver,
    PKGREL: String(pkgrel),
    SDK_VERSION_OVERRIDE: sdkOverride,
    INSTALL_DIR: `opt/${pkgname}`,
    LAUNCHER_BIN: `unreal-engine-${minor}`,
    SYMLINKS: `ue${minor} UE${minor}`,
  };
}

function buildSrcinfo({ pkgname, pkgver, pkgrel, sources, hashes }) {
  // Mirrors generate_srcinfo() in render.py
  const lines = [`pkgbase = ${pkgname}`];
  lines.push(`\tpkgdesc = A 3D game engine by Epic Games which can be used non-commercially for free.`);
  lines.push(`\tpkgver = ${pkgver}`);
  lines.push(`\tpkgrel = ${pkgrel}`);
  lines.push(`\turl = https://www.unrealengine.com/`);
  for (const a of ['x86_64','x86_64_v2','x86_64_v3','x86_64_v4','aarch64']) lines.push(`\tarch = ${a}`);
  for (const l of ['custom:UnrealEngine','GPL3']) lines.push(`\tlicense = ${l}`);
  for (const d of ['git','openssh','sed','grep','glibc','wget','rsync']) lines.push(`\tmakedepends = ${d}`);
  for (const d of ['sdl3','python','dotnet-runtime','dotnet-sdk','vulkan-icd-loader','lld','xdg-user-dirs','dos2unix','openssl','steam','coreutils','findutils']) lines.push(`\tdepends = ${d}`);
  for (const o of [
    'polly: for potentially increased performance',
    'qt5-base: qmake build system for projects',
    'cmake: build system for projects',
    'qtcreator: IDE for projects',
    'codelite: IDE for projects',
    'kdevelop: IDE for projects',
    'clion: IDE for projects',
    'rider: IDE for projects',
    'code: IDE for projects',
    'pacman-contrib: for the paccache cleaning hook',
    'fake-ms-fonts: Font support for "demo/free/sample/example/tutorial" projects',
    'ttf-ms-fonts: Font support for "demo/free/sample/example/tutorial" projects',
  ]) lines.push(`\toptdepends = ${o}`);
  for (const o of ['!strip','staticlibs']) lines.push(`\toptions = ${o}`);
  for (const s of sources) lines.push(`\tsource = ${s}`);
  for (const h of hashes) lines.push(`\tsha256sums = ${h}`);
  lines.push('');
  lines.push(`pkgname = ${pkgname}`);
  return lines.join('\n') + '\n';
}

return $input.all().map((item) => {
  const { minor, pkgver, new_pkgrel, new_template_sha, tpl_path, pkgname } = item.json;
  const minorDir = path.join(tpl_path, 'templates', minor);
  const commonDir = path.join(tpl_path, 'templates', '_common');
  const meta = loadMinorMeta(minorDir);
  const values = deriveValues({ minor, pkgver, pkgrel: new_pkgrel, sdkOverride: meta.sdk_version_override });

  const launcherName = `${values.LAUNCHER_BIN}.sh`;
  const desktopName = `com.unrealengine.UE5_${values.MINOR_UNDERSCORE}Editor.desktop`;
  const hookName = `${values.PKGNAME}-pacman-cache.hook`;
  const iconName = `ue5_${values.MINOR_UNDERSCORE}editor.svg`;

  const files = {};
  files[launcherName] = Buffer.from(substitute(fs.readFileSync(path.join(commonDir, 'unreal-engine.sh.tmpl'), 'utf8'), values), 'utf8');
  files[desktopName] = Buffer.from(substitute(fs.readFileSync(path.join(commonDir, 'com.unrealengine.UE5Editor.desktop.tmpl'), 'utf8'), values), 'utf8');
  files[hookName] = Buffer.from(substitute(fs.readFileSync(path.join(commonDir, 'unreal-engine-5-pacman-cache.hook.tmpl'), 'utf8'), values), 'utf8');
  files[iconName] = fs.readFileSync(path.join(commonDir, 'ue5editor.svg'));

  const patchFilenames = [];
  for (const p of meta.patches) {
    files[p] = fs.readFileSync(path.join(minorDir, 'patches', p));
    patchFilenames.push(p);
  }

  const ordered = [
    [launcherName, files[launcherName]],
    [desktopName, files[desktopName]],
    ...patchFilenames.map((p) => [p, files[p]]),
    [hookName, files[hookName]],
    [iconName, files[iconName]],
  ];
  values.PATCH_SOURCES = ordered.map(([n]) => `'${n}'`).join('\n        ');
  values.NON_TOOLCHAIN_SHA256_LIST = ordered.map(([_, c]) => `'${sha256Hex(c)}'`).join('\n            ');

  const pkgbuildTmpl = fs.readFileSync(path.join(tpl_path, 'PKGBUILD.tmpl'), 'utf8');
  files['PKGBUILD'] = Buffer.from(substitute(pkgbuildTmpl, values), 'utf8');
  files['.SRCINFO'] = Buffer.from(buildSrcinfo({
    pkgname: values.PKGNAME,
    pkgver,
    pkgrel: new_pkgrel,
    sources: ordered.map(([n]) => n),
    hashes: ordered.map(([_, c]) => sha256Hex(c)),
  }), 'utf8');

  const filesB64 = {};
  for (const [name, content] of Object.entries(files)) {
    filesB64[name] = content.toString('base64');
  }
  return { json: { ...item.json, files_b64: filesB64 } };
});
```

- [ ] **Step 2: Update + validate workflow**

`update_workflow` → `validate_workflow`. Fix errors.

- [ ] **Step 3: Cross-validate against Python golden output**

Trigger the workflow manually with DRY_RUN=true (Task 30 prerequisite) and capture node 7 output. For minor 5.6, decode `files_b64['PKGBUILD']` and diff against `tests/fixtures/expected/5.6/PKGBUILD`. Must be byte-identical. If not, fix the JS port until it matches the Python golden.

- [ ] **Step 4: No git commit**

---

### Task 28: Rewrite "Push to AUR" Execute Command node (node 9)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, node `Push to AUR`

- [ ] **Step 1: Construct command**

Build command dynamically from the rendered `files_b64` map. n8n Code node should pre-build the command string; ExecuteCommand just runs it.

In a Code node (or expression on the ExecuteCommand) build:

```javascript
const item = $input.first().json;
const dryRun = ($workflow.staticData?.global?.DRY_RUN ?? 'false') === 'true';
const lines = [
  'set -euo pipefail',
];
if (dryRun) {
  lines.push(`echo "[DRY_RUN] would push ${item.pkgname}-${item.pkgver}-${item.new_pkgrel}"`);
  lines.push('echo "Files:"');
  for (const n of Object.keys(item.files_b64)) lines.push(`echo "  ${n}"`);
  lines.push('exit 0');
}
lines.push(
  'cd "$WORK"',
  `git clone "ssh://aur@aur.archlinux.org/${item.pkgname}.git" repo 2>/dev/null || { mkdir repo && cd repo && git init -b master && git remote add origin "ssh://aur@aur.archlinux.org/${item.pkgname}.git" && cd ..; }`,
  'cd repo',
);
for (const [name, b64] of Object.entries(item.files_b64)) {
  lines.push(`base64 -d > '${name}' <<'B64_EOF'`);
  lines.push(b64);
  lines.push('B64_EOF');
}
lines.push('git add -A');
lines.push(`git -c user.email="bot@filela.de" -c user.name="UE5 AUR Bot" commit -m "Update to ${item.pkgver}-${item.new_pkgrel}" || { echo "nothing to commit"; exit 0; }`);
lines.push('git push origin HEAD:master');
return [{ json: { ...item, push_cmd: lines.join('\n') } }];
```

ExecuteCommand node `command` field: `={{ $json.push_cmd }}`.

- [ ] **Step 2: Update + validate**

`update_workflow` → `validate_workflow`.

- [ ] **Step 3: No git commit**

---

### Task 29: Update "Save New Version" DataTable upsert node (node 10)

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`, node `Save New Version`

- [ ] **Step 1: Update column mapping**

The upsert now writes `template_sha = new_template_sha` in addition to existing columns. Mapping:

```
columns:
  pkgbase:        ={{ $json.pkgbase }}
  minor:          ={{ $json.minor }}
  last_version:   ={{ $json.pkgver }}
  pkgrel:         ={{ $json.new_pkgrel }}
  template_sha:   ={{ $json.new_template_sha }}
  updated_at:     ={{ $now.toISO() }}
matchType: allConditions
match:
  pkgbase: ={{ $json.pkgbase }}
```

- [ ] **Step 2: Update + validate**

`update_workflow` → `validate_workflow`.

- [ ] **Step 3: No git commit**

---

### Task 30: Add DRY_RUN workflow variable + end-to-end dry-run test

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k` — workflow settings / static data

- [ ] **Step 1: Add DRY_RUN to workflow static data**

In n8n UI (or via workflow `staticData`): set `DRY_RUN=true`. The Push to AUR command reads this; when true, it logs and exits before any AUR mutation.

- [ ] **Step 2: Pin test data**

Call: `mcp__claude_ai_n8n__prepare_test_pin_data` with `workflowId="3JYJn2KCJvPUxA0k"`. Pin a known GitHub releases response so the workflow is deterministic during testing.

- [ ] **Step 3: Trigger test execution**

Call: `mcp__claude_ai_n8n__test_workflow` with `workflowId="3JYJn2KCJvPUxA0k"`.

Expected: Each minor row shows `should_publish=true` (first run), each push node logs `[DRY_RUN] would push ...`, DataTable rows created with version + template_sha. Confirm via `search_data_tables`.

- [ ] **Step 4: Second trigger should be a no-op**

Trigger again. Expected: zero `should_publish=true`, zero push log lines, DataTable unchanged.

- [ ] **Step 5: No git commit** — n8n state only.

---

### Task 31: Publish the workflow

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`

- [ ] **Step 1: Publish**

Call: `mcp__claude_ai_n8n__publish_workflow` with `workflowId="3JYJn2KCJvPUxA0k"`.

- [ ] **Step 2: Confirm**

Call: `mcp__claude_ai_n8n__get_workflow_details` with `workflowId="3JYJn2KCJvPUxA0k"`. Confirm `active=true` and the scheduled trigger is armed.

- [ ] **Step 3: No git commit**

---

## Phase G — Production rollout

### Task 32: Push template repo to GitHub

**Files:**
- Remote: `git@github.com:FinleyLaempe/aur-unreal-engine-src.git`

- [ ] **Step 1: User-side prerequisite — create GitHub repo**

This step is performed by Finley in the GitHub web UI (or via `gh repo create`):

```bash
gh repo create FinleyLaempe/aur-unreal-engine-src --public \
  --description "Per-minor AUR PKGBUILD templates for UE5 source builds"
```

- [ ] **Step 2: Push local commits**

```bash
git push -u origin master
```

Expected: all commits from Phases A–E pushed to the new GitHub repo.

- [ ] **Step 3: Verify CI runs**

Check the Actions tab on GitHub. Both `tests` and `render-check` workflows should run on the push and pass.

- [ ] **Step 4: No additional commit** — already pushed.

---

### Task 33: Flip DRY_RUN=false + manual first publish

**Files:**
- (n8n) workflow `3JYJn2KCJvPUxA0k`

- [ ] **Step 1: Set DRY_RUN=false in workflow static data**

- [ ] **Step 2: Trigger manually**

Use the manual trigger button on the Daily Check / Schedule Trigger node.

- [ ] **Step 3: Watch execution**

Each minor 5.0–5.<latest> should:
- Be a fresh `should_publish=true`
- Push to its corresponding AUR repo (auto-created on first push)
- Update DataTable

Expected: per-minor AUR repos visible at `https://aur.archlinux.org/packages/unreal-engine-src-5.X`.

- [ ] **Step 4: If a push fails:** check node 11 (Record Failure) output. Common causes:
  - AUR pre-receive hook complains about PKGBUILD validity → fix `PKGBUILD.tmpl`, push template repo, re-trigger workflow.
  - SSH key not in n8n container's ssh-agent → fix credential setup.
  - Network egress to `ssh.aur.archlinux.org:22` blocked → fix container networking.

State NOT updated on failure (handled by node 11 wiring); next cycle retries automatically.

- [ ] **Step 5: No git commit**

---

### Task 34: Smoke-build at least minor 5.6 locally

**Files:**
- Local: `~/aur-build/unreal-engine-src-5.6/`

- [ ] **Step 1: Clone the published AUR repo**

```bash
mkdir -p ~/aur-build && cd ~/aur-build
git clone ssh://aur@aur.archlinux.org/unreal-engine-src-5.6.git
cd unreal-engine-src-5.6
```

- [ ] **Step 2: Run makepkg --skipinteg -do (no full build, just prepare())**

```bash
makepkg --skipinteg -do
```

Expected:
- Clone fallback probes SSH then HTTPS (uses your local credentials)
- SDK_VERSION parsed from cloned UE5 repo and toolchain downloaded
- Patches applied (5.6.x patches may emit warnings but should not abort)
- Setup.sh runs to completion
- No errors before BuildThirdParty.sh

- [ ] **Step 3: Full build (optional, multi-hour)**

```bash
makepkg --skipinteg -si
```

Expected: package installs to `/opt/unreal-engine-src-5.6/`, binary `/usr/bin/unreal-engine-5.6` works, desktop entry appears in app menu as "Unreal Engine 5.6 Editor", icon `ue5_6editor` shown.

- [ ] **Step 4: No git commit**

---

### Task 35: Document build status per minor + update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add status table to README.md**

After the existing layout section, add:

```markdown
## Build status (verified manually)

| Minor | Patches | Build verified | Notes |
|-------|---------|----------------|-------|
| 5.0   | none    | no             | Bootstrap stub; needs patches |
| 5.1   | none    | no             | Bootstrap stub; needs patches |
| 5.2   | none    | no             | Bootstrap stub; needs patches |
| 5.3   | none    | no             | Bootstrap stub; needs patches |
| 5.4   | none    | no             | Bootstrap stub; needs patches |
| 5.5   | none    | no             | Bootstrap stub; needs patches |
| 5.6   | 0001, 0002 | yes (5.6.1) | Inherited Belmonte patches |
```

Adjust the "yes/no" entries based on Task 34's outcome.

- [ ] **Step 2: Commit + push**

```bash
git add README.md
git commit -m "docs: add per-minor build status table"
git push
```

---

## Self-review

After completing every task, run:

```bash
python -m pytest -v && \
  echo "All tests green" && \
  git log --oneline | head -40
```

Confirm:
- All Python tests pass, including the 5.6 golden file test
- Every commit in the log corresponds to a task in this plan (no orphan commits)
- `git status` is clean
- The `.raw` / `.upstream` files in `templates/` are still untracked (sanity: `git ls-files | grep -E '\.(raw|upstream)$'` returns nothing)

If any of the above fails, return to the corresponding task and fix.

---

## Out of scope (do NOT implement under this plan)

- Notification channel for failures (Discord webhook, email) — deferred to v2
- DataTable backup / restore strategy — deferred to v2
- AUR comment auto-response — out of scope
- Per-minor build matrix automation in CI (the GH-hosted runners can't reasonably build UE5; rely on Task 34 manual verification)
- Cross-minor patch backport tooling — manual per minor as needed
