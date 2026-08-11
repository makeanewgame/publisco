#!/usr/bin/env bash
# Stop hook: reminds Claude to check CLAUDE.md's "Sunucu Paketleri" (Modal
# Image) section whenever modal_worker/main.py's Image definition (apt_install/
# pip_install) changes, since a new Python package sometimes needs an OS-level
# dependency documented there. Fires once per distinct diff (tracked via a
# hash file under .claude/state/) so it doesn't re-block every turn once
# you've been told.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo '{}'; exit 0; }
cd "$repo_root"

state_dir=".claude/state"
mkdir -p "$state_dir"
hash_file="$state_dir/worker-deps-notified.hash"

diff_content="$(git diff HEAD -- modal_worker/main.py modal_worker/requirements.txt 2>/dev/null || true)"

if [ -z "$diff_content" ]; then
  echo '{}'
  exit 0
fi

claude_md_changed="$(git diff HEAD --name-only -- CLAUDE.md 2>/dev/null || true)"
if [ -n "$claude_md_changed" ]; then
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
{"decision":"block","reason":"modal_worker/main.py (or requirements.txt) changed but CLAUDE.md was not. If the new package needs an OS-level dependency (apt_install), update the Modal 'Sunucu Paketleri' section in CLAUDE.md before finishing; otherwise just note that no doc update was needed and stop."}
JSON
