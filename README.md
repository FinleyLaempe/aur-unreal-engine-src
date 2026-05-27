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
templates/
  _common/                 # shared assets (launcher, desktop, icon, hook)
  5.X/
    meta.toml              # per-minor pkgrel, SDK override, patch list
    patches/               # per-minor patches
scripts/render.py          # local renderer
.github/workflows/         # CI: render every minor + namcap-lint
docs/superpowers/specs/    # design docs
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

## Status

Bootstrap. PKGBUILD.tmpl + renderer scripts to be filled in per the implementation plan generated alongside the spec.
