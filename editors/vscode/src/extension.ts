import * as vscode from "vscode";
import { CartographerClient, SearchResult } from "./cartographer";
import { RepoTreeProvider, EntityTreeProvider, SearchTreeProvider, SearchItem } from "./treeViews";
import { createGraphWebview } from "./graphWebview";

let client: CartographerClient;
let repoTree: RepoTreeProvider;
let entityTree: EntityTreeProvider;
let searchTree: SearchTreeProvider;
let statusBar: vscode.StatusBarItem;

export function activate(ctx: vscode.ExtensionContext): void {
  const ch = vscode.window.createOutputChannel("Cartographer");
  client = new CartographerClient(ch);
  ctx.subscriptions.push(ch);

  repoTree = new RepoTreeProvider(client);
  entityTree = new EntityTreeProvider(client);
  searchTree = new SearchTreeProvider();
  // Sync entity tree to workspace repo on startup
  const wsName = vscode.workspace.workspaceFolders?.[0]?.name;
  if (wsName) entityTree.setRepo(wsName);

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

  // Update status bar on workspace change
  ctx.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(updateStatusBar));

  // Register all commands
  const cmds = [
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
    ["cartographer.graph", () => createGraphWebview(client)],
    ["cartographer.graphEntityType", (t: string) => createGraphWebview(client, t, entityTree.currentRepo())],
    ["cartographer.openDb", cmdOpenDb],
    ["cartographer.refresh", cmdRefresh],
    ["cartographer.searchType", cmdSearchByType],
  ] as const;

  for (const [id, fn] of cmds) {
    ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));
  }

  // Hover provider: show node info on code hover (debounced + cached)
  let hoverTimer: NodeJS.Timeout | undefined;
  const hoverCache = new Map<string, { results: SearchResult[]; time: number }>();
  ctx.subscriptions.push(
    vscode.languages.registerHoverProvider("*", {
      provideHover(document, position) {
        const range = document.getWordRangeAtPosition(position);
        if (!range) return null;
        const word = document.getText(range);
        if (!word || word.length < 2) return null;
        // Check cache (1 min TTL)
        const cached = hoverCache.get(word);
        if (cached && Date.now() - cached.time < 60000) {
          if (cached.results.length > 0) {
            return formatHover(cached.results);
          }
          return null;
        }
        // Debounce: don't search on every mouse movement
        return new Promise<vscode.Hover | null | undefined>(resolve => {
          if (hoverTimer) clearTimeout(hoverTimer);
          hoverTimer = setTimeout(() => {
            try {
              const results = client.search(word);
              hoverCache.set(word, { results, time: Date.now() });
              resolve(results.length > 0 ? formatHover(results) : null);
            } catch {
              resolve(null);
            }
          }, 300);
        });
      },
    }),
  );

  // Trim cache every 5 min
  setInterval(() => {
    const cutoff = Date.now() - 120000;
    for (const [k, v] of hoverCache) {
      if (v.time < cutoff) hoverCache.delete(k);
    }
  }, 300000);

  // Selection-based search context menu
  ctx.subscriptions.push(
    vscode.commands.registerCommand("cartographer.searchSelection", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.selection.isEmpty) return;
      const word = editor.document.getText(editor.selection);
      if (word) cmdSearchWith(word);
    }),
  );

  updateStatusBar();
}

// ── Status bar ────────────────────────────────────────────────────────────

function updateStatusBar(): void {
  try {
    const sum = client.summarize();
    if (sum) {
      const ws = vscode.workspace.workspaceFolders?.[0]?.name || sum.name;
      statusBar.text = `$(graph) ${ws}  ${sum.total_nodes}N/${sum.total_edges}E`;
      statusBar.tooltip = `${sum.name}: ${sum.total_nodes} nodes, ${sum.total_edges} edges`;
    } else {
      statusBar.text = "$(graph) Cartographer";
      statusBar.tooltip = "No repo indexed";
    }
  } catch {
    statusBar.text = "$(graph) Cartographer";
  }
}

// ── Command implementations ───────────────────────────────────────────────

function withProgress<T>(title: string, fn: () => T): Thenable<T> {
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title },
    async () => fn(),
  );
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

function cmdIndex(): void {
  if (!vscode.workspace.workspaceFolders?.length) {
    return void showError("Open a workspace folder first");
  }
  withProgress("Cartographer: Indexing repository...", () => {
    const r = client.index();
    if (r.success) {
      vscode.window.showInformationMessage(`Indexed ${r.files} files in ${r.duration_ms}ms`);
      repoTree.refresh();
      entityTree.refresh();
      updateStatusBar();
    } else {
      const msg = r.errors[0]?.replace(/^Error:\s*/, "") || "Index command failed";
      vscode.window.showErrorMessage(`Cartographer index failed: ${msg}`);
      // Show error details in the Cartographer output channel
      const ch = vscode.window.createOutputChannel("Cartographer Index");
      ch.clear();
      ch.appendLine(r.errors.join("\n"));
      ch.show();
    }
  });
}

function cmdSearchByType(entityType: string): void {
  if (!entityType) return;
  withProgress(`Cartographer: Loading ${entityType}s...`, () => {
    const results = client.searchByType(entityType, 100, entityTree.currentRepo());
    searchTree.setResults(results);
    vscode.commands.executeCommand("workbench.view.extension.cartographer");
    if (results.length > 0) {
      vscode.window.showInformationMessage(`Found ${results.length} ${entityType}s`);
    } else {
      // Check if there's a repo mismatch
      vscode.window.showWarningMessage(
        `Found 0 ${entityType}s. Check the Cartographer output channel for details.`
      );
    }
  });
}

function cmdSearchWith(query?: string): void {
  cmdSearch(query);
}

function cmdSearch(initial?: string): void {
  vscode.window.showInputBox({
    prompt: "Search the knowledge graph",
    placeHolder: "class name, function, file...",
    value: initial || "",
  }).then(q => {
    if (!q) return;
    const results = client.search(q);
    searchTree.setResults(results);
    vscode.commands.executeCommand("workbench.view.extension.cartographer");
    vscode.window.showInformationMessage(`Found ${results.length} results for "${q}"`);
  });
}

function cmdAsk(): void {
  vscode.window.showInputBox({
    prompt: "Ask a natural language question about the codebase",
    placeHolder: "e.g. What does the auth module do? Explain checkout flow...",
  }).then(q => {
    if (!q) return;
    withProgress("Cartographer: Querying...", () => {
      const answer = client.ask(q);
      showOutput("Cartographer Answer", answer);
    });
  });
}

function cmdSummarize(repoName?: string): void {
  const s = client.summarize(repoName);
  if (!s) return void showError("No repository indexed");
  // Update entity tree to show this repo's types
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

function cmdArchitecture(): void {
  withProgress("Cartographer: Detecting architecture...", () => {
    const result = client.architecture();
    showOutput("Cartographer Architecture", result);
  });
}

function cmdImpact(): void {
  vscode.window.showInputBox({
    prompt: "Find what depends on this symbol",
    placeHolder: "e.g. User, auth_service, database...",
  }).then(q => {
    if (!q) return;
    const results = client.impact(q);
    if (results.length === 0) return void vscode.window.showInformationMessage(`No dependents found for "${q}"`);
    const lines = [`Impact analysis for "${q}"`, `Found ${results.length} dependents:`, ""];
    for (const r of results) {
      lines.push(`  [${r.type}] ${r.name}`);
      if (r.file_path) lines.push(`    ${r.file_path}`);
    }
    showOutput("Cartographer Impact", lines.join("\n"));
  });
}

function cmdNeighbors(): void {
  vscode.window.showInputBox({
    prompt: "Show neighbors of a node",
    placeHolder: "Node name or class...",
  }).then(async q => {
    if (!q) return;
    const depth = await vscode.window.showInputBox({ prompt: "Traversal depth", value: "2" }) || "2";
    const results = client.neighbors(q, parseInt(depth) || 2);
    if (results.length === 0) return void vscode.window.showInformationMessage(`No neighbors found for "${q}"`);
    const lines = [`Neighbors of "${q}":`, ""];
    for (const r of results) {
      if (r.depth === 0) continue;
      lines.push(`${"  ".repeat(r.depth)}[${r.type}] ${r.name}`);
    }
    showOutput("Cartographer Neighbors", lines.join("\n"));
  });
}

function cmdPath(): void {
  const fromPromise = vscode.window.showInputBox({ prompt: "Start node", placeHolder: "e.g. UserController" });
  fromPromise.then(from => {
    if (!from) return;
    vscode.window.showInputBox({ prompt: "End node", placeHolder: "e.g. Database" }).then(to => {
      if (!to) return;
      const results = client.path(from, to);
      if (results.length === 0) return void vscode.window.showInformationMessage("No path found");
      const lines = [`Path from "${from}" to "${to}":`];
      for (const r of results) {
        const arrow = r.depth > 0 ? "  → " : "     ";
        lines.push(`${arrow}[${r.type}] ${r.name}`);
      }
      showOutput("Cartographer Path", lines.join("\n"));
    });
  });
}

function cmdSimilar(): void {
  vscode.window.showInputBox({
    prompt: "Find semantically similar nodes",
    placeHolder: "Target node name...",
  }).then(q => {
    if (!q) return;
    withProgress("Cartographer: Searching similar...", () => {
      const results = client.similar(q);
      if (results.length === 0) return void vscode.window.showInformationMessage("No similar nodes found");
      const lines = [`Similar to "${q}":`];
      for (const r of results) {
        lines.push(`  [${r.type}] ${r.name}  (score: ${r.score?.toFixed(3)})`);
      }
      showOutput("Cartographer Similar", lines.join("\n"));
    });
  });
}

function cmdEmbed(): void {
  withProgress("Cartographer: Generating embeddings (this may take a while)...", () => {
    const result = client.embed();
    showOutput("Cartographer Embed", result);
  });
}

function cmdGitIndex(): void {
  if (!vscode.workspace.workspaceFolders?.length) {
    return void showError("Open a workspace folder first");
  }
  withProgress("Cartographer: Indexing git history...", () => {
    const result = client.gitIndex();
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

function cmdRefresh(): void {
  repoTree.refresh();
  entityTree.refresh();
  updateStatusBar();
  vscode.window.showInformationMessage("Cartographer views refreshed");
}

export function deactivate(): void {
  // cleanup
}
