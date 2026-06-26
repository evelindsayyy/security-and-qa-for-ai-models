# Shared host identity for Docker Compose (sourced by run.sh, build-pillars.sh, deploy-remote.sh).
#
# Pillar compose files use ${UID}/${GID}; bash sets UID readonly, so pillar builds/runs
# pass IDs via env(1):  compose_with_pillar_ids docker compose …

host_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HOST_REPO="$host_repo"
export HOST_UID="$(id -u)"
export HOST_GID="$(id -g)"
pillar_uid="$HOST_UID"
pillar_gid="$HOST_GID"

if [ -S /var/run/docker.sock ]; then
  export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

compose_with_pillar_ids() {
  env UID="$pillar_uid" GID="$pillar_gid" "$@"
}
