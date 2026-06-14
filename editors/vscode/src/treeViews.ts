import * as vscode from "vscode";
import { CartographerClient, RepoInfo, SearchResult } from "./cartographer";

export class RepoTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly description: string,
    collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly contextValue?: string,
    public readonly command?: vscode.Command,
  ) {
    super(label, collapsibleState);
    this.description = description;
    this.tooltip = description;
  }
}

export class RepoTreeProvider implements vscode.TreeDataProvider<RepoTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private client: CartographerClient) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: RepoTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: RepoTreeItem): Thenable<RepoTreeItem[]> {
    if (element) {
      return Promise.resolve([]);
    }
    const repos = this.client.getRepos();
    if (repos.length === 0) {
      return Promise.resolve([
        new RepoTreeItem(
          "No repositories indexed",
          "Run 'Cartographer: Index Repository' to start",
          vscode.TreeItemCollapsibleState.None,
        ),
      ]);
    }
    return Promise.resolve(
      repos.map(
        (r: RepoInfo) =>
          new RepoTreeItem(
            r.name,
            `${r.nodes} nodes, ${r.edges} edges`,
            vscode.TreeItemCollapsibleState.Collapsed,
            "repo",
            {
              command: "cartographer.summarize",
              title: "Show Summary",
              arguments: [r.name],
            },
          ),
      ),
    );
  }
}

export class SearchTreeItem extends vscode.TreeItem {
  constructor(
    public readonly result: SearchResult,
  ) {
    super(
      `${result.name}`,
      vscode.TreeItemCollapsibleState.None,
    );
    this.description = `[${result.type}]`;
    this.tooltip = result.file_path || result.name;
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

export class SearchTreeProvider implements vscode.TreeDataProvider<SearchTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private results: SearchResult[] = [];

  constructor(private client: CartographerClient) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  setResults(results: SearchResult[]): void {
    this.results = results;
    this.refresh();
  }

  getTreeItem(element: SearchTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): Thenable<SearchTreeItem[]> {
    if (this.results.length === 0) {
      return Promise.resolve([
        new SearchTreeItem({ name: "Search to see results", type: "", score: 0 }),
      ]);
    }
    return Promise.resolve(this.results.map((r) => new SearchTreeItem(r)));
  }
}
