# Claude Code Session Storage Reference

Technical reference for how Claude Code stores conversation data. Used by `search.py` to locate and parse sessions.

## Directory Layout

```
~/.claude/
├── projects/                              # All project-scoped data
│   ├── -home-flight-develop-project/      # Project dir (hashed path)
│   │   ├── sessions-index.json            # Session metadata index
│   │   ├── <session-uuid>.jsonl           # Conversation file
│   │   ├── <session-uuid>/                # Session artifacts
│   │   │   ├── subagents/
│   │   │   │   └── agent-<hash>.jsonl     # Sub-agent conversations
│   │   │   └── tool-results/
│   │   │       └── toolu_<id>.txt         # Cached tool outputs
│   │   └── memory/
│   │       └── MEMORY.md                  # Optional project memory
│   └── ...
├── history.jsonl                          # Global command history (not conversations)
└── recalls/                               # Saved recall results (created by this skill)
```

## sessions-index.json

Metadata index per project. This is the primary target for Phase 1 (metadata) search.

```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "uuid",
      "fullPath": "/absolute/path/to/session.jsonl",
      "fileMtime": 1706234567890,
      "firstPrompt": "First user message text",
      "summary": "Auto-generated session title",
      "messageCount": 78,
      "created": "2026-01-26T03:35:03.917Z",
      "modified": "2026-01-26T07:19:04.022Z",
      "gitBranch": "main",
      "projectPath": "/home/user/develop/project-name",
      "isSidechain": false
    }
  ],
  "originalPath": "/home/user/develop/project-name"
}
```

### Key fields

| Field | Use |
|-------|-----|
| `sessionId` | Unique ID — use for resume command (`claude -r <id>`) |
| `summary` | Auto-generated title — primary metadata search target |
| `firstPrompt` | First user message — secondary metadata search target |
| `messageCount` | Conversation depth indicator for ranking |
| `created` / `modified` | Timestamps for date filtering and recency ranking |
| `gitBranch` | Git context at time of conversation |
| `projectPath` | Human-readable project location |
| `isSidechain` | Whether this was a branched conversation |

## Conversation JSONL Format

Each line is a JSON object. Relevant message types for search:

### User messages
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": "the user's message text"
  },
  "timestamp": "2026-02-10T19:30:00.000Z",
  "uuid": "unique-id",
  "sessionId": "session-uuid",
  "cwd": "/working/directory",
  "gitBranch": "main"
}
```

### Assistant messages
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "response text"},
      {"type": "tool_use", "name": "Read", "input": {"file_path": "/path"}}
    ]
  },
  "timestamp": "2026-02-10T19:30:05.000Z",
  "uuid": "unique-id"
}
```

### Content extraction

Message content can be:
- A plain string: `"content": "hello"`
- An array of blocks: `"content": [{"type": "text", "text": "hello"}, ...]`

Always handle both formats. Only extract `type: "text"` blocks — skip `tool_use`, `tool_result`, etc.

### Noise types to skip

These message types are NOT conversation content:

| Type | What it is |
|------|------------|
| `progress` | Hook/command progress events |
| `bash_progress` | Bash execution status |
| `hook_progress` | Hook execution status |
| `file-history-snapshot` | File version snapshots |
| `thinking` | Extended thinking (may contain useful reasoning but very noisy) |
| `tool_use` / `tool_result` | Tool invocations and returns |

## Project Directory Name Encoding

Project directories are named by encoding the filesystem path:
- `/home/flight/develop/tinyledger` → `-home-flight-develop-tinyledger`
- Leading `/` becomes `-`, all `/` become `-`

This encoding is not perfectly reversible (ambiguous if path segments contain hyphens), but `sessions-index.json` contains the `originalPath` field which is authoritative.

## Sub-agent Conversations

Sub-agent JSONL files follow the same format as main sessions. They are stored under:
```
<session-uuid>/subagents/agent-<hash>.jsonl
```

Sub-agent conversations often contain the actual implementation details while the parent session has the high-level discussion. Include them in search when thoroughness matters, but down-rank in results since the parent session provides better context.
