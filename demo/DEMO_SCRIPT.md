# THE NEW HIRE TEST — live terminal demo (6 minutes)
### Cartographer @ ULAB Foundation Day

> Companion interactive visual: `demo/interactive.html` (double-click, works
> offline — same DB, same real outputs). Full laptop install (package, corpus,
> DB, data, VS Code extension): `bash demo/setup.sh`.

**One-line premise (say first):**
> "On Monday you join a company. They hand you Flask — real software that powers thousands of websites — and say: *understand it by Friday.* Today we do it in 6 minutes, live, nothing pre-recorded."

**Stage setup (do before the audience arrives):**
1. Run `bash demo/setup.sh` (clones Flask to `/tmp/flask-demo`, builds map).
2. `export CARTOGRAPHER_DB=$PWD/demo/flask-demo.db` (run from repo root).
3. Terminal: fullscreen, dark theme, font **22pt+**, `PS1="$ "` (clean prompt). Test projector contrast.
4. VS Code open on `/tmp/flask-demo` with the Cartographer extension, graph command ready (`Ctrl+Shift+C` → Graph). F11 fullscreen.
5. Keep this file open on your phone/second screen. Every command below is copy-pasteable.

---

## ACT 1 — The problem (0:00–0:45)

**Say:** "Flask. 206 files. 108 classes, 718 functions. This is SMALL — real company codebases are a hundred times bigger. A new hire takes weeks just to find their way around. An AI assistant has the same problem: it must read every file, one by one, at full price."

```bash
find /tmp/flask-demo/src /tmp/flask-demo/tests -name "*.py" | wc -l
# → 65  (say: "65 Python files just in src+tests — 206 total with docs and examples")
```

## ACT 2 — The old way: grep finds text, not answers (0:45–1:45)

**Say:** "This is what developers — and AI agents — do today: search text."

```bash
grep -rn "class Flask" /tmp/flask-demo/src
```
Expected (5 lines): `class Flask(App)` in app.py, plus `FlaskProxy`, `FlaskClient`, `FlaskCliRunner`, `FlaskGroup` in other files.
**Say:** "Five answers that all look the same. Which one is the real one? Grep doesn't know — it matched letters, not meaning."

```bash
grep -rln "sansio" /tmp/flask-demo/src
```
Expected (9 files): blueprints, logging, app, config, typing, debughelpers, templating, sansio/app, json/provider.
**Say:** "Nine files mention the word 'sansio'. But which ones would actually BREAK if I change the core file? And which real dependents never use that word at all? Grep can't tell you — it finds text, not relationships. Watch this."

## ACT 3 — Build the map, live (1:45–2:45)

**Say:** "Cartographer reads the whole project once and draws a map: every class, function and file as dots, every connection as lines."

```bash
time cartographer index /tmp/flask-demo
```
Expected: `206 files parsed, 108 classes, 718 functions, 333 methods … 176 cross-file imports` in **~1 second**.
**Say:** "One second. 1,910 pieces of code, 2,611 connections. (If anyone doubts it's live — it just re-read all 206 files in front of you.)"

```bash
cartographer summarize
```
Expected: `Total nodes: 1910, Total edges: 2611`, breakdown, top files (`tests/test_basic.py (104)`, `src/flask/sansio/app.py (79)`).

**VISUAL MOMENT — switch to VS Code (20 seconds, no talking over it):**
`Ctrl+Shift+C` → Graph → fullscreen. Let the map bloom. Then say: *"This is the map. Every dot is code; every line is a connection. Now let's interrogate it."* Switch back to terminal.

## ACT 4 — Just ask (2:45–4:00)

**Say:** "No filenames, no guessing. Ask in plain words."

```bash
cartographer ask "Flask" -t class --limit 3
```
Expected: `[class] Flask → src/flask/app.py`, then FlaskCliRunner, FlaskClient — ranked with scores.
**Say:** "The real one first, with a confidence score — ranked by importance, not alphabet."

**Say:** "Now the file everyone fears — the 79-entity core. Instead of reading it…"

```bash
cartographer file-summary "src/flask/sansio/app.py"
```
Expected: 1 class (`App`), its imports, what depends on it, `App -> Scaffold`, key calls — ~10 lines.
**Say:** "The whole file digested into 10 lines — about 200 tokens instead of 2,000. This is what the AI reads instead of the file."

**Say:** "And look inside the core class without opening anything:"

```bash
cartographer neighbors "App" -d 1
```
Expected: `config_class`, `url_map_class`, `secret_key`, `jinja_environment`… (first ~15 lines, stop with Ctrl+C or let it scroll).
**Say:** "The anatomy of the heart of Flask — its anatomy, on demand."

## ACT 5 — Questions grep cannot ask (4:00–5:00)

**Say:** "Back to our grep list of 9 files. Who REALLY depends on the core file?"

```bash
cartographer impact "src/flask/sansio/app.py"
```
Expected: 18 files via IMPORTS (`app.py`, `config.py`, `ctx.py`, `globals.py`, `sessions.py`, `wrappers.py`, `cli.py`, `testing.py`…).
**Say:** "Eighteen true dependents — including files that never contain the word 'sansio', which grep missed, and excluding `typing.py`, which only mentioned it in passing. Text versus relationships."

**Say:** "And how are two distant pieces connected?"

```bash
cartographer path "App" "Scaffold"
```
Expected: `Path (2 hops): [class] App → [class] Scaffold`.
**Say:** "Two hops: App inherits from Scaffold. Try that with grep."

(Optional, if ahead of time:)
```bash
cartographer architecture --detect
```
Expected: layers with confidence — Testing 94%, Config 93%, MVC 73%.
**Say:** "It even detects the architecture — layers and design patterns, with confidence scores. No manual audit."

## ACT 6 — The agent view + payoff (5:00–6:00)

**Say:** "Everything you just saw, an AI can use too — as structured data, not scraped text:"

```bash
cartographer --json ask "Flask" -t class --limit 2
```
Expected: `{"status": "ok", "count": 2, "results": [{"type": "class", "name": "Flask", "file_path": "src/flask/app.py", "score": 0.79…}]}`.
**Say:** "This exact JSON is what Claude, Cursor or Opencode receives through our 20 MCP tools. No parsing, no hallucinating filenames. The rule for agents is simple: *file_summary instead of reading files, impact instead of grep.*"

**Close (no more commands — look at the audience):**
> "The math: understanding 50 files the old way costs about 60,000 tokens. Through the map: about 200 — **99% less**. A five-question session saves ~96,000 tokens. At scale that's tens of thousands of dollars a month — and new hires who understand the codebase on day one instead of week three.
>
> Cartographer: a map of code, for humans and for AI. Open source, MIT, 31 languages. Thank you — questions?"

---

## FALLBACKS (if anything fails live)

| Failure | Recovery (all pre-tested) |
|---|---|
| No internet on stage | Everything is local: repo at `/tmp/flask-demo`, DB in `demo/`. Only `setup.sh` needs internet — run it beforehand. |
| `index` slow/hangs | DB is already built and committed (`demo/flask-demo.db`). Skip indexing: `cartographer status` + `summarize` prove the map. |
| VS Code graph won't load | Skip it. The terminal IS the demo; say "the map behind these answers" and move on. |
| Wrong/changed output | Outputs above were captured from this exact DB. Pin versions: Flask is `--depth 1` from 2026-10-03; Cartographer 0.1.0. |
| Typo under pressure | Don't type — paste each block from this file on your phone. |
| Projector text too small | Minimum 22pt font, `cartographer ... \| head -n 15` to keep output on one screen. |

## REHEARSAL CHECKLIST
- [ ] `bash demo/setup.sh` runs clean on stage laptop
- [ ] All 9 commands pasted once, outputs match this script
- [ ] Terminal 22pt+, high contrast, fullscreen tested on projector
- [ ] VS Code graph opens in <10s and zooms/fits readably from 5 meters
- [ ] Phone/second screen has this file open (copy-paste source)
- [ ] Total run-through timed: target 5:30–6:00
