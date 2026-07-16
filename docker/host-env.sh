# Shared host identity for Docker Compose (sourced by run.sh, build-pillars.sh, deploy-remote.sh).
#
# Pillar compose files use ${UID}/${GID}; bash sets UID readonly, so pillar builds/runs
# pass IDs via env(1):  compose_with_pillar_ids docker compose …
#
# HOST_UID/HOST_GID must match the user that owns the bind-mounted repo tree.
# GitLab deploy SSHes as security-qa-deploy; if we used that account's id(1), the
# web container could not write vcm-owned paths (summary cache, scan locks, …)
# and browser routes would 500 until someone restarted as vcm. Always prefer the
# repo owner's uid/gid unless the caller already exported HOST_UID/HOST_GID.

host_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HOST_REPO="$host_repo"

if [ -z "${HOST_UID:-}" ] || [ -z "${HOST_GID:-}" ]; then
  if [ -d "$host_repo" ]; then
    export HOST_UID="$(stat -c '%u' "$host_repo")"
    export HOST_GID="$(stat -c '%g' "$host_repo")"
  else
    export HOST_UID="$(id -u)"
    export HOST_GID="$(id -g)"
  fi
fi

pillar_uid="$HOST_UID"
pillar_gid="$HOST_GID"

if [ -S /var/run/docker.sock ]; then
  export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

compose_with_pillar_ids() {
  env UID="$pillar_uid" GID="$pillar_gid" "$@"
}
