import * as vscode from "vscode";
import { CartographerClient, GraphData } from "./cartographer";

const COLORS: Record<string, string> = {
  file: "#4fc3f7", class: "#ffb74d", function: "#81c784", method: "#ce93d8",
  api_endpoint: "#ef5350", interface: "#4dd0e1", enum: "#ffd54f",
  constant: "#a1887f", variable: "#90a4ae", table: "#26a69a",
  module: "#7986cb", controller: "#ff8a65", service: "#66bb6a",
  directory: "#bdbdbd",
};

const DEFAULT_COLOR = "#90a4ae";

function typeColor(t: string): string {
  return COLORS[t.toLowerCase()] || DEFAULT_COLOR;
}

export function createGraphWebview(client: CartographerClient, entityType?: string, repoName?: string): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    "cartographer.graph", entityType ? `Graph: ${entityType}s` : "Cartographer Graph",
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true },
  );

  const gd = entityType
    ? getGraphDataFiltered(client, entityType, repoName)
    : client.getGraphData(400, repoName);
  panel.webview.html = getHtml(gd, entityType);

  panel.webview.onDidReceiveMessage(msg => {
    if (msg.command === "alert") vscode.window.showErrorMessage(msg.text);
    if (msg.command === "openFile" && msg.path) {
      vscode.workspace.openTextDocument(vscode.Uri.file(msg.path))
        .then(doc => vscode.window.showTextDocument(doc));
    }
  });

  return panel;
}

function getGraphDataFiltered(client: CartographerClient, entityType: string, repoName?: string): GraphData {
  const all = client.getGraphData(300, repoName);
  const filtered = all.nodes.filter(n => n.type === entityType);
  const ids = new Set(filtered.map(n => n.id));
  const edges = all.edges.filter(e => ids.has(e.source) && ids.has(e.target));
  return { nodes: filtered, edges, node_types: { [entityType]: all.node_types[entityType] || filtered.length }, total_nodes: all.total_nodes, total_edges: all.total_edges };
}

function getHtml(gd: GraphData, entityType?: string): string {
  const typeEntries = Object.entries(gd.node_types || {}).sort((a, b) => b[1] - a[1]);
  const typeRows = typeEntries.map(([t, c]) =>
    `<div class="stat"><span>${t}</span><span class="val">${c}</span></div>`
  ).join("\n");

  const nodesJson = JSON.stringify(gd.nodes);
  const edgesJson = JSON.stringify(gd.edges);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cartographer Graph</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:var(--vscode-editor-background); color:var(--vscode-editor-foreground);
         overflow:hidden; height:100vh; }
  #app { display:flex; height:100vh; }
  #sidebar { width:280px; border-right:1px solid var(--vscode-panel-border);
             padding:12px; overflow-y:auto; flex-shrink:0; }
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
  .actions { margin-top:12px; display:flex; flex-direction:column; gap:4px; }
  .actions button { background:var(--vscode-button-background); color:var(--vscode-button-foreground);
                    border:none; padding:6px 12px; border-radius:3px; cursor:pointer; font-size:12px; }
  .actions button:hover { background:var(--vscode-button-hoverBackground); }
  .empty { padding:40px 20px; text-align:center; color:var(--vscode-descriptionForeground); }
  #searchBox { width:100%; padding:6px 8px; border:1px solid var(--vscode-input-border);
               background:var(--vscode-input-background); color:var(--vscode-input-foreground);
               border-radius:3px; font-size:12px; margin-bottom:8px; }
  .link { stroke-opacity:.3; }
  .node { cursor:pointer; stroke:#fff; stroke-width:1.5; }
  .node:hover { stroke-width:3; }
  .label { font-size:10px; pointer-events:none; fill:var(--vscode-editor-foreground);
           text-shadow:0 0 3px var(--vscode-editor-background); }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h3>${entityType ? `${entityType}s Graph` : "Repository Graph"}</h3>
    <div class="node-count">Showing ${gd.nodes.length} of ${gd.total_nodes || gd.nodes.length} nodes · ${gd.edges.length} of ${gd.total_edges || gd.edges.length} edges</div>
    <input id="searchBox" placeholder="Filter nodes..." oninput="filterNodes(this.value)">

    <h3>Node Types</h3>
    ${typeRows || '<div style="font-size:12px;color:var(--vscode-descriptionForeground)">Index a repo first</div>'}

    <h3>Legend</h3>
    <div class="legend">
      ${Object.entries(COLORS).slice(0, 10).map(([t, c]) =>
        `<span class="legend-item"><span class="legend-dot" style="background:${c}"></span>${t}</span>`
      ).join("")}
    </div>

    <div class="actions">
      <button onclick="resetZoom()">Reset View</button>
      <button onclick="runLayout()">Re-layout</button>
    </div>
  </div>
  <div id="graph">
    <svg id="svg"></svg>
    <div id="tooltip"></div>
  </div>
</div>

<script>
const nodes = ${nodesJson};
const links = ${edgesJson};

const width = document.getElementById('graph').clientWidth;
const height = document.getElementById('graph').clientHeight;
const svg = d3.select('#svg')
    .attr('width', width)
    .attr('height', height);

const g = svg.append('g');
const zoom = d3.zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (e) => g.attr('transform', e.transform));
svg.call(zoom);

const tooltip = d3.select('#tooltip');

const link = g.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('class', 'link')
    .attr('stroke', '#888')
    .attr('stroke-width', 1)
    .attr('stroke-opacity', 0.6);

const node = g.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('class', 'node')
    .attr('r', d => Math.max(3, Math.min(12, 30 / Math.sqrt(nodes.length / 5 + 1))))
    .attr('fill', d => ${COLORS_MAP})
    .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) sim.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on('mouseenter', (e, d) => {
        tooltip.style('opacity', 1)
            .html(\`<div class="tt-name">\${d.name}</div><div class="tt-type">[\${d.type}]</div>\${d.file_path ? '<br>' + d.file_path : ''}\`)
            .style('left', (e.offsetX + 12) + 'px')
            .style('top', (e.offsetY - 10) + 'px');
    })
    .on('mouseleave', () => tooltip.style('opacity', 0))
    .on('click', (e, d) => {
        if (d.file_path) {
            e.stopPropagation();
            // Dispatch to VS Code
            window.parent.postMessage({ command: 'openFile', path: d.file_path }, '*');
        }
    });

// Labels (only show for higher-degree nodes)
const label = g.append('g')
    .selectAll('text')
    .data(nodes.filter(d => nodes.length < 80))
    .join('text')
    .attr('class', 'label')
    .attr('dx', d => Math.max(3, Math.min(12, 30 / Math.sqrt(nodes.length / 5 + 1))) + 3)
    .attr('dy', 3)
    .text(d => d.name.length > 20 ? d.name.slice(0, 17) + '...' : d.name);

const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(50))
    .force('charge', d3.forceManyBody().strength(-100))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(8))
    .on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        node
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);
        label
            .attr('x', d => d.x)
            .attr('y', d => d.y);
    });

function resetZoom() {
    svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
}

function runLayout() {
    sim.alpha(1).restart();
}

function filterNodes(q) {
    const lower = q.toLowerCase();
    node.attr('opacity', d => !q || d.name.toLowerCase().includes(lower) || d.type.toLowerCase().includes(lower) ? 1 : 0.1);
    link.attr('opacity', d => {
        if (!q) return 0.3;
        const src = d.source.name?.toLowerCase().includes(lower);
        const tgt = d.target.name?.toLowerCase().includes(lower);
        return src || tgt ? 0.5 : 0.02;
    });
    label.attr('opacity', d => !q || d.name.toLowerCase().includes(lower) ? 1 : 0);
}
</script>
</body>
</html>`;
}

// Need COLORS_MAP for inline script — handle via function
const COLORS_MAP = Object.entries(COLORS).reduce((acc, [k, v]) => {
  acc += `d.type === '${k}' ? '${v}' : `;
  return acc;
}, "") + `'${DEFAULT_COLOR}'`;
