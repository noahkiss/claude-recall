#!/usr/bin/env python3
"""Claude Recall - Search engine for Claude Code conversation histories.

Searches session metadata and conversation content across all Claude Code
projects. Outputs structured JSON for consumption by the recall skill agent.

Requires: Python 3.8+, no external dependencies.
Optional: ripgrep (rg) for faster content search.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# typing imports compatible with 3.8
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CLAUDE_DIR = Path.home() / ".claude"

# Message types that contain actual conversation (not progress/hooks/etc)
CONVERSATION_TYPES = {"user", "assistant", "message"}

# Message types that are noise for search purposes
NOISE_TYPES = {"progress", "bash_progress", "hook_progress", "file-history-snapshot"}


# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------

def detect_search_tool():
    # type: () -> str
    """Detect best available text search tool."""
    try:
        subprocess.run(
            ["rg", "--version"], capture_output=True, check=True, timeout=5
        )
        return "rg"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["grep", "--version"], capture_output=True, text=True, timeout=5
        )
        if "GNU" in (result.stdout or ""):
            return "grep-gnu"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "grep-bsd"


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------

def format_timestamp(iso_str, now=None):
    # type: (str, Optional[datetime]) -> str
    """Format ISO timestamp as 'Feb 10 7:30p (4 days ago)' style.

    - Always shows date + time
    - Relative '(Nd ago)' only for < 14 days
    """
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        if iso_str.endswith("Z"):
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return str(iso_str)

    # "Feb 10" — use dt.day to avoid platform-specific strftime flags
    month = dt.strftime("%b")
    date_str = "{} {}".format(month, dt.day)

    # "7:30p"
    hour = dt.hour % 12
    if hour == 0:
        hour = 12
    minute = dt.strftime("%M")
    ampm = "a" if dt.hour < 12 else "p"
    time_str = "{}:{}{}".format(hour, minute, ampm)

    # Relative time (only < 14 days)
    delta = now - dt
    days = delta.days
    relative = ""

    if 0 <= days < 1:
        hours = delta.seconds // 3600
        if hours == 0:
            minutes = delta.seconds // 60
            if minutes > 0:
                relative = " ({}m ago)".format(minutes)
            else:
                relative = " (just now)"
        else:
            relative = " ({}h ago)".format(hours)
    elif days == 1:
        relative = " (yesterday)"
    elif 1 < days < 14:
        relative = " ({}d ago)".format(days)

    return "{}  {}{}".format(date_str, time_str, relative)


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def resolve_project_name(project_path):
    # type: (str) -> str
    """Extract human-readable project name from path."""
    if not project_path:
        return "unknown"
    return Path(project_path).name


def decode_project_dir(dirname):
    # type: (str) -> str
    """Decode a project dir name like '-home-flight-develop-tinyledger' to a path.

    This is best-effort — the encoding isn't perfectly reversible.
    """
    return "/" + dirname.lstrip("-").replace("-", "/")


def _load_session_index(project_dir):
    # type: (Path) -> Optional[Dict]
    """Load sessions-index.json for a project directory."""
    index_file = project_dir / "sessions-index.json"
    if not index_file.exists():
        return None
    try:
        with open(str(index_file), "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def _iter_project_dirs(claude_dir):
    # type: (Path) -> List[Tuple[Path, str, str]]
    """Iterate project directories, yielding (dir, project_name, project_path)."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return []

    results = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        index = _load_session_index(project_dir)
        if index is not None:
            project_path = index.get("originalPath", decode_project_dir(project_dir.name))
        else:
            project_path = decode_project_dir(project_dir.name)
        project_name = resolve_project_name(project_path)
        results.append((project_dir, project_name, project_path))
    return results


# ---------------------------------------------------------------------------
# Text extraction from JSONL message objects
# ---------------------------------------------------------------------------

def _extract_text(obj):
    # type: (Dict) -> str
    """Extract text content from a JSONL message object."""
    # Direct text field
    if isinstance(obj.get("text"), str):
        return obj["text"]

    # Message with content (user/assistant messages)
    msg = obj.get("message", obj)
    content = msg.get("content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
        return " ".join(texts)

    return ""


def _get_message_role(obj):
    # type: (Dict) -> Optional[str]
    """Get the conversation role (user/assistant) from a JSONL object, or None."""
    msg_type = obj.get("type")

    if msg_type in ("user", "assistant"):
        return msg_type
    if msg_type == "message":
        role = obj.get("message", {}).get("role", "")
        if role in ("user", "assistant"):
            return role
    return None


# ---------------------------------------------------------------------------
# Phase 1: Metadata search
# ---------------------------------------------------------------------------

def search_metadata(query, claude_dir=DEFAULT_CLAUDE_DIR):
    # type: (str, Path) -> List[Dict]
    """Search session summaries and first prompts across all projects."""
    results = []
    query_lower = query.lower()

    for project_dir, project_name, project_path in _iter_project_dirs(claude_dir):
        index = _load_session_index(project_dir)
        if index is None:
            continue

        for entry in index.get("entries", []):
            summary = entry.get("summary") or ""
            first_prompt = entry.get("firstPrompt") or ""

            match_fields = []
            if query_lower in summary.lower():
                match_fields.append("summary")
            if query_lower in first_prompt.lower():
                match_fields.append("firstPrompt")

            if match_fields:
                results.append({
                    "sessionId": entry.get("sessionId", ""),
                    "project": project_name,
                    "projectPath": project_path,
                    "projectDir": str(project_dir),
                    "summary": summary,
                    "firstPrompt": first_prompt[:300],
                    "created": entry.get("created", ""),
                    "modified": entry.get("modified", ""),
                    "messageCount": entry.get("messageCount", 0),
                    "gitBranch": entry.get("gitBranch", ""),
                    "matchFields": match_fields,
                    "fullPath": entry.get("fullPath", ""),
                    "isSidechain": entry.get("isSidechain", False),
                })

    results.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Phase 2: Content search
# ---------------------------------------------------------------------------

def _collect_jsonl_files(claude_dir, project_filter=None, include_subagents=False):
    # type: (Path, Optional[str], bool) -> List[Tuple[str, Path]]
    """Collect JSONL file paths to search, with their project dirs."""
    files = []

    for project_dir, project_name, project_path in _iter_project_dirs(claude_dir):
        if project_filter and project_filter.lower() not in project_name.lower():
            continue

        # Main session files (directly in project dir)
        for f in project_dir.iterdir():
            if f.suffix == ".jsonl" and f.is_file():
                files.append((str(f), project_dir))

        # Subagent files (nested under session dirs)
        if include_subagents:
            for child in project_dir.iterdir():
                if child.is_dir():
                    subagent_dir = child / "subagents"
                    if subagent_dir.exists():
                        for f in subagent_dir.iterdir():
                            if f.suffix == ".jsonl":
                                files.append((str(f), project_dir))

    return files


def _grep_for_matches(query, file_paths, search_tool):
    # type: (str, List[str], str) -> List[str]
    """Find files containing query using rg or grep. Returns matching file paths."""
    if not file_paths:
        return []

    # Batch file paths to avoid argument-too-long errors
    # ARG_MAX is typically 128KB-2MB; stay well under with ~500 files per batch
    batch_size = 500
    matching = []

    for i in range(0, len(file_paths), batch_size):
        batch = file_paths[i : i + batch_size]

        try:
            if search_tool == "rg":
                cmd = ["rg", "-l", "-i", "--no-messages", "--", query] + batch
            else:
                # Works for both GNU and BSD grep
                cmd = ["grep", "-l", "-i", "--", query] + batch

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    matching.append(line)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # If search tool fails, fall back to Python-native search
            matching.extend(_python_grep(query, batch))

    return matching


def _python_grep(query, file_paths):
    # type: (str, List[str]) -> List[str]
    """Pure-Python fallback for finding files containing query."""
    query_lower = query.lower()
    matching = []
    for fp in file_paths:
        try:
            with open(fp, "r") as f:
                for line in f:
                    if query_lower in line.lower():
                        matching.append(fp)
                        break
        except (IOError, OSError):
            continue
    return matching


def _extract_content_matches(filepath, query):
    # type: (str, str) -> List[Dict]
    """Extract matching user/assistant messages from a JSONL file."""
    matches = []
    query_lower = query.lower()

    try:
        with open(filepath, "r") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = _get_message_role(obj)
                if role is None:
                    continue

                text = _extract_text(obj)
                if not text or query_lower not in text.lower():
                    continue

                matches.append({
                    "role": role,
                    "text": text[:300],
                    "timestamp": obj.get("timestamp", ""),
                    "uuid": obj.get("uuid", ""),
                    "lineNumber": line_num,
                })
    except (IOError, OSError):
        pass

    return matches


def _find_session_entry(index_data, filepath):
    # type: (Dict, str) -> Optional[Dict]
    """Find the session index entry matching a JSONL filepath."""
    stem = Path(filepath).stem
    for entry in index_data.get("entries", []):
        if entry.get("sessionId", "") == stem:
            return entry
        full = entry.get("fullPath", "")
        if full and Path(full).stem == stem:
            return entry
    return None


def search_content(
    query,
    claude_dir=DEFAULT_CLAUDE_DIR,
    project=None,
    after=None,
    before=None,
    limit=20,
    include_subagents=False,
):
    # type: (str, Path, Optional[str], Optional[str], Optional[str], int, bool) -> List[Dict]
    """Search conversation content across JSONL files."""
    search_tool = detect_search_tool()
    file_tuples = _collect_jsonl_files(claude_dir, project, include_subagents)

    if not file_tuples:
        return []

    file_paths = [fp for fp, _ in file_tuples]
    file_to_project = {fp: pd for fp, pd in file_tuples}

    matching_files = _grep_for_matches(query, file_paths, search_tool)

    results = []
    for filepath in matching_files[:limit]:
        project_dir = file_to_project.get(filepath)
        if not project_dir:
            continue

        # Get project + session metadata
        index = _load_session_index(project_dir)
        project_path = ""
        project_name = "unknown"
        session_summary = ""
        session_created = ""
        session_id = Path(filepath).stem
        message_count = 0
        git_branch = ""

        if index:
            project_path = index.get("originalPath", "")
            project_name = resolve_project_name(project_path)
            entry = _find_session_entry(index, filepath)
            if entry:
                session_summary = entry.get("summary", "")
                session_created = entry.get("created", "")
                session_id = entry.get("sessionId", session_id)
                message_count = entry.get("messageCount", 0)
                git_branch = entry.get("gitBranch", "")

        # Apply date filters
        if after and session_created and session_created < after:
            continue
        if before and session_created and session_created > before:
            continue

        # Extract the actual matching conversation turns
        matches = _extract_content_matches(filepath, query)
        if not matches:
            continue

        is_subagent = "/subagents/" in filepath

        results.append({
            "sessionId": session_id,
            "project": project_name,
            "projectPath": project_path,
            "projectDir": str(project_dir),
            "sessionSummary": session_summary,
            "created": session_created,
            "messageCount": message_count,
            "gitBranch": git_branch,
            "filePath": filepath,
            "isSubagent": is_subagent,
            "matches": matches[:5],
            "matchCount": len(matches),
        })

    results.sort(key=lambda x: x.get("created", ""), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Phase 3: Context extraction
# ---------------------------------------------------------------------------

def extract_context(session_file, line_number=None, uuid=None, turns=3):
    # type: (str, Optional[int], Optional[str], int) -> List[Dict]
    """Extract conversation turns around a specific match point.

    Returns conversation turns (user/assistant only) within `turns`
    messages of the target line/uuid.
    """
    messages = []
    target_idx = None

    try:
        with open(session_file, "r") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = _get_message_role(obj)
                if role is None:
                    continue

                text = _extract_text(obj)
                if not text:
                    continue

                idx = len(messages)
                messages.append({
                    "role": role,
                    "text": text[:2000],
                    "timestamp": obj.get("timestamp", ""),
                    "uuid": obj.get("uuid", ""),
                    "lineNumber": line_num,
                })

                if line_number is not None and line_num == line_number:
                    target_idx = idx
                elif uuid and obj.get("uuid") == uuid:
                    target_idx = idx
    except (IOError, OSError):
        return []

    if target_idx is None:
        # No target — return last N turns as fallback
        return messages[-(turns * 2) :] if messages else []

    start = max(0, target_idx - turns)
    end = min(len(messages), target_idx + turns + 1)
    return messages[start:end]


# ---------------------------------------------------------------------------
# Project listing
# ---------------------------------------------------------------------------

def list_projects(claude_dir=DEFAULT_CLAUDE_DIR):
    # type: (Path) -> List[Dict]
    """List all projects with session counts and activity info."""
    results = []

    for project_dir, project_name, project_path in _iter_project_dirs(claude_dir):
        index = _load_session_index(project_dir)
        if index is None:
            continue

        entries = index.get("entries", [])
        if not entries:
            continue

        total_messages = sum(e.get("messageCount", 0) for e in entries)
        dates = [e.get("modified", "") for e in entries if e.get("modified")]
        last_active = max(dates) if dates else ""

        results.append({
            "project": project_name,
            "projectPath": project_path,
            "projectDir": str(project_dir),
            "sessionCount": len(entries),
            "totalMessages": total_messages,
            "lastActive": last_active,
        })

    results.sort(key=lambda x: x.get("lastActive", ""), reverse=True)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search Claude Code conversation histories",
        prog="search.py",
    )
    parser.add_argument(
        "--claude-dir",
        type=Path,
        default=DEFAULT_CLAUDE_DIR,
        help="Claude config directory (default: ~/.claude)",
    )

    subparsers = parser.add_subparsers(dest="command")
    # Python 3.8: required=True not supported on add_subparsers in 3.8,
    # handle missing command below
    subparsers.required = True

    # -- metadata --
    p_meta = subparsers.add_parser(
        "metadata", help="Search session metadata (summaries, first prompts)"
    )
    p_meta.add_argument("query", help="Search query")

    # -- content --
    p_content = subparsers.add_parser(
        "content", help="Search conversation content (full text)"
    )
    p_content.add_argument("query", help="Search query")
    p_content.add_argument("--project", help="Filter by project name")
    p_content.add_argument("--after", help="Only sessions created after date (ISO)")
    p_content.add_argument("--before", help="Only sessions created before date (ISO)")
    p_content.add_argument(
        "--limit", type=int, default=20, help="Max file results (default: 20)"
    )
    p_content.add_argument(
        "--include-subagents",
        action="store_true",
        help="Include sub-agent conversations",
    )

    # -- context --
    p_ctx = subparsers.add_parser(
        "context", help="Extract conversation turns around a match"
    )
    p_ctx.add_argument("session_file", help="Path to session JSONL file")
    p_ctx.add_argument("--line", type=int, help="Line number of the match")
    p_ctx.add_argument("--uuid", help="UUID of the target message")
    p_ctx.add_argument(
        "--turns", type=int, default=3, help="Turns of context each direction (default: 3)"
    )

    # -- projects --
    subparsers.add_parser("projects", help="List all projects with session counts")

    # -- format-time --
    p_fmt = subparsers.add_parser("format-time", help="Format an ISO timestamp")
    p_fmt.add_argument("timestamp", help="ISO timestamp string")

    # -- version --
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    if args.command == "metadata":
        results = search_metadata(args.query, args.claude_dir)
        json.dump(results, sys.stdout, indent=2)
        print()  # trailing newline

    elif args.command == "content":
        results = search_content(
            args.query,
            claude_dir=args.claude_dir,
            project=args.project,
            after=args.after,
            before=args.before,
            limit=args.limit,
            include_subagents=args.include_subagents,
        )
        json.dump(results, sys.stdout, indent=2)
        print()

    elif args.command == "context":
        results = extract_context(
            args.session_file,
            line_number=args.line,
            uuid=args.uuid,
            turns=args.turns,
        )
        json.dump(results, sys.stdout, indent=2)
        print()

    elif args.command == "projects":
        results = list_projects(args.claude_dir)
        json.dump(results, sys.stdout, indent=2)
        print()

    elif args.command == "format-time":
        print(format_timestamp(args.timestamp))

    elif args.command == "version":
        print("claude-recall 0.1.0")


if __name__ == "__main__":
    main()
