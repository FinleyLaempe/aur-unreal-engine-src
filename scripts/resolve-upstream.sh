#!/usr/bin/env bash
# Print, as JSON, the newest upstream AUR `unreal-engine` commit for each
# UE 5.x minor, with that commit's *.patch files (base64).
#
# Usage:
#   scripts/resolve-upstream.sh [repo-url] [cache-dir]
#
# Run by the n8n "Resolve Upstream" node on the SSH host. Mirrors
# render.py:resolve_upstream() — tests/test_resolve_script.py checks both agree.
#
# Output:
#   {"head":"<sha>","snapshots":[{"minor":"5.8","commit":"<sha>","pkgver":"5.8.2",
#     "author":"Alexis Belmonte","patches":{"0001-x.patch":"<base64>",...}},...]}
# Snapshots are ordered newest commit first.

set -euo pipefail

REPO_URL="${1:-https://aur.archlinux.org/unreal-engine.git}"
CACHE="${2:-${XDG_CACHE_HOME:-${HOME}/.cache}/ue5-aur-bot/upstream}"

if [[ -d "${CACHE}/.git" ]]; then
  git -C "${CACHE}" fetch -q origin
  git -C "${CACHE}" reset -q --hard FETCH_HEAD
else
  rm -rf "${CACHE}"
  mkdir -p "$(dirname "${CACHE}")"
  git clone -q "${REPO_URL}" "${CACHE}"
fi
cd "${CACHE}"

seen=" "
sep=""
printf '{"head":"%s","snapshots":[' "$(git rev-parse HEAD)"
while IFS=$'\t' read -r commit author; do
  pkgver="$(git show "${commit}:PKGBUILD" | sed -n -E 's/^pkgver=([0-9]+\.[0-9]+\.[0-9]+[^[:space:]]*)$/\1/p' | head -n1)"
  [[ "${pkgver}" =~ ^5\.([0-9]+)\. ]] || continue
  minor="5.${BASH_REMATCH[1]}"
  [[ "${seen}" == *" ${minor} "* ]] && continue
  seen+="${minor} "

  author="${author//\\/}"
  author="${author//\"/}"
  printf '%s{"minor":"%s","commit":"%s","pkgver":"%s","author":"%s","patches":{' \
    "${sep}" "${minor}" "${commit}" "${pkgver}" "${author}"
  psep=""
  while IFS= read -r name; do
    printf '%s"%s":"%s"' "${psep}" "${name}" "$(git show "${commit}:${name}" | base64 -w0)"
    psep=","
  done < <(git ls-tree --name-only "${commit}" | grep '\.patch$' | LC_ALL=C sort || true)
  printf '}}'
  sep=","
done < <(git log --format='%H%x09%an' -- PKGBUILD)
printf ']}\n'
