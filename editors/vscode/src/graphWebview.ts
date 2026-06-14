import * as vscode from "vscode";

export function createGraphWebview(extensionUri: vscode.Uri): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    "cartographer.graph",
    "Cartographer Graph",
    vscode.ViewColumn.Beside,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
    },
  );

  panel.webview.html = getGraphHtml();

  panel.webview.onDidReceiveMessage(
    (message) => {
      switch (message.command) {
        case "alert":
          vscode.window.showErrorMessage(message.text);
          return;
      }
    },
    undefined,
  );

  return panel;
}

function getGraphHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cartographer Graph</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--vscode-editor-background); color: var(--vscode-editor-foreground);
         overflow: hidden; height: 100vh; }
  #container { display: flex; height: 100vh; }
  #sidebar { width: 280px; border-right: 1px solid var(--vscode-panel-border);
             padding: 12px; overflow-y: auto; flex-shrink: 0; }
  #graph { flex: 1; position: relative; overflow: hidden; }
  #graph svg { width: 100%; height: 100%; }
  h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
       color: var(--vscode-descriptionForeground); margin: 12px 0 8px; }
  h3:first-child { margin-top: 0; }
  .stat { display: flex; justify-content: space-between; padding: 4px 0;
          font-size: 13px; }
  .stat .val { color: var(--vscode-textLink-foreground); font-weight: 600; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; }
  .legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .help { font-size: 11px; color: var(--vscode-descriptionForeground);
          margin-top: 16px; line-height: 1.6; }
  .empty { text-align: center; padding: 40px 20px; color: var(--vscode-descriptionForeground); }
  .empty p { margin-top: 8px; font-size: 13px; }
  .progress { animation: spin 2s linear infinite; }
  @keyframes spin { 100% { transform: rotate(360deg); } }
</style>
</head>
<body>
<div id="container">
  <div id="sidebar">
    <h3>Repository</h3>
    <div class="stat"><span>Name</span><span class="val" id="repoName">-</span></div>
    <div class="stat"><span>Nodes</span><span class="val" id="nodeCount">-</span></div>
    <div class="stat"><span>Edges</span><span class="val" id="edgeCount">-</span></div>

    <h3>Node Types</h3>
    <div id="nodeBreakdown"></div>

    <h3>Legend</h3>
    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background:#4fc3f7"></span>file</span>
      <span class="legend-item"><span class="legend-dot" style="background:#ffb74d"></span>class</span>
      <span class="legend-item"><span class="legend-dot" style="background:#81c784"></span>function</span>
      <span class="legend-item"><span class="legend-dot" style="background:#ce93d8"></span>method</span>
      <span class="legend-item"><span class="legend-dot" style="background:#ef5350"></span>api</span>
      <span class="legend-item"><span class="legend-dot" style="background:#90a4ae"></span>other</span>
    </div>

    <div class="help">
      <strong>cartographer</strong><br>
      Package docs for details.
    </div>
  </div>
  <div id="graph">
    <svg id="graphSvg"></svg>
  </div>
</div>
</body>
</html>`;
}
