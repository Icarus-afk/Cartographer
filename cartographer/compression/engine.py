from __future__ import annotations

from typing import Any


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def compress_nodes(
    nodes: list[dict[str, Any]],
    max_tokens: int = 500,
    *,
    group: bool = True,
) -> str:
    if not nodes:
        return "No results."

    budget = max_tokens

    type_counts: dict[str, int] = {}
    file_counts: dict[str, list[str]] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        file_path = n.get("file_path") or ""
        if file_path:
            file_counts.setdefault(file_path, []).append(n.get("name", "?"))

    parts: list[str] = []
    parts.append(f"Found {len(nodes)} result(s):")

    if group and len(nodes) > 10:
        for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            parts.append(f"  {t}: {cnt}")
        budget_left = budget - estimate_tokens("\n".join(parts))
        if budget_left > 20 and file_counts:
            file_parts = []
            for fpath in list(file_counts.keys())[:max(1, budget_left // 30)]:
                names = file_counts[fpath]
                file_parts.append(f"  {fpath} ({len(names)} entities)")
            if file_parts:
                parts.append("  Files:")
                parts.extend(file_parts)
    else:
        for n in nodes:
            type_label = n.get("type", "?").ljust(12)
            line = f"  [{type_label}] {n.get('name', '?')}"
            fp = n.get("file_path")
            if fp:
                line += f" ({fp})"
            parts.append(line)

    result = "\n".join(parts)
    if estimate_tokens(result) > budget:
        result = _truncate_lines(parts, budget, "  ...")

    return result


def compress_impact(
    results: list[dict[str, Any]],
    max_tokens: int = 500,
) -> str:
    if not results:
        return "No dependents found."

    by_edge: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_edge.setdefault(r.get("via_edge", "UNKNOWN"), []).append(r)

    parts: list[str] = [f"Impact analysis — {len(results)} dependents:"]
    for edge_type, nodes in sorted(by_edge.items(), key=lambda x: -len(x[1])):
        parts.append(f"  Via {edge_type} ({len(nodes)}):")
        if len(parts) * 10 > max_tokens:
            parts.append("    ...")
            break
        for n in nodes[:max(1, (max_tokens - estimate_tokens("\n".join(parts))) // 40)]:
            parts.append(f"    [{n.get('type', '?')}] {n.get('name', '?')}")
            file_path = n.get("file_path")
            if file_path:
                parts[-1] += f" ({file_path})"

    return _truncate_lines(parts, max_tokens, "  ...")


def compress_path(
    path_results: list[dict[str, Any]],
    max_tokens: int = 500,
) -> str:
    if not path_results:
        return "No path found."

    parts: list[str] = [f"Path ({len(path_results)} hops):"]
    for r in path_results:
        if estimate_tokens("\n".join(parts)) > max_tokens:
            parts.append("  ...")
            break
        arrow = " → " if r.get("depth", 0) > 0 else "   "
        line = f"  {arrow}[{r.get('type', '?')}] {r.get('name', '?')}"
        file_path = r.get("file_path")
        if file_path:
            line += f" ({file_path})"
        parts.append(line)

    return "\n".join(parts)


def compress_summary(
    summary: dict[str, Any],
    max_tokens: int = 500,
) -> str:
    if not summary:
        return "No summary available."

    parts: list[str] = [
        f"Repository: {summary.get('name', '?')}",
        f"  Path: {summary.get('path', '?')}",
        f"  Nodes: {summary.get('total_nodes', 0)}",
        f"  Edges: {summary.get('total_edges', 0)}",
    ]

    node_breakdown = summary.get("node_breakdown", {})
    if node_breakdown:
        parts.append("  Nodes by type:")
        for ntype, count in sorted(node_breakdown.items(), key=lambda x: -x[1])[:8]:
            parts.append(f"    {ntype}: {count}")

    edge_breakdown = summary.get("edge_breakdown", {})
    if edge_breakdown:
        parts.append("  Edges by type:")
        for etype, count in sorted(edge_breakdown.items(), key=lambda x: -x[1])[:6]:
            parts.append(f"    {etype}: {count}")

    for key, label in [("top_files", "Top files"), ("top_classes", "Largest classes")]:
        items = summary.get(key, [])
        if items:
            parts.append(f"  {label}:")
            for item in items[:max(1, (max_tokens - estimate_tokens("\n".join(parts))) // 25)]:
                item_name = item.get("name", "?")
                if "entities" in item:
                    parts.append(f"    {item_name} ({item['entities']} entities)")
                elif "methods" in item:
                    parts.append(f"    {item_name} ({item['methods']} methods)")

    return _truncate_lines(parts, max_tokens, "  ...")


def compress_architecture(
    arch: dict[str, Any],
    max_tokens: int = 500,
) -> str:
    if not arch:
        return "No architecture data available."

    parts: list[str] = [
        f"Architecture: {arch.get('repository', '?')}",
    ]
    if "error" in arch:
        parts.append(f"  Error: {arch['error']}")
        return "\n".join(parts)

    layers = arch.get("layers", {})
    if layers:
        parts.append("  Layers:")
        for lname, info in layers.items():
            desc = info.get("description", lname)
            conf = info.get("confidence", 0)
            count = info.get("entity_count", 0)
            parts.append(f"    {desc} (confidence={conf}, entities={count})")

    patterns = arch.get("patterns", [])
    if patterns:
        parts.append("  Patterns:")
        for p in patterns[:4]:
            parts.append(f"    {p.get('name', '?')} (confidence={p.get('confidence', 0)})")

    domains = arch.get("domains", [])
    if domains:
        parts.append("  Domains:")
        for d in domains[:5]:
            d_name = d.get("name", "?")
            d_type = d.get("type", "?")
            d_conf = d.get("confidence", 0)
            d_files = d.get("file_count", 0)
            parts.append(f"    {d_name} (type={d_type}, conf={d_conf}, files={d_files})")

    return _truncate_lines(parts, max_tokens, "  ...")


def build_context_package(
    summary: dict[str, Any],
    architecture: dict[str, Any] | None = None,
    top_nodes: list[dict[str, Any]] | None = None,
    max_tokens: int = 1500,
) -> str:
    if not summary:
        return "No data available."

    token_budget = max_tokens
    sections: list[str] = []
    current_tokens = 0

    section1 = compress_summary(summary, max_tokens // 3)
    sections.append("## Graph Summary\n" + section1)
    current_tokens += estimate_tokens(section1)

    if architecture and current_tokens < token_budget:
        remaining = token_budget - current_tokens
        section2 = compress_architecture(architecture, max(remaining, 50))
        sections.append("## Architecture\n" + section2)
        current_tokens += estimate_tokens(section2)

    if top_nodes and current_tokens < token_budget:
        remaining = token_budget - current_tokens
        section3 = compress_nodes(top_nodes, max(remaining, 50))
        sections.append("## Key Nodes\n" + section3)
        current_tokens += estimate_tokens(section3)

    result = "\n\n".join(sections)
    if estimate_tokens(result) > max_tokens:
        return _truncate_lines(sections, max_tokens, "\n...")
    return result


def compress(
    data: Any,
    max_tokens: int = 500,
    data_type: str = "nodes",
) -> str:
    if data_type == "nodes":
        return compress_nodes(data, max_tokens)
    elif data_type == "impact":
        return compress_impact(data, max_tokens)
    elif data_type == "path":
        return compress_path(data, max_tokens)
    elif data_type == "summary":
        return compress_summary(data, max_tokens)
    else:
        data_str = str(data)
        if estimate_tokens(data_str) > max_tokens:
            return data_str[: max_tokens * 4] + "..."
        return data_str


def _truncate_lines(parts: list[str], budget: int, ellipsis: str = "...") -> str:
    result = "\n".join(parts)
    while estimate_tokens(result) > budget and len(parts) > 2:
        parts.pop()
        parts.append(ellipsis)
        result = "\n".join(parts)
    return result
