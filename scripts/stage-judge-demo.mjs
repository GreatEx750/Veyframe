import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EXPECTED_SHA256 = "1544a746e058666cfdcbaccb43fac338ec221bd36b39afa6ba73f9662ee23847";
const scriptPath = fileURLToPath(import.meta.url);
const repositoryRoot = resolve(dirname(scriptPath), "..");

function sha256(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

export async function stageJudgeDemo({
  source = resolve(repositoryRoot, "artifacts/verification/golden-export-20s.mp4"),
  destination = resolve(repositoryRoot, "apps/web/public/judge-demo.mp4"),
  expectedSha256 = EXPECTED_SHA256,
} = {}) {
  const sourceContents = await readFile(source);
  const sourceSha256 = sha256(sourceContents);
  if (sourceSha256 !== expectedSha256) {
    throw new Error("Judge demo fixture checksum does not match the packaged artifact.");
  }

  try {
    const destinationContents = await readFile(destination);
    if (sha256(destinationContents) === expectedSha256) {
      return { bytes: destinationContents.length, sha256: expectedSha256 };
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }

  await mkdir(dirname(destination), { recursive: true });
  await copyFile(source, destination);
  return { bytes: sourceContents.length, sha256: sourceSha256 };
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  stageJudgeDemo()
    .then(({ bytes }) => {
      process.stdout.write(`Judge demo video ready (${bytes} bytes).\n`);
    })
    .catch((error) => {
      process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
      process.exitCode = 1;
    });
}
