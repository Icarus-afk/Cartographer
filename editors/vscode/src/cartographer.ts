import { spawn, spawnSync } from "child_process";
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

  cfg<T>(key: string, def: T): T {
    return vscode.workspace.getConfiguration("cartographer").get<T>(key, def);
  }

  private globalFlags(): string[] {
    const f: string[] = [];
    const db = this.cfg("dbPath", "");
    if (db) f.push("--db", db);
    return f;
  }

  private repoFlagSync(): string[] {
    const name = this.resolveRepoSync();
    return name ? ["--repo", name] : [];
  }

  resolveRepoSync(): string | null {
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
      this.output.appendLine("resolveRepoSync: failed");
      return null;
    }
  }

  private async execAsync(args: string[]): Promise<string> {
    const binParts = this.bin.split(/\s+/);
    const allArgs = [...binParts, ...args];
    this.output.appendLine(`$ ${this.bin} ${args.join(" ")}`);
    return new Promise<string>((resolve, reject) => {
      const child = spawn(allArgs[0], allArgs.slice(1), { timeout: 120_000 });
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (chunk: Buffer) => stdout += chunk.toString("utf-8"));
      child.stderr?.on("data", (chunk: Buffer) => stderr += chunk.toString("utf-8"));
      child.on("error", (err: Error) => {
        this.output.appendLine(`ERR: ${err.message}`);
        reject(err);
      });
      child.on("close", (code: number | null) => {
        this.output.appendLine(stdout);
        if (code === 0) {
          resolve(stdout);
        } else {
          const msg = (stderr?.trim() || stdout?.trim() || `exit code ${code}`).slice(0, 500);
          this.output.appendLine(`ERR: ${msg}`);
          reject(new Error(msg));
        }
      });
    });
  }

  async resolveRepoName(): Promise<string | null> {
    return this.resolveRepoSync();
  }

  private wsName(): string {
    return vscode.workspace.workspaceFolders?.[0]?.name || "";
  }

  repoPath(): string {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "";
  }

  // ── CLI commands (async) ────────────────────────────────────────────────

  async index(p?: string): Promise<{ success: boolean; files: number; dirs: number; duration_ms: number; errors: string[] }> {
    const target = p || this.repoPath();
    if (!target) throw new Error("No workspace folder open");
    try {
      const out = await this.execAsync(["index", target, ...this.globalFlags()]);
      this._repoName = null; // reset cached repo name after index
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

  async search(query: string, nodeType?: string, limit?: number, repoName?: string): Promise<SearchResult[]> {
    limit ??= this.cfg<number>("maxResults", 40);
    const args = ["ask", query, "-l", String(limit)];
    if (nodeType) args.push("-t", nodeType);
    try {
      const rf = repoName ? ["--repo", repoName] : this.repoFlagSync();
      const out = await this.execAsync([...args, ...this.globalFlags(), ...rf]);
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

  async ask(query: string): Promise<string> {
    try { return await this.execAsync(["query", query, ...this.globalFlags(), ...this.repoFlagSync()]); }
    catch (e) { this.output.appendLine(`ask error: ${e}`); return "Query failed."; }
  }

  async summarize(repoName?: string): Promise<Summary | null> {
    try {
      const rf = repoName ? ["--repo", repoName] : this.repoFlagSync();
      const out = await this.execAsync(["summarize", ...this.globalFlags(), ...rf]);
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

  async architecture(): Promise<string> {
    try { return await this.execAsync(["architecture", "--detect", ...this.globalFlags(), ...this.repoFlagSync()]); }
    catch (e) { this.output.appendLine(`architecture error: ${e}`); return "Architecture detection failed."; }
  }

  async impact(target: string): Promise<ImpactResult[]> {
    try {
      const out = await this.execAsync(["impact", target, ...this.globalFlags(), ...this.repoFlagSync()]);
      const results: ImpactResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{4}\[(\w+)\s*\]\s(.+?)\s\((.+)\)$/);
        if (m) results.push({ type: m[1], name: m[2].trim(), file_path: m[3].trim() });
      }
      return results;
    } catch (e) { this.output.appendLine(`impact error: ${e}`); return []; }
  }

  async neighbors(name: string, depth = 2): Promise<NeighborResult[]> {
    try {
      const out = await this.execAsync(["neighbors", name, "-d", String(depth), ...this.globalFlags(), ...this.repoFlagSync()]);
      const results: NeighborResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^(\s*)\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: Math.floor(m[1].length / 2) });
      }
      return results;
    } catch (e) { this.output.appendLine(`neighbors error: ${e}`); return []; }
  }

  async path(from: string, to: string): Promise<PathResult[]> {
    try {
      const out = await this.execAsync(["path", from, to, ...this.globalFlags()]);
      const results: PathResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}(→\s)?\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: results.length });
      }
      return results;
    } catch (e) { this.output.appendLine(`path error: ${e}`); return []; }
  }

  async similar(target: string): Promise<SearchResult[]> {
    const limit = this.cfg<number>("maxResults", 20);
    try {
      const out = await this.execAsync(["similar", target, "-l", String(limit), ...this.globalFlags(), ...this.repoFlagSync()]);
      const results: SearchResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}\[(\w+)\s*\]\s(.+?)\s+\(score:\s*([\d.]+)\)/);
        if (m) results.push({ name: m[2].trim(), type: m[1], score: parseFloat(m[3]) });
      }
      return results;
    } catch (e) { this.output.appendLine(`similar error: ${e}`); return []; }
  }

  async embed(): Promise<string> {
    try { return await this.execAsync(["embed", ...this.globalFlags(), ...this.repoFlagSync()]); }
    catch (e) { this.output.appendLine(`embed error: ${e}`); return "Embedding failed."; }
  }

  async gitIndex(): Promise<string> {
    try { return await this.execAsync(["git", "index", "--repo-path", this.repoPath(), ...this.globalFlags(), ...this.repoFlagSync()]); }
    catch (e) { this.output.appendLine(`gitIndex error: ${e}`); return "Git index failed."; }
  }

  async getRepos(): Promise<RepoInfo[]> {
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
      const s = await this.summarize();
      return s ? [{ name: s.name, path: s.path, nodes: s.total_nodes, edges: s.total_edges }] : [];
    }
  }

  async searchByType(nodeType: string, limit = 100, repoName?: string): Promise<SearchResult[]> {
    return this.search("", nodeType, limit, repoName);
  }

  // ── Graph data via CLI graph-data command ────────────────────────────

  async getGraphData(limit = 400, repoOverride?: string): Promise<GraphData> {
    const tryRepo = async (r: string | null | undefined): Promise<GraphData | null> => {
      if (!r) return null;
      try {
        const out = await this.execAsync(["graph-data", "-l", String(limit), ...this.globalFlags(), "--repo", r]);
        const d = JSON.parse(out);
        if (d.error) { this.output.appendLine(`getGraphData error: ${d.error}`); return null; }
        return d;
      } catch (e) {
        this.output.appendLine(`getGraphData failed for '${r}': ${e}`);
        return null;
      }
    };
    const repoName = await this.resolveRepoName();
    return (
      (await tryRepo(repoOverride)) ||
      (await tryRepo(repoName)) ||
      { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0 }
    );
  }
}
