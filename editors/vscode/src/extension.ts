import * as vscode from "vscode";
import { CartographerClient, SearchResult } from "./cartographer";
import { ClientManager } from "./clientManager";
import { RepoTreeProvider, EntityTreeProvider, SearchTreeProvider, SearchItem } from "./treeViews";
import { createGraphWebview } from "./graphWebview";
import { readProjectConfig, watchConfig, resolveDbPath } from "./config";

let clients: ClientManager;
let repoTree: RepoTreeProvider;
let entityTree: EntityTreeProvider;
let searchTree: SearchTreeProvider;
let statusBar: vscode.StatusBarItem;

export function activate(_ctx: vscode.ExtensionContext): void {
  ctx = _ctx;
  const ch = vscode.window.createOutputChannel("Cartographer");
  clients = new ClientManager(ch);
  ctx.subscriptions.push(ch);

  // Initialize clients for all workspace folders
  const folders = vscode.workspace.workspaceFolders || [];
  clients.ensureFolders(folders);
  if (folders.length > 0) {
    clients.startAll().then(() => {
      ch.appendLine(`MCP connected for ${folders.length} folder(s)`);
    });
  }

  // Watch .cartographer/config.json per folder
  for (const f of folders) {
    ctx.subscriptions.push(watchConfig(f.uri.fsPath, () => {
      repoTree.refresh();
      updateStatusBar();
    }));
  }

  // Tree views
  repoTree = new RepoTreeProvider(clients);
  entityTree = new EntityTreeProvider(clients);
  searchTree = new SearchTreeProvider();
  ctx.subscriptions.push(
    vscode.window.registerTreeDataProvider("cartographer.repos", repoTree),
    vscode.window.registerTreeDataProvider("cartographer.entities", entityTree),
    vscode.window.registerTreeDataProvider("cartographer.search", searchTree),
  );

  // Status bar
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  statusBar.command = "cartographer.summarize";
  statusBar.text = "$(graph) Cartographer";
  statusBar.tooltip = "Click for repository summary";
  statusBar.show();
  ctx.subscriptions.push(statusBar);

  // Handle folder changes
  ctx.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders((e) => {
    for (const f of e.removed) {
      const c = clients.get(f.uri.fsPath);
      c.stopMcp();
    }
    clients.ensureFolders(vscode.workspace.workspaceFolders || []);
    for (const f of e.added) {
      const c = clients.get(f.uri.fsPath);
      c.startMcp().catch(() => ch.appendLine(`MCP start failed for ${f.name}`));
      ctx.subscriptions.push(watchConfig(f.uri.fsPath, () => {
        repoTree.refresh();
        updateStatusBar();
      }));
    }
    repoTree.refresh();
    entityTree.refresh();
    updateStatusBar();
  }));

  // Register all commands
  const cmds: [string, (...args: any[]) => any][] = [
    ["cartographer.index", cmdIndex],
    ["cartographer.search", cmdSearch],
    ["cartographer.ask", cmdAsk],
    ["cartographer.summarize", cmdSummarize],
    ["cartographer.architecture", cmdArchitecture],
    ["cartographer.impact", cmdImpact],
    ["cartographer.neighbors", cmdNeighbors],
    ["cartographer.path", cmdPath],
    ["cartographer.similar", cmdSimilar],
    ["cartographer.embed", cmdEmbed],
    ["cartographer.gitIndex", cmdGitIndex],
    ["cartographer.graph", cmdGraph],
    ["cartographer.graphEntityType", (t: string) => cmdGraph(t, entityTree.currentRepo())],
    ["cartographer.openDb", cmdOpenDb],
    ["cartographer.refresh", cmdRefresh],
    ["cartographer.searchType", cmdSearchByType],
    ["cartographer.watch", cmdWatch],
    ["cartographer.context", cmdContext],
    ["cartographer.dbInfo", cmdDbInfo],
  ];

  for (const [id, fn] of cmds) {
    ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));
  }

  // Hover provider: debounced + cached, uses active client
  let hoverTimer: NodeJS.Timeout | undefined;
  const hoverCache = new Map<string, { results: SearchResult[]; time: number }>();
  ctx.subscriptions.push(
    vscode.languages.registerHoverProvider("*", {
      provideHover(document, position) {
        const c = clients.forUri(document.uri);
        if (!c) return null;
        const range = document.getWordRangeAtPosition(position);
        if (!range) return null;
        const word = document.getText(range);
        if (!word || word.length < 2) return null;
        const cached = hoverCache.get(word);
        if (cached && Date.now() - cached.time < 60000) {
          if (cached.results.length > 0) return formatHover(cached.results);
          return null;
        }
        return new Promise<vscode.Hover | null | undefined>(resolve => {
          if (hoverTimer) clearTimeout(hoverTimer);
          hoverTimer = setTimeout(async () => {
            try {
              const results = await c.search(word);
              hoverCache.set(word, { results, time: Date.now() });
              resolve(results.length > 0 ? formatHover(results) : null);
            } catch { resolve(null); }
          }, 300);
        });
      },
    }),
  );

  // Trim cache every 5 min
  const trimInterval = setInterval(() => {
    const cutoff = Date.now() - 120000;
    for (const [k, v] of hoverCache) { if (v.time < cutoff) hoverCache.delete(k); }
  }, 300000);
  ctx.subscriptions.push({ dispose: () => clearInterval(trimInterval) });

  // Selection-based search context menu
  ctx.subscriptions.push(
    vscode.commands.registerCommand("cartographer.searchSelection", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.selection.isEmpty) return;
      const word = editor.document.getText(editor.selection);
      if (word) cmdSearchWith(word);
    }),
  );

  // Auto-index each unindexed folder on activation
  (async () => {
    if (folders.length === 0) { updateStatusBar(); return; }
    const indexed: string[] = [];
    for (const f of folders) {
      const c = clients.get(f.uri.fsPath);
      const cfg = readProjectConfig(f.uri.fsPath);
      if (cfg.autoReindex === false) continue;
      try {
        const s = await c.summarize();
        if (s) { indexed.push(f.name); continue; }
      } catch { /* not indexed */ }
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `Cartographer: Indexing ${f.name}...` },
        async () => { await c.index(); },
      );
      repoTree.refresh();
      entityTree.refresh();
      updateStatusBar();
    }
    if (indexed.length > 0) {
      ch.appendLine(`Already indexed: ${indexed.join(", ")}`);
    }
  })();

  // File watchers: per-folder incremental re-index via MCP
  let reindexTimer: NodeJS.Timeout | undefined;
  const pendingChanges = new Map<string, string>(); // filePath -> "+"/"-"
  function scheduleReindex() {
    if (reindexTimer) clearTimeout(reindexTimer);
    reindexTimer = setTimeout(flushReindex, 2000);
  }
  async function flushReindex() {
    if (pendingChanges.size === 0) return;
    const entries = Array.from(pendingChanges.entries());
    pendingChanges.clear();
    statusBar.text = "$(sync~spin) Cartographer";
    for (const [filePath, op] of entries) {
      const c = clients.forUri(vscode.Uri.file(filePath));
      if (!c) continue;
      try {
        if (op === "+") await c.updateFile(filePath);
        else await c.deleteFile(filePath);
      } catch { /* ignore single file errors */ }
    }
    repoTree.refresh();
    entityTree.refresh();
    updateStatusBar();
  }
  function isIgnored(filePath: string, root: string): boolean {
    const rel = filePath.startsWith(root) ? filePath.slice(root.length) : filePath;
    const ignored = ["node_modules", ".git", ".cartographer", "__pycache__", "venv", ".venv", "dist", "build", ".next", "target"];
    for (const dir of ignored) {
      if (rel.startsWith(`/${dir}`) || rel.startsWith(`${dir}`)) return true;
    }
    return false;
  }
  ctx.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (doc.uri.scheme !== "file") return;
      if (isIgnored(doc.fileName, "")) return;
      const c = clients.forUri(doc.uri);
      if (!c) return;
      const cfg = readProjectConfig(c.projectRoot);
      if (cfg.autoReindex === false) return;
      if (isIgnored(doc.fileName, c.projectRoot)) return;
      pendingChanges.set(doc.fileName, "+");
      scheduleReindex();
    }),
    vscode.workspace.onDidDeleteFiles(async (event) => {
      for (const uri of event.files) {
        const c = clients.forUri(uri);
        if (!c) continue;
        const cfg = readProjectConfig(c.projectRoot);
        if (cfg.autoReindex === false) continue;
        if (isIgnored(uri.fsPath, c.projectRoot)) continue;
        pendingChanges.set(uri.fsPath, "-");
      }
      if (event.files.length > 0) scheduleReindex();
    }),
    vscode.workspace.onDidRenameFiles(async (event) => {
      for (const file of event.files) {
        const c = clients.forUri(file.oldUri);
        if (!c) continue;
        const cfg = readProjectConfig(c.projectRoot);
        if (cfg.autoReindex === false) continue;
        if (isIgnored(file.oldUri.fsPath, c.projectRoot)) continue;
        pendingChanges.set(file.oldUri.fsPath, "-");
        pendingChanges.set(file.newUri.fsPath, "+");
      }
      if (event.files.length > 0) scheduleReindex();
    }),
  );
}

// ── Status bar ──────────────────────────────────────────────────────────

async function updateStatusBar(): Promise<void> {
  try {
    const active = clients.active();
    if (active) {
      const s = await active.summarize();
      if (s) {
        const ws = vscode.workspace.workspaceFolders
          ?.find(f => active.projectRoot.startsWith(f.uri.fsPath))?.name || s.name;
        statusBar.text = `$(graph) ${ws}  ${s.total_nodes}N/${s.total_edges}E`;
        statusBar.tooltip = `${s.name}: ${s.total_nodes} nodes, ${s.total_edges} edges`;
        return;
      }
    }
    // Fallback: aggregate all folders
    const all = await clients.allSummaries();
    if (all.length > 0) {
      const totalNodes = all.reduce((a, b) => a + b.nodes, 0);
      const totalEdges = all.reduce((a, b) => a + b.edges, 0);
      const names = all.length === 1 ? all[0].name : `${all.length} repos`;
      statusBar.text = `$(graph) ${names}  ${totalNodes}N/${totalEdges}E`;
      statusBar.tooltip = all.map(s => `${s.folder}: ${s.nodes}N/${s.edges}E`).join("\n");
    } else {
      statusBar.text = "$(graph) Cartographer";
      statusBar.tooltip = "No repo indexed";
    }
  } catch { statusBar.text = "$(graph) Cartographer"; }
}

// ── Helpers ──────────────────────────────────────────────────────────────

function withProgress<T>(title: string, fn: () => Promise<T>): Thenable<T> {
  return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title }, () => fn());
}

function formatHover(results: SearchResult[]): vscode.Hover {
  const lines = results.slice(0, 5).map(r =>
    `[${r.type}] **${r.name}**${r.file_path ? ` — ${r.file_path}` : ""}`
  );
  return new vscode.Hover(new vscode.MarkdownString(
    "**Cartographer**\n\n" + lines.join("\n") + "\n\n---\n_Click search for more_"
  ));
}

function showOutput(title: string, text: string): void {
  const ch = vscode.window.createOutputChannel(title);
  ch.clear();
  ch.appendLine(text);
  ch.show();
}

function showError(msg: string): void {
  vscode.window.showErrorMessage(`Cartographer: ${msg}`);
}

function pickFolder(): CartographerClient | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    showError("No workspace folder open");
    return;
  }
  if (folders.length === 1) return clients.get(folders[0].uri.fsPath);
  // Ask user to pick
  const active = clients.active();
  if (active) return active;
  return clients.get(folders[0].uri.fsPath);
}

// ── Command implementations ───────────────────────────────────────────────

async function cmdIndex(): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return void showError("No workspace folder open");
  for (const f of folders) {
    await withProgress(`Cartographer: Indexing ${f.name}...`, async () => {
      const c = clients.get(f.uri.fsPath);
      const r = await c.index();
      if (r.success) {
        vscode.window.showInformationMessage(`${f.name}: Indexed ${r.files} files in ${r.duration_ms}ms`);
      } else {
        const msg = r.errors[0]?.replace(/^Error:\s*/, "") || "Index command failed";
        vscode.window.showErrorMessage(`${f.name}: ${msg}`);
        const ch = vscode.window.createOutputChannel(`Cartographer Index ${f.name}`);
        ch.clear();
        ch.appendLine(r.errors.join("\n"));
        ch.show();
      }
    });
  }
  repoTree.refresh();
  entityTree.refresh();
  updateStatusBar();
}

async function cmdSearchByType(entityType: string): Promise<void> {
  if (!entityType) return;
  const c = pickFolder();
  if (!c) return;
  withProgress(`Cartographer: Loading ${entityType}s...`, async () => {
    const results = await c.searchByType(entityType, 100, entityTree.currentRepo());
    searchTree.setResults(results);
    vscode.commands.executeCommand("workbench.view.extension.cartographer");
    if (results.length > 0) {
      vscode.window.showInformationMessage(`Found ${results.length} ${entityType}s`);
    } else {
      vscode.window.showWarningMessage(`Found 0 ${entityType}s. Check the Cartographer output channel for details.`);
    }
  });
}

function cmdSearchWith(query?: string): void { cmdSearch(query); }

async function cmdSearch(initial?: string): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const q = await vscode.window.showInputBox({
    prompt: "Search the knowledge graph",
    placeHolder: "class name, function, file...",
    value: initial || "",
  });
  if (!q) return;
  const results = await c.search(q);
  searchTree.setResults(results);
  vscode.commands.executeCommand("workbench.view.extension.cartographer");
  vscode.window.showInformationMessage(`Found ${results.length} results for "${q}"`);
}

async function cmdAsk(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const q = await vscode.window.showInputBox({
    prompt: "Ask a natural language question about the codebase",
    placeHolder: "e.g. What does the auth module do? Explain checkout flow...",
  });
  if (!q) return;
  withProgress("Cartographer: Querying...", async () => {
    const answer = await c.ask(q);
    showOutput("Cartographer Answer", answer);
  });
}

async function cmdSummarize(repoName?: string): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const s = await c.summarize(repoName);
  if (!s) return void showError("No repository indexed");
  entityTree.setRepo(repoName);
  const lines = [
    `Repository: ${s.name}`,
    `Path: ${s.path}`,
    `Total nodes: ${s.total_nodes}`,
    `Total edges: ${s.total_edges}`,
    "",
    "Node breakdown:",
    ...Object.entries(s.node_breakdown).map(([k, v]) => `  ${k}: ${v}`),
    "",
    "Edge breakdown:",
    ...Object.entries(s.edge_breakdown).map(([k, v]) => `  ${k}: ${v}`),
  ];
  showOutput("Cartographer Summary", lines.join("\n"));
}

async function cmdArchitecture(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  withProgress("Cartographer: Detecting architecture...", async () => {
    const result = await c.architecture();
    showOutput("Cartographer Architecture", result);
  });
}

async function cmdImpact(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const q = await vscode.window.showInputBox({
    prompt: "Find what depends on this symbol",
    placeHolder: "e.g. User, auth_service, database...",
  });
  if (!q) return;
  const results = await c.impact(q);
  if (results.length === 0) return void vscode.window.showInformationMessage(`No dependents found for "${q}"`);
  const lines = [`Impact analysis for "${q}"`, `Found ${results.length} dependents:`, ""];
  for (const r of results) {
    lines.push(`  [${r.type}] ${r.name}`);
    if (r.file_path) lines.push(`    ${r.file_path}`);
  }
  showOutput("Cartographer Impact", lines.join("\n"));
}

async function cmdNeighbors(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const q = await vscode.window.showInputBox({
    prompt: "Show neighbors of a node",
    placeHolder: "Node name or class...",
  });
  if (!q) return;
  const depth = await vscode.window.showInputBox({ prompt: "Traversal depth", value: "2" }) || "2";
  const results = await c.neighbors(q, parseInt(depth) || 2);
  if (results.length === 0) return void vscode.window.showInformationMessage(`No neighbors found for "${q}"`);
  const lines = [`Neighbors of "${q}":`, ""];
  for (const r of results) {
    if (r.depth === 0) continue;
    lines.push(`${"  ".repeat(r.depth)}[${r.type}] ${r.name}`);
  }
  showOutput("Cartographer Neighbors", lines.join("\n"));
}

async function cmdPath(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const from = await vscode.window.showInputBox({ prompt: "Start node", placeHolder: "e.g. UserController" });
  if (!from) return;
  const to = await vscode.window.showInputBox({ prompt: "End node", placeHolder: "e.g. Database" });
  if (!to) return;
  const results = await c.path(from, to);
  if (results.length === 0) return void vscode.window.showInformationMessage("No path found");
  const lines = [`Path from "${from}" to "${to}":`];
  for (const r of results) {
    const arrow = r.depth > 0 ? "  → " : "     ";
    lines.push(`${arrow}[${r.type}] ${r.name}`);
  }
  showOutput("Cartographer Path", lines.join("\n"));
}

async function cmdSimilar(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const q = await vscode.window.showInputBox({
    prompt: "Find semantically similar nodes",
    placeHolder: "Target node name...",
  });
  if (!q) return;
  withProgress("Cartographer: Searching similar...", async () => {
    const results = await c.similar(q);
    if (results.length === 0) return void vscode.window.showInformationMessage("No similar nodes found");
    const lines = [`Similar to "${q}":`];
    for (const r of results) {
      lines.push(`  [${r.type}] ${r.name}  (score: ${r.score?.toFixed(3)})`);
    }
    showOutput("Cartographer Similar", lines.join("\n"));
  });
}

async function cmdEmbed(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  withProgress("Cartographer: Generating embeddings (this may take a while)...", async () => {
    const result = await c.embed();
    showOutput("Cartographer Embed", result);
  });
}

async function cmdGitIndex(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  withProgress("Cartographer: Indexing git history...", async () => {
    const result = await c.gitIndex();
    showOutput("Cartographer Git Index", result);
  });
}

function cmdOpenDb(): void {
  vscode.window.showOpenDialog({
    canSelectFiles: true,
    filters: { "SQLite DB": ["db", "sqlite", "sqlite3"] },
  }).then(uris => {
    if (!uris?.length) return;
    const dbPath = uris[0].fsPath;
    vscode.workspace.getConfiguration("cartographer").update("dbPath", dbPath, true);
    vscode.window.showInformationMessage(`Cartographer DB set to ${dbPath}`);
    repoTree.refresh();
    entityTree.refresh();
    updateStatusBar();
  });
}

async function cmdRefresh(): Promise<void> {
  repoTree.refresh();
  entityTree.refresh();
  await updateStatusBar();
  vscode.window.showInformationMessage("Cartographer views refreshed");
}

// ── New commands ─────────────────────────────────────────────────────────

async function cmdWatch(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  const wsRoot = c.projectRoot;
  withProgress("Cartographer: Starting file watcher...", async () => {
    vscode.window.showInformationMessage("Cartographer watch started (see output channel)");
    const result = await c.invokeWatch(wsRoot);
    const ch = vscode.window.createOutputChannel("Cartographer Watch");
    ch.clear();
    ch.appendLine(result);
    ch.show();
  });
}

async function cmdContext(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  withProgress("Cartographer: Generating context package...", async () => {
    const result = await c.getContext();
    showOutput("Cartographer Context", result);
  });
}

async function cmdDbInfo(): Promise<void> {
  const c = pickFolder();
  if (!c) return;
  try {
    const info = await c.dbInfo();
    showOutput("Cartographer Database", info);
  } catch (e) {
    showError(`DB info failed: ${e}`);
  }
}

function cmdGraph(entityType?: string, repoName?: string): void {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return void showError("No workspace folder open");
  function showGraph(client: CartographerClient) {
    createGraphWebview(client, ctx.extensionUri, entityType, repoName);
  }
  if (folders.length === 1) {
    showGraph(clients.get(folders[0].uri.fsPath));
    return;
  }
  const items = folders.map(f => ({
    label: f.name,
    description: f.uri.fsPath,
    folder: f,
  }));
  const active = clients.active();
  const defaultIdx = active ? folders.findIndex(f => active.projectRoot.startsWith(f.uri.fsPath)) : 0;
  vscode.window.showQuickPick(items, { placeHolder: "Select folder for graph" }
  ).then(selected => {
    if (selected) showGraph(clients.get(selected.folder.uri.fsPath));
  });
}
// Re-export ctx for command use
let ctx: vscode.ExtensionContext;
export function _setCtx(c: vscode.ExtensionContext): void { ctx = c; }

export function deactivate(): void {
  clients?.dispose();
}
