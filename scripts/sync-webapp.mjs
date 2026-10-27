// Keep Python-only hosting and the backend fallback on the exact same frontend build.
import { existsSync, realpathSync, rmSync, cpSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const source = resolve(root, "frontend/dist");
const parent = realpathSync(resolve(root, "backend/app"));
const target = resolve(parent, "webapp");
if (!existsSync(resolve(source, "index.html"))) throw new Error("Frontend build missing.");
// Never remove a symlink/junction or a path outside the known generated directory.
if (dirname(target) !== parent || (existsSync(target) && realpathSync(target) !== target)) {
  throw new Error("Refusing to replace an unexpected webapp directory.");
}
rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
console.log("Synced the verified frontend build to backend/app/webapp.");
