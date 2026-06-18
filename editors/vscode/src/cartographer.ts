import { spawn, spawnSync } from "child_process";
import * as vscode from "vscode";
import * as path from "path";
import { McpClient } from "./mcpClient";
import { ProjectConfig, resolveDbPath, readProjectConfig } from "./config";

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
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[]; node_types: Record<string, number>; total_nodes?: number; total_edges?: number; directories?: { path: string; count: number }[] }

export interface RepoInfo { name: string; path: string; nodes: number; edges: number }

function findBin(): string {
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

export class CartographerClient {
  private output: vscode.OutputChannel;
  private bin: string;
  private mcp: McpClient | null = null;
  private _projectRoot: string;

  constructor(output: vscode.OutputChannel, projectRoot: string) {
    this.output = output;
    this._projectRoot = projectRoot;
    this.bin = findBin();
  }

  get projectRoot(): string { return this._projectRoot; }

  private projectCfg(): ProjectConfig {
    return readProjectConfig(this._projectRoot);
  }

  dbPath(): string {
    const cfg = this.projectCfg();
    const vsce = vscode.workspace.getConfiguration("cartographer").get<string>("dbPath", "");
    if (vsce) return vsce;
    return resolveDbPath(this._projectRoot, cfg);
  }

  private repoName(): string {
    return path.basename(this._projectRoot);
  }

  // ── MCP lifecycle ──────────────────────────────────────────────────────

  async startMcp(): Promise<void> {
    if (this.mcp?.running) return;
    this.mcp = new McpClient(this.output);
    const dbPath = this.dbPath();
    const parts = this.bin.split(/\s+/);
    const args = [...parts.slice(1), "mcp", "start", "--db", dbPath];
    try {
      await this.mcp.start(parts[0], args);
    } catch (e) {
      this.output.appendLine(`MCP start failed, using CLI: ${e}`);
      this.mcp = null;
    }
  }

  async stopMcp(): Promise<void> {
    if (this.mcp) { await this.mcp.dispose(); this.mcp = null; }
  }

  private async mcpOrCli(tool: string, mcpArgs: Record<string, unknown>, cliFn: () => Promise<string>): Promise<string> {
    if (this.mcp?.running) {
      try { return await this.mcp.callTool(tool, mcpArgs); }
      catch (e) { this.output.appendLine(`MCP ${tool} failed, falling back: ${e}`); }
    }
    return cliFn();
  }

  private exec(args: string[]): Promise<string> {
    const parts = this.bin.split(/\s+/);
    const allArgs = [...parts.slice(1), ...args];
    this.output.appendLine(`$ ${this.bin} ${args.join(" ")}`);
    return new Promise((resolve, reject) => {
      const child = spawn(parts[0], allArgs, { timeout: 120_000 });
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (chunk: Buffer) => stdout += chunk.toString("utf-8"));
      child.stderr?.on("data", (chunk: Buffer) => stderr += chunk.toString("utf-8"));
      child.on("error", (err: Error) => { this.output.appendLine(`ERR: ${err.message}`); reject(err); });
      child.on("close", (code: number | null) => {
        this.output.appendLine(stdout.trim());
        if (code === 0) resolve(stdout);
        else {
          const msg = (stderr?.trim() || stdout?.trim() || `exit ${code}`).slice(0, 500);
          this.output.appendLine(`ERR: ${msg}`);
          reject(new Error(msg));
        }
      });
    });
  }

  // ── Tools ───────────────────────────────────────────────────────────────

  async index(p?: string): Promise<{ success: boolean; files: number; dirs: number; duration_ms: number; errors: string[] }> {
    const target = p || this._projectRoot;
    if (!target) throw new Error("No workspace folder open");
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("index", { path: target },
        () => this.exec(["index", target, "--db", db])
      );
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
    const cfg = this.projectCfg();
    limit ??= cfg.maxResults;
    const repo = repoName || this.repoName();
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("search", { query, node_type: nodeType, limit, repo },
        () => {
          const a = ["ask", query, "--limit", String(limit), "--db", db];
          if (nodeType) a.push("--type", nodeType);
          return this.exec(a);
        }
      );
      return this.parseSearchResults(out);
    } catch { return []; }
  }

  private parseSearchResults(out: string): SearchResult[] {
    const results: SearchResult[] = [];
    const root = this._projectRoot;
    let pending: SearchResult | null = null;
    for (const line of out.split("\n")) {
      const m = line.match(/^\s{2}\[(\w+)\s*\]\s(.+)$/);
      if (m) {
        if (pending) results.push(pending);
        pending = { type: m[1], name: m[2].trim(), file_path: undefined };
        continue;
      }
      if (pending && line.trim() && line.startsWith(" ")) {
        const p = line.trim();
        pending.file_path = root ? (p.startsWith("/") ? p : `${root}/${p}`) : p;
      }
    }
    if (pending) results.push(pending);
    return results;
  }

  async ask(query: string): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.mcpOrCli("ask", { query, repo: this.repoName() },
        () => this.exec(["query", query, "--db", db])
      );
    } catch { return "Query failed."; }
  }

  async summarize(repoName?: string): Promise<Summary | null> {
    try {
      const repo = repoName || this.repoName();
      const db = this.dbPath();
      const out = await this.mcpOrCli("summarize", { repo },
        () => this.exec(["summarize", "--repo", repo, "--db", db])
      );
      return this.parseSummary(out);
    } catch { return null; }
  }

  private parseSummary(out: string): Summary | null {
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
  }

  async architecture(): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.mcpOrCli("architecture", { detect: true, repo: this.repoName() },
        () => this.exec(["architecture", "--detect", "--db", db])
      );
    } catch { return "Architecture detection failed."; }
  }

  async impact(target: string): Promise<ImpactResult[]> {
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("impact", { target },
        () => this.exec(["impact", target, "--db", db])
      );
      const results: ImpactResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{4}\[(\w+)\s*\]\s(.+?)\s\((.+)\)$/);
        if (m) results.push({ type: m[1], name: m[2].trim(), file_path: m[3].trim() });
      }
      return results;
    } catch { return []; }
  }

  async neighbors(name: string, depth = 2): Promise<NeighborResult[]> {
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("neighbors", { name, depth },
        () => this.exec(["neighbors", name, "-d", String(depth), "--db", db])
      );
      const results: NeighborResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^(\s*)\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: Math.floor(m[1].length / 2) });
      }
      return results;
    } catch { return []; }
  }

  async path(from: string, to: string): Promise<PathResult[]> {
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("path", { from_name: from, to_name: to },
        () => this.exec(["path", from, to, "--db", db])
      );
      const results: PathResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}(→\s)?\[(\w+)\s*\]\s(.+)$/);
        if (m) results.push({ name: m[3].trim(), type: m[2], depth: results.length });
      }
      return results;
    } catch { return []; }
  }

  async similar(target: string): Promise<SearchResult[]> {
    const limit = this.projectCfg().maxResults;
    try {
      const db = this.dbPath();
      const out = await this.mcpOrCli("similar", { target, limit },
        () => this.exec(["similar", target, "-l", String(limit), "--db", db])
      );
      const results: SearchResult[] = [];
      for (const l of out.split("\n")) {
        const m = l.match(/^\s{2}\[(\w+)\s*\]\s(.+?)\s+\(score:\s*([\d.]+)\)/);
        if (m) results.push({ name: m[2].trim(), type: m[1], score: parseFloat(m[3]) });
      }
      return results;
    } catch { return []; }
  }

  async embed(): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.exec(["embed", "--db", db]);
    } catch { return "Embedding failed."; }
  }

  async gitIndex(): Promise<string> {
    try {
      return await this.exec(["git", "index", "--repo-path", this._projectRoot, "--db", this.dbPath()]);
    } catch { return "Git index failed."; }
  }

  async getRepos(): Promise<RepoInfo[]> {
    const db = this.dbPath();
    try {
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

  async getGraphData(
    limit = 400,
    repoOverride?: string,
    offset = 0,
    dir?: string,
    expandNodeId?: number,
  ): Promise<GraphData> {
    const repo = repoOverride || this.repoName();
    try {
      const db = this.dbPath();
      const mcpArgs: Record<string, unknown> = { repo, limit };
      const cliArgs = ["graph-data", "-l", String(limit), "--db", db, "--repo", repo];
      if (offset > 0) { mcpArgs.offset = offset; cliArgs.push("--offset", String(offset)); }
      if (dir) { mcpArgs.dir = dir; cliArgs.push("--dir", dir); }
      if (expandNodeId !== undefined) { mcpArgs.expand_node_id = expandNodeId; cliArgs.push("--expand-node-id", String(expandNodeId)); }
      const out = await this.mcpOrCli("graph_data", mcpArgs, () => this.exec(cliArgs));
      const d = JSON.parse(out);
      if (d.error) { this.output.appendLine(`getGraphData error: ${d.error}`); return { nodes: [], edges: [], node_types: {}, directories: [] }; }
      return d;
    } catch (e) {
      this.output.appendLine(`getGraphData failed: ${e}`);
      return { nodes: [], edges: [], node_types: {}, directories: [] };
    }
  }

  async updateFile(filePath: string): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.mcpOrCli("update_index", { file_path: filePath },
        () => this.exec(["update-index", filePath, "--db", db])
      );
    } catch { return '{"error":"update_file_failed"}'; }
  }

  async deleteFile(filePath: string): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.mcpOrCli("delete_file", { file_path: filePath },
        () => this.exec(["delete-file", filePath, "--db", db])
      );
    } catch { return '{"error":"delete_file_failed"}'; }
  }

  async invokeWatch(root?: string): Promise<string> {
    const target = root || this._projectRoot;
    try {
      return await this.exec(["watch", target, "--db", this.dbPath()]);
    } catch (e) {
      return `Watch failed: ${e}`;
    }
  }

  async getContext(topN = 10, maxTokens = 1500): Promise<string> {
    try {
      const db = this.dbPath();
      return await this.exec(["context", "--top-n", String(topN), "--max-tokens", String(maxTokens), "--db", db]);
    } catch { return "Context generation failed."; }
  }

  async dbInfo(): Promise<string> {
    const db = this.dbPath();
    try {
      const r = spawnSync("python3", ["-c",
        "import sqlite3,sys,os\n"
        + "p=sys.argv[1]\n"
        + "s=os.path.getsize(p) if os.path.exists(p) else 0\n"
        + "c=sqlite3.connect(p)\n"
        + "r=c.execute('SELECT COUNT(*) FROM repositories').fetchone()[0]\n"
        + "n=c.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]\n"
        + "e=c.execute('SELECT COUNT(*) FROM edges').fetchone()[0]\n"
        + "em=c.execute('SELECT COUNT(*) FROM embeddings').fetchone()[0]\n"
        + "cm=c.execute('SELECT COUNT(*) FROM commits').fetchone()[0]\n"
        + "c.close()\n"
        + "print(f'{r}|{n}|{e}|{em}|{cm}|{s}')",
        db,
      ], { encoding: "utf-8", timeout: 10000 });
      if (r.status === 0) {
        const [repos, nodes, edges, embs, commits, size] = r.stdout.trim().split("|");
        const sz = this.fmtSize(parseInt(size || "0"));
        return `Database: ${db}\nSize: ${sz}\nRepositories: ${repos || "0"}\nNodes: ${nodes || "0"}\nEdges: ${edges || "0"}\nEmbeddings: ${embs || "0"}\nCommits: ${commits || "0"}`;
      }
      return `DB info failed: ${r.stderr?.trim() || `exit ${r.status}`}`;
    } catch (e) { return `DB info error: ${e}`; }
  }

  private fmtSize(bytes: number): string {
    for (const u of ["B", "KB", "MB", "GB"]) { if (bytes < 1024) return `${bytes.toFixed(1)}${u}`; bytes /= 1024; }
    return `${bytes.toFixed(1)}TB`;
  }

  cfg<T>(key: string, def: T): T {
    return vscode.workspace.getConfiguration("cartographer").get<T>(key, def);
  }
}
