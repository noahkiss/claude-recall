# Claude Recall — Development Guide

## Project Structure

```
claude-recall/
├── recall/                    # agentskills.io skill directory
│   ├── SKILL.md               # Skill definition (agent behavior spec)
│   ├── scripts/
│   │   └── search.py          # Search engine (Python 3.8+, stdlib only)
│   └── references/
│       └── REFERENCE.md       # Claude Code JSONL schema documentation
├── install.sh                 # Symlinks recall/ → ~/.claude/skills/recall
├── uninstall.sh               # Removes symlink
├── README.md                  # Public documentation
├── LICENSE                    # MIT
└── AGENTS.md                  # This file
```

## Development Rules

- **Python 3.8+ compatibility**: No match/case (3.10+), no `X | Y` union types (3.10+), no tomllib (3.11+). Use `from typing import Optional, List, Dict, Tuple` for type hints.
- **stdlib only**: No pip dependencies. The search script must work on a fresh Python 3.8+ install.
- **Shell out for speed**: Use ripgrep (`rg`) or grep for initial file-level search. Fall back to pure Python if neither works.
- **JSON output**: `search.py` always outputs JSON to stdout. The skill agent parses it.
- **Skill spec**: Follow [agentskills.io/specification](https://agentskills.io/specification). Keep SKILL.md under 500 lines.

## Testing

Test search.py against real conversation data:

```bash
# Should return results if there are sessions with those terms
python3 recall/scripts/search.py metadata "docker"
python3 recall/scripts/search.py content "docker" --limit 3
python3 recall/scripts/search.py projects

# Format timestamp
python3 recall/scripts/search.py format-time "2026-02-10T19:30:00Z"
```

## Key Design Decisions

1. **Two-phase search**: Metadata first (fast, small), content second (thorough). Most searches resolve in phase 1.
2. **Sub-agent isolation**: Expansion and summarization happen in sub-agents to protect main context.
3. **Re-render buffer UX**: Every response re-renders a compact 5-line state header since we can't do in-place terminal updates.
4. **Intermediate file format**: Search results written to JSON files that both the in-Claude UX and any future TUI could consume.
