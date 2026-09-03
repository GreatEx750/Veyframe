import { spawnSync } from "node:child_process";
import path from "node:path";
import { pathToFileURL } from "node:url";

export function parsePythonVersion(version) {
  const match = /Python\s+(\d+)\.(\d+)\.(\d+)/.exec(version.trim());
  return match ? match.slice(1).map(Number) : null;
}

export function supportsPython312(version) {
  const parsed = parsePythonVersion(version);
  return parsed !== null && (parsed[0] > 3 || (parsed[0] === 3 && parsed[1] >= 12));
}

export function pythonCandidates(platform = process.platform, configured = process.env.PYTHON) {
  const candidates = configured ? [[configured]] : [];
  if (platform === "win32") {
    candidates.push([path.resolve(".venv", "Scripts", "python.exe")]);
    candidates.push(["py", "-3.12"]);
  } else {
    candidates.push([path.resolve(".venv", "bin", "python")]);
  }
  candidates.push(["python3.12"], ["python3"], ["python"]);
  return candidates;
}

export function findPython312(candidates = pythonCandidates()) {
  for (const [command, ...prefix] of candidates) {
    const probe = spawnSync(command, [...prefix, "--version"], {
      encoding: "utf8",
      shell: false,
    });
    const output = `${probe.stdout ?? ""}${probe.stderr ?? ""}`;
    if (probe.status === 0 && supportsPython312(output)) {
      return { command, prefix };
    }
  }
  return null;
}

function main(args) {
  const python = findPython312();
  if (python === null) {
    console.error("DemoDirector requires Python 3.12 or newer. Set PYTHON to a compatible interpreter.");
    return 1;
  }

  const result = spawnSync(python.command, [...python.prefix, ...args], {
    stdio: "inherit",
    shell: false,
  });
  return result.status ?? 1;
}

const invokedPath = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : null;
if (invokedPath === import.meta.url) {
  process.exitCode = main(process.argv.slice(2));
}

