import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  parsePythonVersion,
  pythonCandidates,
  supportsPython312,
} from "./python-runner.mjs";

test("parsePythonVersion extracts semantic version components", () => {
  assert.deepEqual(parsePythonVersion("Python 3.12.8\n"), [3, 12, 8]);
  assert.equal(parsePythonVersion("not a version"), null);
});

test("supportsPython312 enforces the minimum runtime", () => {
  assert.equal(supportsPython312("Python 3.12.0"), true);
  assert.equal(supportsPython312("Python 3.13.1"), true);
  assert.equal(supportsPython312("Python 3.11.9"), false);
});

test("pythonCandidates respects an explicitly configured interpreter", () => {
  const candidates = pythonCandidates("linux", "/opt/python/bin/python");
  assert.deepEqual(candidates[0], ["/opt/python/bin/python"]);
  assert.deepEqual(candidates.slice(2), [["python3.12"], ["python3"], ["python"]]);
  assert.match(candidates[1][0], /\.venv[\\/]bin[\\/]python$/);
});

test("the command-line runner invokes Python with the supplied arguments", () => {
  const runnerPath = fileURLToPath(new URL("./python-runner.mjs", import.meta.url));
  const result = spawnSync(
    process.execPath,
    [runnerPath, "-c", 'print("python-runner-ok")'],
    { encoding: "utf8", shell: false },
  );

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /python-runner-ok/);
});

