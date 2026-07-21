#!/usr/bin/env bash
# Reclaim disk under the repo (especially /home on split-volume hosts).
# Safe: removes regenerable Garak/HF detector caches; keeps safety reports.
#
#   ./scripts/reclaim-disk.sh           # dry-run sizes
#   ./scripts/reclaim-disk.sh --apply   # delete legacy + optional shared cache
#   ./scripts/reclaim-disk.sh --apply --shared-cache  # also wipe shared .garak-cache
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GARAK_OUT="$ROOT/safety/garak/output"
APPLY=0
SHARED=0

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --shared-cache) SHARED=1 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

echo "== Garak XDG caches under $GARAK_OUT =="
if [[ -d "$GARAK_OUT" ]]; then
  du -sh "$GARAK_OUT"/*/.garak-cache 2>/dev/null | sort -hr | head -20 || true
  du -sh "$GARAK_OUT"/.garak-cache "$GARAK_OUT"/.garak-data 2>/dev/null || true
else
  echo "(no garak output dir)"
fi

echo
echo "== scanner/models (should be tiny unless SCAN_KEEP_WEIGHTS) =="
du -sh "$ROOT/scanner/models" 2>/dev/null || echo "(missing)"

if [[ "$APPLY" -ne 1 ]]; then
  echo
  echo "Dry run only. Re-run with --apply to delete per-slug .garak-cache/.garak-data/.garak-config."
  echo "Add --shared-cache to also remove the shared $GARAK_OUT/.garak-cache (re-downloads on next garak run)."
  exit 0
fi

removed=0
if [[ -d "$GARAK_OUT" ]]; then
  while IFS= read -r -d '' dir; do
    rm -rf "$dir"
    removed=$((removed + 1))
  done < <(find "$GARAK_OUT" -mindepth 2 -maxdepth 2 -type d \
    \( -name '.garak-cache' -o -name '.garak-data' -o -name '.garak-config' \) -print0 2>/dev/null || true)
fi

if [[ "$SHARED" -eq 1 ]]; then
  for name in .garak-cache .garak-data .garak-config; do
    if [[ -d "$GARAK_OUT/$name" ]]; then
      rm -rf "$GARAK_OUT/$name"
      removed=$((removed + 1))
    fi
  done
fi

echo "Removed $removed cache/data/config director(ies)."
df -h "$ROOT" / 2>/dev/null || df -h
