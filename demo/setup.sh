#!/usr/bin/env bash
# Cartographer demo — full suite installer for the demo laptop.
# Installs: python package, Flask corpus, indexed DB, demo data payloads,
# graph layout, and the VS Code extension. Re-runnable and offline-safe
# after the first run (only git clone needs the network).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$ROOT/demo"
export CARTOGRAPHER_DB="$DEMO/flask-demo.db"
REPO=/tmp/flask-demo

have() { command -v "$1" >/dev/null 2>&1; }
say()  { echo "▶ $1"; }
ok()   { echo "✓ $1"; }
warn() { echo "⚠ $1"; }

echo "=== Cartographer demo setup ==="
echo "repo root: $ROOT"

# ── 0. prerequisites ────────────────────────────────────────────────
for cmd in python3 git; do
  have "$cmd" || { echo "✗ missing required tool: $cmd"; exit 1; }
done
have code || warn "'code' CLI not found — VS Code extension step will be skipped (install VS Code + shell command first)."

# ── 1. cartographer CLI ─────────────────────────────────────────────
if have cartographer; then
  ok "cartographer CLI: $(cartographer version 2>/dev/null | head -n1)"
else
  say "installing cartographer package..."
  python3 -m pip install -e "$ROOT" || python3 -m pip install -e "$ROOT" --break-system-packages
  ok "cartographer installed"
fi

# ── 2. real corpus (Flask) ──────────────────────────────────────────
if [ ! -d "$REPO" ]; then
  say "cloning Flask (~3 MB)..."
  git clone --depth 1 https://github.com/pallets/flask.git "$REPO"
else
  ok "Flask already at $REPO"
fi

# ── 3. index it (live, ~1 s; committed DB is reused if repo unchanged)
say "indexing Flask..."
cartographer index "$REPO" > /dev/null
ok "$(cartographer --json summarize | python3 -c 'import json,sys; s=json.load(sys.stdin); d=s.get("data",s.get("summary",{})); print(str(d["total_nodes"])+" nodes, "+str(d["total_edges"])+" edges")')"

# ── 4. demo data payload (real captured tool outputs) ───────────────
say "capturing real tool outputs..."
python3 "$DEMO/gen_data.py"

# ── 5. graph layout (precomputed so the demo never jitters) ─────────
if ! python3 -c "import networkx" 2>/dev/null; then
  say "installing networkx (layout builder)..."
  python3 -m pip install networkx 2>/dev/null || python3 -m pip install networkx --break-system-packages
fi
say "solving graph layout..."
PYTHONHASHSEED=0 python3 "$DEMO/build_layout.py" /tmp/flask_full.json "$DEMO/graph.js" 2>/dev/null || {
  say "exporting graph data first..."
  cartographer graph-data -r flask-demo --limit 2000 > /tmp/flask_full.json
  PYTHONHASHSEED=0 python3 "$DEMO/build_layout.py" /tmp/flask_full.json "$DEMO/graph.js"
}

# ── 6. VS Code extension ────────────────────────────────────────────
VSIX="$ROOT/editors/vscode/cartographer-0.1.0.vsix"
if have code; then
  if [ -f "$VSIX" ]; then
    say "installing VS Code extension..."
    code --install-extension "$VSIX" --force 2>&1 | tail -n 1
    ok "VS Code extension installed"
  elif [ -d "$ROOT/editors/vscode" ]; then
    warn "vsix not found — building (needs npm + vsce)..."
    (cd "$ROOT/editors/vscode" && npm install && npx vsce package) \
      && code --install-extension "$ROOT"/editors/vscode/*.vsix --force 2>&1 | tail -n 1 \
      && ok "VS Code extension built + installed"
  else
    warn "editors/vscode missing — skipping extension install"
  fi
else
  warn "skipping VS Code extension ('code' CLI not on PATH)"
fi

# ── 7. verify ─────────────────────────────────────────────────────────
echo ""
echo "=== verify ==="
cartographer status 2>&1 | head -n 6
for f in "$DEMO/interactive.html" "$DEMO/data.js" "$DEMO/graph.js"; do
  [ -f "$f" ] && ok "$f" || { echo "✗ missing $f"; exit 1; }
done
echo ""
echo "=== DEMO IS READY ==="
echo "1. Open this file in a browser (double-click, no server needed):"
echo "     $DEMO/interactive.html"
echo "2. Live terminal (same DB the page was built from):"
echo "     export CARTOGRAPHER_DB=$DEMO/flask-demo.db"
echo '     cartographer ask "Flask" -t class --limit 3'
echo "3. VS Code: open $REPO, Ctrl+Shift+C → Graph"
