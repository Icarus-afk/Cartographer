import * as vscode from "vscode";
import { CartographerClient, GraphData, GraphNode, GraphEdge } from "./cartographer";

const COLORS: Record<string, string> = {
  file: "#4fc3f7", class: "#ffb74d", function: "#81c784", method: "#ce93d8",
  api_endpoint: "#ef5350", interface: "#4dd0e1", enum: "#ffd54f",
  constant: "#a1887f", variable: "#90a4ae", table: "#26a69a",
  module: "#7986cb", controller: "#ff8a65", service: "#66bb6a",
  directory: "#bdbdbd",
};

const EDGE_COLORS: Record<string, string> = {
  CONTAINS: "#888", DEFINES: "#4fc3f7", IMPORTS: "#ffb74d",
  DECLARES: "#81c784", EXTENDS: "#ce93d8", IMPLEMENTS: "#4dd0e1",
  CALLS: "#ef5350", REFERENCES: "#a1887f", INHERITS: "#ce93d8",
};

function dedupNodes(base: GraphNode[], add: GraphNode[]): GraphNode[] {
  if (add.length === 0) return base;
  const seen = new Set(base.map(n => n.id));
  const out = [...base];
  for (const n of add) {
    if (!seen.has(n.id)) { seen.add(n.id); out.push(n); }
  }
  return out;
}

function dedupEdges(base: GraphEdge[], add: GraphEdge[]): GraphEdge[] {
  if (add.length === 0) return base;
  const seen = new Set(base.map(e => `${e.source}→${e.target}:${e.type}`));
  const out = [...base];
  for (const e of add) {
    const k = `${e.source}→${e.target}:${e.type}`;
    if (!seen.has(k)) { seen.add(k); out.push(e); }
  }
  return out;
}

export function createGraphWebview(
  client: CartographerClient,
  extensionUri: vscode.Uri,
  entityType?: string,
  repoName?: string,
): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    "cartographer.graph", entityType ? `Graph: ${entityType}s` : "Cartographer Graph",
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extensionUri, "resources")] },
  );

  const limit = client.cfg("graphLimit", 400);

  const emptyData = (): GraphData => ({
    nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0,
    directories: [], next_offset: 0, has_more: false,
  });
  let currentData: GraphData = emptyData();
  let allNodes: GraphNode[] = [];
  let allEdges: GraphEdge[] = [];
  let currentDir = "";
  let nextOffset = 0;
  let hasMore = true;
  let loading = false;

  async function loadData(offset = 0, dir?: string, expandId?: number): Promise<GraphData> {
    if (loading) return currentData;
    loading = true;
    panel.webview.postMessage({ command: "showLoading" });
    try {
      if (entityType) {
        const all = await client.getGraphData(limit, repoName, offset, dir, expandId);
        const filtered = all.nodes.filter(n => n.type === entityType);
        const ids = new Set(filtered.map(n => n.id));
        return {
          ...all,
          nodes: filtered,
          edges: all.edges.filter(e => ids.has(e.source) && ids.has(e.target)),
        };
      }
      return await client.getGraphData(limit, repoName, offset, dir, expandId);
    } finally {
      loading = false;
      panel.webview.postMessage({ command: "hideLoading" });
    }
  }

  function pushState(extra: Record<string, unknown> = {}) {
    panel.webview.postMessage({
      command: "appendData",
      nodes: allNodes,
      edges: allEdges,
      totalNodes: currentData.total_nodes,
      totalEdges: currentData.total_edges,
      hasMore,
      nextOffset,
      loadedNodes: allNodes.length,
      loadedEdges: allEdges.length,
      ...extra,
    });
  }

  async function render(): Promise<void> {
    currentData = await loadData(0);
    allNodes = [...currentData.nodes];
    allEdges = [...currentData.edges];
    currentDir = "";
    nextOffset = currentData.next_offset ?? 0;
    hasMore = currentData.has_more ?? false;

    const gd = { ...currentData, nodes: allNodes, edges: allEdges };
    panel.webview.html = getHtml(gd, entityType, panel.webview, extensionUri);
  }

  panel.webview.onDidReceiveMessage(async msg => {
    switch (msg.command) {
      case "alert":
        vscode.window.showErrorMessage(msg.text);
        break;
      case "openFile":
        if (msg.path) {
          try {
            const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(msg.path));
            await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
          } catch {
            vscode.window.showWarningMessage(`Cannot open ${msg.path}`);
          }
        }
        break;
      case "loadMore": {
        if (loading) break;
        if (!hasMore) {
          vscode.window.showInformationMessage("All nodes loaded.");
          pushState();
          break;
        }
        const more = await loadData(nextOffset, currentDir || undefined);
        const before = allNodes.length;
        allNodes = dedupNodes(allNodes, more.nodes);
        allEdges = dedupEdges(allEdges, more.edges);
        nextOffset = more.next_offset ?? nextOffset;
        hasMore = more.has_more ?? false;
        if (allNodes.length === before && !hasMore) {
          vscode.window.showInformationMessage("All nodes loaded.");
        }
        pushState({ added: allNodes.length - before });
        break;
      }
      case "expandNode": {
        const nodeData = await loadData(0, undefined, msg.nodeId);
        if (nodeData.nodes.length <= 1) {
          vscode.window.showInformationMessage("No neighbors found for this node.");
          break;
        }
        const before = allNodes.length;
        allNodes = dedupNodes(allNodes, nodeData.nodes);
        allEdges = dedupEdges(allEdges, nodeData.edges);
        pushState({ added: allNodes.length - before });
        break;
      }
      case "filterDir":
        currentDir = msg.dir || "";
        {
          const filtered = await loadData(0, msg.dir || undefined);
          currentData = filtered;
          allNodes = [...filtered.nodes];
          allEdges = [...filtered.edges];
          nextOffset = filtered.next_offset ?? 0;
          hasMore = filtered.has_more ?? false;
          panel.webview.postMessage({
            command: "replaceData",
            nodes: allNodes,
            edges: allEdges,
            directories: filtered.directories,
            totalNodes: filtered.total_nodes,
            totalEdges: filtered.total_edges,
            hasMore,
            nextOffset,
            loadedNodes: allNodes.length,
            loadedEdges: allEdges.length,
          });
        }
        break;
      case "impactNode": {
        try {
          const items = await client.impact(msg.name);
          panel.webview.postMessage({ command: "impactResult", name: msg.name, items: items.slice(0, 30), total: items.length });
        } catch {
          panel.webview.postMessage({ command: "impactResult", name: msg.name, items: [], total: 0 });
        }
        break;
      }
      case "resetGraph":
        await render();
        break;
    }
  });

  render();
  return panel;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getHtml(
  gd: GraphData, entityType: string | undefined,
  webview: vscode.Webview, extensionUri: vscode.Uri,
): string {
  const totalNodes = Number.isFinite(gd.total_nodes) ? gd.total_nodes! : gd.nodes.length;
  const totalEdges = Number.isFinite(gd.total_edges) ? gd.total_edges! : gd.edges.length;
  if (gd.nodes.length === 0 && totalNodes === 0) {
    return `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
      body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:var(--vscode-editor-background);color:var(--vscode-editor-foreground);text-align:center;padding:24px}
      .welcome{max-width:480px}
      h2{font-size:20px;margin-bottom:12px}
      p{color:var(--vscode-descriptionForeground);font-size:13px;line-height:1.5;margin-bottom:16px}
      button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:none;padding:10px 20px;border-radius:6px;cursor:pointer;font-size:13px}
      button:hover{background:var(--vscode-button-hoverBackground)}
      code{background:var(--vscode-textCodeBlock-background);padding:2px 6px;border-radius:3px;font-size:12px}
    </style></head><body><div class="welcome">
      <h2>Welcome to Cartographer</h2>
      <p>No graph data yet. Index a repository to see its knowledge graph, search, and AI tools.</p>
      <p><code>cartographer index .</code> or run <b>Cartographer: Index Repository</b> from the Command Palette.</p>
      <button onclick="acquireVsCodeApi().postMessage({command:'alert',text:'Run Cartographer: Index Repository from Command Palette (Ctrl+Shift+C I)'})">How to index</button>
    </div></body></html>`;
  }

  const typeEntries = Object.entries(gd.node_types || {}).sort((a, b) => b[1] - a[1]);
  const typeRows = typeEntries.map(([t, c]) =>
    `<label class="chip"><input type="checkbox" checked data-ntype="${esc(t)}" onchange="toggleNType('${esc(t)}', this.checked)"><span class="dot" style="background:${COLORS[t] || "#90a4ae"}"></span>${esc(t)}<span class="val">${Number.isFinite(c) ? c : 0}</span></label>`
  ).join("\n");

  const edgeCounts: Record<string, number> = {};
  for (const e of gd.edges) edgeCounts[e.type] = (edgeCounts[e.type] || 0) + 1;
  const edgeEntries = Object.entries(edgeCounts).sort((a, b) => b[1] - a[1]);
  const edgeRows = edgeEntries.map(([t, c]) =>
    `<label class="chip"><input type="checkbox" checked data-etype="${esc(t)}" onchange="toggleEType('${esc(t)}', this.checked)"><span class="dot" style="background:${EDGE_COLORS[t] || "#888"}"></span>${esc(t)}<span class="val">${c}</span></label>`
  ).join("\n");

  const dirs = gd.directories || [];
  const dirRows = dirs.slice(0, 30).map(d =>
    `<div class="dir-item" onclick="filterDir('${esc(d.path)}')">` +
    `<span class="dir-path">${esc(d.path)}</span>` +
    `<span class="dir-count">${Number.isFinite(d.count) ? d.count : 0}</span></div>`
  ).join("\n");

  const nodesJson = JSON.stringify(gd.nodes);
  const edgesJson = JSON.stringify(gd.edges);
  const d3Uri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "resources", "d3.v7.min.js"));
  const initHasMore = gd.has_more ? "true" : "false";
  const initNext = gd.next_offset ?? 0;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cartographer Graph</title>
<script src="${d3Uri}"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:var(--vscode-editor-background); color:var(--vscode-editor-foreground);
         overflow:hidden; height:100vh; }
  #app { display:flex; height:100vh; }
  #sidebar { width:290px; border-right:1px solid var(--vscode-panel-border);
             padding:12px; overflow-y:auto; flex-shrink:0; display:flex; flex-direction:column; }
  #graph { flex:1; position:relative; }
  #graph svg { width:100%; height:100%; }
  h3 { font-size:11px; text-transform:uppercase; letter-spacing:.5px;
       color:var(--vscode-descriptionForeground); margin:12px 0 8px; }
  h3:first-child { margin-top:0; }
  .node-count { font-size:11px; color:var(--vscode-descriptionForeground); margin-bottom:8px; line-height:1.5; }
  .actions { display:flex; flex-direction:column; gap:4px; }
  .actions button { background:var(--vscode-button-background);
    color:var(--vscode-button-foreground); border:none; padding:6px 12px; border-radius:3px;
    cursor:pointer; font-size:12px; text-align:center; }
  .actions button:hover { background:var(--vscode-button-hoverBackground); }
  .actions button:disabled { opacity:.45; cursor:default; }
  .actions button.secondary { background:var(--vscode-button-secondaryBackground);
    color:var(--vscode-button-secondaryForeground); }
  #searchBox { width:100%; padding:6px 8px; border:1px solid var(--vscode-input-border);
               background:var(--vscode-input-background); color:var(--vscode-input-foreground);
               border-radius:3px; font-size:12px; margin-bottom:8px; }
  .link { stroke-opacity:.4; }
  .node { cursor:pointer; stroke:#fff; stroke-width:1.5; }
  .node:hover { stroke-width:3; }
  .node.selected { stroke:#ffab40; stroke-width:3; }
  .label { font-size:10px; pointer-events:none; fill:var(--vscode-editor-foreground);
           text-shadow:0 0 3px var(--vscode-editor-background); }
  #statusBar { display:flex; gap:4px; margin:8px 0; flex-wrap:wrap; }
  #statusBar button { flex:1 1 45%; }
  .dir-list { max-height:160px; overflow-y:auto; margin-bottom:8px;
              border:1px solid var(--vscode-panel-border); border-radius:3px; }
  .dir-item { display:flex; justify-content:space-between; padding:3px 6px; font-size:11px;
              cursor:pointer; border-bottom:1px solid var(--vscode-panel-border); }
  .dir-item:hover { background:var(--vscode-list-hoverBackground); }
  .dir-item:last-child { border-bottom:none; }
  .dir-path { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; }
  .dir-count { color:var(--vscode-textLink-foreground); margin-left:6px; }
  .sidebar-section { margin-bottom:8px; }
  .chips { display:flex; flex-wrap:wrap; gap:4px; }
  .chip { display:inline-flex; align-items:center; gap:4px; font-size:11px; padding:2px 6px;
          border:1px solid var(--vscode-panel-border); border-radius:10px; cursor:pointer; }
  .chip input { margin:0; }
  .chip .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .chip .val { color:var(--vscode-textLink-foreground); font-weight:600; }
  #details { border:1px solid var(--vscode-panel-border); border-radius:4px; padding:8px;
             font-size:12px; display:none; margin-bottom:4px; }
  #details.show { display:block; }
  #details .d-name { font-weight:600; word-break:break-all; }
  #details .d-meta { color:var(--vscode-descriptionForeground); font-size:11px; margin:2px 0 6px; word-break:break-all; }
  #details .d-btns { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
  #details .d-btns button { flex:1 1 45%; background:var(--vscode-button-secondaryBackground);
    color:var(--vscode-button-secondaryForeground); border:none; padding:4px 6px; border-radius:3px;
    cursor:pointer; font-size:11px; }
  #details .d-btns button:hover { background:var(--vscode-button-hoverBackground); color:var(--vscode-button-foreground); }
  #impactList { margin-top:6px; max-height:120px; overflow-y:auto; font-size:11px; }
  #impactList div { padding:2px 0; border-top:1px solid var(--vscode-panel-border); word-break:break-all; }
  #tooltip { position:absolute; padding:8px 12px; background:var(--vscode-editorWidget-background);
             border:1px solid var(--vscode-panel-border); border-radius:4px; font-size:12px;
             pointer-events:none; opacity:0; transition:opacity .15s; z-index:100;
             max-width:300px; box-shadow:0 2px 8px rgba(0,0,0,.15); }
  #tooltip .tt-name { font-weight:600; }
  #tooltip .tt-type { color:var(--vscode-descriptionForeground); font-size:11px; }
  #loading { display:none; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
             padding:12px 24px; background:var(--vscode-editorWidget-background);
             border:1px solid var(--vscode-panel-border); border-radius:6px; font-size:13px;
             z-index:200; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  #loading.active { display:flex; align-items:center; gap:8px; }
  .spinner { width:16px; height:16px; border:2px solid var(--vscode-descriptionForeground);
             border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  #minimap { position:absolute; bottom:12px; right:12px; width:150px; height:100px;
             background:var(--vscode-editorWidget-background); border:1px solid var(--vscode-panel-border);
             border-radius:4px; overflow:hidden; z-index:50; cursor:pointer; }
  #minimap canvas { width:100%; height:100%; }
  #zoomControls { position:absolute; bottom:12px; left:12px; display:flex; gap:4px; z-index:50; }
  #zoomControls button { background:var(--vscode-button-background); color:var(--vscode-button-foreground);
    border:none; width:28px; height:28px; border-radius:3px; cursor:pointer; font-size:14px;
    display:flex; align-items:center; justify-content:center; }
  #zoomControls button:hover { background:var(--vscode-button-hoverBackground); }
  .mode-indicator { position:absolute; top:12px; right:12px; padding:4px 8px;
    background:var(--vscode-badge-background); color:var(--vscode-badge-foreground);
    border-radius:3px; font-size:11px; z-index:50; pointer-events:none; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h3>${entityType ? `${entityType}s Graph` : "Repository Graph"}</h3>
    <div class="node-count" id="nodeCount">
      Showing ${gd.nodes.length} of ${gd.total_nodes || gd.nodes.length} nodes
      &middot; ${gd.edges.length} of ${gd.total_edges || gd.edges.length} edges
    </div>
    <input id="searchBox" placeholder="Filter nodes... (Enter: zoom to match)" oninput="filterNodes(this.value)" onkeydown="if(event.key==='Enter')zoomToMatch(this.value)">

    <div class="sidebar-section" id="details">
      <div class="d-name" id="dName"></div>
      <div class="d-meta" id="dMeta"></div>
      <div class="d-btns">
        <button onclick="openSelected()">Open file</button>
        <button onclick="expandSelected()">Expand</button>
        <button onclick="focusSelected()">Focus</button>
        <button onclick="clearFocus()" id="clearFocusBtn" style="display:none">Clear focus</button>
        <button onclick="impactSelected()">Impact</button>
      </div>
      <div id="impactList"></div>
    </div>

    <div class="sidebar-section">
      <h3>Node Types</h3>
      <div class="chips" id="ntypeChips">
        ${typeRows || '<div style="font-size:12px;color:var(--vscode-descriptionForeground)">Index a repo first</div>'}
      </div>
    </div>

    <div class="sidebar-section">
      <h3>Edge Types</h3>
      <div class="chips" id="etypeChips">
        ${edgeRows || '<div style="font-size:12px;color:var(--vscode-descriptionForeground)">No edges</div>'}
      </div>
    </div>

    <div class="sidebar-section">
      <h3>Directories</h3>
      <div class="dir-list" id="dirList">
        <div class="dir-item" onclick="filterDir('')" style="font-weight:600">
          <span class="dir-path">(all)</span>
          <span class="dir-count">${gd.total_nodes || gd.nodes.length}</span>
        </div>
        ${dirRows || '<div style="font-size:11px;color:var(--vscode-descriptionForeground);padding:4px">No directory data</div>'}
      </div>
    </div>

    <h3>Actions</h3>
    <div id="statusBar" class="actions">
      <button id="loadMoreBtn" onclick="loadMore()">+ Load More</button>
      <button class="secondary" onclick="resetGraph()">Reset View</button>
      <button class="secondary" onclick="runLayout()">Re-layout</button>
      <button class="secondary" id="pauseBtn" onclick="togglePause()">Pause layout</button>
      <button class="secondary" onclick="clusterByDir()">Cluster by Dir</button>
      <button class="secondary" onclick="exportGraph()">Export SVG</button>
      <button class="secondary" onclick="toggleLabels()">Toggle Labels</button>
      <button class="secondary" onclick="zoomToFit()">Zoom to Fit</button>
    </div>
  </div>
  <div id="graph">
    <svg id="svg"></svg>
    <div id="tooltip"></div>
    <div id="loading"><div class="spinner"></div><span>Loading...</span></div>
    <div id="minimap"><canvas id="minimapCanvas"></canvas></div>
    <div id="zoomControls">
      <button onclick="zoomIn()" title="Zoom In">+</button>
      <button onclick="zoomOut()" title="Zoom Out">&minus;</button>
      <button onclick="zoomToFit()" title="Zoom to Fit">&#8862;</button>
    </div>
    <div class="mode-indicator" id="modeIndicator">${gd.nodes.length} nodes</div>
  </div>
</div>

<script>
const vscode = acquireVsCodeApi();
const COLORS = ${JSON.stringify(COLORS)};
const EDGE_COLORS = ${JSON.stringify(EDGE_COLORS)};
const DEFAULT_COLOR = "#90a4ae";
const DEFAULT_EDGE_COLOR = "#888";
let nodes = ${nodesJson};
let links = ${edgesJson};
let showLabels = true;
let hasMore = ${initHasMore};
let totalNodes = ${totalNodes};
let totalEdges = ${totalEdges};
let selectedId = null;
let focusedId = null;
let paused = false;
const hiddenTypes = new Set();
const hiddenEdgeTypes = new Set();
const posCache = {};
let nodeById = {};

function escapeHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function idOf(v) { return (v && typeof v === 'object') ? v.id : v; }
function savePositions() { nodes.forEach(n => { if (n.x !== undefined && !isNaN(n.x)) posCache[n.id] = { x: n.x, y: n.y }; }); }
function rebuildIndex() { nodeById = {}; nodes.forEach(n => nodeById[n.id] = n); }

const degree = {};
function recomputeDegree() {
  Object.keys(degree).forEach(k => delete degree[k]);
  nodes.forEach(n => degree[n.id] = 0);
  links.forEach(e => { degree[idOf(e.source)] = (degree[idOf(e.source)] || 0) + 1; degree[idOf(e.target)] = (degree[idOf(e.target)] || 0) + 1; });
  maxDegree = Math.max(1, ...Object.values(degree));
}
let maxDegree = 1;

const width = document.getElementById('graph').clientWidth;
const height = document.getElementById('graph').clientHeight;
const svg = d3.select('#svg').attr('width', width).attr('height', height);
const g = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.02, 20]).on('zoom', (e) => { g.attr('transform', e.transform); updateMinimap(e.transform); });
svg.call(zoom);

const tooltip = document.getElementById('tooltip');
const minimapCanvas = document.getElementById('minimapCanvas');
minimapCanvas.width = 150 * window.devicePixelRatio;
minimapCanvas.height = 100 * window.devicePixelRatio;
const minimapCtx = minimapCanvas.getContext('2d');
minimapCtx.scale(window.devicePixelRatio, window.devicePixelRatio);

let sim, linkGroup, nodeGroup, labelGroup;

function getRadius(d) { return 3 + 11 * Math.sqrt((degree[d.id]||0) / maxDegree); }

function buildGraph() {
  g.selectAll('*').remove();
  linkGroup = g.append('g');
  nodeGroup = g.append('g');
  labelGroup = g.append('g');
  rebuildIndex();
  recomputeDegree();

  linkGroup.selectAll('line').data(links).join('line').attr('class','link')
    .attr('stroke', d => EDGE_COLORS[d.type] || DEFAULT_EDGE_COLOR)
    .attr('stroke-width', 1).attr('stroke-opacity', 0.35);

  nodeGroup.selectAll('circle').data(nodes, d => d.id).join('circle').attr('class', 'node')
    .attr('r', d => getRadius(d))
    .attr('fill', d => COLORS[d.type] || DEFAULT_COLOR)
    .classed('selected', d => d.id === selectedId)
    .call(d3.drag()
      .on('start', (e,d) => { if(!e.active && !paused) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
      .on('end', (e,d) => { if(!e.active && !paused) sim.alphaTarget(0); d.fx=null; d.fy=null; })
    )
    .on('mouseenter', (e,d) => {
      const dg = degree[d.id] || 0;
      tooltip.style.opacity = '1';
      tooltip.innerHTML = '<div class="tt-name">'+escapeHtml(d.name)+'</div><div class="tt-type">['+escapeHtml(d.type)+'] degree: '+dg+'<br>click: details &middot; double-click: expand</div>'+(d.file_path?'<br>'+escapeHtml(d.file_path):'');
      tooltip.style.left = (e.offsetX+12)+'px';
      tooltip.style.top = (e.offsetY-10)+'px';
    })
    .on('mouseleave', () => tooltip.style.opacity = 0)
    .on('click', (e,d) => { e.stopPropagation(); selectNode(d.id); })
    .on('dblclick', (e,d) => { e.stopPropagation(); vscode.postMessage({ command:'expandNode', nodeId:d.id }); });

  const topLabels = [...nodes].sort((a,b) => (degree[b.id]||0) - (degree[a.id]||0)).slice(0, 80);
  const topIds = new Set(topLabels.map(n => n.id));
  labelGroup.selectAll('text').data(nodes.filter(d => topIds.has(d.id)), d => d.id)
    .join('text').attr('class', 'label')
    .attr('dx', d => 3 + getRadius(d))
    .attr('dy', 3)
    .text(d => d.name.length > 25 ? d.name.slice(0,22)+'...' : d.name);

  nodes.forEach(n => { const p = posCache[n.id]; if (p) { n.x = p.x; n.y = p.y; } });

  if (sim) sim.stop();
  sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(40))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(width/2, height/2))
    .force('collision', d3.forceCollide().radius(d => getRadius(d) + 2))
    .alphaDecay(0.02)
    .on('tick', tick);
  if (paused) sim.stop();
  applyFilters();
}

function endX(v) { return (v && typeof v === 'object') ? v.x : (nodeById[v] ? nodeById[v].x : 0); }
function endY(v) { return (v && typeof v === 'object') ? v.y : (nodeById[v] ? nodeById[v].y : 0); }

let tickCount = 0;
function tick() {
  tickCount++;
  if (tickCount % 2 !== 0) return;
  linkGroup.selectAll('line').attr('x1', d=>endX(d.source)).attr('y1', d=>endY(d.source))
    .attr('x2', d=>endX(d.target)).attr('y2', d=>endY(d.target));
  nodeGroup.selectAll('circle').attr('cx', d=>d.x).attr('cy', d=>d.y);
  if (showLabels) labelGroup.selectAll('text').attr('x', d=>d.x).attr('y', d=>d.y);
  updateMinimap(d3.zoomTransform(svg.node()));
}

function updateMinimap(t) {
  if (nodes.length === 0) return;
  minimapCtx.clearRect(0, 0, 150, 100);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    if (n.x === undefined || isNaN(n.x)) return;
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
  });
  if (!isFinite(minX)) return;
  const padding = 10;
  const graphW = (maxX - minX) || 1;
  const graphH = (maxY - minY) || 1;
  const scale = Math.min((150-padding*2)/graphW, (100-padding*2)/graphH);
  nodes.forEach(n => {
    if (n.x === undefined || isNaN(n.x)) return;
    const mx = padding + (n.x - minX) * scale;
    const my = padding + (n.y - minY) * scale;
    minimapCtx.beginPath();
    minimapCtx.arc(mx, my, 1.5, 0, Math.PI * 2);
    minimapCtx.fillStyle = COLORS[n.type] || DEFAULT_COLOR;
    minimapCtx.globalAlpha = 0.6;
    minimapCtx.fill();
  });
  minimapCtx.globalAlpha = 1;
  minimapCtx.strokeStyle = '#888';
  minimapCtx.lineWidth = 1;
  const vpW = (width / t.k) * scale;
  const vpH = (height / t.k) * scale;
  minimapCtx.strokeRect(padding, padding, vpW, vpH);
}

minimapCanvas.addEventListener('click', (e) => {
  if (nodes.length === 0) return;
  const rect = minimapCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => { if(n.x===undefined||isNaN(n.x))return; if(n.x<minX)minX=n.x; if(n.x>maxX)maxX=n.x; if(n.y<minY)minY=n.y; if(n.y>maxY)maxY=n.y; });
  if (!isFinite(minX)) return;
  const padding = 10;
  const scale = Math.min((150-padding*2)/((maxX-minX)||1), (100-padding*2)/((maxY-minY)||1));
  const graphX = (mx-padding)/scale+minX, graphY = (my-padding)/scale+minY;
  const ct = d3.zoomTransform(svg.node());
  svg.transition().duration(300).call(zoom.transform,
    d3.zoomIdentity.translate(width/2,height/2).scale(ct.k).translate(-graphX,-graphY));
});

function updateCounts() {
  document.getElementById('nodeCount').textContent =
    'Showing ' + nodes.length + ' of ' + (totalNodes || nodes.length) + ' nodes \u00b7 ' +
    links.length + ' of ' + (totalEdges || links.length) + ' edges';
  document.getElementById('modeIndicator').textContent = nodes.length + ' nodes';
  refreshLoadBtn();
}

function refreshLoadBtn() {
  const btn = document.getElementById('loadMoreBtn');
  if (!btn) return;
  if (!hasMore) { btn.textContent = 'All loaded ✓'; btn.disabled = true; }
  else { btn.textContent = '+ Load More (' + nodes.length + ' of ' + (totalNodes || nodes.length) + ')'; btn.disabled = false; }
}

// Message handlers
window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'showLoading') document.getElementById('loading').classList.add('active');
  if (msg.command === 'hideLoading') document.getElementById('loading').classList.remove('active');
  if (msg.command === 'appendData' || msg.command === 'replaceData') {
    savePositions();
    nodes = msg.nodes;
    links = msg.edges;
    totalNodes = msg.totalNodes || totalNodes;
    totalEdges = msg.totalEdges || totalEdges;
    hasMore = !!msg.hasMore;
    if (msg.directories) {
      const dirList = document.getElementById('dirList');
      dirList.innerHTML = '<div class="dir-item" onclick="filterDir(\\'\\')" style="font-weight:600"><span class="dir-path">(all)</span><span class="dir-count">'+(msg.totalNodes||nodes.length)+'</span></div>' +
        msg.directories.slice(0,30).map(d => '<div class="dir-item" onclick="filterDir(\\''+escapeHtml(d.path)+'\\')"><span class="dir-path">'+escapeHtml(d.path)+'</span><span class="dir-count">'+d.count+'</span></div>').join('');
    }
    if (selectedId !== null && !nodeById[selectedId] && !msg.nodes.some(n => n.id === selectedId)) { selectedId = null; }
    buildGraph();
    updateCounts();
  }
  if (msg.command === 'impactResult') showImpact(msg.name, msg.items || [], msg.total || 0);
});

function loadMore() {
  if (!hasMore) return;
  const btn = document.getElementById('loadMoreBtn');
  if (btn) { btn.textContent = 'Loading...'; btn.disabled = true; }
  vscode.postMessage({ command:'loadMore' });
}
function resetGraph() { selectedId = null; focusedId = null; vscode.postMessage({ command:'resetGraph' }); }
function runLayout() { if (sim) { paused = false; document.getElementById('pauseBtn').textContent = 'Pause layout'; sim.alpha(1).restart(); } }
function togglePause() {
  if (!sim) return;
  paused = !paused;
  if (paused) sim.stop(); else sim.alpha(0.5).restart();
  document.getElementById('pauseBtn').textContent = paused ? 'Resume layout' : 'Pause layout';
}
function clusterByDir() {
  const dirPos = {};
  const dirs = [...new Set(nodes.map(n => (n.file_path||'').split('/').slice(0,-1).join('/')||'/'))].sort();
  const cols = Math.ceil(Math.sqrt(dirs.length));
  dirs.forEach((d,i) => { dirPos[d] = { x: (i%cols+0.5)*200, y: (Math.floor(i/cols)+0.5)*200 }; });
  nodes.forEach(n => {
    const d = (n.file_path||'').split('/').slice(0,-1).join('/')||'/';
    const p = dirPos[d] || { x: width/2, y: height/2 };
    n.fx = p.x + (Math.random()-0.5)*50; n.fy = p.y + (Math.random()-0.5)*50;
  });
  if (paused) togglePause();
  sim.alpha(1).restart();
  setTimeout(() => nodes.forEach(n => { n.fx=null; n.fy=null; }), 3000);
}
function filterDir(dir) { vscode.postMessage({ command:'filterDir', dir }); }

function selectNode(id) {
  selectedId = id;
  const n = nodeById[id] || nodes.find(x => x.id === id);
  nodeGroup.selectAll('circle').classed('selected', d => d.id === selectedId);
  const panel = document.getElementById('details');
  if (!n) { panel.classList.remove('show'); return; }
  panel.classList.add('show');
  document.getElementById('dName').textContent = n.name;
  document.getElementById('dMeta').textContent = '[' + n.type + '] degree ' + (degree[n.id] || 0) + (n.file_path ? ' · ' + n.file_path : '');
  document.getElementById('impactList').innerHTML = '';
  document.getElementById('clearFocusBtn').style.display = focusedId !== null ? '' : 'none';
}
function selectedNode() { return (nodeById[selectedId] || nodes.find(x => x.id === selectedId)); }
function openSelected() { const n = selectedNode(); if (n && n.file_path) vscode.postMessage({ command:'openFile', path:n.file_path }); }
function expandSelected() { if (selectedId !== null) vscode.postMessage({ command:'expandNode', nodeId:selectedId }); }
function focusSelected() {
  if (selectedId === null) return;
  focusedId = selectedId;
  document.getElementById('clearFocusBtn').style.display = '';
  applyFilters();
}
function clearFocus() { focusedId = null; document.getElementById('clearFocusBtn').style.display = 'none'; applyFilters(); }
function impactSelected() {
  const n = selectedNode();
  if (!n) return;
  document.getElementById('impactList').innerHTML = '<div>Loading impact...</div>';
  vscode.postMessage({ command:'impactNode', name:n.name });
}
function showImpact(name, items, total) {
  const box = document.getElementById('impactList');
  if (!items.length) { box.innerHTML = '<div>No dependents found for ' + escapeHtml(name) + '</div>'; return; }
  box.innerHTML = '<div style="color:var(--vscode-descriptionForeground)">Showing ' + items.length + ' of ' + total + ' dependents:</div>' +
    items.map(r => '<div>[' + escapeHtml(r.type || '?') + '] ' + escapeHtml(r.name || '?') + (r.file_path ? '<br><span style="color:var(--vscode-descriptionForeground)">' + escapeHtml(r.file_path) + '</span>' : '') + '</div>').join('');
}

function neighborSet(id) {
  const s = new Set();
  links.forEach(e => {
    const a = idOf(e.source), b = idOf(e.target);
    if (a === id) s.add(b);
    if (b === id) s.add(a);
  });
  return s;
}
function nodeVisible(n) {
  if (focusedId !== null) {
    if (n.id === focusedId) return true;
    return neighborSet(focusedId).has(n.id);
  }
  return !hiddenTypes.has(n.type);
}
function applyFilters() {
  if (!nodeGroup) return;
  const focusSet = focusedId !== null ? neighborSet(focusedId) : null;
  nodeGroup.selectAll('circle')
    .attr('opacity', d => nodeVisible(d) ? 1 : 0.07)
    .style('pointer-events', d => nodeVisible(d) ? null : 'none');
  linkGroup.selectAll('line').attr('opacity', e => {
    if (hiddenEdgeTypes.has(e.type)) return 0.02;
    const a = idOf(e.source), b = idOf(e.target);
    const na = nodeById[a], nb = nodeById[b];
    if (focusedId !== null) return (a === focusedId || b === focusedId) ? 0.7 : 0.02;
    if ((na && hiddenTypes.has(na.type)) || (nb && hiddenTypes.has(nb.type))) return 0.03;
    return 0.35;
  });
  labelGroup.selectAll('text').attr('opacity', d => nodeVisible(d) ? 1 : 0);
  if (focusSet && focusedId !== null) {
    const n = nodeById[focusedId];
    if (n && n.x !== undefined) {
      const t = d3.zoomIdentity.translate(width/2, height/2).scale(1).translate(-n.x, -n.y);
      svg.transition().duration(400).call(zoom.transform, t);
    }
  }
}
function toggleNType(t, on) { if (on) hiddenTypes.delete(t); else hiddenTypes.add(t); applyFilters(); }
function toggleEType(t, on) { if (on) hiddenEdgeTypes.delete(t); else hiddenEdgeTypes.add(t); applyFilters(); }

let filterTimeout;
function filterNodes(q) {
  if (filterTimeout) clearTimeout(filterTimeout);
  filterTimeout = setTimeout(() => {
    const lower = (q||'').toLowerCase();
    if (!nodeGroup) return;
    nodeGroup.selectAll('circle').attr('opacity', d =>
      (!q || d.name.toLowerCase().includes(lower) || d.type.toLowerCase().includes(lower)) && nodeVisible(d) ? 1 : 0.08);
    linkGroup.selectAll('line').attr('opacity', e => {
      if (!q) return 0.35;
      const a = nodeById[idOf(e.source)], b = nodeById[idOf(e.target)];
      const an = (a ? a.name : '').toLowerCase(), bn = (b ? b.name : '').toLowerCase();
      return (an.includes(lower) || bn.includes(lower)) ? 0.6 : 0.02;
    });
    labelGroup.selectAll('text').attr('opacity', d => !q || d.name.toLowerCase().includes(lower) ? 1 : 0);
  }, 100);
}
function zoomToMatch(q) {
  const lower = (q||'').toLowerCase();
  if (!lower) return;
  const hit = nodes.filter(n => nodeVisible(n) && n.name.toLowerCase().includes(lower))
    .sort((a,b) => (degree[b.id]||0) - (degree[a.id]||0))[0];
  if (!hit || hit.x === undefined) return;
  selectNode(hit.id);
  const t = d3.zoomIdentity.translate(width/2, height/2).scale(1.5).translate(-hit.x, -hit.y);
  svg.transition().duration(400).call(zoom.transform, t);
}

function exportGraph() {
  const clone = document.getElementById('svg').cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%'); bg.setAttribute('fill', '#1e1e1e');
  clone.insertBefore(bg, clone.firstChild);
  const blob = new Blob([clone.outerHTML], { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'cartographer-graph.svg'; a.click();
  URL.revokeObjectURL(url);
}
function toggleLabels() {
  showLabels = !showLabels;
  labelGroup.selectAll('text').attr('display', showLabels ? null : 'none');
}
function zoomIn() { svg.transition().duration(200).call(zoom.scaleBy, 1.5); }
function zoomOut() { svg.transition().duration(200).call(zoom.scaleBy, 0.67); }
function zoomToFit() {
  if (nodes.length === 0) return;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => { if(n.x===undefined||isNaN(n.x))return; if(n.x<minX)minX=n.x; if(n.x>maxX)maxX=n.x; if(n.y<minY)minY=n.y; if(n.y>maxY)maxY=n.y; });
  if (!isFinite(minX)) return;
  const padding = 60;
  const scale = Math.min(width/(maxX-minX+padding*2), height/(maxY-minY+padding*2), 2);
  const t = d3.zoomIdentity.translate(width/2,height/2).scale(scale).translate(-(minX+maxX)/2,-(minY+maxY)/2);
  svg.transition().duration(500).call(zoom.transform, t);
}

rebuildIndex();
recomputeDegree();
buildGraph();
updateCounts();
</script>
</body>
</html>`;
}
