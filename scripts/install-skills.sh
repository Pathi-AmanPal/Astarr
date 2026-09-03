#!/usr/bin/env bash
# Set up the vendored skills.
#
#   ./scripts/install-skills.sh             # repair this repo (run once after clone)
#   ./scripts/install-skills.sh --global    # also install into ~/.claude for every project
#   ./scripts/install-skills.sh --global --force
#
# Repo repair recreates .agent/skills/impeccable, which Impeccable's scripts and
# allowed-tools resolve against. Git checkouts on Windows (and any archive export)
# can land it as a plain text file instead of a link.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
GLOBAL=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --global|-g) GLOBAL=1 ;;
    --force|-f)  FORCE=1 ;;
    -h|--help)   sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- repo repair
# The link must match what is committed, byte for byte: git tracks the symlink's
# TARGET TEXT as the blob, so an absolute target that resolves perfectly still shows
# up as a permanent modification in `git status` and would commit a machine-specific
# path if anyone staged it.
link="$ROOT/.agent/skills/impeccable"
want="../../.claude/skills/impeccable"
mkdir -p "$ROOT/.agent/skills"

# Two failure modes this deliberately does NOT treat as success:
#   1. A symlink that resolves but points somewhere else (e.g. an absolute path).
#      `[ -L ] && [ -d ]` is true for it, which is why the old check passed it.
#   2. `ln -s` on a Git-Bash/MSYS checkout without symlink privileges, which silently
#      COPIES the directory and exits 0. `[ -d ]` is true for the copy, so the old
#      check reported "relinked" for 163 duplicated files that then drift out of sync
#      with .claude/skills/impeccable, with nothing to catch it.
if [ -L "$link" ] && [ -d "$link" ] && [ "$(readlink "$link")" = "$want" ]; then
  echo "ok   .agent/skills/impeccable -> $(readlink "$link")"
else
  if [ -L "$link" ]; then
    current="$(readlink "$link" 2>/dev/null || true)"
    [ -n "$current" ] && echo "     replacing link -> $current"
    rm -f "$link"            # a link: remove the link, never follow into the target
  elif [ -e "$link" ]; then
    echo "     replacing a real directory/file (not a link)"
    rm -rf "$link"
  fi

  # nativestrict makes ln -s FAIL loudly rather than fall back to copying, so the
  # copy path below is reached deliberately instead of masquerading as a link.
  MSYS="${MSYS:-}${MSYS:+ }winsymlinks:nativestrict" \
    ln -s "$want" "$link" 2>/dev/null || true

  if [ -L "$link" ] && [ -d "$link" ] && [ "$(readlink "$link")" = "$want" ]; then
    echo "fix  .agent/skills/impeccable relinked -> $want"
  else
    # Not a usable link. Clear whatever landed there before copying, so a partial
    # or wrong-target link is never left behind next to the copy.
    if [ -L "$link" ]; then rm -f "$link"; elif [ -e "$link" ]; then rm -rf "$link"; fi
    cp -R "$ROOT/.claude/skills/impeccable" "$link"
    echo "warn .agent/skills/impeccable COPIED, not linked (symlinks unavailable here)"
    echo "     the copy will drift from .claude/skills/impeccable and git will show"
    echo "     the tracked symlink as deleted. To get a real link: enable Windows"
    echo "     Developer Mode (or run elevated), 'git config core.symlinks true',"
    echo "     then re-run this script."
  fi
fi

if [ ! -f "$ROOT/.claude/skills/impeccable/scripts/context.mjs" ]; then
  echo "error: .claude/skills/impeccable is missing. Run ./scripts/update-skills.sh first." >&2
  exit 1
fi

# ------------------------------------------------------------- global install
if [ "$GLOBAL" = "1" ]; then
  echo
  echo "Installing into $CLAUDE_HOME"
  mkdir -p "$CLAUDE_HOME/skills" "$CLAUDE_HOME/agents"

  for src in "$ROOT"/.claude/skills/*/; do
    name="$(basename "$src")"
    dest="$CLAUDE_HOME/skills/$name"
    if [ -e "$dest" ] && [ "$FORCE" != "1" ] && ! diff -rq "$src" "$dest" >/dev/null 2>&1; then
      echo "skip $name (already installed and differs; --force to overwrite)"
      continue
    fi
    rm -rf "$dest"
    cp -R "$src" "$dest"
    echo "  +  $name"
  done

  cp "$ROOT"/.claude/agents/impeccable-*.md "$CLAUDE_HOME/agents/"
  echo "  +  4 impeccable agents"

  # Pre-approve the script calls at their global path so they don't prompt.
  node - "$CLAUDE_HOME" <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
const home = process.argv[2];
const file = path.join(home, 'settings.json');
const want = [
  `Bash(node ${path.join(home, 'skills/impeccable/scripts')}/*)`,
  'Bash(node .claude/skills/impeccable/scripts/*)',
  'Bash(node .agent/skills/impeccable/scripts/*)',
  'Bash(npx impeccable *)',
];
let settings = {};
if (fs.existsSync(file)) {
  try {
    settings = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    console.log(`warn ${file} is not valid JSON - add these to permissions.allow yourself:`);
    for (const w of want) console.log(`       ${w}`);
    process.exit(0);
  }
}
settings.permissions ??= {};
const allow = (settings.permissions.allow ??= []);
const added = want.filter((w) => !allow.includes(w));
if (added.length) {
  allow.push(...added);
  fs.writeFileSync(file, `${JSON.stringify(settings, null, 2)}\n`);
  console.log(`  +  ${added.length} permission(s) in ${file}`);
} else {
  console.log('  =  permissions already present');
}
NODE

  cat <<'EOT'

Done. Restart Claude Code, then type / to see the skills in any project.

Note: Impeccable writes PRODUCT.md and DESIGN.md into whatever project you run it
in, and reads the project's own code - a global install changes where the skill
lives, not where it works.
EOT
fi
