#!/usr/bin/env bash
# Build + install a rendered package without the multi-hour-then-sudo-timeout
# trap.
#
# Usage:
#   scripts/build-and-install.sh <pkgdir>
#
# Workflow:
#   1. Cache sudo credentials upfront (you type your password once).
#   2. Start a background keepalive that re-validates sudo every 50s so its
#      timestamp never expires during the multi-hour build.
#   3. Run makepkg --skipinteg -si --noconfirm. The install step at the end
#      uses the still-warm sudo cache — no surprise prompt.
#   4. Trap kills the keepalive on exit / Ctrl-C so we don't leak a process.
#   5. On success, reclaim disk: the build leaves the full UE clone, the
#      Setup.sh dependency blobs and the toolchain in src/ (tens of GiB), plus
#      the staged package in pkg/. We delete those but KEEP the SDK toolchain
#      tarball so a later rebuild skips the slow/flaky Epic CDN download.
#      Pass --no-clean (or NO_CLEAN=1) to keep everything for debugging.
#
# The argument is the directory containing the rendered PKGBUILD (the n8n
# Bundle ZIP unpacks one directory per minor, e.g. unreal-engine-src-5.7/).

set -euo pipefail

NO_CLEAN="${NO_CLEAN:-0}"
ARGS=()
for arg in "$@"; do
  case "${arg}" in
    --no-clean) NO_CLEAN=1 ;;
    *) ARGS+=("${arg}") ;;
  esac
done
set -- "${ARGS[@]}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [--no-clean] <pkgdir>" >&2
  echo "  e.g. $0 unreal-engine-src-5.7" >&2
  exit 1
fi

PKGDIR="$1"
if [[ ! -f "${PKGDIR}/PKGBUILD" ]]; then
  echo "Error: no PKGBUILD at ${PKGDIR}/PKGBUILD" >&2
  exit 1
fi

cd "${PKGDIR}"

echo "[build-and-install] caching sudo upfront. Type your password once:"
sudo -v

# Refresh the sudo timestamp every 50s so both makepkg sudo points (the -s
# syncdeps install at the start and the -i package install at the end) run
# without re-prompting. Don't exit on a single transient miss — just keep
# trying; only stop when the parent script is gone.
PARENT=$$
( while kill -0 "${PARENT}" 2>/dev/null; do
    sudo -nv 2>/dev/null || true
    sleep 50
  done
) &
KEEPALIVE_PID=$!
trap '[[ -n "${KEEPALIVE_PID:-}" ]] && kill "${KEEPALIVE_PID}" 2>/dev/null || true' EXIT INT TERM

echo "[build-and-install] sudo cached + refreshing in background (pid ${KEEPALIVE_PID})."
echo "[build-and-install] starting makepkg --skipinteg -si --noconfirm"
echo

makepkg --skipinteg -si --noconfirm

if [[ "${NO_CLEAN}" != "1" ]]; then
  echo
  echo "[build-and-install] install OK — reclaiming build disk (keeping SDK tarball)."
  # prepare() looks for the toolchain tarball at src/native-linux-*.tar.gz and
  # skips Epic's slow/flaky CDN download if it's already there. So delete every
  # other entry under src/ (the UE clone with its .git, the Setup.sh dependency
  # blobs, the extracted SDK — tens of GiB) but leave that tarball in place.
  if [[ -d src ]]; then
    find src -mindepth 1 -maxdepth 1 \
      ! -name 'native-linux-*.tar.gz' \
      -exec rm -rf {} + 2>/dev/null || true
  fi
  rm -rf pkg
else
  echo
  echo "[build-and-install] --no-clean set; leaving src/ and pkg/ in place."
fi

echo
echo "[build-and-install] done."
