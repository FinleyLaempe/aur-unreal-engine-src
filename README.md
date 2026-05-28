# aur-unreal-engine-src

Per-minor AUR PKGBUILD templates for source builds of Unreal Engine 5. Each
minor version (5.0, 5.1, ..., 5.<latest>) is published as a parallel-installable
AUR package `unreal-engine-src-5.X`, installing under `/opt/unreal-engine-src-5.X/`.

Inspired by Alexis Belmonte's upstream [`unreal-engine`](https://aur.archlinux.org/packages/unreal-engine)
AUR package. This repo holds the templating + automation pieces around a
per-minor parallel-install variant.

## Layout

```
PKGBUILD.tmpl              # single template, substituted per minor
render.py                  # Python renderer + CLI
templates/
  _common/                 # shared assets (launcher.tmpl, desktop.tmpl, icon, hook.tmpl)
  5.X/
    meta.toml              # per-minor pkgrel, SDK override, patch list
    patches/               # per-minor patches
scripts/add-minor.sh       # scaffold helper for new minors
tests/                     # pytest + golden-file regression for 5.6
.github/workflows/         # CI: pytest + render-every-minor + namcap
docs/superpowers/{specs,plans}/   # design + implementation plan
```

## Local render

```sh
python render.py 5.6 --pkgver 5.6.1 --out out/5.6
ls out/5.6   # PKGBUILD, .SRCINFO, unreal-engine-5.6.sh, etc.
```

`out/<minor>/` is a buildable package directory; from there:

```sh
cd out/5.6
makepkg --skipinteg -do   # run prepare() (clone EpicGames + SDK download) without full build
makepkg --skipinteg -si   # full build + install (multi-hour)
```

## Automation

An n8n workflow polls EpicGames/UnrealEngine releases daily, picks the latest
`X.Y.Z-release` tag per minor, and pushes a rendered package to the
corresponding AUR repo when it sees a bump. The workflow only reads this repo;
template changes are pushed manually by the maintainer.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the full design.

## Adding a new minor

```sh
./scripts/add-minor.sh 5.7
# edit templates/5.7/meta.toml + add patches if needed
git add templates/5.7 && git commit -m "Add 5.7 templates"
git push
```

The next n8n cycle will publish `unreal-engine-src-5.7` once Epic ships a
`5.7.Z-release` tag.

## n8n bundle trigger

The same n8n workflow has a separate Manual Trigger "Bundle All Minors" that
renders every minor at hardcoded latest tags (edit the `TAGS` constant inside
the Bundle Render All Code node to change) and returns a single
`unreal-engine-src-bundle.zip` containing all rendered packages, each in its
own `unreal-engine-src-5.X/` subdirectory. Useful for end-to-end local testing
without touching AUR.

## Build status (verified manually)

| Minor | Patches in repo | Local build verified | Notes |
|-------|-----------------|----------------------|-------|
| 5.0   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.1   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.2   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.3   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.4   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.5   | none            | no                   | Bootstrap stub; needs per-minor patches |
| 5.6   | 0001, 0002      | not yet              | Inherited from Alexis Belmonte's upstream `unreal-engine` (verified against 5.6.1-release) |

As each minor is built and verified, update this table.

## SHA256 sources

All non-toolchain entries in `source=()` use `sha256sums=('SKIP')`. These files
(launcher, desktop, hook, patches, icon) are rendered locally by the workflow
or the local renderer, so makepkg's integrity check would only be checking the
renderer's own output against itself. The toolchain tarball is downloaded
inside `prepare()` via `curl -f`, which fails loudly on download failure.

## Status

Phase A–E complete (renderer + templates + CI). n8n workflow rewired
(Phase F). Production publish requires SSH credential setup on the
`Push to AUR` node and `DRY_RUN='false'` flip inside `Build Push Command`
(currently safe-default `true`).
