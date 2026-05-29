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
#
# The argument is the directory containing the rendered PKGBUILD (the n8n
# Bundle ZIP unpacks one directory per minor, e.g. unreal-engine-src-5.7/).

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <pkgdir>" >&2
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

# Refresh the sudo timestamp every 50s. Killed by the EXIT trap.
( while true; do
    sudo -nv 2>/dev/null || exit 0
    sleep 50
  done
) &
KEEPALIVE_PID=$!
trap '[[ -n "${KEEPALIVE_PID:-}" ]] && kill "${KEEPALIVE_PID}" 2>/dev/null || true' EXIT INT TERM

echo "[build-and-install] sudo cached + refreshing in background (pid ${KEEPALIVE_PID})."
echo "[build-and-install] starting makepkg --skipinteg -si --noconfirm"
echo

makepkg --skipinteg -si --noconfirm

echo
echo "[build-and-install] done."
