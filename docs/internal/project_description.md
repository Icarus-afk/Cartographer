# Cartographer — Project Description

Cartographer is a tool that reads a codebase and builds a map of how everything connects. It scans every file to find classes, functions, methods, and files, then figures out how they relate — what imports what, what calls what, what inherits from what. All of this is stored in a portable SQLite database that can be searched in under a second.

The system ingests source code across **20 programming languages** using Tree-sitter parsing with ~200 query patterns: Python, JavaScript, TypeScript, TSX, Go, Rust, Java, Kotlin, C#, PHP, Ruby, C, C++, Swift, Scala, Elixir, Lua, Julia, Zig, and Groovy. It resolves cross-file imports, detects architectural layers (Controller, API, Presentation, Business, Data, Testing, Middleware, Config, Utility) via multi-strategy scoring, and fingerprints frameworks from package manifests. The graph uses typed edges (CONTAINS, DEFINES, IMPORTS, CALLS, INHERITS, IMPLEMENTS, DECLARES) and stores each node at roughly 310 bytes.

Beyond the knowledge graph, Cartographer includes a **compression engine** that fits output to any token budget (200–8,000 tokens) with four adaptive strategies, a **query planner** that classifies natural language intent across nine categories, a **git intelligence engine** for commit indexing, blame analysis, co-change detection, and "why was this introduced?" queries, and an **embedding engine** using ONNX-runtime for semantic similarity search. The default model is `BAAI/bge-small-en-v1.5` (384-dim), configurable via `.env` to any model from the fastembed library.

Indexing uses a bounded `ThreadPoolExecutor` (max 2 workers) to avoid CPU pegging on laptops. Binaries are skipped via extension whitelist plus null-byte sampling (8 KB). The system is designed to run on consumer hardware — no GPU needed.

Cartographer has been benchmarked against **22 real-world repositories** totalling over 25,000 files: django, react, spring-boot, hugo, junit5, fastapi, redis, tokio, kotlinx.coroutines, json, cats, serde, Humanizer, and more. It indexes at an average of 459 files/s on a Ryzen 7 7840HS with 16GB DDR5 RAM. The knowledge graph contains 219,882 nodes and 264,840 edges. Embedding generation takes about 666 seconds for all 22 repos (jina-embeddings-v2-small-en, CPU). Semantic search queries achieve 220/220 (100%) top-5 recall across the full benchmark suite. When used with AI coding assistants via MCP, it reduces token consumption by replacing raw file dumps with structured graph queries — roughly 150 tokens per query vs 512 tokens for manual context selection, and versus hundreds of thousands for a full source dump.

The system is written in Python, licensed under MIT, and is currently in alpha development. It powers a 30-command CLI, a VS Code extension with live D3 graph visualization, and a full Model Context Protocol (MCP) server exposing 14 tools and 3 resources for AI coding assistants. MCP integration has been tested with OpenCode, Claude Desktop, and Cursor.

---

## LinkedIn Post

I am working on Cartographer — an open source tool that reads your codebase and builds a searchable map of how everything connects.

You give it a GitHub repo. It scans every file to find classes, functions, and files. Then it figures out what imports what, what calls what, and what inherits from what. All of this goes into a small SQLite database that the tool can search really fast.

You can ask things like "where is the error handling logic" or "what depends on this module" and get an answer in under a second. It works across 20 programming languages.

I benchmarked it against 22 real repos — django, react, spring-boot, redis, tokio, fastapi, and 16 more — about 25,000 files total. It indexes at around 460 files per second on my laptop (Ryzen 7 7840HS, 16GB DDR5, CPU only). The whole knowledge graph across all 22 repos is about 220,000 nodes with 265,000 connections. Semantic search passed 220 out of 220 test queries.

It also connects to AI coding assistants through MCP — so tools like Cursor and Claude Desktop can search your codebase naturally. Instead of dumping entire files as context, it sends only the relevant pieces, which saves tokens.

This is early days and I have a long list of improvements planned. If you work with large codebases or monorepos, I would love to hear what kinds of questions you wish your tools could answer. The repo is on GitHub under MIT.
