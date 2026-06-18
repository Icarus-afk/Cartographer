import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

export interface ProjectConfig {
  dbPath: string;
  autoReindex: boolean;
  watch: boolean;
  mcpPort: number;
  graphLimit: number;
  maxResults: number;
}

const DEFAULTS: ProjectConfig = {
  dbPath: "",
  autoReindex: true,
  watch: false,
  mcpPort: 0,
  graphLimit: 400,
  maxResults: 40,
};

let _cached: { config: ProjectConfig; root: string } | null = null;
let _watcher: fs.FSWatcher | null = null;

export function readProjectConfig(root: string): ProjectConfig {
  if (_cached && _cached.root === root) return _cached.config;
  try {
    const configPath = path.join(root, ".cartographer", "config.json");
    if (fs.existsSync(configPath)) {
      const raw = JSON.parse(fs.readFileSync(configPath, "utf-8"));
      const cfg: ProjectConfig = { ...DEFAULTS };
      if (typeof raw.dbPath === "string") cfg.dbPath = raw.dbPath;
      if (typeof raw.autoReindex === "boolean") cfg.autoReindex = raw.autoReindex;
      if (typeof raw.watch === "boolean") cfg.watch = raw.watch;
      if (typeof raw.mcpPort === "number") cfg.mcpPort = raw.mcpPort;
      if (typeof raw.graphLimit === "number") cfg.graphLimit = raw.graphLimit;
      if (typeof raw.maxResults === "number") cfg.maxResults = raw.maxResults;
      _cached = { config: cfg, root };
      return cfg;
    }
  } catch {
    // fall through to defaults
  }
  _cached = { config: DEFAULTS, root };
  return DEFAULTS;
}

export function resolveDbPath(projectRoot: string, cfg: ProjectConfig): string {
  if (cfg.dbPath) {
    if (path.isAbsolute(cfg.dbPath)) return cfg.dbPath;
    return path.resolve(projectRoot, cfg.dbPath);
  }
  const cartDir = path.join(projectRoot, ".cartographer");
  if (!fs.existsSync(cartDir)) {
    try { fs.mkdirSync(cartDir, { recursive: true }); } catch { /* ignore */ }
  }
  return path.join(projectRoot, ".cartographer", "data.db");
}

export function watchConfig(root: string, onChange: () => void): vscode.Disposable {
  const configPath = path.join(root, ".cartographer", "config.json");
  if (_watcher) _watcher.close();
  if (fs.existsSync(configPath)) {
    _watcher = fs.watch(configPath, () => {
      _cached = null;
      onChange();
    });
  }
  return {
    dispose: () => {
      if (_watcher) { _watcher.close(); _watcher = null; }
      _cached = null;
    },
  };
}
