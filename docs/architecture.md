# Architecture — How Cartographer Works

## Pipeline

```
discover_files (TEXT_EXTENSIONS + LANGUAGE_EXTENSIONS, .gitignore + .cartographerignore, 10MiB skip, symlink loop guard, 0.1% binary check)
  → detect_languages / fingerprint_frameworks / package_managers / monorepo
  → _parse_repository (ThreadPool min(cpu,8), 30s future timeout, per-file isolation → Generic fallback, 1MiB/2MiB caps)
    → BaseParser (Parser(Language), b"\x00" check, has_error, count_error_nodes, errors=replace, 1MiB/2MiB truncate warnings)
  → extract_references (FILE_EXTENSIONS per lang, IMPORT_PATTERNS regex, suffix-index, MODULE_INDICATORS)
  → extract_schema (Django/JPA/Prisma/SQL, CREATE TABLE parsing)
  → build_graph (reclassify Controller/Service/Middleware/Repository, chunked 1000, SQLITE_BUSY retry 3×, WAL)
  → embeddings (bge-small-en-v1.5, 384d, chunked 500, batch 256, 3× model retry, valid-blob filter, hybrid keyword boost)
  → storage (SQLite WAL, busy_timeout 5s, indices repo/type/file_path/name)
```

## Storage

`storage/connection.py` — `get_connection(path, timeout=10.0, check_same_thread=False)` + `WAL/NORMAL/-8000/MEMORY/5000`. `init_schema` creates:

- `repositories(id,path UNIQUE,name,manifest_json)`
- `nodes(id,repo,node_type,name,file_path,metadata_json)` — `type ∈ {directory,file,class,function,method,interface,enum,constant,variable,api_endpoint,controller,service,repository_layer,middleware,job,worker,queue,table,markdown,adr,diagram,wiki,commit}`
- `edges(id,repo,src,tgt,edge_type)` — `CONTAINS|DEFINES|DECLARES|CALLS|INHERITS|IMPLEMENTS|DECORATES|IMPORTS`
- `embeddings(id,node,model,vector BLOB)` — `UNIQUE(node,model)`
- `commits/commit_files/commit_authors/architecture`

Indices: `idx_nodes_repo_type`, `idx_nodes_file_path/name`, `idx_edges_repo_type/source/target`, `idx_embeddings_node_model` (UNIQUE).

## Parsers (31 languages, 24 files)

`parser/base.py` — `Parser(Language)`, `_count_error_nodes`, `_node_text(errors=replace)`, docstring `///|/**|//`.

`parser/registry.py` — `_ensure_parsers` does `_try_import` per language (missing grammar → `GenericParser` with `bytes→utf-8` regex), `register_parser(language, cls, [".ext"])` extends `LANGUAGE_EXTENSIONS` + `ENG_EXT`, `get_parser` thread-local cache, fallback `GenericParser` for any unknown.

Languages: `python (.py)`, `javascript (.js/.jsx/.mjs/.cjs)`, `typescript (.ts)`, `tsx`, `go (.go)`, `rust (.rs)`, `java (.java)`, `kotlin (.kt/.kts)`, `csharp (.cs)`, `php (.php/.phtml)`, `ruby (.rb)`, `c (.c/.h)`, `cpp (.cpp/.hpp/.cc/.cxx)`, `swift (.swift)`, `scala (.scala/.sc)`, `elixir (.ex/.exs)`, `lua (.lua)`, `julia (.jl)`, `zig (.zig)`, `groovy (.groovy/.gvy/.gsh)`, `dart (.dart)` (regex + `tree_sitter_dart` if present), `markdown (.md/.markdown/.mdx)` (headings→`markdown`/`adr`, `mermaid`→`diagram`), `yaml/json/toml/sql/html/css/shell/dockerfile/protobuf` via `GenericParser` (class/func + import regex, `empty→[]`).

`EMBEDDABLE_TYPES = {class,function,method,file,interface,enum,type_alias}` — others indexed not embedded.

## Graph Builder (`graph/builder.py`)

`build_graph` — `reclassify` `*Controller→controller` etc., `DELETE embeddings/architecture/edges/nodes` per repo, `base_id = MAX(id)+1`, `dir_cache`/`file_cache`, `_batch_node/_batch_edge` with `name_to_entity_ids`, `_process_entity` (`MODULE→skip`, `DEFINES/DECLARES/CONTAINS`), `references` → `IMPORTS`, `_resolve_relationships` (`CALLS/INHERITS/IMPLEMENTS` via `name_to_entity_ids`). Chunked `1000`, commit retry `0.2*(attempt+1)`, `invalidate_cache`.

`update_file_in_graph`/`delete_file_from_graph` — incremental, `_ensure_dir_path_nodes`.

## Embeddings (`embedding/engine.py`)

`EMBEDDING_MODEL bge-small-en-v1.5` / `384` / `256` / `0`. `_get_model` 3× retry + backoff `2^attempt`. `_build_node_text` includes `node_type:name`, `file`, `directory`, `docstring` (500), `signature`, `parameters` (10), `returns`, `decorators` (200), `bases` (5), `parent/module`, `language`.

`generate_embeddings` — `WHERE node_type IN EMBEDDABLE AND e.id IS NULL`, count skip, chunked texts `500`, `model.embed(batch 256)` with per-chunk `try/except` + incremental `executemany` + `commit`, `total_embedded, skip_count`.

`_load_vectors` — filter `len(blob)==384*4`, `>100k` warning, `frombuffer(b"".join(blobs)).reshape`, per-row fallback, `nan_to_num`, `norm==0 →1`, cache `10` entries LRU, `exclude_id` mask.

`similarity_search` — `_encode_query` cached `128`, `query_norm==0→[]`, `hybrid` boost `+0.1*overlap` when `top<0.35` (name/file words), filter `<0.15` but keep 3, `argpartition` top. `find_similar` similar.

## Ingestion (`ingestion/engine.py`, `discoverer.py`)

`discover_files` — `_load_ignore_patterns(.cartographerignore)` + `_load_gitignore_spec` (pathspec `gitwildmatch`), `_walk` sorted, `IGNORED_DIRS` (`node_modules/.git/__pycache__`…), `BINARY_EXTENSIONS` check `b"\x00"`, `MAX_DISCOVER_FILE_BYTES 10MiB`.

`index_repository` — `lang_counts/package_managers/build_systems/monorepo/frameworks`, dirs set, `manifest RepositoryManifest`, `_parse_repository`, `extract_references`/`extract_schema` (each `try`), `build_graph`, `fatal Filter: not (startswith Parse/Failed to parse/large/truncated)`.

`_parse_single_file` — `10MiB` skip → `Parse skipped`, `2MiB` truncate log, `_detect_lang_for_file` (Dockerfile/makefile), `get_parser` → `Generic` fallback, `parse_file` + `extract_entities` with inner `try` → generic on crash, ultimate isolation.

`_parse_repository` — `supported_languages` → `ext_map`, `ThreadPool min(cpu,8)`, `as_completed` `done%10`, `future.result(timeout=30)` → `Parse timeout` + `cancel`, `future failed` per-file, `sort` by path, `update_index` reuses same `Generic` fallback + `generate_embeddings` for changed nodes.

## Retrieval

`searcher.py` — `_TYPE_PRIORITY` (`api_endpoint 1.2 > controller 1.1 > class/interface/service 1.0 > function/method 0.9 > file 0.7`), `_name_score` (`==1.0/startswith0.8/contains0.5/multi-word0.3+`), `_compute_score` (`0.5*name+0.2*type+0.2*log(ref)+0.1/depth`), `_search` `name LIKE %q%` + `r.name = ?` exact first, `LIKE q%` second, clamped `limit 1-100`, empty `→[]`, escaped. `_fetch_ref_counts` `LEFT JOIN edges target`.

`traversal.py` — `_traverse` DFS `visited`, `get_neighbors`, `impact_analysis` transitive `target_id` BFS batch, `_resolve_target` `isdigit→id` else `name=file_path exact else LIKE`, `find_path` BFS `max_depth`, `_build_path_result`.

`summarizer.py` — `generate_summary` picks `CWD/path` exact else largest `COUNT(nodes)`, `node_breakdown` / `edge_breakdown`, `top_files`, `top_classes` (`method count`).

## Architecture (`architecture/engine.py`)

`_tokenize` `([a-z0-9])([A-Z])→_`, split `_[.]` lower. `_score_name` `suffix 1.0 / prefix 0.8 / token 0.75 / contains 0.5`. `_score_file_name` `boundary_keywords {api,spec,test,env,lib,ui}` token check else `in stem`. `_score_directory` `== or token 1.0 / contains 0.6`.

`FRAMEWORK_FILE_RULES` for `django/flask/rails/express/fastapi/next.js/laravel/actix_web/axum/flutter/dart`. `LAYER_META` + `documentation`.

`_collect_evidence` — `class/interface/enum/controller/service/...` naming, `I/T` prefix, `function`, `file`, `framework_file`, `directory`, `django_app/rails`, `docs` (`*.md→documentation 0.7`, `adr 0.9`), `markdown_node`, `flutter`, `infra yaml/dockerfile`, `proto→api`.

`_aggregate_layers` — `avg*0.35+max*0.5+diversity*0.05` × `min(count/3,1)` with `single-entity single-kind & max<1.0 → *0.75` and `len==1 & max<0.9 → *0.7`, filter `<0.2`.

`_analyze_dependency_flow` via `IMPORTS` edges + `entity_map`.

## Query (`query/engine.py`)

`INTENT_RULES` 9 intents with priority regex, `_extract_targets`, `classify_intent` → `search fallback`.

Builders `_search_step/_summarize_step/_explain_step/_impact_step/_path_step/_architecture_step/_build_git_*` → `PLAN_BUILDERS`; `execute_query` → `builder` + `max_tokens` trunc (`estimate_tokens`).

## Compression (`compression/engine.py`)

4 strategies, `estimate_tokens` (`chars/4`), `compress` by `max_tokens`.

## Robustness Summary

Parser: 1MiB/2MiB caps, binary guard, timeout 30s, generic fallback, isolated errors. Embedding: model retry 3×, chunked 500, valid-blob filter, hybrid boost, zero-vector fallback. Graph: chunked 1000, WAL retry. Storage: `timeout 10s`, `busy 3×`. Ingestion: 10MiB skip, per-file isolation. Search: clamped, empty fast path, DB try/finally.
