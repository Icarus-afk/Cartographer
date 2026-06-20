import { ChildProcess, spawn } from "child_process";
import * as vscode from "vscode";

interface McpRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface McpResponse {
  jsonrpc: "2.0";
  id: number;
  result?: { content?: { type: string; text: string }[]; [key: string]: unknown };
  error?: { code: number; message: string; data?: unknown };
}

export class McpClient implements vscode.Disposable {
  private proc: ChildProcess | null = null;
  private reqId = 0;
  private pending = new Map<number, { resolve: (v: string) => void; reject: (e: Error) => void }>();
  private buffer = "";
  private _ready: Promise<void>;
  private _readyResolve!: () => void;
  private _readyReject!: (e: Error) => void;
  private output: vscode.OutputChannel;
  private _disposed = false;

  constructor(output: vscode.OutputChannel) {
    this.output = output;
    this._ready = new Promise((resolve, reject) => {
      this._readyResolve = resolve;
      this._readyReject = reject;
    });
  }

  get ready(): Promise<void> {
    return this._ready;
  }

  async start(bin: string, args: string[]): Promise<void> {
    const binStr = `${bin} ${args.join(" ")}`;
    this.output.appendLine(`MCP: starting ${binStr}`);
    this.proc = spawn(bin, args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    this.proc.stdout!.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString("utf-8");
      this.processMessages();
    });

    this.proc.stderr!.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf-8").trim();
      if (text) this.output.appendLine(`MCP: ${text}`);
    });

    this.proc.on("error", (err) => {
      this.output.appendLine(`MCP error: ${err.message}`);
      this._readyReject(err);
      this.rejectAll(err);
    });

    this.proc.on("exit", (code) => {
      this.output.appendLine(`MCP exited (code ${code})`);
      if (!this._disposed) {
        this.rejectAll(new Error(`MCP exited with code ${code}`));
      }
    });

    try {
      await this.initialize();
      this._readyResolve();
    } catch (e) {
      this._readyReject(e as Error);
      throw e;
    }
  }

  private processMessages(): void {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg: McpResponse = JSON.parse(line);
        if (msg.id != null) {
          const pending = this.pending.get(msg.id);
          if (pending) {
            this.pending.delete(msg.id);
            if (msg.error) {
              pending.reject(new Error(`${msg.error.message} (code ${msg.error.code})`));
            } else if (msg.result) {
              const content = msg.result.content;
              if (content && content.length > 0) {
                pending.resolve(content.map(c => c.text).join("\n"));
              } else {
                pending.resolve(JSON.stringify(msg.result));
              }
            } else {
              pending.resolve("");
            }
          }
        }
      } catch (e) {
        this.output.appendLine(`MCP parse error: ${e} line: ${line}`);
      }
    }
  }

  private send(method: string, params?: Record<string, unknown>, timeoutMs = 30_000): Promise<string> {
    return new Promise((resolve, reject) => {
      const id = ++this.reqId;
      const req: McpRequest = { jsonrpc: "2.0", id, method };
      if (params) req.params = params;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`MCP ${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      const raw = JSON.stringify(req) + "\n";
      this.proc?.stdin?.write(raw);
    });
  }

  private sendNotification(method: string): void {
    const raw = JSON.stringify({ jsonrpc: "2.0", method }) + "\n";
    this.proc?.stdin?.write(raw);
  }

  private async initialize(): Promise<void> {
    const supportedVersions = ["2025-03-26", "2024-11-05"];
    const resp = await this.send("initialize", {
      protocolVersion: supportedVersions[0],
      capabilities: { tools: {} },
      clientInfo: { name: "cartographer-vscode", version: "0.1.0" },
    }, 10_000);
    const parsed = JSON.parse(resp);
    const serverVersion = parsed.protocolVersion || supportedVersions[0];
    this.sendNotification("notifications/initialized");
  }

  async callTool(name: string, args?: Record<string, unknown>, timeoutMs = 30_000): Promise<string> {
    await this._ready;
    return this.send("tools/call", { name, arguments: args || {} }, timeoutMs);
  }

  async dispose(): Promise<void> {
    this._disposed = true;
    try {
      await this.send("shutdown");
    } catch { /* ignore */ }
    this.rejectAll(new Error("MCP client disposed"));
    if (this.proc) {
      this.proc.kill("SIGTERM");
      setTimeout(() => this.proc?.kill("SIGKILL"), 2000);
      this.proc = null;
    }
  }

  private rejectAll(err: Error): void {
    for (const [, p] of this.pending) {
      p.reject(err);
    }
    this.pending.clear();
  }

  get running(): boolean {
    return this.proc !== null && this.proc.exitCode === null;
  }
}
