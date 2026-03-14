#!/bin/bash
set -e

# ── SSH known hosts ──────────────────────────────────────────
# Pre-populate known_hosts so git push/pull to Azure DevOps
# (and GitHub/GitLab) don't prompt for host verification.
# The mounted ~/.ssh is read-only, so we write to /root/.ssh_runtime
# and merge.

mkdir -p /root/.ssh_runtime

# If user mounted their known_hosts, use it as a base
if [ -f /root/.ssh/known_hosts ]; then
    cp /root/.ssh/known_hosts /root/.ssh_runtime/known_hosts
fi

# Add common Git hosting SSH host keys
ssh-keyscan -t rsa,ecdsa,ed25519 \
    ssh.dev.azure.com \
    vs-ssh.visualstudio.com \
    github.com \
    gitlab.com \
    >> /root/.ssh_runtime/known_hosts 2>/dev/null || true

# Point SSH at runtime known_hosts but still use mounted keys
export GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=/root/.ssh_runtime/known_hosts -o StrictHostKeyChecking=no"

# ── Git safe.directory ───────────────────────────────────────
# Container runs as root but the mounted repo is owned by the
# host user. Git will refuse to operate without this.
cp /root/.gitconfig /root/.gitconfig_runtime
export GIT_CONFIG_GLOBAL=/root/.gitconfig_runtime
git config --global --add safe.directory /repo

# ── Fix SSH key permissions ──────────────────────────────────
# Mounted keys are read-only but SSH complains if perms are too open.
# Copy keys to writable location with correct perms.
if [ -d /root/.ssh ]; then
    for key in /root/.ssh/id_*; do
        [ -f "$key" ] || continue
        base=$(basename "$key")
        cp "$key" "/root/.ssh_runtime/$base"
        chmod 600 "/root/.ssh_runtime/$base"
    done
    # Copy SSH config if present
    if [ -f /root/.ssh/config ]; then
        cp /root/.ssh/config /root/.ssh_runtime/config
        chmod 600 /root/.ssh_runtime/config
    fi
    export GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=/root/.ssh_runtime/known_hosts -o StrictHostKeyChecking=no -i /root/.ssh_runtime/id_ed25519 -i /root/.ssh_runtime/id_rsa -F /root/.ssh_runtime/config"
fi

echo "  SSH keys: $(ls /root/.ssh_runtime/id_* 2>/dev/null | wc -l) found"
echo "  Git safe.directory: /repo"
echo "  Repo: $(cd /repo && git remote get-url origin 2>/dev/null || echo 'no remote')"
echo "  Branch: $(cd /repo && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
echo ""

# ── Start app ────────────────────────────────────────────────
exec "$@"
