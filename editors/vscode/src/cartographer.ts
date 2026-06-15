import { execSync, ExecSyncOptions } from "child_process";
import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";

// ── Public types ──────────────────────────────────────────────────────────

export interface SearchResult {
  name: string;
  type: string;
  file_path?: string;
  score?: number;
}

export interface Summary {
  name: string;
  path: string;
  total_nodes: number;
  total_edges: number;
  node_breakdown: Record<string, number>;
  edge_breakdown: Record<string, number>;
}

export interface ImpactResult {
  name: string;
  type: string;
  file_path?: string;
  via_edge?: string;
}

export interface NeighborResult {
  name: string;
  type: string;
  depth: number;
}

export interface PathResult {
  name: string;
  type: string;
  depth: number;
}

export interface GraphNode { id: number; name: string; type: string; file_path?: string }
export interface GraphEdge { source: number; target: number; type: string }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[]; node_types: Record<string, number>; total_nodes?: number; total_edges?: number }

export interface RepoInfo { name: string; path: string; nodes: number; edges: number }

// ── Client ─────────────────────────────────────────────────────────────────

export class CartographerClient {
  private output: vscode.OutputChannel;
  private bin: string;

  constructor(output: vscode.OutputChannel) {
    this.output = output;
    this.bin = this.findBin();
  }

  private findBin(): string {
    const cfg = vscode.workspace.getConfiguration("cartographer");
    const c = cfg.get<string>("binPath", "cartographer");
    if (c !== "cartographer") return c;
    // Prefer python3 -m cartographer (always works when package is installed)
    try {
      execSync("python3 -m cartographer version", { encoding: "utf-8", timeout: 5000 });
      return "python3 -m cartographer";
    } catch {}
    // Fall back: check PATH for a cartographer binary
    try {
      const r = execSync("which cartographer 2>/dev/null", { encoding: "utf-8" });
      if (r.trim()) return r.trim();
    } catch { /* ignore */ }
    return "cartographer";
  }

  private cfg<T>(key: string, def: T): T {
    return vscode.workspace.getConfiguration("cartographer").get<T>(key, def);
  }

  private globalFlags(): string[] {
    const f: string[] = [];
    const db = this.cfg("dbPath", "");
    if (db) f.push(`--db "${db}"`);
    return f;
  }

  private _repoName: string | null = null;

  private repoFlag(): string[] {
    const name = this._resolveRepoName();
    return name ? [`--repo "${name}"`] : [];
  }

  /** Find the repo name by matching workspace path or folder name in the DB. */
  private _resolveRepoName(): string | null {
    if (this._repoName) return this._repoName;
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return null;
    const db = this.cfg("dbPath", "") || path.join(os.homedir(), ".cartographer", "index.db");
    try {
      const raw = execSync(
        `python3 -c "
import sqlite3, sys
db, wpath, wname = sys.argv[1], sys.argv[2], sys.argv[3]
conn = sqlite3.connect(db)
# Try path match first, then name match
row = conn.execute('SELECT name FROM repositories WHERE path = ?', (wpath,)).fetchone()
if not row:
    row = conn.execute('SELECT name FROM repositories WHERE name = ?', (wname,)).fetchone()
conn.close()
if row:
    print(row[0])
" "${db}" "${ws.uri.fsPath}" "${ws.name}"`,
        { encoding: "utf-8", timeout: 10000 },
      );
      const name = raw.trim();
      if (name) this._repoName = name;
      return this._repoName;
    } catch {
      return null;
    }
  }

  private exec(args: string[]): string {
    const opts: ExecSyncOptions = { encoding: "utf-8", timeout: 120_000 };
    const cmd = `${this.bin} ${args.join(" ")}`;
    this.output.appendLine(`$ ${cmd}`);
    try {
      const raw = execSync(cmd, opts);
      const s = typeof raw === "string" ? raw : raw.toString();
      this.output.appendLine(s);
      return s;
    } catch (e: unknown) {
      const err = e as { stderr?: Buffer; stdout?: Buffer; message?: string };
      const msg = err.stderr?.toString() || err.stdout?.toString() || err.message || "unknown error";
      this.output.appendLine(`ERR: ${msg}`);
      throw new Error(msg);
    }
  }

  private repoName(): string {
    return vscode.workspace.workspaceFolders?.[0]?.name || "";
  }

  private repoPath(): string {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "";
  }

  private extensionDir(): string {
    return path.dirname(__dirname); // out/.. → editors/vscode
  }

  // ── CLI commands ──────────────────────────────────────────────────────

  index(p?: string): { success: boolean; files: number; dirs: number; duration_ms: number; errors: string[] } {
    const target = p || this.repoPath();
    if (!target) throw new Error("No workspace folder open");
    try {
      const out = this.exec(["index", `"${target}"`, ...this.globalFlags()]);
      const files = parseInt(out.match(/Indexed (\d+) files/)?.[1] || "0");
      const dirs = parseInt(out.match(/in (\d+) directories/)?.[1] || "0");
      const dur = parseFloat(out.match(/Duration: ([\d.]+)ms/)?.[1] || "0");
      const errs = out.split("\n").filter(l => l.startsWith("Warning:") || l.startsWith("Error:"));
      return { success: errs.length === 0, files, dirs, duration_ms: dur, errors: errs };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return { success: false, files: 0, dirs: 0, duration_ms: 0, errors: [msg] };
    }
  }

  search(query: string, nodeType?: string, limit?: number, repoName?: string): SearchResult[] {
    limit ??= this.cfg("maxResults", 40);
    const args = ["ask", `"${query}"`, `-l ${limit}`];
    if (nodeType) args.push(`-t "${nodeType}"`);
    try {
      const rf = repoName ? [`--repo "${repoName}"`] : this.repoFlag();
      const out = this.exec([...args, ...this.globalFlags(), ...rf]);
      this.output.appendLine(`search raw output:\n${out}`);
      const results: SearchResult[] = [];
      const root = this.repoPath();
      let pending: SearchResult | null = null;
      for (const line of out.split("\n")) {
        const entityMatch = line.match(/^\s{2}\[(\w+)\s*\]\s(.+)$/);
        if (entityMatch) {
          if (pending) results.push(pending);
          pending = {
            type: entityMatch[1],
            name: entityMatch[2].trim(),
            file_path: undefined,
          };
          continue;
        }
        if (pending && line.trim() && line.startsWith(" ")) {
          const path = line.trim();
          pending.file_path = root ? path.startsWith("/") ? path : `${root}/${path}` : path;
        }
      }
      if (pending) results.push(pending);
      return results;
    } catch (e) {
      this.output.appendLine(`search error: ${e}`);
      return [];
    }
  }

  ask(query: string): string {
    try { return this.exec(["query", `"${query}"`, ...this.globalFlags(), ...this.repoFlag()]); }
    catch { return "Query failed."; }
  }

  summarize(repoName?: string): Summary | null {
    try {
      const rf = repoName ? [`--repo "${repoName}"`] : this.repoFlag();
      const out = this.exec(["summarize", ...this.globalFlags(), ...rf]);
      const lines = out.split("\n");
      const s: Summary = {
        name: lines[0]?.replace("Repository: ", "").trim() || "",
        path: lines[1]?.replace("Path: ", "").trim() || "",
        total_nodes: parseInt(lines[2]?.replace("Total nodes: ", "").trim() || "0"),
        total_edges: parseInt(lines[3]?.replace("Total edges: ", "").trim() || "0"),
        node_breakdown: {}, edge_breakdown: {},
      };
      let section: string | null = null;
      for (const l of lines) {
        if (l.startsWith("Node breakdown:")) section = "nodes";
        else if (l.startsWith("Edge breakdown:")) section = "edges";
        else if (l.startsWith("Top files") || l.startsWith("Largest")) section = null;
        else if (section && /^\s{2}\S/.test(l)) {
          const parts = l.trim().split(": ");
          if (parts.length === 2) {
            if (section === "nodes") s.node_breakdown[parts[0].trim()] = parseInt(parts[1].trim());
            else s.edge_breakdown[parts[0].trim()] = parseInt(parts[1].trim());
          }
        }
      }
      return s;
    } catch { return null; }
  }

  architecture(): string {
    try { return this.exec(["architecture", "--detect", ...this.globalFlags(), ...this.repoFlag()]); }
    catch { return "Architecture detection failed."; }
  }

  impact(target: string): ImpactResult[] {
    try {
      const out = this.exec(["impact", `"${target}"`, ...this.globalFlags(), ...this.repoFlag()]);
      const results: ImpactResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{4}\[(\w+)\s*\]\s(.+?)\s\((.+)\)$/);
        if (m) results.push({ type: m[1], name: m[2].trim(), file_path: m[3].trim() });
      }
      return results;
    } catch { return []; }
  }

  neighbors(name: string, depth = 2): NeighborResult[] {
    try {
      const out = this.exec(["neighbors", `"${name}"`, `-d ${depth}`, ...this.globalFlags(), ...this.repoFlag()]);
      const results: NeighborResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^(\s*)\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: Math.floor(m[1].length / 2) });
      }
      return results;
    } catch { return []; }
  }

  path(from: string, to: string): PathResult[] {
    try {
      const out = this.exec(["path", `"${from}"`, `"${to}"`, ...this.globalFlags()]);
      const results: PathResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}(→\s)?\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: results.length });
      }
      return results;
    } catch { return []; }
  }

  similar(target: string): SearchResult[] {
    const limit = this.cfg("maxResults", 20);
    try {
      const out = this.exec(["similar", `"${target}"`, `-l ${limit}`, ...this.globalFlags(), ...this.repoFlag()]);
      const results: SearchResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}\[(\w+)\s*\]\s(.+?)\s+\(score:\s*([\d.]+)\)/);
        if (m) results.push({ name: m[2].trim(), type: m[1], score: parseFloat(m[3]) });
      }
      return results;
    } catch { return []; }
  }

  embed(): string {
    try { return this.exec(["embed", ...this.globalFlags(), ...this.repoFlag()]); }
    catch { return "Embedding failed."; }
  }

  gitIndex(): string {
    try { return this.exec(["git", "index", `--repo-path "${this.repoPath()}"`, ...this.globalFlags(), ...this.repoFlag()]); }
    catch { return "Git index failed."; }
  }

  getRepos(): RepoInfo[] {
    try {
      const db = this.cfg("dbPath", "") || path.join(os.homedir(), ".cartographer", "index.db");
      const raw = execSync(
        `python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
rows = conn.execute('''
    SELECT r.name, r.path,
           (SELECT COUNT(*) FROM nodes WHERE repository_id = r.id) as nodes,
           (SELECT COUNT(*) FROM edges WHERE repository_id = r.id) as edges
    FROM repositories r ORDER BY r.name
''').fetchall()
conn.close()
for n, p, nodes, edges in rows:
    print(f'{n}|{p}|{nodes}|{edges}')
" "${db}"`,
        { encoding: "utf-8", timeout: 10000 },
      );
      return raw.trim().split("\n").filter(Boolean).map(line => {
        const [name, path, nodes, edges] = line.split("|");
        return { name, path, nodes: parseInt(nodes || "0"), edges: parseInt(edges || "0") };
      });
    } catch {
      const s = this.summarize();
      return s ? [{ name: s.name, path: s.path, nodes: s.total_nodes, edges: s.total_edges }] : [];
    }
  }

  searchByType(nodeType: string, limit = 100, repoName?: string): SearchResult[] {
    return this.search("", nodeType, limit, repoName);
  }

  // ── Graph data via bundled Python script ──────────────────────────────

  getGraphData(limit = 80, repoOverride?: string): GraphData {
    const db = this.cfg("dbPath", "") || path.join(os.homedir(), ".cartographer", "index.db");
    const script = path.join(this.extensionDir(), "scripts", "graph_data.py");
    const pys = new Set<string>();
    if (this.bin.includes("python")) pys.add(this.bin.split(" ")[0]);
    pys.add("python3"); pys.add("python");
    const tryRepo = (r: string | null | undefined): GraphData | null => {
      if (!r) return null;
      this.output.appendLine(`getGraphData: trying repo '${r}', scripts at '${script}', db='${db}'`);
      // Primary: run graph_data.py directly (standalone, no module needed)
      for (const py of pys) {
        try {
          const cmd = `"${py}" "${script}" "${db}" "${r}" ${limit}`;
          this.output.appendLine(`getGraphData: trying script: ${cmd}`);
          const raw = execSync(cmd, {
            encoding: "utf-8", timeout: 30_000,
          });
          const d = JSON.parse(raw);
          if (d.error) { this.output.appendLine(`getGraphData: script error: ${d.error}`); continue; }
          this.output.appendLine(`getGraphData: script OK — ${d.nodes?.length || 0} nodes`);
          return d;
        } catch (e) {
          this.output.appendLine(`getGraphData: script '${py}' failed: ${e}`);
        }
      }
      // Fallback: try CLI graph-data command
      try {
        this.output.appendLine("getGraphData: trying CLI fallback");
        const out = this.exec(["graph-data", `-l ${limit}`, ...this.globalFlags(), ...(r ? [`--repo "${r}"`] : [])]);
        const d = JSON.parse(out);
        if (d.error) { this.output.appendLine(`getGraphData: CLI error: ${d.error}`); return null; }
        this.output.appendLine(`getGraphData: CLI OK — ${d.nodes?.length || 0} nodes`);
        return d;
      } catch (e) {
        this.output.appendLine(`getGraphData: CLI fallback failed: ${e}`);
      }
      return null;
    };
    return (
      tryRepo(repoOverride) ||
      tryRepo(this.repoName()) ||
      tryRepo(this._resolveRepoName()) ||
      tryRepo(this._firstRepoName()) ||
      { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0 }
    );
  }
  private _firstRepoName(): string | null {
    try {
      const db = this.cfg("dbPath", "") || path.join(os.homedir(), ".cartographer", "index.db");
      const raw = execSync(`python3 -c "import sqlite3,sys; r=sqlite3.connect(sys.argv[1]).execute('SELECT name FROM repositories LIMIT 1').fetchone(); print(r[0] if r else '')" "${db}"`,
        { encoding: "utf-8", timeout: 5000 });
      return raw.trim() || null;
    } catch { return null; }
  }
}
