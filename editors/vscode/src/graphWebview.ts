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
  CALLS: "#ef5350", REFERENCES: "#a1887f",
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

  // Directory tree
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
  .legend { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
  .legend-item { display:flex; align-items:center; gap:3px; font-size:10px; }
  .legend-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .actions { display:flex; flex-direction:column; gap:4px; }
  .actions button, .actions .action-btn { background:var(--vscode-button-background);
    color:var(--vscode-button-foreground); border:none; padding:6px 12px; border-radius:3px;
    cursor:pointer; font-size:12px; text-align:center; }
  .actions button:hover, .actions .action-btn:hover { background:var(--vscode-button-hoverBackground); }
  .actions .action-btn.secondary { background:var(--vscode-button-secondaryBackground);
    color:var(--vscode-button-secondaryForeground); }
  .empty { padding:40px 20px; text-align:center; color:var(--vscode-descriptionForeground); }
  #searchBox { width:100%; padding:6px 8px; border:1px solid var(--vscode-input-border);
               background:var(--vscode-input-background); color:var(--vscode-input-foreground);
               border-radius:3px; font-size:12px; margin-bottom:8px; }
  .link { stroke-opacity:.4; }
  .node { cursor:pointer; stroke:#fff; stroke-width:1.5; transition:opacity .2s; }
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
    </div>
  </div>
  <div id="graph">
    <svg id="svg"></svg>
    <div id="tooltip"></div>
    <div id="loading">Loading...</div>
  </div>
</div>

<script>
const COLORS = ${JSON.stringify(COLORS)};
const EDGE_COLORS = ${JSON.stringify(EDGE_COLORS)};
const DEFAULT_COLOR = "#90a4ae";
const DEFAULT_EDGE_COLOR = "#888";
let nodes = ${nodesJson};
let links = ${edgesJson};

function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// Build degree index
const degree = {};
nodes.forEach(n => degree[n.id] = 0);
links.forEach(e => { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });

const width = document.getElementById('graph').clientWidth;
const height = document.getElementById('graph').clientHeight;
const svg = d3.select('#svg').attr('width', width).attr('height', height);

const g = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.05, 15]).on('zoom', (e) => g.attr('transform', e.transform));
svg.call(zoom);

const tooltip = d3.select('#tooltip');
let sim, linkGroup, nodeGroup, labelGroup;

function buildGraph() {
  // Remove old elements
  g.selectAll('*').remove();
  linkGroup = g.append('g');
  nodeGroup = g.append('g');
  labelGroup = g.append('g');

  // Recompute degree
  Object.keys(degree).forEach(k => delete degree[k]);
  nodes.forEach(n => degree[n.id] = 0);
  links.forEach(e => { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });

  renderLinks();
  renderNodes();

  const maxDegree = Math.max(1, ...Object.values(degree));

  const topLabels = [...nodes].sort((a,b) => (degree[b.id]||0) - (degree[a.id]||0)).slice(0, 50);
  const topIds = new Set(topLabels.map(n => n.id));

  labelGroup.selectAll('text').data(nodes.filter(d => topIds.has(d.id)))
    .join('text').attr('class', 'label')
    .attr('dx', d => 3 + 3 + 11 * Math.sqrt((degree[d.id]||0) / maxDegree))
    .attr('dy', 3)
    .text(d => d.name.length > 25 ? d.name.slice(0,22)+'...' : d.name);

  if (sim) sim.stop();
  sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(40))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(width/2, height/2))
    .force('collision', d3.forceCollide().radius(d => 3 + 11 * Math.sqrt((degree[d.id]||0) / maxDegree)))
    .on('tick', () => {
      linkGroup.selectAll('line').attr('x1', d=>d.source.x).attr('y1', d=>d.source.y)
        .attr('x2', d=>d.target.x).attr('y2', d=>d.target.y);
      nodeGroup.selectAll('circle').attr('cx', d=>d.x).attr('cy', d=>d.y);
      labelGroup.selectAll('text').attr('x', d=>d.x).attr('y', d=>d.y);
    });
}

function renderLinks() {
  linkGroup.selectAll('line').data(links).join('line').attr('class','link')
    .attr('stroke', d => EDGE_COLORS[d.type] || DEFAULT_EDGE_COLOR)
    .attr('stroke-width', 1).attr('stroke-opacity', 0.35);
}

function renderNodes() {
  const maxDegree = Math.max(1, ...Object.values(degree));
  nodeGroup.selectAll('circle').data(nodes).join('circle').attr('class', 'node')
    .attr('r', d => 3 + 11 * Math.sqrt((degree[d.id]||0) / maxDegree))
    .attr('fill', d => COLORS[d.type] || DEFAULT_COLOR)
    .call(d3.drag()
      .on('start', (e,d) => { if(!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
      .on('end', (e,d) => { if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; })
    )
    .on('mouseenter', (e,d) => {
      const dg = degree[d.id] || 0;
      tooltip.style('opacity',1)
        .html('<div class="tt-name">'+d.name+'</div><div class="tt-type">['+d.type+'] degree: '+dg+'</div>'+(d.file_path?'<br>'+d.file_path:''))
        .style('left',(e.offsetX+12)+'px').style('top',(e.offsetY-10)+'px');
    })
    .on('mouseleave', () => tooltip.style('opacity',0))
    .on('click', (e,d) => {
      e.stopPropagation();
      if (d.file_path) {
        window.parent.postMessage({ command:'openFile', path:d.file_path }, window.origin);
      }
    })
    .on('dblclick', (e,d) => {
      e.stopPropagation();
      window.parent.postMessage({ command:'expandNode', nodeId:d.id }, window.origin);
    });
}

// ── Message handlers ────────────────────────────────────────────────────

window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'appendData') {
    nodes = msg.nodes;
    links = msg.edges;
    document.getElementById('nodeCount').textContent =
      'Showing ' + nodes.length + ' of ' + (msg.totalNodes || nodes.length) + ' nodes · ' +
      links.length + ' of ' + (msg.totalEdges || links.length) + ' edges';
    buildGraph();
  }
  if (msg.command === 'replaceData') {
    nodes = msg.nodes;
    links = msg.edges;
    document.getElementById('nodeCount').textContent =
      'Showing ' + nodes.length + ' of ' + (msg.totalNodes || nodes.length) + ' nodes · ' +
      links.length + ' of ' + (msg.totalEdges || links.length) + ' edges';
    buildGraph();
  }
});

// ── UI actions ──────────────────────────────────────────────────────────

function loadMore() {
  const btn = document.querySelector('#statusBar button:first-child');
  if (btn) btn.textContent = 'Loading...';
  window.parent.postMessage({ command:'loadMore' }, window.origin);
  setTimeout(() => { if(btn) btn.textContent = '+ Load More'; }, 1000);
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
  dirs.forEach((d,i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    dirPos[d] = { x: (col+0.5)*200, y: (row+0.5)*200 };
  });
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
      const src = d.source.name?.toLowerCase().includes(lower);
      const tgt = d.target.name?.toLowerCase().includes(lower);
      return src || tgt ? 0.6 : 0.02;
    });
    labelGroup.selectAll('text').attr('opacity', d =>
      !q || d.name.toLowerCase().includes(lower) ? 1 : 0);
  }, 100);
}

buildGraph();
</script>
</body>
</html>`;
}
