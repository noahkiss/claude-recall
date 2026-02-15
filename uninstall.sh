#!/usr/bin/env bash
set -euo pipefail

TARGET="$HOME/.claude/skills/recall"
RECALLS_DIR="$HOME/.claude/recalls"

if [ -L "$TARGET" ]; then
    rm "$TARGET"
    echo "Removed skill symlink: $TARGET"
elif [ -e "$TARGET" ]; then
    echo "Warning: $TARGET is not a symlink — not removing. Delete manually if intended." >&2
else
    echo "Skill not installed (no symlink at $TARGET)"
fi

if [ "${1:-}" = "--purge" ]; then
    if [ -d "$RECALLS_DIR" ]; then
        rm -rf "$RECALLS_DIR"
        echo "Removed saved recalls: $RECALLS_DIR"
    fi
else
    if [ -d "$RECALLS_DIR" ]; then
        echo "Saved recalls preserved at $RECALLS_DIR (use --purge to remove)"
    fi
fi

echo "Done."
