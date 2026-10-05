#!/usr/bin/env bash
# Cartographer one-command installer: python package + VS Code extension + MCP configs.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Icarus-afk/Cartographer/main/install.sh | bash
#   ./install.sh                    # from a clone: installs editable + local .vsix
#   ./install.sh --with-index        # also index current repo
#   ./install.sh --scope global      # system-wide only (default)
set -euo pipefail

REPO_URL="https://github.com/Icarus-afk/Cartographer.git"
SCOPE="global"
WITH_INDEX="--no-index"
EXTRA_SETUP_ARGS=""

for arg in "$@"; do
  case "$arg" in
    --with-index) WITH_INDEX="--with-index" ;;
    --scope=*) SCOPE="${arg#--scope=}" ;;
    --scope) shift ;;
    -y|--yes) EXTRA_SETUP_ARGS="$EXTRA_SETUP_ARGS --yes" ;;
    -h|--help)
      echo "Usage: install.sh [--with-index] [--scope global|project|all]"
      exit 0
      ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

echo "==> Cartographer full-suite install (python + vscode + MCP)"

if ! have python3; then
  echo "ERROR: python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "    python $PY_VER"

PIP_CMD=""
if have pipx; then
  echo "    using pipx"
  PIP_CMD="pipx install"
elif have pip3; then
  PIP_CMD="pip3 install --user"
elif have pip; then
  PIP_CMD="pip install --user"
else
  echo "ERROR: no pip found." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${0}}")" 2>/dev/null && pwd || pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q 'name = "cartographer"' "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
  echo "==> Installing python package from local source (editable)"
  python3 -m pip install -e "$SCRIPT_DIR" 2>/dev/null || $PIP_CMD -e "$SCRIPT_DIR" || python3 -m pip install --user -e "$SCRIPT_DIR" --break-system-packages
  echo "==> Installing watchdog (file watcher)"
  python3 -m pip install --user watchdog 2>/dev/null || python3 -m pip install watchdog --break-system-packages 2>/dev/null || true
else
  echo "==> Installing python package from GitHub"
  # shellcheck disable=SC2086
  $PIP_CMD "git+${REPO_URL}" || python3 -m pip install "git+${REPO_URL}" --break-system-packages
  python3 -m pip install --user watchdog 2>/dev/null || true
fi

export PATH="$HOME/.local/bin:$PATH"
if ! have cartographer; then
  echo "WARNING: 'cartographer' not on PATH. Add ~/.local/bin to PATH." >&2
fi

echo "==> Configuring MCP for all agents (scope: $SCOPE)"
if have cartographer; then
  # shellcheck disable=SC2086
  cartographer setup . --scope "$SCOPE" $WITH_INDEX $EXTRA_SETUP_ARGS || \
    python3 -m cartographer setup . --scope "$SCOPE" $WITH_INDEX $EXTRA_SETUP_ARGS || true
else
  echo "    skip: cartographer CLI not found" >&2
fi

echo ""
echo "Done. Next steps:"
echo "  cd your-repo && cartographer setup --with-index   # per-project MCP + index"
echo "  cartographer status                                # verify"
echo "Restart opencode / Cursor / Claude Desktop to load MCP."
