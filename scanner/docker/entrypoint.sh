#!/bin/sh
# Named volume mounts arrive root-owned; chown once as root, then drop to UID/GID.
set -eu

models_root="${MODELS_ROOT:-/app/scanner/models}"
target_uid="${UID:-1000}"
target_gid="${GID:-1000}"

mkdir -p "$models_root"

if [ "$(id -u)" -eq 0 ]; then
  chown -R "${target_uid}:${target_gid}" "$models_root"
  exec gosu "${target_uid}:${target_gid}" "$@"
fi

exec "$@"
