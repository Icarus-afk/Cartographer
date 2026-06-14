from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from cartographer.compression.engine import estimate_tokens
from cartographer.git.engine import (
    co_change_analysis, get_node_history, list_authors, why_introduced,
)
from cartographer.retrieval.searcher import search_nodes
from cartographer.retrieval.summarizer import generate_summary
from cartographer.retrieval.traversal import find_path, impact_analysis

# Pattern list: (intent_type, category, [(priority, pattern, target_group), ...])
# target_group: 0 = use entire query, >0 = use that captured group, -1 = use all captured groups

INTENT_RULES: list[tuple[str, str, list[tuple[int, re.Pattern[str], int]]]] = [
    ("architecture", "architecture", [
        (10, re.compile(r"\barchitecture\b"), 0),
        (10, re.compile(r"\blayers?\b"), 0),
        (10, re.compile(r"\bpatterns?\b"), 0),
        (10, re.compile(r"(how is|how are).*(organized|structured)"), 0),
    ]),
    ("summarize", "summarize", [
        (10, re.compile(r"\boverview\b"), 0),
        (10, re.compile(r"\bsummarize\b"), 0),
        (10, re.compile(r"what (is this|does this)"), 0),
        (10, re.compile(r"describe (the )?(project|repo|codebase)"), 0),
        (10, re.compile(r"tell me about"), 0),
    ]),
    ("path", "path", [
        (10, re.compile(r"\brelationship\b"), 0),
        (5, re.compile(r"path (?:between|from)\s+(\S+)\s+(?:and|to)\s+(\S+)"), -1),
        (5, re.compile(r"(?:how are|connection between)\s+(\S+)\s+(?:and|to)\s+(\S+)"), -1),
    ]),
    ("git_blame", "git", [
        (10, re.compile(r"\bauthors?\b"), 0),
        (5, re.compile(r"who (wrote|changed|made|created|authored)\s+(\S+)"), 2),
        (5, re.compile(r"\bblame\s+(\S+)"), 1),
        (5, re.compile(r"history of\s+(\S+)"), 1),
    ]),
    ("git_why", "git", [
        (5, re.compile(r"why (was|is|does)\s+(\S+)"), 2),
        (5, re.compile(r"\bintroduced\s+(\S+)"), 1),
    ]),
    ("git_cochange", "git", [
        (5, re.compile(r"what changes (with|together)\s+(\S+)"), 2),
        (5, re.compile(r"\bco-change\b"), 0),
    ]),
    ("impact", "impact", [
        (5, re.compile(
            r"(what depends on|what uses|who calls|dependents of|impact of)\s+(\S+)"
        ), 2),
        (3, re.compile(r"\bimpact\b"), 0),
        (3, re.compile(r"\bdependents?\b"), 0),
    ]),
    ("explain", "explain", [
        (5, re.compile(r"(?:what is|what's|explain|describe)\s+([A-Z]\w+)"), 1),
        (5, re.compile(r"how does\s+(\S+)\s+work"), 1),
        (5, re.compile(r"what does\s+(\S+)\s+do"), 1),
    ]),
]


def _extract_targets(query: str, rules: list[tuple[int, re.Pattern[str], int]]) -> list[str] | None:
    best: tuple[int, list[str]] | None = None
    for priority, pattern, target_group in rules:
        m = pattern.search(query)
        if m:
            if target_group == 0:
                return []
            if target_group == -1:
                targets = [g for g in m.groups() if g]
                if best is None or priority > best[0]:
                    best = (priority, targets)
            else:
                target = m.group(target_group)
                if best is None or priority > best[0]:
                    best = (priority, [target])
    return best[1] if best else None

def classify_intent(query: str) -> dict[str, Any]:
    for intent_type, category, rules in INTENT_RULES:
        targets = _extract_targets(query, rules)
        if targets is not None:
            return {
                "type": intent_type,
                "category": category,
                "targets": targets if targets else [query],
                "confidence": 0.8,
            }

    has_word = re.search(r"[A-Z]\w+", query)
    confidence = 0.5 if has_word else 0.3
    return {"type": "search", "category": "search", "targets": [query], "confidence": confidence}


def _search_step(query: str, db_path: Path, repo: str | None, limit: int) -> str:
    results = search_nodes(query, db_path, repo, None, limit)
    if not results:
        return "No matching nodes found."

    lines = [f"Found {len(results)} matching node(s):"]
    for r in results:
        type_label = r["type"].ljust(12)
        lines.append(f"  [{type_label}] {r['name']}")
        if r["file_path"]:
            lines.append(f"           {r['file_path']}")
    return "\n".join(lines)


def _summarize_step(db_path: Path, repo: str | None) -> str:
    summary = generate_summary(db_path, repo)
    if not summary:
        return "No repository data found."

    top_types = sorted(summary["node_breakdown"].items(), key=lambda x: -x[1])[:5]
    top_types_str = ", ".join(f"{t}: {c}" for t, c in top_types)
    top_files_str = ", ".join(f["name"] for f in summary.get("top_files", [])[:5])
    return (
        f"Repository: {summary['name']}\n"
        f"Nodes: {summary['total_nodes']}, Edges: {summary['total_edges']}\n"
        f"Top types: {top_types_str}\n"
        f"Top files: {top_files_str}"
    )


def _explain_step(
    targets: list[str], db_path: Path, repo: str | None, limit: int
) -> str:
    if not targets:
        return ""
    target = targets[0]

    lines = [f"--- {target} ---"]

    nodes = search_nodes(target, db_path, repo, limit=limit)
    if nodes:
        lines.append(f"Found {len(nodes)} node(s):")
        for n in nodes[:5]:
            lines.append(f"  [{n['type']}] {n['name']} ({n['file_path']})")

    impacts = impact_analysis(target, db_path, repo)
    if impacts:
        by_edge: dict[str, int] = {}
        for imp in impacts:
            edge = imp.get("via_edge", "?")
            by_edge[edge] = by_edge.get(edge, 0) + 1
        sorted_edges = sorted(by_edge.items(), key=lambda x: -x[1])
        edge_summary = ", ".join(f"{k}: {v}" for k, v in sorted_edges)
        lines.append(f"Dependents: {len(impacts)} ({edge_summary})")

    return "\n".join(lines)


def _impact_step(
    targets: list[str], db_path: Path, repo: str | None
) -> str:
    if not targets:
        return ""

    results = impact_analysis(targets[0], db_path, repo)
    if not results:
        return f"No dependents found for '{targets[0]}'."

    by_edge: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_edge.setdefault(r.get("via_edge", "UNKNOWN"), []).append(r)

    lines = [f"Impact analysis for '{targets[0]}' — {len(results)} dependents:"]
    for edge_type, nodes in sorted(by_edge.items(), key=lambda x: -len(x[1])):
        lines.append(f"  Via {edge_type} ({len(nodes)}):")
        for n in nodes[:3]:
            lines.append(f"    [{n['type']}] {n['name']} ({n['file_path']})")
        if len(nodes) > 3:
            lines.append(f"    ... and {len(nodes) - 3} more")

    return "\n".join(lines)


def _path_step(
    targets: list[str], db_path: Path, repo: str | None
) -> str:
    if len(targets) < 2:
        return "Need two targets to find a path."
    results = find_path(targets[0], targets[1], db_path, repo_name=repo)
    if not results:
        return f"No path found between '{targets[0]}' and '{targets[1]}'."
    lines = [f"Path ({len(results)} hops):"]
    for r in results:
        arrow = " → " if r.get("depth", 0) > 0 else "   "
        lines.append(f"  {arrow}[{r['type']}] {r['name']}")
        if r["file_path"]:
            lines.append(f"      {r['file_path']}")
    return "\n".join(lines)


def _architecture_step(db_path: Path, repo: str | None) -> str:
    from cartographer.architecture.engine import detect_architecture

    result = detect_architecture(db_path, repo)
    if "error" in result:
        return result["error"]

    lines = [f"Architecture: {result.get('repository', '?')}"]

    if result.get("frameworks"):
        lines.append("Frameworks:")
        for fw in result["frameworks"]:
            lines.append(f"  {fw['name']} ({round(fw['confidence'] * 100)}% confidence)")

    if result.get("patterns"):
        lines.append("Patterns:")
        for p in result["patterns"]:
            lines.append(f"  {p['name']} ({round(p['confidence'] * 100)}% confidence)")

    if result.get("layers"):
        lines.append("Layers:")
        for name, info in list(result["layers"].items())[:8]:
            lines.append(f"  {info['description']} ({info['entity_count']} entities)")

    return "\n".join(lines) or "No architecture detected."


def _build_summarize(intent, db_path, repo, limit, max_tokens):
    return _summarize_step(db_path, repo)


def _build_explain(intent, db_path, repo, limit, max_tokens):
    return _explain_step(intent["targets"], db_path, repo, limit)


def _build_impact(intent, db_path, repo, limit, max_tokens):
    return _impact_step(intent["targets"], db_path, repo)


def _build_path(intent, db_path, repo, limit, max_tokens):
    return _path_step(intent["targets"], db_path, repo)


def _build_architecture(intent, db_path, repo, limit, max_tokens):
    return _architecture_step(db_path, repo)


def _build_search(intent, db_path, repo, limit, max_tokens):
    return _search_step(intent["targets"][0], db_path, repo, limit)


def _build_git_blame(intent, db_path, repo, limit, max_tokens):
    targets = intent.get("targets", [])
    if not targets:
        authors = list_authors(db_path, repo_name=repo, limit=limit)
        if not authors:
            return "No authors found."
        lines = ["Authors:"]
        for a in authors:
            lines.append(f"  {a['name']} ({a['email']}) — {a['commit_count']} commits")
        return "\n".join(lines)

    target = targets[0]
    history = get_node_history(db_path, target, repo_name=repo, limit=limit)
    if not history:
        return f"No history found for '{target}'."
    lines = [f"History of '{target}':"]
    for h in history:
        lines.append(f"  {h['committed_at']} | {h['author']} | {h['message']}")
    return "\n".join(lines)


def _build_git_why(intent, db_path, repo, limit, max_tokens):
    targets = intent.get("targets", [])
    if not targets:
        return "What do you want to know about?"
    result = why_introduced(db_path, targets[0], repo_name=repo)
    if not result:
        return f"Could not determine why '{targets[0]}' was introduced."
    return (
        f"'{result['target']}' ({result['file_path']}) "
        f"was introduced in commit {result['introduced_in'][:8]} "
        f"by {result['by']} on {result['committed_at']}:\n"
        f"  {result['message']}"
    )


def _build_git_cochange(intent, db_path, repo, limit, max_tokens):
    targets = intent.get("targets", [])
    if not targets:
        return "What file do you want to analyze?"
    from cartographer.retrieval.traversal import _resolve_target
    from cartographer.storage.connection import get_connection

    conn = get_connection(db_path)
    node = _resolve_target(conn, targets[0], repo)
    conn.close()
    if not node or not node.get("file_path"):
        return f"Could not find '{targets[0]}'."

    changes = co_change_analysis(db_path, node["file_path"], repo_name=repo, limit=limit)
    if not changes:
        return f"No co-changes found for '{targets[0]}'."
    lines = [f"Files that change with '{targets[0]}':"]
    for c in changes:
        lines.append(f"  {c['file_path']} ({c['co_occurrences']} times)")
    return "\n".join(lines)


PLAN_BUILDERS: dict[str, Any] = {
    "summarize": _build_summarize,
    "explain": _build_explain,
    "impact": _build_impact,
    "path": _build_path,
    "architecture": _build_architecture,
    "git_blame": _build_git_blame,
    "git_why": _build_git_why,
    "git_cochange": _build_git_cochange,
    "search": _build_search,
}


def execute_query(
    query: str,
    db_path: Path,
    repo: str | None = None,
    limit: int = 20,
    max_tokens: int = 0,
) -> str:
    intent = classify_intent(query)
    intent_type = intent["type"]
    builder = PLAN_BUILDERS.get(intent_type)
    if not builder:
        builder = PLAN_BUILDERS["search"]

    result = builder(intent, db_path, repo, limit, max_tokens)

    if max_tokens and isinstance(result, str):
        if estimate_tokens(result) > max_tokens:
            parts = result.split("\n")
            while estimate_tokens("\n".join(parts)) > max_tokens and len(parts) > 3:
                parts.pop()
            parts.append("...")
            return "\n".join(parts)
        return result

    return result
