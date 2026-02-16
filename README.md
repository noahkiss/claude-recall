<p align="center">
  <img src="banner.png" alt="Claude Recall" width="100%">
</p>

# Claude Recall

Search and retrieve context from past Claude Code conversations.

Ever discussed something weeks ago and can't remember where? Recall searches your entire Claude Code conversation history across all projects, lets you browse results interactively, and pulls relevant context back into your current session.

## Quick Install

**One-liner** (clones to `~/.local/share/claude-recall` and symlinks the skill):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/noahkiss/claude-recall/main/install-remote.sh)
```

**Or clone manually:**

```bash
git clone https://github.com/noahkiss/claude-recall.git
cd claude-recall
bash install.sh
```

Both methods create a symlink at `~/.claude/skills/recall/` pointing to the skill directory. Claude Code picks up new skills on the next session start.

### Requirements

- **Python 3.8+** (stdlib only — no pip dependencies)
- **Claude Code** — this is a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill
- **ripgrep** (optional) — `rg` speeds up content search; falls back to `grep` automatically

### Verify installation

```bash
# Check the symlink exists
ls -la ~/.claude/skills/recall

# Test the search engine directly
python3 ~/.claude/skills/recall/scripts/search.py projects
```

## Usage

### Search for past discussions

In any Claude Code session:

```
/recall docker networking
/recall that bug with the auth tokens
/recall when we set up the CI pipeline
```

The agent interprets your query, generates search variants, and presents results as compact cards:

```
## Recall: "docker networking" (8 matches, showing 1-3)

1. **tinyledger** — Feb 10 7:30p (4d ago)
   "Setting up bridge network for multi-container deploy"
   > You: "how should I handle container-to-container networking..."
   > Claude: "For your compose stack, I'd recommend a dedicated bridge..."
   12 msgs · branch: feat/docker-deploy
   session: a1b2c3d4 · ~/develop/tinyledger
```

### Interactive commands

After results appear, stay in the recall loop:

| Command | What it does |
|---------|-------------|
| `more` | Show the next page of results |
| `expand 2` | Drill into result #2 — shows summary, key exchanges, decisions |
| `pull 3` | Add result #3's context to the buffer |
| `done` | Exit recall and inject buffer into current conversation |
| `save` | Write buffer to disk for later use |
| `refine: new terms` | Re-search with different terms |

These are natural language — "tell me more about 2", "grab that one", "actually it was last week" all work.

### Buffer system

Pull multiple results into a buffer before injecting them:

```
→ pull 1
Added to buffer (1 item). Keep searching or say "done".

→ pull 3
Added to buffer (2 items). Keep searching or say "done".

→ done
## Recall Buffer (2 items)
[Summarized context from both sessions, ready to use]
```

### Saved recalls

```
/recall:history              # list past saved recalls
/recall:load <filename>      # load a saved recall into context
```

Saved recalls go to `~/.claude/recalls/` and persist across sessions.

## How It Works

### Two-phase search

1. **Metadata search** (fast) — scans `sessions-index.json` files for matching session summaries and first prompts. This is usually enough.
2. **Content search** (thorough) — if metadata doesn't find enough, searches actual conversation messages in JSONL files using ripgrep or grep.

### What gets searched

| Source | Search phase | Speed |
|--------|-------------|-------|
| Session summaries | Metadata | Instant |
| First user messages | Metadata | Instant |
| User messages in conversations | Content | ~1-3 seconds |
| Assistant responses | Content | ~1-3 seconds |
| Sub-agent conversations | Content (opt-in) | ~1-3 seconds |

### What doesn't get searched

Tool outputs (file reads, bash results), progress events, thinking blocks, and file history snapshots are excluded — they're noise for search purposes.

### Context protection

When you expand or pull a result, a **sub-agent** reads and summarizes the conversation. This keeps the main context window lean — you only pay tokens for the final summary, not the raw conversation data.

## Standalone search script

The search engine at `recall/scripts/search.py` works independently of Claude Code:

```bash
# Search session metadata (summaries, first prompts)
python3 recall/scripts/search.py metadata "auth setup"

# Search conversation content
python3 recall/scripts/search.py content "database migration" --project myapp --limit 5

# Extract conversation context around a match
python3 recall/scripts/search.py context /path/to/session.jsonl --line 42 --turns 3

# List all projects with session counts
python3 recall/scripts/search.py projects

# Format timestamps
python3 recall/scripts/search.py format-time "2026-02-10T19:30:00Z"
# → Feb 10  7:30p (4d ago)
```

All commands output JSON to stdout, suitable for piping to `jq` or other tools.

## Example

See [examples/real-world-search.md](examples/real-world-search.md) for a walkthrough of an actual Recall session — showing the two-phase search, cross-project discovery, refinement, and sub-agent usage with real token counts and timing.

## Skill specification

This skill follows the [Agent Skills](https://agentskills.io/specification) format:

```
recall/
├── SKILL.md              # Skill definition and agent behavior
├── scripts/
│   └── search.py         # Search engine (Python 3.8+, stdlib only)
└── references/
    └── REFERENCE.md      # Claude Code JSONL schema documentation
```

## Uninstall

From the cloned repo:
```bash
bash uninstall.sh           # remove skill symlink
bash uninstall.sh --purge   # also remove saved recall history
```

Or manually:
```bash
rm ~/.claude/skills/recall
rm -rf ~/.claude/recalls/   # optional: remove saved recalls
```

If you used the one-liner install:
```bash
rm ~/.claude/skills/recall
rm -rf ~/.local/share/claude-recall   # remove cloned repo
rm -rf ~/.claude/recalls/             # optional: remove saved recalls
```

## License

MIT
