import * as vscode from "vscode";
import { CartographerClient, RepoInfo, type SearchResult } from "./cartographer";

// ── Repository Tree ──────────────────────────────────────────────────────

export class RepoItem extends vscode.TreeItem {
  constructor(
    label: string,
    description: string,
    collapsible: vscode.TreeItemCollapsibleState,
    icon: string,
    cmd?: vscode.Command,
  ) {
    super(label, collapsible);
    this.description = description;
    this.tooltip = description;
    this.iconPath = new vscode.ThemeIcon(icon);
    this.contextValue = "repoItem";
    this.command = cmd;
  }
}

export class RepoTreeProvider implements vscode.TreeDataProvider<RepoItem> {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChange.event;

  constructor(private client: CartographerClient) {}

  refresh(): void { this._onDidChange.fire(); }

  getTreeItem(el: RepoItem): vscode.TreeItem { return el; }

  getChildren(el?: RepoItem): Thenable<RepoItem[]> {
    if (el) return Promise.resolve([]);

    const repos = this.client.getRepos();
    if (repos.length === 0) {
      return Promise.resolve([
        new RepoItem("No repository indexed", "Run Index Repository", vscode.TreeItemCollapsibleState.None, "question"),
      ]);
    }

    return Promise.resolve(
      repos.map(r => new RepoItem(
        r.name,
        `${r.nodes} nodes · ${r.edges} edges`,
        vscode.TreeItemCollapsibleState.Collapsed,
        "repo",
        { command: "cartographer.summarize", title: "Summary", arguments: [r.name] },
      )),
    );
  }
}

// ── Entity Type Tree ──────────────────────────────────────────────────────

const ENTITY_ICONS: Record<string, string> = {
  class: "symbol-class",
  function: "symbol-function",
  method: "symbol-method",
  file: "file",
  directory: "folder",
  interface: "symbol-interface",
  enum: "symbol-enum",
  constant: "symbol-constant",
  variable: "symbol-variable",
  api_endpoint: "symbol-ruler",
  table: "database",
  module: "symbol-module",
  controller: "symbol-misc",
  service: "symbol-misc",
};

export class EntityItem extends vscode.TreeItem {
  constructor(
    label: string,
    count: number,
    public readonly entityType: string,
    collapsible: vscode.TreeItemCollapsibleState,
  ) {
    super(`${label} (${count})`, collapsible);
    this.description = entityType;
    this.iconPath = new vscode.ThemeIcon(ENTITY_ICONS[entityType] || "symbol-property");
    this.contextValue = "entityType";
    this.command = {
      command: "cartographer.searchType",
      title: "Search by Type",
      arguments: [entityType],
    };
  }
}

export class EntityTreeProvider implements vscode.TreeDataProvider<EntityItem> {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChange.event;
  private _repoName: string | undefined;

  constructor(private client: CartographerClient) {}

  setRepo(name?: string): void {
    this._repoName = name;
    this.refresh();
  }
  currentRepo(): string | undefined {
    return this._repoName;
  }

  refresh(): void { this._onDidChange.fire(); }

  getTreeItem(el: EntityItem): vscode.TreeItem { return el; }

  getChildren(): Thenable<EntityItem[]> {
    const s = this.client.summarize(this._repoName);
    if (!s?.node_breakdown || Object.keys(s.node_breakdown).length === 0) {
      return Promise.resolve([
        new EntityItem("No data", 0, "", vscode.TreeItemCollapsibleState.None),
      ]);
    }
    const items = Object.entries(s.node_breakdown)
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => new EntityItem(type, count, type, vscode.TreeItemCollapsibleState.None));
    return Promise.resolve(items);
  }
}

// ── Search Results Tree ───────────────────────────────────────────────────

export class SearchItem extends vscode.TreeItem {
  constructor(result: SearchResult) {
    super(result.name, vscode.TreeItemCollapsibleState.None);
    this.description = `[${result.type}]`;
    this.tooltip = result.file_path || result.name;
    this.iconPath = new vscode.ThemeIcon(ENTITY_ICONS[result.type] || "symbol-property");
    this.contextValue = "searchResult";
    if (result.file_path) {
      this.command = {
        command: "vscode.open",
        title: "Open File",
        arguments: [vscode.Uri.file(result.file_path)],
      };
    }
  }
}

export class SearchTreeProvider implements vscode.TreeDataProvider<SearchItem> {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChange.event;
  private results: SearchResult[] = [];

  constructor() {}

  refresh(): void { this._onDidChange.fire(); }

  setResults(r: SearchResult[]): void { this.results = r; this.refresh(); }

  getTreeItem(el: SearchItem): vscode.TreeItem { return el; }

  getChildren(): Thenable<SearchItem[]> {
    if (this.results.length === 0) {
      return Promise.resolve([new SearchItem({ name: "Run a search to see results", type: "" })]);
    }
    return Promise.resolve(this.results.map(r => new SearchItem(r)));
  }
}
