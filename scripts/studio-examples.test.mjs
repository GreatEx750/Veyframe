import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const assets = {
  "northstar-product-20s.mp4": "934a2dd8fa93b3e2259ce8a9e3e81fab2ce60a0f30f79c1f3458b1d457a99b57",
  "northstar-product-20s.jpg": "243558d877a3e14be7765fa1cccaa20b9e2e8308389b81e5050c6b53bc9f3e2b",
  "northstar-presentation-20s.mp4": "a0974fb0453af5ff1824ee3ed1fb9dcb1e4f46797f92653fa78eb63e2800908d",
  "northstar-presentation-20s.jpg": "e2bee156b30e8194f1b46ba89e3c46d2c6215ea9cd4749d1e739af6394dce711",
};

test("Studio ships both verified example videos and their posters", async () => {
  for (const [filename, expected] of Object.entries(assets)) {
    const bytes = await readFile(new URL(`../apps/web/public/examples/${filename}`, import.meta.url));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), expected, filename);
    if (filename.endsWith(".mp4")) {
      assert.ok(bytes.indexOf(Buffer.from("moov")) < bytes.indexOf(Buffer.from("mdat")), "Playback metadata must precede video data");
    }
  }
});
