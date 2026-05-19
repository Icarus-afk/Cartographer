from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from cartographer.storage.connection import get_connection, init_schema

# ─── naming pattern definitions ──────────────────────────────────────────────

CLASS_SUFFIX_RULES: list[tuple[str, str, float]] = [
    ("controller",   "controller", 1.0),
    ("restcontroller", "controller", 1.0),
    ("resource",     "controller", 0.9),
    ("service",      "business",   1.0),
    ("manager",      "business",   0.8),
    ("orchestrator", "business",   0.9),
    ("usecase",      "business",   1.0),
    ("use_case",     "business",   1.0),
    ("repository",   "data",       1.0),
    ("repo_impl",    "data",       0.9),
    ("dao",          "data",       1.0),
    ("entity",       "data",       1.0),
    ("model",        "data",       0.8),
    ("dto",          "data",       0.9),
    ("mapper",       "data",       0.8),
    ("transformer",  "data",       0.8),
    ("converter",    "data",       0.8),
    ("middleware",   "middleware", 1.0),
    ("filter",       "middleware", 0.8),
    ("interceptor",  "middleware", 0.9),
    ("aspect",       "middleware", 0.8),
    ("config",       "config",     1.0),
    ("configuration","config",     1.0),
    ("settings",     "config",     0.9),
    ("helper",       "utility",    1.0),
    ("util",         "utility",    1.0),
    ("support",      "utility",    0.8),
    ("handler",      "controller", 0.8),
    ("adapter",      "infrastructure", 1.0),
    ("client",       "infrastructure", 0.9),
    ("connector",    "infrastructure", 0.9),
    ("provider",     "infrastructure", 0.8),
    ("factory",      "infrastructure", 0.7),
    ("builder",      "infrastructure", 0.6),
    ("validator",    "utility",    0.8),
    ("exception",    "utility",    0.6),
    ("error",        "utility",    0.5),
]

CLASS_PREFIX_RULES: list[tuple[str, str, float]] = [
    ("abstract", "utility", 0.3),
]

INTERFACE_PREFIX_RULES: list[tuple[str, str, float]] = [
    ("i", "controller", 0.3),
]

FILE_NAME_RULES: list[tuple[str, str, float]] = [
    ("controller",   "controller", 1.0),
    ("route",        "controller", 0.9),
    ("handler",      "controller", 0.8),
    ("service",      "business",   1.0),
    ("manager",      "business",   0.7),
    ("repository",   "data",       1.0),
    ("dao",          "data",       1.0),
    ("model",        "data",       0.8),
    ("entity",       "data",       0.9),
    ("middleware",   "middleware", 1.0),
    ("filter",       "middleware", 0.7),
    ("config",       "config",     1.0),
    ("setting",      "config",     0.8),
    ("util",         "utility",    1.0),
    ("helper",       "utility",    1.0),
    ("common",       "utility",    0.7),
    ("shared",       "utility",    0.7),
    ("migration",    "migration",  1.0),
    ("migrate",      "migration",  1.0),
    ("test",         "testing",    1.0),
    ("spec",         "testing",    1.0),
    ("benchmark",    "testing",    0.8),
    ("view",         "presentation", 0.8),
    ("component",    "presentation", 0.8),
    ("page",         "presentation", 0.7),
    ("template",     "presentation", 0.8),
    ("screen",       "presentation", 0.8),
    ("api",          "api",        0.9),
    ("graphql",      "api",        1.0),
    ("grpc",         "api",        1.0),
    ("endpoint",     "api",        0.9),
]

DIRECTORY_NAME_RULES: list[tuple[str, str, float]] = [
    ("controllers", "controller", 1.0),
    ("controller",  "controller", 1.0),
    ("routes",      "controller", 1.0),
    ("handlers",    "controller", 0.9),
    ("endpoints",   "controller", 0.9),
    ("services",    "business",   1.0),
    ("service",     "business",   1.0),
    ("core",        "business",   0.8),
    ("domain",      "business",   0.9),
    ("logic",       "business",   0.8),
    ("use_cases",   "business",   1.0),
    ("usecases",    "business",   0.9),
    ("models",      "data",       0.9),
    ("entities",    "data",       1.0),
    ("repositories","data",       1.0),
    ("repository",  "data",       1.0),
    ("dao",         "data",       1.0),
    ("dal",         "data",       1.0),
    ("gateways",    "data",       0.9),
    ("middleware",   "middleware", 1.0),
    ("filters",     "middleware", 0.8),
    ("interceptors","middleware", 0.9),
    ("aspects",     "middleware", 0.8),
    ("config",      "config",     1.0),
    ("configuration","config",     1.0),
    ("settings",    "config",     0.9),
    ("env",         "config",     0.5),
    ("utils",       "utility",    1.0),
    ("util",        "utility",    1.0),
    ("helpers",     "utility",    1.0),
    ("common",      "utility",    0.7),
    ("shared",      "utility",    0.7),
    ("lib",         "utility",    0.6),
    ("support",     "utility",    0.7),
    ("infrastructure","infrastructure", 1.0),
    ("infra",       "infrastructure", 1.0),
    ("adapters",    "infrastructure", 1.0),
    ("adapter",     "infrastructure", 1.0),
    ("external",    "infrastructure", 0.8),
    ("clients",     "infrastructure", 0.8),
    ("providers",   "infrastructure", 0.8),
    ("migrations",  "migration",  1.0),
    ("migrate",     "migration",  1.0),
    ("alembic",     "migration",  0.8),
    ("tests",       "testing",    1.0),
    ("test",        "testing",    1.0),
    ("spec",        "testing",    1.0),
    ("specs",       "testing",    1.0),
    ("__tests__",   "testing",    1.0),
    ("views",       "presentation", 1.0),
    ("templates",   "presentation", 1.0),
    ("ui",          "presentation", 0.9),
    ("components",  "presentation", 0.9),
    ("pages",       "presentation", 0.8),
    ("screens",     "presentation", 0.8),
    ("api",         "api",        0.9),
    ("rest",        "api",        0.8),
    ("graphql",     "api",        1.0),
    ("grpc",        "api",        1.0),
]

FRAMEWORK_FILE_RULES: dict[str, list[tuple[str, str, float]]] = {
    "django": [
        ("models.py",    "data",       1.0),
        ("admin.py",     "presentation", 0.7),
        ("views.py",     "presentation", 1.0),
        ("urls.py",      "controller", 1.0),
        ("serializers.py","data",      1.0),
        ("forms.py",     "presentation", 0.8),
        ("apps.py",      "config",     0.8),
    ],
    "flask": [
        ("models.py",    "data",       1.0),
        ("views.py",     "presentation", 0.8),
        ("routes.py",    "controller", 1.0),
        ("forms.py",     "presentation", 0.7),
    ],
    "rails": [
        ("application_controller.rb", "controller", 1.0),
        ("application_record.rb",     "data",       1.0),
        ("routes.rb",                 "controller", 1.0),
    ],
    "express": [
        ("routes",       "controller", 1.0),
        ("controllers",  "controller", 1.0),
        ("middleware",   "middleware", 1.0),
        ("models",       "data",       1.0),
        ("views",        "presentation", 0.9),
        ("app.js",       "controller", 0.6),
        ("server.js",    "controller", 0.6),
        ("router",       "controller", 0.9),
    ],
    "fastapi": [
        ("routers",      "controller", 1.0),
        ("schemas",      "data",       1.0),
        ("models",       "data",       0.9),
        ("dependencies", "middleware", 0.8),
        ("main.py",      "controller", 0.6),
        ("app.py",       "controller", 0.6),
    ],
    "next.js": [
        ("page",         "presentation", 1.0),
        ("layout",       "presentation", 0.9),
        ("loading",      "presentation", 0.7),
        ("error",        "presentation", 0.7),
        ("not-found",    "presentation", 0.6),
        ("route",        "api",        1.0),
        ("api",          "api",        0.9),
        ("components",   "presentation", 0.8),
    ],
    "laravel": [
        ("Controller",   "controller", 1.0),
        ("Request",      "controller", 0.7),
        ("Resource",     "controller", 0.7),
        ("Model",        "data",       1.0),
        ("Migration",    "migration",  1.0),
        ("Seeder",       "data",       0.6),
        ("Factory",      "infrastructure", 0.6),
        ("routes",       "controller", 0.9),
        ("web.php",      "controller", 1.0),
        ("api.php",      "api",        1.0),
    ],
    "actix_web": [
        ("handlers",     "controller", 1.0),
        ("handler",      "controller", 0.8),
        ("routes",       "controller", 0.9),
        ("models",       "data",       0.8),
        ("middleware",   "middleware", 1.0),
        ("main.rs",      "controller", 0.5),
    ],
    "axum": [
        ("handlers",     "controller", 1.0),
        ("handler",      "controller", 0.8),
        ("routes",       "controller", 0.9),
        ("models",       "data",       0.8),
        ("state",        "config",     0.7),
        ("middleware",   "middleware", 1.0),
        ("main.rs",      "controller", 0.5),
    ],
}

LAYER_META: dict[str, dict[str, str]] = {
    "controller":   {"label": "Controller",   "color": "blue"},
    "presentation": {"label": "Presentation", "color": "green"},
    "api":          {"label": "API",          "color": "cyan"},
    "business":     {"label": "Business",     "color": "yellow"},
    "data":         {"label": "Data",         "color": "magenta"},
    "middleware":   {"label": "Middleware",   "color": "red"},
    "config":       {"label": "Config",       "color": "white"},
    "infrastructure": {"label": "Infrastructure", "color": "bright_black"},
    "migration":    {"label": "Migration",    "color": "bright_blue"},
    "testing":      {"label": "Testing",      "color": "bright_green"},
    "utility":      {"label": "Utility",      "color": "bright_white"},
}

PATTERN_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "mvc",
        "name": "Model-View-Controller",
        "layers": {"controller", "presentation", "data"},
        "description": "Models (data), Views (presentation), Controllers (request handling)",
    },
    {
        "key": "layered",
        "name": "Layered (n-tier)",
        "layers": {"presentation", "business", "data"},
        "description": "Horizontal layers with strict dependency direction",
    },
    {
        "key": "clean",
        "name": "Clean Architecture",
        "layers": {"business", "infrastructure", "api"},
        "description": "Domain core with infrastructure and API adapters, dependency inversion",
    },
    {
        "key": "hexagonal",
        "name": "Hexagonal (Ports & Adapters)",
        "layers": {"business", "infrastructure", "api"},
        "description": "Business core with inbound (API) and outbound (infrastructure) adapters",
    },
    {
        "key": "repository",
        "name": "Repository Pattern",
        "layers": {"data"},
        "description": "Data access abstracted behind repository interfaces",
    },
    {
        "key": "service_oriented",
        "name": "Service-Oriented",
        "layers": {"api", "business"},
        "description": "Business logic exposed through an API/controller layer",
    },
]


# ─── detection helpers ───────────────────────────────────────────────────────

def _score_name(name: str, rules: list[tuple[str, str, float]]) -> list[tuple[str, float, str]]:
    results: list[tuple[str, float, str]] = []
    lower = name.lower().replace("-", "_")
    for keyword, layer, weight in rules:
        if lower.endswith(keyword):
            results.append((layer, weight, f"name suffix '{keyword}'"))
        elif lower.startswith(keyword):
            results.append((layer, weight * 0.8, f"name prefix '{keyword}'"))
        elif keyword in lower:
            results.append((layer, weight * 0.5, f"name contains '{keyword}'"))
    return results


def _score_file_name(
    name: str, rules: list[tuple[str, str, float]]
) -> list[tuple[str, float, str]]:
    results: list[tuple[str, float, str]] = []
    lower = name.lower()
    stem = Path(lower).stem
    for keyword, layer, weight in rules:
        kw = keyword.lower()
        if kw in stem:
            results.append((layer, weight, f"filename contains '{keyword}'"))
    return results


def _score_directory(
    name: str, rules: list[tuple[str, str, float]]
) -> list[tuple[str, float, str]]:
    results: list[tuple[str, float, str]] = []
    lower = name.lower()
    for keyword, layer, weight in rules:
        if lower == keyword:
            results.append((layer, weight, f"directory named '{keyword}'"))
    return results


def _detect_framework_from_graph(
    conn: sqlite3.Connection,
    repo_id: int,
) -> list[dict[str, Any]]:
    manifest_row = conn.execute(
        "SELECT manifest_json FROM repositories WHERE id = ?", (repo_id,)
    ).fetchone()
    if manifest_row and manifest_row[0]:
        try:
            manifest_data = json.loads(manifest_row[0])
            fw_list = manifest_data.get("frameworks", [])
            if fw_list:
                return [
                    {"name": f["name"].lower().replace(" ", "_").replace("-", "_"),
                     "confidence": f["confidence"]}
                    for f in fw_list
                ]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    file_names = conn.execute(
        """SELECT DISTINCT n.name FROM nodes n
           WHERE n.repository_id = ? AND n.node_type = 'file'""",
        (repo_id,),
    ).fetchall()

    fnames = set(r[0] for r in file_names)

    dir_entries = conn.execute(
        """SELECT DISTINCT n.file_path FROM nodes n
           WHERE n.repository_id = ? AND n.node_type = 'directory'""",
        (repo_id,),
    ).fetchall()
    all_segments: set[str] = set()
    for (dp,) in dir_entries:
        for seg in dp.lower().split("/"):
            all_segments.add(seg)

    scores: dict[str, float] = {}

    checks: list[tuple[str, str, float]] = [
        ("django",   "settings", 0.5),
        ("django",   "wsgi",     0.3),
        ("rails",    "app",      0.3),
        ("laravel",  "app/http", 0.5),
        ("nestjs",   "module",   0.5),
        ("express",  "routes",   0.4),
        ("express",  "controllers", 0.4),
        ("express",  "middleware", 0.3),
        ("fastapi",  "routers",  0.5),
        ("fastapi",  "schemas",  0.4),
        ("next.js",  "pages",    0.4),
        ("next.js",  "app",      0.3),
        ("actix_web", "handlers", 0.4),
        ("axum",     "handlers", 0.4),
    ]
    for fw, keyword, weight in checks:
        if keyword in all_segments:
            scores[fw] = scores.get(fw, 0) + weight

    for fname in fnames:
        lower = fname.lower()
        if lower == "manage.py":
            scores["django"] = scores.get("django", 0) + 0.8
        if lower in ("gemfile",):
            scores["rails"] = scores.get("rails", 0) + 0.5
        if lower in ("artisan",):
            scores["laravel"] = scores.get("laravel", 0) + 0.6
        if lower in ("next.config.js", "next.config.ts"):
            scores["next.js"] = scores.get("next.js", 0) + 0.7
        if lower in ("nest-cli.json",):
            scores["nestjs"] = scores.get("nestjs", 0) + 0.7
        if lower.endswith("pom.xml") or lower.endswith("build.gradle"):
            scores["spring_boot"] = scores.get("spring_boot", 0) + 0.6

    results = []
    for fw, score in sorted(scores.items(), key=lambda x: -x[1]):
        results.append({"name": fw, "confidence": round(min(score, 1.0), 2)})
    return results


# ─── main detection ──────────────────────────────────────────────────────────

def detect_architecture(
    db_path: Path,
    repo_name: str | None = None,
) -> dict[str, Any]:
    conn = get_connection(db_path)
    init_schema(conn)
    result = _analyze(conn, repo_name)
    conn.close()
    return result


def _normalize_layer(layer: str) -> str:
    aliases = {
        "models": "data",
        "model": "data",
        "service": "business",
        "services": "business",
        "view": "presentation",
        "views": "presentation",
        "route": "controller",
        "routes": "controller",
        "handler": "controller",
        "handlers": "controller",
        "repo": "data",
        "repos": "data",
    }
    return aliases.get(layer, layer)


def _analyze(
    conn: sqlite3.Connection,
    repo_name: str | None,
) -> dict[str, Any]:
    repo_filter = ""
    params: list[Any] = []
    if repo_name:
        repo_filter = "AND r.name = ?"
        params.append(repo_name)

    repo_row = conn.execute(
        f"""SELECT id, name, path FROM repositories
            WHERE 1=1 {repo_filter.replace('r.name', 'name')}
            LIMIT 1""",
        params,
    ).fetchone()

    if not repo_row:
        return {"error": "No repository found. Run 'cartographer index' first."}

    repo_id, repo_name_val, repo_path = repo_row

    frameworks = _detect_framework_from_graph(conn, repo_id)
    fw_names = {f["name"] for f in frameworks if f["confidence"] >= 0.3}

    architecture: dict[str, Any] = {
        "repository": repo_name_val,
        "path": repo_path,
        "frameworks": frameworks,
        "layers": {},
        "files_by_layer": {},
        "patterns": [],
    }

    layer_evidence, _layer_entity_count = _collect_evidence(conn, repo_id, fw_names)
    resolved = _aggregate_layers(layer_evidence)

    flow_insights = _analyze_dependency_flow(conn, repo_id, resolved)
    if flow_insights:
        architecture["dependency_flow"] = flow_insights

    architecture["layers"] = dict(sorted(
        resolved.items(),
        key=lambda x: (-x[1]["confidence"], -x[1]["entity_count"]),
    ))

    architecture["patterns"] = _detect_patterns(resolved, fw_names)
    architecture["framework_patterns"] = _detect_framework_patterns(resolved, fw_names)

    _persist_architecture(conn, repo_id, resolved,
                          architecture["patterns"], architecture["framework_patterns"])
    return architecture


def _collect_evidence(
    conn: sqlite3.Connection,
    repo_id: int,
    fw_names: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    all_dir_rows = conn.execute(
        """SELECT n.name, n.file_path FROM nodes n
           WHERE n.repository_id = ? AND n.node_type = 'directory'""",
        (repo_id,),
    ).fetchall()

    all_file_rows = conn.execute(
        """SELECT n.name, n.file_path FROM nodes n
           WHERE n.repository_id = ? AND n.node_type = 'file'""",
        (repo_id,),
    ).fetchall()

    all_class_rows = conn.execute(
        """SELECT n.name, n.file_path FROM nodes n
           WHERE n.repository_id = ? AND n.node_type IN ('class','interface','enum')""",
        (repo_id,),
    ).fetchall()

    all_function_rows = conn.execute(
        """SELECT n.name, n.file_path FROM nodes n
           WHERE n.repository_id = ? AND n.node_type IN ('function','method')""",
        (repo_id,),
    ).fetchall()

    layer_evidence: dict[str, list[dict[str, Any]]] = {}
    layer_entity_count: dict[str, int] = {}

    def _add_evidence(layer: str, kind: str, source: str, evidence: str, weight: float) -> None:
        layer = _normalize_layer(layer)
        if layer not in layer_evidence:
            layer_evidence[layer] = []
            layer_entity_count[layer] = 0
        layer_evidence[layer].append({
            "kind": kind,
            "source": source,
            "evidence": evidence,
            "weight": weight,
        })
        layer_entity_count[layer] += 1

    # 1. Class/interface naming
    for cname, fpath in all_class_rows:
        for layer, weight, reason in _score_name(cname, CLASS_SUFFIX_RULES):
            if weight >= 0.6:
                _add_evidence(layer, "class_naming", f"{cname} ({fpath})", reason, weight)

    # 2. Function/method naming
    for fname, fpath in all_function_rows:
        for layer, weight, reason in _score_name(fname, CLASS_SUFFIX_RULES):
            if weight >= 0.7:
                _add_evidence(layer, "function_naming", f"{fname} ({fpath})", reason, weight * 0.8)

    # 3. File naming
    for fname, fpath in all_file_rows:
        for layer, weight, reason in _score_file_name(fname, FILE_NAME_RULES):
            _add_evidence(layer, "file_naming", fpath, reason, weight)

    # 4. Framework-specific file rules
    active_file_rules: list[tuple[str, str, float]] = []
    for fw in fw_names:
        fw_key = fw.lower().replace(" ", "_").replace("-", "_")
        if fw_key in FRAMEWORK_FILE_RULES:
            active_file_rules.extend(FRAMEWORK_FILE_RULES[fw_key])
    for fname, fpath in all_file_rows:
        stem = Path(fname).stem.lower()
        fname_only = Path(fname).name.lower()
        for keyword, layer, weight in active_file_rules:
            if fname_only == keyword.lower() or stem == Path(keyword).stem.lower():
                _add_evidence(layer, "framework_file", fpath, f"framework file '{keyword}'", weight)

    # 5. Directory naming
    all_segments: set[str] = set()
    for dname, dpath in all_dir_rows:
        for segment in dpath.lower().split("/"):
            all_segments.add(segment)
    for dname, dpath in all_dir_rows:
        for layer, weight, reason in _score_directory(dname, DIRECTORY_NAME_RULES):
            _add_evidence(layer, "directory", dpath, reason, weight)

    # 6. Framework-specific directory conventions
    if "django" in fw_names:
        for fname, fpath in all_file_rows:
            parts = Path(fpath).parts
            if len(parts) >= 2 and Path(fname).name.lower() in (
                "models.py", "views.py", "urls.py", "admin.py",
            ):
                app_dir = parts[0]
                _add_evidence("controller", "django_app", fpath,
                              f"Django app '{app_dir}'", 0.5)

    if "rails" in fw_names:
        for dname, dpath in all_dir_rows:
            if dpath == "app/controllers":
                _add_evidence("controller", "rails_convention", dpath,
                              "Rails controllers directory", 1.0)
            if dpath == "app/models":
                _add_evidence("data", "rails_convention", dpath,
                              "Rails models directory", 1.0)
            if dpath == "app/views":
                _add_evidence("presentation", "rails_convention", dpath,
                              "Rails views directory", 1.0)

    return layer_evidence, layer_entity_count


def _aggregate_layers(
    layer_evidence: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    for layer, evidence in layer_evidence.items():
        if not evidence:
            continue
        weights = [e["weight"] for e in evidence]
        avg_weight = sum(weights) / len(weights)
        max_weight = max(weights)
        entity_count = len(set(e["source"] for e in evidence))

        evidence_by_kind: dict[str, int] = {}
        for e in evidence:
            evidence_by_kind[e["kind"]] = evidence_by_kind.get(e["kind"], 0) + 1

        conf_raw = (avg_weight * 0.4 + max_weight * 0.6) * min(entity_count / 3, 1.0)
        confidence = round(min(conf_raw, 1.0), 2)

        resolved[layer] = {
            "description": LAYER_META.get(layer, {}).get("label", layer),
            "confidence": confidence,
            "entity_count": entity_count,
            "total_hits": len(evidence),
            "evidence_types": evidence_by_kind,
            "examples": [e["source"] for e in evidence[:8]],
        }
    return resolved


def _analyze_dependency_flow(
    conn: sqlite3.Connection,
    repo_id: int,
    resolved: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    import_edges = conn.execute(
        """SELECT e.source_node_id, e.target_node_id, n1.file_path, n2.file_path
           FROM edges e
           JOIN nodes n1 ON e.source_node_id = n1.id
           JOIN nodes n2 ON e.target_node_id = n2.id
           WHERE e.edge_type = 'IMPORTS'
           AND e.repository_id = ?
           AND n1.node_type = 'file'
           AND n2.node_type = 'file'""",
        (repo_id,),
    ).fetchall()

    entity_map: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute(
        """SELECT n.file_path, n.name, n.node_type FROM nodes n
           WHERE n.repository_id = ? AND n.node_type IN
           ('class','function','method','interface')""",
        (repo_id,),
    ).fetchall():
        entity_map.setdefault(row[0], []).append((row[1], row[2]))

    flow_summary: dict[str, dict[str, Any]] = {}

    def _file_layer(fpath: str) -> str | None:
        fname = Path(fpath).name
        layer_scores: list[tuple[str, float]] = []
        file_hits = _score_file_name(fname, FILE_NAME_RULES)
        dir_hits: list[tuple[str, float, str]] = []
        for d in fpath.lower().split("/"):
            dir_hits.extend(_score_directory(d, DIRECTORY_NAME_RULES))
        hits = list(file_hits) + dir_hits
        for layer, weight, _reason in hits:
            if layer in resolved:
                layer_scores.append((layer, weight))
        for ename, etype in entity_map.get(fpath, []):
            for sublayer, weight, _reason in _score_name(ename, CLASS_SUFFIX_RULES):
                if sublayer in resolved and weight >= 0.6:
                    layer_scores.append((sublayer, weight))
        return max(layer_scores, key=lambda x: x[1])[0] if layer_scores else None

    seen_pairs: set[tuple[int, int]] = set()
    for src_id, tgt_id, src_path, tgt_path in import_edges:
        pair = (src_id, tgt_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        src_layer = _file_layer(src_path)
        tgt_layer = _file_layer(tgt_path)
        if src_layer and tgt_layer and src_layer != tgt_layer:
            key = f"{src_layer} -> {tgt_layer}"
            if key not in flow_summary:
                flow_summary[key] = {"count": 0, "examples": []}
            flow_summary[key]["count"] += 1
            if len(flow_summary[key]["examples"]) < 3:
                flow_summary[key]["examples"].append(
                    f"{src_path} -> {tgt_path}"
                )

    expected_directions: list[tuple[str, str, str]] = [
        ("controller", "business", "Controller imports from business/service"),
        ("business", "data", "Business imports from data layer"),
        ("api", "business", "API imports from business layer"),
        ("middleware", "controller", "Middleware imports from controller"),
        ("presentation", "business", "Presentation imports from business"),
    ]

    flow_insights: list[dict[str, Any]] = []
    for src_layer, tgt_layer, desc in expected_directions:
        key = f"{src_layer} -> {tgt_layer}"
        rev_key = f"{tgt_layer} -> {src_layer}"
        fwd = flow_summary.get(key, {}).get("count", 0)
        rev = flow_summary.get(rev_key, {}).get("count", 0)
        if fwd > 0 or rev > 0:
            flow_insights.append({
                "direction": f"{src_layer} -> {tgt_layer}",
                "description": desc,
                "forward": fwd,
                "reverse": rev,
                "expected": fwd >= rev,
            })

    for key, info in sorted(flow_summary.items(), key=lambda x: -x[1]["count"]):
        src_layer, _, tgt_layer = key.partition(" -> ")
        matched = any(insight["direction"] == key for insight in flow_insights)
        if not matched:
            flow_insights.append({
                "direction": key,
                "description": f"{src_layer} imports from {tgt_layer}",
                "forward": info["count"],
                "reverse": 0,
                "expected": None,
            })

    return flow_insights


def _detect_patterns(
    resolved: dict[str, dict[str, Any]],
    fw_names: set[str],
) -> list[dict[str, Any]]:
    detected_layers_set = set(resolved.keys())
    patterns: list[dict[str, Any]] = []

    for pat in PATTERN_DEFINITIONS:
        required = pat["layers"]
        matched = required & detected_layers_set
        ratio = len(matched) / len(required) if required else 0
        if ratio >= 0.5:
            matched_conf = [resolved[layer]["confidence"] for layer in matched]
            avg_conf = sum(matched_conf) / len(matched_conf) if matched_conf else 0
            patterns.append({
                "name": pat["name"],
                "key": pat["key"],
                "confidence": round(avg_conf * ratio, 2),
                "matched_layers": sorted(matched),
                "missing_layers": sorted(required - detected_layers_set),
                "description": pat["description"],
            })

    patterns.sort(key=lambda p: -p["confidence"])
    return patterns


def _detect_framework_patterns(
    resolved: dict[str, dict[str, Any]],
    fw_names: set[str],
) -> list[dict[str, Any]]:
    detected = set(resolved.keys())
    patterns: list[dict[str, Any]] = []
    fwp: list[tuple[str, str, set[str], float | None]] = [
        ("Django MTV (Model-Template-View)", "django", {"data", "controller"}, None),
        ("Ruby on Rails MVC", "rails", {"controller", "data", "presentation"}, 0.9),
        ("Spring Boot Layered", "spring_boot", {"controller", "business"}, 0.85),
        ("NestJS Modular", "nestjs", {"controller", "business"}, None),
        ("Express MVC", "express", {"controller", "data", "presentation"}, None),
        ("FastAPI Modular", "fastapi", {"controller", "data", "middleware"}, None),
        ("Next.js App Router", "next.js", {"presentation", "api", "config"}, None),
        ("Laravel MVC", "laravel", {"controller", "data", "presentation", "migration"}, None),
        ("Actix Web Modular", "actix_web", {"controller", "data", "middleware"}, None),
        ("Axum Modular", "axum", {"controller", "data", "middleware", "config"}, None),
    ]
    for name, fw_key, layers, fixed_conf in fwp:
        if fw_key not in fw_names:
            continue
        matched = layers & detected
        if fixed_conf is not None:
            conf = fixed_conf
        elif matched:
            conf = round(sum(resolved[lyr]["confidence"] for lyr in matched) / len(layers), 2)
        else:
            continue
        if not matched:
            continue
        patterns.append({"name": name, "confidence": conf, "description": ""})
    return patterns


def _persist_architecture(
    conn: sqlite3.Connection,
    repo_id: int,
    resolved: dict[str, dict[str, Any]],
    patterns: list[dict[str, Any]],
    fw_patterns: list[dict[str, Any]],
) -> None:
    conn.execute("DELETE FROM architecture WHERE repository_id = ?", (repo_id,))
    for layer_name, info in resolved.items():
        conn.execute(
            "INSERT INTO architecture (repository_id, layer, pattern, description) "
            "VALUES (?, ?, NULL, ?)",
            (repo_id, layer_name, info["description"]),
        )
    for pat in patterns:
        conn.execute(
            "INSERT INTO architecture (repository_id, layer, pattern, description) "
            "VALUES (?, 'pattern', ?, ?)",
            (repo_id, pat["name"], pat["description"]),
        )
    for fwp in fw_patterns:
        conn.execute(
            "INSERT INTO architecture (repository_id, layer, pattern, description) "
            "VALUES (?, 'framework_pattern', ?, ?)",
            (repo_id, fwp["name"], fwp.get("description", "")),
        )
    conn.commit()


def get_architecture(
    db_path: Path,
    repo_name: str | None = None,
) -> dict[str, Any]:
    conn = get_connection(db_path)

    repo_filter = ""
    params: list[Any] = []
    if repo_name:
        repo_filter = "AND r.name = ?"
        params.append(repo_name)

    repo_row = conn.execute(
        f"""SELECT r.id, r.name, r.path FROM repositories r
            WHERE 1=1 {repo_filter.replace('r.name', 'name')}
            LIMIT 1""",
        params,
    ).fetchone()

    if not repo_row:
        conn.close()
        return {"error": "No repository found."}

    repo_id, repo_name_val, repo_path = repo_row

    rows = conn.execute(
        "SELECT layer, pattern, description FROM architecture WHERE repository_id = ?",
        (repo_id,),
    ).fetchall()

    conn.close()

    layers: list[dict[str, str]] = []
    patterns: list[dict[str, str]] = []
    framework_patterns: list[dict[str, str]] = []
    for layer, pattern, description in rows:
        if layer == "pattern":
            patterns.append({"name": pattern, "description": description})
        elif layer == "framework_pattern":
            framework_patterns.append({"name": pattern, "description": description})
        else:
            layers.append({"name": layer, "description": description})

    return {
        "repository": repo_name_val,
        "path": repo_path,
        "layers": layers,
        "patterns": patterns,
        "framework_patterns": framework_patterns,
    }
