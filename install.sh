#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/recall" && pwd)"
TARGET="$HOME/.claude/skills/recall"

# Check Python 3.8+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found in PATH." >&2
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    echo "Error: Python 3.8+ required, found $PY_VERSION" >&2
    exit 1
fi

# Check for ripgrep (optional)
if command -v rg &>/dev/null; then
    echo "Found: ripgrep (fast search)"
else
    echo "Note: ripgrep (rg) not found — falling back to grep (slower but works fine)"
fi

# Create skills directory if needed
mkdir -p "$HOME/.claude/skills"

# Create or update symlink
if [ -L "$TARGET" ]; then
    EXISTING=$(readlink "$TARGET")
    if [ "$EXISTING" = "$SKILL_DIR" ]; then
        echo "Already installed at $TARGET"
        exit 0
    fi
    echo "Updating symlink (was: $EXISTING)"
    rm "$TARGET"
elif [ -e "$TARGET" ]; then
    echo "Error: $TARGET exists and is not a symlink. Remove it first." >&2
    exit 1
fi

ln -s "$SKILL_DIR" "$TARGET"
echo "Installed: $TARGET -> $SKILL_DIR"

# Create recalls directory for saved searches
mkdir -p "$HOME/.claude/recalls"
echo "Recalls directory: ~/.claude/recalls/"

echo ""
echo "Done. Use /recall <query> in Claude Code to search past conversations."
