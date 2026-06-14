# Getting Started with Cartographer

Cartographer turns any repository into a navigable knowledge graph. This guide walks through installation, your first index, and the most common workflows — with explanations of what's happening at each step.

---

## Prerequisites

- **Python 3.11 or later** — Cartographer uses modern Python features
- **pip** — Python package installer
- **Git** — only needed if you want git intelligence features

---

## Installation

### From source (recommended for now)

```bash
git clone https://github.com/your-org/cartographer.git
cd cartographer
pip install -e .
```

The `-e` flag installs in "editable" mode, so changes you make to the source code are reflected immediately.

Verify it works:
```bash
cartographer version
```

### What gets installed

Cartographer installs these key dependencies automatically:

| Dependency | What it's used for |
|---|---|
| **click** | Building the command-line interface |
| **tree-sitter** | Parsing source code into syntax trees — supports 19 languages |
| **fastembed** | Generating vector embeddings from code for semantic search |
| **pathspec** | Reading `.gitignore` files so Cartographer skips what Git ignores |
| **pyyaml** | Reading YAML configuration files |
| **packaging** | Detecting package versions |

Tree-sitter language grammars (one per language) are downloaded automatically the first time you index a file written in that language. The embedding model (`BAAI/bge-small-en-v1.5`, ~33MB) downloads the first time you run `cartographer embed`.

---

## Your First Index

### 1. Choose a repository

Pick any code project on your machine. If you don't have one handy, index Cartographer itself:

```bash
cartographer index /path/to/your/project
```

### 2. Watch the output

You'll see something like this:

```
Indexed 152 files in 24 directories
Duration: 2431.18ms
Languages: python: 89, javascript: 43, typescript: 20
Frameworks: Django (98% confidence)
Package Managers: pip
Build Systems: setuptools
Entities: 152 files parsed, 45 classes, 312 functions, 89 methods
References: 234 cross-file imports
```

Let's break down what each line means:

- **Files/Directories** — how many source files were discovered and indexed
- **Duration** — how long it took (for most projects, under a few seconds)
- **Languages** — which programming languages were found and how many files of each
- **Frameworks** — web frameworks detected automatically (Django, Flask, Spring, etc.)
- **Package Managers** — npm, pip, cargo, bundler, etc.
- **Build Systems** — Makefile, CMake, setuptools, etc.
- **Entities** — how many classes, functions, and methods were parsed out of the code
- **References** — cross-file imports that were resolved

### 3. The database

By default, Cartographer stores everything in `~/.cartographer/index.db`. This is a SQLite database file that contains:
- **Nodes** — every entity (files, classes, functions, variables, etc.)
- **Edges** — relationships between entities (contains, defines, imports, etc.)
- **Embeddings** — vector representations for semantic search
- **Repositories** — metadata about what's been indexed
- **Commits/Authors** — git history data (if you run `git index`)

You can override the database path on every command:

```bash
cartographer --db /tmp/my-project.db index /path/to/your/project
```

Or set an environment variable:

```bash
export CARTOGRAPHER_DB=/tmp/my-project.db
cartographer index /path/to/your/project
```

### 4. What gets indexed (and what doesn't)

Cartographer automatically skips:
- Binary files (`.pyc`, `.so`, `.png`, `.pdf`, `.zip`, etc.) — detected by file extension AND by checking for null bytes
- Hidden directories starting with `.` (like `.git`, `.venv`, `.next`)
- 23+ well-known ignored directories (`node_modules`, `__pycache__`, `target`, `build`, `dist`, etc.)
- Files matching patterns in `.cartographerignore` (if present in the repo root)
- Files matching patterns in the root `.gitignore` (parsed via the `pathspec` library)

This means you can safely index large projects without worrying about vendored dependencies or generated code.

---

## Next Steps After Indexing

### Search for specific symbols

```bash
cartographer ask "UserService"
```

This searches all node names using SQL `LIKE`. Results are sorted by relevance: exact match first, then prefix match, then substring match.

### Ask questions in natural language

```bash
cartographer query "what is the architecture"
```

The `query` command automatically figures out what you're asking and runs the right analysis. It can detect 9 different intent types (architecture, explain, impact, path, summarize, git blame, git why, git cochange, plain search).

### See what depends on something

```bash
cartographer impact config.py
```

This answers the question "what would break if I changed this file?" by tracing all import/reference edges backwards from the target.

### Explore connections

```bash
cartographer neighbors UserService --depth 2
cartographer path "controller" "repository"
```

### Generate semantic embeddings

```bash
cartographer embed
cartographer similar "database connection pool"
```

Embedding converts each code entity into a 384-dimensional vector that captures its meaning. The similarity search then finds nodes that are conceptually related, even if they don't share keywords.

### Index git history

```bash
cd /path/to/repo && cartographer git index
cartographer git blame config.py
cartographer git why UserService
cartographer git cochange settings.py
cartographer git authors
```

### Start the MCP server for AI assistants

```bash
cartographer mcp
```

This starts a local server that exposes Cartographer's tools to AI coding assistants like Claude Desktop, Cursor, or OpenCode. Configure your assistant to connect to it (see the [OpenCode Integration](opencode.md) doc for details).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | Path to the SQLite database |
| `HF_TOKEN` | (none) | HuggingFace token for model downloads (needed for some models) |

---

## What's Next?

- [Command Reference](commands.md) — every command with detailed options and examples
- [Architecture Deep Dive](architecture.md) — how the system works internally
- [OpenCode Integration](opencode.md) — using Cartographer with AI coding assistants
- [Troubleshooting](troubleshooting.md) — common issues and solutions
