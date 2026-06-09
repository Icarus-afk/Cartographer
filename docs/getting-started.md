# Getting Started with Cartographer

Cartographer turns any repository into a navigable knowledge graph. This guide walks through installation, your first index, and the most common workflows.

## Prerequisites

- Python 3.11 or later
- pip
- Git (for git intelligence features)

## Installation

### From source (recommended for now)

```bash
git clone https://github.com/your-org/cartographer.git
cd cartographer
pip install -e .
```

Verify it works:

```bash
cartographer version
# cartographer 0.1.0
```

### Dependencies

Cartographer installs these key dependencies automatically:

| Dependency | Purpose |
|------------|---------|
| `click>=8.1` | CLI framework |
| `tree-sitter>=0.23` | AST parsing (19 languages) |
| `fastembed>=0.8.0` | Vector embeddings for semantic search |
| `pyyaml>=6.0` | YAML config support |
| `packaging>=24.0` | Package version detection |

Tree-sitter language grammars are downloaded on demand when you index a repository in a given language.

The fastembed model (`BAAI/bge-small-en-v1.5`) is downloaded on first use of `cartographer embed`.

## Your First Index

### 1. Index a repository

```bash
cartographer index /path/to/your/project
```

Output example:

```
Indexed 152 files in 24 directories
Duration: 2431.18ms
Languages: python: 89, javascript: 43, typescript: 20
Entities: 152 files parsed, 45 classes, 312 functions, 89 methods
References: 234 cross-file imports
```

The database is stored at `~/.cartographer/index.db` by default.

### 2. Specify a custom database

```bash
cartographer --db /tmp/my-project.db index /path/to/your/project
# or
export CARTOGRAPHER_DB=/tmp/my-project.db
cartographer index /path/to/your/project
```

### 3. Search for symbols

```bash
cartographer ask "UserService"
```

Output:

```
Found 5 result(s):
  [class       ] UserService
           src/services/user_service.py
  [class       ] UserServiceImpl
           src/services/impl/user_service_impl.py
  [interface   ] IUserService
           src/services/user_service.py
  [function    ] create_user_service
           src/factories/service_factory.py
  [method      ] get_user_service
           src/controllers/user_controller.py
```

### 4. Ask natural language questions

```bash
cartographer query "what is the architecture"
cartographer query "explain the UserRepository class"
cartographer query "what depends on the auth module"
cartographer query "path between controller and repository"
cartographer query "summarize this project"
```

The `query` command automatically detects what you're asking and runs the right analysis.

### 5. Analyze architecture

```bash
cartographer architecture --detect
```

This detects layers, architecture patterns, frameworks, and dependency flows.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | Path to the SQLite database |
| `HF_TOKEN` | (none) | HuggingFace token for model downloads |

## Next Steps

- [Command Reference](commands.md) — all commands with detailed examples
- [Architecture Deep Dive](architecture.md) — how the system works internally
- [OpenCode Integration](opencode.md) — using Cartographer with AI coding assistants
- [Troubleshooting](troubleshooting.md) — common issues and solutions
