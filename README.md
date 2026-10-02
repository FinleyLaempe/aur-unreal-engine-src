# aur-unreal-engine-src

Per-minor AUR packages for source builds of Unreal Engine 5. Each minor version
from 5.4 up (5.4, 5.5, ..., 5.<latest>) is published as a parallel-installable
AUR package `unreal-engine-src-5.X`, installing under `/opt/unreal-engine-src-5.X/`.
New Epic releases, including new minors, are picked up and published automatically.

## Credits

This project is built on, and copies from, the
[`unreal-engine`](https://aur.archlinux.org/packages/unreal-engine) AUR package,
maintained by **Alexis Belmonte**, and before that by Neko-san, Dylan Ferris,
Michael Lojkovic, Shatur95 and slx. Copied from it:

- the build logic in `PKGBUILD.tmpl` (templated per minor, with changes for
  parallel installs and package size)
- the launcher, desktop entry, pacman cache hook and icon in `templates/_common/`
- **all source patches**. These are taken automatically, for each UE minor, from
  upstream's newest release of that minor. Every rendered PKGBUILD names the
  exact upstream commit and author its patches came from.

Bugs in the engine build itself are most likely fixed upstream first. Please
report packaging problems specific to the per-minor variants here, not to the
upstream maintainer.

## How patches are chosen

`render.py` (and the n8n workflow) walk the upstream AUR repo's history and, for
each minor, take the `*.patch` files of the newest commit whose `pkgver` is
`5.<minor>.*`:

| Minor | Upstream commit | Upstream version | By |
|-------|-----------------|------------------|----|
| 5.4   | f5fa798         | 5.4.4            | Neko-san |
| 5.5   | 025480c         | 5.5.0            | Neko-san |
| 5.6   | 6d6c25d         | 5.6.1            | Alexis Belmonte |
| 5.7   | 3faddc1         | 5.7.4            | Alexis Belmonte |
| 5.8   | dc9aa87         | 5.8.2            | Alexis Belmonte |

(As of 2026-10-02. It updates itself when upstream publishes something new.)

- A minor upstream hasn't packaged yet (e.g. a fresh 5.9) uses the newest
  upstream patches until upstream catches up, then switches automatically.
- `upstream-ignore.txt` lists upstream patches we never copy (for example
  `use_system_clang.patch`, which is opt-in upstream).
- `templates/<minor>/` is an optional override: a `meta.toml` with an SDK
  override and/or extra local patches in `patches/`. No minor needs one today.

Only the patches follow upstream automatically. Changes to upstream's PKGBUILD
build logic must be ported to `PKGBUILD.tmpl` by hand.

## Layout

```
PKGBUILD.tmpl              # single template, substituted per minor
render.py                  # Python renderer + CLI
upstream-ignore.txt        # upstream patches we leave out
templates/
  _common/                 # shared assets (launcher.tmpl, desktop.tmpl, icon, hook.tmpl)
  <minor>/                 # optional per-minor override (meta.toml, patches/)
scripts/
  resolve-upstream.sh      # upstream snapshot per minor, as JSON (run by n8n)
  build-and-install.sh     # local multi-hour build + install helper
tests/                     # pytest, golden files for 5.6, resolver parity test
.github/workflows/         # CI: pytest + render-every-minor + namcap
docs/superpowers/{specs,plans}/   # original design + implementation plan
```

## Local render

```sh
git clone https://aur.archlinux.org/unreal-engine.git ../aur-unreal-engine
python render.py 5.8 --pkgver 5.8.3 --upstream ../aur-unreal-engine --out out/5.8
ls out/5.8   # PKGBUILD, .SRCINFO, unreal-engine-5.8.sh, patches, etc.
```

`out/<minor>/` is a buildable package directory; from there:

```sh
cd out/5.8
makepkg --skipinteg -do   # run prepare() (clone EpicGames + SDK download) without full build
../../scripts/build-and-install.sh .   # full build + install (multi-hour)
```

## Automation

An n8n workflow runs daily at 06:00. It:

1. reads EpicGames/UnrealEngine releases and picks the latest `5.X.Z-release`
   per minor (5.4 and newer, set in the workflow's `Config` node)
2. resolves upstream's patch snapshot per minor (`scripts/resolve-upstream.sh`
   on the SSH host)
3. republishes a minor when Epic's version, this repo's commit, or that minor's
   upstream snapshot changed (pkgrel bump for the last two)
4. pushes the rendered package to `ssh://aur@aur.archlinux.org/unreal-engine-src-5.X.git`

The workflow only reads this repo. Nothing runs on GitHub's scheduler, so the
automation doesn't stop when the repo is quiet.

## n8n bundle trigger

The same n8n workflow has a separate Manual Trigger "Bundle All Minors" that
reuses the live release feed (same `Pick Latest Per Minor` output as the daily
job — no hardcoded tags) and returns a single `unreal-engine-src-bundle.zip`
containing all rendered packages, each in its own `unreal-engine-src-5.X/`
subdirectory, plus `build-and-install.sh` at the ZIP root. Useful for
end-to-end local testing without touching AUR.

## Build status (verified manually)

| Minor | Local build verified | Notes |
|-------|----------------------|-------|
| 5.4   | no                   | Upstream shipped no default patches for 5.4 |
| 5.5   | no                   | Upstream snapshot is 5.5.0; Epic is at 5.5.4 |
| 5.6   | no                   | |
| 5.7   | no                   | |
| 5.8   | no                   | Matches upstream's current release line |

As each minor is built and verified, update this table.

## SHA256 sources

All non-toolchain entries in `source=()` use `sha256sums=('SKIP')`. These files
(launcher, desktop, hook, patches, icon) are rendered locally by the workflow
or the local renderer, so makepkg's integrity check would only be checking the
renderer's own output against itself. The toolchain tarball is downloaded
inside `prepare()` via `curl -f`, which fails loudly on download failure.

## Package size

The package ships only the **Installed Build** produced by
`Make Installed Build Linux` (headers + static libs included, so C++ projects
still compile), and binaries are stripped. It does NOT re-bundle the full
source checkout on top — that previously dragged in `.git`, Setup.sh's
ThirdParty downloads, the SDK toolchain and the DDC, inflating the package to
~140 GiB. Win64 cross-compile components are also off by default
(`UE_WITH_WIN64=false`). Expect roughly 40 GiB installed. Re-enable any of
these via env vars in `/etc/makepkg.conf` if you need them.

## Status

Renderer, templates, CI and the n8n workflow are in place. Before the first
real publish:

1. Add an SSH credential in n8n (a host with `git`, `curl` and a key registered
   on your AUR account) to the `Resolve Upstream` and `Push to AUR` nodes.
2. Run the workflow once with `DRY_RUN` on (the `Config` node, default `true`)
   and check the output. A dry run does not write state.
3. Set `DRY_RUN` to `false`, run it, then publish (activate) the workflow.

Email alerts for failed pushes are planned but not built yet.
