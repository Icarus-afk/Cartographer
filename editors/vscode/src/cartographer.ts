import { spawnSync } from "child_process";
import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";

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

export class CartographerClient {
  private output: vscode.OutputChannel;
  private bin: string;
  private _repoName: string | null = null;

  constructor(output: vscode.OutputChannel) {
    this.output = output;
    this.bin = this.findBin();
  }

  private dbPath(): string {
    return this.cfg("dbPath", "") || path.join(os.homedir(), ".cartographer", "index.db");
  }

  private findBin(): string {
    const cfg = vscode.workspace.getConfiguration("cartographer");
    const c = cfg.get<string>("binPath", "cartographer");
    if (c !== "cartographer") return c;
    try {
      const r = spawnSync("python3", ["-m", "cartographer", "version"], { encoding: "utf-8", timeout: 5000 });
      if (r.status === 0) return "python3 -m cartographer";
    } catch { /* ignore */ }
    try {
      const r = spawnSync("which", ["cartographer"], { encoding: "utf-8" });
      if (r.status === 0 && r.stdout.trim()) return r.stdout.trim();
    } catch { /* ignore */ }
    return "cartographer";
  }

  private cfg<T>(key: string, def: T): T {
    return vscode.workspace.getConfiguration("cartographer").get<T>(key, def);
  }

  private globalFlags(): string[] {
    const f: string[] = [];
    const db = this.cfg("dbPath", "");
    if (db) f.push("--db", db);
    return f;
  }

  private repoFlag(): string[] {
    const name = this._resolveRepoName();
    return name ? ["--repo", name] : [];
  }

  private exec(args: string[]): string {
    const binParts = this.bin.split(/\s+/);
    const allArgs = [...binParts, ...args];
    this.output.appendLine(`$ ${this.bin} ${args.join(" ")}`);
    const r = spawnSync(allArgs[0], allArgs.slice(1), {
      encoding: "utf-8", timeout: 120_000,
    });
    if (r.error) {
      this.output.appendLine(`ERR: ${r.error.message}`);
      throw r.error;
    }
    if (r.status !== 0) {
      const msg = (r.stderr?.trim() || r.stdout?.trim() || `exit code ${r.status}`).slice(0, 500);
      this.output.appendLine(`ERR: ${msg}`);
      throw new Error(msg);
    }
    this.output.appendLine(r.stdout);
    return r.stdout;
  }

  private _resolveRepoName(): string | null {
    if (this._repoName) return this._repoName;
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return null;
    try {
      const db = this.dbPath();
      const r = spawnSync("python3", ["-c",
        "import sqlite3,sys\ndb,wpath,wname=sys.argv[1],sys.argv[2],sys.argv[3]\n"
        + "c=sqlite3.connect(db)\n"
        + "row=c.execute('SELECT name FROM repositories WHERE path = ?',(wpath,)).fetchone()\n"
        + "if not row:\n"
        + "  row=c.execute('SELECT name FROM repositories WHERE name = ?',(wname,)).fetchone()\n"
        + "c.close()\n"
        + "if row: print(row[0])",
        db, ws.uri.fsPath, ws.name,
      ], { encoding: "utf-8", timeout: 10000 });
      if (r.status === 0) {
        const name = r.stdout.trim();
        if (name) this._repoName = name;
      }
      return this._repoName;
    } catch {
      this.output.appendLine("_resolveRepoName: failed");
      return null;
    }
  }

  private _firstRepoName(): string | null {
    try {
      const r = spawnSync("python3", ["-c",
        "import sqlite3,sys\n"
        + "c=sqlite3.connect(sys.argv[1])\n"
        + "row=c.execute('SELECT name FROM repositories LIMIT 1').fetchone()\n"
        + "c.close()\n"
        + "print(row[0] if row else '')",
        this.dbPath(),
      ], { encoding: "utf-8", timeout: 5000 });
      return r.status === 0 ? r.stdout.trim() || null : null;
    } catch {
      this.output.appendLine("_firstRepoName: failed");
      return null;
    }
  }

  private wsName(): string {
    return vscode.workspace.workspaceFolders?.[0]?.name || "";
  }

  private repoPath(): string {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "";
  }

  private extensionDir(): string {
    return path.dirname(__dirname);
  }

  // ── CLI commands ──────────────────────────────────────────────────────

  index(p?: string): { success: boolean; files: number; dirs: number; duration_ms: number; errors: string[] } {
    const target = p || this.repoPath();
    if (!target) throw new Error("No workspace folder open");
    try {
      const out = this.exec(["index", target, ...this.globalFlags()]);
      const files = parseInt(out.match(/Indexed (\d+) files/)?.[1] || "0");
      const dirs = parseInt(out.match(/in (\d+) directories/)?.[1] || "0");
      const dur = parseFloat(out.match(/Duration: ([\d.]+)ms/)?.[1] || "0");
      const errs = out.split("\n").filter(l => l.startsWith("Warning:") || l.startsWith("Error:"));
      return { success: errs.length === 0, files, dirs, duration_ms: dur, errors: errs };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.output.appendLine(`index error: ${msg}`);
      return { success: false, files: 0, dirs: 0, duration_ms: 0, errors: [msg] };
    }
  }

  search(query: string, nodeType?: string, limit?: number, repoName?: string): SearchResult[] {
    limit ??= this.cfg("maxResults", 40);
    const args = ["ask", query, "-l", String(limit)];
    if (nodeType) args.push("-t", nodeType);
    try {
      const rf = repoName ? ["--repo", repoName] : this.repoFlag();
      const out = this.exec([...args, ...this.globalFlags(), ...rf]);
      const results: SearchResult[] = [];
      const root = this.repoPath();
      let pending: SearchResult | null = null;
      for (const line of out.split("\n")) {
        const entityMatch = line.match(/^\s{2}\[(\w+)\s*\]\s(.+)$/);
        if (entityMatch) {
          if (pending) results.push(pending);
          pending = { type: entityMatch[1], name: entityMatch[2].trim(), file_path: undefined };
          continue;
        }
        if (pending && line.trim() && line.startsWith(" ")) {
          const p = line.trim();
          pending.file_path = root ? (p.startsWith("/") ? p : `${root}/${p}`) : p;
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
    try { return this.exec(["query", query, ...this.globalFlags(), ...this.repoFlag()]); }
    catch (e) { this.output.appendLine(`ask error: ${e}`); return "Query failed."; }
  }

  summarize(repoName?: string): Summary | null {
    try {
      const rf = repoName ? ["--repo", repoName] : this.repoFlag();
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
    } catch (e) { this.output.appendLine(`summarize error: ${e}`); return null; }
  }

  architecture(): string {
    try { return this.exec(["architecture", "--detect", ...this.globalFlags(), ...this.repoFlag()]); }
    catch (e) { this.output.appendLine(`architecture error: ${e}`); return "Architecture detection failed."; }
  }

  impact(target: string): ImpactResult[] {
    try {
      const out = this.exec(["impact", target, ...this.globalFlags(), ...this.repoFlag()]);
      const results: ImpactResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{4}\[(\w+)\s*\]\s(.+?)\s\((.+)\)$/);
        if (m) results.push({ type: m[1], name: m[2].trim(), file_path: m[3].trim() });
      }
      return results;
    } catch (e) { this.output.appendLine(`impact error: ${e}`); return []; }
  }

  neighbors(name: string, depth = 2): NeighborResult[] {
    try {
      const out = this.exec(["neighbors", name, "-d", String(depth), ...this.globalFlags(), ...this.repoFlag()]);
      const results: NeighborResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^(\s*)\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: Math.floor(m[1].length / 2) });
      }
      return results;
    } catch (e) { this.output.appendLine(`neighbors error: ${e}`); return []; }
  }

  path(from: string, to: string): PathResult[] {
    try {
      const out = this.exec(["path", from, to, ...this.globalFlags()]);
      const results: PathResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}(→\s)?\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: results.length });
      }
      return results;
    } catch (e) { this.output.appendLine(`path error: ${e}`); return []; }
  }

  similar(target: string): SearchResult[] {
    const limit = this.cfg("maxResults", 20);
    try {
      const out = this.exec(["similar", target, "-l", String(limit), ...this.globalFlags(), ...this.repoFlag()]);
      const results: SearchResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}\[(\w+)\s*\]\s(.+?)\s+\(score:\s*([\d.]+)\)/);
        if (m) results.push({ name: m[2].trim(), type: m[1], score: parseFloat(m[3]) });
      }
      return results;
    } catch (e) { this.output.appendLine(`similar error: ${e}`); return []; }
  }

  embed(): string {
    try { return this.exec(["embed", ...this.globalFlags(), ...this.repoFlag()]); }
    catch (e) { this.output.appendLine(`embed error: ${e}`); return "Embedding failed."; }
  }

  gitIndex(): string {
    try { return this.exec(["git", "index", `--repo-path`, this.repoPath(), ...this.globalFlags(), ...this.repoFlag()]); }
    catch (e) { this.output.appendLine(`gitIndex error: ${e}`); return "Git index failed."; }
  }

  getRepos(): RepoInfo[] {
    try {
      const db = this.dbPath();
      const r = spawnSync("python3", ["-c",
        "import sqlite3,sys\n"
        + "c=sqlite3.connect(sys.argv[1])\n"
        + "rows=c.execute('''SELECT r.name,r.path,"
        + "(SELECT COUNT(*) FROM nodes WHERE repository_id=r.id) as nodes,"
        + "(SELECT COUNT(*) FROM edges WHERE repository_id=r.id) as edges "
        + "FROM repositories r ORDER BY r.name''').fetchall()\n"
        + "c.close()\n"
        + "for n,p,nodes,edges in rows: print(f'{n}|{p}|{nodes}|{edges}')",
        db,
      ], { encoding: "utf-8", timeout: 10000 });
      if (r.status === 0) {
        return r.stdout.trim().split("\n").filter(Boolean).map(line => {
          const [name, path, nodes, edges] = line.split("|");
          return { name, path, nodes: parseInt(nodes || "0"), edges: parseInt(edges || "0") };
        });
      }
      throw new Error(r.stderr?.trim() || `exit ${r.status}`);
    } catch (e) {
      this.output.appendLine(`getRepos error: ${e}`);
      const s = this.summarize();
      return s ? [{ name: s.name, path: s.path, nodes: s.total_nodes, edges: s.total_edges }] : [];
    }
  }

  searchByType(nodeType: string, limit = 100, repoName?: string): SearchResult[] {
    return this.search("", nodeType, limit, repoName);
  }

  // ── Graph data via CLI graph-data command ────────────────────────────

  getGraphData(limit = 400, repoOverride?: string): GraphData {
    const tryRepo = (r: string | null | undefined): GraphData | null => {
      if (!r) return null;
      try {
        const out = this.exec(["graph-data", "-l", String(limit), ...this.globalFlags(), "--repo", r]);
        const d = JSON.parse(out);
        if (d.error) { this.output.appendLine(`getGraphData error: ${d.error}`); return null; }
        return d;
      } catch (e) {
        this.output.appendLine(`getGraphData failed for '${r}': ${e}`);
        return null;
      }
    };
    return (
      tryRepo(repoOverride) ||
      tryRepo(this._resolveRepoName()) ||
      tryRepo(this._firstRepoName()) ||
      { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0 }
    );
  }
}
