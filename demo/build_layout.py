"""Pre-compute a deterministic, art-directed layout for the booth demo graph.

Runtime jitter on a kiosk is unacceptable, so the force layout is solved here,
once, and the resulting coordinates are baked into the demo payload.
Clusters (top-level package) are laid out on a grid; nodes inside each cluster
use a local spring layout. This reads as organized islands instead of a hairball.
"""
import json
import math
import sys
from collections import defaultdict

import networkx as nx

SRC = sys.argv[1] if len(sys.argv) > 1 else "/tmp/flask_full.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "demo/booth_graph.js"

data = json.load(open(SRC))
raw_nodes = data["nodes"]
raw_edges = data["edges"]

# Keep the map legible on a projector: constants carry no story and dominate
# the corpus, so they are excluded from the drawn graph.
SKIP_TYPES = {"constant", "variable"}

nodes = [n for n in raw_nodes if n["type"] not in SKIP_TYPES]
keep_ids = {n["id"] for n in nodes}

edges = [
    {"source": e["source"], "target": e["target"], "type": e["type"]}
    for e in raw_edges
    if e["source"] in keep_ids and e["target"] in keep_ids
]

# Deduplicate edges; parallel edges only add ink.
seen = set()
uniq = []
for e in edges:
    key = (min(e["source"], e["target"]), max(e["source"], e["target"]), e["type"])
    if key in seen:
        continue
    seen.add(key)
    uniq.append(e)
edges = uniq

id_to_node = {n["id"]: n for n in nodes}


def cluster_of(node):
    """Group into a few big, instantly-legible islands.

    A booth viewer has ~5 seconds. Five named continents (Library source,
    Tests, Docs, Examples, Project) can be read at a glance; 70 fragments
    cannot. Sub-directories roll up into their top-level area.
    """
    path = node.get("file_path") or ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "Project"
    top = parts[0]
    if top == "src":
        return "Flask source"
    if top in {"tests", "test"}:
        return "Tests"
    if top in {"docs", "doc"}:
        return "Documentation"
    if top in {"examples", "example"}:
        return "Examples"
    return "Project"


clusters = defaultdict(list)
for n in nodes:
    clusters[cluster_of(n)].append(n)

G = nx.Graph()
for n in nodes:
    G.add_node(n["id"])
for e in edges:
    G.add_edge(e["source"], e["target"])

# Global spring layout inside each cluster, seeded for reproducibility.
pos = {}
for name, members in clusters.items():
    sub = G.subgraph([m["id"] for m in members])
    if sub.number_of_nodes() == 1:
        only = members[0]["id"]
        pos[only] = (0.0, 0.0)
        continue
    k = 1.6 / math.sqrt(max(1, sub.number_of_nodes()))
    local = nx.spring_layout(
        sub,
        k=k,
        iterations=220,
        seed=hash(name) % (2**31),
        weight="weight",
    )
    pos.update(local)

# Normalize each cluster to a unit disc *scaled by its size*, so a 12-node
# island stays small and a 536-node island stays large. Equal-radius clusters
# make the composition read as one shapeless blob.
unit = {}
max_count = max(len(m) for m in clusters.values())
for name, members in clusters.items():
    ids = [m["id"] for m in members]
    xs = [pos[i][0] for i in ids]
    ys = [pos[i][1] for i in ids]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    span = max(
        max(abs(x - cx) for x in xs),
        max(abs(y - cy) for y in ys),
        1e-6,
    )
    scale = 1.0 / span
    # sqrt keeps area proportional to node count; floor stops tiny clusters
    # from vanishing entirely
    weight = max(0.42, (len(members) / max_count) ** 0.5)
    for i in ids:
        unit[i] = ((pos[i][0] - cx) * scale, (pos[i][1] - cy) * scale, weight)

order = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
cols = math.ceil(math.sqrt(len(order) * 1.5))
rows = math.ceil(len(order) / cols)
CELL = 2.9
final = {}
for idx, (name, members) in enumerate(order):
    col = idx % cols
    row = idx // cols
    ox = (col - (cols - 1) / 2) * CELL
    oy = (row - (rows - 1) / 2) * CELL
    for m in members:
        ux, uy, w = unit[m["id"]]
        # deterministic jitter breaks perfect symmetry without visible drift
        h = hash((name, m["id"])) % 1000 / 1000.0
        final[m["id"]] = (ox + ux * w + (h - 0.5) * 0.04,
                          oy + uy * w + (h - 0.5) * 0.04)

xs = [p[0] for p in final.values()]
ys = [p[1] for p in final.values()]
minx, maxx = min(xs), max(xs)
miny, maxy = min(ys), max(ys)
spanx = (maxx - minx) or 1.0
spany = (maxy - miny) or 1.0
cx = (minx + maxx) / 2
cy = (miny + maxy) / 2

# Normalise each axis independently to roughly [-1, 1]. A wide-and-short grid
# squeezed into a square would leave dead margins on a 16:9 projector; letting
# each axis fill its own dimension uses the whole frame. Node radius is
# unaffected (computed in screen pixels at render time), so nothing looks
# squashed -- only the spacing between islands stretches.
payload_nodes = []
for n in nodes:
    x, y = final[n["id"]]
    payload_nodes.append(
        {
            "id": n["id"],
            "n": n["name"],
            "t": n["type"],
            "f": n.get("file_path") or "",
            "c": cluster_of(n),
            "x": round((x - cx) / (spanx / 2), 4),
            "y": round((y - cy) / (spany / 2), 4),
        }
    )

idx_of = {n["id"]: i for i, n in enumerate(payload_nodes)}
payload_edges = [
    [idx_of[e["source"]], idx_of[e["target"]], e["type"]] for e in edges
]

cluster_counts = defaultdict(int)
for n in payload_nodes:
    cluster_counts[n["c"]] += 1

payload = {
    "nodes": payload_nodes,
    "edges": payload_edges,
    "clusters": [
        {"name": k, "count": v}
        for k, v in sorted(cluster_counts.items(), key=lambda kv: -kv[1])
    ],
    "stats": {
        "total_nodes": data["total_nodes"],
        "total_edges": data["total_edges"],
        "drawn_nodes": len(payload_nodes),
        "drawn_edges": len(payload_edges),
        "files": data["node_types"].get("file", 0),
        "classes": data["node_types"].get("class", 0),
        "functions": data["node_types"].get("function", 0),
        "methods": data["node_types"].get("method", 0),
        "endpoints": data["node_types"].get("api_endpoint", 0),
    },
}

with open(OUT, "w") as fh:
    fh.write("window.GRAPH = " + json.dumps(payload, separators=(",", ":")) + ";")

print(f"wrote {OUT}")
print(f"  drawn {len(payload_nodes)} nodes / {len(payload_edges)} edges")
print(f"  clusters: {len(payload['clusters'])}")
print(f"  stats: {payload['stats']}")
import os

print(f"  size: {os.path.getsize(OUT) / 1024:.0f} KB")