---
name: recall
description: Search past Claude Code conversation histories to find previous discussions, decisions, and context. Use when the user wants to find something they discussed before, recall a past decision, or pull context from an old session into the current one. Invoked with /recall or when user says "I remember discussing...", "where did we talk about...", "find that conversation about...", etc.
compatibility: Requires Python 3.8+, Claude Code. Optional ripgrep (rg) for faster search.
metadata:
  author: noahkiss
  version: "0.1.0"
  repo: https://github.com/noahkiss/claude-recall
---

# Recall

Search and retrieve context from past Claude Code sessions.

## Commands

- `/recall <query>` — Search for past discussions (default)
- `/recall:history` — List previously saved recall results
- `/recall:load <filename>` — Load a saved recall back into context

## Search Engine

The search engine is at `scripts/search.py` (relative to this skill directory). Always invoke via `python3`.

```bash
SKILL_DIR="$(dirname "$(readlink -f "$0")")"  # not needed — see invocation below
```

Invoke the search script using its absolute path based on this skill's location. The skill is installed at `~/.claude/skills/recall/`, so the script is at `~/.claude/skills/recall/scripts/search.py`.

### Commands

```bash
# Phase 1: Search session metadata (fast — searches summaries and first prompts)
python3 ~/.claude/skills/recall/scripts/search.py metadata "<query>"

# Phase 2: Search conversation content (slower — searches actual messages)
python3 ~/.claude/skills/recall/scripts/search.py content "<query>" [--project NAME] [--limit N]

# Phase 3: Extract context around a specific match
python3 ~/.claude/skills/recall/scripts/search.py context <session.jsonl> --line <N> --turns 3

# List all projects
python3 ~/.claude/skills/recall/scripts/search.py projects

# Format a timestamp
python3 ~/.claude/skills/recall/scripts/search.py format-time "<ISO timestamp>"
```

All commands output JSON to stdout.

## Workflow: `/recall <query>`

### Step 1: Interpret the query

The user's query will often be fuzzy: "that docker networking thing", "when we set up auth", "the bug with the API". Your job is to generate **multiple search variants** to maximize recall:

- Extract key terms from the query
- Generate 2-5 variants: synonyms, related terms, abbreviated/expanded forms
- Example: "docker networking" → search for "docker network", "container network", "bridge network", "compose network", "docker dns"

### Step 2: Metadata search (always do this first)

Run `search.py metadata` for each variant. This is fast and searches session summaries and first prompts — often enough to find what the user wants.

```bash
python3 ~/.claude/skills/recall/scripts/search.py metadata "docker network"
python3 ~/.claude/skills/recall/scripts/search.py metadata "container network"
```

Run these in parallel when possible. Deduplicate results by sessionId.

### Step 3: Content search (if metadata didn't find enough)

If metadata search returned few or no results, escalate to content search:

```bash
python3 ~/.claude/skills/recall/scripts/search.py content "docker network" --limit 10
```

This searches the actual conversation text. Slower but catches discussions where the summary doesn't mention the topic.

### Step 4: Rank and group results

**Ranking factors** (use your judgment to weight these):
- Semantic relevance to the user's query (most important)
- Recency (newer sessions ranked higher, all else equal)
- Conversation depth (more messages = deeper discussion = more likely useful)
- Match density (multiple matches in one session > single mention)
- Main session > subagent (main sessions have the full picture)

**Grouping**: If results span a common theme across sessions, group them into threads:

```markdown
### Thread: Container networking (3 sessions)
1. ...
2. ...

### Thread: Reverse proxy setup (2 sessions)
3. ...
```

Only create threads if there are 5+ results and clear thematic clusters. Otherwise, just show a flat ranked list.

### Step 5: Present compact results

Display results in this exact format — compact, scannable, consistent:

```markdown
## Recall: "<query>" (N matches, showing 1-3)

1. **project-name** — Feb 10 7:30p (4d ago)
   "Session summary from the index"
   > You: "matching user message snippet..."
   > Claude: "matching assistant message snippet..."
   N msgs · branch: main
   session: abc12345 · ~/develop/project-name

2. **other-project** — Feb 3 2:15p (11d ago)
   ...

→ "more" for next 3 · "expand N" for detail · "pull N" to buffer
```

**Formatting rules:**
- Use `format-time` output style for dates: `Feb 10 7:30p (4d ago)`
- Relative time only for sessions < 14 days old
- Snippets: one user line + one assistant line from the matching turn, truncated to ~80 chars each
- Always show: message count, git branch (if available), session ID, project directory
- Page size: 3 results at a time (keeps output compact)
- Footer shows available commands

### Step 6: Interactive loop

Stay in the recall loop until the user explicitly exits. Handle these interactions naturally (exact phrasing doesn't matter — interpret intent):

| Intent | Action |
|--------|--------|
| "more" / "next" / "keep going" | Show next page of results |
| "expand N" / "tell me more about N" | Drill into result N (see Expansion below) |
| "pull N" / "grab N" / "add N" | Add result N to the buffer (see Buffer below) |
| "refine: new terms" / "actually try..." | Re-run search with new/additional terms |
| "exclude project-name" | Remove a project from results, re-display |
| "it was last week" / date hints | Re-run with date filter |
| "done" / "that's enough" / "thanks" | Exit recall, render buffer if non-empty |
| "save" | Write buffer to file, then exit |

**Re-render the state header with every response.** Since we can't update in-place, re-display the compact result list at the top of each response so the user always sees current state without scrolling back. Mark buffered items with ★:

```markdown
## Recall: "docker networking" [page 1/3] [buffer: 2]

  ★ 1. **tinyledger** — Feb 10 7:30p (4d ago) — "Bridge network setup"
    2. **athena** — Feb 3 2:15p (11d ago) — "DNS resolution"
  ★ 3. **paperfawn** — Jan 15 9:45a — "Traefik proxy"

→ more · expand N · pull N · done · save
```

This is 5-6 lines. Render it every time.

## Expansion

When the user asks to expand a result, **spawn a sub-agent** to read the session JSONL and extract detailed context. This protects the main conversation from context bloat.

The sub-agent should:
1. Use `search.py context` to extract turns around the match
2. Summarize the conversation arc
3. Extract key decisions, code snippets, files touched
4. Return a structured summary

Present the expansion like this:

```markdown
## Recall → Expanded #2: athena (Feb 3)

### Summary
[2-3 sentence summary of the conversation]

### Key Exchanges (N of M messages shown)
> You: [relevant user message]
> Claude: [relevant assistant response]
> You: [follow-up]
> Claude: [follow-up response]

### Decisions Made
- [Decision 1]
- [Decision 2]

### Files Touched
- path/to/file.py
- path/to/other.js

---
To resume this session:
  cd ~/develop/athena && claude -r abc12345
```

Then re-render the state header.

## Buffer

The buffer accumulates pulled results for injection into the current conversation.

- "pull N" → sub-agent reads and summarizes that session → adds to buffer
- Show confirmation: `Added to buffer (N items). Keep searching or say "done".`
- "done" → render all buffer items into the conversation as a `## Recall Buffer` section
- "save" → write buffer to `~/.claude/recalls/recall-<ISO-timestamp>.md`

Buffer items should be concise summaries (not full conversation dumps):

```markdown
## Recall Buffer (2 items)

### 1. tinyledger — Feb 10 — Docker bridge networking
**Context**: Setting up container networking for multi-service deploy.
**Solution**: Custom bridge network in compose with explicit aliases.
**Key config**: [relevant code snippet]
**Outcome**: All containers resolving by name.

### 2. athena — Feb 3 — DNS resolution fix
**Context**: Containers couldn't resolve each other on default bridge.
**Solution**: Switched from default to custom bridge network.
**Outcome**: Added network aliases, resolved immediately.

---
To resume: cd ~/develop/athena && claude -r e5f6g7h8
Saved from: /recall "docker networking" on Feb 14, 2026
```

## `/recall:history`

List saved recall files from `~/.claude/recalls/`:

```bash
ls -la ~/.claude/recalls/recall-*.md 2>/dev/null
```

Present as a simple list:

```markdown
## Saved Recalls

1. recall-2026-02-14T19-30-00.md — "docker networking" (2 items)
2. recall-2026-02-10T14-15-00.md — "auth setup" (1 item)
3. recall-2026-02-01T09-00-00.md — "deployment pipeline" (3 items)

→ "load N" to bring into context
```

Read the first few lines of each file to extract the query and item count.

## `/recall:load <file>`

Read the specified recall file and inject its contents into the conversation. Use the file number from `/recall:history` or the filename directly.

## Saving recall files

When the user says "save", write the buffer to:

```
~/.claude/recalls/recall-<YYYY-MM-DDTHH-MM-SS>.md
```

Create `~/.claude/recalls/` if it doesn't exist. The file should be the rendered buffer content (same markdown shown to the user), with a metadata header:

```markdown
---
query: "docker networking"
date: 2026-02-14T19:30:00Z
items: 2
sessions:
  - id: abc12345
    project: tinyledger
  - id: e5f6g7h8
    project: athena
---

[Buffer content here]
```

## Important behaviors

- **Exclude current session**: Don't return the session the user is currently in. Check the `CLAUDE_SESSION_ID` environment variable if available, or heuristically skip the most recent session in the current project directory.
- **Truncation safety**: Some messages are huge (file contents from Read tool). When extracting snippets, cap at ~200 chars and pick the most relevant sentence, not just the first 200 chars.
- **Dedup**: If the same session appears in both metadata and content results, merge them (prefer the richer result).
- **No context flooding**: Use sub-agents for expansion and pulling. The main context should only see the compact result cards and buffer summaries.
- **Cross-session awareness**: When multiple results cover the same topic across sessions, note it: "This topic appeared in 3 sessions spanning Feb 1-10" — this helps the user understand the thread.

## Uninstalling

Run `uninstall.sh` from the repo, or manually:
```bash
rm ~/.claude/skills/recall         # remove skill symlink
rm -rf ~/.claude/recalls/          # optional: remove saved recall history
```
