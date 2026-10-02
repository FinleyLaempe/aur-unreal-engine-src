#!/usr/bin/env bash
# One-time setup of the machine the n8n workflow SSHes into to publish the
# unreal-engine-src-5.X packages to the AUR ("Resolve Upstream" and "Push to
# AUR" nodes).
#
# Usage, as root on that machine (normally the n8n server):
#   bash <(curl -fsSL https://raw.githubusercontent.com/FinleyLaempe/aur-unreal-engine-src/master/scripts/setup-push-host.sh)
#
# Creates an `aur-bot` user with git + curl, a dedicated key for pushing to the
# AUR, and a login key for n8n, then prints what to paste into the AUR account
# page and the n8n credential. Safe to re-run: the user and keys are kept.

set -euo pipefail

BOT_USER="${BOT_USER:-aur-bot}"
SHOW_PRIVATE_KEY="${SHOW_PRIVATE_KEY:-1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this as root." >&2
  exit 1
fi

# --- git, curl, ssh client (base64 comes with coreutils) ---
if ! command -v git >/dev/null || ! command -v curl >/dev/null || ! command -v ssh >/dev/null; then
  if command -v pacman >/dev/null; then
    pacman -S --needed --noconfirm git curl openssh
  elif command -v apt-get >/dev/null; then
    apt-get update -q && apt-get install -yq git curl openssh-client
  elif command -v dnf >/dev/null; then
    dnf install -y git curl openssh-clients
  elif command -v apk >/dev/null; then
    apk add --no-cache bash coreutils git curl openssh-client
  else
    echo "Install git, curl and an ssh client, then re-run." >&2
    exit 1
  fi
fi

# --- bot user ---
if ! id "${BOT_USER}" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "${BOT_USER}"
fi
BOT_GROUP="$(id -gn "${BOT_USER}")"
BOT_HOME="$(getent passwd "${BOT_USER}" | cut -d: -f6)"
SSH_DIR="${BOT_HOME}/.ssh"
install -d -m 700 -o "${BOT_USER}" -g "${BOT_GROUP}" "${SSH_DIR}"

# --- keys: one to push to the AUR, one for n8n to log in here ---
AUR_KEY="${SSH_DIR}/aur_ed25519"
LOGIN_KEY="${SSH_DIR}/n8n_login_ed25519"
[[ -f "${AUR_KEY}" ]] || ssh-keygen -q -t ed25519 -N '' -C "${BOT_USER}@$(uname -n) aur push" -f "${AUR_KEY}"
[[ -f "${LOGIN_KEY}" ]] || ssh-keygen -q -t ed25519 -N '' -C "n8n -> ${BOT_USER}@$(uname -n)" -f "${LOGIN_KEY}"

touch "${SSH_DIR}/authorized_keys" "${SSH_DIR}/config" "${SSH_DIR}/known_hosts"
grep -qxF "$(cat "${LOGIN_KEY}.pub")" "${SSH_DIR}/authorized_keys" || cat "${LOGIN_KEY}.pub" >> "${SSH_DIR}/authorized_keys"
if ! grep -q 'aur_ed25519' "${SSH_DIR}/config"; then
  cat >> "${SSH_DIR}/config" <<'EOF'
Host aur.archlinux.org
  User aur
  IdentityFile ~/.ssh/aur_ed25519
  IdentitiesOnly yes
EOF
fi
if ! grep -q '^aur.archlinux.org ' "${SSH_DIR}/known_hosts"; then
  ssh-keyscan -t ed25519 aur.archlinux.org 2>/dev/null >> "${SSH_DIR}/known_hosts" || true
fi
chown -R "${BOT_USER}:${BOT_GROUP}" "${SSH_DIR}"
chmod 600 "${SSH_DIR}"/*
chmod 644 "${AUR_KEY}.pub" "${LOGIN_KEY}.pub"

# --- what n8n should use as Host ---
HOST_HINT="the LAN address n8n uses to reach this machine"
if ps -eo args 2>/dev/null | grep -qE '(^|/)n8n start'; then
  HOST_HINT="127.0.0.1   (n8n runs natively on this machine)"
elif command -v docker >/dev/null && N8N_CTR="$(docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | awk 'tolower($0) ~ /n8n/ {print $1; exit}')" && [[ -n "${N8N_CTR}" ]]; then
  GW="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.Gateway}} {{end}}' "${N8N_CTR}" 2>/dev/null | awk '{print $1}')"
  [[ -n "${GW}" ]] && HOST_HINT="${GW}   (n8n runs in Docker container '${N8N_CTR}'; this is its gateway to this host)"
fi
if [[ "${SHOW_PRIVATE_KEY}" == "1" ]]; then
  PRIVATE_KEY_TEXT="$(cat "${LOGIN_KEY}")"
else
  PRIVATE_KEY_TEXT="(not shown) Print it on this machine with:  cat ${LOGIN_KEY}"
fi
SSHD_NOTE=""
if command -v ss >/dev/null && ! ss -ltn 2>/dev/null | grep -qE '[:.]22[[:space:]]'; then
  SSHD_NOTE="WARNING: nothing is listening on port 22 here. n8n needs sshd on this machine."
fi

cat <<EOF

================================================================================
 1. Add this key to your AUR account
    https://aur.archlinux.org/account/  ->  Edit account  ->  "SSH Public Key"
    Put it on a NEW line under your existing key (keep that one).
================================================================================
$(cat "${AUR_KEY}.pub")

================================================================================
 2. Create the n8n credential
    n8n -> Credentials -> Create -> "SSH Private Key"
      Name:        AUR push host
      Host:        ${HOST_HINT}
      Port:        22
      Username:    ${BOT_USER}
      Private Key: everything below, including the BEGIN/END lines
      Passphrase:  (leave empty)
================================================================================
${PRIVATE_KEY_TEXT}

================================================================================
 3. Check (after step 1):
      runuser -u ${BOT_USER} -- ssh aur@aur.archlinux.org help
    should print the AUR command list instead of "Permission denied".
${SSHD_NOTE}
================================================================================
EOF
