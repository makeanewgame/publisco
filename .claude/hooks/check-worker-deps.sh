#!/usr/bin/env bash
# Stop hook: reminds Claude to check apps/worker/README.md's "Sunucu Paketleri"
# section whenever apps/worker's pip manifests change, since a new Python
# package sometimes needs an OS-level dependency documented there.
# Fires once per distinct requirements diff (tracked via a hash file under
# .claude/state/) so it doesn't re-block every turn once you've been told.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo '{}'; exit 0; }
cd "$repo_root"

state_dir=".claude/state"
mkdir -p "$state_dir"
hash_file="$state_dir/worker-deps-notified.hash"

diff_content="$(git diff HEAD -- apps/worker/requirements.txt apps/worker/requirements-dev.txt 2>/dev/null || true)"

if [ -z "$diff_content" ]; then
  echo '{}'
  exit 0
fi

readme_changed="$(git diff HEAD --name-only -- apps/worker/README.md 2>/dev/null || true)"
if [ -n "$readme_changed" ]; then
  echo '{}'
  exit 0
fi

current_hash="$(printf '%s' "$diff_content" | shasum -a 256 | cut -d' ' -f1)"
last_hash=""
[ -f "$hash_file" ] && last_hash="$(cat "$hash_file")"

if [ "$current_hash" = "$last_hash" ]; then
  echo '{}'
  exit 0
fi

printf '%s' "$current_hash" > "$hash_file"

cat <<'JSON'
{"decision":"block","reason":"apps/worker/requirements*.txt changed but apps/worker/README.md was not. If the new package needs an OS-level dependency, update the 'Sunucu Paketleri' section before finishing; otherwise just note that no doc update was needed and stop."}
JSON
