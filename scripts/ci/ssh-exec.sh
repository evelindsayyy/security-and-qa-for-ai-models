#!/usr/bin/env bash
set -Eeuo pipefail

log() {
    printf '[ci-ssh] %s\n' "$*" >&2
}

die() {
    log "ERROR: $*"
    exit 1
}

require_env() {
    local name=$1
    if [[ -z "${!name:-}" ]]; then
        die "$name is not set"
    fi
}

require_file_env() {
    local name=$1
    local path=${!name:-}

    require_env "$name"

    if [[ ! -f "$path" ]]; then
        die "$name does not point to a file"
    fi

    if [[ ! -s "$path" ]]; then
        die "$name points to an empty file"
    fi
}

if [[ $# -eq 0 ]]; then
    die "usage: $0 <remote-command> [args...]"
fi

require_env DEPLOY_HOST
require_env DEPLOY_USER
require_file_env DEPLOY_SSH_PRIVATE_KEY
require_file_env DEPLOY_SSH_KNOWN_HOSTS

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/ci-ssh.XXXXXX")
cleanup() {
    rm -rf "$tmp_dir"
}
trap cleanup EXIT

key_file="$tmp_dir/deploy_key"
known_hosts_file="$tmp_dir/known_hosts"

cp "$DEPLOY_SSH_PRIVATE_KEY" "$key_file"
# GitLab file variables can lose the final newline; OpenSSH requires it.
printf '\n' >> "$key_file"
chmod 400 "$key_file"

cp "$DEPLOY_SSH_KNOWN_HOSTS" "$known_hosts_file"
chmod 644 "$known_hosts_file"

log "Prepared deploy SSH credentials"
log "Executing remote command"

ssh \
    -i "$key_file" \
    -o BatchMode=yes \
    -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$known_hosts_file" \
    "$DEPLOY_USER@$DEPLOY_HOST" \
    "$@"

log "Remote command completed"
