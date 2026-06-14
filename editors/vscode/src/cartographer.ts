import { execSync, ExecSyncOptions } from "child_process";
import * as vscode from "vscode";

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
  top_files?: { name: string; entities: number }[];
  top_classes?: { name: string; methods: number }[];
}

export interface ArchitectureResult {
  repository: string;
  layers?: { name: string; description: string }[];
  patterns?: { name: string; confidence: number }[];
  domains?: { name: string; confidence: number; file_count: number }[];
  frameworks?: { name: string; confidence: number }[];
}

export interface NeighborNode {
  name: string;
  type: string;
  depth: number;
  file_path?: string;
}

export interface ImpactResult {
  name: string;
  type: string;
  file_path?: string;
  via_edge?: string;
}

export interface IndexResult {
  success: boolean;
  files: number;
  dirs: number;
  duration_ms: number;
  errors: string[];
}

export interface RepoInfo {
  name: string;
  path: string;
  nodes: number;
  edges: number;
}

export interface NodeInfo {
  id: number;
  name: string;
  node_type: string;
  file_path?: string;
  repo?: string;
  metadata?: Record<string, unknown>;
}

export class CartographerClient {
  private outputChannel: vscode.OutputChannel;
  private binPath: string;

  constructor(outputChannel: vscode.OutputChannel) {
    this.outputChannel = outputChannel;
    this.binPath = this.resolveBin();
  }

  private resolveBin(): string {
    try {
      const result = execSync("which cartographer 2>/dev/null || echo ''",
        { encoding: "utf-8" });
      const which = result.trim();
      if (which) return which;
    } catch {
      // fall through
    }
    return "cartographer";
  }

  private run(args: string[], cwd?: string): string {
    const opts: ExecSyncOptions = {
      encoding: "utf-8",
      timeout: 120_000,
    };
    if (cwd) opts.cwd = cwd;
    try {
      const output = execSync(`${this.binPath} ${args.join(" ")}`, opts);
      this.outputChannel.appendLine(`$ ${this.binPath} ${args.join(" ")}`);
      const result = typeof output === "string" ? output : output.toString();
      this.outputChannel.appendLine(result);
      return result;
    } catch (e: unknown) {
      const err = e as { stderr?: Buffer; stdout?: Buffer; message?: string };
      const msg = err.stderr?.toString() || err.stdout?.toString() || err.message || "Unknown error";
      this.outputChannel.appendLine(`Error: ${msg}`);
      throw new Error(msg);
    }
  }

  private repoFlag(): string {
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return "";
    return ` --repo "${ws.name}"`;
  }

  index(path?: string): IndexResult {
    const target = path || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!target) throw new Error("No workspace folder open");
    const output = this.run(["index", `"${target}"`]);
    const files = parseInt(output.match(/Indexed (\d+) files/)?.[1] || "0");
    const dirs = parseInt(output.match(/in (\d+) directories/)?.[1] || "0");
    const duration = parseFloat(output.match(/Duration: ([\d.]+)ms/)?.[1] || "0");
    const hasErrors = output.includes("Warning:") || output.includes("Error:");
    const errors = hasErrors
      ? output.split("\n").filter(l => l.startsWith("Warning:") || l.startsWith("Error:"))
      : [];
    return { success: !hasErrors, files, dirs, duration_ms: duration, errors };
  }

  search(query: string, limit: number = 20): SearchResult[] {
    const output = this.run(["ask", query, `--limit ${limit}`, this.repoFlag()].filter(Boolean));
    const results: SearchResult[] = [];
    const lines = output.split("\n");
    for (const line of lines) {
      const m = line.match(/^\s{2}\[(\w+)\]\s(.+?)(?:\s{2,}(.+))?$/);
      if (m) {
        results.push({ type: m[1], name: m[2], file_path: m[3]?.trim() });
      }
    }
    return results;
  }

  summarize(): Summary | null {
    try {
      const output = this.run(["summarize", this.repoFlag()].filter(Boolean));
      const lines = output.split("\n");
      const summary: Summary = {
        name: lines[0]?.replace("Repository: ", "").trim() || "",
        path: lines[1]?.replace("Path: ", "").trim() || "",
        total_nodes: parseInt(lines[2]?.replace("Total nodes: ", "").trim() || "0"),
        total_edges: parseInt(lines[3]?.replace("Total edges: ", "").trim() || "0"),
        node_breakdown: {},
        edge_breakdown: {},
      };
      let section: "nodes" | "edges" | "files" | "classes" | null = null;
      for (const line of lines) {
        if (line.startsWith("Node breakdown:")) section = "nodes";
        else if (line.startsWith("Edge breakdown:")) section = "edges";
        else if (line.startsWith("Top files")) section = "files";
        else if (line.startsWith("Largest classes")) section = "classes";
        else if (section === "nodes" && line.trim().startsWith("- ")) {
          const [key, val] = line.trim().replace(/^- /, "").split(": ");
          if (key && val) summary.node_breakdown[key.trim()] = parseInt(val.trim());
        } else if (section === "edges" && line.trim().startsWith("- ")) {
          const [key, val] = line.trim().replace(/^- /, "").split(": ");
          if (key && val) summary.edge_breakdown[key.trim()] = parseInt(val.trim());
        }
      }
      return summary;
    } catch {
      return null;
    }
  }

  architecture(detect: boolean = false): ArchitectureResult | null {
    try {
      const flag = detect ? " --detect" : "";
      const output = this.run(["architecture", flag, this.repoFlag()].filter(Boolean));
      const result: ArchitectureResult = { repository: "" };
      const lines = output.split("\n");
      for (const line of lines) {
        if (line.startsWith("Architecture for ")) {
          result.repository = line.replace("Architecture for ", "").trim();
        }
      }
      return result;
    } catch {
      return null;
    }
  }

  impact(target: string): ImpactResult[] {
    try {
      const output = this.run(["impact", `"${target}"`, this.repoFlag()].filter(Boolean));
      const results: ImpactResult[] = [];
      const lines = output.split("\n");
      for (const line of lines) {
        const m = line.match(/^\s{4}\[(\w+)\]\s(.+?)\s\((.+)\)$/);
        if (m) {
          results.push({ type: m[1], name: m[2], file_path: m[3] });
        }
      }
      return results;
    } catch {
      return [];
    }
  }

  getRepos(): RepoInfo[] {
    try {
      const run = this.run(["summarize", "--repo ''"]);
      const lines = run.split("\n");
      if (lines.length > 0 && lines[0].startsWith("Repository:")) {
        return [{
          name: lines[0].replace("Repository: ", "").trim(),
          path: lines[1].replace("Path: ", "").trim(),
          nodes: parseInt(lines[2]?.replace("Total nodes: ", "").trim() || "0"),
          edges: parseInt(lines[3]?.replace("Total edges: ", "").trim() || "0"),
        }];
      }
      return [];
    } catch {
      return [];
    }
  }
}
