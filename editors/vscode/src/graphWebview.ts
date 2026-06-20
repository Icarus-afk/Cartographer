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

  let currentData: GraphData = { nodes: [], edges: [], node_types: {}, total_nodes: 0, total_edges: 0, directories: [] };
  let allNodes: GraphNode[] = [];
  let allEdges: GraphEdge[] = [];
  let currentOffset = 0;
  let currentDir = "";
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
        all.nodes = filtered;
        all.edges = all.edges.filter(e => ids.has(e.source) && ids.has(e.target));
        return all;
      }
      return await client.getGraphData(limit, repoName, offset, dir, expandId);
    } finally {
      loading = false;
      panel.webview.postMessage({ command: "hideLoading" });
    }
  }

  async function render(): Promise<void> {
    currentData = await loadData(0);
    allNodes = [...currentData.nodes];
    allEdges = [...currentData.edges];

    const gd = {
      ...currentData,
      nodes: allNodes,
      edges: allEdges,
    };

    panel.webview.html = getHtml(gd, entityType, panel.webview, extensionUri);
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
        if (loading) break;
        currentOffset += limit;
        const more = await loadData(currentOffset, currentDir || undefined);
        if (more.nodes.length === 0) {
          vscode.window.showInformationMessage("No more nodes to load.");
          break;
        }
        allNodes = [...allNodes, ...more.nodes.filter(n => !allNodes.some(x => x.id === n.id))];
        allEdges = [...allEdges, ...more.edges.filter(e =>
          !allEdges.some(x => x.source === e.source && x.target === e.target && x.type === e.type)
        )];
        panel.webview.postMessage({
          command: "appendData",
          nodes: allNodes,
          edges: allEdges,
          totalNodes: currentData.total_nodes,
          totalEdges: currentData.total_edges,
        });
        break;
      case "expandNode":
        const nodeData = await loadData(0, undefined, msg.nodeId);
        if (nodeData.nodes.length <= 1) {
          vscode.window.showInformationMessage("No neighbors found for this node.");
          break;
        }
        allNodes = [...allNodes, ...nodeData.nodes.filter(n => !allNodes.some(x => x.id === n.id))];
        allEdges = [...allEdges, ...nodeData.edges.filter(e =>
          !allEdges.some(x => x.source === e.source && x.target === e.target && x.type === e.type)
        )];
        panel.webview.postMessage({
          command: "appendData",
          nodes: allNodes,
          edges: allEdges,
          totalNodes: currentData.total_nodes,
          totalEdges: currentData.total_edges,
        });
        break;
      case "filterDir":
        currentDir = msg.dir || "";
        currentOffset = 0;
        const filtered = await loadData(0, msg.dir || undefined);
        allNodes = [...filtered.nodes];
        allEdges = [...filtered.edges];
        panel.webview.postMessage({
          command: "replaceData",
          nodes: allNodes,
          edges: allEdges,
          directories: filtered.directories,
          totalNodes: currentData.total_nodes,
          totalEdges: currentData.total_edges,
        });
        break;
      case "resetGraph":
        currentOffset = 0;
        currentDir = "";
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
  const typeEntries = Object.entries(gd.node_types || {}).sort((a, b) => b[1] - a[1]);
  const typeRows = typeEntries.map(([t, c]) =>
    `<div class="stat"><span>${t}</span><span class="val">${c}</span></div>`
  ).join("\n");

  const dirs = gd.directories || [];
  const dirRows = dirs.slice(0, 30).map(d =>
    `<div class="dir-item" onclick="filterDir('${esc(d.path)}')">` +
    `<span class="dir-path">${esc(d.path)}</span>` +
    `<span class="dir-count">${d.count}</span></div>`
  ).join("\n");

  const nodesJson = JSON.stringify(gd.nodes);
  const edgesJson = JSON.stringify(gd.edges);
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
  #graph svg { width:100%; height:100%; }
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
    <input id="searchBox" placeholder="Filter nodes..." oninput="filterNodes(this.value)">

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

    <div class="sidebar-section">
      <h3>Node Types</h3>
      ${typeRows || '<div style="font-size:12px;color:var(--vscode-descriptionForeground)">Index a repo first</div>'}
    </div>

    <h3>Actions</h3>
    <div id="statusBar" class="actions">
      <button class="action-btn" onclick="loadMore()">+ Load More</button>
      <button class="action-btn secondary" onclick="resetGraph()">Reset View</button>
      <button class="action-btn secondary" onclick="runLayout()">Re-layout</button>
      <button class="action-btn secondary" onclick="clusterByDir()">Cluster by Dir</button>
      <button class="action-btn secondary" onclick="exportGraph()">Export SVG</button>
      <button class="action-btn secondary" onclick="toggleLabels()">Toggle Labels</button>
      <button class="action-btn secondary" onclick="zoomToFit()">Zoom to Fit</button>
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
    <div class="mode-indicator">${gd.nodes.length} nodes</div>
  </div>
</div>

<script>
const COLORS = ${JSON.stringify(COLORS)};
const EDGE_COLORS = ${JSON.stringify(EDGE_COLORS)};
const DEFAULT_COLOR = "#90a4ae";
const DEFAULT_EDGE_COLOR = "#888";
let nodes = ${nodesJson};
let links = ${edgesJson};
let showLabels = true;

function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

const degree = {};
nodes.forEach(n => degree[n.id] = 0);
links.forEach(e => { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });

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
let maxDegree = Math.max(1, ...Object.values(degree));

function getRadius(d) { return 3 + 11 * Math.sqrt((degree[d.id]||0) / maxDegree); }

function buildGraph() {
  g.selectAll('*').remove();
  linkGroup = g.append('g');
  nodeGroup = g.append('g');
  labelGroup = g.append('g');

  Object.keys(degree).forEach(k => delete degree[k]);
  nodes.forEach(n => degree[n.id] = 0);
  links.forEach(e => { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });
  maxDegree = Math.max(1, ...Object.values(degree));

  linkGroup.selectAll('line').data(links).join('line').attr('class','link')
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
      const dg = degree[d.id] || 0;
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

  const topLabels = [...nodes].sort((a,b) => (degree[b.id]||0) - (degree[a.id]||0)).slice(0, 80);
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
    .on('tick', tick);
}

let tickCount = 0;
function tick() {
  tickCount++;
  if (tickCount % 2 !== 0) return;
  linkGroup.selectAll('line').attr('x1', d=>d.source.x).attr('y1', d=>d.source.y)
    .attr('x2', d=>d.target.x).attr('y2', d=>d.target.y);
  nodeGroup.selectAll('circle').attr('cx', d=>d.x).attr('cy', d=>d.y);
  if (showLabels) labelGroup.selectAll('text').attr('x', d=>d.x).attr('y', d=>d.y);
  updateMinimap(d3.zoomTransform(svg.node()));
}

function updateMinimap(t) {
  if (nodes.length === 0) return;
  minimapCtx.clearRect(0, 0, 150, 100);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
  });
  const padding = 10;
  const graphW = (maxX - minX) || 1;
  const graphH = (maxY - minY) || 1;
  const scale = Math.min((150-padding*2)/graphW, (100-padding*2)/graphH);
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
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => { if(n.x<minX)minX=n.x; if(n.x>maxX)maxX=n.x; if(n.y<minY)minY=n.y; if(n.y>maxY)maxY=n.y; });
  const padding = 10;
  const scale = Math.min((150-padding*2)/((maxX-minX)||1), (100-padding*2)/((maxY-minY)||1));
  const graphX = (mx-padding)/scale+minX, graphY = (my-padding)/scale+minY;
  const ct = d3.zoomTransform(svg.node());
  svg.transition().duration(300).call(zoom.transform,
    d3.zoomIdentity.translate(width/2,height/2).scale(ct.k).translate(-graphX,-graphY));
});

// Message handlers
window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'showLoading') document.getElementById('loading').classList.add('active');
  if (msg.command === 'hideLoading') document.getElementById('loading').classList.remove('active');
  if (msg.command === 'appendData' || msg.command === 'replaceData') {
    nodes = msg.nodes;
    links = msg.edges;
    document.getElementById('nodeCount').textContent =
      'Showing ' + nodes.length + ' of ' + (msg.totalNodes || nodes.length) + ' nodes \u00b7 ' +
      links.length + ' of ' + (msg.totalEdges || links.length) + ' edges';
    if (msg.directories) {
      const dirList = document.getElementById('dirList');
      dirList.innerHTML = '<div class="dir-item" onclick="filterDir(\\'\\')" style="font-weight:600"><span class="dir-path">(all)</span><span class="dir-count">'+(msg.totalNodes||nodes.length)+'</span></div>' +
        msg.directories.slice(0,30).map(d => '<div class="dir-item" onclick="filterDir(\\''+escapeHtml(d.path)+'\\')"><span class="dir-path">'+escapeHtml(d.path)+'</span><span class="dir-count">'+d.count+'</span></div>').join('');
    }
    buildGraph();
  }
});

function loadMore() {
  const btn = document.querySelector('#statusBar button:first-child');
  if (btn) btn.textContent = 'Loading...';
  window.parent.postMessage({ command:'loadMore' }, window.origin);
  setTimeout(() => { if(btn) btn.textContent = '+ Load More'; }, 2000);
}
function resetGraph() { window.parent.postMessage({ command:'resetGraph' }, window.origin); }
function runLayout() { if (sim) sim.alpha(1).restart(); }
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
  sim.alpha(1).restart();
  setTimeout(() => nodes.forEach(n => { n.fx=null; n.fy=null; }), 3000);
}
function filterDir(dir) { window.parent.postMessage({ command:'filterDir', dir }, window.origin); }

let filterTimeout;
function filterNodes(q) {
  if (filterTimeout) clearTimeout(filterTimeout);
  filterTimeout = setTimeout(() => {
    const lower = (q||'').toLowerCase();
    nodeGroup.selectAll('circle').attr('opacity', d =>
      !q || d.name.toLowerCase().includes(lower) || d.type.toLowerCase().includes(lower) ? 1 : 0.08);
    linkGroup.selectAll('line').attr('opacity', d => {
      if (!q) return 0.35;
      return (d.source.name||'').toLowerCase().includes(lower) || (d.target.name||'').toLowerCase().includes(lower) ? 0.6 : 0.02;
    });
    labelGroup.selectAll('text').attr('opacity', d => !q || d.name.toLowerCase().includes(lower) ? 1 : 0);
  }, 100);
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
  nodes.forEach(n => { if(n.x<minX)minX=n.x; if(n.x>maxX)maxX=n.x; if(n.y<minY)minY=n.y; if(n.y>maxY)maxY=n.y; });
  const padding = 60;
  const scale = Math.min(width/(maxX-minX+padding*2), height/(maxY-minY+padding*2), 2);
  const t = d3.zoomIdentity.translate(width/2,height/2).scale(scale).translate(-(minX+maxX)/2,-(minY+maxY)/2);
  svg.transition().duration(500).call(zoom.transform, t);
}

buildGraph();
</script>
</body>
</html>`;
}
