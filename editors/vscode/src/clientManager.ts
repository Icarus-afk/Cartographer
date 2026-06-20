import * as vscode from "vscode";
import { CartographerClient } from "./cartographer";
import { readProjectConfig, watchConfig } from "./config";

export class ClientManager {
  private clients = new Map<string, CartographerClient>();
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChange = this._onDidChange.event;

  constructor(
    private output: vscode.OutputChannel,
  ) {}

  // ── Accessors ───────────────────────────────────────────────────────────

  get(folderPath: string): CartographerClient {
    let c = this.clients.get(folderPath);
    if (!c) {
      c = new CartographerClient(this.output, folderPath);
      this.clients.set(folderPath, c);
    }
    return c;
  }

  /** Find the workspace folder containing this URI and return its client. */
  forUri(uri: vscode.Uri): CartographerClient | null {
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    if (!folder) return null;
    return this.get(folder.uri.fsPath);
  }

  /** Return the client for the active text editor's folder, or the first folder. */
  active(): CartographerClient | null {
    const ed = vscode.window.activeTextEditor;
    if (ed) {
      const c = this.forUri(ed.document.uri);
      if (c) return c;
    }
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) return null;
    return this.get(folders[0].uri.fsPath);
  }

  all(): CartographerClient[] {
    return Array.from(this.clients.values());
  }

  allFolders(): { folder: string; client: CartographerClient }[] {
    return Array.from(this.clients.entries()).map(([folder, client]) => ({ folder, client }));
  }

  /** Ensure a client exists for each workspace folder that's open. */
  ensureFolders(folders: readonly vscode.WorkspaceFolder[]): void {
    const needed = new Set(folders.map(f => f.uri.fsPath));
    // Add new folders
    for (const f of folders) {
      this.get(f.uri.fsPath);
    }
    // Remove stale folders
    for (const [path] of this.clients) {
      if (!needed.has(path)) {
        this.clients.get(path)?.stopMcp();
        this.clients.delete(path);
      }
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────

  async startAll(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders || [];
    for (const f of folders) {
      const client = this.get(f.uri.fsPath);
      try {
        await client.startMcp();
      } catch {
        this.output.appendLine(`MCP start failed for ${f.name}`);
      }
    }
  }

  async dispose(): Promise<void> {
    for (const c of this.clients.values()) {
      await c.stopMcp();
    }
    this.clients.clear();
  }

  refreshAll(): void {
    this._onDidChange.fire();
  }

  /** Return the active client's summarize result */
  async activeSummary() {
    const c = this.active();
    if (!c) return null;
    try { return await c.summarize(); } catch { return null; }
  }

  /** Aggregate all folder summaries (parallel) */
  async allSummaries(): Promise<{ folder: string; name: string; nodes: number; edges: number }[]> {
    const folders = this.allFolders();
    const results = await Promise.allSettled(
      folders.map(async ({ folder, client }) => {
        const s = await client.summarize();
        if (s) return { folder, name: s.name, nodes: s.total_nodes, edges: s.total_edges };
        return null;
      })
    );
    return results.filter((r): r is PromiseFulfilledResult<{ folder: string; name: string; nodes: number; edges: number }> =>
      r.status === 'fulfilled' && r.value !== null
    ).map(r => r.value);
  }
}
