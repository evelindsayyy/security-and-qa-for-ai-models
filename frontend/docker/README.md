# frontend/docker — legacy

**Use the repo-root stack instead:** [`docker/README.md`](../../docker/README.md) and
[`docs/docker.md`](../../docs/docker.md).

The production UI runs from `docker/Dockerfile` via `python3 main.py` /
`./docker/run.sh`. That image bind-mounts the repo and the Docker socket so
browser **Start** buttons launch pillar jobs on the host daemon.

This directory (`frontend/docker/`) is an older experimental layout (port 3000,
view-only deploy notes). It is not used by CI or the application VM.
