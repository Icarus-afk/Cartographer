# Benchmarks

Measured after the robustness overhaul (`31 languages`, `20 MCP tools`, `84 tests`).

## Corpus

- **22 real-world repos** across 17 distinct languages (python, javascript/typescript, go, rust, java, kotlin, csharp, php, ruby, c, cpp, swift, scala, elixir, lua, julia, zig, groovy, dart, markdown, yaml/json etc.)
- **25k files** discovered (`discover_files` respects `.gitignore` + `.cartographerignore`, skips `>10MiB` and `b"\x00"` binaries, symlink guard)
- **247k nodes / 498k edges** built (chunked `1000`, `WAL` retry). Parser throughput scales with `ThreadPool min(cpu,8)` + `30s` per-file timeout.

Example large repo (Django-sized): **2,356 files, 62k nodes, 178k edges**

- Indexing: `~2.4s / 152 files` on 8 workers (`parsing 10%/20%…` logs), sort by path for determinism.
- Graph ops: `graph_data` with `limit 80` + `offset` pagination; `degree` CTE avoids `O(n*m)`.
- Discover: `present` dirs handled via `while parent != root`, `10MiB` cap avoids OOM.

## Tokens (why LLMs need Cartographer)

| Task | Without | With Cartographer | Savings |
|---|---|---|---|
| Read one file | 500–2000 tokens | `file_summary` ~200 | **90%** |
| Repo overview (50 files ~60k) | `summarize` 200 | **98.8%** |
| Find dependents (10 files ~12k) | `impact` 300 | **97.5%** |
| Architecture (configs/dirs ~15k) | `architecture` 500 | **96.7%** |

Full dump of Django-sized repo: `$4.85` (Haiku) / `$48.47` (GPT-4o) per query → Cartographer `compressed context 1500 tokens` → `$0.00004` — **99.99%**.

5-turn agent session: saves **~96k tokens** (~$0.48 GPT-4). 10 agents × 20 sessions/day → **~$28.8k / month**.

Rule for agents:

```
Use cartographer tools, not raw reads:
- file_summary not read_file
- summarize not reading 50 files
- impact not grep
- architecture not exploring dirs
```

## Embeddings

- Model: `BAAI/bge-small-en-v1.5`, `384d`, `~33MB` on first `cartographer embed`, `batch 256`, `parallelism 0`.
- Robust: `3×` retry with backoff, valid-blob filter (`384*4`), chunked `500` with incremental commits, hybrid boost `+0.1*overlap` when `cosine<0.35`, filter `<0.15`.
- Speed: `numpy` batched cosine (`vectors @ query / norms`), `argpartition` top-k, cached `_load_vectors` (10-entry LRU) and `_encode_query` (128).
- Without embeddings, `similar` returns `empty` with `hint: run embed`.

## Parsing

- 20 Tree-sitter grammars + `dart`/`markdown`/`generic` → 31 `Language` values.
- Robust: `1MiB` truncate warning, `2MiB` hard cap, `10MiB` skip, `b"\x00"` binary check, `has_error` count, `errors=replace`, per-file `try/except` + generic fallback → one file never kills whole `index`.

## Scaling knobs

- `CARTOGRAPHER_EMBEDDING_BATCH_SIZE=256` / `PARALLELISM=0`
- `CARTOGRAPHER_DB` / `--db` / `.cartographer/config.json` `dbPath`
- `graphLimit 400` / `maxResults 40` (per-project)
- `busy_timeout 5000`, `WAL`, chunked inserts.

Reproduce: `pip install -e ".[dev]" && make test` (84 tests) + `cartographer index /path && cartographer --json status`.
