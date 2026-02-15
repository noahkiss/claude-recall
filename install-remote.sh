#!/usr/bin/env bash
# Remote installer for Claude Recall
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/noahkiss/claude-recall/main/install-remote.sh)
set -euo pipefail

REPO="https://github.com/noahkiss/claude-recall.git"
INSTALL_DIR="${HOME}/.local/share/claude-recall"
SKILL_TARGET="${HOME}/.claude/skills/recall"

echo "Claude Recall — installing..."

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

# Check for git
if ! command -v git &>/dev/null; then
    echo "Error: git is required but not found in PATH." >&2
    exit 1
fi

# Clone or update
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation at $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || {
        echo "Warning: could not fast-forward. Remove $INSTALL_DIR and re-run to get a fresh clone." >&2
    }
else
    echo "Cloning to $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO" "$INSTALL_DIR"
fi

# Check for ripgrep (optional)
if command -v rg &>/dev/null; then
    echo "Found: ripgrep (fast search)"
else
    echo "Note: ripgrep (rg) not found — search will use grep (slower but works fine)"
fi

# Create skills directory if needed
mkdir -p "${HOME}/.claude/skills"

# Create or update symlink
SKILL_DIR="${INSTALL_DIR}/recall"

if [ -L "$SKILL_TARGET" ]; then
    rm "$SKILL_TARGET"
elif [ -e "$SKILL_TARGET" ]; then
    echo "Error: $SKILL_TARGET exists and is not a symlink. Remove it first." >&2
    exit 1
fi

ln -s "$SKILL_DIR" "$SKILL_TARGET"
echo "Installed: $SKILL_TARGET -> $SKILL_DIR"

# Create recalls directory for saved searches
mkdir -p "${HOME}/.claude/recalls"

echo ""
echo "Done. Start a new Claude Code session and use /recall <query> to search past conversations."
echo ""
echo "To uninstall:"
echo "  rm ~/.claude/skills/recall"
echo "  rm -rf ~/.local/share/claude-recall"
