import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const desktop = path.resolve(here, "..");
const project = path.resolve(desktop, "..");
const dataDir = path.join(tmpdir(), "math-grader-desktop-demo-data");
const python = process.env.MATH_GRADER_PYTHON || "python3";

const service = spawn(python, ["-m", "local_service", "--host", "127.0.0.1", "--port", "8765", "--data-dir", dataDir], {
  cwd: project,
  stdio: "inherit",
  env: process.env,
});
const web = spawn("npm", ["run", "dev"], { cwd: desktop, stdio: "inherit", env: process.env });

function stop(code = 0) {
  service.kill("SIGTERM");
  web.kill("SIGTERM");
  process.exitCode = code;
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => stop(0));
service.on("exit", (code) => { if (code && code !== 0) stop(code); });
web.on("exit", (code) => { if (code && code !== 0) stop(code); });
