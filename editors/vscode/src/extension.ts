import * as vscode from "vscode";
import { CartographerClient } from "./cartographer";
import { RepoTreeProvider, SearchTreeProvider } from "./treeViews";
import { createGraphWebview } from "./graphWebview";

let client: CartographerClient;
let repoTreeProvider: RepoTreeProvider;
let searchTreeProvider: SearchTreeProvider;

export function activate(context: vscode.ExtensionContext): void {
  const outputChannel = vscode.window.createOutputChannel("Cartographer");
  client = new CartographerClient(outputChannel);
  context.subscriptions.push(outputChannel);

  repoTreeProvider = new RepoTreeProvider(client);
  searchTreeProvider = new SearchTreeProvider(client);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("cartographer.repos", repoTreeProvider),
    vscode.window.registerTreeDataProvider("cartographer.search", searchTreeProvider),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("cartographer.index", cmdIndex),
    vscode.commands.registerCommand("cartographer.search", cmdSearch),
    vscode.commands.registerCommand("cartographer.summarize", cmdSummarize),
    vscode.commands.registerCommand("cartographer.architecture", cmdArchitecture),
    vscode.commands.registerCommand("cartographer.impact", cmdImpact),
    vscode.commands.registerCommand("cartographer.graph", () => createGraphWebview(context.extensionUri)),
    vscode.commands.registerCommand("cartographer.refresh", () => {
      repoTreeProvider.refresh();
      vscode.window.showInformationMessage("Cartographer views refreshed");
    }),
  );

  vscode.commands.registerCommand("cartographer.openNode", (filePath: string) => {
    if (filePath) {
      vscode.workspace.openTextDocument(vscode.Uri.file(filePath))
        .then(doc => vscode.window.showTextDocument(doc));
    }
  });
}

function cmdIndex(): void {
  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Cartographer: Indexing repository..." },
    async () => {
      try {
        const result = client.index();
        if (result.success) {
          vscode.window.showInformationMessage(
            `Indexed ${result.files} files in ${result.dirs} directories (${result.duration_ms}ms)`,
          );
        } else {
          vscode.window.showWarningMessage(
            `Indexed with ${result.errors.length} warnings`,
          );
        }
        repoTreeProvider.refresh();
      } catch (e) {
        vscode.window.showErrorMessage(`Index failed: ${e}`);
      }
    },
  );
}

function cmdSearch(): void {
  vscode.window.showInputBox({
    prompt: "Search the knowledge graph",
    placeHolder: "e.g. class name, function, file...",
  }).then((query) => {
    if (!query) return;
    const results = client.search(query);
    searchTreeProvider.setResults(results);
    vscode.commands.executeCommand("workbench.view.extension.cartographer");
    vscode.window.showInformationMessage(`Found ${results.length} results for "${query}"`);
  });
}

function cmdSummarize(): void {
  const summary = client.summarize();
  if (!summary) {
    vscode.window.showErrorMessage("No repository found. Run 'Cartographer: Index Repository' first.");
    return;
  }
  const panel = vscode.window.createOutputChannel("Cartographer Summary");
  panel.clear();
  panel.appendLine(`Repository: ${summary.name}`);
  panel.appendLine(`Path: ${summary.path}`);
  panel.appendLine(`Total nodes: ${summary.total_nodes}`);
  panel.appendLine(`Total edges: ${summary.total_edges}`);
  panel.appendLine("");
  panel.appendLine("Node breakdown:");
  for (const [type, count] of Object.entries(summary.node_breakdown)) {
    panel.appendLine(`  ${type}: ${count}`);
  }
  panel.appendLine("");
  panel.appendLine("Edge breakdown:");
  for (const [type, count] of Object.entries(summary.edge_breakdown)) {
    panel.appendLine(`  ${type}: ${count}`);
  }
  panel.show();
}

function cmdArchitecture(): void {
  const arch = client.architecture(true);
  if (!arch) {
    vscode.window.showErrorMessage("Architecture detection failed. Run 'Cartographer: Index Repository' first.");
    return;
  }
  const panel = vscode.window.createOutputChannel("Cartographer Architecture");
  panel.clear();
  panel.appendLine(`Architecture for ${arch.repository}`);
  if (arch.frameworks) {
    panel.appendLine("");
    panel.appendLine("Frameworks:");
    for (const fw of arch.frameworks) {
      panel.appendLine(`  ${fw.name} (${Math.round(fw.confidence * 100)}% confidence)`);
    }
  }
  panel.show();
}

function cmdImpact(): void {
  vscode.window.showInputBox({
    prompt: "Target file or symbol for impact analysis",
    placeHolder: "e.g. auth_service, User, models.py...",
  }).then((target) => {
    if (!target) return;
    const results = client.impact(target);
    if (results.length === 0) {
      vscode.window.showInformationMessage(`No dependents found for "${target}"`);
      return;
    }
    const panel = vscode.window.createOutputChannel("Cartographer Impact");
    panel.clear();
    panel.appendLine(`Impact analysis for "${target}":`);
    panel.appendLine(`Found ${results.length} dependents:`);
    for (const r of results) {
      panel.appendLine(`  [${r.type}] ${r.name}`);
      if (r.file_path) panel.appendLine(`    ${r.file_path}`);
    }
    panel.show();
  });
}

export function deactivate(): void {
  // cleanup
}
