import { mkdir, copyFile, access } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(root, "apps/web/public/landing");
await mkdir(output, { recursive: true });
await mkdir(path.join(root, "apps/web/public/brand"), { recursive: true });
await copyFile(path.join(root, "artifacts/brand/veyframe/veyframe-icon-concept.png"),
  path.join(root, "apps/web/public/brand/veyframe-icon.png"));

function ffmpeg(args) {
  const result = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: "inherit" });
  if (result.status !== 0) throw new Error("Landing sample encoding failed");
}

const samples = [
  ["product", "apps/web/public/examples/northstar-product-20s.mp4", 3],
  ["presentation", "apps/web/public/examples/northstar-presentation-20s.mp4", 2],
  ["spotlight", "artifacts/cloud-new-key-smoke/spotlight/cloud-export.mp4", 5],
  ["short", "artifacts/landing-short-google/short-google-45s.mp4", 5],
];
for (const [mode, relative, start] of samples) {
  if (process.argv.includes("--short-only") && mode !== "short") continue;
  const input = path.join(root, relative);
  await access(input);
  const preview = path.join(output, `${mode}-preview.mp4`);
  const scale = mode === "short" ? "scale=720:1280" : "scale=1280:720";
  ffmpeg(["-ss", String(start), "-i", input, "-t", "8", "-an", "-vf", scale,
    "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", preview]);
  const posterName = mode === "short" ? "short-google-editorial" : mode;
  ffmpeg(["-i", preview, "-frames:v", "1", "-update", "1", path.join(output, `${posterName}-poster.jpg`)]);
  if (mode === "spotlight" || mode === "short") {
    ffmpeg(["-i", input, "-vf", scale, "-c:v", "libx264", "-preset", "fast",
      "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", path.join(output, `${mode}-example.mp4`)]);
  }
  console.log(`Prepared ${mode} landing sample`);
}
