import { expect, test as base } from "@playwright/test";
import { existsSync } from "node:fs";
import { rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

export { expect };
export type { Page } from "@playwright/test";

const e2eDir = fileURLToPath(new URL(".", import.meta.url));
const uiDir = path.resolve(e2eDir, "..");
const repoRoot = path.resolve(uiDir, "..");
const basePort = Number.parseInt(process.env.GLEAN_E2E_BASE_PORT ?? "18080", 10);

type WorkerFixtures = {
  workerBaseURL: string;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pythonCommand(): { command: string; args: string[] } {
  const venvPython = path.join(
    repoRoot,
    ".venv",
    process.platform === "win32" ? "Scripts\\python.exe" : "bin/python",
  );
  if (existsSync(venvPython)) {
    return { command: venvPython, args: ["e2e/_server.py"] };
  }
  return {
    command: process.platform === "win32" ? "uv.exe" : "uv",
    args: ["run", "python", "e2e/_server.py"],
  };
}

async function waitForServer(
  baseURL: string,
  server: ChildProcessWithoutNullStreams,
  logs: string[],
): Promise<void> {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`E2E server exited early with code ${server.exitCode}:\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${baseURL}/healthz`);
      if (response.ok) return;
    } catch {
      // Server is still starting; keep polling until the deadline.
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for E2E server at ${baseURL}:\n${logs.join("")}`);
}

async function stopServer(server: ChildProcessWithoutNullStreams): Promise<void> {
  if (server.exitCode !== null) return;
  server.kill();
  const exited = new Promise<void>((resolve) => server.once("exit", () => resolve()));
  await Promise.race([exited, sleep(5_000)]);
  if (server.exitCode === null) {
    server.kill("SIGKILL");
  }
}

export const test = base.extend<object, WorkerFixtures>({
  workerBaseURL: [
    async ({}, use, workerInfo) => {
      const port = basePort + workerInfo.workerIndex;
      const baseURL = `http://127.0.0.1:${port}`;
      const stateDir = path.join(uiDir, "e2e", ".tmp", `worker-${workerInfo.workerIndex}`);
      await rm(stateDir, { recursive: true, force: true });

      const { command, args } = pythonCommand();
      const logs: string[] = [];
      const server = spawn(command, args, {
        cwd: uiDir,
        env: {
          ...process.env,
          GLEAN_E2E_PORT: String(port),
          GLEAN_E2E_STATE_DIR: stateDir,
          PYTHONUNBUFFERED: "1",
        },
      });
      server.stdout.on("data", (chunk: Buffer) => logs.push(chunk.toString()));
      server.stderr.on("data", (chunk: Buffer) => logs.push(chunk.toString()));

      await waitForServer(baseURL, server, logs);
      try {
        await use(baseURL);
      } finally {
        await stopServer(server);
      }
    },
    { scope: "worker" },
  ],
  baseURL: async ({ workerBaseURL }, use) => {
    await use(workerBaseURL);
  },
});
