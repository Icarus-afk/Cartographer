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

const CANVAS_THRESHOLD = 2000;
const BATCH_SIZE = 100;
const MAX_RENDERED = 5000;

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

  let currentData: GraphData = { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0, directories: [] };
  let allNodes: GraphNode[] = [];
  let allEdges: GraphEdge[] = [];
  let currentOffset = 0;
  let currentDir = "";
  let loading = false;
  let loadingBatch = false;

  async function fetchBatch(offset: number, dir?: string, expandId?: number): Promise<GraphData> {
    try {
      if (entityType) {
        const all = await client.getGraphData(BATCH_SIZE, repoName, offset, dir, expandId);
        const filtered = all.nodes.filter(n => n.type === entityType);
        const ids = new Set(filtered.map(n => n.id));
        all.nodes = filtered;
        all.edges = all.edges.filter(e => ids.has(e.source) && ids.has(e.target));
        return all;
      }
      return await client.getGraphData(BATCH_SIZE, repoName, offset, dir, expandId);
    } catch {
      return { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0, directories: [] };
    }
  }

  function addBatch(data: GraphData): { newNodes: GraphNode[]; newEdges: GraphEdge[] } {
    const existingIds = new Set(allNodes.map(n => n.id));
    const newNodes = data.nodes.filter(n => !existingIds.has(n.id));
    const existingEdgeKeys = new Set(allEdges.map(e => `${e.source}-${e.target}-${e.type}`));
    const newEdges = data.edges.filter(e => !existingEdgeKeys.has(`${e.source}-${e.target}-${e.type}`));
    allNodes.push(...newNodes);
    allEdges.push(...newEdges);
    return { newNodes, newEdges };
  }

  async function streamGraph(): Promise<void> {
    currentOffset = 0;
    allNodes = [];
    allEdges = [];
    currentData = await fetchBatch(0, currentDir || undefined);
    if (currentData.total_nodes !== undefined) {
      currentData.total_nodes = currentData.total_nodes;
    }
    const { newNodes, newEdges } = addBatch(currentData);

    panel.webview.postMessage({
      command: "initGraph",
      nodes: newNodes,
      edges: newEdges,
      totalNodes: currentData.total_nodes || newNodes.length,
      totalEdges: currentData.total_edges || newEdges.length,
      nodeTypes: currentData.node_types,
      directories: currentData.directories,
    });

    const totalWanted = Math.min(currentData.total_nodes || 999999, MAX_RENDERED);
    currentOffset = BATCH_SIZE;

    while (allNodes.length < totalWanted && !loading) {
      loadingBatch = true;
      panel.webview.postMessage({ command: "showStreaming", loaded: allNodes.length, total: currentData.total_nodes || 0 });
      const batch = await fetchBatch(currentOffset, currentDir || undefined);
      if (batch.nodes.length === 0) break;
      const { newNodes: nn, newEdges: ne } = addBatch(batch);
      if (nn.length > 0) {
        panel.webview.postMessage({
          command: "appendBatch",
          nodes: nn,
          edges: ne,
          loaded: allNodes.length,
          total: currentData.total_nodes || 0,
        });
      }
      currentOffset += BATCH_SIZE;
      await new Promise(r => setTimeout(r, 50));
    }

    loadingBatch = false;
    panel.webview.postMessage({
      command: "streamDone",
      loaded: allNodes.length,
      total: currentData.total_nodes || 0,
    });
  }

  panel.webview.onDidReceiveMessage(async msg => {
    switch (msg.command) {
      case "alert":
        vscode.window.showErrorMessage(msg.text);
        break;
      case "openFile":
        if (msg.path) {
          vscode.workspace.openTextDocument(vscode.Uri.file(msg.path))
            .then(doc => vscode.window.showTextDocument(doc));
        }
        break;
      case "loadMore":
        if (loadingBatch) break;
        const batch = await fetchBatch(currentOffset, currentDir || undefined);
        if (batch.nodes.length === 0) {
          vscode.window.showInformationMessage("All nodes loaded.");
          break;
        }
        const { newNodes, newEdges } = addBatch(batch);
        currentOffset += BATCH_SIZE;
        panel.webview.postMessage({
          command: "appendBatch",
          nodes: newNodes,
          edges: newEdges,
          loaded: allNodes.length,
          total: currentData.total_nodes || 0,
        });
        break;
      case "expandNode":
        const nodeData = await fetchBatch(0, undefined, msg.nodeId);
        if (nodeData.nodes.length <= 1) {
          vscode.window.showInformationMessage("No neighbors found.");
          break;
        }
        const { newNodes: enn, newEdges: ene } = addBatch(nodeData);
        panel.webview.postMessage({
          command: "appendBatch",
          nodes: enn,
          edges: ene,
          loaded: allNodes.length,
          total: currentData.total_nodes || 0,
        });
        break;
      case "filterDir":
        currentDir = msg.dir || "";
        loading = true;
        await streamGraph();
        loading = false;
        break;
      case "resetGraph":
        currentDir = "";
        loading = true;
        await streamGraph();
        loading = false;
        break;
    }
  });

  streamGraph();
  return panel;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getHtml(
  entityType: string | undefined,
  webview: vscode.Webview, extensionUri: vscode.Uri,
): string {
  const d3Uri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, "resources", "d3.v7.min.js"));

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
  #sidebar { width:280px; border-right:1px solid var(--vscode-panel-border);
             padding:12px; overflow-y:auto; flex-shrink:0; display:flex; flex-direction:column; }
  #graph { flex:1; position:relative; }
  #graph svg, #graph canvas { width:100%; height:100%; display:block; }
  h3 { font-size:11px; text-transform:uppercase; letter-spacing:.5px;
       color:var(--vscode-descriptionForeground); margin:12px 0 8px; }
  h3:first-child { margin-top:0; }
  .stat { display:flex; justify-content:space-between; padding:3px 0; font-size:13px; }
  .stat .val { color:var(--vscode-textLink-foreground); font-weight:600; }
  #tooltip { position:absolute; padding:8px 12px; background:var(--vscode-editorWidget-background);
             border:1px solid var(--vscode-panel-border); border-radius:4px; font-size:12px;
             pointer-events:none; opacity:0; transition:opacity .15s; z-index:100;
             max-width:300px; box-shadow:0 2px 8px rgba(0,0,0,.15); }
  #tooltip .tt-name { font-weight:600; }
  #tooltip .tt-type { color:var(--vscode-descriptionForeground); font-size:11px; }
  .node-count { font-size:11px; color:var(--vscode-descriptionForeground); margin-bottom:8px; }
  .actions { display:flex; flex-direction:column; gap:4px; }
  .actions button, .actions .action-btn { background:var(--vscode-button-background);
    color:var(--vscode-button-foreground); border:none; padding:6px 12px; border-radius:3px;
    cursor:pointer; font-size:12px; text-align:center; }
  .actions button:hover, .actions .action-btn:hover { background:var(--vscode-button-hoverBackground); }
  .actions .action-btn.secondary { background:var(--vscode-button-secondaryBackground);
    color:var(--vscode-button-secondaryForeground); }
  #searchBox { width:100%; padding:6px 8px; border:1px solid var(--vscode-input-border);
               background:var(--vscode-input-background); color:var(--vscode-input-foreground);
               border-radius:3px; font-size:12px; margin-bottom:8px; }
  .link { stroke-opacity:.4; }
  .node { cursor:pointer; stroke:#fff; stroke-width:1.5; }
  .node:hover { stroke-width:3; }
  .label { font-size:10px; pointer-events:none; fill:var(--vscode-editor-foreground);
           text-shadow:0 0 3px var(--vscode-editor-background); }
  #statusBar { display:flex; gap:4px; margin:8px 0; }
  #statusBar .action-btn { flex:1; }
  .dir-list { max-height:200px; overflow-y:auto; margin-bottom:8px;
              border:1px solid var(--vscode-panel-border); border-radius:3px; }
  .dir-item { display:flex; justify-content:space-between; padding:3px 6px; font-size:11px;
              cursor:pointer; border-bottom:1px solid var(--vscode-panel-border); }
  .dir-item:hover { background:var(--vscode-list-hoverBackground); }
  .dir-item:last-child { border-bottom:none; }
  .dir-path { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; }
  .dir-count { color:var(--vscode-textLink-foreground); margin-left:6px; }
  .sidebar-section { margin-bottom:8px; }
  #loading { display:none; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
             padding:12px 24px; background:var(--vscode-editorWidget-background);
             border:1px solid var(--vscode-panel-border); border-radius:6px; font-size:13px;
             z-index:200; box-shadow:0 2px 8px rgba(0,0,0,.2); }
  #loading.active { display:flex; align-items:center; gap:8px; }
  .spinner { width:16px; height:16px; border:2px solid var(--vscode-descriptionForeground);
             border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  #streamStatus { position:absolute; top:12px; left:50%; transform:translateX(-50%);
    padding:6px 16px; background:var(--vscode-badge-background); color:var(--vscode-badge-foreground);
    border-radius:12px; font-size:12px; z-index:50; transition:opacity .3s; pointer-events:none; }
  #streamStatus.done { opacity:0; }
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
    <div class="node-count" id="nodeCount">Loading...</div>
    <input id="searchBox" placeholder="Filter nodes..." oninput="filterNodes(this.value)">

    <div class="sidebar-section">
      <h3>Directories</h3>
      <div class="dir-list" id="dirList"></div>
    </div>

    <div class="sidebar-section">
      <h3>Node Types</h3>
      <div id="typeBreakdown"></div>
    </div>

    <h3>Actions</h3>
    <div id="statusBar" class="actions">
      <button class="action-btn" onclick="loadMore()">+ Load More</button>
      <button class="action-btn secondary" onclick="resetGraph()">Reset View</button>
      <button class="action-btn secondary" onclick="runLayout()">Re-layout</button>
      <button class="action-btn secondary" onclick="clusterByDir()">Cluster by Dir</button>
      <button class="action-btn secondary" onclick="exportGraph()">Export PNG</button>
      <button class="action-btn secondary" onclick="toggleLabels()">Toggle Labels</button>
      <button class="action-btn secondary" onclick="zoomToFit()">Zoom to Fit</button>
    </div>
  </div>
  <div id="graph">
    <svg id="svg"></svg>
    <div id="tooltip"></div>
    <div id="loading"><div class="spinner"></div><span>Loading...</span></div>
    <div id="streamStatus"></div>
    <div id="minimap"><canvas id="minimapCanvas"></canvas></div>
    <div id="zoomControls">
      <button onclick="zoomIn()" title="Zoom In">+</button>
      <button onclick="zoomOut()" title="Zoom Out">&minus;</button>
      <button onclick="zoomToFit()" title="Zoom to Fit">&#8862;</button>
    </div>
  </div>
</div>

<script>
const COLORS = ${JSON.stringify(COLORS)};
const EDGE_COLORS = ${JSON.stringify(EDGE_COLORS)};
const DEFAULT_COLOR = "#90a4ae";
const DEFAULT_EDGE_COLOR = "#888";
let nodes = [];
let links = [];
let showLabels = true;
let sim, linkGroup, nodeGroup, labelGroup, svg, g, zoom;
let minimapCanvas, minimapCtx;
let nodeById = {};

const graphEl = document.getElementById('graph');
const width = graphEl.clientWidth;
const height = graphEl.clientHeight;

svg = d3.select('#svg').attr('width', width).attr('height', height);
g = svg.append('g');
zoom = d3.zoom().scaleExtent([0.02, 20]).on('zoom', (e) => {
  g.attr('transform', e.transform);
  updateMinimap(e.transform);
});
svg.call(zoom);

minimapCanvas = document.getElementById('minimapCanvas');
minimapCanvas.width = 150 * window.devicePixelRatio;
minimapCanvas.height = 100 * window.devicePixelRatio;
minimapCtx = minimapCanvas.getContext('2d');
minimapCtx.scale(window.devicePixelRatio, window.devicePixelRatio);

const tooltip = document.getElementById('tooltip');
const streamStatus = document.getElementById('streamStatus');

function getRadius(d) {
  const deg = nodeById[d.id]?.degree || 0;
  const maxDeg = nodeById._maxDegree || 1;
  return 3 + 11 * Math.sqrt(deg / maxDeg);
}

function recomputeDegree() {
  const degree = {};
  nodes.forEach(n => degree[n.id] = 0);
  links.forEach(e => {
    degree[e.source] = (degree[e.source] || 0) + 1;
    degree[e.target] = (degree[e.target] || 0) + 1;
  });
  let maxDeg = 1;
  nodes.forEach(n => {
    const d = degree[n.id] || 0;
    if (n.id in nodeById) nodeById[n.id].degree = d;
    if (d > maxDeg) maxDeg = d;
  });
  nodeById._maxDegree = maxDeg;
}

function buildGraph() {
  g.selectAll('.link-layer,.node-layer,.label-layer').remove();
  linkGroup = g.append('g').attr('class', 'link-layer');
  nodeGroup = g.append('g').attr('class', 'node-layer');
  labelGroup = g.append('g').attr('class', 'label-layer');

  recomputeDegree();

  linkGroup.selectAll('line').data(links).join('line').attr('class', 'link')
    .attr('stroke', d => EDGE_COLORS[d.type] || DEFAULT_EDGE_COLOR)
    .attr('stroke-width', 1).attr('stroke-opacity', 0.35);

  nodeGroup.selectAll('circle').data(nodes).join('circle').attr('class', 'node')
    .attr('r', d => getRadius(d))
    .attr('fill', d => COLORS[d.type] || DEFAULT_COLOR)
    .call(d3.drag()
      .on('start', (e,d) => { if(!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
      .on('end', (e,d) => { if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; })
    )
    .on('mouseenter', (e,d) => {
      const dg = nodeById[d.id]?.degree || 0;
      tooltip.style.opacity = '1';
      tooltip.innerHTML = '<div class="tt-name">'+escapeHtml(d.name)+'</div><div class="tt-type">['+d.type+'] degree: '+dg+'</div>'+(d.file_path?'<br>'+escapeHtml(d.file_path):'');
      tooltip.style.left = (e.offsetX+12)+'px';
      tooltip.style.top = (e.offsetY-10)+'px';
    })
    .on('mouseleave', () => tooltip.style.opacity = 0)
    .on('click', (e,d) => {
      e.stopPropagation();
      if (d.file_path) window.parent.postMessage({ command:'openFile', path:d.file_path }, window.origin);
    })
    .on('dblclick', (e,d) => {
      e.stopPropagation();
      window.parent.postMessage({ command:'expandNode', nodeId:d.id }, window.origin);
    });

  const topLabels = [...nodes].sort((a,b) => (nodeById[b.id]?.degree||0) - (nodeById[a.id]?.degree||0)).slice(0, 80);
  const topIds = new Set(topLabels.map(n => n.id));

  labelGroup.selectAll('text').data(nodes.filter(d => topIds.has(d.id)))
    .join('text').attr('class', 'label')
    .attr('dx', d => 3 + getRadius(d))
    .attr('dy', 3)
    .text(d => d.name.length > 25 ? d.name.slice(0,22)+'...' : d.name);

  if (sim) sim.stop();
  sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(40))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(width/2, height/2))
    .force('collision', d3.forceCollide().radius(d => getRadius(d) + 2))
    .alphaDecay(0.02)
    .on('tick', tickSVG);
}

let tickCount = 0;
function tickSVG() {
  tickCount++;
  if (tickCount % 2 !== 0) return;
  linkGroup.selectAll('line').attr('x1', d=>d.source.x).attr('y1', d=>d.source.y)
    .attr('x2', d=>d.target.x).attr('y2', d=>d.target.y);
  nodeGroup.selectAll('circle').attr('cx', d=>d.x).attr('cy', d=>d.y);
  if (showLabels) {
    labelGroup.selectAll('text').attr('x', d=>d.x).attr('y', d=>d.y);
  }
}

function updateMinimap(t) {
  if (!minimapCtx || nodes.length === 0) return;
  minimapCtx.clearRect(0, 0, 150, 100);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  });
  const padding = 10;
  const graphW = (maxX - minX) || 1;
  const graphH = (maxY - minY) || 1;
  const scaleX = (150 - padding*2) / graphW;
  const scaleY = (100 - padding*2) / graphH;
  const scale = Math.min(scaleX, scaleY);
  nodes.forEach(n => {
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
  const vpLeft = (-t.x / t.k - minX) * scale + padding;
  const vpTop = (-t.y / t.k - minY) * scale + padding;
  const vpW = (width / t.k) * scale;
  const vpH = (height / t.k) * scale;
  minimapCtx.strokeRect(vpLeft, vpTop, vpW, vpH);
}

minimapCanvas.addEventListener('click', (e) => {
  if (nodes.length === 0) return;
  const rect = minimapCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
  });
  const padding = 10;
  const graphW = (maxX - minX) || 1;
  const graphH = (maxY - minY) || 1;
  const scale = Math.min((150-padding*2)/graphW, (100-padding*2)/graphH);
  const graphX = (mx - padding) / scale + minX;
  const graphY = (my - padding) / scale + minY;
  const ct = d3.zoomTransform(svg.node());
  const newT = d3.zoomIdentity.translate(width/2, height/2).scale(ct.k).translate(-graphX, -graphY);
  svg.transition().duration(300).call(zoom.transform, newT);
});

function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// Message handlers
window.addEventListener('message', event => {
  const msg = event.data;

  if (msg.command === 'showLoading') {
    document.getElementById('loading').classList.add('active');
  }
  if (msg.command === 'hideLoading') {
    document.getElementById('loading').classList.remove('active');
  }

  if (msg.command === 'initGraph') {
    document.getElementById('loading').classList.remove('active');
    nodes = [];
    links = [];
    nodeById = {};
    msg.nodes.forEach(n => { nodeById[n.id] = n; nodes.push(n); });
    msg.edges.forEach(e => links.push(e));

    updateTypeBreakdown(msg.nodeTypes || {});
    updateDirList(msg.directories || []);
    updateNodeCount(msg.loaded, msg.total);
    buildGraph();
  }

  if (msg.command === 'appendBatch') {
    msg.nodes.forEach(n => { nodeById[n.id] = n; nodes.push(n); });
    msg.edges.forEach(e => links.push(e));
    recomputeDegree();

    linkGroup.selectAll('line').data(links).join('line').attr('class', 'link')
      .attr('stroke', d => EDGE_COLORS[d.type] || DEFAULT_EDGE_COLOR)
      .attr('stroke-width', 1).attr('stroke-opacity', 0.35);

    nodeGroup.selectAll('circle').data(nodes).join('circle').attr('class', 'node')
      .attr('r', d => getRadius(d))
      .attr('fill', d => COLORS[d.type] || DEFAULT_COLOR)
      .call(d3.drag()
        .on('start', (e,d) => { if(!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; })
        .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
        .on('end', (e,d) => { if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; })
      )
      .on('mouseenter', (e,d) => {
        const dg = nodeById[d.id]?.degree || 0;
        tooltip.style.opacity = '1';
        tooltip.innerHTML = '<div class="tt-name">'+escapeHtml(d.name)+'</div><div class="tt-type">['+d.type+'] degree: '+dg+'</div>'+(d.file_path?'<br>'+escapeHtml(d.file_path):'');
        tooltip.style.left = (e.offsetX+12)+'px';
        tooltip.style.top = (e.offsetY-10)+'px';
      })
      .on('mouseleave', () => tooltip.style.opacity = 0)
      .on('click', (e,d) => {
        e.stopPropagation();
        if (d.file_path) window.parent.postMessage({ command:'openFile', path:d.file_path }, window.origin);
      })
      .on('dblclick', (e,d) => {
        e.stopPropagation();
        window.parent.postMessage({ command:'expandNode', nodeId:d.id }, window.origin);
      });

    if (showLabels) {
      const topLabels = [...nodes].sort((a,b) => (nodeById[b.id]?.degree||0) - (nodeById[a.id]?.degree||0)).slice(0, 80);
      const topIds = new Set(topLabels.map(n => n.id));
      labelGroup.selectAll('text').data(nodes.filter(d => topIds.has(d.id)))
        .join('text').attr('class', 'label')
        .attr('dx', d => 3 + getRadius(d)).attr('dy', 3)
        .text(d => d.name.length > 25 ? d.name.slice(0,22)+'...' : d.name);
    }

    sim.nodes(nodes);
    sim.force('link').links(links);
    sim.alpha(0.3).restart();
    updateNodeCount(msg.loaded, msg.total);
  }

  if (msg.command === 'showStreaming') {
    streamStatus.textContent = 'Loading... ' + msg.loaded + ' / ' + msg.total + ' nodes';
    streamStatus.classList.remove('done');
  }

  if (msg.command === 'streamDone') {
    streamStatus.textContent = msg.loaded + ' nodes loaded';
    streamStatus.classList.add('done');
    updateNodeCount(msg.loaded, msg.total);
  }
});

function updateNodeCount(loaded, total) {
  document.getElementById('nodeCount').textContent =
    'Showing ' + loaded + ' of ' + (total || loaded) + ' nodes \u00b7 ' +
    links.length + ' edges';
}

function updateTypeBreakdown(types) {
  const el = document.getElementById('typeBreakdown');
  const sorted = Object.entries(types).sort((a,b) => b[1] - a[1]);
  el.innerHTML = sorted.map(([t, c]) =>
    '<div class="stat"><span>'+t+'</span><span class="val">'+c+'</span></div>'
  ).join('');
}

function updateDirList(dirs) {
  const el = document.getElementById('dirList');
  const total = nodes.length;
  el.innerHTML = '<div class="dir-item" onclick="filterDir(\\'\\')" style="font-weight:600"><span class="dir-path">(all)</span><span class="dir-count">'+total+'</span></div>' +
    dirs.slice(0, 30).map(d =>
      '<div class="dir-item" onclick="filterDir(\\''+escapeHtml(d.path)+'\\')"><span class="dir-path">'+escapeHtml(d.path)+'</span><span class="dir-count">'+d.count+'</span></div>'
    ).join('');
}

function loadMore() {
  window.parent.postMessage({ command:'loadMore' }, window.origin);
}
function resetGraph() {
  window.parent.postMessage({ command:'resetGraph' }, window.origin);
}
function runLayout() {
  if (sim) sim.alpha(1).restart();
}
function clusterByDir() {
  const dirPos = {};
  const dirs = [...new Set(nodes.map(n => (n.file_path||'').split('/').slice(0,-1).join('/')||'/'))].sort();
  const cols = Math.ceil(Math.sqrt(dirs.length));
  dirs.forEach((d,i) => { dirPos[d] = { x: (i%cols+0.5)*200, y: (Math.floor(i/cols)+0.5)*200 }; });
  nodes.forEach(n => {
    const d = (n.file_path||'').split('/').slice(0,-1).join('/')||'/';
    const p = dirPos[d] || { x: width/2, y: height/2 };
    n.fx = p.x + (Math.random()-0.5)*50;
    n.fy = p.y + (Math.random()-0.5)*50;
  });
  sim.alpha(1).restart();
  setTimeout(() => nodes.forEach(n => { n.fx=null; n.fy=null; }), 3000);
}
function filterDir(dir) {
  window.parent.postMessage({ command:'filterDir', dir }, window.origin);
}

let filterTimeout;
function filterNodes(q) {
  if (filterTimeout) clearTimeout(filterTimeout);
  filterTimeout = setTimeout(() => {
    const lower = (q||'').toLowerCase();
    nodeGroup.selectAll('circle').attr('opacity', d =>
      !q || d.name.toLowerCase().includes(lower) || d.type.toLowerCase().includes(lower) ? 1 : 0.08);
    linkGroup.selectAll('line').attr('opacity', d => {
      if (!q) return 0.35;
      const src = typeof d.source === 'object' ? d.source.name : '';
      const tgt = typeof d.target === 'object' ? d.target.name : '';
      return src.toLowerCase().includes(lower) || tgt.toLowerCase().includes(lower) ? 0.6 : 0.02;
    });
    labelGroup.selectAll('text').attr('opacity', d =>
      !q || d.name.toLowerCase().includes(lower) ? 1 : 0);
  }, 100);
}

function exportGraph() {
  const svgEl = document.getElementById('svg');
  const clone = svgEl.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%');
  bg.setAttribute('fill', '#1e1e1e');
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
  nodes.forEach(n => {
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
  });
  const padding = 60;
  const scale = Math.min(width / (maxX-minX+padding*2), height / (maxY-minY+padding*2), 2);
  const cx = (minX+maxX)/2, cy = (minY+maxY)/2;
  const t = d3.zoomIdentity.translate(width/2, height/2).scale(scale).translate(-cx, -cy);
  svg.transition().duration(500).call(zoom.transform, t);
}
</script>
</body>
</html>`;
}
