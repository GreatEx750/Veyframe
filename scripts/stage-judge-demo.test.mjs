import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { stageJudgeDemo } from "./stage-judge-demo.mjs";

test("stageJudgeDemo copies only the expected packaged fixture", async () => {
  const directory = await mkdtemp(join(tmpdir(), "demodirector-judge-video-"));
  const source = join(directory, "fixture.mp4");
  const destination = join(directory, "public", "judge-demo.mp4");
  const contents = Buffer.from("trusted-video-fixture");
  const expectedSha256 = createHash("sha256").update(contents).digest("hex");

  try {
    await writeFile(source, contents);
    const result = await stageJudgeDemo({ source, destination, expectedSha256 });

    assert.equal(result.bytes, contents.length);
    assert.equal(result.sha256, expectedSha256);
    assert.deepEqual(await readFile(destination), contents);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("stageJudgeDemo rejects an unexpected fixture without creating the public asset", async () => {
  const directory = await mkdtemp(join(tmpdir(), "demodirector-judge-video-"));
  const source = join(directory, "fixture.mp4");
  const destination = join(directory, "public", "judge-demo.mp4");

  try {
    await writeFile(source, "unexpected");
    await assert.rejects(
      stageJudgeDemo({ source, destination, expectedSha256: "0".repeat(64) }),
      /checksum does not match/,
    );
    await assert.rejects(readFile(destination), /ENOENT/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
