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
