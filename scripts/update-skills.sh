#!/usr/bin/env bash
# Re-sync the vendored agent skills from their upstream repos.
#
#   ./scripts/update-skills.sh            # sync all sources at their pinned commits
#   ./scripts/update-skills.sh --latest   # sync all sources at upstream HEAD
#   ./scripts/update-skills.sh taste-skill impeccable [--latest]
#
# After a --latest run, update the "commit" fields in skills-manifest.json
# (the script prints the SHAs it checked out) and commit the result.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LATEST=0
WANTED=()
for arg in "$@"; do
  case "$arg" in
    --latest) LATEST=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) WANTED+=("$arg") ;;
  esac
done

wants() {
  [ ${#WANTED[@]} -eq 0 ] && return 0
  for w in "${WANTED[@]}"; do [ "$w" = "$1" ] && return 0; done
  return 1
}

sync() { # id repo commit
  local id="$1" repo="$2" commit="$3" dir="$WORK/$1"
  wants "$id" || return 0
  echo "==> $id  ($repo)"
  if [ "$LATEST" = "1" ]; then
    git clone --depth 1 "$repo" "$dir" -q
  else
    git clone --filter=blob:none "$repo" "$dir" -q
    git -C "$dir" checkout -q "$commit"
  fi
  echo "    at $(git -C "$dir" rev-parse HEAD)"

  case "$id" in
    taste-skill)
      for s in "$dir"/skills/*/; do
        name="$(basename "$s")"
        rm -rf "$ROOT/.claude/skills/$name"
        cp -R "$s" "$ROOT/.claude/skills/$name"
      done
      cp "$dir/skills/llms.txt" "$ROOT/docs/skills/taste-skill-llms.txt" 2>/dev/null || true
      cp "$dir/LICENSE" "$ROOT/docs/skills/licenses/taste-skill.LICENSE"
      ;;
    emilkowalski-skills)
      for s in "$dir"/skills/*/; do
        name="$(basename "$s")"
        rm -rf "$ROOT/.claude/skills/$name"
        cp -R "$s" "$ROOT/.claude/skills/$name"
      done
      cp "$dir/LICENSE" "$ROOT/docs/skills/licenses/emilkowalski-skills.LICENSE"
      ;;
    impeccable)
      rm -rf "$ROOT/.claude/skills/impeccable"
      cp -R "$dir/.claude/skills/impeccable" "$ROOT/.claude/skills/impeccable"
      cp "$dir"/.claude/agents/impeccable-*.md "$ROOT/.claude/agents/"
      cp "$dir/LICENSE" "$ROOT/docs/skills/licenses/impeccable.LICENSE"
      cp "$dir/NOTICE.md" "$ROOT/docs/skills/licenses/impeccable.NOTICE.md"
      mkdir -p "$ROOT/.agent/skills"
      ln -sfn ../../.claude/skills/impeccable "$ROOT/.agent/skills/impeccable"
      ;;
  esac
}

sync taste-skill         https://github.com/leonxlnx/taste-skill        ccbc15639c97057cbfcf32ecebc38ef716e4bb37
sync emilkowalski-skills https://github.com/emilkowalski/skills         d23d7f88a2e21c9e4b1418c7abe420f5c1052ba7
sync impeccable          https://github.com/pbakaus/impeccable          6f6af815af7db71602d2fb4bf95f84e677d2414d

echo
echo "Done. Review with: git status && git diff --stat"
