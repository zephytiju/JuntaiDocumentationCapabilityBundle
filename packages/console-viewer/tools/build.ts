import { execFileSync } from "node:child_process";
import { cp, mkdir, rm } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const dist = new URL("../dist", import.meta.url);
await rm(dist, { recursive: true, force: true });
execFileSync(process.execPath, ["./node_modules/typescript/bin/tsc", "-p", "tsconfig.json"], {
  cwd: root,
  stdio: "inherit",
});
await mkdir(dist, { recursive: true });
await cp(new URL("../src/styles.css", import.meta.url), new URL("../dist/styles.css", import.meta.url));
