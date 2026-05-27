# UE5 → AUR Publisher Design

**Date:** 2026-05-28
**Owner:** Finley Laempe
**Status:** Approved

## Goal

Auto-publish per-minor AUR packages of Unreal Engine 5 source builds. One AUR repo per minor version (`unreal-engine-src-5.0`, `unreal-engine-src-5.1`, ..., `unreal-engine-src-5.<latest>`), allowing parallel installs at `/opt/unreal-engine-src-5.X/` so developers locked to a specific minor can each install what they need.

When Epic ships a new patch release on `EpicGames/UnrealEngine` (e.g. `5.6.2-release`), the corresponding AUR package bumps and republishes automatically. New minor versions (`5.7.0-release`) trigger creation of a new AUR repo without manual intervention.

## Non-goals

- GUI for managing minors (use git PRs against template repo)
- Automated patch generation / rebasing across minors (manual per minor)
- Notification system for failures (deferred to v2)
- AUR comment auto-response
- Multi-arch test matrix
- Caching toolchain tarballs across minors
- Replacing or competing with Alexis Belmonte's upstream `unreal-engine` AUR package; this is a per-minor parallel-install variant that credits inspiration in its PKGBUILD header

## Architecture

Three components.

### 1. Template repo

`FinleyLaempe/aur-unreal-engine-src` on GitHub. **Public.** Holds packaging logic. No write access from n8n.

```
aur-unreal-engine-src/
├── README.md
├── PKGBUILD.tmpl
├── templates/
│   ├── _common/
│   │   ├── unreal-engine.sh.tmpl
│   │   ├── com.unrealengine.UE5Editor.desktop.tmpl
│   │   ├── ue5editor.svg
│   │   └── unreal-engine-5-pacman-cache.hook.tmpl
│   ├── 5.0/
│   │   ├── meta.toml
│   │   └── patches/
│   ├── 5.1/...
│   └── 5.6/
│       ├── meta.toml
│       └── patches/
│           ├── 0001-override-shared-target-build.patch
│           └── 0002-suppress-scriptbuild-warnings-for-5-6.patch
├── scripts/
│   ├── render.py            # local renderer mirroring n8n logic
│   └── add-minor.sh         # scaffolds templates/5.X/
└── .github/workflows/
    └── render-check.yml     # renders every minor + namcap-lints
```

Finley pushes template changes manually. n8n only clones (anonymous).

### 2. n8n workflow

Reuse existing workflow ID `3JYJn2KCJvPUxA0k` on `n8n.filela.de`. Keep 11-node skeleton; rewrite Code nodes.

### 3. AUR repos

`unreal-engine-src-5.0` … `unreal-engine-src-5.<latest>`. Auto-created on first push to `ssh://aur@aur.archlinux.org/<pkgname>.git`. Each receives templated PKGBUILD, `.SRCINFO`, per-minor patches, shared assets.

## Data flow

```
EpicGames GH releases (bot PAT, read)
        │
        ▼
n8n: pick latest X.Y.Z-release per minor
        │
        ▼
DataTable ue5_aur_state: stored last_version + template_sha per pkgbase
        │
        ▼ (diff)
changed minors → anonymous clone of template repo
        │
        ▼
render PKGBUILD.tmpl + _common/*.tmpl per minor
        │
        ▼
hand-roll .SRCINFO from rendered PKGBUILD
        │
        ▼
git push ssh://aur@aur.archlinux.org/unreal-engine-src-5.X
        │
        ▼
DataTable upsert (pkgver, pkgrel, updated_at, template_sha)
```

## Placeholder schema

Substituted in all `.tmpl` files.

| Token | Example | Used in |
|-------|---------|---------|
| `{{PKGNAME}}` | `unreal-engine-src-5.6` | PKGBUILD, hook, launcher |
| `{{MINOR}}` | `5.6` | PKGBUILD, paths, launcher |
| `{{MINOR_UNDERSCORE}}` | `5_6` | desktop filename, icon filename |
| `{{PKGVER}}` | `5.6.1` | PKGBUILD |
| `{{PKGREL}}` | `1` | PKGBUILD (from meta.toml + state) |
| `{{SDK_VERSION_OVERRIDE}}` | `""` or e.g. `native-linux-v26_clang-20.1.8-rockylinux8` | PKGBUILD (empty = parse at build) |
| `{{INSTALL_DIR}}` | `opt/unreal-engine-src-5.6` | PKGBUILD, launcher, desktop |
| `{{LAUNCHER_BIN}}` | `unreal-engine-5.6` | symlinks, desktop Exec |
| `{{SYMLINKS}}` | `ue5.6 UE5.6` | space-separated, per minor |
| `{{PATCH_SOURCES}}` | quoted filenames list | PKGBUILD `source=()` |
| `{{NON_TOOLCHAIN_SHA256_LIST}}` | hex hashes, matching order | PKGBUILD `sha256sums=()` |

### `meta.toml` per minor

```toml
sdk_version_override = ""       # empty = parse from cloned UE5 repo at build
pkgrel = 1
patches = [
  "0001-override-shared-target-build.patch",
  "0002-suppress-scriptbuild-warnings-for-5-6.patch",
]
notes = "5.6.x patches; verified against 5.6.1-release"
```

## n8n workflow nodes

| # | Node | Type | Responsibility |
|---|------|------|----------------|
| 1 | Daily Check | Schedule Trigger | Existing. `daysInterval: 1`, `triggerAtHour: 6`. |
| 2 | Fetch UE5 Releases | GitHub list-releases | `EpicGames/UnrealEngine`, paginate up to ~100 latest. Needs bot PAT (existing classic PAT, `repo` scope). |
| 3 | Pick Latest Per Minor | Code | Filter tags `/^(\d+)\.(\d+)\.(\d+)-release$/`. Group by `5.X`. Keep highest `Z` per group. Emit `[{minor, pkgver, tag}, ...]` covering all 5.0–5.<latest>. |
| 4 | Lookup Stored Version | DataTable search | Per minor, query `ue5_aur_state` where `minor == X.Y`. |
| 5 | Decide If Update Needed | Code | Compare `pkgver` vs `last_version` and `template_sha` (from node 6) vs stored. Cases: row absent → `should_publish=true`, `new_pkgrel=1`, `new_template_sha=<node 6 SHA>`. `pkgver` newer → `should_publish=true`, `new_pkgrel=1`. `pkgver` same + `template_sha` differs → `should_publish=true`, `new_pkgrel=<stored+1>`. Else skip. |
| 6 | Clone Template Repo | Execute Command | `git clone --depth=1 https://github.com/FinleyLaempe/aur-unreal-engine-src.git /tmp/tpl-<runId>`. Capture commit SHA. |
| 7 | Render PKGBUILD + Assets | Code | For each `should_publish` item: load `templates/5.X/meta.toml`, `PKGBUILD.tmpl`, `templates/_common/*.tmpl`, patches. Substitute placeholders. Compute sha256 for each rendered non-toolchain source file. Inject `{{PATCH_SOURCES}}` + `{{NON_TOOLCHAIN_SHA256_LIST}}`. Hand-roll `.SRCINFO`. Emit `{minor, pkgname, pkgver, pkgrel, files: {filename: base64-content}}`. |
| 8 | Per Package | SplitInBatches | Iterate per minor sequentially. Existing. |
| 9 | Push to AUR | Execute Command | See "Push command" below. On error → Record Failure. |
| 10 | Save New Version | DataTable upsert | Match on `pkgbase`. Set `minor`, `last_version`, `pkgrel`, `updated_at`, `template_sha`. |
| 11 | Record Failure | Set | Existing. Captures stderr + minor for review. State NOT updated → automatic retry on next cycle. |

### DataTable schema change

Add column `template_sha` (string) to `ue5_aur_state` (id `GrWfNL8VhYWMKfWI`). Existing columns: `pkgbase`, `minor`, `last_version`, `pkgrel`, `updated_at`.

### Push command (node 9)

```bash
set -euo pipefail
WORK=$(mktemp -d)
cd "$WORK"

git clone "ssh://aur@aur.archlinux.org/{{PKGNAME}}.git" repo 2>/dev/null || {
  # First push: AUR repo not yet created, init locally
  mkdir repo && cd repo && git init -b master
  git remote add origin "ssh://aur@aur.archlinux.org/{{PKGNAME}}.git"
  cd ..
}
cd repo

# Write each file from base64-encoded payload (avoids shell-quoting issues for arbitrary file content).
# The n8n Code node emits one heredoc block per file from the `files: {filename: base64-content}` map:
#   cat > '<filename>' <<'B64_EOF' | base64 -d > '<filename>'
#   <base64-content>
#   B64_EOF
# All file writes are inline-generated here at render time and concatenated into this command.

git add -A
git -c user.email="bot@filela.de" -c user.name="UE5 AUR Bot" \
  commit -m "Update to {{PKGVER}}-{{PKGREL}}" || { echo "nothing to commit"; exit 0; }
git push origin HEAD:master
```

n8n container must have: `git`, `openssh-client`, `curl`, AUR SSH key in ssh-agent, egress to `ssh.aur.archlinux.org:22`.

## PKGBUILD.tmpl detail

Derived from upstream PKGBUILD (Alexis Belmonte's, currently 5.6.1). Preserves all build logic. Only diffs what must vary per minor.

### Header

```bash
# Inspired by Alexis Belmonte's <alexbelm48@gmail.com> upstream `unreal-engine` AUR
# Per-minor parallel-install variant. Templates auto-published from:
#   https://github.com/FinleyLaempe/aur-unreal-engine-src
# Maintainer: Finley Laempe <finley.laempe@web.de>

pkgname={{PKGNAME}}
pkgver={{PKGVER}}
pkgrel={{PKGREL}}
_uetag="${pkgver}-release"
_ueminor="{{MINOR}}"
_ueminor_us="{{MINOR_UNDERSCORE}}"
_ue_sdk_override="{{SDK_VERSION_OVERRIDE}}"
```

### Install dir / launcher / symlinks

```bash
if [[ "${UE_INSTALL_DIR}" == "" ]]; then
  export UE_INSTALL_DIR="{{INSTALL_DIR}}"
fi

install -Dm755 ../unreal-engine.sh "${pkgdir}/usr/bin/{{LAUNCHER_BIN}}"
for _link in {{SYMLINKS}}; do
  ln -s "/usr/bin/{{LAUNCHER_BIN}}" "${pkgdir}/usr/bin/${_link}"
done
```

Per-minor `{{SYMLINKS}}` = `ue5.6 UE5.6` (or analogous). No `ue5`/`UE5`/`unreal-engine-5` symlinks because they collide between minors.

### Desktop file

- Filename: `com.unrealengine.UE5_{{MINOR_UNDERSCORE}}Editor.desktop`
- `Name=Unreal Engine {{MINOR}} Editor`
- `Exec=/usr/bin/{{LAUNCHER_BIN}} %U`

### Pacman hook

- Filename: `{{PKGNAME}}-pacman-cache.hook`
- `Target = {{PKGNAME}}`

### Icon

- Filename: `ue5_{{MINOR_UNDERSCORE}}editor.svg` (avoid pixmap collision between packages)

### Clone fallback (replaces upstream prepare() lines 248–253, 314–331)

```bash
prepare() {
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
    exit 1
  fi

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
    fi
    cd ..
  fi

  # ... patch loop + SDK download (below) + upstream Setup.sh + BuildThirdParty.sh ...
}
```

### SDK toolchain parse

`source=()` and `sha256sums=()` no longer reference the toolchain tarball. Downloaded explicitly in prepare() after clone:

```bash
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

local _sdk_url="https://cdn.unrealengine.com/Toolchain_Linux/${_sdk_ver}.tar.gz"
local _sdk_tar="${srcdir}/${_sdk_ver}.tar.gz"
if [[ ! -f "${_sdk_tar}" ]]; then
  curl -fL --retry 3 -o "${_sdk_tar}" "${_sdk_url}" || {
    error "Failed to download SDK toolchain from ${_sdk_url}"
    exit 1
  }
fi

mkdir -p "${srcdir}/${pkgname}/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/"
tar -xf "${_sdk_tar}" -C "${srcdir}/${pkgname}/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/"
```

**Trade-off accepted:** SDK tarball outside makepkg's `source=()` means makepkg's offline-mode + integrity verification don't cover it. Acceptable because Epic CDN is the canonical source, and Setup.sh already downloads ~11 GiB during prepare() anyway.

## Renderer logic

`scripts/render.py <minor>` (also embedded in n8n Code node 7):

1. Read `templates/<minor>/meta.toml` → `{sdk_version_override, pkgrel, patches[]}`
2. Read `PKGBUILD.tmpl` + each `_common/*.tmpl`
3. Substitute placeholders (single-pass `str.replace` per token)
4. Copy each patch listed in `meta.toml.patches` from `templates/<minor>/patches/` into output dir
5. Compute sha256 for each rendered non-toolchain source file (launcher, desktop, hook, icon, each patch)
6. Inject `{{PATCH_SOURCES}}` (quoted filenames) + `{{NON_TOOLCHAIN_SHA256_LIST}}` (matching order)
7. Hand-roll `.SRCINFO` by parsing rendered PKGBUILD (flat `key = value` dump matching the arrays — same format upstream `.SRCINFO` uses)

`scripts/render.py` is the unit-testable surface. The n8n Code node embeds the same logic in JavaScript for in-process rendering — both must produce byte-identical output for the same inputs.

## Testing strategy

### Local

- `scripts/render.py 5.6 --out out/5.6` → writes rendered package
- Diff `out/5.6/PKGBUILD` against upstream maintainer files; expect only the templated lines to differ
- `cd out/5.6 && namcap PKGBUILD` → lint
- `makepkg -do --skipinteg` in `out/5.6` → runs prepare() locally without full build; validates clone fallback, SDK parse, patch apply
- `.github/workflows/render-check.yml`: render every minor 5.0–5.<latest>, namcap-lint, PR-blocking

### n8n

- Manual trigger button on Daily Check → fires whole flow
- Dry-run mode via workflow variable `DRY_RUN=true` → skips node 9, logs would-be commit
- Test sequence:
  1. Empty DataTable, `DRY_RUN=true` → expect render for every minor 5.0–latest, zero pushes
  2. Pre-seed DataTable with current versions → expect zero renders
  3. Delete one row (5.6) → expect render + push for 5.6 only
  4. Bump template repo commit → expect pkgrel bump for all minors next run
  5. Real run, `DRY_RUN=false` → first push creates AUR repos

### Post-publish

Finley installs each package on dev box (`paru -S unreal-engine-src-5.X`). Confirms 5.6 builds. Older minors (5.0–5.5) ship without patches initially and may fail; add per-minor patches as needed.

## Rollout plan

1. **Day 0:** Create template repo on GitHub, populate, commit. n8n unchanged.
2. **Day 0:** Local render + `makepkg --skipinteg` for 5.6. Validate templating diff.
3. **Day 1:** Update n8n workflow Code nodes via `mcp__claude_ai_n8n__update_workflow`. Trigger manually with `DRY_RUN=true`. Inspect rendered output.
4. **Day 1:** Set `DRY_RUN=false`, trigger manually. First AUR repo creations.
5. **Day 2+:** Install own package per minor. Document which minors build vs need patches.
6. **Ongoing:** When build fails for a minor → add patches to `templates/5.X/patches/` + update `meta.toml` → push template repo. Next n8n cycle bumps pkgrel + republishes.

## Edge cases

| Case | Behavior |
|------|----------|
| Epic ships 5.7.0-release (new minor) | Picked up automatically; new row in DataTable; new AUR repo created on first push. No code change. |
| Epic ships 5.6.2-release (patch bump) | Workflow detects, pkgver=5.6.2, pkgrel=1, push. |
| Same pkgver, template repo changed | `template_sha` differs from stored → pkgrel++ for that minor. Republishes. |
| Epic ships preview/early-access tag | Regex filters out anything not `^\d+\.\d+\.\d+-release$`. Ignored. |
| AUR rejects push (invalid PKGBUILD) | Node 11 captures stderr + minor. State NOT updated → automatic retry next cycle. Alert via n8n notification (deferred to v2). |
| Template repo clone fails (GH outage) | Run fails-fast at node 6. Retry next day. State untouched. |
| Patch fails to apply during user build | Upstream PKGBUILD prints msg + continues (line 336). Preserved. Build may still complete. |
| User has no GitHub/Epic linkage | Clone fallback hits else-branch, prints explicit instructions, exit 1. |
| AUR SSH key rotated | All pushes fail. n8n credential update needed. Failure rows accumulate; user notices. |
| Bot PAT expires | Node 2 fails. No release data → run aborts before any AUR mutation. Safe failure. |
| Two minors get patches in same cycle | SplitInBatches processes serially. Both push within one run. |
| Renderer bug produces broken PKGBUILD | namcap CI catches before merge. Bad commit on main → all minors fail to push next cycle (visible). |

## Open follow-ups (do not block design)

- Confirm n8n container has `git`, `openssh-client`, `curl`, AUR SSH key in agent, egress to `ssh.aur.archlinux.org:22`
- Confirm bot PAT scope is `repo` (private repo read) — for `EpicGames/UnrealEngine` release fetch
- Decide notification channel for failures (Discord webhook, email, etc.) — v2
- Decide DataTable backup strategy — v2

## Repository restructure

This local checkout at `/home/finley/Code/UE5/unreal-engine` is currently a clone of `https://aur.archlinux.org/unreal-engine.git`. To become the template repo:

1. Move existing maintainer files into appropriate subdirs (uncommitted):
   - `PKGBUILD`, `0001-*.patch`, `0002-*.patch` → `templates/5.6/patches/` (patches) + reference for `PKGBUILD.tmpl`
   - `unreal-engine.sh`, `com.unrealengine.UE5Editor.desktop`, `ue5editor.svg`, `unreal-engine-5-pacman-cache.hook` → `templates/_common/`
   - `.SRCINFO` → discard (generated)
2. Drop upstream git history (`rm -rf .git`), `git init -b master`, set remote to `git@github.com:FinleyLaempe/aur-unreal-engine-src.git`
3. First commit includes: this spec (`docs/superpowers/specs/`), `README.md`, `PKGBUILD.tmpl`, `templates/_common/` (templated copies of moved assets), `templates/5.6/` (with patches), `templates/5.0/`–`templates/5.5/` (empty `patches/` + minimal `meta.toml`), `scripts/render.py` + `scripts/add-minor.sh`, `.github/workflows/render-check.yml`
4. Push to GitHub
5. Node 5's "row absent" path will then create state for every minor on first n8n run; first run with `DRY_RUN=false` provisions all AUR repos in one pass
