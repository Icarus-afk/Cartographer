import * as vscode from "vscode";
import { CartographerClient, SearchResult } from "./cartographer";
import { RepoTreeProvider, EntityTreeProvider, SearchTreeProvider, SearchItem } from "./treeViews";
import { createGraphWebview } from "./graphWebview";
import { readProjectConfig, watchConfig, resolveDbPath } from "./config";

let client: CartographerClient;
let repoTree: RepoTreeProvider;
let entityTree: EntityTreeProvider;
let searchTree: SearchTreeProvider;
let statusBar: vscode.StatusBarItem;

export function activate(ctx: vscode.ExtensionContext): void {
  const ch = vscode.window.createOutputChannel("Cartographer");
  const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "";

  // Read project config
  const projCfg = readProjectConfig(wsRoot);
  client = new CartographerClient(ch, wsRoot);
  ctx.subscriptions.push(ch);

  // Watch .cartographer/config.json for changes
  if (wsRoot) {
    ctx.subscriptions.push(watchConfig(wsRoot, () => {
      repoTree.refresh();
      updateStatusBar();
    }));
  }

  repoTree = new RepoTreeProvider(client);
  entityTree = new EntityTreeProvider(client);
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

  ctx.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => updateStatusBar()));

  // Start MCP server as persistent child process
  if (wsRoot) {
    client.startMcp().then(() => {
      ch.appendLine("MCP server connected");
    });
  }

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
    ["cartographer.graph", () => createGraphWebview(client, ctx.extensionUri)],
    ["cartographer.graphEntityType", (t: string) => createGraphWebview(client, ctx.extensionUri, t, entityTree.currentRepo())],
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

  // Hover provider: debounced + cached
  let hoverTimer: NodeJS.Timeout | undefined;
  const hoverCache = new Map<string, { results: SearchResult[]; time: number }>();
  ctx.subscriptions.push(
    vscode.languages.registerHoverProvider("*", {
      provideHover(document, position) {
        if (!client) return null;
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
              const results = await client.search(word);
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

  // Auto-index workspace on activation if not already indexed
  (async () => {
    if (!wsRoot) { updateStatusBar(); return; }
    if (projCfg.autoReindex === false) { updateStatusBar(); return; }
    const repoName = await resolveRepoQuick();
    if (repoName) { updateStatusBar(); return; }
    vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Cartographer: Indexing repository..." },
      async () => {
        await client.index();
        repoTree.refresh();
        entityTree.refresh();
        updateStatusBar();
      },
    );
  })();

  // File watcher: incremental re-index via update_index/delete_file MCP tools
  let reindexTimer: NodeJS.Timeout | undefined;
  let progressKey: string | undefined;
  const pendingFiles = new Set<string>();
  function scheduleReindex() {
    if (reindexTimer) clearTimeout(reindexTimer);
    reindexTimer = setTimeout(flushReindex, 2000);
  }
  async function flushReindex() {
    const files = Array.from(pendingFiles);
    pendingFiles.clear();
    if (files.length === 0) return;
    statusBar.text = "$(sync~spin) Cartographer";
    progressKey = "updating";
    for (const f of files) {
      try {
        if (f.startsWith("+")) {
          const raw = f.slice(1);
          await client.updateFile(raw);
        } else if (f.startsWith("-")) {
          const raw = f.slice(1);
          await client.deleteFile(raw);
        }
      } catch { /* ignore single file errors */ }
    }
    progressKey = undefined;
    repoTree.refresh();
    entityTree.refresh();
    updateStatusBar();
  }
  ctx.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (!wsRoot) return;
      if (!projCfg.autoReindex) return;
      if (doc.uri.scheme !== "file") return;
      if (!doc.fileName.startsWith(wsRoot)) return;
      if (isIgnored(doc.fileName, wsRoot)) return;
      pendingFiles.add("+" + doc.fileName);
      scheduleReindex();
    }),
    vscode.workspace.onDidDeleteFiles(async (event) => {
      if (!wsRoot) return;
      if (!projCfg.autoReindex) return;
      for (const uri of event.files) {
        if (!uri.fsPath.startsWith(wsRoot)) continue;
        if (isIgnored(uri.fsPath, wsRoot)) continue;
        pendingFiles.add("-" + uri.fsPath);
      }
      if (event.files.length > 0) scheduleReindex();
    }),
    vscode.workspace.onDidRenameFiles(async (event) => {
      if (!wsRoot) return;
      if (!projCfg.autoReindex) return;
      for (const file of event.files) {
        if (!file.oldUri.fsPath.startsWith(wsRoot)) continue;
        if (isIgnored(file.oldUri.fsPath, wsRoot)) continue;
        pendingFiles.add("-" + file.oldUri.fsPath);
        pendingFiles.add("+" + file.newUri.fsPath);
      }
      if (event.files.length > 0) scheduleReindex();
    }),
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────

function isIgnored(filePath: string, root: string): boolean {
  const rel = filePath.startsWith(root) ? filePath.slice(root.length) : filePath;
  const ignored = ["node_modules", ".git", ".cartographer", "__pycache__", "venv", ".venv", "dist", "build", ".next", "target"];
  for (const dir of ignored) {
    if (rel.startsWith(`/${dir}`) || rel.startsWith(`${dir}`)) return true;
  }
  return false;
}

async function resolveRepoQuick(): Promise<string | null> {
  try {
    const sum = await client.summarize();
    return sum?.name || null;
  } catch { return null; }
}

async function updateStatusBar(): Promise<void> {
  try {
    const sum = await client.summarize();
    if (sum) {
      const ws = vscode.workspace.workspaceFolders?.[0]?.name || sum.name;
      statusBar.text = `$(graph) ${ws}  ${sum.total_nodes}N/${sum.total_edges}E`;
      statusBar.tooltip = `${sum.name}: ${sum.total_nodes} nodes, ${sum.total_edges} edges`;
    } else {
      statusBar.text = "$(graph) Cartographer";
      statusBar.tooltip = "No repo indexed";
    }
  } catch { statusBar.text = "$(graph) Cartographer"; }
}

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

// ── Command implementations ───────────────────────────────────────────────

async function cmdIndex(): Promise<void> {
  withProgress("Cartographer: Indexing repository...", async () => {
    const r = await client.index();
    if (r.success) {
      vscode.window.showInformationMessage(`Indexed ${r.files} files in ${r.duration_ms}ms`);
      repoTree.refresh();
      entityTree.refresh();
      updateStatusBar();
    } else {
      const msg = r.errors[0]?.replace(/^Error:\s*/, "") || "Index command failed";
      vscode.window.showErrorMessage(`Cartographer index failed: ${msg}`);
      const ch = vscode.window.createOutputChannel("Cartographer Index");
      ch.clear();
      ch.appendLine(r.errors.join("\n"));
      ch.show();
    }
  });
}

async function cmdSearchByType(entityType: string): Promise<void> {
  if (!entityType) return;
  withProgress(`Cartographer: Loading ${entityType}s...`, async () => {
    const results = await client.searchByType(entityType, 100, entityTree.currentRepo());
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
  const q = await vscode.window.showInputBox({
    prompt: "Search the knowledge graph",
    placeHolder: "class name, function, file...",
    value: initial || "",
  });
  if (!q) return;
  const results = await client.search(q);
  searchTree.setResults(results);
  vscode.commands.executeCommand("workbench.view.extension.cartographer");
  vscode.window.showInformationMessage(`Found ${results.length} results for "${q}"`);
}

async function cmdAsk(): Promise<void> {
  const q = await vscode.window.showInputBox({
    prompt: "Ask a natural language question about the codebase",
    placeHolder: "e.g. What does the auth module do? Explain checkout flow...",
  });
  if (!q) return;
  withProgress("Cartographer: Querying...", async () => {
    const answer = await client.ask(q);
    showOutput("Cartographer Answer", answer);
  });
}

async function cmdSummarize(repoName?: string): Promise<void> {
  const s = await client.summarize(repoName);
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
  withProgress("Cartographer: Detecting architecture...", async () => {
    const result = await client.architecture();
    showOutput("Cartographer Architecture", result);
  });
}

async function cmdImpact(): Promise<void> {
  const q = await vscode.window.showInputBox({
    prompt: "Find what depends on this symbol",
    placeHolder: "e.g. User, auth_service, database...",
  });
  if (!q) return;
  const results = await client.impact(q);
  if (results.length === 0) return void vscode.window.showInformationMessage(`No dependents found for "${q}"`);
  const lines = [`Impact analysis for "${q}"`, `Found ${results.length} dependents:`, ""];
  for (const r of results) {
    lines.push(`  [${r.type}] ${r.name}`);
    if (r.file_path) lines.push(`    ${r.file_path}`);
  }
  showOutput("Cartographer Impact", lines.join("\n"));
}

async function cmdNeighbors(): Promise<void> {
  const q = await vscode.window.showInputBox({
    prompt: "Show neighbors of a node",
    placeHolder: "Node name or class...",
  });
  if (!q) return;
  const depth = await vscode.window.showInputBox({ prompt: "Traversal depth", value: "2" }) || "2";
  const results = await client.neighbors(q, parseInt(depth) || 2);
  if (results.length === 0) return void vscode.window.showInformationMessage(`No neighbors found for "${q}"`);
  const lines = [`Neighbors of "${q}":`, ""];
  for (const r of results) {
    if (r.depth === 0) continue;
    lines.push(`${"  ".repeat(r.depth)}[${r.type}] ${r.name}`);
  }
  showOutput("Cartographer Neighbors", lines.join("\n"));
}

async function cmdPath(): Promise<void> {
  const from = await vscode.window.showInputBox({ prompt: "Start node", placeHolder: "e.g. UserController" });
  if (!from) return;
  const to = await vscode.window.showInputBox({ prompt: "End node", placeHolder: "e.g. Database" });
  if (!to) return;
  const results = await client.path(from, to);
  if (results.length === 0) return void vscode.window.showInformationMessage("No path found");
  const lines = [`Path from "${from}" to "${to}":`];
  for (const r of results) {
    const arrow = r.depth > 0 ? "  → " : "     ";
    lines.push(`${arrow}[${r.type}] ${r.name}`);
  }
  showOutput("Cartographer Path", lines.join("\n"));
}

async function cmdSimilar(): Promise<void> {
  const q = await vscode.window.showInputBox({
    prompt: "Find semantically similar nodes",
    placeHolder: "Target node name...",
  });
  if (!q) return;
  withProgress("Cartographer: Searching similar...", async () => {
    const results = await client.similar(q);
    if (results.length === 0) return void vscode.window.showInformationMessage("No similar nodes found");
    const lines = [`Similar to "${q}":`];
    for (const r of results) {
      lines.push(`  [${r.type}] ${r.name}  (score: ${r.score?.toFixed(3)})`);
    }
    showOutput("Cartographer Similar", lines.join("\n"));
  });
}

async function cmdEmbed(): Promise<void> {
  withProgress("Cartographer: Generating embeddings (this may take a while)...", async () => {
    const result = await client.embed();
    showOutput("Cartographer Embed", result);
  });
}

async function cmdGitIndex(): Promise<void> {
  withProgress("Cartographer: Indexing git history...", async () => {
    const result = await client.gitIndex();
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
  const wsRoot = client.projectRoot;
  if (!wsRoot) return void showError("No workspace folder open");
  withProgress("Cartographer: Starting file watcher...", async () => {
    vscode.window.showInformationMessage("Cartographer watch started (see output channel)");
    const result = await client.invokeWatch(wsRoot);
    const ch = vscode.window.createOutputChannel("Cartographer Watch");
    ch.clear();
    ch.appendLine(result);
    ch.show();
  });
}

async function cmdContext(): Promise<void> {
  withProgress("Cartographer: Generating context package...", async () => {
    const result = await client.getContext();
    showOutput("Cartographer Context", result);
  });
}

async function cmdDbInfo(): Promise<void> {
  try {
    const info = await client.dbInfo();
    showOutput("Cartographer Database", info);
  } catch (e) {
    showError(`DB info failed: ${e}`);
  }
}

export function deactivate(): void {
  client?.stopMcp();
}
